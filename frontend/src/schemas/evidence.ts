export type EvidenceVerdict =
  | "SUPPORTED"
  | "CONTRADICTED"
  | "INSUFFICIENT_EVIDENCE"
  | "OUT_OF_SCOPE";

export type ConfidenceLevel = "HIGH" | "MEDIUM" | "LOW";

export interface EvidenceCitation {
  evidence_id: string;
  source_type: "CHEMBL_ACTIVITY" | "PUBCHEM_BIOASSAY" | "PAPER_PASSAGE" | "RUN_RECORD";
  source_record_id: string;
  basis: "EXPERIMENTAL" | "COMPUTED" | "LITERATURE_CONTEXT";
  directness: "DIRECT" | "INDIRECT" | "CONTEXT_ONLY";
  stance: "SUPPORTS" | "CONTRADICTS" | "NEUTRAL";
  relation?: "=" | "<" | ">" | "<=" | ">=" | null;
  value?: number | null;
  unit?: string | null;
  paper_id?: string | null;
  passage_locator?: string | null;
  passage_text?: string | null;
  retraction_status: string;
  snapshot_id: string;
  assay_conditions: Record<string, unknown>;
  quality_flags: string[];
}

export interface EvidenceStatementVerdict {
  statement: {
    statement_id: string;
    text: string;
    claim_type: string;
  };
  resolution: {
    status: string;
    molecule_inchikey?: string | null;
    target_id?: string | null;
    organism?: string | null;
    endpoint?: string | null;
    reason_codes: string[];
  };
  verdict: EvidenceVerdict;
  citations: EvidenceCitation[];
  reason: string;
  reason_codes: string[];
  limitations: string[];
  conflict_summary?: string | null;
  confidence: {
    level: ConfidenceLevel;
    benchmark_accuracy?: number | null;
    benchmark_case_count?: number | null;
  };
}

export interface ClaimCheckResponse {
  assistant_run_id: string;
  verdicts: EvidenceStatementVerdict[];
  research_aid_notice: string;
  manifest: {
    model_name: string;
    model_digest: string;
    evidence_snapshot_id: string;
    input_sha256: string;
    configuration_sha256: string;
    output_sha256: string;
  };
}
