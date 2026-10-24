from app.models.evidence_assistant import (
    OUT_OF_SCOPE_REASON_CODES,
    ClaimType,
    DecisionReasonCode,
    EvidenceBasis,
    EvidenceDirectness,
    EvidencePacket,
    EvidenceStance,
    ResolutionStatus,
    RetractionStatus,
    Verdict,
    VerdictProposal,
)


class VerdictValidationError(ValueError):
    """Raised when a model-proposed verdict violates the evidence contract."""

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        super().__init__("; ".join(violations))


def validate_verdict(packet: EvidencePacket, proposal: VerdictProposal) -> list[str]:
    """Return non-fatal warnings or raise when a proposal is not legally allowed.

    This validator intentionally does not judge free text. It checks only facts that
    the retrieval pipeline has represented as typed, reproducible evidence metadata.
    """

    violations: list[str] = []
    warnings: list[str] = []

    if proposal.statement_id != packet.statement.statement_id:
        violations.append("STATEMENT_ID_MISMATCH")

    evidence_by_id = {item.evidence_id: item for item in packet.evidence_items}
    unknown_citations = [
        citation_id for citation_id in proposal.citation_ids if citation_id not in evidence_by_id
    ]
    if unknown_citations:
        violations.append("CITATION_NOT_IN_EVIDENCE_PACKET")

    cited = [
        evidence_by_id[citation_id]
        for citation_id in proposal.citation_ids
        if citation_id in evidence_by_id
    ]

    if proposal.verdict in {Verdict.SUPPORTED, Verdict.CONTRADICTED}:
        if packet.resolution.status not in {
            ResolutionStatus.RESOLVED,
            ResolutionStatus.NOT_REQUIRED,
        }:
            violations.append("ENTITY_RESOLUTION_REQUIRED")
        if not cited:
            violations.append("DECISIVE_VERDICT_REQUIRES_CITATION")
        if any(item.retraction_status == RetractionStatus.RETRACTED for item in cited):
            violations.append("RETRACTED_EVIDENCE_CANNOT_DECIDE_VERDICT")
        if packet.resolution.molecule_inchikey and any(
            item.molecule_inchikey != packet.resolution.molecule_inchikey for item in cited
        ):
            violations.append("CITATION_MOLECULE_MISMATCH")
        if packet.resolution.target_id and any(
            item.target_id != packet.resolution.target_id for item in cited
        ):
            violations.append("CITATION_TARGET_MISMATCH")
        if packet.conflict_assessment.decision_conflict:
            violations.append("COMPARABLE_ASSAY_CONFLICT_REQUIRES_ABSTENTION")

    direct_support = [
        item
        for item in cited
        if item.directness == EvidenceDirectness.DIRECT
        and item.stance == EvidenceStance.SUPPORTS
    ]
    direct_contradiction = [
        item
        for item in cited
        if item.directness == EvidenceDirectness.DIRECT
        and item.stance == EvidenceStance.CONTRADICTS
    ]
    packet_direct_support = [
        item
        for item in packet.evidence_items
        if item.directness == EvidenceDirectness.DIRECT
        and item.stance == EvidenceStance.SUPPORTS
        and item.retraction_status != RetractionStatus.RETRACTED
    ]
    packet_direct_contradiction = [
        item
        for item in packet.evidence_items
        if item.directness == EvidenceDirectness.DIRECT
        and item.stance == EvidenceStance.CONTRADICTS
        and item.retraction_status != RetractionStatus.RETRACTED
    ]

    if proposal.verdict == Verdict.SUPPORTED:
        if not direct_support:
            violations.append("SUPPORTED_REQUIRES_DIRECT_SUPPORT")
        if packet_direct_support and packet_direct_contradiction:
            violations.append("DIRECT_CONFLICT_REQUIRES_ABSTENTION")
        if packet.statement.claim_type == ClaimType.BIOLOGICAL_ACTIVITY:
            experimental_support = [
                item for item in direct_support if item.basis == EvidenceBasis.EXPERIMENTAL
            ]
            if not experimental_support:
                violations.append("ACTIVITY_CANNOT_BE_SUPPORTED_BY_COMPUTATION_ALONE")

    elif proposal.verdict == Verdict.CONTRADICTED:
        if not direct_contradiction:
            violations.append("CONTRADICTED_REQUIRES_DIRECT_CONTRADICTION")
        if packet.statement.claim_type == ClaimType.BIOLOGICAL_ACTIVITY:
            experimental_contradiction = [
                item for item in direct_contradiction if item.basis == EvidenceBasis.EXPERIMENTAL
            ]
            if not experimental_contradiction:
                violations.append("ACTIVITY_CONTRADICTION_REQUIRES_EXPERIMENTAL_EVIDENCE")

    elif proposal.verdict == Verdict.INSUFFICIENT_EVIDENCE:
        if not proposal.reason_codes:
            violations.append("INSUFFICIENT_EVIDENCE_REQUIRES_REASON_CODE")
        if (
            packet.conflict_assessment.decision_conflict
            and DecisionReasonCode.CONFLICTING_ASSAYS not in proposal.reason_codes
        ):
            violations.append("ASSAY_CONFLICT_REQUIRES_CONFLICT_REASON_CODE")

    elif proposal.verdict == Verdict.OUT_OF_SCOPE:
        if proposal.citation_ids:
            violations.append("OUT_OF_SCOPE_MUST_NOT_INVENT_SCIENTIFIC_CITATIONS")
        if not OUT_OF_SCOPE_REASON_CODES.intersection(proposal.reason_codes):
            violations.append("OUT_OF_SCOPE_REQUIRES_SCOPE_REASON_CODE")
        if packet.statement.claim_type != ClaimType.CLINICAL_OR_SAFETY:
            warnings.append("OUT_OF_SCOPE_NONCLINICAL_CLAIM_REQUIRES_POLICY_REVIEW")

    if proposal.verdict != Verdict.OUT_OF_SCOPE and OUT_OF_SCOPE_REASON_CODES.intersection(
        proposal.reason_codes
    ):
        violations.append("SCOPE_REASON_CODE_REQUIRES_OUT_OF_SCOPE_VERDICT")

    if any(
        item.retraction_status == RetractionStatus.EXPRESSION_OF_CONCERN for item in cited
    ):
        warnings.append("EXPRESSION_OF_CONCERN_REQUIRES_PROMINENT_FLAG")
    if any(item.retraction_status == RetractionStatus.UNKNOWN for item in cited):
        warnings.append("UNKNOWN_RETRACTION_STATUS_LIMITS_CONFIDENCE")

    if violations:
        raise VerdictValidationError(violations)
    return warnings


def default_insufficient_reason(packet: EvidencePacket) -> DecisionReasonCode:
    """Choose a deterministic abstention reason from packet metadata."""

    if packet.resolution.status == ResolutionStatus.AMBIGUOUS:
        return DecisionReasonCode.AMBIGUOUS_ENTITY
    if packet.resolution.status == ResolutionStatus.UNRESOLVED:
        return DecisionReasonCode.UNRESOLVED_ENTITY
    if packet.conflict_assessment.decision_conflict:
        return DecisionReasonCode.CONFLICTING_ASSAYS
    if packet.evidence_items and all(
        item.retraction_status == RetractionStatus.RETRACTED for item in packet.evidence_items
    ):
        return DecisionReasonCode.RETRACTED_EVIDENCE_EXCLUDED
    if packet.evidence_items and all(
        item.basis == EvidenceBasis.COMPUTED for item in packet.evidence_items
    ):
        return DecisionReasonCode.COMPUTED_EVIDENCE_ONLY
    if packet.evidence_items and all(
        item.directness != EvidenceDirectness.DIRECT for item in packet.evidence_items
    ):
        return DecisionReasonCode.INDIRECT_EVIDENCE_ONLY
    return DecisionReasonCode.NO_DIRECT_EVIDENCE
