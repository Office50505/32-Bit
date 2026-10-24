export type Severity = "error" | "warning" | "info";
export type MoleculeStatus = "valid" | "ambiguous" | "invalid";

export type MoleculeRelationship =
  | "EXACT_SAME_STRUCTURE"
  | "SAME_STANDARDIZED_PARENT"
  | "STEREOISOMERS"
  | "DIFFERENT_STRUCTURE"
  | "INDETERMINATE";

export type ResultStatus =
  | "AVAILABLE"
  | "INVALID_INPUT"
  | "AMBIGUOUS_INPUT"
  | "NOT_COMPUTABLE"
  | "NOT_AVAILABLE"
  | "NOT_APPLICABLE"
  | "NO_REFERENCE_MATCH"
  | "OUTSIDE_SNAPSHOT_COVERAGE"
  | "COMPUTATION_ERROR"
  | "CONFLICTING_EVIDENCE";

export interface SourceMentionMetadata {
  kind: "pdf-text" | "csv-row" | "image" | "manual";
  page?: number;
  row?: number;
  locator?: string;
  excerpt?: string;
}

export interface SourceMetadata {
  filename?: string;
  source_type?: string;
  citation?: string;
  page?: number;
  media_type?: string;
  file_size?: number;
  file_sha256?: string;
  extraction_method?: string;
  row?: number;
  source_excerpt?: string;
  mention_count?: number;
  mentions?: SourceMentionMetadata[];
}

export interface AnalyzeRequest {
  structure: string;
  input_type?: "smiles";
  label?: string;
  source?: SourceMetadata;
}

export interface IssueLocation {
  atom_indices: number[];
  bond_indices: number[];
  smiles_start?: number | null;
  smiles_end?: number | null;
}

export interface ValidationIssue {
  code: string;
  subcode?: string | null;
  title: string;
  severity: Severity;
  summary: string;
  explanation: string;
  why_it_matters: string;
  next_step: string;
  location: IssueLocation;
  technical_detail?: string | null;
}

export interface StandardizationStep {
  code: string;
  label: string;
  before_smiles: string;
  after_smiles: string;
  changed: boolean;
  status: "applied" | "failed";
  reason_code?: string | null;
  reason?: string | null;
}

export interface PropertyObservation {
  value: string | number | null;
  unit?: string | null;
  status: ResultStatus;
  reason_code?: string | null;
  reason?: string | null;
}

export interface PropertyComparison {
  key: string;
  label: string;
  computed: PropertyObservation;
  evidence: PropertyObservation;
  comparison_status: ResultStatus;
}

export interface BioactivityEvidence {
  source: "ChEMBL";
  status: ResultStatus;
  molecule_chembl_id?: string | null;
  preferred_name?: string | null;
  release?: string | null;
  activity_count?: number | null;
  snapshot_id: string;
  snapshot_scope: string;
  retrieved_at?: string | null;
  source_url?: string | null;
  response_sha256?: string | null;
  reason_code: string;
  reason: string;
}

export interface RunManifest {
  analysis_id: string;
  input_sha256: string;
  configuration_sha256: string;
  output_sha256: string;
  snapshot_id: string;
  snapshot_scope: string;
  tool_versions: {
    pipeline: string;
    python: string;
    rdkit: string;
    ruleset: string;
  };
}

export interface AnalyzeResponse {
  analysis_id: string;
  label: string;
  raw_input: string;
  input_type: "smiles";
  status: MoleculeStatus;
  canonical_smiles?: string | null;
  standardized_smiles?: string | null;
  depiction_svg?: string | null;
  issues: ValidationIssue[];
  standardization_steps: StandardizationStep[];
  properties: PropertyComparison[];
  bioactivity_evidence: BioactivityEvidence;
  source?: SourceMetadata | null;
  manifest: RunManifest;
}

export interface MoleculeIdentityComparison {
  left_index: number;
  right_index: number;
  relationship: MoleculeRelationship;
  reason_code: string;
  reason: string;
  left_standardized_smiles?: string | null;
  right_standardized_smiles?: string | null;
}

export interface BatchAnalyzeResponse {
  results: AnalyzeResponse[];
  identity_comparisons: MoleculeIdentityComparison[];
}

export interface ReplayEnvironment {
  python: string;
  rdkit: string;
  platform: string;
  machine: string;
  dependency_lock_sha256: string;
  environment_sha256: string;
}

export interface RunResponse extends BatchAnalyzeResponse {
  run_id: string;
  input_sha256: string;
  configuration_sha256: string;
  output_sha256: string;
  environment?: ReplayEnvironment | null;
}

export interface ReplayVerification {
  run_id: string;
  status: "MATCH" | "ENVIRONMENT_MISMATCH" | "OUTPUT_MISMATCH" | "LEGACY_RUN_NO_ENVIRONMENT";
  reproducible: boolean;
  expected_output_sha256: string;
  actual_output_sha256: string;
  expected_environment_sha256?: string | null;
  actual_environment_sha256: string;
  differences: string[];
}

export interface ApiErrorResponse {
  error: {
    code: string;
    message: string;
    field?: string | null;
    technical_detail?: string | null;
  };
}

export interface TokenConfidence {
  token: string;
  confidence: number;
}

export interface ExtractionEngineStatus {
  stage: "not_ready" | "downloading" | "extracting" | "loading" | "ready" | "error";
  engine: "MolNexTR";
  model_kind: "general";
  ready: boolean;
  message: string;
  bytes_downloaded: number;
  bytes_total?: number | null;
  progress_percent?: number | null;
  model_version: string;
  error_code?: string | null;
  technical_detail?: string | null;
}

export interface ImageExtractionResponse {
  status: "candidate";
  candidate_smiles: string;
  method: "MolNexTR-Graph-Recognizer";
  model_version: string;
  device?: string | null;
  source_sha256: string;
  filename: string;
  media_type: "image/png" | "image/jpeg" | "image/webp";
  confidence_mean?: number | null;
  confidence_min?: number | null;
  token_confidences: TokenConfidence[];
  warnings: string[];
}

export interface DocumentMention {
  page: number;
  excerpt: string;
  label?: string | null;
  locator: string;
  extraction_method: "tagged-smiles" | "structure-token";
}

export interface DocumentMoleculeCandidate {
  candidate_id: string;
  label: string;
  smiles: string;
  canonical_smiles?: string | null;
  confidence: "high" | "medium" | "needs-review";
  mentions: DocumentMention[];
  mention_count: number;
}

export interface DocumentExtractionResponse {
  status: "candidates";
  source_sha256: string;
  filename: string;
  media_type: "application/pdf";
  method: "PDF-text-SMILES-extractor";
  total_mentions: number;
  candidates: DocumentMoleculeCandidate[];
  warnings: string[];
}

export interface ConformerAtom {
  element: string;
  x: number;
  y: number;
  z: number;
  formal_charge: number;
}

export interface ConformerBond {
  begin: number;
  end: number;
  order: number;
}

export interface Conformer3D {
  method: string;
  structure_role: "standardized-parent";
  coordinate_sha256: string;
  atoms: ConformerAtom[];
  bonds: ConformerBond[];
}
