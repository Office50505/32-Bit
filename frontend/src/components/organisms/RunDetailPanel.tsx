import type { AnalyzeResponse } from "../../schemas/analysis";
import { PropertyComparisonTable } from "./PropertyComparisonTable";
import type { RunTab } from "../molecules/RunTabs";

interface RunDetailPanelProps {
  activeTab: RunTab;
  results: AnalyzeResponse[];
  selected: AnalyzeResponse;
}

export function RunDetailPanel({ activeTab, results, selected }: RunDetailPanelProps) {
  if (activeTab === "validation" || activeTab === "properties") {
    return <PropertyComparisonTable results={results} />;
  }

  if (activeTab === "standardization") {
    return (
      <section className="run-detail-panel">
        <header><h2>Standardization record</h2><span>{selected.label}</span></header>
        <ol className="standardization-list">
          {selected.standardization_steps.length ? selected.standardization_steps.map((step) => (
            <li key={step.code} className={step.changed ? "standardization-step--changed" : ""}>
              <div><strong>{step.label}</strong><span>{step.changed ? "Changed" : "No change"}</span></div>
              <code>{step.before_smiles}</code>
              <span aria-hidden="true">→</span>
              <code>{step.after_smiles}</code>
            </li>
          )) : <li>No standardization was attempted because the input is invalid.</li>}
        </ol>
      </section>
    );
  }

  if (activeTab === "evidence") {
    return (
      <section className="run-detail-panel">
        <header><h2>Frozen evidence</h2><span>{selected.manifest.snapshot_id}</span></header>
        <p className="coverage-note">{selected.manifest.snapshot_scope}</p>
        <div className="evidence-list">
          {selected.properties.map((property) => (
            <div key={property.key}>
              <strong>{property.label}</strong>
              <span>{property.evidence.status.replaceAll("_", " ").toLowerCase()}</span>
              <p>{property.evidence.reason ?? "Evidence value is available in the frozen fixture."}</p>
            </div>
          ))}
        </div>
      </section>
    );
  }

  return (
    <section className="run-detail-panel">
      <header><h2>Reproducibility manifest</h2><span>{selected.analysis_id}</span></header>
      <dl className="manifest-grid">
        <div><dt>Input SHA-256</dt><dd><code>{selected.manifest.input_sha256}</code></dd></div>
        <div><dt>Configuration SHA-256</dt><dd><code>{selected.manifest.configuration_sha256}</code></dd></div>
        <div><dt>Output SHA-256</dt><dd><code>{selected.manifest.output_sha256}</code></dd></div>
        <div><dt>RDKit</dt><dd>{selected.manifest.tool_versions.rdkit}</dd></div>
        <div><dt>Pipeline</dt><dd>{selected.manifest.tool_versions.pipeline}</dd></div>
        <div><dt>Ruleset</dt><dd>{selected.manifest.tool_versions.ruleset}</dd></div>
      </dl>
    </section>
  );
}
