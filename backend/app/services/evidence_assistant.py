import hashlib
import json
import re
from collections.abc import Mapping

from app.evidence.store import EvidenceStore
from app.models.evidence_assistant import (
    RESEARCH_AID_NOTICE,
    ClaimCheckRequest,
    ClaimCheckResponse,
    ClaimDecomposition,
    ConfidenceLevel,
    DecisionReasonCode,
    EvidenceAssistantManifest,
    EvidenceDirectness,
    EvidencePacket,
    EvidenceStance,
    RetractionStatus,
    Verdict,
    VerdictProposal,
)
from app.services.claim_routing import ClaimRoute, EntityResolver, duplicate_statement_pairs
from app.services.evidence_retrieval import EvidencePacketBuilder
from app.services.ollama import OllamaClient, OllamaError
from app.services.verdict_engine import materialize_statement_verdict
from app.services.verdict_validation import (
    VerdictValidationError,
    default_insufficient_reason,
)

PIPELINE_VERSION = "phase2-orchestrator-v1"


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _deduplicate(decomposition: ClaimDecomposition) -> ClaimDecomposition:
    duplicate_ids = {right for _, right in duplicate_statement_pairs(decomposition)}
    statements = [
        statement.model_copy(update={"statement_id": f"S{index}"})
        for index, statement in enumerate(
            (
                statement
                for statement in decomposition.statements
                if statement.statement_id not in duplicate_ids
            ),
            start=1,
        )
    ]
    return ClaimDecomposition(statements=statements)


def _scope_reason(statement_text: str) -> DecisionReasonCode:
    lowered = statement_text.casefold()
    if re.search(r"\b(?:should i|the patient|personalized|for me)\b", lowered):
        return DecisionReasonCode.PERSONALIZED_ADVICE_OUT_OF_SCOPE
    if re.search(r"\b(?:safe|safely|safety|side effects?|toxicity|toxic)\b", lowered):
        return DecisionReasonCode.SAFETY_PREDICTION_OUT_OF_SCOPE
    if re.search(r"\b(?:will|future|cure)\b", lowered):
        return DecisionReasonCode.FUTURE_EFFICACY_OUT_OF_SCOPE
    return DecisionReasonCode.CLINICAL_PREDICTION_OUT_OF_SCOPE


def _deterministic_abstention(packet: EvidencePacket) -> VerdictProposal | None:
    if packet.conflict_assessment.decision_conflict:
        cited_ids = list(
            dict.fromkeys(
                evidence_id
                for disagreement in packet.conflict_assessment.disagreements
                if disagreement.comparable
                for evidence_id in disagreement.evidence_ids
            )
        )
        return VerdictProposal(
            statement_id=packet.statement.statement_id,
            verdict=Verdict.INSUFFICIENT_EVIDENCE,
            citation_ids=cited_ids,
            reason="Comparable direct assays disagree, so the system abstained.",
            reason_codes=[DecisionReasonCode.CONFLICTING_ASSAYS],
            limitations=["A scientific reviewer should inspect the conflicting assay contexts."],
            conflict_summary=packet.conflict_assessment.summary,
        )

    actionable = [
        item
        for item in packet.evidence_items
        if item.directness == EvidenceDirectness.DIRECT
        and item.stance in {EvidenceStance.SUPPORTS, EvidenceStance.CONTRADICTS}
        and item.retraction_status != RetractionStatus.RETRACTED
    ]
    if actionable:
        return None
    reason_code = default_insufficient_reason(packet)
    inspected_ids = [item.evidence_id for item in packet.evidence_items[:10]]
    return VerdictProposal(
        statement_id=packet.statement.statement_id,
        verdict=Verdict.INSUFFICIENT_EVIDENCE,
        citation_ids=inspected_ids,
        reason="No eligible direct evidence can decide this statement in the frozen snapshot.",
        reason_codes=[reason_code],
        limitations=["The result is limited to the configured frozen evidence snapshot."],
    )


