export type MoleculeStatus = "valid" | "ambiguous" | "invalid";
export type EvidenceStatus = "MATCH" | "DIFFERENCE" | "NOT_AVAILABLE" | "OUTSIDE_SNAPSHOT_COVERAGE" | "NOT_APPLICABLE" | "NO_REFERENCE_MATCH" | "AMBIGUOUS_INPUT" | "NOT_COMPUTED";
export type StepId = "source" | "confirm" | "validate" | "compare" | "report";
export type AuditTab = "validation" | "standardization" | "properties" | "evidence" | "provenance";

export interface CandidateSourceMention {
  kind: "pdf-text" | "csv-row" | "image" | "manual";
  page?: number;
  row?: number;
  locator: string;
  excerpt: string;
}

export interface ExtractedSourceCandidate {
  id: string;
  label: string;
  smiles: string;
  confidence: "high" | "medium" | "needs-review";
  mentions: CandidateSourceMention[];
}

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
  snapshotScope: string;
}

export interface MoleculeCandidate {
  id: string;
  label: string;
  smiles: string;
  standardizedSmiles?: string | null;
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
  sourcePage?: number | null;
  sourceRow?: number | null;
  sourceExcerpt?: string | null;
  sourceMentions?: Array<{
    kind: "pdf-text" | "csv-row" | "image" | "manual";
    page?: number;
    row?: number;
    locator?: string;
    excerpt?: string;
  }>;
  mentionCount: number;
  inputIndex: number;
}
