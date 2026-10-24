from collections.abc import Mapping

from app.models.evidence_assistant import (
    ConfidenceAssessment,
    ConfidenceLevel,
    EvidenceDirectness,
    EvidenceItem,
    EvidencePacket,
    ResolutionStatus,
    RetractionStatus,
)

_FACTOR_WEIGHTS = {
    "entity_match": 0.15,
    "evidence_directness": 0.15,
    "target_confidence": 0.10,
    "source_independence": 0.10,
    "comparable_assay_agreement": 0.15,
    "measurement_quality": 0.10,
    "citation_validity": 0.10,
    "retraction_status": 0.10,
    "retrieval_coverage": 0.05,
}
_SEVERE_QUALITY_FLAGS = {
    "LOW_TARGET_CONFIDENCE",
    "NON_MOLAR_MEASUREMENT",
    "POTENTIAL_DUPLICATE",
}


def assess_confidence(
    packet: EvidencePacket,
    citation_ids: list[str],
    *,
    benchmark_by_level: Mapping[ConfidenceLevel, tuple[float, int]] | None = None,
) -> ConfidenceAssessment:
    evidence_by_id = {item.evidence_id: item for item in packet.evidence_items}
    cited = [evidence_by_id[item_id] for item_id in citation_ids if item_id in evidence_by_id]
    considered = cited or packet.evidence_items

    factors = {
        "entity_match": _entity_score(packet.resolution.status),
        "evidence_directness": _directness_score(considered),
        "target_confidence": _target_confidence_score(considered),
        "source_independence": _independence_score(considered),
        "comparable_assay_agreement": _agreement_score(packet),
        "measurement_quality": _measurement_quality_score(considered),
        "citation_validity": _citation_validity_score(citation_ids, evidence_by_id),
        "retraction_status": _retraction_score(considered),
        "retrieval_coverage": _coverage_score(packet.evidence_items),
    }
    overall = sum(factors[name] * weight for name, weight in _FACTOR_WEIGHTS.items())
    factors["overall"] = round(overall, 6)
    high_confidence_gate = (
        factors["source_independence"] == 1.0
        and factors["retrieval_coverage"] == 1.0
        and factors["retraction_status"] >= 0.7
    )
    if overall >= 0.86 and high_confidence_gate:
        level = ConfidenceLevel.HIGH
    elif overall >= 0.62:
        level = ConfidenceLevel.MEDIUM
    else:
        level = ConfidenceLevel.LOW

    benchmark_accuracy: float | None = None
    benchmark_case_count: int | None = None
    if benchmark_by_level and level in benchmark_by_level:
        benchmark_accuracy, benchmark_case_count = benchmark_by_level[level]
    return ConfidenceAssessment(
        level=level,
        factor_scores=factors,
        benchmark_accuracy=benchmark_accuracy,
        benchmark_case_count=benchmark_case_count,
    )


def _entity_score(status: ResolutionStatus) -> float:
    return {
        ResolutionStatus.RESOLVED: 1.0,
        ResolutionStatus.NOT_REQUIRED: 1.0,
        ResolutionStatus.AMBIGUOUS: 0.0,
        ResolutionStatus.UNRESOLVED: 0.0,
    }[status]


def _directness_score(items: list[EvidenceItem]) -> float:
    if not items:
        return 0.0
    scores = {
        EvidenceDirectness.DIRECT: 1.0,
        EvidenceDirectness.INDIRECT: 0.4,
        EvidenceDirectness.CONTEXT_ONLY: 0.2,
    }
    return sum(scores[item.directness] for item in items) / len(items)


def _target_confidence_score(items: list[EvidenceItem]) -> float:
    if not items:
        return 0.0
    scores: list[float] = []
    for item in items:
        raw_score = item.assay_conditions.get("target_confidence_score")
        if isinstance(raw_score, int | float):
            scores.append(max(0.0, min(1.0, float(raw_score) / 9.0)))
        elif item.target_id is not None:
            scores.append(0.6)
        else:
            scores.append(0.0)
    return sum(scores) / len(scores)


def _independence_score(items: list[EvidenceItem]) -> float:
    if not items:
        return 0.0
    sources = {
        (
            item.source_type.value,
            item.paper_id or str(item.assay_conditions.get("assay_id") or item.source_record_id),
        )
        for item in items
    }
    if len(sources) >= 2:
        return 1.0
    return 0.5


def _agreement_score(packet: EvidencePacket) -> float:
    conflicts = packet.conflict_assessment
    if conflicts.decision_conflict:
        return 0.0
    if conflicts.disagreements:
        return 0.5
    return 1.0


def _measurement_quality_score(items: list[EvidenceItem]) -> float:
    if not items:
        return 0.0
    scores: list[float] = []
    for item in items:
        severe_count = sum(
            flag in _SEVERE_QUALITY_FLAGS or flag.startswith("DATA_VALIDITY:")
            for flag in item.quality_flags
        )
        scores.append(max(0.0, 1.0 - severe_count * 0.3))
    return sum(scores) / len(scores)


def _citation_validity_score(
    citation_ids: list[str],
    evidence_by_id: dict[str, EvidenceItem],
) -> float:
    if not citation_ids:
        return 0.0
    valid = sum(
        item_id in evidence_by_id
        and evidence_by_id[item_id].retraction_status != RetractionStatus.RETRACTED
        for item_id in citation_ids
    )
    return valid / len(citation_ids)


def _retraction_score(items: list[EvidenceItem]) -> float:
    if not items:
        return 0.0
    status_scores = {
        RetractionStatus.CLEAR: 1.0,
        RetractionStatus.REINSTATED: 1.0,
        RetractionStatus.CORRECTED: 0.7,
        RetractionStatus.UNKNOWN: 0.4,
        RetractionStatus.EXPRESSION_OF_CONCERN: 0.2,
        RetractionStatus.RETRACTED: 0.0,
    }
    return min(status_scores[item.retraction_status] for item in items)


def _coverage_score(items: list[EvidenceItem]) -> float:
    usable_direct = {
        item.evidence_id
        for item in items
        if item.directness == EvidenceDirectness.DIRECT
        and item.retraction_status != RetractionStatus.RETRACTED
    }
    if len(usable_direct) >= 2:
        return 1.0
    if len(usable_direct) == 1:
        return 0.5
    return 0.0
