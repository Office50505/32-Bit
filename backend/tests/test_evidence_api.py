from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.main import app
from app.models.evidence_assistant import (
    AtomicStatement,
    ClaimCheckRequest,
    ClaimCheckResponse,
    ClaimType,
    ConfidenceAssessment,
    ConfidenceLevel,
    DecisionReasonCode,
    EvidenceAssistantManifest,
    ResolutionStatus,
    ResolutionSummary,
    StatementVerdict,
    Verdict,
)
from app.services.evidence_runtime import EvidenceRuntimeError

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_claim_run_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROVENANCELAB_CLAIM_RUN_DB", str(tmp_path / "claim-runs.sqlite3"))


def _response(claim: str) -> ClaimCheckResponse:
    return ClaimCheckResponse(
        assistant_run_id="EA-test",
        verdicts=[
            StatementVerdict(
                statement=AtomicStatement(
                    statement_id="S1",
                    text=claim,
                    claim_type=ClaimType.BIOLOGICAL_ACTIVITY,
                    molecule_mentions=["Imatinib"],
                    target_mentions=["ABL1"],
                ),
                resolution=ResolutionSummary(
                    status=ResolutionStatus.UNRESOLVED,
                    reason_codes=["TEST_FIXTURE"],
                ),
                verdict=Verdict.INSUFFICIENT_EVIDENCE,
                citations=[],
                reason="No direct evidence was available in this test fixture.",
                reason_codes=[DecisionReasonCode.NO_DIRECT_EVIDENCE],
                confidence=ConfidenceAssessment(
                    level=ConfidenceLevel.LOW,
                    factor_scores={"overall": 0.0},
                ),
            )
        ],
        manifest=EvidenceAssistantManifest(
            model_name="qwen3:4b-instruct",
            model_digest="a" * 64,
            evidence_snapshot_id="test-snapshot@123456789abc",
            input_sha256="b" * 64,
            configuration_sha256="c" * 64,
            output_sha256="d" * 64,
        ),
    )


class _FakeRuntime:
    def check_claim(self, request: ClaimCheckRequest) -> ClaimCheckResponse:
        return _response(request.claim)


class _UnavailableRuntime:
    def check_claim(self, _request: ClaimCheckRequest) -> Any:
        raise EvidenceRuntimeError("The frozen evidence snapshot is unavailable.")


def test_evidence_endpoint_returns_typed_research_aid_response(monkeypatch) -> None:
    monkeypatch.setattr(routes, "get_evidence_runtime", lambda: _FakeRuntime())
    response = client.post(
        "/api/evidence/check",
        json={"claim": "Imatinib inhibits ABL1."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verdicts"][0]["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert body["research_aid_notice"].startswith("Research aid only")
    assert body["manifest"]["model_name"] == "qwen3:4b-instruct"

    stored = client.get(f"/api/evidence/runs/{body['assistant_run_id']}")
    assert stored.status_code == 200
    assert stored.json() == body


def test_abstention_is_persisted_with_an_auditable_run_citation(monkeypatch) -> None:
    monkeypatch.setattr(routes, "get_evidence_runtime", lambda: _FakeRuntime())
    response = client.post(
        "/api/evidence/check",
        json={"claim": "Imatinib inhibits ABL1."},
    )
    body = response.json()

    assert body["verdicts"][0]["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert body["verdicts"][0]["citations"] == []
    assert body["assistant_run_id"] == "EA-test"
    assert client.get("/api/evidence/runs/EA-test").status_code == 200


def test_evidence_endpoint_rejects_blank_claim() -> None:
    response = client.post("/api/evidence/check", json={"claim": "   "})
    assert response.status_code == 422


def test_evidence_endpoint_reports_local_runtime_failure(monkeypatch) -> None:
    monkeypatch.setattr(routes, "get_evidence_runtime", lambda: _UnavailableRuntime())
    response = client.post(
        "/api/evidence/check",
        json={"claim": "Imatinib inhibits ABL1."},
    )
    assert response.status_code == 503
    assert "snapshot is unavailable" in response.json()["error"]["message"]
