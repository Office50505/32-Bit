export type MoleculeStatus = "valid" | "ambiguous" | "invalid";
export type EvidenceStatus = "MATCH" | "DIFFERENCE" | "NOT_AVAILABLE" | "OUTSIDE_SNAPSHOT_COVERAGE" | "NOT_APPLICABLE" | "NO_REFERENCE_MATCH" | "AMBIGUOUS_INPUT" | "NOT_COMPUTED";
export type StepId = "source" | "confirm" | "validate" | "compare" | "report";
export type AuditTab = "validation" | "standardization" | "properties" | "evidence" | "provenance";

export interface ValidationIssue {
  code: string;
  subcode?: string | null;
  title: string;
  explanation: string;
  whyItMatters: string;
  nextStep: string;
  atomIndex?: number;
  severity: "error" | "warning" | "info";
}

export interface StandardizationStep {
  code: string;
  label: string;
  before: string;
  after: string;
  changed: boolean;
}

export interface DescriptorRecord {
  key: string;
  label: string;
  value: string | number | null;
  unit?: string;
  reference: string | number | null;
  status: EvidenceStatus;
  reason: string;
}

export interface ProvenanceManifest {
  analysisId: string;
  inputSha256: string;
  outputSha256: string;
  configurationSha256: string;
  rdkitVersion: string;
  snapshotId: string;
}

export interface MoleculeCandidate {
  id: string;
  label: string;
  smiles: string;
  formula: string | null;
  weight: number | null;
  status: MoleculeStatus;
  source: string;
  issue: ValidationIssue | null;
  issues: ValidationIssue[];
  steps: StandardizationStep[];
  descriptors: DescriptorRecord[];
  manifest: ProvenanceManifest;
  confirmed: boolean;
  depictionSvg?: string | null;
  sourceFileSha256?: string | null;
  inputIndex: number;
}
