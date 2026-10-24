from app.models.evidence_assistant import (
    AtomicStatement,
    ClaimType,
    ConfidenceLevel,
    ConflictAssessment,
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
from app.services.confidence import assess_confidence
from app.services.verdict_engine import materialize_statement_verdict

HASH = "a" * 64
INCHIKEY = "KTUFNOKKBVMGRW-UHFFFAOYSA-N"


def item(suffix: str, *, paper_id: str, status: RetractionStatus = RetractionStatus.CLEAR):
    return EvidenceItem(
        evidence_id=f"E-{suffix}",
        source_type=EvidenceSourceType.CHEMBL_ACTIVITY,
        source_record_id=suffix,
        basis=EvidenceBasis.EXPERIMENTAL,
        stance=EvidenceStance.SUPPORTS,
        directness=EvidenceDirectness.DIRECT,
        molecule_inchikey=INCHIKEY,
        target_id="CHEMBL1862",
        organism="Homo sapiens",
        endpoint="IC50",
        relation="=",
        value=42,
        unit="nM",
        assay_conditions={"assay_id": f"A-{suffix}", "target_confidence_score": 9},
        paper_id=paper_id,
        retraction_status=status,
        snapshot_id="pilot-v1",
        raw_record_sha256=HASH,
    )


def packet(*items: EvidenceItem) -> EvidencePacket:
    return EvidencePacket(
        statement=AtomicStatement(
            statement_id="S1",
            text="Imatinib inhibits ABL1.",
            claim_type=ClaimType.BIOLOGICAL_ACTIVITY,
            molecule_mentions=["Imatinib"],
            target_mentions=["ABL1"],
        ),
        resolution=ResolutionSummary(
            status=ResolutionStatus.RESOLVED,
            molecule_inchikey=INCHIKEY,
            target_id="CHEMBL1862",
            organism="Homo sapiens",
        ),
        evidence_items=list(items),
        conflict_assessment=ConflictAssessment(),
    )


def test_one_clear_direct_source_is_medium_not_overconfident() -> None:
    evidence = item("1", paper_id="P1")
    confidence = assess_confidence(packet(evidence), [evidence.evidence_id])
    assert confidence.level == ConfidenceLevel.MEDIUM
    assert confidence.factor_scores["source_independence"] == 0.5
    assert confidence.factor_scores["retrieval_coverage"] == 0.5


def test_two_independent_clear_sources_can_reach_high_confidence() -> None:
    first = item("1", paper_id="P1")
    second = item("2", paper_id="P2")
    confidence = assess_confidence(
        packet(first, second),
        [first.evidence_id, second.evidence_id],
    )
    assert confidence.level == ConfidenceLevel.HIGH
    assert confidence.factor_scores["source_independence"] == 1.0


def test_unknown_retraction_status_caps_confidence() -> None:
    evidence = item("1", paper_id="P1", status=RetractionStatus.UNKNOWN)
    confidence = assess_confidence(packet(evidence), [evidence.evidence_id])
    assert confidence.level == ConfidenceLevel.MEDIUM
    assert confidence.factor_scores["retraction_status"] == 0.4


def test_materialized_verdict_uses_deterministic_confidence_and_calibration() -> None:
    first = item("1", paper_id="P1")
    second = item("2", paper_id="P2")
    evidence_packet = packet(first, second)
    proposal = VerdictProposal(
        statement_id="S1",
        verdict=Verdict.SUPPORTED,
        citation_ids=[first.evidence_id, second.evidence_id],
        reason="Two direct experimental records support the claim.",
    )
    result = materialize_statement_verdict(
        evidence_packet,
        proposal,
        benchmark_by_level={ConfidenceLevel.HIGH: (0.91, 35)},
    )
    assert result.confidence.level == ConfidenceLevel.HIGH
    assert result.confidence.benchmark_accuracy == 0.91
    assert result.confidence.benchmark_case_count == 35
    assert [citation.evidence_id for citation in result.citations] == ["E-1", "E-2"]


def test_abstention_without_evidence_is_low_confidence() -> None:
    empty_packet = packet()
    proposal = VerdictProposal(
        statement_id="S1",
        verdict=Verdict.INSUFFICIENT_EVIDENCE,
        citation_ids=[],
        reason="No direct evidence was found in the frozen snapshot.",
        reason_codes=[DecisionReasonCode.NO_DIRECT_EVIDENCE],
    )
    result = materialize_statement_verdict(empty_packet, proposal)
    assert result.confidence.level == ConfidenceLevel.LOW


def test_same_paper_records_do_not_count_as_independent_sources() -> None:
    first = item("1", paper_id="P1")
    second = item("2", paper_id="P1")
    confidence = assess_confidence(
        packet(first, second),
        [first.evidence_id, second.evidence_id],
    )
    assert confidence.level == ConfidenceLevel.MEDIUM
    assert confidence.factor_scores["source_independence"] == 0.5
