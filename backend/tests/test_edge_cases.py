import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "hm01_edge_cases.json"
EDGE_CASES: list[dict[str, Any]] = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _analyze(case: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        "/api/analyze",
        json={"structure": case["smiles"], "label": case["id"]},
    )
    assert response.status_code == 200
    return response.json()


def test_corpus_contains_exactly_31_declared_cases() -> None:
    assert len(EDGE_CASES) == 31
    assert len({case["id"] for case in EDGE_CASES}) == 31


@pytest.mark.parametrize("case", EDGE_CASES, ids=lambda case: case["id"])
def test_edge_case_classification_and_missing_value_contract(case: dict[str, Any]) -> None:
    result = _analyze(case)
    issue_codes = {issue["code"] for issue in result["issues"]}

    assert result["status"] == case["expected_status"]
    if case["expected_issue"] is not None:
        assert case["expected_issue"] in issue_codes

    for issue in result["issues"]:
        assert issue["title"]
        assert issue["explanation"]
        assert issue["why_it_matters"]
        assert issue["next_step"]

    if case["expected_status"] == "invalid":
        assert result["canonical_smiles"] is None
        assert result["standardized_smiles"] is None
        assert all(
            property_result["computed"]["status"] == "INVALID_INPUT"
            for property_result in result["properties"]
        )
        assert all(
            property_result["evidence"]["status"] == "NOT_APPLICABLE"
            for property_result in result["properties"]
        )
    else:
        assert result["canonical_smiles"]
        assert result["standardized_smiles"]
        assert result["depiction_svg"].startswith("<?xml")
        assert all(
            property_result["computed"]["status"] == "AVAILABLE"
            for property_result in result["properties"]
        )
        assert all(
            property_result["evidence"]["reason_code"]
            == "REFERENCE_SNAPSHOT_NOT_CONFIGURED"
            for property_result in result["properties"]
        )

    if case.get("expect_standardization_change"):
        assert any(step["changed"] for step in result["standardization_steps"])


@pytest.mark.parametrize("case", EDGE_CASES, ids=lambda case: case["id"])
def test_edge_case_hashes_are_repeatable(case: dict[str, Any]) -> None:
    first = _analyze(case)
    second = _analyze(case)

    assert first["analysis_id"] == second["analysis_id"]
    assert first["manifest"] == second["manifest"]


@pytest.mark.parametrize(
    ("smiles", "stereo_marker"),
    [
        ("C/C=C/C", "/"),
        ("C[C@H](O)CC", "@"),
        ("N[C@@H](C)C(=O)O", "@"),
    ],
)
def test_standardization_preserves_explicit_stereochemistry(
    smiles: str, stereo_marker: str
) -> None:
    response = client.post("/api/analyze", json={"structure": smiles})
    assert response.status_code == 200
    assert stereo_marker in response.json()["standardized_smiles"]


@pytest.mark.parametrize(
    "payload",
    [
        {"structure": ""},
        {"structure": "   \n\t"},
        {"structure": "C" * 20_001},
        {"structure": "CCO", "input_type": "molfile"},
        {"structure": "CCO", "label": "x" * 201},
        {"structure": "CCO", "source": {"file_sha256": "not-a-sha256"}},
    ],
)
def test_invalid_request_boundaries_return_422(payload: dict[str, Any]) -> None:
    response = client.post("/api/analyze", json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "molecules",
    [
        [],
        [{"structure": "CCO"}] * 101,
    ],
)
def test_invalid_batch_boundaries_return_422(molecules: list[dict[str, str]]) -> None:
    response = client.post("/api/analyze/batch", json={"molecules": molecules})
    assert response.status_code == 422
