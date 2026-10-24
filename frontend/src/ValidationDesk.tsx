import { useState } from "react";
import { AlertCircle, ArrowRight, BookOpen, CheckCircle2, FileText, Maximize2, Minus,
  Pencil, Plus, RotateCcw, Search } from "lucide-react";
import type { AuditTab, MoleculeCandidate, StepId } from "./domain";
import { Molecule2D } from "./Molecule2D";
import { LiveMoleculeSvg } from "./LiveMoleculeSvg";
import Molecule3D from "./Molecule3D";
import { CompareTable } from "./CompareTable";
import { EvidenceStatusBadge, MoleculeStatusBadge } from "./StatusBadge";

const tabs: { id: AuditTab; label: string }[] = [
  { id: "validation", label: "Validation" }, { id: "standardization", label: "Standardization" },
  { id: "properties", label: "Properties" }, { id: "evidence", label: "Evidence" },
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

export function ValidationDesk({ step, molecules, selected, filtered, search, onSearch, onSelect,
  onAddSource, onEdit, onReviewSource }: Props) {
  const [tab, setTab] = useState<AuditTab>("validation");
  const [view, setView] = useState<"2d" | "3d">("3d");
  const [autorotate, setAutorotate] = useState(false);
  const [showLabels, setShowLabels] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [resetSignal, setResetSignal] = useState(0);
  const [fullScreen, setFullScreen] = useState(false);
  const [issueTip, setIssueTip] = useState(false);

  function changeZoom(direction: number) {
    setZoom((current) => Math.max(0.65, Math.min(1.55, current + direction * 0.12)));
  }

  return <>
    <section className={`inspection-grid ${fullScreen ? "inspection-grid--fullscreen" : ""}`} aria-label="Molecular inspection workspace">
      <div className="molecule-list panel">
        <div className="panel-heading"><div><h2>Structures <span>({filtered.length})</span></h2><p>Confirmed molecules in this run</p></div></div>
        <label className="list-search"><Search size={16} /><input id="structure-search" value={search} onChange={(event) => onSearch(event.target.value)} placeholder="Search structures" aria-label="Search structures" /></label>
        <div className="molecule-rows">{filtered.map((molecule) => <button key={molecule.id}
          className={`molecule-row molecule-row--${molecule.status} ${selected.id === molecule.id ? "molecule-row--selected" : ""}`}
          onClick={() => { onSelect(molecule.id); setIssueTip(false); setZoom(1); }} aria-pressed={selected.id === molecule.id}>
          <span className="row-thumbnail"><Molecule2D molecule={molecule} compact /></span>
          <span className="row-info"><strong>{molecule.label}</strong><small>{molecule.formula ?? "Formula blocked"}</small>
            <em>{molecule.source}</em><MoleculeStatusBadge status={molecule.status} /></span>
        </button>)}{filtered.length === 0 && <p className="list-empty">No structures match that search.</p>}</div>
        <button className="list-add" onClick={onAddSource}><Plus size={16} /> Add source</button>
      </div>

      <div className="viewer-panel panel">
        <div className="viewer-heading"><div><h2>Molecular view</h2><p>{selected.label} · {view === "3d" ? "SMILES connectivity · illustrative 3D layout" : "RDKit 2D depiction"}</p></div>
          <div className="view-switch" role="group" aria-label="View dimension">
            <button className={view === "2d" ? "active" : ""} onClick={() => setView("2d")}>2D view</button>
            <button className={view === "3d" ? "active" : ""} onClick={() => setView("3d")}>3D sketch</button>
          </div>
        </div>
        <div className="viewer-options">
          {view === "3d" ? <>
            <label className="toggle-label">Atom labels <input type="checkbox" checked={showLabels} onChange={(event) => setShowLabels(event.target.checked)} /><span className="toggle-track" /></label>
            <label className="toggle-label">Autorotate <input type="checkbox" checked={autorotate} onChange={(event) => setAutorotate(event.target.checked)} /><span className="toggle-track" /></label>
          </> : <span className="viewer-mode-note">Evidence-backed 2D depiction</span>}
        </div>
        <div className={`viewer-canvas ${view === "3d" ? "viewer-canvas--3d" : "viewer-canvas--2d"}`}>
          {view === "2d"
            ? selected.manifest.mode === "live"
              ? <LiveMoleculeSvg svg={selected.depictionSvg} />
              : <Molecule2D molecule={selected} zoom={zoom} onIssueClick={() => setIssueTip((current) => !current)} />
            : <Molecule3D
                key={selected.id}
                smiles={selected.smiles}
                label={selected.label}
                autorotate={autorotate}
                showLabels={showLabels}
                highlightedAtoms={selected.issue?.atomIndex === undefined ? [] : [selected.issue.atomIndex]}
                resetSignal={resetSignal}
                zoom={zoom}
              />}
          {view === "2d" && selected.status === "invalid" && issueTip && <span className="atom-tooltip">Oxygen atom 7: impossible valence</span>}
          {view === "3d" && <span className="viewer-watermark">Illustrative coordinates · connectivity comes from SMILES</span>}
        </div>
        <div className="viewer-toolbar"><div className="zoom-control"><button onClick={() => changeZoom(-1)} aria-label="Zoom out"><Minus size={17} /></button><span>{Math.round(zoom * 100)}%</span><button onClick={() => changeZoom(1)} aria-label="Zoom in"><Plus size={17} /></button></div>
          <button onClick={() => setFullScreen((current) => !current)}><Maximize2 size={17} /> {fullScreen ? "Exit fullscreen" : "Expand"}</button>
          <button onClick={onEdit}><Pencil size={17} /> Edit structure</button>
          <button onClick={() => { setZoom(1); setResetSignal((current) => current + 1); }}><RotateCcw size={17} /> Reset camera</button>
        </div>
      </div>

      <div className="diagnostic-panel panel">
        <div className="panel-heading diagnostic-heading"><div><h2>Diagnostic</h2><p>Interpretation and next step</p></div><MoleculeStatusBadge status={selected.status} compact /></div>
        <div className={`diagnostic-summary diagnostic-summary--${selected.status}`}><span className="diagnostic-icon">
          {selected.status === "valid" ? <CheckCircle2 size={23} /> : <AlertCircle size={23} />}</span><div>
          <strong>{selected.issue?.title ?? "No blocking issue detected"}</strong>
          <p>{selected.issue?.explanation ?? "The example notation is presented as valid. Live validation is required for a verified scientific result."}</p>
        </div></div>
        <div className="diagnostic-block"><h3>Why this matters</h3><p>{selected.issue?.whyItMatters ?? "A valid graph is a prerequisite for descriptors. Frozen reference evidence requires a configured snapshot."}</p></div>
        <div className="next-step"><BookOpen size={19} /><div><strong>Next step</strong><p>{selected.issue?.nextStep ?? "Review the source and standardization record before interpreting values."}</p>
          <button onClick={onReviewSource}>Review source <ArrowRight size={15} /></button></div></div>
        <div className="source-reference"><FileText size={19} /><div><strong>Source reference</strong><p>{selected.source}</p><span>{selected.manifest.mode === "demo" ? "Illustrative source excerpt" : "Recorded input metadata"}</span></div></div>
      </div>
    </section>

    <section className="audit-panel panel">
      <div className="audit-tabs" role="tablist" aria-label="Audit details">{tabs.map((item) => <button key={item.id} role="tab" aria-selected={tab === item.id}
        className={tab === item.id ? "audit-tab--active" : ""} onClick={() => setTab(item.id)}>{item.label}</button>)}</div>
      <div className="audit-body">
        {tab === "validation" && <CompareTable molecules={molecules} brief={step !== "compare"} />}
        {tab === "properties" && <><div className="audit-intro"><div><h2>{selected.label} property audit</h2><p>Invalid inputs display an explicit “Not computed” result.</p></div><span className="snapshot-pill">{selected.manifest.snapshotId}</span></div>
          <div className="table-scroll"><table className="property-table"><thead><tr><th>Property</th><th>Computed</th><th>Frozen evidence</th><th>Status</th></tr></thead><tbody>
            {selected.descriptors.map((record) => <tr key={record.key}><th scope="row">{record.label}</th><td>{record.value === null ? "—" : `${record.value}${record.unit ? ` ${record.unit}` : ""}`}</td><td className="table-muted">{record.reference ?? "—"}</td><td><EvidenceStatusBadge status={record.status} /></td></tr>)}
          </tbody></table></div></>}
        {tab === "standardization" && <div className="detail-layout"><div><h2>Standardization record</h2><p>Every transformation is listed, with the raw input preserved.</p>
          {selected.steps.length ? <ol className="step-records">{selected.steps.map((record) => <li key={record.code}><strong>{record.label}</strong><span>{record.changed ? "Changed" : "No change"}</span><code>{record.before} → {record.after}</code></li>)}</ol>
            : <p className="empty-detail">No standardization was attempted because the input is invalid.</p>}</div><div className="detail-note"><strong>Submitted SMILES</strong><code>{selected.smiles}</code></div></div>}
        {tab === "evidence" && <div className="detail-layout"><div><h2>Reference evidence</h2><p>The small bootstrap demo dataset is not ChEMBL 37. Outside coverage here says nothing about full ChEMBL.</p>
          <div className="evidence-details">{selected.descriptors.slice(0, 4).map((record) => <div key={record.key}><strong>{record.label}</strong><EvidenceStatusBadge status={record.status} /><p>{record.reason}</p></div>)}</div></div>
          <div className="detail-note"><strong>Snapshot ID</strong><code>{selected.manifest.snapshotId}</code><small>Actual ChEMBL snapshot: not configured</small></div></div>}
        {tab === "provenance" && <div className="detail-layout"><div><h2>Provenance manifest</h2><p>{selected.manifest.mode === "demo" ? "Demo hashes and RDKit version are intentionally not fabricated." : "Hashes and toolkit version returned by the live RDKit service."}</p>
          <dl className="manifest-list"><div><dt>Input SHA-256</dt><dd>{selected.manifest.inputSha256 ?? "Not generated for demo"}</dd></div><div><dt>Output SHA-256</dt><dd>{selected.manifest.outputSha256 ?? "Not generated for demo"}</dd></div><div><dt>RDKit version</dt><dd>{selected.manifest.rdkitVersion ?? "Not run for demo"}</dd></div></dl></div>
          <div className="detail-note"><strong>Analysis ID</strong><code>{selected.manifest.analysisId}</code><strong>Snapshot ID</strong><code>{selected.manifest.snapshotId}</code></div></div>}
      </div>
    </section>
  </>;
}
