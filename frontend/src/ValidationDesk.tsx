import { lazy, Suspense, useState } from "react";
import { AlertCircle, ArrowRight, BookOpen, CheckCircle2, FileText, Maximize2, Minus,
  Pencil, Plus, RotateCcw, Search } from "lucide-react";
import type { AuditTab, MoleculeCandidate, StepId, ViewerStyle } from "./domain";
import { Molecule2D } from "./Molecule2D";
import { LiveMoleculeSvg } from "./LiveMoleculeSvg";
import { CompareTable } from "./CompareTable";
import { EvidenceStatusBadge, MoleculeStatusBadge } from "./StatusBadge";

const Molecule3D = lazy(() => import("./Molecule3D"));
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
  const [style, setStyle] = useState<ViewerStyle>("ball-stick");
  const [autorotate, setAutorotate] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [resetSignal, setResetSignal] = useState(0);
  const [fullScreen, setFullScreen] = useState(false);
  const [issueTip, setIssueTip] = useState(false);
  const effectiveView = selected.manifest.mode === "live" ? "2d" : view;

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
        <div className="viewer-heading"><div><h2>3-D Molecular View</h2><p>{selected.label} · {selected.manifest.mode === "demo" ? "illustrative geometry" : "RDKit 2D depiction"}</p></div>
          <div className="view-switch" role="group" aria-label="View dimension">
            <button className={effectiveView === "2d" ? "active" : ""} onClick={() => setView("2d")}>2D view</button>
            <button className={effectiveView === "3d" ? "active" : ""} onClick={() => setView("3d")}
              disabled={selected.manifest.mode === "live"} title={selected.manifest.mode === "live" ? "No verified 3D conformer is available" : undefined}>3D View</button>
          </div>
        </div>
        <div className="viewer-options"><label>Style <span className="select-wrap"><select value={style} onChange={(event) => setStyle(event.target.value as ViewerStyle)} disabled={effectiveView === "2d"}>
          <option value="ball-stick">Ball & Stick</option><option value="space-filling">Space-filling</option><option value="wireframe">Wireframe</option>
        </select></span></label><label className="toggle-label">Autorotate <input type="checkbox" checked={autorotate} onChange={(event) => setAutorotate(event.target.checked)} disabled={effectiveView === "2d"} /><span className="toggle-track" /></label></div>
        <div className={`viewer-canvas ${effectiveView === "3d" ? "viewer-canvas--dark" : "viewer-canvas--2d"}`}>
          {selected.manifest.mode === "live" ? <LiveMoleculeSvg svg={selected.depictionSvg} />
            : effectiveView === "2d" ? <Molecule2D molecule={selected} zoom={zoom} onIssueClick={() => setIssueTip((current) => !current)} />
              : <Suspense fallback={<div className="viewer-loading">Loading interactive 3D viewer…</div>}>
                <Molecule3D key={selected.id} moleculeId={selected.id} style={style} autorotate={autorotate}
                  highlightedAtom={selected.issue?.severity === "error" ? selected.issue.atomIndex : undefined}
                  resetSignal={resetSignal} zoom={zoom} />
              </Suspense>}
          {effectiveView === "2d" && selected.status === "invalid" && issueTip && <span className="atom-tooltip">Oxygen atom 7: impossible valence</span>}
          {effectiveView === "3d" && <span className="viewer-watermark">Illustrative coordinates · not an optimized conformer</span>}
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
