from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _relationship(left: str, right: str) -> dict[str, object]:
    response = client.post(
        "/api/analyze/batch",
        json={"molecules": [{"structure": left}, {"structure": right}]},
    )
    assert response.status_code == 200
    comparisons = response.json()["identity_comparisons"]
    assert len(comparisons) == 1
    return comparisons[0]


def test_equivalent_smiles_are_explicitly_the_same_molecule() -> None:
    comparison = _relationship("CCO", "OCC")
    assert comparison["relationship"] == "EXACT_SAME_STRUCTURE"
    assert comparison["reason_code"] == "CANONICAL_ISOMERIC_STRUCTURE_MATCH"


def test_enantiomers_are_explicitly_different_stereoisomers() -> None:
    comparison = _relationship("N[C@@H](C)C(=O)O", "N[C@H](C)C(=O)O")
    assert comparison["relationship"] == "STEREOISOMERS"
    assert comparison["reason_code"] == "CONNECTIVITY_MATCH_STEREOCHEMISTRY_DIFFERS"


def test_different_connectivity_is_an_explicit_different_molecule_verdict() -> None:
    comparison = _relationship("CCO", "CC")
    assert comparison["relationship"] == "DIFFERENT_STRUCTURE"


def test_unspecified_stereochemistry_abstains_from_exact_identity() -> None:
    comparison = _relationship("CC(O)F", "C[C@H](O)F")
    assert comparison["relationship"] == "INDETERMINATE"
    assert comparison["reason_code"] == "UNSPECIFIED_STEREOCHEMISTRY_PREVENTS_EXACT_IDENTITY"
