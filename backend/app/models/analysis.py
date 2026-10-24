from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


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


class IssueLocation(ApiModel):
    atom_indices: list[int] = Field(default_factory=list)
    bond_indices: list[int] = Field(default_factory=list)
    smiles_start: int | None = None
    smiles_end: int | None = None


class ValidationIssue(ApiModel):
    code: str
    subcode: str | None = None
    title: str
    severity: Severity
    summary: str
    explanation: str
    why_it_matters: str
    next_step: str
    location: IssueLocation = Field(default_factory=IssueLocation)
    technical_detail: str | None = None


class StandardizationStep(ApiModel):
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


class PropertyObservation(ApiModel):
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


class PropertyComparison(ApiModel):
    key: str
    label: str
    computed: PropertyObservation
    evidence: PropertyObservation
    comparison_status: ResultStatus


class SourceMentionMetadata(ApiModel):
    kind: Literal["pdf-text", "csv-row", "image", "manual"]
    page: int | None = Field(default=None, ge=1)
    row: int | None = Field(default=None, ge=2)
    locator: str | None = Field(default=None, max_length=200)
    excerpt: str | None = Field(default=None, max_length=600)


class SourceMetadata(ApiModel):
    filename: str | None = None
    source_type: Literal["direct-smiles", "photo", "paper", "csv"] | None = None
    citation: str | None = None
    page: int | None = None
    media_type: str | None = None
    file_size: int | None = Field(default=None, ge=0)
    file_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    extraction_method: str | None = None
    row: int | None = Field(default=None, ge=2)
    source_excerpt: str | None = Field(default=None, max_length=600)
    mention_count: int | None = Field(default=None, ge=1)
    mentions: list[SourceMentionMetadata] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_source_metadata(self) -> Self:
        if self.source_type == "direct-smiles":
            supplied_file_fields = (
                self.filename,
                self.page,
                self.media_type,
                self.file_size,
                self.file_sha256,
                self.extraction_method,
                self.row,
                self.source_excerpt,
                self.mention_count,
            )
            if any(value is not None for value in supplied_file_fields) or self.mentions:
                raise ValueError("direct SMILES input cannot include file metadata")
            return self
        if self.source_type in {"photo", "paper", "csv"}:
            required = {
                "filename": self.filename,
                "media_type": self.media_type,
                "file_size": self.file_size,
                "file_sha256": self.file_sha256,
                "extraction_method": self.extraction_method,
            }
            missing = [key for key, value in required.items() if value is None]
            if missing:
                raise ValueError(
                    f"{self.source_type} source metadata is incomplete: {', '.join(missing)}"
                )
            if self.source_type == "paper" and self.media_type != "application/pdf":
                raise ValueError("paper sources must use the application/pdf media type")
            if self.source_type == "photo" and self.media_type not in {
                "image/png",
                "image/jpeg",
                "image/webp",
            }:
                raise ValueError("photo sources must be PNG, JPEG, or WebP")
            if self.source_type == "csv" and self.media_type != "text/csv":
                raise ValueError("CSV sources must use the text/csv media type")
            if self.mention_count is not None and self.mention_count != len(self.mentions):
                raise ValueError("mention_count must match the number of source mentions")
        return self


class AnalyzeRequest(ApiModel):
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


class ToolVersions(ApiModel):
    pipeline: str
    python: str
    rdkit: str
    ruleset: str


class RunManifest(ApiModel):
    analysis_id: str
    input_sha256: str
    configuration_sha256: str
    output_sha256: str
    snapshot_id: str
    snapshot_scope: str
    tool_versions: ToolVersions


class ConformerAtom(ApiModel):
    element: str
    x: float
    y: float
    z: float
    formal_charge: int = 0


class ConformerBond(ApiModel):
    begin: int = Field(ge=0)
    end: int = Field(ge=0)
    order: float = Field(gt=0)


class Conformer3D(ApiModel):
    method: str
    structure_role: Literal["standardized-parent"] = "standardized-parent"
    coordinate_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    atoms: list[ConformerAtom]
    bonds: list[ConformerBond]


class ConformerRequest(ApiModel):
    structure: str = Field(min_length=1, max_length=20_000)


class AnalyzeResponse(ApiModel):
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


class BatchAnalyzeRequest(ApiModel):
    molecules: list[AnalyzeRequest] = Field(min_length=1, max_length=100)


class BatchAnalyzeResponse(ApiModel):
    results: list[AnalyzeResponse]


class RunResponse(ApiModel):
    run_id: str
    results: list[AnalyzeResponse]
    input_sha256: str
    configuration_sha256: str
    output_sha256: str


class ApiErrorItem(ApiModel):
    code: str
    message: str
    field: str | None = None
    technical_detail: str | None = None


class ApiErrorResponse(ApiModel):
    error: ApiErrorItem


class HealthResponse(ApiModel):
    status: Literal["ok"]
    service: str
    versions: dict[str, Any]


class TokenConfidence(ApiModel):
    token: str
    confidence: float = Field(ge=0, le=1)


class ExtractionEngineStatus(ApiModel):
    stage: Literal["not_ready", "downloading", "extracting", "loading", "ready", "error"]
    engine: Literal["MolNexTR"] = "MolNexTR"
    model_kind: Literal["general"] = "general"
    ready: bool
    message: str
    bytes_downloaded: int = Field(default=0, ge=0)
    bytes_total: int | None = Field(default=None, ge=0)
    progress_percent: float | None = Field(default=None, ge=0, le=100)
    model_version: str
    error_code: str | None = None
    technical_detail: str | None = None


class ImageExtractionResponse(ApiModel):
    status: Literal["candidate"] = "candidate"
    candidate_smiles: str
    method: Literal["MolNexTR-Graph-Recognizer"] = "MolNexTR-Graph-Recognizer"
    model_version: str
    device: str | None = None
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    filename: str
    media_type: Literal["image/png", "image/jpeg", "image/webp"]
    confidence_mean: float | None = Field(default=None, ge=0, le=1)
    confidence_min: float | None = Field(default=None, ge=0, le=1)
    token_confidences: list[TokenConfidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DocumentMention(ApiModel):
    page: int = Field(ge=1)
    excerpt: str = Field(max_length=600)
    label: str | None = Field(default=None, max_length=200)
    locator: str = Field(max_length=200)
    extraction_method: Literal["tagged-smiles", "structure-token"]


class DocumentMoleculeCandidate(ApiModel):
    candidate_id: str
    label: str = Field(max_length=200)
    smiles: str
    canonical_smiles: str | None = None
    confidence: Literal["high", "medium", "needs-review"]
    mentions: list[DocumentMention] = Field(min_length=1)
    mention_count: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_mention_count(self) -> Self:
        if self.mention_count != len(self.mentions):
            raise ValueError("mention_count must match the number of source mentions")
        return self


class DocumentExtractionResponse(ApiModel):
    status: Literal["candidates"] = "candidates"
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    filename: str
    media_type: Literal["application/pdf"] = "application/pdf"
    method: Literal["PDF-text-SMILES-extractor"] = "PDF-text-SMILES-extractor"
    total_mentions: int = Field(ge=0)
    candidates: list[DocumentMoleculeCandidate]
    warnings: list[str] = Field(default_factory=list)
