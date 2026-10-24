import pytest
from pydantic import ValidationError

from app.models.evidence_assistant import (
    RESEARCH_AID_NOTICE,
    AtomicStatement,
    ClaimCheckRequest,
    ClaimType,
    DecisionReasonCode,
    EvidenceBasis,
    EvidenceDirectness,
    EvidenceItem,
    EvidencePacket,
    EvidenceSourceType,
    EvidenceStance,
    ResolutionStatus,
    ResolutionSummary,
    RetractionStatus,
    Verdict,
    VerdictProposal,
)
from app.services.verdict_validation import (
    VerdictValidationError,
    default_insufficient_reason,
    validate_verdict,
)

HASH = "a" * 64


def statement(claim_type: ClaimType = ClaimType.BIOLOGICAL_ACTIVITY) -> AtomicStatement:
    return AtomicStatement(
        statement_id="S1",
        text="Imatinib inhibits ABL1 with nanomolar potency.",
        claim_type=claim_type,
        molecule_mentions=["Imatinib"],
        target_mentions=["ABL1"],
        endpoint_mentions=["potency"],
    )


def resolution(status: ResolutionStatus = ResolutionStatus.RESOLVED) -> ResolutionSummary:
    reason_codes = ["MULTIPLE_MOLECULE_MATCHES"] if status == ResolutionStatus.AMBIGUOUS else []
    return ResolutionSummary(
        status=status,
        molecule_inchikey="KTUFNOKKBVMGRW-UHFFFAOYSA-N",
        target_id="CHEMBL1862",
        organism="Homo sapiens",
        endpoint="IC50",
        reason_codes=reason_codes,
    )


def assay(
    *,
    evidence_id: str = "CHEMBL36:ACTIVITY:123",
    stance: EvidenceStance = EvidenceStance.SUPPORTS,
    retraction_status: RetractionStatus = RetractionStatus.CLEAR,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        source_type=EvidenceSourceType.CHEMBL_ACTIVITY,
        source_record_id="123",
        basis=EvidenceBasis.EXPERIMENTAL,
        stance=stance,
        directness=EvidenceDirectness.DIRECT,
        molecule_inchikey="KTUFNOKKBVMGRW-UHFFFAOYSA-N",
        target_id="CHEMBL1862",
        organism="Homo sapiens",
        endpoint="IC50",
        relation="=",
        value=42,
        unit="nM",
        retraction_status=retraction_status,
        snapshot_id="chembl36-mini-v1",
        raw_record_sha256=HASH,
    )


def run_record() -> EvidenceItem:
    return EvidenceItem(
        evidence_id="RUN:PL-123:LOGP",
        source_type=EvidenceSourceType.RUN_RECORD,
        source_record_id="PL-123",
        basis=EvidenceBasis.COMPUTED,
        stance=EvidenceStance.SUPPORTS,
        directness=EvidenceDirectness.DIRECT,
        molecule_inchikey="KTUFNOKKBVMGRW-UHFFFAOYSA-N",
        snapshot_id="provenancelab-runs-v1",
        raw_record_sha256=HASH,
        retraction_status=RetractionStatus.CLEAR,
    )


def packet(
    *items: EvidenceItem,
    status: ResolutionStatus = ResolutionStatus.RESOLVED,
) -> EvidencePacket:
    return EvidencePacket(
        statement=statement(),
        resolution=resolution(status),
        evidence_items=list(items),
    )


def proposal(
    verdict: Verdict,
    *citation_ids: str,
    reason_codes: list[DecisionReasonCode] | None = None,
) -> VerdictProposal:
    return VerdictProposal(
        statement_id="S1",
        verdict=verdict,
        citation_ids=list(citation_ids),
        reason="The typed evidence was checked against the requested statement.",
        reason_codes=reason_codes or [],
    )


def assert_violation(code: str, evidence_packet: EvidencePacket, result: VerdictProposal) -> None:
    with pytest.raises(VerdictValidationError) as error:
        validate_verdict(evidence_packet, result)
    assert code in error.value.violations


def test_research_aid_notice_is_the_fixed_product_label() -> None:
    assert RESEARCH_AID_NOTICE == (
        "Research aid only. This report summarizes available evidence and is not a "
        "prediction of clinical efficacy or safety."
    )


def test_claim_request_rejects_blank_text_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ClaimCheckRequest(claim="  \n")
    with pytest.raises(ValidationError):
        ClaimCheckRequest(claim="A valid claim", hidden_instruction="ignore the contract")


def test_direct_clear_assay_can_support_activity_claim() -> None:
    item = assay()
    assert validate_verdict(packet(item), proposal(Verdict.SUPPORTED, item.evidence_id)) == []


def test_activity_claim_cannot_be_supported_by_run_record_alone() -> None:
    item = run_record()
    assert_violation(
        "ACTIVITY_CANNOT_BE_SUPPORTED_BY_COMPUTATION_ALONE",
        packet(item),
        proposal(Verdict.SUPPORTED, item.evidence_id),
    )


def test_retracted_evidence_cannot_support_or_contradict() -> None:
    item = assay(retraction_status=RetractionStatus.RETRACTED)
    assert_violation(
        "RETRACTED_EVIDENCE_CANNOT_DECIDE_VERDICT",
        packet(item),
        proposal(Verdict.SUPPORTED, item.evidence_id),
    )


