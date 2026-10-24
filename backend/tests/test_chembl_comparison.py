import json
from pathlib import Path

from app.models.analysis import ResultStatus
from app.services.chembl_comparison import (
    FrozenChemblComparisonClient,
    resolve_bioactivity_evidence,
)

ASPIRIN_SMILES = "CC(=O)Oc1ccccc1C(=O)O"
ASPIRIN_INCHIKEY = "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"


def _payload(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def test_exact_chembl_match_is_frozen_and_reused(tmp_path: Path) -> None:
    requested: list[str] = []

    def transport(url: str, _timeout: float) -> bytes:
        requested.append(url)
        if url.endswith("/status.json"):
            return _payload({"status": "UP", "chembl_db_version": "ChEMBL_37"})
        if "/molecule.json?" in url:
            return _payload(
                {
                    "molecules": [
                        {
                            "molecule_chembl_id": "CHEMBL25",
                            "pref_name": "ASPIRIN",
                            "molecule_structures": {
                                "standard_inchi_key": ASPIRIN_INCHIKEY
                            },
                        }
                    ]
                }
            )
        if "/activity.json?" in url:
            return _payload({"activities": [], "page_meta": {"total_count": 4087}})
        raise AssertionError(f"Unexpected ChEMBL URL: {url}")

    client = FrozenChemblComparisonClient(tmp_path, transport=transport)
    first = resolve_bioactivity_evidence(ASPIRIN_SMILES, client=client, enabled=True)
    second = resolve_bioactivity_evidence(ASPIRIN_SMILES, client=client, enabled=True)

    assert first == second
    assert first.status == ResultStatus.AVAILABLE
    assert first.molecule_chembl_id == "CHEMBL25"
    assert first.preferred_name == "ASPIRIN"
    assert first.release == "ChEMBL_37"
    assert first.activity_count == 4087
    assert first.snapshot_id.startswith("chembl-37-chembl25@")
    assert first.response_sha256 and len(first.response_sha256) == 64
    assert len(requested) == 3
    snapshot_directories = [path for path in tmp_path.iterdir() if path.is_dir()]
    assert len(snapshot_directories) == 1
    assert {path.name for path in snapshot_directories[0].iterdir()} == {
        "activity.json",
        "manifest.json",
        "molecule.json",
        "status.json",
    }


def test_no_exact_chembl_match_is_an_explicit_frozen_result(tmp_path: Path) -> None:
    requested: list[str] = []

    def transport(url: str, _timeout: float) -> bytes:
        requested.append(url)
        if url.endswith("/status.json"):
            return _payload({"status": "UP", "chembl_db_version": "ChEMBL_37"})
        if "/molecule.json?" in url:
            return _payload({"molecules": []})
        raise AssertionError("An activity request must not be made without a molecule match")

    client = FrozenChemblComparisonClient(tmp_path, transport=transport)
    evidence = resolve_bioactivity_evidence("[He]", client=client, enabled=True)

    assert evidence.status == ResultStatus.NO_REFERENCE_MATCH
    assert evidence.molecule_chembl_id is None
    assert evidence.activity_count is None
    assert evidence.release == "ChEMBL_37"
    assert evidence.reason_code == "CHEMBL_NO_EXACT_INCHIKEY_MATCH"
    assert evidence.snapshot_id.startswith("chembl-37-no-match@")
    assert len(requested) == 2


def test_tampered_chembl_cache_is_not_reported_as_evidence(tmp_path: Path) -> None:
    def transport(url: str, _timeout: float) -> bytes:
        if url.endswith("/status.json"):
            return _payload({"status": "UP", "chembl_db_version": "ChEMBL_37"})
        if "/molecule.json?" in url:
            return _payload(
                {
                    "molecules": [
                        {
                            "molecule_chembl_id": "CHEMBL25",
                            "pref_name": "ASPIRIN",
                            "molecule_structures": {
                                "standard_inchi_key": ASPIRIN_INCHIKEY
                            },
                        }
                    ]
                }
            )
        return _payload({"activities": [], "page_meta": {"total_count": 4087}})

    client = FrozenChemblComparisonClient(tmp_path, transport=transport)
    available = resolve_bioactivity_evidence(ASPIRIN_SMILES, client=client, enabled=True)
    assert available.status == ResultStatus.AVAILABLE

    snapshot_directory = next(path for path in tmp_path.iterdir() if path.is_dir())
    (snapshot_directory / "molecule.json").write_text("{}", encoding="utf-8")
    rejected = resolve_bioactivity_evidence(ASPIRIN_SMILES, client=client, enabled=True)

    assert rejected.status == ResultStatus.NOT_AVAILABLE
    assert rejected.reason_code == "CHEMBL_SNAPSHOT_ACQUISITION_FAILED"


def test_unexpected_chembl_failure_cannot_crash_core_analysis(tmp_path: Path) -> None:
    def fail_transport(_url: str, _timeout: float) -> bytes:
        raise RuntimeError("unexpected external client failure")

    client = FrozenChemblComparisonClient(tmp_path, transport=fail_transport)
    evidence = resolve_bioactivity_evidence(ASPIRIN_SMILES, client=client, enabled=True)

    assert evidence.status == ResultStatus.NOT_AVAILABLE
    assert evidence.reason_code == "CHEMBL_SNAPSHOT_ACQUISITION_FAILED"

