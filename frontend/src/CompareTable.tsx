import { moleculeDisplayLabel, type MoleculeCandidate } from "./domain";
import { EvidenceStatusBadge } from "./StatusBadge";
import type { MoleculeIdentityComparison, MoleculeRelationship } from "./schemas/analysis";

export function CompareTable({
  molecules,
  identityComparisons,
  brief = false,
}: {
  molecules: MoleculeCandidate[];
  identityComparisons: MoleculeIdentityComparison[];
  brief?: boolean;
}) {
  const comparable = molecules.filter((molecule) => molecule.status !== "invalid");
  const snapshotIds = [...new Set(comparable.map((molecule) => molecule.manifest.snapshotId))];
  const snapshotId = snapshotIds[0];
  const hasFrozenSnapshot = snapshotIds.length === 1 && snapshotId?.startsWith("pubchem-pug-cid-");
  const snapshotSummary = snapshotIds.length === 0
    ? "not applicable"
    : snapshotIds.length === 1
      ? snapshotId
      : "per-molecule reference status";
  const invalidCount = molecules.length - comparable.length;
  const rows = (comparable[0]?.descriptors ?? []).filter((descriptor) =>
    !brief || ["molecular_formula", "molecular_weight", "exact_mass", "logp"].includes(descriptor.key),
  );

  return <div className="space-y-3">
    {identityComparisons.length ? <section className="identity-comparison" aria-labelledby="identity-comparison-title">
      <div className="identity-comparison__heading">
        <div>
          <h3 id="identity-comparison-title">Molecule identity verdicts</h3>
          <p>Explicit cross-input decisions from canonical and standardized structures.</p>
        </div>
        <span>{identityComparisons.length} pair{identityComparisons.length === 1 ? "" : "s"}</span>
      </div>
      <div className="identity-comparison__grid">{identityComparisons.map((comparison) => {
        const left = molecules[comparison.left_index];
        const right = molecules[comparison.right_index];
        return <article key={`${comparison.left_index}-${comparison.right_index}`}>
          <div><strong>{left ? moleculeDisplayLabel(left) : `Structure ${comparison.left_index + 1}`}</strong><span>vs</span><strong>{right ? moleculeDisplayLabel(right) : `Structure ${comparison.right_index + 1}`}</strong></div>
          <mark data-relationship={comparison.relationship}>{relationshipLabel(comparison.relationship)}</mark>
          <p>{comparison.reason}</p>
          <code>{comparison.reason_code}</code>
        </article>;
      })}</div>
    </section> : null}
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 className="font-serif text-[17px] font-bold text-slate-800">Auditable property comparison</h2>
        <p className="mt-1 text-[11px] leading-relaxed text-slate-500">Computed results and reference evidence remain separate for each molecule.</p>
      </div>
      <span className={`reference-snapshot-chip ${hasFrozenSnapshot ? "reference-snapshot-chip--ready" : ""}`}>
        {hasFrozenSnapshot ? "Frozen PubChem reference" : "Reference evidence"}: {snapshotSummary}
      </span>
    </div>
    <div className="table-scroll">
      <table className="property-table comparison-table">
        <thead>
          <tr>
            <th rowSpan={2} scope="col">Property</th>
            {comparable.map((molecule) => <th key={molecule.id} colSpan={3} scope="colgroup">
              <span className="comparison-molecule-name">{moleculeDisplayLabel(molecule)}{molecule.status === "ambiguous" ? " · ambiguous" : ""}</span>
              <small className="comparison-snapshot-state">{snapshotStateLabel(molecule.manifest.snapshotId)}</small>
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
    <section className="chembl-comparison" aria-labelledby="chembl-comparison-title">
      <div className="chembl-comparison__heading">
        <div>
          <h3 id="chembl-comparison-title">ChEMBL bioactivity evidence</h3>
          <p>Exact standardized-structure coverage is shown separately from PubChem physicochemical properties.</p>
        </div>
        <span>Dynamic · frozen per molecule</span>
      </div>
      <div className="chembl-comparison__grid">
        {molecules.map((molecule) => <article className="chembl-card" key={`${molecule.id}-chembl`}>
          <div className="chembl-card__title">
            <strong>{moleculeDisplayLabel(molecule)}</strong>
            <EvidenceStatusBadge status={molecule.bioactivity.status} />
          </div>
          {molecule.bioactivity.moleculeChemblId ? <dl>
            <div><dt>ChEMBL molecule</dt><dd>{molecule.bioactivity.moleculeChemblId}</dd></div>
            <div><dt>Preferred name</dt><dd>{molecule.bioactivity.preferredName ?? "Not assigned"}</dd></div>
            <div><dt>Release</dt><dd>{molecule.bioactivity.release ?? "Unknown"}</dd></div>
            <div><dt>Activity records</dt><dd>{molecule.bioactivity.activityCount ?? "Not reported"}</dd></div>
          </dl> : <p>{molecule.bioactivity.reason}</p>}
          <footer>
            <code title={molecule.bioactivity.snapshotScope}>{molecule.bioactivity.snapshotId}</code>
            {molecule.bioactivity.sourceUrl ? <a href={molecule.bioactivity.sourceUrl} target="_blank" rel="noreferrer">Source response</a> : null}
          </footer>
        </article>)}
      </div>
      <p className="chembl-comparison__caveat">Activity-record counts describe database coverage only. They are not evidence that a molecule is effective or safe.</p>
    </section>
    {invalidCount > 0 ? <p className="calculation-blocker">
      <strong>{invalidCount} invalid {invalidCount === 1 ? "structure was" : "structures were"} omitted:</strong> descriptor calculation is blocked only for invalid molecular graphs. The valid structures shown above were computed normally.
    </p> : null}
  </div>;
}

function relationshipLabel(relationship: MoleculeRelationship): string {
  const labels: Record<MoleculeRelationship, string> = {
    EXACT_SAME_STRUCTURE: "Same exact molecule",
    SAME_STANDARDIZED_PARENT: "Same standardized parent",
    STEREOISOMERS: "Different stereoisomers",
    DIFFERENT_STRUCTURE: "Different molecules",
    INDETERMINATE: "Identity indeterminate",
  };
  return labels[relationship];
}

function snapshotStateLabel(snapshotId: string): string {
  if (snapshotId.startsWith("pubchem-pug-cid-")) return snapshotId;
  if (snapshotId === "pubchem-no-reference-match") return "No exact PubChem CID found";
  if (snapshotId === "pubchem-pug-unavailable") return "PubChem temporarily unavailable";
  if (snapshotId.startsWith("not-applicable")) return "Reference lookup not applicable";
  return snapshotId;
}