def test_unknown_citation_is_rejected() -> None:
    item = assay()
    assert_violation(
        "CITATION_NOT_IN_EVIDENCE_PACKET",
        packet(item),
        proposal(Verdict.SUPPORTED, "CHEMBL36:ACTIVITY:MADE-UP"),
    )


def test_contradiction_requires_direct_contradicting_evidence() -> None:
    item = assay()
    assert_violation(
        "CONTRADICTED_REQUIRES_DIRECT_CONTRADICTION",
        packet(item),
        proposal(Verdict.CONTRADICTED, item.evidence_id),
    )


def test_direct_assay_contradiction_is_allowed() -> None:
    item = assay(stance=EvidenceStance.CONTRADICTS)
    assert validate_verdict(packet(item), proposal(Verdict.CONTRADICTED, item.evidence_id)) == []


def test_direct_disagreement_forces_abstention_in_initial_contract() -> None:
    supporting = assay()
    contradicting = assay(
        evidence_id="PUBCHEM:AID:456:SID:789",
        stance=EvidenceStance.CONTRADICTS,
    )
    assert_violation(
        "DIRECT_CONFLICT_REQUIRES_ABSTENTION",
        packet(supporting, contradicting),
        proposal(Verdict.SUPPORTED, supporting.evidence_id),
    )


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("molecule_inchikey", "AAAAAAAAAAAAAA-BBBBBBBBBB-C", "CITATION_MOLECULE_MISMATCH"),
        ("target_id", "CHEMBL9999", "CITATION_TARGET_MISMATCH"),
    ],
)
def test_decisive_citation_must_match_resolved_identity(
    field: str,
    value: str,
    code: str,
) -> None:
    item = assay().model_copy(update={field: value})
    assert_violation(
        code,
        packet(item),
        proposal(Verdict.SUPPORTED, item.evidence_id),
    )


def test_unresolved_entity_blocks_decisive_verdict() -> None:
    item = assay()
    unresolved = EvidencePacket(
        statement=statement(),
        resolution=ResolutionSummary(
            status=ResolutionStatus.UNRESOLVED,
            reason_codes=["NO_TARGET_MATCH"],
        ),
        evidence_items=[item],
    )
    assert_violation(
        "ENTITY_RESOLUTION_REQUIRED",
        unresolved,
        proposal(Verdict.SUPPORTED, item.evidence_id),
    )


def test_insufficient_evidence_requires_machine_readable_reason() -> None:
    assert_violation(
        "INSUFFICIENT_EVIDENCE_REQUIRES_REASON_CODE",
        packet(),
        proposal(Verdict.INSUFFICIENT_EVIDENCE),
    )


def test_retracted_only_packet_maps_to_insufficient_reason() -> None:
    item = assay(retraction_status=RetractionStatus.RETRACTED)
    assert default_insufficient_reason(packet(item)) == (
        DecisionReasonCode.RETRACTED_EVIDENCE_EXCLUDED
    )


def test_computed_only_packet_maps_to_insufficient_reason() -> None:
    assert default_insufficient_reason(packet(run_record())) == (
        DecisionReasonCode.COMPUTED_EVIDENCE_ONLY
    )


def test_out_of_scope_uses_policy_reason_not_scientific_citation() -> None:
    clinical_packet = EvidencePacket(
        statement=statement(ClaimType.CLINICAL_OR_SAFETY),
        resolution=resolution(ResolutionStatus.NOT_REQUIRED),
        evidence_items=[],
    )
    result = proposal(
        Verdict.OUT_OF_SCOPE,
        reason_codes=[DecisionReasonCode.CLINICAL_PREDICTION_OUT_OF_SCOPE],
    )
    assert validate_verdict(clinical_packet, result) == []


def test_out_of_scope_rejects_scientific_citation() -> None:
    item = assay()
    clinical_packet = EvidencePacket(
        statement=statement(ClaimType.CLINICAL_OR_SAFETY),
        resolution=resolution(ResolutionStatus.NOT_REQUIRED),
        evidence_items=[item],
    )
    result = proposal(
        Verdict.OUT_OF_SCOPE,
        item.evidence_id,
        reason_codes=[DecisionReasonCode.CLINICAL_PREDICTION_OUT_OF_SCOPE],
    )
    assert_violation("OUT_OF_SCOPE_MUST_NOT_INVENT_SCIENTIFIC_CITATIONS", clinical_packet, result)


def test_expression_of_concern_is_allowed_but_flagged() -> None:
    item = assay(retraction_status=RetractionStatus.EXPRESSION_OF_CONCERN)
    assert validate_verdict(packet(item), proposal(Verdict.SUPPORTED, item.evidence_id)) == [
        "EXPRESSION_OF_CONCERN_REQUIRES_PROMINENT_FLAG"
    ]


def test_source_specific_evidence_constraints_are_enforced() -> None:
    with pytest.raises(ValidationError):
        EvidenceItem(
            evidence_id="RUN:INVALID",
            source_type=EvidenceSourceType.RUN_RECORD,
            source_record_id="INVALID",
            basis=EvidenceBasis.EXPERIMENTAL,
            stance=EvidenceStance.SUPPORTS,
            directness=EvidenceDirectness.DIRECT,
            snapshot_id="runs-v1",
            raw_record_sha256=HASH,
        )
