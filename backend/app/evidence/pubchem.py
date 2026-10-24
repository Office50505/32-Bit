import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.evidence.retractions import FrozenRetractionIndex
from app.evidence.store import EvidenceStore, EvidenceStoreError, SnapshotSpec

PUBCHEM_CONCISE_COLUMNS = (
    "AID",
    "SID",
    "CID",
    "Activity Outcome",
    "Target Accession",
    "Target GeneID",
    "Activity Value [uM]",
    "Activity Name",
    "Assay Name",
    "Assay Type",
    "PubMed ID",
    "RNAi",
)


def _sha256(value: bytes | object) -> str:
    if isinstance(value, bytes):
        payload = value
    else:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _combined_source_hash(raw_files: dict[int, bytes], selection: object) -> str:
    digest = hashlib.sha256()
    digest.update(_sha256(selection).encode("ascii"))
    digest.update(b"\n")
    for aid, payload in sorted(raw_files.items()):
        digest.update(str(aid).encode("ascii"))
        digest.update(b"\0")
        digest.update(_sha256(payload).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class PubChemMoleculeSpec:
    cid: int
    inchikey: str
    canonical_smiles: str
    preferred_name: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PubChemTargetSpec:
    target_id: str
    preferred_name: str
    organism: str
    accession: str | None = None
    gene_symbol: str | None = None
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PubChemAssaySpec:
    aid: int
    target_id: str
    selected_cids: tuple[int, ...]
    conditions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PubChemImportResult:
    snapshot_id: str
    assay_count: int
    activity_count: int
    molecule_count: int
    target_count: int
    content_sha256: str


def _parse_concise(payload: bytes, expected_aid: int) -> list[dict[str, str]]:
    try:
        document = json.loads(payload)
        table = document["Table"]
        columns = table["Columns"]["Column"]
        rows = table["Row"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise EvidenceStoreError(
            f"invalid PubChem concise JSON for AID {expected_aid}"
        ) from error
    if not isinstance(columns, list) or not all(isinstance(column, str) for column in columns):
        raise EvidenceStoreError(f"PubChem AID {expected_aid} has invalid concise columns")
    missing = [column for column in PUBCHEM_CONCISE_COLUMNS if column not in columns]
    if missing:
        raise EvidenceStoreError(
            f"PubChem AID {expected_aid} is missing concise columns: {missing}"
        )
    if not isinstance(rows, list):
        raise EvidenceStoreError(f"PubChem AID {expected_aid} has no concise rows")
    parsed: list[dict[str, str]] = []
    for row in rows:
        cells = row.get("Cell") if isinstance(row, dict) else None
        if not isinstance(cells, list) or len(cells) != len(columns):
            raise EvidenceStoreError(
                f"PubChem AID {expected_aid} has a malformed concise row"
            )
        record = {column: str(value).strip() for column, value in zip(columns, cells, strict=True)}
        try:
            row_aid = int(record["AID"])
        except ValueError as error:
            raise EvidenceStoreError("PubChem concise row has a non-numeric AID") from error
        if row_aid != expected_aid:
            raise EvidenceStoreError(
                f"PubChem concise row AID {row_aid} does not match expected {expected_aid}"
            )
        parsed.append(record)
    return parsed


def _optional_int(value: str, *, field_name: str) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError as error:
        raise EvidenceStoreError(f"PubChem {field_name} must be an integer: {value}") from error


def _optional_float(value: str, *, field_name: str) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError as error:
        raise EvidenceStoreError(f"PubChem {field_name} must be numeric: {value}") from error


def import_pubchem_snapshot(
    store: EvidenceStore,
    *,
    snapshot_id: str,
    source_version: str,
    created_at: str,
    raw_files: dict[int, bytes],
    molecules: tuple[PubChemMoleculeSpec, ...],
    targets: tuple[PubChemTargetSpec, ...],
    assays: tuple[PubChemAssaySpec, ...],
    retraction_index: FrozenRetractionIndex,
    source_uri: str = "https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest",
) -> PubChemImportResult:
    if not assays:
        raise ValueError("PubChem snapshot requires at least one selected assay")
    if len({molecule.cid for molecule in molecules}) != len(molecules):
        raise ValueError("PubChem molecule CIDs must be unique")
    if len({target.target_id for target in targets}) != len(targets):
        raise ValueError("PubChem target IDs must be unique")
    if len({assay.aid for assay in assays}) != len(assays):
        raise ValueError("PubChem assay AIDs must be unique")
    expected_aids = {assay.aid for assay in assays}
    if set(raw_files) != expected_aids:
        raise EvidenceStoreError(
            "PubChem raw files must exactly match selected AIDs: "
            f"expected {sorted(expected_aids)}, found {sorted(raw_files)}"
        )

    molecule_by_cid = {molecule.cid: molecule for molecule in molecules}
    target_by_id = {target.target_id: target for target in targets}
    selection_payload = {
        "molecules": [
            {
                "cid": molecule.cid,
                "inchikey": molecule.inchikey,
                "canonical_smiles": molecule.canonical_smiles,
                "preferred_name": molecule.preferred_name,
                "aliases": molecule.aliases,
            }
            for molecule in molecules
        ],
        "targets": [
            {
                "target_id": target.target_id,
                "preferred_name": target.preferred_name,
                "organism": target.organism,
                "accession": target.accession,
                "gene_symbol": target.gene_symbol,
                "aliases": target.aliases,
            }
            for target in targets
        ],
        "assays": [
            {
                "aid": assay.aid,
                "target_id": assay.target_id,
                "selected_cids": assay.selected_cids,
                "conditions": assay.conditions,
            }
            for assay in assays
        ],
    }
    source_hash = _combined_source_hash(raw_files, selection_payload)
    store.register_snapshot(
        SnapshotSpec(
            snapshot_id=snapshot_id,
            source_name="PubChem BioAssay concise",
            source_version=source_version,
            source_sha256=source_hash,
            source_uri=source_uri,
            license="Public domain; verify individual depositor terms",
            scope={
                "aids": sorted(expected_aids),
                "cids": sorted(molecule_by_cid),
                "target_ids": sorted(target_by_id),
            },
            created_at=created_at,
        )
    )

    for molecule in molecules:
        raw_hash = _sha256(
            {
                "cid": molecule.cid,
                "inchikey": molecule.inchikey,
                "canonical_smiles": molecule.canonical_smiles,
                "preferred_name": molecule.preferred_name,
            }
        )
        store.add_molecule(
            snapshot_id=snapshot_id,
            inchikey=molecule.inchikey,
            canonical_smiles=molecule.canonical_smiles,
            preferred_name=molecule.preferred_name,
            pubchem_cid=molecule.cid,
            raw_record_sha256=raw_hash,
        )
        for alias in dict.fromkeys((molecule.preferred_name, *molecule.aliases)):
            store.add_molecule_alias(
                snapshot_id=snapshot_id,
                inchikey=molecule.inchikey,
                alias=alias,
                source="PubChem selection",
            )

    for target in targets:
        raw_hash = _sha256(
            {
                "target_id": target.target_id,
                "preferred_name": target.preferred_name,
                "organism": target.organism,
                "accession": target.accession,
                "gene_symbol": target.gene_symbol,
            }
        )
        store.add_target(
            snapshot_id=snapshot_id,
            target_id=target.target_id,
            preferred_name=target.preferred_name,
            organism=target.organism,
            target_type="PUBCHEM_REVIEWED_MAPPING",
            accession=target.accession,
            gene_symbol=target.gene_symbol,
            raw_record_sha256=raw_hash,
        )
        aliases = dict.fromkeys(
            value
            for value in (target.preferred_name, target.gene_symbol, *target.aliases)
            if value
        )
        for alias in aliases:
            store.add_target_alias(
                snapshot_id=snapshot_id,
                target_id=target.target_id,
                alias=alias,
                source="PubChem selection",
            )

    imported_activities = 0
    imported_papers: set[str] = set()
    for assay_spec in assays:
        if assay_spec.target_id not in target_by_id:
            raise EvidenceStoreError(
                f"PubChem AID {assay_spec.aid} references unknown target {assay_spec.target_id}"
            )
        unknown_cids = sorted(set(assay_spec.selected_cids) - set(molecule_by_cid))
        if unknown_cids:
            raise EvidenceStoreError(
                f"PubChem AID {assay_spec.aid} references unknown CIDs: {unknown_cids}"
            )
        payload = raw_files[assay_spec.aid]
        rows = _parse_concise(payload, assay_spec.aid)
        selected_rows = [
            (row, _optional_int(row["CID"], field_name="CID"))
            for row in rows
            if _optional_int(row["CID"], field_name="CID") in assay_spec.selected_cids
        ]
        if not selected_rows:
            raise EvidenceStoreError(
                f"PubChem AID {assay_spec.aid} contains no rows for selected CIDs"
            )
        pmids = {row["PubMed ID"] for row, _ in selected_rows if row["PubMed ID"]}
        if len(pmids) > 1:
            raise EvidenceStoreError(
                f"PubChem AID {assay_spec.aid} maps to multiple PubMed IDs: {sorted(pmids)}"
            )
        pmid = next(iter(pmids), None)
        paper_id = f"PMID:{pmid}" if pmid else None
        if paper_id and paper_id not in imported_papers:
            store.add_paper(
                snapshot_id=snapshot_id,
                paper_id=paper_id,
                pmid=pmid,
                title=None,
                retraction_status=retraction_index.status_for(pmid=pmid).value,
                raw_record_sha256=_sha256({"pmid": pmid, "aid": assay_spec.aid}),
            )
            imported_papers.add(paper_id)

        assay_names = {row["Assay Name"] for row, _ in selected_rows if row["Assay Name"]}
        assay_types = {row["Assay Type"] for row, _ in selected_rows if row["Assay Type"]}
        if len(assay_names) > 1 or len(assay_types) > 1:
            raise EvidenceStoreError(
                f"PubChem AID {assay_spec.aid} has inconsistent assay metadata"
            )
        assay_name = next(iter(assay_names), None)
        assay_type = next(iter(assay_types), None)
        conditions = dict(assay_spec.conditions)
        conditions.update(
            {
                "pubchem_aid": assay_spec.aid,
                "reviewed_target_mapping": True,
            }
        )
        assay_id = f"PUBCHEM:AID:{assay_spec.aid}"
        store.add_assay(
            snapshot_id=snapshot_id,
            assay_id=assay_id,
            source="PUBCHEM",
            target_id=assay_spec.target_id,
            organism=target_by_id[assay_spec.target_id].organism,
            assay_type=assay_type,
            description=assay_name,
            conditions=conditions,
            paper_id=paper_id,
            raw_record_sha256=_sha256(payload),
        )
        for row, cid in selected_rows:
            if cid is None:
                continue
            molecule = molecule_by_cid[cid]
            sid = _optional_int(row["SID"], field_name="SID")
            if sid is None:
                raise EvidenceStoreError(
                    f"PubChem AID {assay_spec.aid} selected row has no SID"
                )
            activity_value_um = _optional_float(
                row["Activity Value [uM]"],
                field_name="Activity Value [uM]",
            )
            activity_name = row["Activity Name"] or "ACTIVITY_OUTCOME"
            store.add_activity(
                snapshot_id=snapshot_id,
                activity_id=(
                    f"PUBCHEM:AID:{assay_spec.aid}:SID:{sid}:CID:{cid}"
                ),
                assay_id=assay_id,
                molecule_inchikey=molecule.inchikey,
                measurement_type=activity_name,
                original_value=activity_value_um,
                original_unit="uM" if activity_value_um is not None else None,
                original_relation="=" if activity_value_um is not None else None,
                standard_value=(
                    activity_value_um * 1_000 if activity_value_um is not None else None
                ),
                standard_unit="nM" if activity_value_um is not None else None,
                standard_relation="=" if activity_value_um is not None else None,
                activity_outcome=row["Activity Outcome"] or None,
                raw_record_sha256=_sha256(row),
            )
            imported_activities += 1

    content_hash = store.seal_snapshot(snapshot_id)
    return PubChemImportResult(
        snapshot_id=snapshot_id,
        assay_count=len(assays),
        activity_count=imported_activities,
        molecule_count=len(molecules),
        target_count=len(targets),
        content_sha256=content_hash,
    )


def read_pubchem_raw_files(
    directory: str | Path,
    aids: tuple[int, ...],
) -> dict[int, bytes]:
    root = Path(directory).resolve()
    raw_files: dict[int, bytes] = {}
    for aid in aids:
        path = root / f"AID-{aid}.concise.json"
        if not path.is_file():
            raise EvidenceStoreError(f"missing frozen PubChem response: {path}")
        raw_files[aid] = path.read_bytes()
    return raw_files
