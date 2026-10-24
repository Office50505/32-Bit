import type { AnalyzeResponse, PropertyComparison } from "./schemas/analysis";
import type { DescriptorRecord, EvidenceStatus, MoleculeCandidate } from "./domain";

function mapProperty(property: PropertyComparison): DescriptorRecord {
  let status: EvidenceStatus;
  switch (property.comparison_status) {
    case "AVAILABLE": status = "MATCH"; break;
    case "CONFLICTING_EVIDENCE": status = "DIFFERENCE"; break;
    case "INVALID_INPUT":
    case "NOT_COMPUTABLE":
    case "COMPUTATION_ERROR": status = "NOT_COMPUTED"; break;
    case "AMBIGUOUS_INPUT": status = "AMBIGUOUS_INPUT"; break;
    case "NOT_AVAILABLE": status = "NOT_AVAILABLE"; break;
    case "NOT_APPLICABLE": status = "NOT_APPLICABLE"; break;
    case "NO_REFERENCE_MATCH": status = "NO_REFERENCE_MATCH"; break;
    case "OUTSIDE_SNAPSHOT_COVERAGE": status = "OUTSIDE_SNAPSHOT_COVERAGE"; break;
  }
  return {
    key: property.key, label: property.label, value: property.computed.value,
    unit: property.computed.unit ?? undefined, reference: property.evidence.value,
    status, reason: property.evidence.reason ?? property.computed.reason ?? "No reason supplied.",
  };
}

export function fromApi(result: AnalyzeResponse, inputIndex = 0): MoleculeCandidate {
  const formula = result.properties.find((item) => item.key === "molecular_formula")?.computed.value;
  const weight = result.properties.find((item) => item.key === "molecular_weight")?.computed.value;
  const issues = result.issues.map((item) => ({
    code: item.code, subcode: item.subcode, title: item.title, explanation: item.explanation,
    whyItMatters: item.why_it_matters, nextStep: item.next_step, severity: item.severity,
    atomIndex: item.location.atom_indices[0],
  }));
  const issue = issues[0];
  return {
    id: `${result.analysis_id}-${inputIndex}`, label: result.label, smiles: result.raw_input,
    standardizedSmiles: result.standardized_smiles,
    formula: formula == null ? null : String(formula), weight: typeof weight === "number" ? weight : null,
    status: result.status, source: result.source?.filename ?? result.source?.source_type ?? "Direct SMILES",
    issue: issue ?? null, issues,
    steps: result.standardization_steps.map((step) => ({ code: step.code, label: step.label,
      before: step.before_smiles, after: step.after_smiles, changed: step.changed })),
    descriptors: result.properties.map(mapProperty), confirmed: true, depictionSvg: result.depiction_svg,
    sourceFileSha256: result.source?.file_sha256, inputIndex,
    sourcePage: result.source?.page, sourceRow: result.source?.row,
    sourceExcerpt: result.source?.source_excerpt,
    sourceMentions: result.source?.mentions,
    mentionCount: result.source?.mention_count ?? result.source?.mentions?.length ?? 1,
    manifest: { analysisId: result.analysis_id, inputSha256: result.manifest.input_sha256,
      outputSha256: result.manifest.output_sha256, configurationSha256: result.manifest.configuration_sha256,
      rdkitVersion: result.manifest.tool_versions.rdkit, snapshotId: result.manifest.snapshot_id,
      snapshotScope: result.manifest.snapshot_scope },
  };
}
