import math

from fastapi.testclient import TestClient

from app.main import app
from app.services.conformers import generate_conformer

client = TestClient(app)


def test_conformer_is_deterministic_and_contains_finite_coordinates() -> None:
    generate_conformer.cache_clear()
    first = generate_conformer("CC(=O)Oc1ccccc1C(=O)O")
    generate_conformer.cache_clear()
    second = generate_conformer("CC(=O)Oc1ccccc1C(=O)O")

    assert first.coordinate_sha256 == second.coordinate_sha256
    assert first.method.startswith("ETKDGv3")
    assert first.structure_role == "standardized-parent"
    assert len(first.atoms) == 21
    assert all(
        math.isfinite(coordinate)
        for atom in first.atoms
        for coordinate in (atom.x, atom.y, atom.z)
    )


def test_conformer_endpoint_returns_computed_model() -> None:
    response = client.post("/api/conformer", json={"structure": "c1ccccc1"})

    assert response.status_code == 200
    assert response.json()["method"].startswith("ETKDGv3")
    assert len(response.json()["atoms"]) == 12


def test_conformer_keeps_hydrogens_for_water() -> None:
    response = client.post("/api/conformer", json={"structure": "O"})

    assert response.status_code == 200
    assert [atom["element"] for atom in response.json()["atoms"]].count("H") == 2
    assert len(response.json()["bonds"]) == 2


def test_conformer_blocks_invalid_and_ambiguous_structures() -> None:
    invalid = client.post("/api/conformer", json={"structure": "c(c)(c)(c)(c)"})
    ambiguous = client.post("/api/conformer", json={"structure": "CCC(O)C"})

    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_STRUCTURE"
    assert ambiguous.status_code == 409
    assert ambiguous.json()["error"]["code"] == "AMBIGUOUS_STEREOCHEMISTRY"
