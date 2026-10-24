from collections.abc import Mapping

from app.models.evidence_assistant import (
    ConfidenceLevel,
    DecisionReasonCode,
    EvidencePacket,
    StatementVerdict,
    VerdictProposal,
)
from app.services.confidence import assess_confidence
from app.services.verdict_validation import validate_verdict


def materialize_statement_verdict(
    packet: EvidencePacket,
    proposal: VerdictProposal,
    *,
    benchmark_by_level: Mapping[ConfidenceLevel, tuple[float, int]] | None = None,
) -> StatementVerdict:
    """Turn a model proposal into a typed verdict after deterministic enforcement."""

    warnings = validate_verdict(packet, proposal)
    evidence_by_id = {item.evidence_id: item for item in packet.evidence_items}
    citations = [evidence_by_id[item_id] for item_id in proposal.citation_ids]
    limitations = list(dict.fromkeys([*proposal.limitations, *warnings]))
    conflict_summary = (
        packet.conflict_assessment.summary
        if packet.conflict_assessment.disagreements
        else proposal.conflict_summary
    )
    confidence = assess_confidence(
        packet,
        proposal.citation_ids,
        benchmark_by_level=benchmark_by_level,
    )
    if DecisionReasonCode.MODEL_OUTPUT_REJECTED in proposal.reason_codes:
        factor_scores = dict(confidence.factor_scores)
        factor_scores["synthesis_validity"] = 0.0
        factor_scores["overall"] = min(factor_scores["overall"], 0.4)
        confidence = confidence.model_copy(
            update={"level": ConfidenceLevel.LOW, "factor_scores": factor_scores}
        )
    return StatementVerdict(
        statement=packet.statement,
        resolution=packet.resolution,
        verdict=proposal.verdict,
        citations=citations,
        reason=proposal.reason,
        reason_codes=proposal.reason_codes,
        limitations=limitations,
        conflict_summary=conflict_summary,
        confidence=confidence,
    )
