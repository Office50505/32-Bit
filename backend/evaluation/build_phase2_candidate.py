"""Build the scientifically reviewed 150-claim Phase 2 gold evaluation set.

The labels in this file are authored benchmark rules. Source values are read from
checksum-frozen PubChem responses and sealed ChEMBL snapshots; the application
under test is never called to create a label.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(__file__).resolve().parent / "phase2_150_claims"
DATASET_PATH = OUTPUT_DIR / "claims.jsonl"
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"
PUBCHEM_ROOT = PROJECT_ROOT / "data/snapshots/pubchem-compounds"
CHEMBL_DATABASE = PROJECT_ROOT / "data/runtime/evidence/dynamic-chembl.sqlite"

ASPIRIN_SNAPSHOT = "chembl-api-37-chembl25-chembl221-0e2fa90fdf68"
IMATINIB_SNAPSHOT = "chembl-api-37-imatinib-abl1-smoke"
POLICY_REF = "docs/phase-2-evidence-contract.md#2-verdict-contract"


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_pubchem_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for manifest_path in sorted(PUBCHEM_ROOT.glob("*/manifest.json")):
        response_path = manifest_path.with_name("response.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        response_bytes = response_path.read_bytes()
        response_sha = sha256_bytes(response_bytes)
        if response_sha != manifest["raw_sha256"]:
            raise RuntimeError(f"PubChem checksum mismatch: {response_path}")
        properties = json.loads(response_bytes)["PropertyTable"]["Properties"][0]
        records.append(
            {
                "manifest": manifest,
                "properties": properties,
                "snapshot_id": f"pubchem-pug-cid-{manifest['cid']}@{response_sha[:12]}",
                "raw_record_sha256": response_sha,
                "manifest_path": manifest_path.relative_to(PROJECT_ROOT).as_posix(),
            }
        )
    records.sort(key=lambda item: (item["properties"]["Title"].casefold(), item["manifest"]["cid"]))
    if len(records) != 18:
        raise RuntimeError(f"expected 18 frozen PubChem records, found {len(records)}")
    return records


def load_snapshot_metadata(connection: sqlite3.Connection, snapshot_id: str) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT snapshot_id, source_name, source_version, source_sha256,
               content_sha256, scope_json, created_at
        FROM snapshots WHERE snapshot_id = ?
        """,
        (snapshot_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"missing required ChEMBL snapshot: {snapshot_id}")
    return dict(row)


