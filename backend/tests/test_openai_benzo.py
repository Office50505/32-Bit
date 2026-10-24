from types import SimpleNamespace

from app.models.benzo import (
    BenzoChatRequest,
    BenzoModelAnswer,
    BenzoStructureSuggestion,
)
from app.services.openai_benzo import OUT_OF_SCOPE_ANSWER, FalBenzoAssistant


class FakeCompletions:
    def __init__(self, answer: BenzoModelAnswer) -> None:
        self.answer = answer
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(content=self.answer.model_dump_json())
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeClient:
    def __init__(self, answer: BenzoModelAnswer) -> None:
        self.completions = FakeCompletions(answer)
        self.chat = SimpleNamespace(completions=self.completions)


def test_unrelated_question_is_rejected_before_openai() -> None:
    model_answer = BenzoModelAnswer(scope="ANSWERED", answer="Should not run", suggestions=[])
    client = FakeClient(model_answer)
    assistant = FalBenzoAssistant(client=client, model="test-model")

    result = assistant.answer(BenzoChatRequest(question="Who won the football match?"))

    assert result.scope == "OUT_OF_SCOPE"
    assert result.answer == OUT_OF_SCOPE_ANSWER
    assert result.suggestions == []
    assert client.completions.calls == []


def test_structure_question_uses_structured_openai_response() -> None:
    model_answer = BenzoModelAnswer(
        scope="ANSWERED",
        answer="A double bond has bond order two.",
        suggestions=[
            BenzoStructureSuggestion(
                title="Try ethene",
                detail="Use a carbon-carbon double bond and validate it in ProvenanceLab.",
                smiles="C=C",
            )
        ],
    )
    client = FakeClient(model_answer)
    assistant = FalBenzoAssistant(client=client, model="test-model")

    result = assistant.answer(BenzoChatRequest(question="Suggest a molecule with a double bond."))

    assert result.scope == "ANSWERED"
    assert result.suggestions[0].smiles == "C=C"
    call = client.completions.calls[0]
    assert call["model"] == "test-model"
    assert call["response_format"]["type"] == "json_schema"
    assert call["temperature"] == 0.2


def test_invalid_suggested_smiles_is_not_exposed() -> None:
    client = FakeClient(
        BenzoModelAnswer(
            scope="ANSWERED",
            answer="Check the ring closure.",
            suggestions=[
                BenzoStructureSuggestion(
                    title="Incomplete ring",
                    detail="This proposed structure is intentionally invalid in the fixture.",
                    smiles="C1CC",
                )
            ],
        )
    )
    assistant = FalBenzoAssistant(client=client, model="test-model")

    result = assistant.answer(BenzoChatRequest(question="Help fix this molecular ring."))

    assert result.suggestions[0].smiles is None
