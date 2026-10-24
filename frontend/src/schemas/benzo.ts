export type EvidenceVerdict =
  | "SUPPORTED"
  | "CONTRADICTED"
  | "INSUFFICIENT_EVIDENCE"
  | "OUT_OF_SCOPE";

export interface EvidenceCitation {
  evidence_id: string;
  source_type: "CHEMBL_ACTIVITY" | "PUBCHEM_BIOASSAY" | "PAPER_PASSAGE" | "RUN_RECORD";
  source_record_id: string;
  basis: "EXPERIMENTAL" | "COMPUTED" | "LITERATURE_CONTEXT";
  stance: "SUPPORTS" | "CONTRADICTS" | "NEUTRAL";
  directness: "DIRECT" | "INDIRECT" | "CONTEXT_ONLY";
  endpoint?: string | null;
  relation?: "=" | "<" | ">" | "<=" | ">=" | null;
  value?: number | null;
  unit?: string | null;
  paper_id?: string | null;
  passage_locator?: string | null;
  passage_text?: string | null;
  retraction_status: string;
  snapshot_id: string;
  raw_record_sha256: string;
  quality_flags: string[];
}

export interface StatementVerdict {
  statement: {
    statement_id: string;
    text: string;
    claim_type: string;
    molecule_mentions: string[];
    target_mentions: string[];
    endpoint_mentions: string[];
  };
  resolution: {
    status: "RESOLVED" | "AMBIGUOUS" | "UNRESOLVED" | "NOT_REQUIRED";
    reason_codes: string[];
  };
  verdict: EvidenceVerdict;
  citations: EvidenceCitation[];
  reason: string;
  reason_codes: string[];
  limitations: string[];
  conflict_summary?: string | null;
  confidence: {
    level: "HIGH" | "MEDIUM" | "LOW";
    method: "deterministic-calibration-v1";
    factor_scores: Record<string, number>;
    benchmark_accuracy?: number | null;
    benchmark_case_count?: number | null;
  };
}

export interface BenzoEvidenceResponse {
  assistant_run_id: string;
  verdicts: StatementVerdict[];
  research_aid_notice: "Research aid only. This report summarizes available evidence and is not a prediction of clinical efficacy or safety.";
  manifest: {
    model_name: string;
    model_digest: string;
    evidence_snapshot_id: string;
    input_sha256: string;
    configuration_sha256: string;
    output_sha256: string;
  };
}
