import json
import urllib.parse
from pathlib import Path

from app.evidence.store import EvidenceStore
from app.models.evidence_assistant import AtomicStatement, ClaimDecomposition, ClaimType
from app.services.claim_routing import EntityResolver
from app.services.dynamic_chembl import DynamicChemblSnapshots


def _encoded(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _molecule() -> dict[str, object]:
    return {
        "molecule_chembl_id": "CHEMBL941",
        "pref_name": "IMATINIB",
        "molecule_hierarchy": {"parent_chembl_id": "CHEMBL941"},
        "molecule_structures": {
            "canonical_smiles": "Cc1ccc(NC(=O)c2ccccc2)cc1",
            "standard_inchi_key": "KTUFNOKKBVMGRW-UHFFFAOYSA-N",
        },
        "molecule_synonyms": [
            {"synonyms": "Gleevec", "syn_type": "TRADE_NAME"}
        ],
    }


def _target(*, identifier: str, organism: str) -> dict[str, object]:
    return {
        "target_chembl_id": identifier,
        "pref_name": "Tyrosine-protein kinase ABL1",
        "organism": organism,
        "target_type": "SINGLE PROTEIN",
        "target_components": [
            {
                "component_id": 173 if organism == "Homo sapiens" else 174,
                "accession": "P00519" if organism == "Homo sapiens" else "P00520",
                "component_type": "PROTEIN",
                "component_description": "Tyrosine-protein kinase ABL1",
                "target_component_synonyms": [
                    {"component_synonym": "ABL1", "syn_type": "GENE_SYMBOL"}
                ],
            }
        ],
    }


class FakeDynamicChemblApi:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        parsed = urllib.parse.urlsplit(url)
        if parsed.path.endswith("/status.json"):
            return _encoded(
                {
                    "status": "UP",
                    "chembl_db_version": "ChEMBL_37",
                    "chembl_release_date": "2026-05-01",
                }
            )
        if parsed.path.endswith("/molecule/search.json"):
            return _encoded(
                {
                    "molecules": [_molecule()],
                    "page_meta": {"limit": 20, "offset": 0, "next": None},
                }
            )
        if parsed.path.endswith("/target/search.json"):
            return _encoded(
                {
                    "targets": [
                        _target(identifier="CHEMBL3099", organism="Mus musculus"),
                        _target(identifier="CHEMBL1862", organism="Homo sapiens"),
                    ],
                    "page_meta": {"limit": 20, "offset": 0, "next": None},
                }
            )
        if parsed.path.endswith("/molecule/CHEMBL941.json"):
            return _encoded(_molecule())
        if parsed.path.endswith("/target/CHEMBL1862.json"):
            return _encoded(_target(identifier="CHEMBL1862", organism="Homo sapiens"))
        if parsed.path.endswith("/activity.json"):
            return _encoded(
                {
                    "activities": [
                        {
                            "activity_id": 909963,
                            "assay_chembl_id": "CHEMBL846547",
                            "document_chembl_id": "CHEMBL1130562",
                            "molecule_chembl_id": "CHEMBL941",
                            "target_chembl_id": "CHEMBL1862",
                            "type": "IC50",
                            "relation": "=",
                            "value": "0.038",
                            "units": "uM",
                            "standard_type": "IC50",
                            "standard_relation": "=",
                            "standard_value": "38.0",
                            "standard_units": "nM",
                            "pchembl_value": "7.42",
                            "potential_duplicate": 0,
                        }
                    ],
                    "page_meta": {"limit": 1000, "offset": 0, "next": None},
                }
            )
        if parsed.path.endswith("/assay.json"):
            return _encoded(
                {
                    "assays": [
                        {
                            "assay_chembl_id": "CHEMBL846547",
                            "document_chembl_id": "CHEMBL1130562",
                            "target_chembl_id": "CHEMBL1862",
                            "assay_organism": "Homo sapiens",
                            "assay_type": "B",
                            "description": "Inhibition of ABL1.",
                            "confidence_score": 8,
                        }
                    ],
                    "page_meta": {"limit": 1000, "offset": 0, "next": None},
                }
            )
        if parsed.path.endswith("/document.json"):
            return _encoded(
                {
                    "documents": [
                        {
                            "document_chembl_id": "CHEMBL1130562",
                            "doi": "10.1016/S0960-894X(96)00601-4",
                            "pubmed_id": "12345",
                            "title": "Potent and selective inhibitors of Abl kinase",
                        }
                    ],
                    "page_meta": {"limit": 1000, "offset": 0, "next": None},
                }
            )
        raise AssertionError(f"unexpected URL: {url}")


def test_dynamic_pair_is_frozen_imported_and_reused(tmp_path: Path) -> None:
    fixed_database = tmp_path / "fixed.sqlite"
    with EvidenceStore.create(fixed_database):
        pass
    retraction_csv = tmp_path / "retractions.csv"
    retraction_csv.write_text(
        "Record ID,RetractionDate,OriginalPaperDOI,OriginalPaperPubMedID,"
        "RetractionNature,Reason\n"
        "1,01/01/2020,10.1000/retracted,999,Retraction,Unreliable\n",
        encoding="utf-8",
    )
    fake_api = FakeDynamicChemblApi()
    snapshots = DynamicChemblSnapshots(
        fixed_database_path=fixed_database,
        combined_database_path=tmp_path / "combined.sqlite",
        raw_root=tmp_path / "raw",
        retraction_watch_csv=retraction_csv,
        fetch=fake_api,
    )
    decomposition = ClaimDecomposition(
        statements=[
            AtomicStatement(
                statement_id="S1",
                text="Imatinib inhibits ABL1 with an IC50 of 38 nM.",
                claim_type=ClaimType.BIOLOGICAL_ACTIVITY,
                molecule_mentions=["imatinib"],
                target_mentions=["ABL1"],
                endpoint_mentions=["IC50"],
            )
        ]
    )

    first = snapshots.ensure_for_decomposition(decomposition)
    assert len(first) == 1
    assert first[0].startswith("chembl-api-37-chembl941-chembl1862-")
    with EvidenceStore.open_read_only(snapshots.combined_database_path) as store:
        assert store.verify_snapshot(first[0])
        assert store.resolve_molecule_alias(first[0], "imatinib")
        assert store.resolve_target_alias(first[0], "ABL1")[0]["organism"] == "Homo sapiens"
        paper = store._connection.execute(  # noqa: SLF001
            "SELECT retraction_status FROM papers WHERE snapshot_id = ?",
            (first[0],),
        ).fetchone()
        assert paper["retraction_status"] == "CLEAR"
        resolved = EntityResolver(store, first).resolve_and_route(
            decomposition.statements[0]
        )
        assert resolved.resolution.target_id == "CHEMBL1862"
        assert resolved.resolution.organism == "Homo sapiens"

    first_call_count = len(fake_api.urls)
    assert snapshots.ensure_for_decomposition(decomposition) == first
    assert len(fake_api.urls) == first_call_count + 3
    assert len(list((tmp_path / "raw").iterdir())) == 1
