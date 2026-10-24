import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.models.evidence_assistant import (
    ClaimCheckRequest,
    ClaimDecomposition,
    EvidencePacket,
    VerdictProposal,
)

JsonObject = dict[str, Any]
Transport = Callable[[str, str, JsonObject | None, float], JsonObject]
StructuredValue = TypeVar("StructuredValue", bound=BaseModel)

CLAIM_DECOMPOSITION_SYSTEM_PROMPT = """/no_think
You decompose scientific claims for ProvenanceLab.
Return JSON matching the supplied schema. Split the input into independently checkable atomic
statements. Preserve the claim's meaning; do not add facts. Label biological assay/activity claims
BIOLOGICAL_ACTIVITY, mechanistic claims MECHANISM, calculated molecular descriptors
COMPUTED_PROPERTY, claims explicitly stated in literature LITERATURE_FACT, clinical efficacy,
safety, or patient-level claims CLINICAL_OR_SAFETY, and anything else OTHER. Copy molecule,
target, and endpoint mentions exactly as written when present. Use IDs S1, S2, ... in order.
Do not provide analysis, hidden reasoning, citations, or text outside the JSON object."""

VERDICT_SYSTEM_PROMPT = """/no_think
You synthesize only the supplied evidence packet for ProvenanceLab.
Return JSON matching the supplied schema. SUPPORTED requires direct evidence that supports the
atomic statement. CONTRADICTED requires direct comparable evidence that conflicts with it; absence
of evidence is not contradiction. Use INSUFFICIENT_EVIDENCE for ambiguity, indirect evidence,
computed-only evidence for biological activity, unresolved disagreement, or missing direct
evidence. Use OUT_OF_SCOPE for clinical efficacy, safety prediction, personalized treatment, or
unsupported future efficacy. Cite only evidence_id values present in the packet. Never use a
retracted item to support or contradict. Do not provide hidden reasoning or text outside JSON.
Deterministic code will reject any verdict that violates these rules."""


class OllamaError(RuntimeError):
    """Base error for local model failures."""


class OllamaUnavailableError(OllamaError):
    """Raised when the local Ollama service cannot be reached."""


class OllamaProtocolError(OllamaError):
    """Raised when Ollama returns a malformed or schema-invalid response."""


class ModelIdentityError(OllamaError):
    """Raised when the installed model does not match the pinned model contract."""


@dataclass(frozen=True, slots=True)
class OllamaConfig:
    model: str
    expected_digest: str
    base_url: str = "http://127.0.0.1:11434"
    timeout_seconds: float = 120.0
    keep_alive: str = "15m"
    seed: int = 42
    context_length: int = 8192
    maximum_output_tokens: int = 512
    maximum_parameters: int = 8_000_000_000
    structured_output_mode: Literal["json_schema", "json"] = "json_schema"

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("Ollama model name cannot be blank")
        digest = self.expected_digest.removeprefix("sha256:")
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("expected_digest must be a lowercase SHA-256 digest")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.context_length < 2_048:
            raise ValueError("context_length must be at least 2048")
        if not 32 <= self.maximum_output_tokens <= 2_048:
            raise ValueError("maximum_output_tokens must be between 32 and 2048")


@dataclass(frozen=True, slots=True)
class OllamaModelIdentity:
    name: str
    digest: str
    parameter_count: int
    parameter_size: str
    quantization_level: str
    family: str


@dataclass(frozen=True, slots=True)
class OllamaCallMetadata:
    model: str
    total_duration_ns: int | None
    load_duration_ns: int | None
    prompt_tokens: int | None
    completion_tokens: int | None


@dataclass(frozen=True, slots=True)
class StructuredModelResult(Generic[StructuredValue]):
    value: StructuredValue
    metadata: OllamaCallMetadata


class _ModelStatement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=5_000)
    claim_type: str
    molecule_mentions: list[str] = Field(default_factory=list)
    target_mentions: list[str] = Field(default_factory=list)
    endpoint_mentions: list[str] = Field(default_factory=list)


class _ModelDecomposition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statements: list[_ModelStatement] = Field(min_length=1, max_length=10)


