from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROVENANCELAB_DB_PATH", str(tmp_path / "runs.sqlite3"))


def test_run_is_persisted_and_retrievable() -> None:
    response = client.post(
        "/api/runs",
        json={"molecules": [{"structure": "CCO", "label": "Ethanol"}]},
    )
    assert response.status_code == 200
    run = response.json()
    assert run["run_id"].startswith("PLR-")
    assert run["results"][0]["status"] == "valid"

    retrieved = client.get(f"/api/runs/{run['run_id']}")
    assert retrieved.status_code == 200
    assert retrieved.json() == run


def test_pdf_report_is_deterministic_and_downloadable() -> None:
    run = client.post(
        "/api/runs",
        json={
            "molecules": [
                {"structure": "CCO", "label": "Ethanol"},
                {"structure": "C[O](C)C", "label": "Invalid oxygen"},
            ]
        },
    ).json()
    first = client.get(f"/api/runs/{run['run_id']}/report.pdf")
    second = client.get(f"/api/runs/{run['run_id']}/report.pdf")

    assert first.status_code == 200
    assert first.headers["content-type"] == "application/pdf"
    assert first.headers["x-provenancelab-run-id"] == run["run_id"]
    assert "attachment" in first.headers["content-disposition"]
    assert first.content.startswith(b"%PDF-")
    assert len(first.content) > 5_000
    assert first.content == second.content


def test_missing_run_has_structured_error() -> None:
    response = client.get("/api/runs/PLR-NOT-FOUND")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RUN_NOT_FOUND"


@pytest.mark.parametrize(
    ("structure", "subcode"),
    [
        ("C1CC", "UNCLOSED_RING"),
        ("C(C", "UNMATCHED_BRANCH"),
        ("C]", "UNMATCHED_BRACKET"),
        ("=CC", "INVALID_BOND_SEQUENCE"),
        ("Q", "INVALID_ATOM_TOKEN"),
        ("C-#C", "INVALID_BOND_SEQUENCE"),
    ],
)
def test_syntax_failures_have_precise_subcodes(structure: str, subcode: str) -> None:
    response = client.post("/api/analyze", json={"structure": structure})
    assert response.status_code == 200
    issue = response.json()["issues"][0]
    assert issue["code"] == "SMILES_SYNTAX_ERROR"
    assert issue["subcode"] == subcode
    assert issue["explanation"]


def test_request_validation_has_stable_error_envelope() -> None:
    response = client.post("/api/analyze", json={"structure": ""})
    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "EMPTY_STRUCTURE",
            "message": "String should have at least 1 character",
            "field": "structure",
            "technical_detail": "string_too_short",
        }
    }
