from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def analyze(structure: str, label: str = "Test molecule") -> dict:
    response = client.post("/api/analyze", json={"structure": structure, "label": label})
    assert response.status_code == 200
    return response.json()


def test_aspirin_is_valid_and_computed() -> None:
    result = analyze("CC(=O)Oc1ccccc1C(=O)O", "Aspirin")
    assert result["status"] == "valid"
    weight = next(item for item in result["properties"] if item["key"] == "molecular_weight")
    assert weight["computed"]["status"] == "AVAILABLE"
    assert weight["computed"]["value"] == 180.16
    assert weight["evidence"]["status"] == "NOT_AVAILABLE"
    assert weight["evidence"]["reason_code"] == "REFERENCE_SNAPSHOT_NOT_CONFIGURED"


def test_impossible_valence_is_not_computed() -> None:
    result = analyze("C[O](C)C", "Impossible oxygen")
    assert result["status"] == "invalid"
    assert result["issues"][0]["code"] == "IMPOSSIBLE_VALENCE"
    assert all(item["computed"]["status"] == "INVALID_INPUT" for item in result["properties"])


def test_unassigned_stereochemistry_is_ambiguous() -> None:
    result = analyze("CCC(O)C", "2-butanol")
    assert result["status"] == "ambiguous"
    assert any(issue["code"] == "UNSPECIFIED_STEREOCHEMISTRY" for issue in result["issues"])


def test_same_request_produces_same_hashes() -> None:
    first = analyze("CCO", "Ethanol")
    second = analyze("CCO", "Ethanol")
    assert first["analysis_id"] == second["analysis_id"]
    assert first["manifest"]["output_sha256"] == second["manifest"]["output_sha256"]


def test_photo_source_metadata_is_preserved_and_hashed() -> None:
    source = {
        "source_type": "photo",
        "filename": "paper-figure.png",
        "media_type": "image/png",
        "file_size": 1024,
        "file_sha256": "a" * 64,
        "extraction_method": "manual-smiles-transcription",
    }
    response = client.post(
        "/api/analyze",
        json={"structure": "CCO", "label": "Ethanol", "source": source},
    )
    assert response.status_code == 200
    result = response.json()
    assert all(result["source"][key] == value for key, value in source.items())

    direct = analyze("CCO", "Ethanol")
    assert result["manifest"]["input_sha256"] != direct["manifest"]["input_sha256"]
