import json
from pathlib import Path

from app.models.analysis import AnalyzeRequest, ResultStatus
from app.services import chemistry
from app.services.evidence import evidence_for, resolve_property_evidence
from app.services.pubchem_questions import FrozenPubChemClient


def _aspirin_payload() -> bytes:
    return json.dumps(
        {
            "PropertyTable": {
                "Properties": [
                    {
                        "CID": 2244,
                        "Title": "Aspirin",
                        "IUPACName": "2-acetyloxybenzoic acid",
                        "ConnectivitySMILES": "CC(=O)OC1=CC=CC=C1C(=O)O",
                        "SMILES": "CC(=O)OC1=CC=CC=C1C(=O)O",
                        "InChIKey": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
                        "MolecularFormula": "C9H8O4",
                        "MolecularWeight": "180.16",
                        "ExactMass": "180.04225873",
                        "XLogP": 1.2,
                        "TPSA": 63.6,
                        "HBondDonorCount": 1,
                        "HBondAcceptorCount": 4,
                        "RotatableBondCount": 3,
                    }
                ]
            }
        },
        separators=(",", ":"),
    ).encode()


def test_frozen_pubchem_properties_are_compared_and_reused(tmp_path: Path) -> None:
    calls: list[str] = []

    def transport(url: str, _timeout: float) -> bytes:
        calls.append(url)
        return _aspirin_payload()

    client = FrozenPubChemClient(tmp_path, transport=transport)
    first = resolve_property_evidence(
        "CC(=O)Oc1ccccc1C(=O)O",
        client=client,
        enabled=True,
    )
    second = resolve_property_evidence(
        "CC(=O)Oc1ccccc1C(=O)O",
        client=client,
        enabled=True,
    )

    assert first == second
    assert len(calls) == 1
    assert "/compound/inchikey/BSYNRYMUTXBXSQ-UHFFFAOYSA-N/" in calls[0]
    assert first.record is not None
    assert first.snapshot_id.startswith("pubchem-pug-cid-2244@")
    assert evidence_for(first, "molecular_weight", "g/mol").value == 180.16
    assert evidence_for(first, "exact_mass", "Da").value == 180.04225873
    assert evidence_for(first, "ring_count", "count").status == (
        ResultStatus.OUTSIDE_SNAPSHOT_COVERAGE
    )


def test_analysis_manifest_identifies_the_frozen_pubchem_record(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client = FrozenPubChemClient(tmp_path, transport=lambda _url, _timeout: _aspirin_payload())
    resolution = resolve_property_evidence(
        "CC(=O)Oc1ccccc1C(=O)O",
        client=client,
        enabled=True,
    )
    monkeypatch.setattr(chemistry, "resolve_property_evidence", lambda _smiles: resolution)

    result = chemistry.analyze_structure(
        AnalyzeRequest(structure="CC(=O)Oc1ccccc1C(=O)O", label="Aspirin")
    )
    weight = next(item for item in result.properties if item.key == "molecular_weight")

    assert result.manifest.snapshot_id == resolution.snapshot_id
    assert "CID 2244" in result.manifest.snapshot_scope
    assert weight.evidence.value == 180.16
    assert weight.comparison_status == ResultStatus.AVAILABLE