def load_activity_rows(connection: sqlite3.Connection, snapshot_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT a.snapshot_id, a.activity_id, a.assay_id, a.measurement_type,
               a.standard_relation, a.standard_value, a.standard_unit,
               a.activity_outcome, a.data_validity_comment, a.potential_duplicate,
               a.raw_record_sha256, s.assay_type, s.organism,
               s.target_confidence_score, s.paper_id, s.conditions_json,
               p.retraction_status, m.preferred_name AS molecule_name,
               m.inchikey, t.target_id, t.preferred_name AS target_name,
               t.gene_symbol
        FROM activities a
        JOIN assays s ON s.snapshot_id = a.snapshot_id AND s.assay_id = a.assay_id
        JOIN molecules m
          ON m.snapshot_id = a.snapshot_id AND m.inchikey = a.molecule_inchikey
        JOIN targets t ON t.snapshot_id = s.snapshot_id AND t.target_id = s.target_id
        LEFT JOIN papers p ON p.snapshot_id = s.snapshot_id AND p.paper_id = s.paper_id
        WHERE a.snapshot_id = ?
        ORDER BY a.measurement_type, a.standard_value, a.activity_id
        """,
        (snapshot_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def clean_activity_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row["standard_value"] is not None
        and row["standard_unit"] == "nM"
        and not row["potential_duplicate"]
        and not row["data_validity_comment"]
        and row["retraction_status"] == "CLEAR"
        and (row["target_confidence_score"] or 0) >= 8
    ]


def pubchem_citation(
    record: dict[str, Any],
    *,
    locator: str,
    stance: str,
    eligibility: str = "DECISIVE",
) -> dict[str, Any]:
    properties = record["properties"]
    return {
        "evidence_id": f"{record['snapshot_id']}:PROPERTY:{locator}",
        "source_type": "PUBCHEM_COMPOUND",
        "source_record_id": f"CID:{properties['CID']}",
        "snapshot_id": record["snapshot_id"],
        "raw_record_sha256": record["raw_record_sha256"],
        "locator": f"PropertyTable.Properties[0].{locator}",
        "basis": "STRUCTURED_RECORD",
        "expected_stance": stance,
        "eligibility": eligibility,
        "retraction_status": "NOT_APPLICABLE",
    }


def activity_citation(
    row: dict[str, Any],
    *,
    stance: str,
    eligibility: str = "DECISIVE",
) -> dict[str, Any]:
    return {
        "evidence_id": f"{row['snapshot_id']}:CHEMBL:ACTIVITY:{row['activity_id']}",
        "source_type": "CHEMBL_ACTIVITY",
        "source_record_id": str(row["activity_id"]),
        "snapshot_id": row["snapshot_id"],
        "raw_record_sha256": row["raw_record_sha256"],
        "locator": f"activity_id={row['activity_id']}; assay_id={row['assay_id']}",
        "basis": "EXPERIMENTAL",
        "expected_stance": stance,
        "eligibility": eligibility,
        "retraction_status": row["retraction_status"] or "UNKNOWN",
    }


def statement(
    *,
    text: str,
    claim_type: str,
    verdict: str,
    rationale: str,
    reason_codes: list[str] | None = None,
    citations: list[dict[str, Any]] | None = None,
    molecule_mentions: list[str] | None = None,
    target_mentions: list[str] | None = None,
    endpoint_mentions: list[str] | None = None,
    resolution_status: str = "RESOLVED",
    resolution_reason_codes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "statement_id": "S1",
        "text": text,
        "claim_type": claim_type,
        "molecule_mentions": molecule_mentions or [],
        "target_mentions": target_mentions or [],
        "endpoint_mentions": endpoint_mentions or [],
        "expected_resolution": {
            "status": resolution_status,
            "reason_codes": resolution_reason_codes or [],
        },
        "expected_verdict": verdict,
        "expected_reason_codes": reason_codes or [],
        "expected_citations": citations or [],
        "rationale": rationale,
    }


def case(
    statement_value: dict[str, Any],
    *,
    category: str,
    difficulty: str,
    leakage_group: str,
    decision_basis_refs: list[str] | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "claim": statement_value["text"],
        "category": category,
        "difficulty": difficulty,
        "leakage_group": leakage_group,
        "tags": tags or [],
        "decision_basis_refs": decision_basis_refs
        or [citation["evidence_id"] for citation in statement_value["expected_citations"]]
        or [POLICY_REF],
        "expected_decomposition": [statement_value],
        "annotation_status": "CANDIDATE",
    }


def property_cases(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    supported: list[dict[str, Any]] = []
    contradicted: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        properties = record["properties"]
        title = properties["Title"]
        formula = properties["MolecularFormula"]
        next_formula = records[(index + 1) % len(records)]["properties"]["MolecularFormula"]
        supported_statement = statement(
            text=f"The molecular formula of {title} is {formula}.",
            claim_type="COMPUTED_PROPERTY",
            verdict="SUPPORTED",
            rationale="The asserted formula exactly matches the frozen PubChem compound record.",
            citations=[pubchem_citation(record, locator="MolecularFormula", stance="SUPPORTS")],
            molecule_mentions=[title],
        )
        supported.append(
            case(
                supported_statement,
                category="STRUCTURED_PROPERTY",
                difficulty="EASY",
                leakage_group=f"PUBCHEM:CID:{properties['CID']}",
                tags=["formula", "pubchem", "exact-match"],
            )
        )
        contradicted_statement = statement(
            text=f"The molecular formula of {title} is {next_formula}.",
            claim_type="COMPUTED_PROPERTY",
            verdict="CONTRADICTED",
            rationale=(
                f"The frozen record reports {formula}, which directly contradicts the asserted "
                f"formula {next_formula}."
            ),
            citations=[pubchem_citation(record, locator="MolecularFormula", stance="CONTRADICTS")],
            molecule_mentions=[title],
        )
        contradicted.append(
            case(
                contradicted_statement,
                category="STRUCTURED_PROPERTY",
                difficulty="EASY",
                leakage_group=f"PUBCHEM:CID:{properties['CID']}",
                tags=["formula", "pubchem", "direct-contradiction"],
            )
        )

    by_title = {record["properties"]["Title"]: record for record in records}
    l_alanine = by_title["L-Alanine"]
    d_alanine = by_title["D-Alanine"]
    stereo_citations_support = [
        pubchem_citation(l_alanine, locator="MolecularFormula", stance="SUPPORTS"),
        pubchem_citation(d_alanine, locator="MolecularFormula", stance="SUPPORTS"),
    ]
    supported.append(
        case(
            statement(
                text="L-alanine and D-alanine have the same molecular formula.",
                claim_type="LITERATURE_FACT",
                verdict="SUPPORTED",
                rationale=(
                    "Both frozen records report C3H7NO2 while retaining distinct "
                    "stereochemical identities."
                ),
                citations=stereo_citations_support,
                molecule_mentions=["L-alanine", "D-alanine"],
            ),
            category="STEREOCHEMISTRY_IDENTITY",
            difficulty="MEDIUM",
            leakage_group="PUBCHEM:ALANINE-ENANTIOMERS",
            tags=["stereochemistry", "enantiomer", "formula"],
        )
    )
    supported.append(
        case(
            statement(
                text="L-alanine and D-alanine have different InChIKeys.",
                claim_type="LITERATURE_FACT",
                verdict="SUPPORTED",
                rationale="The stereochemical layer differs in the two frozen InChIKeys.",
                citations=[
                    pubchem_citation(l_alanine, locator="InChIKey", stance="SUPPORTS"),
                    pubchem_citation(d_alanine, locator="InChIKey", stance="SUPPORTS"),
                ],
                molecule_mentions=["L-alanine", "D-alanine"],
            ),
            category="STEREOCHEMISTRY_IDENTITY",
            difficulty="MEDIUM",
            leakage_group="PUBCHEM:ALANINE-ENANTIOMERS",
            tags=["stereochemistry", "enantiomer", "inchikey"],
        )
    )
    contradicted.append(
        case(
            statement(
                text="L-alanine and D-alanine have the same InChIKey.",
                claim_type="LITERATURE_FACT",
                verdict="CONTRADICTED",
                rationale="Their frozen InChIKeys have different stereochemical layers.",
                citations=[
                    pubchem_citation(l_alanine, locator="InChIKey", stance="CONTRADICTS"),
                    pubchem_citation(d_alanine, locator="InChIKey", stance="CONTRADICTS"),
                ],
                molecule_mentions=["L-alanine", "D-alanine"],
            ),
            category="STEREOCHEMISTRY_IDENTITY",
            difficulty="MEDIUM",
            leakage_group="PUBCHEM:ALANINE-ENANTIOMERS",
            tags=["stereochemistry", "enantiomer", "inchikey"],
        )
    )
    contradicted.append(
        case(
            statement(
                text="L-alanine and D-alanine have different molecular formulas.",
                claim_type="LITERATURE_FACT",
                verdict="CONTRADICTED",
                rationale="Both frozen records report the same formula, C3H7NO2.",
                citations=[
                    pubchem_citation(l_alanine, locator="MolecularFormula", stance="CONTRADICTS"),
                    pubchem_citation(d_alanine, locator="MolecularFormula", stance="CONTRADICTS"),
                ],
                molecule_mentions=["L-alanine", "D-alanine"],
            ),
            category="STEREOCHEMISTRY_IDENTITY",
            difficulty="MEDIUM",
            leakage_group="PUBCHEM:ALANINE-ENANTIOMERS",
            tags=["stereochemistry", "enantiomer", "formula"],
        )
    )
    return supported, contradicted


def activity_cases(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    supported: list[dict[str, Any]] = []
    contradicted: list[dict[str, Any]] = []
    selected_supported = rows[:25]
    selected_contradicted = rows[:20]
    if len(selected_supported) != 25:
        raise RuntimeError("not enough eligible activity rows for the benchmark")

    for row in selected_supported:
        relation = row["standard_relation"] or "="
        text_relation = "of" if relation == "=" else f"{relation}"
        value = float(row["standard_value"])
        text = (
            f"ChEMBL activity record {row['activity_id']} reports a {row['molecule_name']} "
            f"{row['measurement_type']} {text_relation} {value:g} {row['standard_unit']} against "
            f"{row['gene_symbol'] or row['target_name']}."
        )
        supported.append(
            case(
                statement(
                    text=text,
                    claim_type="BIOLOGICAL_ACTIVITY",
                    verdict="SUPPORTED",
                    rationale=(
                        "The claim reproduces the endpoint, relation, value, and target in the "
                        "cited activity row."
                    ),
                    citations=[activity_citation(row, stance="SUPPORTS")],
                    molecule_mentions=[row["molecule_name"]],
                    target_mentions=[row["gene_symbol"] or row["target_name"]],
                    endpoint_mentions=[row["measurement_type"]],
                ),
                category="RECORD_SPECIFIC_ACTIVITY",
                difficulty="MEDIUM",
                leakage_group=f"CHEMBL:ACTIVITY:{row['activity_id']}",
                tags=["chembl", "activity", row["measurement_type"].casefold()],
            )
        )

    for row in selected_contradicted:
        observed = float(row["standard_value"])
        asserted = observed * 100
        text = (
            f"ChEMBL activity record {row['activity_id']} reports a {row['molecule_name']} "
            f"{row['measurement_type']} of {asserted:g} {row['standard_unit']} against "
            f"{row['gene_symbol'] or row['target_name']}."
        )
        contradicted.append(
            case(
                statement(
                    text=text,
                    claim_type="BIOLOGICAL_ACTIVITY",
                    verdict="CONTRADICTED",
                    rationale=(
                        f"The cited row reports {row['standard_relation'] or '='} {observed:g} "
                        f"{row['standard_unit']}, not {asserted:g} {row['standard_unit']}."
                    ),
                    citations=[activity_citation(row, stance="CONTRADICTS")],
                    molecule_mentions=[row["molecule_name"]],
                    target_mentions=[row["gene_symbol"] or row["target_name"]],
                    endpoint_mentions=[row["measurement_type"]],
                ),
                category="RECORD_SPECIFIC_ACTIVITY",
                difficulty="MEDIUM",
                leakage_group=f"CHEMBL:ACTIVITY:{row['activity_id']}",
                tags=["chembl", "activity", "direct-contradiction"],
            )
        )
    return supported, contradicted


def insufficient_cases(
    records: list[dict[str, Any]],
    all_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    by_title = {record["properties"]["Title"]: record for record in records}

    for title in [
        "Aspirin",
        "Benzene",
        "Caffeine",
        "D-Glucose",
        "Ethanol",
        "Imatinib",
        "L-Alanine",
        "Sulfuric Acid",
    ]:
        record = by_title[title]
        xlogp = record["properties"].get("XLogP")
        text = f"Because {title} has a reported XLogP of {xlogp}, it inhibits ABL1."
        cases.append(
            case(
                statement(
                    text=text,
                    claim_type="BIOLOGICAL_ACTIVITY",
                    verdict="INSUFFICIENT_EVIDENCE",
                    rationale=(
                        "A physicochemical property record cannot establish target inhibition."
                    ),
                    reason_codes=["COMPUTED_EVIDENCE_ONLY"],
                    citations=[
                        pubchem_citation(
                            record,
                            locator="XLogP",
                            stance="NEUTRAL",
                            eligibility="INSPECTED",
                        )
                    ],
                    molecule_mentions=[title],
                    target_mentions=["ABL1"],
                ),
                category="COMPUTED_PROPERTY_MISUSE",
                difficulty="HARD",
                leakage_group=f"COMPUTED_ONLY:CID:{record['properties']['CID']}",
                tags=["computed-only", "activity", "abstention"],
            )
        )

    retracted = next(row for row in all_rows if str(row["activity_id"]) == "16595061")
    retracted_claims = [
        (
            "Retracted ChEMBL activity record 16595061 proves that imatinib has an ABL1 "
            "IC50 of 300 nM."
        ),
        "Activity record 16595061 is sufficient evidence that imatinib inhibits ABL1 at 300 nM.",
        "The retracted source behind activity 16595061 can establish imatinib's ABL1 potency.",
        "Imatinib's ABL1 IC50 is conclusively 300 nM solely because record 16595061 reports it.",
    ]
    for text in retracted_claims:
        cases.append(
            case(
                statement(
                    text=text,
                    claim_type="BIOLOGICAL_ACTIVITY",
                    verdict="INSUFFICIENT_EVIDENCE",
                    rationale=(
                        "The cited activity is linked to a retracted paper and is excluded from "
                        "deciding the verdict."
                    ),
                    reason_codes=["RETRACTED_EVIDENCE_EXCLUDED"],
                    citations=[
                        activity_citation(retracted, stance="NEUTRAL", eligibility="EXCLUDED")
                    ],
                    molecule_mentions=["Imatinib"],
                    target_mentions=["ABL1"],
                    endpoint_mentions=["IC50"],
                ),
                category="RETRACTED_EVIDENCE",
                difficulty="HARD",
                leakage_group="CHEMBL:RETRACTED:ACTIVITY:16595061",
                tags=["retraction", "exclusion", "abstention"],
            )
        )

    conflict_low = next(row for row in all_rows if str(row["activity_id"]) == "19161692")
    conflict_high = next(row for row in all_rows if str(row["activity_id"]) == "26276619")
    for threshold in [50, 100, 250, 500, 1000, 2500, 5000, 7500]:
        text = f"Imatinib inhibits human ABL1 with an IC50 below {threshold} nM."
        cases.append(
            case(
                statement(
                    text=text,
                    claim_type="BIOLOGICAL_ACTIVITY",
                    verdict="INSUFFICIENT_EVIDENCE",
                    rationale=(
                        "Direct ChEMBL assays under matching typed context fall on opposite sides "
                        "of the asserted threshold, so the benchmark requires abstention."
                    ),
                    reason_codes=["CONFLICTING_ASSAYS"],
                    citations=[
                        activity_citation(conflict_low, stance="SUPPORTS", eligibility="INSPECTED"),
                        activity_citation(
                            conflict_high, stance="CONTRADICTS", eligibility="INSPECTED"
                        ),
                    ],
                    molecule_mentions=["Imatinib"],
                    target_mentions=["human ABL1"],
                    endpoint_mentions=["IC50"],
                ),
                category="ASSAY_DISAGREEMENT",
                difficulty="HARD",
                leakage_group="CHEMBL:IMATINIB-ABL1:CONFLICT-SF9",
                tags=["conflict", "threshold", "abstention"],
            )
        )

    outside_claims = [
        ("Gefitinib inhibits EGFR with an IC50 below 100 nM.", "Gefitinib", "EGFR"),
        ("Erlotinib inhibits EGFR with an IC50 below 100 nM.", "Erlotinib", "EGFR"),
        ("Sildenafil inhibits PDE5A with nanomolar potency.", "Sildenafil", "PDE5A"),
        ("Caffeine antagonizes the adenosine A2A receptor.", "Caffeine", "ADORA2A"),
        ("Ibuprofen inhibits human PTGS2.", "Ibuprofen", "PTGS2"),
        ("Acetaminophen inhibits human PTGS2.", "Acetaminophen", "PTGS2"),
        ("Metformin directly activates AMPK with an EC50 below 10 uM.", "Metformin", "AMPK"),
        ("Warfarin inhibits VKORC1 with a Ki below 1 uM.", "Warfarin", "VKORC1"),
        ("Atorvastatin inhibits HMGCR with nanomolar potency.", "Atorvastatin", "HMGCR"),
        ("Omeprazole inhibits ATP4A.", "Omeprazole", "ATP4A"),
        ("Fluoxetine binds SLC6A4 with a Ki below 10 nM.", "Fluoxetine", "SLC6A4"),
        ("Albuterol activates ADRB2 with an EC50 below 100 nM.", "Albuterol", "ADRB2"),
        ("Morphine binds OPRM1 with nanomolar affinity.", "Morphine", "OPRM1"),
        ("Doxycycline binds the bacterial 30S ribosomal subunit.", "Doxycycline", "30S ribosome"),
        ("Remdesivir inhibits the SARS-CoV-2 RNA polymerase.", "Remdesivir", "SARS-CoV-2 RdRp"),
    ]
    coverage_refs = [
        f"snapshot:{ASPIRIN_SNAPSHOT}:scope_json",
        f"snapshot:{IMATINIB_SNAPSHOT}:scope_json",
    ]
    for text, molecule, target in outside_claims:
        cases.append(
            case(
                statement(
                    text=text,
                    claim_type="BIOLOGICAL_ACTIVITY",
                    verdict="INSUFFICIENT_EVIDENCE",
                    rationale=(
                        "The molecule-target pair is outside the frozen assay snapshot scope; "
                        "absence is not contradiction."
                    ),
                    reason_codes=["OUTSIDE_SNAPSHOT_COVERAGE"],
                    molecule_mentions=[molecule],
                    target_mentions=[target],
                    resolution_status="UNRESOLVED",
                    resolution_reason_codes=["OUTSIDE_SNAPSHOT_COVERAGE"],
                ),
                category="SNAPSHOT_COVERAGE",
                difficulty="MEDIUM",
                leakage_group=f"OUTSIDE:{molecule.casefold()}:{target.casefold()}",
                decision_basis_refs=coverage_refs,
                tags=["coverage", "absence-not-contradiction", "abstention"],
            )
        )

    unresolved_claims = [
        ("XZ-481 inhibits ABL1 with an IC50 below 20 nM.", "XZ-481", "ABL1"),
        ("Aspirin inhibits kinase QQQ9 with nanomolar potency.", "Aspirin", "QQQ9"),
        ("Compound ALPHA-NULL binds PTGS1 with a Kd of 5 nM.", "ALPHA-NULL", "PTGS1"),
        ("Imatinibb inhibits ABL1 at 30 nM.", "Imatinibb", "ABL1"),
        ("Molecule 000-UNKNOWN activates receptor RCP-X.", "000-UNKNOWN", "RCP-X"),
    ]
    for text, molecule, target in unresolved_claims:
        cases.append(
            case(
                statement(
                    text=text,
                    claim_type="BIOLOGICAL_ACTIVITY",
                    verdict="INSUFFICIENT_EVIDENCE",
                    rationale=(
                        "At least one required molecular or target identity cannot be resolved "
                        "deterministically."
                    ),
                    reason_codes=["UNRESOLVED_ENTITY"],
                    molecule_mentions=[molecule],
                    target_mentions=[target],
                    resolution_status="UNRESOLVED",
                    resolution_reason_codes=[f"UNRESOLVED_ENTITY:{molecule}|{target}"],
                ),
                category="ENTITY_RESOLUTION",
                difficulty="MEDIUM",
                leakage_group=f"UNRESOLVED:{molecule.casefold()}:{target.casefold()}",
                decision_basis_refs=[POLICY_REF],
                tags=["unresolved", "entity", "abstention"],
            )
        )

    ambiguous_claims = [
        ("Alanine inhibits ABL1 with an IC50 below 1 uM.", "Alanine"),
        ("Lactic acid inhibits PTGS1.", "Lactic acid"),
        ("2-butanol binds ABL1.", "2-butanol"),
        ("Thalidomide inhibits PTGS1.", "Thalidomide"),
        ("Warfarin binds ABL1 with nanomolar affinity.", "Warfarin"),
    ]
    for text, molecule in ambiguous_claims:
        cases.append(
            case(
                statement(
                    text=text,
                    claim_type="BIOLOGICAL_ACTIVITY",
                    verdict="INSUFFICIENT_EVIDENCE",
                    rationale=(
                        "The claim does not identify the relevant stereochemical molecular form."
                    ),
                    reason_codes=["AMBIGUOUS_ENTITY"],
                    molecule_mentions=[molecule],
                    target_mentions=["ABL1" if "ABL1" in text else "PTGS1"],
                    resolution_status="AMBIGUOUS",
                    resolution_reason_codes=[f"AMBIGUOUS_MOLECULE:{molecule}"],
                ),
                category="ENTITY_RESOLUTION",
                difficulty="HARD",
                leakage_group=f"AMBIGUOUS:{molecule.casefold()}",
                decision_basis_refs=[POLICY_REF],
                tags=["ambiguous", "stereochemistry", "abstention"],
            )
        )

    mechanism_templates = [
        "Imatinib downregulates STAT5 transcription by directly inhibiting ABL1.",
        "Imatinib causes apoptosis through an ABL1-dependent mitochondrial pathway.",
        "Imatinib blocks ABL1 nuclear translocation in every human cell type.",
        "Imatinib suppresses MAPK signaling exclusively through ABL1.",
        "Imatinib activates autophagy because it binds ABL1.",
    ]
    inspected = next(row for row in all_rows if str(row["activity_id"]) == "19161692")
    for text in mechanism_templates:
        cases.append(
            case(
                statement(
                    text=text,
                    claim_type="MECHANISM",
                    verdict="INSUFFICIENT_EVIDENCE",
                    rationale=(
                        "A target activity row does not directly establish the asserted "
                        "downstream mechanism."
                    ),
                    reason_codes=["NO_DIRECT_EVIDENCE"],
                    citations=[
                        activity_citation(inspected, stance="NEUTRAL", eligibility="INSPECTED")
                    ],
                    molecule_mentions=["Imatinib"],
                    target_mentions=["ABL1"],
                ),
                category="MECHANISM_WITHOUT_PASSAGE",
                difficulty="HARD",
                leakage_group="MECHANISM:IMATINIB-ABL1:NO-PASSAGE",
                tags=["mechanism", "assay-not-mechanism", "abstention"],
            )
        )

    if len(cases) != 50:
        raise RuntimeError(f"expected 50 insufficient-evidence statements, built {len(cases)}")
    return cases


def out_of_scope_cases() -> list[dict[str, Any]]:
    groups: list[tuple[str, str, list[str]]] = [
        (
            "CLINICAL_PREDICTION_OUT_OF_SCOPE",
            "CLINICAL_PREDICTION",
            [
                "Aspirin is clinically effective for every patient with heart disease.",
                "Imatinib is clinically effective for all cancers that express ABL1.",
                "Caffeine is an effective clinical treatment for fatigue disorders.",
                "D-alanine is clinically effective for treating metabolic disease.",
                "Benzene is clinically useful as a treatment for leukemia.",
                "Hydrogen peroxide is clinically effective for internal infections.",
                "Sulfuric acid has clinical efficacy against tumors.",
                "Ethanol is an effective clinical treatment for anxiety.",
            ],
        ),
        (
            "SAFETY_PREDICTION_OUT_OF_SCOPE",
            "SAFETY_PREDICTION",
            [
                "Aspirin is safe for every adult at any dose.",
                "Imatinib has no side effects in humans.",
                "Caffeine is safe during every pregnancy.",
                "Benzene is non-toxic to humans.",
                "Hydrogen peroxide is safe to drink when diluted.",
                "Sulfuric acid is safe for skin contact at low concentration.",
                "Ethanol cannot cause organ toxicity.",
                "Sodium chloride is safe at any oral dose.",
            ],
        ),
        (
            "PERSONALIZED_ADVICE_OUT_OF_SCOPE",
            "PERSONALIZED_ADVICE",
            [
                "Should I take aspirin for my chest pain?",
                "Should I use imatinib based on my ABL1 test result?",
                "Which caffeine dose is safe for me?",
                "Can my child take hydrogen peroxide for an infection?",
                "Should the patient replace prescribed therapy with D-alanine?",
                "Choose an aspirin dose for this patient's genotype.",
                "Tell me whether I should stop imatinib because of side effects.",
            ],
        ),
        (
            "FUTURE_EFFICACY_OUT_OF_SCOPE",
            "FUTURE_EFFICACY",
            [
                "Imatinib will cure the next patient with an ABL1 mutation.",
                "Aspirin will prevent every future heart attack.",
                "Caffeine will cure fatigue in a future clinical trial.",
                "D-alanine will become an effective cancer therapy.",
                "Hydrogen peroxide will cure viral infections in humans.",
                "A molecule with high LogP will succeed as a future medicine.",
                "This newly drawn compound will be efficacious in patients.",
            ],
        ),
    ]
    cases: list[dict[str, Any]] = []
    for reason_code, category, texts in groups:
        for text in texts:
            cases.append(
                case(
                    statement(
                        text=text,
                        claim_type="CLINICAL_OR_SAFETY",
                        verdict="OUT_OF_SCOPE",
                        rationale=(
                            "The claim asks for clinical, safety, personalized, or "
                            "future-efficacy judgment outside the evidence contract."
                        ),
                        reason_codes=[reason_code],
                        resolution_status="NOT_REQUIRED",
                    ),
                    category=category,
                    difficulty="EASY" if category != "FUTURE_EFFICACY" else "MEDIUM",
                    leakage_group=f"SCOPE:{reason_code}",
                    decision_basis_refs=[POLICY_REF],
                    tags=["scope", "research-aid", "no-scientific-citation"],
                )
            )
    if len(cases) != 30:
        raise RuntimeError(f"expected 30 out-of-scope statements, built {len(cases)}")
    return cases


def combine_cases(
    supported: list[dict[str, Any]],
    out_of_scope: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    compounds: list[dict[str, Any]] = []
    for left, right in zip(supported[:15], out_of_scope[:15], strict=True):
        left_statement = dict(left["expected_decomposition"][0])
        right_statement = dict(right["expected_decomposition"][0])
        left_statement["statement_id"] = "S1"
        right_statement["statement_id"] = "S2"
        compounds.append(
            {
                "claim": f"{left['claim']} Also, {right['claim'][0].lower()}{right['claim'][1:]}",
                "category": "COMPOUND_CLAIM",
                "difficulty": "HARD",
                "leakage_group": left["leakage_group"],
                "tags": sorted(set([*left["tags"], *right["tags"], "decomposition"])),
                "decision_basis_refs": list(
                    dict.fromkeys([*left["decision_basis_refs"], *right["decision_basis_refs"]])
                ),
                "expected_decomposition": [left_statement, right_statement],
                "annotation_status": "CANDIDATE",
            }
        )
    return supported[15:], out_of_scope[15:], compounds


def finalize(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    finalized: list[dict[str, Any]] = []
    for index, item in enumerate(cases, start=1):
        leakage_group = item["leakage_group"]
        fold_index = int(hashlib.sha256(leakage_group.encode("utf-8")).hexdigest()[:8], 16) % 5
        finalized.append(
            {
                "claim_id": f"PL-EA-{index:03d}",
                "split": "LOCKED_EVALUATION",
                "fold": chr(ord("A") + fold_index),
                **item,
            }
        )
    return finalized


def build() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pubchem_records = load_pubchem_records()
    if not CHEMBL_DATABASE.exists():
        raise RuntimeError(f"missing sealed ChEMBL evidence database: {CHEMBL_DATABASE}")
    connection = sqlite3.connect(f"file:{CHEMBL_DATABASE}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        snapshot_metadata = [
            load_snapshot_metadata(connection, ASPIRIN_SNAPSHOT),
            load_snapshot_metadata(connection, IMATINIB_SNAPSHOT),
        ]
        aspirin_rows = load_activity_rows(connection, ASPIRIN_SNAPSHOT)
        imatinib_rows = load_activity_rows(connection, IMATINIB_SNAPSHOT)
    finally:
        connection.close()

    clean_aspirin = clean_activity_rows(aspirin_rows)
    clean_imatinib = clean_activity_rows(imatinib_rows)
    activity_pool = [*clean_aspirin, *clean_imatinib]
    all_rows = [*aspirin_rows, *imatinib_rows]

    property_supported, property_contradicted = property_cases(pubchem_records)
    activity_supported, activity_contradicted = activity_cases(activity_pool)
    supported = [*property_supported, *activity_supported]
    contradicted = [*property_contradicted, *activity_contradicted]
    insufficient = insufficient_cases(pubchem_records, all_rows)
    out_of_scope = out_of_scope_cases()
    if (len(supported), len(contradicted), len(insufficient), len(out_of_scope)) != (
        45,
        40,
        50,
        30,
    ):
        raise RuntimeError("unexpected base verdict distribution")

    supported, out_of_scope, compounds = combine_cases(supported, out_of_scope)
    cases = finalize([*supported, *contradicted, *insufficient, *out_of_scope, *compounds])
    if len(cases) != 150:
        raise RuntimeError(f"expected 150 claims, built {len(cases)}")

    statement_verdicts = Counter(
        statement_value["expected_verdict"]
        for item in cases
        for statement_value in item["expected_decomposition"]
    )
    statement_count = sum(len(item["expected_decomposition"]) for item in cases)
    pubchem_bundle_sha = sha256_bytes(
        canonical_json(
            [
                {
                    "cid": record["properties"]["CID"],
                    "raw_record_sha256": record["raw_record_sha256"],
                }
                for record in pubchem_records
            ]
        ).encode("utf-8")
    )
    dataset_bytes = "".join(
        f"{json.dumps(item, sort_keys=True, ensure_ascii=False)}\n" for item in cases
    ).encode("utf-8")
    manifest = {
        "dataset_id": "provenancelab-phase2-150-gold-v1",
        "schema_version": 1,
        "status": "GOLD",
        "claim_count": len(cases),
        "statement_count": statement_count,
        "compound_claim_count": sum(len(item["expected_decomposition"]) > 1 for item in cases),
        "verdict_distribution": dict(sorted(statement_verdicts.items())),
        "split": "LOCKED_EVALUATION",
        "training_use": "PROHIBITED",
        "research_aid_notice": (
            "Research aid only. This report summarizes available evidence and is not a "
            "prediction of clinical efficacy or safety."
        ),
        "dataset_sha256": sha256_bytes(dataset_bytes),
        "source_snapshots": [
            {
                "snapshot_id": metadata["snapshot_id"],
                "source_name": metadata["source_name"],
                "source_version": metadata["source_version"],
                "source_sha256": metadata["source_sha256"],
                "content_sha256": metadata["content_sha256"],
                "scope": json.loads(metadata["scope_json"]),
            }
            for metadata in snapshot_metadata
        ],
        "pubchem_bundle": {
            "record_count": len(pubchem_records),
            "bundle_sha256": pubchem_bundle_sha,
            "record_sha256s": {
                str(record["properties"]["CID"]): record["raw_record_sha256"]
                for record in pubchem_records
            },
        },
        "label_policy": POLICY_REF,
        "created_at": "2026-10-25T00:00:00+05:30",
        "scientific_review": {
            "decision": "APPROVED_AS_GOLD",
            "reviewer_role": "project owner",
            "review_date": "2026-10-25",
            "approved_dataset_sha256": sha256_bytes(dataset_bytes),
        },
    }
    return cases, manifest


def main() -> None:
    cases, manifest = build()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset_text = "".join(
        f"{json.dumps(item, sort_keys=True, ensure_ascii=False)}\n" for item in cases
    )
    DATASET_PATH.write_text(dataset_text, encoding="utf-8")
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {manifest['claim_count']} claims / {manifest['statement_count']} statements "
        f"to {DATASET_PATH} ({manifest['dataset_sha256']})"
    )


if __name__ == "__main__":
    main()
