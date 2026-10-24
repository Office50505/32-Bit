from pathlib import Path
from types import SimpleNamespace

from app.evidence import EvidenceStore, SnapshotSpec
from app.models.evidence_assistant import (
    RESEARCH_AID_NOTICE,
    AtomicStatement,
    ClaimCheckRequest,
    ClaimDecomposition,
    ClaimType,
    ConfidenceLevel,
    DecisionReasonCode,
    Verdict,
    VerdictProposal,
)
from app.services.evidence_assistant import EvidenceAssistant
from app.services.ollama import (
    OllamaCallMetadata,
    OllamaModelIdentity,
    StructuredModelResult,
)

HASH = "a" * 64
SNAPSHOT_ID = "chembl36-pilot-v1"
IMATINIB = "KTUFNOKKBVMGRW-UHFFFAOYSA-N"
METADATA = OllamaCallMetadata(
    model="qwen3:4b-instruct",
    total_duration_ns=10,
    load_duration_ns=1,
    prompt_tokens=20,
    completion_tokens=10,
)


class FakeModel:
    def __init__(
        self,
        decomposition: ClaimDecomposition,
        *,
        invalid_citation: bool = False,
    ) -> None:
        self.decomposition = decomposition
        self.invalid_citation = invalid_citation
        self.config = SimpleNamespace(structured_output_mode="json")
        self.verdict_packets = []

    def verify_model(self) -> OllamaModelIdentity:
        return OllamaModelIdentity(
            name="qwen3:4b-instruct",
            digest="b" * 64,
            parameter_count=4_022_468_096,
            parameter_size="4.0B",
            quantization_level="Q4_K_M",
            family="qwen3",
        )

    def decompose_claim(
        self,
        _request: ClaimCheckRequest,
    ) -> StructuredModelResult[ClaimDecomposition]:
        return StructuredModelResult(value=self.decomposition, metadata=METADATA)

    def propose_verdict(self, packet):
        self.verdict_packets.append(packet)
        citation_id = (
            "MADE-UP-CITATION"
            if self.invalid_citation
            else next(
                item.evidence_id
                for item in packet.evidence_items
                if item.stance.value == "SUPPORTS"
            )
        )
        proposal = VerdictProposal(
            statement_id=packet.statement.statement_id,
            verdict=Verdict.SUPPORTED,
            citation_ids=[citation_id],
            reason="The direct experimental record supports this statement.",
        )
        return StructuredModelResult(value=proposal, metadata=METADATA)


def activity_statement(
    *,
    statement_id: str = "S1",
    claim_type: ClaimType = ClaimType.COMPUTED_PROPERTY,
) -> AtomicStatement:
    return AtomicStatement(
        statement_id=statement_id,
        text="Imatinib inhibits ABL1 with nanomolar potency.",
        claim_type=claim_type,
        molecule_mentions=["Imatinib"],
        target_mentions=["ABL1"],
        endpoint_mentions=["IC50"],
    )


def make_store(tmp_path: Path, values: list[tuple[float, str]]) -> EvidenceStore:
    store = EvidenceStore.create(tmp_path / "evidence.sqlite")
    store.register_snapshot(
        SnapshotSpec(
            snapshot_id=SNAPSHOT_ID,
            source_name="ChEMBL",
            source_version="36",
            source_sha256=HASH,
            scope={},
            created_at="2026-10-24T00:00:00Z",
        )
    )
    store.add_molecule(
        snapshot_id=SNAPSHOT_ID,
        inchikey=IMATINIB,
        canonical_smiles="CC",
        preferred_name="Imatinib",
        raw_record_sha256=HASH,
    )
    store.add_molecule_alias(
        snapshot_id=SNAPSHOT_ID,
        inchikey=IMATINIB,
        alias="Imatinib",
        source="ChEMBL",
    )
    store.add_target(
        snapshot_id=SNAPSHOT_ID,
        target_id="CHEMBL1862",
        preferred_name="ABL1",
        organism="Homo sapiens",
        raw_record_sha256=HASH,
    )
    store.add_target_alias(
        snapshot_id=SNAPSHOT_ID,
        target_id="CHEMBL1862",
        alias="ABL1",
        source="ChEMBL",
    )
    store.add_paper(
        snapshot_id=SNAPSHOT_ID,
        paper_id="DOC-1",
        title="ABL1 assays",
        retraction_status="CLEAR",
        raw_record_sha256=HASH,
    )
    for index, (value, unit) in enumerate(values, start=1):
        store.add_assay(
            snapshot_id=SNAPSHOT_ID,
            assay_id=f"ASSAY-{index}",
            source="CHEMBL",
            target_id="CHEMBL1862",
            organism="Homo sapiens",
            assay_type="B",
            description="Direct binding",
            target_confidence_score=9,
            paper_id="DOC-1",
            raw_record_sha256=HASH,
        )
        store.add_activity(
            snapshot_id=SNAPSHOT_ID,
            activity_id=f"ACT-{index}",
            assay_id=f"ASSAY-{index}",
            molecule_inchikey=IMATINIB,
            measurement_type="IC50",
            standard_value=value,
            standard_unit=unit,
            standard_relation="=",
            raw_record_sha256=HASH,
        )
    store.seal_snapshot(SNAPSHOT_ID)
    return store


