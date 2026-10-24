from fastapi.testclient import TestClient

from app.api import routes
from app.main import app
from app.models.benzo import BenzoChatRequest, BenzoChatResponse

client = TestClient(app)


class FakeBenzo:
    def answer(self, request: BenzoChatRequest) -> BenzoChatResponse:
        return BenzoChatResponse(
            scope="ANSWERED",
            answer=f"Project answer: {request.question}",
            suggestions=[],
            model="test-model",
        )


def test_benzo_chat_endpoint_returns_scoped_answer(monkeypatch) -> None:
    monkeypatch.setattr(routes, "get_benzo_assistant", lambda: FakeBenzo())

    response = client.post(
        "/api/benzo/chat",
        json={"question": "Explain a carbon-carbon double bond.", "current_smiles": "C=C"},
    )

    assert response.status_code == 200
    assert response.json()["scope"] == "ANSWERED"
    assert response.json()["model"] == "test-model"


def test_benzo_chat_endpoint_rejects_blank_question() -> None:
    response = client.post("/api/benzo/chat", json={"question": "   "})

    assert response.status_code == 422
