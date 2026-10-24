from pathlib import Path

import pytest

from app.evidence import EvidenceStore, SnapshotSpec
from app.models.evidence_assistant import (
    AssayDisagreementKind,
    AtomicStatement,
    ClaimType,
    DecisionReasonCode,
    EvidenceStance,
    ResolutionStatus,
    Verdict,
    VerdictProposal,
)
from app.services.assay_evidence import (
    StructuredAssayPacketBuilder,
    measurement_interval,
    parse_activity_constraint,
    stance_for_measurement,
    to_molar,
)
from app.services.claim_routing import EntityResolver
from app.services.verdict_validation import (
    VerdictValidationError,
    default_insufficient_reason,
    validate_verdict,
)

HASH = "a" * 64
SNAPSHOT_ID = "chembl36-pilot-v1"
IMATINIB = "KTUFNOKKBVMGRW-UHFFFAOYSA-N"


@pytest.fixture
def store(tmp_path: Path) -> EvidenceStore:
    evidence_store = EvidenceStore.create(tmp_path / "evidence.sqlite")
    evidence_store.register_snapshot(
        SnapshotSpec(
            snapshot_id=SNAPSHOT_ID,
            source_name="ChEMBL",
            source_version="36",
            source_sha256=HASH,
            scope={},
            created_at="2026-10-24T00:00:00Z",
        )
    )
    evidence_store.add_molecule(
        snapshot_id=SNAPSHOT_ID,
        inchikey=IMATINIB,
        canonical_smiles="CC",
        preferred_name="Imatinib",
        raw_record_sha256=HASH,
    )
    evidence_store.add_molecule_alias(
        snapshot_id=SNAPSHOT_ID,
        inchikey=IMATINIB,
        alias="Imatinib",
        source="ChEMBL",
    )
    evidence_store.add_target(
        snapshot_id=SNAPSHOT_ID,
        target_id="CHEMBL1862",
        preferred_name="ABL1",
        organism="Homo sapiens",
        raw_record_sha256=HASH,
    )
    evidence_store.add_target_alias(
        snapshot_id=SNAPSHOT_ID,
        target_id="CHEMBL1862",
        alias="ABL1",
        source="ChEMBL",
    )
    evidence_store.add_paper(
        snapshot_id=SNAPSHOT_ID,
        paper_id="CHEMBL:DOC:1",
        title="ABL1 inhibition",
        retraction_status="CLEAR",
        raw_record_sha256=HASH,
    )
    yield evidence_store
    evidence_store.close()


def add_activity(
    store: EvidenceStore,
    *,
    suffix: str,
    value: float,
    unit: str = "nM",
    relation: str = "=",
    conditions: dict[str, str] | None = None,
    outcome: str | None = None,
    target_confidence: int = 9,
) -> None:
    store.add_assay(
        snapshot_id=SNAPSHOT_ID,
        assay_id=f"ASSAY-{suffix}",
        source="CHEMBL",
        target_id="CHEMBL1862",
        organism="Homo sapiens",
        assay_type="B",
        description="Direct ABL1 binding assay",
        conditions=conditions,
        target_confidence_score=target_confidence,
        paper_id="CHEMBL:DOC:1",
        raw_record_sha256=HASH,
    )
    store.add_activity(
        snapshot_id=SNAPSHOT_ID,
        activity_id=f"ACT-{suffix}",
        assay_id=f"ASSAY-{suffix}",
        molecule_inchikey=IMATINIB,
        measurement_type="IC50",
        standard_value=value,
        standard_unit=unit,
        standard_relation=relation,
        activity_outcome=outcome,
        raw_record_sha256=HASH,
    )


def statement(text: str = "Imatinib inhibits ABL1 with nanomolar potency.") -> AtomicStatement:
    return AtomicStatement(
        statement_id="S1",
        text=text,
        claim_type=ClaimType.BIOLOGICAL_ACTIVITY,
        molecule_mentions=["Imatinib"],
        target_mentions=["ABL1"],
        endpoint_mentions=["IC50"],
    )


def build_packet(
    store: EvidenceStore,
    text: str = "Imatinib inhibits ABL1 with nanomolar potency.",
):
    resolver = EntityResolver(store, (SNAPSHOT_ID,))
    resolved = resolver.resolve_and_route(statement(text))
    assert resolved.resolution.status == ResolutionStatus.RESOLVED
    return StructuredAssayPacketBuilder(store, (SNAPSHOT_ID,)).build(resolved)


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [(42, "nM", 42e-9), (2.5, "µM", 2.5e-6), (1, "mg/mL", None)],
)
def test_molar_unit_normalization(value: float, unit: str, expected: float | None) -> None:
    if expected is None:
        assert to_molar(value, unit) is None
    else:
        assert to_molar(value, unit) == pytest.approx(expected)


