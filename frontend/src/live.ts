import type { AnalyzeResponse, PropertyComparison } from "./schemas/analysis";
import type { DescriptorRecord, MoleculeCandidate } from "./domain";

function mapProperty(property: PropertyComparison): DescriptorRecord {
  const status = property.computed.status === "INVALID_INPUT" || property.computed.status === "COMPUTATION_ERROR" ? "NOT_COMPUTED"
    : property.comparison_status === "AVAILABLE" ? "MATCH"
    : property.comparison_status === "CONFLICTING_EVIDENCE" ? "DIFFERENCE"
    : property.comparison_status === "OUTSIDE_SNAPSHOT_COVERAGE" ? "OUTSIDE_COVERAGE"
    : property.comparison_status === "NOT_APPLICABLE" ? "NOT_APPLICABLE" : "NOT_AVAILABLE";
  return {
    key: property.key, label: property.label, value: property.computed.value,
    unit: property.computed.unit ?? undefined, reference: property.evidence.value,
    status, reason: property.evidence.reason ?? property.computed.reason ?? "No reason supplied.",
  };
}

export function fromApi(result: AnalyzeResponse): MoleculeCandidate {
  const formula = result.properties.find((item) => item.key === "molecular_formula")?.computed.value;
  const weight = result.properties.find((item) => item.key === "molecular_weight")?.computed.value;
  const issue = result.issues[0];
  return {
    id: result.analysis_id, label: result.label, smiles: result.raw_input,
    formula: formula == null ? null : String(formula), weight: typeof weight === "number" ? weight : null,
    status: result.status, source: result.source?.filename ?? result.source?.source_type ?? "Direct SMILES",
    issue: issue ? { code: issue.code, title: issue.title, explanation: issue.explanation,
      whyItMatters: issue.why_it_matters, nextStep: issue.next_step, severity: issue.severity,
      atomIndex: issue.location.atom_indices[0] } : null,
    steps: result.standardization_steps.map((step) => ({ code: step.code, label: step.label,
      before: step.before_smiles, after: step.after_smiles, changed: step.changed })),
    descriptors: result.properties.map(mapProperty), confirmed: true, depictionSvg: result.depiction_svg,
    manifest: { analysisId: result.analysis_id, inputSha256: result.manifest.input_sha256,
      outputSha256: result.manifest.output_sha256, configurationSha256: result.manifest.configuration_sha256,
      rdkitVersion: result.manifest.tool_versions.rdkit, snapshotId: result.manifest.snapshot_id, mode: "live" },
  };
}