class EvidenceAssistant:
    """Fail-closed orchestration around a pinned model and frozen evidence store."""

    def __init__(
        self,
        *,
        store: EvidenceStore,
        snapshot_ids: tuple[str, ...],
        model: OllamaClient,
        benchmark_by_level: Mapping[ConfidenceLevel, tuple[float, int]] | None = None,
    ) -> None:
        if not snapshot_ids:
            raise ValueError("evidence assistant requires at least one snapshot")
        snapshot_hashes = {
            snapshot_id: store.verified_snapshot_hash(snapshot_id)
            for snapshot_id in snapshot_ids
        }
        identity = model.verify_model()
        self._store = store
        self._snapshot_ids = snapshot_ids
        self._model = model
        self._resolver = EntityResolver(store, snapshot_ids)
        self._packets = EvidencePacketBuilder(store, snapshot_ids)
        self._benchmark_by_level = benchmark_by_level
        self._model_name = identity.name
        self._model_digest = identity.digest
        self._snapshot_label = "+".join(
            f"{snapshot_id}@{snapshot_hashes[snapshot_id][:12]}"
            for snapshot_id in snapshot_ids
        )
        self._configuration_hash = _sha256(
            {
                "pipeline_version": PIPELINE_VERSION,
                "model": identity.name,
                "model_digest": identity.digest,
                "structured_output_mode": model.config.structured_output_mode,
                "snapshots": snapshot_hashes,
            }
        )

    def check_claim(self, request: ClaimCheckRequest) -> ClaimCheckResponse:
        decomposition = _deduplicate(self._model.decompose_claim(request).value)
        verdicts = []
        run_record_ids = tuple(request.run_record_ids)
        for statement in decomposition.statements:
            resolved = self._resolver.resolve_and_route(statement)
            packet = self._packets.build(resolved, run_record_ids=run_record_ids)
            if resolved.routing.route == ClaimRoute.OUT_OF_SCOPE_REVIEW:
                proposal = VerdictProposal(
                    statement_id=packet.statement.statement_id,
                    verdict=Verdict.OUT_OF_SCOPE,
                    reason=(
                        "Clinical efficacy, safety prediction, or personalized treatment advice "
                        "is outside this evidence assistant's scope."
                    ),
                    reason_codes=[_scope_reason(packet.statement.text)],
                )
            else:
                proposal = _deterministic_abstention(packet)
                if proposal is None:
                    try:
                        proposed = self._model.propose_verdict(packet).value
                        verdict = materialize_statement_verdict(
                            packet,
                            proposed,
                            benchmark_by_level=self._benchmark_by_level,
                        )
                    except (OllamaError, VerdictValidationError):
                        proposal = VerdictProposal(
                            statement_id=packet.statement.statement_id,
                            verdict=Verdict.INSUFFICIENT_EVIDENCE,
                            reason=(
                                "The local model output could not be accepted under the "
                                "deterministic evidence contract, so the system abstained."
                            ),
                            reason_codes=[DecisionReasonCode.MODEL_OUTPUT_REJECTED],
                            limitations=["No model-generated decisive verdict was exposed."],
                        )
                    else:
                        verdicts.append(verdict)
                        continue
            verdicts.append(
                materialize_statement_verdict(
                    packet,
                    proposal,
                    benchmark_by_level=self._benchmark_by_level,
                )
            )

        input_hash = _sha256(request.model_dump(mode="json"))
        output_payload = {
            "verdicts": [verdict.model_dump(mode="json") for verdict in verdicts],
            "research_aid_notice": RESEARCH_AID_NOTICE,
        }
        output_hash = _sha256(output_payload)
        return ClaimCheckResponse(
            assistant_run_id=f"EA-{input_hash[:12]}-{output_hash[:12]}",
            verdicts=verdicts,
            manifest=EvidenceAssistantManifest(
                model_name=self._model_name,
                model_digest=self._model_digest,
                evidence_snapshot_id=self._snapshot_label,
                input_sha256=input_hash,
                configuration_sha256=self._configuration_hash,
                output_sha256=output_hash,
            ),
        )
