from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class MoleculeStatus(StrEnum):
    VALID = "valid"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"


class ResultStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    INVALID_INPUT = "INVALID_INPUT"
    AMBIGUOUS_INPUT = "AMBIGUOUS_INPUT"
    NOT_COMPUTABLE = "NOT_COMPUTABLE"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NO_REFERENCE_MATCH = "NO_REFERENCE_MATCH"
    OUTSIDE_SNAPSHOT_COVERAGE = "OUTSIDE_SNAPSHOT_COVERAGE"
    COMPUTATION_ERROR = "COMPUTATION_ERROR"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"


class IssueLocation(BaseModel):
    atom_indices: list[int] = Field(default_factory=list)
    bond_indices: list[int] = Field(default_factory=list)
    smiles_start: int | None = None
    smiles_end: int | None = None


class ValidationIssue(BaseModel):
    code: str
    title: str
    severity: Severity
    summary: str
    explanation: str
    why_it_matters: str
    next_step: str
    location: IssueLocation = Field(default_factory=IssueLocation)
    technical_detail: str | None = None


class StandardizationStep(BaseModel):
    code: str
    label: str
    before_smiles: str
    after_smiles: str
    changed: bool
    status: Literal["applied", "failed"] = "applied"
    reason_code: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def validate_failure_reason(self) -> Self:
        if self.status == "failed" and (not self.reason_code or not self.reason):
            raise ValueError("failed standardization steps require a reason code and explanation")
        return self


class PropertyObservation(BaseModel):
    value: str | float | int | None
    unit: str | None = None
    status: ResultStatus
    reason_code: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def validate_value_semantics(self) -> Self:
        if self.value is None and self.status == ResultStatus.AVAILABLE:
            raise ValueError("AVAILABLE observations require a value")
        if self.value is None and (not self.reason_code or not self.reason):
            raise ValueError("missing observations require a reason code and explanation")
        return self


class PropertyComparison(BaseModel):
    key: str
    label: str
    computed: PropertyObservation
    evidence: PropertyObservation
    comparison_status: ResultStatus


class SourceMetadata(BaseModel):
    filename: str | None = None
    source_type: str | None = None
    citation: str | None = None
    page: int | None = None
    media_type: str | None = None
    file_size: int | None = Field(default=None, ge=0)
    file_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    extraction_method: str | None = None


class AnalyzeRequest(BaseModel):
    structure: str = Field(min_length=1, max_length=20_000)
    input_type: Literal["smiles"] = "smiles"
    label: str | None = Field(default=None, max_length=200)
    source: SourceMetadata | None = None

    @field_validator("structure")
    @classmethod
    def reject_whitespace_only_structure(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("structure must contain non-whitespace SMILES text")
        return value


class ToolVersions(BaseModel):
    pipeline: str
    python: str
    rdkit: str
    ruleset: str


class RunManifest(BaseModel):
    analysis_id: str
    input_sha256: str
    configuration_sha256: str
    output_sha256: str
    snapshot_id: str
    snapshot_scope: str
    tool_versions: ToolVersions


class AnalyzeResponse(BaseModel):
    analysis_id: str
    label: str
    raw_input: str
    input_type: Literal["smiles"]
    status: MoleculeStatus
    canonical_smiles: str | None = None
    standardized_smiles: str | None = None
    depiction_svg: str | None = None
    issues: list[ValidationIssue]
    standardization_steps: list[StandardizationStep]
    properties: list[PropertyComparison]
    source: SourceMetadata | None = None
    manifest: RunManifest


class BatchAnalyzeRequest(BaseModel):
    molecules: list[AnalyzeRequest] = Field(min_length=1, max_length=100)


class BatchAnalyzeResponse(BaseModel):
    results: list[AnalyzeResponse]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    versions: dict[str, Any]