class OllamaClient:
    def __init__(self, config: OllamaConfig, *, transport: Transport | None = None) -> None:
        self.config = config
        self._transport = transport or self._http_transport
        self._verified_identity: OllamaModelIdentity | None = None

    def _http_transport(
        self,
        method: str,
        path: str,
        payload: JsonObject | None,
        timeout: float,
    ) -> JsonObject:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.config.base_url.rstrip('/')}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                response_body = response.read()
        except (urllib.error.URLError, TimeoutError) as error:
            raise OllamaUnavailableError(f"local Ollama request failed: {path}") from error
        try:
            parsed = json.loads(response_body)
        except json.JSONDecodeError as error:
            raise OllamaProtocolError(f"Ollama returned invalid JSON for {path}") from error
        if not isinstance(parsed, dict):
            raise OllamaProtocolError(f"Ollama returned a non-object response for {path}")
        return parsed

    def verify_model(self, *, force: bool = False) -> OllamaModelIdentity:
        if self._verified_identity is not None and not force:
            return self._verified_identity
        tags = self._transport("GET", "/api/tags", None, self.config.timeout_seconds)
        models = tags.get("models")
        if not isinstance(models, list):
            raise OllamaProtocolError("Ollama tags response does not contain a models array")
        selected = next(
            (
                item
                for item in models
                if isinstance(item, dict)
                and (
                    item.get("name") == self.config.model
                    or item.get("model") == self.config.model
                )
            ),
            None,
        )
        if selected is None:
            raise ModelIdentityError(f"required Ollama model is not installed: {self.config.model}")
        digest = str(selected.get("digest", "")).removeprefix("sha256:")
        expected = self.config.expected_digest.removeprefix("sha256:")
        if digest != expected:
            raise ModelIdentityError(
                f"model digest mismatch for {self.config.model}: "
                f"expected {expected}, found {digest}"
            )
        show = self._transport(
            "POST",
            "/api/show",
            {"model": self.config.model, "verbose": False},
            self.config.timeout_seconds,
        )
        model_info = show.get("model_info")
        details = show.get("details")
        if not isinstance(model_info, dict) or not isinstance(details, dict):
            raise OllamaProtocolError("Ollama show response is missing model metadata")
        parameter_count = model_info.get("general.parameter_count")
        if not isinstance(parameter_count, int):
            raise OllamaProtocolError("Ollama show response is missing parameter count")
        if parameter_count > self.config.maximum_parameters:
            raise ModelIdentityError(
                f"model has {parameter_count} parameters; "
                f"maximum is {self.config.maximum_parameters}"
            )
        identity = OllamaModelIdentity(
            name=self.config.model,
            digest=digest,
            parameter_count=parameter_count,
            parameter_size=str(details.get("parameter_size", "unknown")),
            quantization_level=str(details.get("quantization_level", "unknown")),
            family=str(details.get("family", "unknown")),
        )
        self._verified_identity = identity
        return identity

    def prewarm(self) -> OllamaCallMetadata:
        self.verify_model()
        response = self._transport(
            "POST",
            "/api/chat",
            {
                "model": self.config.model,
                "messages": [],
                "stream": False,
                "think": False,
                "keep_alive": self.config.keep_alive,
            },
            self.config.timeout_seconds,
        )
        return self._metadata(response)

    def decompose_claim(
        self,
        request: ClaimCheckRequest,
    ) -> StructuredModelResult[ClaimDecomposition]:
        prompt = json.dumps(
            {"claim": request.claim},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        model_result = self._structured_chat(
            system_prompt=CLAIM_DECOMPOSITION_SYSTEM_PROMPT,
            user_prompt=prompt,
            output_type=_ModelDecomposition,
        )
        statements = [
            {
                "statement_id": f"S{index}",
                **statement.model_dump(mode="json"),
            }
            for index, statement in enumerate(model_result.value.statements, start=1)
        ]
        try:
            decomposition = ClaimDecomposition.model_validate({"statements": statements})
        except ValidationError as error:
            raise OllamaProtocolError("Ollama decomposition used an unknown claim type") from error
        return StructuredModelResult(value=decomposition, metadata=model_result.metadata)

    def propose_verdict(self, packet: EvidencePacket) -> StructuredModelResult[VerdictProposal]:
        prompt = packet.model_dump_json(exclude_none=False)
        if len(prompt) > 60_000:
            raise OllamaProtocolError("evidence packet exceeds the configured compact-prompt limit")
        return self._structured_chat(
            system_prompt=VERDICT_SYSTEM_PROMPT,
            user_prompt=prompt,
            output_type=VerdictProposal,
        )

    def _structured_chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_type: type[StructuredValue],
    ) -> StructuredModelResult[StructuredValue]:
        self.verify_model()
        schema = output_type.model_json_schema()
        if self.config.structured_output_mode == "json":
            system_prompt = (
                f"{system_prompt}\nRequired JSON Schema:\n"
                f"{json.dumps(schema, separators=(',', ':'))}"
            )
        request_payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{user_prompt}\n\n/no_think"},
            ],
            "format": schema if self.config.structured_output_mode == "json_schema" else "json",
            "stream": False,
            "think": False,
            "keep_alive": self.config.keep_alive,
            "options": {
                "temperature": 0,
                "seed": self.config.seed,
                "num_ctx": self.config.context_length,
                "num_predict": self.config.maximum_output_tokens,
            },
        }
        response = self._transport(
            "POST",
            "/api/chat",
            request_payload,
            self.config.timeout_seconds,
        )
        message = response.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise OllamaProtocolError("Ollama chat response is missing message.content")
        try:
            parsed = output_type.model_validate_json(message["content"])
        except ValidationError as error:
            raise OllamaProtocolError("Ollama output failed the required JSON schema") from error
        return StructuredModelResult(value=parsed, metadata=self._metadata(response))

    def _metadata(self, response: JsonObject) -> OllamaCallMetadata:
        def optional_int(key: str) -> int | None:
            value = response.get(key)
            return value if isinstance(value, int) else None

        return OllamaCallMetadata(
            model=str(response.get("model", self.config.model)),
            total_duration_ns=optional_int("total_duration"),
            load_duration_ns=optional_int("load_duration"),
            prompt_tokens=optional_int("prompt_eval_count"),
            completion_tokens=optional_int("eval_count"),
        )
