from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

RESEARCH_AID_NOTICE = (
    "Research aid only. This report summarizes available evidence and is not a "
    "prediction of clinical efficacy or safety."
)


class EvidenceContractModel(BaseModel):
    """Strict base model for the Phase 2 evidence contract."""

    model_config = ConfigDict(extra="forbid")


class ClaimType(StrEnum):
    BIOLOGICAL_ACTIVITY = "BIOLOGICAL_ACTIVITY"
    MECHANISM = "MECHANISM"
    COMPUTED_PROPERTY = "COMPUTED_PROPERTY"
    LITERATURE_FACT = "LITERATURE_FACT"
    CLINICAL_OR_SAFETY = "CLINICAL_OR_SAFETY"
    OTHER = "OTHER"


class Verdict(StrEnum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class ConfidenceLevel(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ResolutionStatus(StrEnum):
    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"
    NOT_REQUIRED = "NOT_REQUIRED"


class EvidenceSourceType(StrEnum):
    CHEMBL_ACTIVITY = "CHEMBL_ACTIVITY"
    PUBCHEM_BIOASSAY = "PUBCHEM_BIOASSAY"
    PAPER_PASSAGE = "PAPER_PASSAGE"
    RUN_RECORD = "RUN_RECORD"


class EvidenceBasis(StrEnum):
    EXPERIMENTAL = "EXPERIMENTAL"
    COMPUTED = "COMPUTED"
    LITERATURE_CONTEXT = "LITERATURE_CONTEXT"


class EvidenceStance(StrEnum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    NEUTRAL = "NEUTRAL"


class EvidenceDirectness(StrEnum):
    DIRECT = "DIRECT"
    INDIRECT = "INDIRECT"
    CONTEXT_ONLY = "CONTEXT_ONLY"


class RetractionStatus(StrEnum):
    CLEAR = "CLEAR"
    RETRACTED = "RETRACTED"
    EXPRESSION_OF_CONCERN = "EXPRESSION_OF_CONCERN"
    CORRECTED = "CORRECTED"
    REINSTATED = "REINSTATED"
    UNKNOWN = "UNKNOWN"


class DecisionReasonCode(StrEnum):
    NO_DIRECT_EVIDENCE = "NO_DIRECT_EVIDENCE"
    INDIRECT_EVIDENCE_ONLY = "INDIRECT_EVIDENCE_ONLY"
    COMPUTED_EVIDENCE_ONLY = "COMPUTED_EVIDENCE_ONLY"
    RETRACTED_EVIDENCE_EXCLUDED = "RETRACTED_EVIDENCE_EXCLUDED"
    AMBIGUOUS_ENTITY = "AMBIGUOUS_ENTITY"
    UNRESOLVED_ENTITY = "UNRESOLVED_ENTITY"
    CONFLICTING_ASSAYS = "CONFLICTING_ASSAYS"
    OUTSIDE_SNAPSHOT_COVERAGE = "OUTSIDE_SNAPSHOT_COVERAGE"
    CLINICAL_PREDICTION_OUT_OF_SCOPE = "CLINICAL_PREDICTION_OUT_OF_SCOPE"
    SAFETY_PREDICTION_OUT_OF_SCOPE = "SAFETY_PREDICTION_OUT_OF_SCOPE"
    PERSONALIZED_ADVICE_OUT_OF_SCOPE = "PERSONALIZED_ADVICE_OUT_OF_SCOPE"
    FUTURE_EFFICACY_OUT_OF_SCOPE = "FUTURE_EFFICACY_OUT_OF_SCOPE"


OUT_OF_SCOPE_REASON_CODES = frozenset(
    {
        DecisionReasonCode.CLINICAL_PREDICTION_OUT_OF_SCOPE,
        DecisionReasonCode.SAFETY_PREDICTION_OUT_OF_SCOPE,
        DecisionReasonCode.PERSONALIZED_ADVICE_OUT_OF_SCOPE,
        DecisionReasonCode.FUTURE_EFFICACY_OUT_OF_SCOPE,
    }
)


class ClaimCheckRequest(EvidenceContractModel):
    claim: str = Field(min_length=1, max_length=20_000)
    run_record_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("claim")
    @classmethod
    def reject_whitespace_only_claim(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("claim must contain non-whitespace text")
        return value


class AtomicStatement(EvidenceContractModel):
    statement_id: str = Field(pattern=r"^S[1-9][0-9]*$")
    text: str = Field(min_length=1, max_length=5_000)
    claim_type: ClaimType
    molecule_mentions: list[str] = Field(default_factory=list)
    target_mentions: list[str] = Field(default_factory=list)
    endpoint_mentions: list[str] = Field(default_factory=list)


class ClaimDecomposition(EvidenceContractModel):
    statements: list[AtomicStatement] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def require_ordered_statement_ids(self) -> Self:
        expected = [f"S{index}" for index in range(1, len(self.statements) + 1)]
        actual = [statement.statement_id for statement in self.statements]
        if actual != expected:
            raise ValueError("statement IDs must be unique and ordered S1, S2, ...")
        return self


class ResolutionSummary(EvidenceContractModel):
    status: ResolutionStatus
    molecule_inchikey: str | None = None
    target_id: str | None = None
    organism: str | None = None
    endpoint: str | None = None
    reason_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_resolution_reason(self) -> Self:
        if self.status in {ResolutionStatus.AMBIGUOUS, ResolutionStatus.UNRESOLVED}:
            if not self.reason_codes:
                raise ValueError("ambiguous or unresolved entities require a reason code")
        return self


class EvidenceItem(EvidenceContractModel):
    evidence_id: str = Field(min_length=1, max_length=300)
    source_type: EvidenceSourceType
    source_record_id: str = Field(min_length=1, max_length=300)
    basis: EvidenceBasis
    stance: EvidenceStance
    directness: EvidenceDirectness
    molecule_inchikey: str | None = None
    target_id: str | None = None
    organism: str | None = None
    endpoint: str | None = None
    relation: Literal["=", "<", ">", "<=", ">="] | None = None
    value: float | None = None
    unit: str | None = None
    assay_conditions: dict[str, Any] = Field(default_factory=dict)
    paper_id: str | None = None
    passage_locator: str | None = None
    passage_text: str | None = None
    retraction_status: RetractionStatus = RetractionStatus.UNKNOWN
    snapshot_id: str = Field(min_length=1, max_length=200)
    raw_record_sha256: str = Field(pattern=r"^(sha256:)?[a-f0-9]{64}$")
    quality_flags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_source_contract(self) -> Self:
        if self.source_type == EvidenceSourceType.RUN_RECORD:
            if self.basis != EvidenceBasis.COMPUTED:
                raise ValueError("run-record evidence must be labelled COMPUTED")
        elif self.source_type in {
            EvidenceSourceType.CHEMBL_ACTIVITY,
            EvidenceSourceType.PUBCHEM_BIOASSAY,
        }:
            if self.basis != EvidenceBasis.EXPERIMENTAL:
                raise ValueError("assay evidence must be labelled EXPERIMENTAL")
        elif not self.paper_id or not self.passage_locator or not self.passage_text:
            raise ValueError(
                "paper-passage evidence requires paper_id, passage_locator, and passage_text"
            )
        return self


class EvidencePacket(EvidenceContractModel):
    statement: AtomicStatement
    resolution: ResolutionSummary
    evidence_items: list[EvidenceItem] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def require_unique_evidence_ids(self) -> Self:
        evidence_ids = [item.evidence_id for item in self.evidence_items]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence packet contains duplicate evidence IDs")
        return self


class VerdictProposal(EvidenceContractModel):
    statement_id: str = Field(pattern=r"^S[1-9][0-9]*$")
    verdict: Verdict
    citation_ids: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1, max_length=5_000)
    reason_codes: list[DecisionReasonCode] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    conflict_summary: str | None = Field(default=None, max_length=5_000)

    @field_validator("citation_ids")
    @classmethod
    def reject_duplicate_citations(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("citation IDs must be unique")
        return value


class ConfidenceAssessment(EvidenceContractModel):
    level: ConfidenceLevel
    method: Literal["deterministic-calibration-v1"] = "deterministic-calibration-v1"
    factor_scores: dict[str, float]
    benchmark_accuracy: float | None = Field(default=None, ge=0, le=1)
    benchmark_case_count: int | None = Field(default=None, ge=1)

    @field_validator("factor_scores")
    @classmethod
    def validate_factor_scores(cls, value: dict[str, float]) -> dict[str, float]:
        invalid = [name for name, score in value.items() if not 0 <= score <= 1]
        if invalid:
            raise ValueError(f"confidence factors must be between 0 and 1: {invalid}")
        return value

    @model_validator(mode="after")
    def require_complete_benchmark_pair(self) -> Self:
        supplied = (self.benchmark_accuracy is not None, self.benchmark_case_count is not None)
        if supplied[0] != supplied[1]:
            raise ValueError("benchmark accuracy and case count must be supplied together")
        return self


class StatementVerdict(EvidenceContractModel):
    statement: AtomicStatement
    resolution: ResolutionSummary
    verdict: Verdict
    citations: list[EvidenceItem]
    reason: str
    reason_codes: list[DecisionReasonCode] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    conflict_summary: str | None = None
    confidence: ConfidenceAssessment


class EvidenceAssistantManifest(EvidenceContractModel):
    model_name: str
    model_digest: str
    evidence_snapshot_id: str
    input_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    configuration_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    output_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ClaimCheckResponse(EvidenceContractModel):
    assistant_run_id: str
    verdicts: list[StatementVerdict]
    research_aid_notice: Literal[
        "Research aid only. This report summarizes available evidence and is not a "
        "prediction of clinical efficacy or safety."
    ] = RESEARCH_AID_NOTICE
    manifest: EvidenceAssistantManifest
