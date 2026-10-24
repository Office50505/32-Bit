from typing import Any

import pytest

from app.models.evidence_assistant import (
    AtomicStatement,
    ClaimCheckRequest,
    ClaimDecomposition,
    ClaimType,
    EvidencePacket,
    ResolutionStatus,
    ResolutionSummary,
    Verdict,
    VerdictProposal,
)
from app.services.ollama import (
    ModelIdentityError,
    OllamaClient,
    OllamaConfig,
    OllamaProtocolError,
)

DIGEST = "a" * 64


class FakeTransport:
    def __init__(self, chat_content: str) -> None:
        self.chat_content = chat_content
        self.calls: list[tuple[str, str, dict[str, Any] | None, float]] = []
        self.digest = DIGEST
        self.parameter_count = 4_022_468_096

    def __call__(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        timeout: float,
    ) -> dict[str, Any]:
        self.calls.append((method, path, payload, timeout))
        if path == "/api/tags":
            return {"models": [{"name": "qwen3:4b-instruct", "digest": self.digest}]}
        if path == "/api/show":
            return {
                "details": {
                    "parameter_size": "4.0B",
                    "quantization_level": "Q4_K_M",
                    "family": "qwen3",
                },
                "model_info": {"general.parameter_count": self.parameter_count},
            }
        if path == "/api/chat":
            return {
                "model": "qwen3:4b-instruct",
                "message": {"role": "assistant", "content": self.chat_content},
                "total_duration": 10,
                "load_duration": 2,
                "prompt_eval_count": 50,
                "eval_count": 20,
            }
        raise AssertionError(f"unexpected fake request: {path}")


def config() -> OllamaConfig:
    return OllamaConfig(model="qwen3:4b-instruct", expected_digest=DIGEST)


def decomposition_json() -> str:
    return (
        '{"statements":[{"text":"Imatinib inhibits ABL1.",'
        '"claim_type":"BIOLOGICAL_ACTIVITY","molecule_mentions":["Imatinib"],'
        '"target_mentions":["ABL1"],"endpoint_mentions":[]}]}'
    )


def test_decomposition_uses_schema_zero_temperature_seed_and_no_thinking() -> None:
    transport = FakeTransport(decomposition_json())
    client = OllamaClient(config(), transport=transport)
    result = client.decompose_claim(ClaimCheckRequest(claim="Imatinib inhibits ABL1."))
    assert isinstance(result.value, ClaimDecomposition)
    assert result.value.statements[0].statement_id == "S1"
    chat_payload = next(call[2] for call in transport.calls if call[1] == "/api/chat")
    assert chat_payload is not None
    assert chat_payload["stream"] is False
    assert chat_payload["think"] is False
    assert chat_payload["options"] == {
        "temperature": 0,
        "seed": 42,
        "num_ctx": 8192,
        "num_predict": 512,
    }
    assert chat_payload["messages"][0]["content"].startswith("/no_think")
    assert chat_payload["messages"][1]["content"].endswith("/no_think")
    assert chat_payload["format"]["type"] == "object"
    assert chat_payload["format"]["additionalProperties"] is False
    assert result.metadata.prompt_tokens == 50


def test_json_compatibility_mode_still_validates_and_assigns_ids() -> None:
    transport = FakeTransport(decomposition_json())
    json_config = OllamaConfig(
        model="qwen3:4b-instruct",
        expected_digest=DIGEST,
        structured_output_mode="json",
    )
    client = OllamaClient(json_config, transport=transport)
    result = client.decompose_claim(ClaimCheckRequest(claim="Imatinib inhibits ABL1."))
    assert result.value.statements[0].statement_id == "S1"
    chat_payload = next(call[2] for call in transport.calls if call[1] == "/api/chat")
    assert chat_payload is not None
    assert chat_payload["format"] == "json"
    assert "Required JSON Schema" in chat_payload["messages"][0]["content"]


def test_model_digest_mismatch_blocks_chat() -> None:
    transport = FakeTransport(decomposition_json())
    transport.digest = "b" * 64
    client = OllamaClient(config(), transport=transport)
    with pytest.raises(ModelIdentityError, match="digest mismatch"):
        client.decompose_claim(ClaimCheckRequest(claim="Imatinib inhibits ABL1."))
    assert not any(call[1] == "/api/chat" for call in transport.calls)


def test_model_over_8b_is_rejected() -> None:
    transport = FakeTransport(decomposition_json())
    transport.parameter_count = 8_000_000_001
    client = OllamaClient(config(), transport=transport)
    with pytest.raises(ModelIdentityError, match="maximum"):
        client.verify_model()


def test_invalid_structured_output_fails_closed() -> None:
    transport = FakeTransport('{"statements": [{"statement_id": "S9"}]}')
    client = OllamaClient(config(), transport=transport)
    with pytest.raises(OllamaProtocolError, match="JSON schema"):
        client.decompose_claim(ClaimCheckRequest(claim="Imatinib inhibits ABL1."))


def test_decomposition_requires_ordered_unique_statement_ids() -> None:
    with pytest.raises(ValueError, match="ordered S1"):
        ClaimDecomposition(
            statements=[
                AtomicStatement(
                    statement_id="S2",
                    text="A statement.",
                    claim_type=ClaimType.OTHER,
                )
            ]
        )


def test_verdict_call_uses_packet_schema() -> None:
    verdict = VerdictProposal(
        statement_id="S1",
        verdict=Verdict.INSUFFICIENT_EVIDENCE,
        reason="No direct evidence was supplied.",
        reason_codes=["NO_DIRECT_EVIDENCE"],
    )
    transport = FakeTransport(verdict.model_dump_json())
    client = OllamaClient(config(), transport=transport)
    packet = EvidencePacket(
        statement=AtomicStatement(
            statement_id="S1",
            text="Imatinib inhibits ABL1.",
            claim_type=ClaimType.BIOLOGICAL_ACTIVITY,
            molecule_mentions=["Imatinib"],
            target_mentions=["ABL1"],
        ),
        resolution=ResolutionSummary(
            status=ResolutionStatus.RESOLVED,
            molecule_inchikey="KTUFNOKKBVMGRW-UHFFFAOYSA-N",
            target_id="CHEMBL1862",
        ),
        evidence_items=[],
    )
    result = client.propose_verdict(packet)
    assert result.value == verdict
    chat_payload = next(call[2] for call in transport.calls if call[1] == "/api/chat")
    assert chat_payload is not None
    assert chat_payload["format"]["title"] == "VerdictProposal"


def test_model_verification_is_cached_between_calls() -> None:
    transport = FakeTransport(decomposition_json())
    client = OllamaClient(config(), transport=transport)
    request = ClaimCheckRequest(claim="Imatinib inhibits ABL1.")
    client.decompose_claim(request)
    client.decompose_claim(request)
    assert sum(call[1] == "/api/tags" for call in transport.calls) == 1
    assert sum(call[1] == "/api/show" for call in transport.calls) == 1
    assert sum(call[1] == "/api/chat" for call in transport.calls) == 2
