from pathlib import Path

import pytest

from app.evidence import EvidenceStore, SnapshotSpec
from app.models.evidence_assistant import (
    AtomicStatement,
    ClaimType,
    DecisionReasonCode,
    EvidenceDirectness,
    EvidenceStance,
    RetractionStatus,
    Verdict,
    VerdictProposal,
)
from app.services.claim_routing import EntityResolver
from app.services.evidence_retrieval import (
    EvidencePacketBuilder,
    build_fts_query,
    infer_property_claim,
)
from app.services.verdict_engine import materialize_statement_verdict
from app.services.verdict_validation import default_insufficient_reason

HASH = "a" * 64
SNAPSHOT_ID = "pilot-v1"
IMATINIB = "KTUFNOKKBVMGRW-UHFFFAOYSA-N"


@pytest.fixture
def store(tmp_path: Path) -> EvidenceStore:
    evidence_store = EvidenceStore.create(tmp_path / "evidence.sqlite")
    evidence_store.register_snapshot(
        SnapshotSpec(
            snapshot_id=SNAPSHOT_ID,
            source_name="mixed pilot",
            source_version="1",
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
        source="pilot",
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
        source="pilot",
    )
    yield evidence_store
    evidence_store.close()


def make_statement(
    text: str,
    claim_type: ClaimType,
    *,
    targets: list[str] | None = None,
) -> AtomicStatement:
    return AtomicStatement(
        statement_id="S1",
        text=text,
        claim_type=claim_type,
        molecule_mentions=["Imatinib"],
        target_mentions=targets or [],
    )


def test_run_record_packet_can_support_matching_computed_property(
    store: EvidenceStore,
) -> None:
    store.add_run_record(
        snapshot_id=SNAPSHOT_ID,
        record_id="RUN-1:MW",
        analysis_id="RUN-1",
        molecule_inchikey=IMATINIB,
        property_key="molecular_weight",
        value=493.6,
        unit="g/mol",
        manifest={"tool": "RDKit", "version": "2025.03"},
        raw_record_sha256=HASH,
    )
    statement = make_statement(
        "The calculated molecular weight of Imatinib is 493.6 g/mol.",
        ClaimType.OTHER,
    )
    resolved = EntityResolver(store, (SNAPSHOT_ID,)).resolve_and_route(statement)
    packet = EvidencePacketBuilder(store, (SNAPSHOT_ID,)).build(
        resolved,
        run_record_ids=("RUN-1:MW",),
    )
    assert len(packet.evidence_items) == 1
    evidence = packet.evidence_items[0]
    assert evidence.stance == EvidenceStance.SUPPORTS
    assert evidence.endpoint == "molecular_weight"
    assert evidence.value == 493.6
    assert evidence.assay_conditions["manifest"]["tool"] == "RDKit"

    result = materialize_statement_verdict(
        packet,
        VerdictProposal(
            statement_id="S1",
            verdict=Verdict.SUPPORTED,
            citation_ids=[evidence.evidence_id],
            reason="The cited run record matches the stated computed property.",
        ),
    )
    assert result.verdict == Verdict.SUPPORTED


def test_run_record_filter_does_not_substitute_an_unrequested_run(
    store: EvidenceStore,
) -> None:
    store.add_run_record(
        snapshot_id=SNAPSHOT_ID,
        record_id="RUN-OTHER:LOGP",
        analysis_id="RUN-OTHER",
        molecule_inchikey=IMATINIB,
        property_key="logp",
        value=4.5,
        unit="unitless",
        manifest={},
        raw_record_sha256=HASH,
    )
    statement = make_statement("The computed LogP of Imatinib is 4.5.", ClaimType.OTHER)
    resolved = EntityResolver(store, (SNAPSHOT_ID,)).resolve_and_route(statement)
    packet = EvidencePacketBuilder(store, (SNAPSHOT_ID,)).build(
        resolved,
        run_record_ids=("RUN-REQUESTED:LOGP",),
    )
    assert packet.evidence_items == []
    assert default_insufficient_reason(packet) == DecisionReasonCode.NO_DIRECT_EVIDENCE


def test_formula_claim_parsing_is_typed() -> None:
    claim = infer_property_claim(
        make_statement("The molecular formula of Imatinib is C29H31N7O.", ClaimType.OTHER)
    )
    assert claim.property_key == "molecular_formula"
    assert claim.asserted_value == "C29H31N7O"


def test_literature_retrieval_is_traceable_but_not_automatic_entailment(
    store: EvidenceStore,
) -> None:
    store.add_paper(
        snapshot_id=SNAPSHOT_ID,
        paper_id="PMCID:PMC1",
        title="Imatinib and ABL1 phosphorylation",
        retraction_status="CLEAR",
        raw_record_sha256=HASH,
    )
    store.add_passage(
        snapshot_id=SNAPSHOT_ID,
        passage_id="PMC1:RESULTS:P2",
        paper_id="PMCID:PMC1",
        section_name="Results",
        paragraph_number=2,
        sentence_start=10,
        sentence_end=82,
        passage_text="Imatinib reduced ABL1-dependent phosphorylation in the cellular assay.",
        passage_sha256=HASH,
        priority=1,
    )
    statement = make_statement(
        "Imatinib changes the ABL1 phosphorylation pathway.",
        ClaimType.MECHANISM,
        targets=["ABL1"],
    )
    resolved = EntityResolver(store, (SNAPSHOT_ID,)).resolve_and_route(statement)
    packet = EvidencePacketBuilder(store, (SNAPSHOT_ID,)).build(resolved)
    assert len(packet.evidence_items) == 1
    passage = packet.evidence_items[0]
    assert passage.paper_id == "PMCID:PMC1"
    assert passage.passage_locator == "Results, paragraph 2, characters 10-82"
    assert passage.passage_text.startswith("Imatinib reduced")
    assert passage.directness == EvidenceDirectness.CONTEXT_ONLY
    assert passage.stance == EvidenceStance.NEUTRAL
    assert "PASSAGE_ENTAILMENT_NOT_YET_VERIFIED" in passage.quality_flags
    assert default_insufficient_reason(packet) == DecisionReasonCode.INDIRECT_EVIDENCE_ONLY


def test_retracted_passage_is_returned_only_as_excluded_context(
    store: EvidenceStore,
) -> None:
    store.add_paper(
        snapshot_id=SNAPSHOT_ID,
        paper_id="PMCID:RETRACTED",
        title="Retracted Imatinib ABL1 report",
        retraction_status="RETRACTED",
        raw_record_sha256=HASH,
    )
    store.add_passage(
        snapshot_id=SNAPSHOT_ID,
        passage_id="RETRACTED:P1",
        paper_id="PMCID:RETRACTED",
        section_name="Results",
        passage_text="Imatinib altered the ABL1 pathway.",
        passage_sha256=HASH,
    )
    statement = make_statement(
        "Imatinib changes the ABL1 pathway.",
        ClaimType.MECHANISM,
        targets=["ABL1"],
    )
    resolved = EntityResolver(store, (SNAPSHOT_ID,)).resolve_and_route(statement)
    packet = EvidencePacketBuilder(store, (SNAPSHOT_ID,)).build(resolved)
    assert packet.evidence_items[0].retraction_status == RetractionStatus.RETRACTED
    assert "RETRACTED_PAPER_EXCLUDED" in packet.evidence_items[0].quality_flags
    assert default_insufficient_reason(packet) == DecisionReasonCode.RETRACTED_EVIDENCE_EXCLUDED


def test_fts_query_escapes_user_punctuation_as_quoted_tokens() -> None:
    query = build_fts_query(
        make_statement(
            'Does Imatinib target ABL1 OR "anything"?',
            ClaimType.LITERATURE_FACT,
            targets=["ABL1"],
        )
    )
    assert query.startswith('"imatinib" OR "abl1"')
    assert '"anything"' in query
