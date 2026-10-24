import json
import urllib.parse
from pathlib import Path

import pytest

from app.evidence import EvidenceStore, EvidenceStoreError
from app.evidence.build_chembl_api_snapshot import load_api_selection, main
from app.evidence.chembl_api import (
    MANIFEST_FILENAME,
    ChemblApiError,
    ChemblApiSelection,
    acquire_chembl_api_snapshot,
    import_chembl_api_snapshot,
    inspect_frozen_chembl_api_snapshot,
)
from app.evidence.retractions import FrozenRetractionIndex

INCHIKEY = "KTUFNOKKBVMGRW-UHFFFAOYSA-N"
SNAPSHOT_ID = "chembl-api-37-pilot-v1"


def _encoded(payload: object) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def _molecule() -> dict[str, object]:
    return {
        "molecule_chembl_id": "CHEMBL941",
        "pref_name": "IMATINIB",
        "molecule_hierarchy": {
            "molecule_chembl_id": "CHEMBL941",
            "parent_chembl_id": "CHEMBL941",
        },
        "molecule_structures": {
            "canonical_smiles": "Cc1ccc(NC(=O)c2ccccc2)cc1",
            "standard_inchi_key": INCHIKEY,
        },
        "molecule_synonyms": [
            {"synonyms": "Gleevec", "syn_type": "TRADE_NAME"},
            {"synonyms": "STI-571", "syn_type": "RESEARCH_CODE"},
        ],
    }


def _target() -> dict[str, object]:
    return {
        "target_chembl_id": "CHEMBL1862",
        "pref_name": "Tyrosine-protein kinase ABL1",
        "organism": "Homo sapiens",
        "target_type": "SINGLE PROTEIN",
        "target_components": [
            {
                "component_id": 173,
                "accession": "P00519",
                "component_type": "PROTEIN",
                "component_description": "Tyrosine-protein kinase ABL1",
                "target_component_synonyms": [
                    {"component_synonym": "ABL1", "syn_type": "GENE_SYMBOL"},
                    {"component_synonym": "c-Abl", "syn_type": "UNIPROT"},
                ],
            }
        ],
    }


def _activity() -> dict[str, object]:
    return {
        "activity_id": 909963,
        "assay_chembl_id": "CHEMBL846547",
        "document_chembl_id": "CHEMBL1130562",
        "molecule_chembl_id": "CHEMBL941",
        "target_chembl_id": "CHEMBL1862",
        "type": "IC50",
        "relation": "=",
        "value": "0.038",
        "units": "uM",
        "text_value": None,
        "standard_type": "IC50",
        "standard_relation": "=",
        "standard_value": "38.0",
        "standard_units": "nM",
        "standard_text_value": None,
        "pchembl_value": "7.42",
        "activity_comment": None,
        "data_validity_comment": None,
        "potential_duplicate": 0,
    }


def _assay() -> dict[str, object]:
    return {
        "assay_chembl_id": "CHEMBL846547",
        "document_chembl_id": "CHEMBL1130562",
        "target_chembl_id": "CHEMBL1862",
        "assay_organism": "Homo sapiens",
        "assay_type": "B",
        "description": "Inhibition of v-Abl tyrosine kinase.",
        "confidence_score": 8,
        "assay_test_type": "in vitro",
        "assay_category": "confirmatory",
        "assay_strain": None,
        "assay_tissue": None,
        "assay_cell_type": None,
        "assay_subcellular_fraction": None,
        "relationship_type": "H",
        "bao_format": "BAO_0000357",
        "assay_group": None,
        "variant_sequence": None,
    }


def _document() -> dict[str, object]:
    return {
        "document_chembl_id": "CHEMBL1130562",
        "doi": "10.1016/S0960-894X(96)00601-4",
        "pubmed_id": "12345",
        "title": "Potent and selective inhibitors of the Abl-kinase",
        "doc_type": "PUBLICATION",
    }


