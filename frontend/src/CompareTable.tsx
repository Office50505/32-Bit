import type { MoleculeCandidate } from "./domain";
import { EvidenceStatusBadge } from "./StatusBadge";

export function CompareTable({ molecules, brief = false }: { molecules: MoleculeCandidate[]; brief?: boolean }) {
  const comparable = molecules.filter((molecule) => molecule.status !== "invalid");
  const snapshotId = comparable[0]?.manifest.snapshotId;
  const hasFrozenSnapshot = snapshotId?.startsWith("pubchem-pug-cid-") ?? false;
  const rows = (comparable[0]?.descriptors ?? []).filter((descriptor) =>
    !brief || ["molecular_formula", "molecular_weight", "exact_mass", "logp"].includes(descriptor.key),
  );

  return <div className="space-y-3">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 className="font-serif text-[17px] font-bold text-slate-800">Auditable property comparison</h2>
        <p className="mt-1 text-[11px] leading-relaxed text-slate-500">Computed results and reference evidence remain separate for each molecule.</p>
      </div>
      <span className={`reference-snapshot-chip ${hasFrozenSnapshot ? "reference-snapshot-chip--ready" : ""}`}>
        {hasFrozenSnapshot ? "Frozen PubChem reference" : "Reference snapshot"}: {snapshotId ?? "not applicable"}
      </span>
    </div>
    <div className="table-scroll">
      <table className="property-table comparison-table">
        <thead>
          <tr>
            <th rowSpan={2} scope="col">Property</th>
            {comparable.map((molecule) => <th key={molecule.id} colSpan={3} scope="colgroup">
              {molecule.label}{molecule.status === "ambiguous" ? " · ambiguous" : ""}
            </th>)}
          </tr>
          <tr>{comparable.flatMap((molecule) => [
            <th key={`${molecule.id}-computed`} scope="col">Computed</th>,
            <th key={`${molecule.id}-evidence`} scope="col">Frozen evidence</th>,
            <th key={`${molecule.id}-status`} scope="col">Status</th>,
          ])}</tr>
        </thead>
        <tbody>{rows.map((row) => <tr key={row.key}>
          <th scope="row">{row.label}</th>
          {comparable.flatMap((molecule) => {
            const descriptor = molecule.descriptors.find((item) => item.key === row.key);
            if (!descriptor) return [
              <td key={`${molecule.id}-computed`}>—</td>,
              <td key={`${molecule.id}-evidence`}>—</td>,
              <td key={`${molecule.id}-status`}><EvidenceStatusBadge status="NOT_COMPUTED" /></td>,
            ];
            return [
              <td key={`${molecule.id}-computed`}>{descriptor.value === null ? "—" : `${descriptor.value}${descriptor.unit ? ` ${descriptor.unit}` : ""}`}</td>,
              <td key={`${molecule.id}-evidence`} className="table-muted">{descriptor.reference === null ? "—" : `${descriptor.reference}${descriptor.unit ? ` ${descriptor.unit}` : ""}`}</td>,
              <td key={`${molecule.id}-status`}><EvidenceStatusBadge status={descriptor.status} /><small className="cell-reason">{descriptor.reason}</small></td>,
            ];
          })}
        </tr>)}</tbody>
      </table>
    </div>
    {molecules.some((molecule) => molecule.status === "invalid") ? <p className="calculation-blocker">
      <strong>Why values are not computed:</strong> invalid structures are excluded from descriptor calculation. Correct the highlighted atom or bond, then rerun the analysis.
    </p> : null}
  </div>;
}