def test_orchestrator_returns_cited_validated_reproducible_response(tmp_path: Path) -> None:
    store = make_store(tmp_path, [(42, "nM")])
    model = FakeModel(ClaimDecomposition(statements=[activity_statement()]))
    assistant = EvidenceAssistant(
        store=store,
        snapshot_ids=(SNAPSHOT_ID,),
        model=model,  # type: ignore[arg-type]
    )
    request = ClaimCheckRequest(claim="Imatinib inhibits ABL1 with nanomolar potency.")
    first = assistant.check_claim(request)
    second = assistant.check_claim(request)

    assert first == second
    assert first.research_aid_notice == RESEARCH_AID_NOTICE
    assert len(first.verdicts) == 1
    verdict = first.verdicts[0]
    assert verdict.statement.claim_type == ClaimType.BIOLOGICAL_ACTIVITY
    assert verdict.verdict == Verdict.SUPPORTED
    assert verdict.citations[0].source_record_id == "ACT-1"
    assert verdict.confidence.level == ConfidenceLevel.MEDIUM
    assert first.manifest.model_digest == "b" * 64
    assert first.manifest.evidence_snapshot_id.startswith(f"{SNAPSHOT_ID}@")
    assert len(first.manifest.input_sha256) == 64
    assert first.assistant_run_id.startswith("EA-")


def test_comparable_assay_conflict_abstains_without_model_selection(tmp_path: Path) -> None:
    store = make_store(tmp_path, [(42, "nM"), (42, "uM")])
    model = FakeModel(ClaimDecomposition(statements=[activity_statement()]))
    assistant = EvidenceAssistant(
        store=store,
        snapshot_ids=(SNAPSHOT_ID,),
        model=model,  # type: ignore[arg-type]
    )
    result = assistant.check_claim(ClaimCheckRequest(claim="claim"))
    verdict = result.verdicts[0]
    assert verdict.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert verdict.reason_codes == [DecisionReasonCode.CONFLICTING_ASSAYS]
    assert verdict.conflict_summary == "Found 1 assay disagreement(s); 1 are directly comparable."
    assert model.verdict_packets == []


def test_invalid_model_citation_fails_closed_to_low_confidence_abstention(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path, [(42, "nM")])
    model = FakeModel(
        ClaimDecomposition(statements=[activity_statement()]),
        invalid_citation=True,
    )
    assistant = EvidenceAssistant(
        store=store,
        snapshot_ids=(SNAPSHOT_ID,),
        model=model,  # type: ignore[arg-type]
    )
    verdict = assistant.check_claim(ClaimCheckRequest(claim="claim")).verdicts[0]
    assert verdict.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert verdict.reason_codes == [DecisionReasonCode.MODEL_OUTPUT_REJECTED]
    assert verdict.citations == []
    assert verdict.confidence.level == ConfidenceLevel.LOW
    assert verdict.confidence.factor_scores["synthesis_validity"] == 0.0


def test_clinical_claim_is_out_of_scope_without_scientific_citation(tmp_path: Path) -> None:
    store = make_store(tmp_path, [])
    statement = AtomicStatement(
        statement_id="S1",
        text="Imatinib will safely cure every patient.",
        claim_type=ClaimType.BIOLOGICAL_ACTIVITY,
        molecule_mentions=["Imatinib"],
    )
    model = FakeModel(ClaimDecomposition(statements=[statement]))
    assistant = EvidenceAssistant(
        store=store,
        snapshot_ids=(SNAPSHOT_ID,),
        model=model,  # type: ignore[arg-type]
    )
    verdict = assistant.check_claim(ClaimCheckRequest(claim=statement.text)).verdicts[0]
    assert verdict.verdict == Verdict.OUT_OF_SCOPE
    assert verdict.reason_codes == [DecisionReasonCode.SAFETY_PREDICTION_OUT_OF_SCOPE]
    assert verdict.citations == []
    assert model.verdict_packets == []


def test_duplicate_model_statements_are_removed_before_retrieval(tmp_path: Path) -> None:
    store = make_store(tmp_path, [(42, "nM")])
    model = FakeModel(
        ClaimDecomposition(
            statements=[
                activity_statement(),
                AtomicStatement(
                    statement_id="S2",
                    text="Imatinib inhibits ABL1.",
                    claim_type=ClaimType.BIOLOGICAL_ACTIVITY,
                    molecule_mentions=["Imatinib"],
                    target_mentions=["ABL1"],
                    endpoint_mentions=["IC50"],
                ),
            ]
        )
    )
    assistant = EvidenceAssistant(
        store=store,
        snapshot_ids=(SNAPSHOT_ID,),
        model=model,  # type: ignore[arg-type]
    )
    result = assistant.check_claim(ClaimCheckRequest(claim="duplicate claim"))
    assert len(result.verdicts) == 1
