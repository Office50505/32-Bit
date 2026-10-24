import type { MoleculeCandidate } from "./domain";

export function CompareTable({ molecules }: { molecules: MoleculeCandidate[] }) {
  const valid = molecules.filter((item) => item.status !== "invalid");
  const rows = valid[0]?.descriptors ?? [];
  return <>
    <div className="audit-intro"><div><h2>Multi-structure audit</h2><p>Only valid or ambiguous molecular graphs have computed descriptors. Ambiguity remains visible.</p></div><span className="snapshot-pill">{valid.length} comparable · {molecules.length - valid.length} blocked</span></div>
    <div className="table-scroll"><table className="property-table"><thead><tr><th>Property</th>{valid.map((item) => <th key={item.id}>{item.label}{item.status === "ambiguous" ? " · ambiguous" : ""}</th>)}<th>Bootstrap evidence</th></tr></thead><tbody>{rows.map((row) => <tr key={row.key}><th>{row.label}</th>{valid.map((item) => { const record = item.descriptors.find((entry) => entry.key === row.key); return <td key={item.id}>{record?.value ?? "—"}{record?.value != null && record.unit ? ` ${record.unit}` : ""}</td>; })}<td><span className={`evidence-badge evidence-badge--${row.status.toLowerCase()}`}>{row.status.toLowerCase().replaceAll("_", " ")}</span></td></tr>)}</tbody></table></div>
    {molecules.some((item) => item.status === "invalid") && <p className="compare-note">Invalid inputs are excluded from numerical comparison because no descriptor was calculated.</p>}
  </>;
}
