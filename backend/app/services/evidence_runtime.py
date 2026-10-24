import json
import os
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.evidence.store import EvidenceStore
from app.models.evidence_assistant import ClaimCheckRequest, ClaimCheckResponse
from app.services.evidence_assistant import EvidenceAssistant
from app.services.ollama import OllamaClient, OllamaConfig
from app.services.pubchem_questions import (
    FrozenPubChemClient,
    PubChemQuestionAssistant,
    PubChemQuestionError,
)

DEFAULT_SNAPSHOT_ID = "chembl-api-37-imatinib-abl1-smoke"
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_DATABASE = (
    _PROJECT_ROOT / "data/processed/chembl-api-37-imatinib-abl1-smoke.sqlite"
)
_DEFAULT_MODEL_CONFIG = _PROJECT_ROOT / "backend/config/evidence/ollama-model.json"
_DEFAULT_PUBCHEM_CACHE = _PROJECT_ROOT / "data/runtime/pubchem-compound-snapshots"


class EvidenceRuntimeError(RuntimeError):
    """Raised when the configured local evidence runtime cannot be started."""


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise EvidenceRuntimeError(f"Ollama configuration is missing {key}")
    return value


def load_ollama_config(path: str | Path) -> OllamaConfig:
    config_path = Path(path).resolve()
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvidenceRuntimeError(
            f"cannot read the pinned Ollama configuration: {config_path}"
        ) from error
    if not isinstance(payload, dict):
        raise EvidenceRuntimeError("the pinned Ollama configuration must be a JSON object")
    return OllamaConfig(
        model=_required_string(payload, "model"),
        expected_digest=_required_string(payload, "digest"),
        base_url=os.environ.get("PROVENANCELAB_OLLAMA_URL", "http://127.0.0.1:11434"),
        timeout_seconds=float(payload.get("timeout_seconds", 120)),
        keep_alive=str(payload.get("keep_alive", "15m")),
        seed=int(payload.get("seed", 42)),
        context_length=int(payload.get("context_length", 8192)),
        maximum_output_tokens=int(payload.get("maximum_output_tokens", 512)),
        structured_output_mode=payload.get("structured_output_mode", "json_schema"),
    )


class EvidenceRuntime:
    """Serialized local-model access with a fresh read-only SQLite handle per request."""

    def __init__(
        self,
        *,
        database_path: str | Path,
        snapshot_ids: tuple[str, ...],
        model_config_path: str | Path,
    ) -> None:
        if not snapshot_ids:
            raise ValueError("at least one evidence snapshot ID is required")
        self.database_path = Path(database_path).resolve()
        self.snapshot_ids = snapshot_ids
        self.model_config_path = Path(model_config_path).resolve()
        self._model: OllamaClient | None = None
        self._pubchem_questions = PubChemQuestionAssistant(
            FrozenPubChemClient(
                os.environ.get("PROVENANCELAB_PUBCHEM_CACHE", str(_DEFAULT_PUBCHEM_CACHE)),
                base_url=os.environ.get(
                    "PROVENANCELAB_PUBCHEM_URL",
                    "https://pubchem.ncbi.nlm.nih.gov/rest/pug",
                ),
            )
        )
        self._lock = threading.Lock()

    @classmethod
    def from_environment(cls) -> "EvidenceRuntime":
        database_path = os.environ.get(
            "PROVENANCELAB_EVIDENCE_DB",
            str(_DEFAULT_DATABASE),
        )
        raw_snapshot_ids = os.environ.get(
            "PROVENANCELAB_EVIDENCE_SNAPSHOTS",
            DEFAULT_SNAPSHOT_ID,
        )
        snapshot_ids = tuple(
            snapshot_id.strip()
            for snapshot_id in raw_snapshot_ids.split(",")
            if snapshot_id.strip()
        )
        model_config_path = os.environ.get(
            "PROVENANCELAB_OLLAMA_CONFIG",
            str(_DEFAULT_MODEL_CONFIG),
        )
        return cls(
            database_path=database_path,
            snapshot_ids=snapshot_ids,
            model_config_path=model_config_path,
        )

    def check_claim(self, request: ClaimCheckRequest) -> ClaimCheckResponse:
        if not self.database_path.is_file():
            raise EvidenceRuntimeError(
                "The frozen evidence snapshot is not configured on this machine."
            )
        if not self.model_config_path.is_file():
            raise EvidenceRuntimeError(
                "The pinned Ollama model configuration is not available on this machine."
            )
        with self._lock:
            try:
                pubchem_response = self._pubchem_questions.try_check(request)
            except PubChemQuestionError as error:
                raise EvidenceRuntimeError(str(error)) from error
            if pubchem_response is not None:
                return pubchem_response
            if self._model is None:
                self._model = OllamaClient(load_ollama_config(self.model_config_path))
            with EvidenceStore.open_read_only(self.database_path) as store:
                assistant = EvidenceAssistant(
                    store=store,
                    snapshot_ids=self.snapshot_ids,
                    model=self._model,
                )
                return assistant.check_claim(request)


@lru_cache(maxsize=1)
def get_evidence_runtime() -> EvidenceRuntime:
    return EvidenceRuntime.from_environment()
