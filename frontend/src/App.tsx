import { useMemo, useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";
import { AlertCircle, ArrowRight, Atom, Check, ChevronRight, CircleHelp, Download, Expand,
  FileImage, FileText, FlaskConical, Home, Pencil, Search, ShieldCheck, UploadCloud,
  UserRound, X } from "lucide-react";
import { analyzeMolecule } from "./api/analysis";
import { DEMO_MOLECULES } from "./demoData";
import type { MoleculeCandidate, StepId } from "./domain";
import { fromApi } from "./live";
import { Molecule2D } from "./Molecule2D";
import { MoleculeStatusBadge } from "./StatusBadge";
import { ValidationDesk } from "./ValidationDesk";
import { RunRecordDialog } from "./RunRecordDialog";
import { SourceReviewDialog } from "./SourceReviewDialog";
import { createRunRecord } from "./runRecord";

const steps: { id: StepId; label: string; detail: string }[] = [
  { id: "source", label: "Source", detail: "Upload or paste" },
  { id: "confirm", label: "Confirm", detail: "Candidate triage" },
  { id: "validate", label: "Validate", detail: "Inspect structure" },
  { id: "compare", label: "Compare", detail: "Batch audit" },
  { id: "report", label: "Report", detail: "Manifest & export" },
];
const inputModes = ["Paper or PDF", "Photo or screenshot", "Draw molecule", "Structure data (SMILES/MOL)"] as const;
type InputMode = typeof inputModes[number];

export default function App() {
  const [step, setStep] = useState<StepId>("validate");
  const [molecules, setMolecules] = useState<MoleculeCandidate[]>(DEMO_MOLECULES);
  const [selectedId, setSelectedId] = useState("source-row-14");
  const recordDialogRef = useRef<HTMLDialogElement>(null);
  const sourceDialogRef = useRef<HTMLDialogElement>(null);
  const [mode, setMode] = useState<InputMode>("Structure data (SMILES/MOL)");
  const [draftLabel, setDraftLabel] = useState("");
  const [draftSmiles, setDraftSmiles] = useState("");
  const [draftDemoId, setDraftDemoId] = useState<string | null>(null);
  const [confirmError, setConfirmError] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [search, setSearch] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const [fileHash, setFileHash] = useState<string | null>(null);
  const [fileError, setFileError] = useState("");
  const selected = molecules.find((item) => item.id === selectedId) ?? molecules[0] ?? null;
  const filtered = useMemo(() => molecules.filter((item) => `${item.label} ${item.smiles}`.toLowerCase().includes(search.toLowerCase())), [molecules, search]);
  const validCount = molecules.filter((item) => item.status !== "invalid").length;
  const runId = molecules.find((item) => item.manifest.mode === "live")?.manifest.analysisId ?? "PL-2026-0042 · DEMO";
  const runRecord = createRunRecord(runId, molecules);
  const activeDemo = DEMO_MOLECULES.find((item) => item.id === draftDemoId);

  async function chooseFile(next?: File) {
    if (!next) return;
    if (next.size > 5 * 1024 * 1024) { setFileError("Choose a file smaller than 5 MB."); return; }
    if (!/\.(csv|pdf|png|jpe?g|webp)$/i.test(next.name)) { setFileError("Choose a PDF, PNG, JPEG, WebP, or CSV file."); return; }
    if (fileUrl) URL.revokeObjectURL(fileUrl);
    setFile(next); setFileUrl(URL.createObjectURL(next)); setFileError(""); setDraftDemoId(null); setFileHash(null);
    try {
      const digest = await crypto.subtle.digest("SHA-256", await next.arrayBuffer());
      setFileHash(Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join(""));
    } catch {
      setFileError("This file could not be hashed. Choose it again before confirming.");
    }
  }
  function startDemo(candidate: MoleculeCandidate) {
    setDraftDemoId(candidate.id); setDraftLabel(candidate.label); setDraftSmiles(candidate.smiles); setConfirmError(""); setStep("confirm");
  }
  async function confirmCandidate() {
    if (!draftSmiles.trim()) { setConfirmError("Enter a SMILES string before confirming."); return; }
    if (file && !fileHash) { setConfirmError("Wait for the source file hash before confirming."); return; }
    setConfirmError("");
    if (activeDemo && !file && draftSmiles.trim() === activeDemo.smiles) {
      setSelectedId(activeDemo.id); setStep("validate"); return;
    }
    setConfirming(true);
    try {
      const result = await analyzeMolecule({ structure: draftSmiles.trim(), label: draftLabel.trim() || undefined,
        source: file && fileHash ? { source_type: file.type === "application/pdf" ? "paper" : file.type.startsWith("image/") ? "photo" : "csv",
          filename: file.name, media_type: file.type, file_size: file.size, file_sha256: fileHash,
          extraction_method: "manual-smiles-transcription" } : { source_type: "direct-smiles" } });
      const candidate = fromApi(result);
      setMolecules((current) => [...current.filter((item) => item.id !== candidate.id), candidate]);
      setSelectedId(candidate.id); setStep("validate");
    } catch (error) {
      setConfirmError(error instanceof Error ? `${error.message}. Start the FastAPI service for live analysis.` : "Analysis failed. Start the FastAPI service for live analysis.");
    } finally { setConfirming(false); }
  }
  function downloadRun() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(runRecord, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `${runId.toLowerCase()}-record.json`; anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function rejectReviewedCandidate() {
    if (!selected) return;
    const remaining = molecules.filter((item) => item.id !== selected.id);
    setMolecules(remaining);
    setSelectedId(remaining[0]?.id ?? "");
    sourceDialogRef.current?.close();
    if (remaining.length === 0) setStep("source");
  }
  function editReviewedCandidate() {
    if (!selected) return;
    setDraftLabel(selected.label);
    setDraftSmiles(selected.smiles);
    setDraftDemoId(null);
    sourceDialogRef.current?.close();
    setStep("source");
  }

  return <div className="app-frame">
    <header className="topbar">
      <button className="brand" onClick={() => setStep("validate")} aria-label="ProvenanceLab home"><span className="brand-mark"><Atom size={21} strokeWidth={1.8} /></span><span>Provenance<span className="brand-accent">Lab</span></span></button>
      <nav className="topnav" aria-label="Main navigation"><button onClick={() => setStep("source")}>New analysis</button><button onClick={() => setStep("validate")}>Runs</button><button onClick={() => document.getElementById("about-dialog")?.showPopover()}>About</button></nav>
      <div className="topbar-right"><span className="run-chip">RUN {runId}</span><span className="header-divider" /><button className="icon-button" onClick={() => { setStep("validate"); window.setTimeout(() => document.getElementById("structure-search")?.focus(), 0); }} aria-label="Search structures"><Search size={18} /></button><button className="avatar" aria-label="Demo profile"><UserRound size={17} /></button></div>
    </header>
    <div id="about-dialog" popover="auto" className="about-popover"><strong>About ProvenanceLab</strong><p>A molecular audit workspace. Demo records are illustrative; live calculations require the FastAPI and RDKit service.</p></div>
    <div className="workspace-layout"><aside className="step-rail" aria-label="Analysis steps"><div className="rail-caption">WORKFLOW</div>{steps.map((item, index) => <button key={item.id} className={`step-item ${step === item.id ? "step-item--active" : ""}`} onClick={() => setStep(item.id)} aria-current={step === item.id ? "step" : undefined}><span className="step-number">{index + 1}</span><span className="step-text"><strong>{item.label}</strong><small>{item.detail}</small></span></button>)}<div className="rail-help"><CircleHelp size={18} /><span>Need help?<small>Scientific method guide</small></span></div></aside>
      <main className="main-content"><div className="page-heading"><div><p className="breadcrumb"><Home size={14} /> Workspace <ChevronRight size={13} /> {steps.find((item) => item.id === step)?.label}</p><h1>{step === "source" ? "Add a molecular source" : step === "confirm" ? "Confirm a candidate" : step === "compare" ? "Compare structures" : step === "report" ? "Run report" : "Validation complete"}</h1><p className="page-description">{step === "validate" ? "Two structures are ready to compare. One needs attention before properties can be calculated." : step === "source" ? "Choose a source and transcribe a structure. No image or document is interpreted automatically." : step === "confirm" ? "A human decision is required before a candidate enters the analysis workspace." : step === "compare" ? "Compare calculated values while keeping reference coverage explicit." : "Review the provenance record and export the run."}</p></div><div className="demo-notice"><FlaskConical size={18} /><div><strong>Demonstration data</strong><span>Three example compounds are illustrative. Live results require RDKit.</span></div></div></div>
      {step === "source" && <section className="source-screen"><div className="section-head"><div><h2>Source ingestion</h2><p>Start with an example or provide your own source.</p></div><span className="section-kicker">01 / SOURCE</span></div><div className="input-tabs" role="tablist" aria-label="Input source">{inputModes.map((item) => <button key={item} role="tab" aria-selected={mode === item} className={mode === item ? "input-tab--active" : ""} onClick={() => setMode(item)}>{item}</button>)}</div><div className="source-grid"><div className="source-entry"><label className="dropzone" onDragOver={(event: DragEvent<HTMLLabelElement>) => event.preventDefault()} onDrop={(event: DragEvent<HTMLLabelElement>) => { event.preventDefault(); void chooseFile(event.dataTransfer.files[0]); }}><input type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.csv" onChange={(event: ChangeEvent<HTMLInputElement>) => { void chooseFile(event.target.files?.[0]); event.target.value = ""; }} /><UploadCloud size={30} strokeWidth={1.5} /><strong>{file ? file.name : "Drop a PDF, screenshot, or CSV here"}</strong><span>{file ? "File stays in this browser. Only SHA-256 metadata is sent with live analysis." : "Or click to browse · PDF, PNG, JPEG, WebP, CSV · up to 5 MB"}</span></label>{fileError && <p className="form-error" role="alert">{fileError}</p>}{mode === "Draw molecule" && <p className="capability-note"><Pencil size={16} /> A drawing editor is not connected. Enter a SMILES transcription below.</p>}{mode === "Structure data (SMILES/MOL)" && <p className="capability-note"><FileText size={16} /> Live analysis accepts SMILES. MOL parsing is not connected yet.</p>}<div className="source-fields"><label>Molecule label<input value={draftLabel} onChange={(event) => { setDraftLabel(event.target.value); setDraftDemoId(null); }} placeholder="e.g. Compound 7b" /></label><label>SMILES transcription<textarea value={draftSmiles} onChange={(event) => { setDraftSmiles(event.target.value); setDraftDemoId(null); }} rows={3} placeholder="Paste or type a SMILES string" /></label><p>Transcription is untrusted until confirmed. Invalidity and ambiguity are never silently repaired.</p><button className="button button--primary" onClick={() => { setConfirmError(""); setStep("confirm"); }}>Review candidate <ArrowRight size={16} /></button></div></div><div className="example-list"><div className="example-head"><h3>Try an example</h3><p>Preloaded for a clickable demonstration</p></div>{DEMO_MOLECULES.map((item) => <button className="example-row" key={item.id} onClick={() => startDemo(item)}><span className="example-symbol"><Molecule2D molecule={item} compact /></span><span><strong>{item.label}</strong><small>{item.smiles}</small></span><MoleculeStatusBadge status={item.status} compact /><ChevronRight size={16} /></button>)}</div></div></section>}
      {step === "confirm" && <section className="confirmation-screen"><div className="section-head"><div><h2>Source and candidate</h2><p>Check the transcription against the source before analysis.</p></div><span className="section-kicker">02 / CONFIRM</span></div><div className="confirm-grid"><div className="source-preview"><div className="panel-title"><FileImage size={17} /><strong>Source document</strong><span>{file?.name ?? "Demo source"}</span></div><div className="document-surface">{fileUrl && file?.type.startsWith("image/") ? <img src={fileUrl} alt="Uploaded molecular source" /> : fileUrl && file?.type === "application/pdf" ? <iframe src={fileUrl} title="Uploaded PDF source" /> : <div className="demo-document"><span>ILLUSTRATIVE SOURCE EXCERPT</span><h3>{activeDemo?.label ?? "Your source"}</h3><p>Figure 2 · Molecular notation supplied for student review</p>{activeDemo ? <Molecule2D molecule={activeDemo} /> : <FileText size={74} strokeWidth={1} />}<small>{file ? "Preview unavailable for this file type. Review the original locally." : "Mock document crop, not an extracted paper."}</small></div>}</div></div><div className="candidate-card"><div className="panel-title"><Atom size={18} /><strong>Untrusted candidate</strong><span className="untrusted-pill">Requires confirmation</span></div><div className="candidate-visual">{activeDemo && draftSmiles.trim() === activeDemo.smiles ? <Molecule2D molecule={activeDemo} /> : <div className="unrendered"><Atom size={48} strokeWidth={1} /><strong>Structure not rendered yet</strong><p>Only the RDKit service can verify and depict custom input.</p></div>}</div><div className="candidate-facts"><div><span>Label</span><strong>{draftLabel || "Untitled molecule"}</strong></div><div><span>Formula</span><strong>{activeDemo?.formula ?? "Unverified"}</strong></div><div><span>Weight</span><strong>{activeDemo?.weight ? `${activeDemo.weight} g/mol` : "Unverified"}</strong></div><div className="candidate-smiles"><span>Submitted SMILES</span><code>{draftSmiles || "No transcription entered"}</code></div></div><p className="candidate-warning"><AlertCircle size={17} /> {activeDemo ? "Demo values are illustrative and have no RDKit manifest." : "Custom structures are analyzed only after confirmation."}</p><div className="candidate-actions"><button className="button button--primary" disabled={confirming} onClick={() => void confirmCandidate()}><Check size={17} />{confirming ? "Analyzing…" : "Confirm structure"}</button><button className="button button--quiet" onClick={() => setStep("source")}><Pencil size={17} /> Edit structure</button><button className="button button--danger" onClick={() => { setDraftSmiles(""); setDraftDemoId(null); setStep("source"); }}><X size={16} /> Reject candidate</button></div>{confirmError && <p className="form-error" role="alert">{confirmError}</p>}</div></div></section>}
      {(step === "validate" || step === "compare") && (selected
        ? <ValidationDesk step={step} molecules={molecules} selected={selected} filtered={filtered}
            search={search} onSearch={setSearch} onSelect={setSelectedId}
            onAddSource={() => setStep("source")} onEdit={editReviewedCandidate}
            onReviewSource={() => sourceDialogRef.current?.showModal()} />
        : <div className="empty-run panel"><strong>No structures remain in this run.</strong><button className="button button--primary" onClick={() => setStep("source")}>Add a source</button></div>)}
      {step === "report" && <section className="report-screen panel"><div className="report-heading"><ShieldCheck size={26} /><div><h2>Run record</h2><p>{molecules.length} structures · {validCount} with computable properties · {molecules.length - validCount} invalid</p></div></div><div className="report-grid"><div><strong>Run ID</strong><code>{runId}</code></div><div><strong>Reference snapshot</strong><code>{selected?.manifest.snapshotId ?? "No active record"}</code></div><div><strong>Verified backend records</strong><span>{molecules.filter((item) => item.manifest.mode === "live").length}</span></div><div><strong>Illustrative records</strong><span>{molecules.filter((item) => item.manifest.mode === "demo").length}</span></div></div><p className="report-caveat">The JSON export includes real hashes only for live RDKit analyses. Demo records retain null hashes and version fields. Source files remain in your browser; only metadata may accompany live analyses.</p><button className="button button--primary" onClick={() => recordDialogRef.current?.showModal()}><Download size={17} /> Download run record</button></section>}
      </main></div>
    <RunRecordDialog dialogRef={recordDialogRef} record={runRecord} onDownload={downloadRun} />
    {selected && <SourceReviewDialog dialogRef={sourceDialogRef} molecule={selected}
      sourceUrl={fileUrl} sourceFile={file} sourceHash={fileHash} onReject={rejectReviewedCandidate}
      onEdit={editReviewedCandidate} onConfirm={() => sourceDialogRef.current?.close()} />}
    <footer className="footer-bar"><p><ShieldCheck size={16} /> Source files stay in your browser. Every live transformation is logged.</p><div><button className="button button--outline" onClick={() => recordDialogRef.current?.showModal()}><Download size={16} /> Download run record</button><button className="button button--primary" onClick={() => setStep("compare")}><Expand size={16} /> Compare valid structures ({validCount})</button></div></footer>
  </div>;
}