class FakeChemblApi:
    def __init__(self, *, release: str = "ChEMBL_37") -> None:
        self.release = release
        self.urls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        parsed = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path.endswith("/status.json"):
            return _encoded(
                {
                    "status": "UP",
                    "chembl_db_version": self.release,
                    "chembl_release_date": "2026-05-01",
                }
            )
        if parsed.path.endswith("/molecule/CHEMBL941.json"):
            return _encoded(_molecule())
        if parsed.path.endswith("/target/CHEMBL1862.json"):
            return _encoded(_target())
        if parsed.path.endswith("/activity.json"):
            if query.get("offset") == ["1"]:
                return _encoded(
                    {
                        "activities": [],
                        "page_meta": {
                            "limit": 1000,
                            "offset": 1,
                            "total_count": 1,
                            "next": None,
                        },
                    }
                )
            return _encoded(
                {
                    "activities": [_activity()],
                    "page_meta": {
                        "limit": 1000,
                        "offset": 0,
                        "total_count": 1,
                        "next": "/chembl/api/data/activity.json?offset=1",
                    },
                }
            )
        if parsed.path.endswith("/assay.json"):
            return _encoded(
                {
                    "assays": [_assay()],
                    "page_meta": {"limit": 1000, "offset": 0, "next": None},
                }
            )
        if parsed.path.endswith("/document.json"):
            return _encoded(
                {
                    "documents": [_document()],
                    "page_meta": {"limit": 1000, "offset": 0, "next": None},
                }
            )
        raise AssertionError(f"unexpected ChEMBL API URL: {url}")


def selection() -> ChemblApiSelection:
    return ChemblApiSelection(
        expected_release="ChEMBL_37",
        molecule_chembl_ids=("CHEMBL941",),
        target_chembl_ids=("CHEMBL1862",),
        endpoints=("IC50",),
    )


def retraction_index(tmp_path: Path) -> FrozenRetractionIndex:
    path = tmp_path / "retractions.csv"
    path.write_text(
        "Record ID,RetractionDate,OriginalPaperDOI,OriginalPaperPubMedID,"
        "RetractionNature,Reason\n"
        "1,01/01/2020,10.1000/retracted,999,Retraction,Unreliable\n",
        encoding="utf-8",
    )
    return FrozenRetractionIndex.from_csv(path)


def test_acquires_hashed_release_pinned_raw_responses(tmp_path: Path) -> None:
    raw_path = tmp_path / "chembl-api"
    fake_api = FakeChemblApi()
    result = acquire_chembl_api_snapshot(
        raw_path,
        selection=selection(),
        retrieved_at="2026-10-24T00:00:00Z",
        fetch=fake_api,
    )

    assert result.release == "ChEMBL_37"
    assert result.release_date == "2026-05-01"
    assert result.response_count == 7
    assert len(result.source_sha256) == 64
    manifest = json.loads((raw_path / MANIFEST_FILENAME).read_text())
    assert manifest["selection"]["expected_release"] == "ChEMBL_37"
    assert manifest["source_sha256"] == result.source_sha256
    assert inspect_frozen_chembl_api_snapshot(raw_path).selection == selection()
    assert [entry["resource"] for entry in manifest["responses"]] == [
        "status",
        "molecule",
        "target",
        "activity",
        "activity",
        "assay",
        "document",
    ]


def test_imports_frozen_api_data_and_seals_snapshot(tmp_path: Path) -> None:
    raw_path = tmp_path / "chembl-api"
    acquire_chembl_api_snapshot(
        raw_path,
        selection=selection(),
        retrieved_at="2026-10-24T00:00:00Z",
        fetch=FakeChemblApi(),
    )
    with EvidenceStore.create(tmp_path / "evidence.sqlite") as store:
        stats = import_chembl_api_snapshot(
            store,
            raw_directory=raw_path,
            snapshot_id=SNAPSHOT_ID,
            created_at="2026-10-24T00:00:00Z",
            retraction_index=retraction_index(tmp_path),
        )
        assert stats.activities == 1
        assert stats.assays == 1
        assert stats.papers == 1
        assert store.verify_snapshot(SNAPSHOT_ID)

        snapshot = store._connection.execute(  # noqa: SLF001
            "SELECT * FROM snapshots WHERE snapshot_id = ?", (SNAPSHOT_ID,)
        ).fetchone()
        assert snapshot["source_version"] == "ChEMBL_37"
        assert len(snapshot["source_sha256"]) == 64
        assert store.resolve_molecule_alias(SNAPSHOT_ID, "gleevec")[0]["inchikey"] == INCHIKEY
        assert store.resolve_target_alias(SNAPSHOT_ID, "abl1")[0]["target_id"] == "CHEMBL1862"

        activity = store._connection.execute(  # noqa: SLF001
            "SELECT * FROM activities WHERE activity_id = '909963'"
        ).fetchone()
        assert activity["original_value"] == 0.038
        assert activity["standard_value"] == 38
        assert activity["standard_unit"] == "nM"
        paper = store._connection.execute("SELECT * FROM papers").fetchone()  # noqa: SLF001
        assert paper["retraction_status"] == "CLEAR"


