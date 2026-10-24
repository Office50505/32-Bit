import { useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  FileText,
  Maximize2,
  Minus,
  Pencil,
  Plus,
  RotateCcw,
  Search,
} from "lucide-react";

import { CompareTable } from "./CompareTable";
import { ComputedMolecule3D } from "./ComputedMolecule3D";
import type { AuditTab, MoleculeCandidate, StepId } from "./domain";
import { LiveMoleculeSvg } from "./LiveMoleculeSvg";
import { EvidenceStatusBadge, MoleculeStatusBadge } from "./StatusBadge";

const tabs: { id: AuditTab; label: string }[] = [
  { id: "validation", label: "Validation" },
  { id: "standardization", label: "Standardization" },
  { id: "properties", label: "Properties" },
  { id: "evidence", label: "Evidence" },
  { id: "provenance", label: "Provenance" },
];

interface Props {
  step: StepId;
  molecules: MoleculeCandidate[];
  selected: MoleculeCandidate;
  filtered: MoleculeCandidate[];
  search: string;
  onSearch: (value: string) => void;
  onSelect: (id: string) => void;
  onAddSource: () => void;
  onEdit: () => void;
  onReviewSource: () => void;
}

export function ValidationDesk({
  step,
  molecules,
  selected,
  filtered,
  search,
  onSearch,
  onSelect,
  onAddSource,
  onEdit,
  onReviewSource,
}: Props) {
  const [tab, setTab] = useState<AuditTab>("validation");
  const [view, setView] = useState<"2d" | "3d">("2d");
  const [autorotate, setAutorotate] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [resetSignal, setResetSignal] = useState(0);
  const [fullScreen, setFullScreen] = useState(false);
  const primaryIssue = selected.issues[0];
  const hasFrozenSnapshot = selected.manifest.snapshotId.startsWith("pubchem-pug-cid-");
  const snapshotLabel = selected.status === "invalid"
    ? "Not applicable—invalid structure"
    : hasFrozenSnapshot
      ? selected.manifest.snapshotId
      : "Reference temporarily unavailable";

  function changeZoom(direction: number) {
    setZoom((current) => Math.max(0.65, Math.min(1.55, current + direction * 0.12)));
  }

  return <>
    <section className={`inspection-grid ${fullScreen ? "inspection-grid--fullscreen" : ""}`} aria-label="Molecular inspection workspace">
      <div className="molecule-list panel">
        <div className="panel-heading"><div><h2>Structures <span>({filtered.length})</span></h2><p>Backend-verified records in this run</p></div></div>
        <label className="list-search"><Search size={16} /><input id="structure-search" value={search} onChange={(event) => onSearch(event.target.value)} placeholder="Search structures" aria-label="Search structures" /></label>
        <div className="molecule-rows">{filtered.map((molecule) => <button key={molecule.id} className={`molecule-row molecule-row--${molecule.status} ${selected.id === molecule.id ? "molecule-row--selected" : ""}`} onClick={() => { onSelect(molecule.id); setZoom(1); }} aria-pressed={selected.id === molecule.id}>
          <span className="row-thumbnail"><LiveMoleculeSvg svg={molecule.depictionSvg} /></span>
          <span className="row-info"><strong>{molecule.label}</strong><small>{molecule.formula ?? "Formula not computed"}</small><em>{molecule.mentionCount > 1 ? `${molecule.mentionCount} source mentions` : molecule.source}</em><MoleculeStatusBadge status={molecule.status} /></span>
        </button>)}{filtered.length === 0 ? <p className="list-empty">No structures match that search.</p> : null}</div>
        <button className="list-add" onClick={onAddSource}><Plus size={16} /> Add source</button>
      </div>

      <div className="viewer-panel panel">
        <div className="viewer-heading"><div><h2>Molecular view</h2><p>{selected.label} · {view === "2d" ? "RDKit depiction tied to validation findings" : "on-demand RDKit conformer from the standardized parent"}</p></div><div className="view-switch" role="group" aria-label="View dimension"><button className={view === "2d" ? "active" : ""} onClick={() => setView("2d")}>2D evidence view</button><button className={view === "3d" ? "active" : ""} onClick={() => setView("3d")}>Computed 3D</button></div></div>
        <div className="viewer-options">{view === "3d" ? <label className="toggle-label">Autorotate <input type="checkbox" checked={autorotate} onChange={(event) => setAutorotate(event.target.checked)} /><span className="toggle-track" /></label> : <span className="viewer-mode-note">Evidence-backed 2D depiction</span>}</div>
        <div className={`viewer-canvas ${view === "2d" ? "viewer-canvas--2d" : "viewer-canvas--3d"}`}>
          {view === "2d" ? <LiveMoleculeSvg svg={selected.depictionSvg} zoom={zoom} /> : <ComputedMolecule3D key={selected.id} structure={selected.standardizedSmiles} label={selected.label} status={selected.status} autorotate={autorotate} resetSignal={resetSignal} zoom={zoom} />}
        </div>
        <div className="viewer-toolbar"><div className="zoom-control"><button onClick={() => changeZoom(-1)} aria-label="Zoom out"><Minus size={17} /></button><span>{Math.round(zoom * 100)}%</span><button onClick={() => changeZoom(1)} aria-label="Zoom in"><Plus size={17} /></button></div>
          <button onClick={() => setFullScreen((current) => !current)}><Maximize2 size={17} /> {fullScreen ? "Exit fullscreen" : "Expand"}</button>
          <button onClick={onEdit}><Pencil size={17} /> Edit structure</button>
          <button onClick={() => { setZoom(1); setResetSignal((current) => current + 1); }}><RotateCcw size={17} /> Reset view</button>
        </div>
      </div>

      <div className="diagnostic-panel panel">
        <div className="panel-heading diagnostic-heading"><div><h2>Diagnostic</h2><p>{selected.issues.length} finding{selected.issues.length === 1 ? "" : "s"}</p></div><MoleculeStatusBadge status={selected.status} compact /></div>
        <div className={`diagnostic-summary diagnostic-summary--${selected.status}`}><span className="diagnostic-icon">{selected.status === "valid" ? <CheckCircle2 size={23} /> : <AlertCircle size={23} />}</span><div><strong>{primaryIssue?.title ?? "No blocking issue detected"}</strong><p>{primaryIssue?.explanation ?? "The submitted molecular graph passed the configured validation rules."}</p>{primaryIssue?.subcode ? <code className="issue-code">{primaryIssue.code} / {primaryIssue.subcode}</code> : primaryIssue ? <code className="issue-code">{primaryIssue.code}</code> : null}</div></div>
        {selected.issues.length > 1 ? <div className="additional-findings"><strong>Additional findings</strong>{selected.issues.slice(1).map((issue) => <button key={`${issue.code}-${issue.atomIndex ?? "none"}`} onClick={() => setTab("validation")}><span>{issue.title}</span><code>{issue.subcode ?? issue.code}</code></button>)}</div> : null}
        <div className="diagnostic-block"><h3>Why this matters</h3><p>{primaryIssue?.whyItMatters ?? "A valid molecular graph is required before descriptors can be interpreted safely."}</p></div>
        <div className="next-step"><BookOpen size={19} /><div><strong>Next step</strong><p>{primaryIssue?.nextStep ?? "Review the standardization record and evidence coverage before using the values."}</p><button onClick={onReviewSource}>{selected.sourceFileSha256 ? "Review source" : "Review submitted input"} <ArrowRight size={15} /></button></div></div>
        <div className="source-reference"><FileText size={19} /><div><strong>Source reference</strong><p>{selected.source}</p><span>{selected.sourceFileSha256 ? `SHA-256 ${selected.sourceFileSha256.slice(0, 16)}…` : "Direct molecular notation"}</span></div></div>
      </div>
    </section>

    <section className="audit-panel panel">
      <div className="audit-tabs" role="tablist" aria-label="Audit details">{tabs.map((item) => <button key={item.id} role="tab" aria-selected={tab === item.id} className={tab === item.id ? "audit-tab--active" : ""} onClick={() => setTab(item.id)}>{item.label}</button>)}</div>
      <div className="audit-body">
        {tab === "validation" ? <><CompareTable molecules={molecules} brief={step !== "compare"} /><div className="finding-list"><h2>Validation findings for {selected.label}</h2>{selected.issues.length ? selected.issues.map((issue) => <article key={`${issue.code}-${issue.subcode ?? "general"}-${issue.atomIndex ?? "none"}`}><div><strong>{issue.title}</strong><code>{issue.subcode ?? issue.code}</code></div><p>{issue.explanation}</p><small>{issue.nextStep}</small></article>) : <p className="empty-detail">No validation issue was detected.</p>}</div></> : null}
        {tab === "properties" ? <><div className="audit-intro"><div><h2>{selected.label} property audit</h2><p>{selected.status === "invalid" ? "Computation is blocked until the molecular graph is valid." : "RDKit calculations are compared with a hash-verified frozen PubChem record when covered."}</p></div><span className={`snapshot-pill ${hasFrozenSnapshot ? "snapshot-pill--ready" : ""}`}>{snapshotLabel}</span></div>{selected.status === "invalid" ? <div className="property-blocked-notice" role="note"><AlertCircle size={18} /><div><strong>Calculation stopped for safety</strong><p>{primaryIssue?.explanation} {primaryIssue?.nextStep}</p></div></div> : null}<div className="table-scroll"><table className="property-table"><thead><tr><th>Property</th><th>Computed</th><th>Frozen evidence</th><th>Status and reason</th></tr></thead><tbody>{selected.descriptors.map((record) => <tr key={record.key}><th scope="row">{record.label}</th><td>{record.value === null ? "Not computed" : `${record.value}${record.unit ? ` ${record.unit}` : ""}`}</td><td className="table-muted">{record.reference ?? "No value"}</td><td><EvidenceStatusBadge status={record.status} /><small className="cell-reason">{record.reason}</small></td></tr>)}</tbody></table></div></> : null}
        {tab === "standardization" ? <div className="detail-layout"><div><h2>Standardization record</h2><p>Every transformation is listed while the submitted form remains preserved.</p>{selected.steps.length ? <ol className="step-records">{selected.steps.map((record) => <li key={record.code}><strong>{record.label}</strong><span>{record.changed ? "Changed" : "No change"}</span><code>{record.before} → {record.after}</code></li>)}</ol> : <p className="empty-detail">No standardization was attempted because the input is invalid.</p>}</div><div className="detail-note"><strong>Submitted SMILES</strong><code>{selected.smiles}</code></div></div> : null}
        {tab === "evidence" ? <div className="detail-layout"><div><h2>Reference evidence</h2><p>{selected.status === "invalid" ? "Evidence lookup was skipped because no valid standardized identity exists." : "Computed values and external evidence remain separate. Available reference values come from one hash-verified PubChem response."}</p><div className="evidence-details">{selected.descriptors.map((record) => <div key={record.key}><strong>{record.label}</strong><EvidenceStatusBadge status={record.status} /><p>{record.reason}</p></div>)}</div></div><div className="detail-note"><strong>Snapshot ID</strong><code>{selected.manifest.snapshotId}</code><small>{selected.manifest.snapshotScope}</small></div></div> : null}
        {tab === "provenance" ? <div className="detail-layout"><div><h2>Provenance manifest</h2><p>These values were returned by the live backend and identify the exact input, configuration and output.</p><dl className="manifest-list"><div><dt>Input SHA-256</dt><dd>{selected.manifest.inputSha256}</dd></div><div><dt>Output SHA-256</dt><dd>{selected.manifest.outputSha256}</dd></div><div><dt>Configuration SHA-256</dt><dd>{selected.manifest.configurationSha256}</dd></div><div><dt>RDKit version</dt><dd>{selected.manifest.rdkitVersion}</dd></div></dl></div><div className="detail-note"><strong>Analysis ID</strong><code>{selected.manifest.analysisId}</code><strong>Snapshot ID</strong><code>{selected.manifest.snapshotId}</code></div></div> : null}
      </div>
    </section>
  </>;
}
