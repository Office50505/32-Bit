export type Severity = "error" | "warning" | "info";
export type MoleculeStatus = "valid" | "ambiguous" | "invalid";

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

export interface SourceMetadata {
  filename?: string;
  source_type?: string;
  citation?: string;
  page?: number;
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
  source?: SourceMetadata | null;
  manifest: RunManifest;
}

export interface BatchAnalyzeResponse {
  results: AnalyzeResponse[];
}
