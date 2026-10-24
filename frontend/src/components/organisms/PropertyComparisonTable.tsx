import type { AnalyzeResponse, ResultStatus } from "../../schemas/analysis";
import { StatusLabel } from "../atoms/StatusLabel";
import type { StatusTone } from "../atoms/StatusMark";
import { PropertyValue } from "../molecules/PropertyValue";

const STATUS_COPY: Record<ResultStatus, string> = {
  AVAILABLE: "Match",
  INVALID_INPUT: "Invalid input",
  AMBIGUOUS_INPUT: "Ambiguous input",
  NOT_COMPUTABLE: "Not computable",
  NOT_AVAILABLE: "Not available",
  NOT_APPLICABLE: "Not applicable",
  NO_REFERENCE_MATCH: "No reference match",
  OUTSIDE_SNAPSHOT_COVERAGE: "Outside coverage",
  COMPUTATION_ERROR: "Computation error",
  CONFLICTING_EVIDENCE: "Difference",
};

function toneForComparison(status: ResultStatus): StatusTone {
  if (status === "AVAILABLE") return "verified";
  if (status === "CONFLICTING_EVIDENCE" || status === "AMBIGUOUS_INPUT") return "ambiguous";
  if (status === "INVALID_INPUT" || status === "COMPUTATION_ERROR") return "invalid";
  return "unknown";
}

export function PropertyComparisonTable({ results }: { results: AnalyzeResponse[] }) {
  const validResults = results.filter((result) => result.status !== "invalid");
  const propertyKeys = validResults[0]?.properties.map((item) => item.key) ?? [];
  const snapshotLabel = validResults[0]?.manifest.snapshot_id ?? "No snapshot";

  return (
    <section className="property-section" aria-labelledby="property-heading">
      <header>
        <h2 id="property-heading">Property comparison (valid structures only)</h2>
        <span>{snapshotLabel} · frozen development fixture</span>
      </header>
      <div className="property-table-wrap">
        <table className="property-table">
          <thead>
            <tr>
              <th rowSpan={2}>Property</th>
              {validResults.map((result) => <th key={result.analysis_id} colSpan={3}>{result.label}</th>)}
            </tr>
            <tr>
              {validResults.flatMap((result) => [
                <th key={`${result.analysis_id}-computed`}>Computed</th>,
                <th key={`${result.analysis_id}-evidence`}>Frozen evidence</th>,
                <th key={`${result.analysis_id}-status`}>Status</th>,
              ])}
            </tr>
          </thead>
          <tbody>
            {propertyKeys.map((key) => {
              const firstProperty = validResults[0]?.properties.find((item) => item.key === key);
              return (
                <tr key={key}>
                  <th>{firstProperty?.label}</th>
                  {validResults.flatMap((result) => {
                    const property = result.properties.find((item) => item.key === key);
                    if (!property) return [];
                    return [
                      <td key={`${result.analysis_id}-${key}-computed`}><PropertyValue observation={property.computed} /></td>,
                      <td key={`${result.analysis_id}-${key}-evidence`}><PropertyValue observation={property.evidence} /></td>,
                      <td key={`${result.analysis_id}-${key}-status`}>
                        <StatusLabel tone={toneForComparison(property.comparison_status)}>
                          {STATUS_COPY[property.comparison_status]}
                        </StatusLabel>
                      </td>,
                    ];
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