def test_rejects_tampered_response_before_database_import(tmp_path: Path) -> None:
    raw_path = tmp_path / "chembl-api"
    acquire_chembl_api_snapshot(
        raw_path,
        selection=selection(),
        retrieved_at="2026-10-24T00:00:00Z",
        fetch=FakeChemblApi(),
    )
    manifest = json.loads((raw_path / MANIFEST_FILENAME).read_text())
    response_path = raw_path / manifest["responses"][1]["filename"]
    response_path.write_bytes(b"{}")

    with EvidenceStore.create(tmp_path / "evidence.sqlite") as store:
        with pytest.raises(ChemblApiError, match="hash mismatch"):
            import_chembl_api_snapshot(
                store,
                raw_directory=raw_path,
                snapshot_id=SNAPSHOT_ID,
                created_at="2026-10-24T00:00:00Z",
                retraction_index=retraction_index(tmp_path),
            )


def test_refuses_api_release_drift_without_leaving_partial_files(tmp_path: Path) -> None:
    raw_path = tmp_path / "chembl-api"
    with pytest.raises(ChemblApiError, match="expected ChEMBL_37"):
        acquire_chembl_api_snapshot(
            raw_path,
            selection=selection(),
            retrieved_at="2026-10-24T00:00:00Z",
            fetch=FakeChemblApi(release="ChEMBL_38"),
        )
    assert not raw_path.exists()


def test_api_selection_loader_requires_explicit_release_pin(tmp_path: Path) -> None:
    path = tmp_path / "selection.json"
    path.write_text(
        json.dumps(
            {
                "expected_release": "ChEMBL_37",
                "molecule_chembl_ids": ["CHEMBL941"],
                "target_chembl_ids": ["CHEMBL1862"],
            }
        ),
        encoding="utf-8",
    )
    assert load_api_selection(path).expected_release == "ChEMBL_37"
    path.write_text(
        json.dumps(
            {
                "molecule_chembl_ids": ["CHEMBL941"],
                "target_chembl_ids": ["CHEMBL1862"],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(EvidenceStoreError, match="requires expected_release"):
        load_api_selection(path)


def test_offline_cli_refuses_selection_that_differs_from_frozen_raw_data(
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "chembl-api"
    acquire_chembl_api_snapshot(
        raw_path,
        selection=selection(),
        retrieved_at="2026-10-24T00:00:00Z",
        fetch=FakeChemblApi(),
    )
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(
        json.dumps(
            {
                "expected_release": "ChEMBL_37",
                "molecule_chembl_ids": ["CHEMBL941"],
                "target_chembl_ids": ["CHEMBL1862"],
                "endpoints": ["Ki"],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(EvidenceStoreError, match="does not match"):
        main(
            [
                "--selection",
                str(selection_path),
                "--raw-dir",
                str(raw_path),
                "--output",
                str(tmp_path / "out.sqlite"),
                "--snapshot-id",
                SNAPSHOT_ID,
                "--created-at",
                "2026-10-24T00:00:00Z",
                "--retraction-watch-csv",
                str(tmp_path / "not-read.csv"),
                "--offline",
            ]
        )


def test_selection_rejects_duplicate_identifiers() -> None:
    with pytest.raises(ValueError, match="duplicate molecule IDs"):
        ChemblApiSelection(
            expected_release="ChEMBL_37",
            molecule_chembl_ids=("CHEMBL941", "CHEMBL941"),
            target_chembl_ids=("CHEMBL1862",),
        )