def test_censored_measurement_preserves_an_interval() -> None:
    interval = measurement_interval(50, "nM", "<")
    assert interval is not None
    assert interval.lower_molar is None
    assert interval.upper_molar == pytest.approx(50e-9)
    assert interval.exact_molar is None


def test_nanomolar_claim_is_evaluated_against_typed_measurement() -> None:
    constraint = parse_activity_constraint(statement())
    assert stance_for_measurement(
        constraint,
        interval=measurement_interval(42, "nM", "="),
        activity_outcome=None,
    ) == EvidenceStance.SUPPORTS
    assert stance_for_measurement(
        constraint,
        interval=measurement_interval(42, "uM", "="),
        activity_outcome=None,
    ) == EvidenceStance.CONTRADICTS


def test_inconclusive_outcome_is_not_mislabelled_as_contradiction() -> None:
    constraint = parse_activity_constraint(statement("Imatinib inhibits ABL1."))
    assert stance_for_measurement(
        constraint,
        interval=None,
        activity_outcome="Inconclusive",
    ) == EvidenceStance.NEUTRAL


def test_packet_builder_creates_traceable_assay_citation(store: EvidenceStore) -> None:
    add_activity(store, suffix="1", value=42)
    packet = build_packet(store)
    assert len(packet.evidence_items) == 1
    item = packet.evidence_items[0]
    assert item.evidence_id == f"{SNAPSHOT_ID}:CHEMBL:ACTIVITY:ACT-1"
    assert item.source_record_id == "ACT-1"
    assert item.stance == EvidenceStance.SUPPORTS
    assert item.value == 42
    assert item.unit == "nM"
    assert item.paper_id == "CHEMBL:DOC:1"
    assert item.assay_conditions["assay_id"] == "ASSAY-1"
    assert item.raw_record_sha256 == HASH


def test_matching_assays_with_opposite_stance_force_abstention(
    store: EvidenceStore,
) -> None:
    add_activity(store, suffix="support", value=42)
    add_activity(store, suffix="contradict", value=42, unit="uM")
    packet = build_packet(store)
    conflict = packet.conflict_assessment
    assert conflict.decision_conflict
    assert len(conflict.disagreements) == 1
    assert conflict.disagreements[0].kind == AssayDisagreementKind.DIRECT_STANCE_CONFLICT
    assert default_insufficient_reason(packet) == DecisionReasonCode.CONFLICTING_ASSAYS

    support = next(item for item in packet.evidence_items if item.stance == EvidenceStance.SUPPORTS)
    proposal = VerdictProposal(
        statement_id="S1",
        verdict=Verdict.SUPPORTED,
        citation_ids=[support.evidence_id],
        reason="One assay supports the statement.",
    )
    with pytest.raises(VerdictValidationError) as error:
        validate_verdict(packet, proposal)
    assert "COMPARABLE_ASSAY_CONFLICT_REQUIRES_ABSTENTION" in error.value.violations


def test_context_difference_is_reported_without_false_direct_conflict(
    store: EvidenceStore,
) -> None:
    add_activity(store, suffix="a", value=42, conditions={"cell_line": "K562"})
    add_activity(store, suffix="b", value=42, unit="uM", conditions={"cell_line": "HEK293"})
    packet = build_packet(store)
    assert not packet.conflict_assessment.decision_conflict
    disagreement = packet.conflict_assessment.disagreements[0]
    assert disagreement.kind == AssayDisagreementKind.CONTEXTUAL_STANCE_DIFFERENCE
    assert disagreement.differing_dimensions == ["cell_line"]


def test_large_assay_sets_rank_and_cap_reported_disagreements(
    store: EvidenceStore,
) -> None:
    for index in range(50):
        add_activity(
            store,
            suffix=f"large-{index:02d}",
            value=1 if index % 2 == 0 else 100,
            unit="nM" if index % 2 == 0 else "uM",
        )
    packet = build_packet(store)
    conflict = packet.conflict_assessment
    assert conflict.decision_conflict
    assert len(conflict.disagreements) == 100
    assert all(
        disagreement.kind == AssayDisagreementKind.DIRECT_STANCE_CONFLICT
        for disagreement in conflict.disagreements
    )
    assert conflict.summary is not None
    assert "Found 625 assay disagreement(s)" in conflict.summary
    assert "omits 525" in conflict.summary


def test_low_target_confidence_is_indirect_and_flagged(store: EvidenceStore) -> None:
    add_activity(store, suffix="low", value=42, target_confidence=4)
    item = build_packet(store).evidence_items[0]
    assert item.directness.value == "INDIRECT"
    assert "LOW_TARGET_CONFIDENCE" in item.quality_flags
