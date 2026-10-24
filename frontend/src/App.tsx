import { useMemo, useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";
import {
  AlertCircle,
  ArrowRight,
  Atom,
  Check,
  ChevronRight,
  CircleHelp,
  Download,
  FileImage,
  Home,
  LoaderCircle,
  Pencil,
  ScanLine,
  Search,
  ShieldCheck,
  UploadCloud,
  X,
} from "lucide-react";

import {
  analyzeMolecule,
  createAnalysisRun,
  downloadRunReport,
  extractMoleculeImage,
} from "./api/analysis";
import type { MoleculeCandidate, StepId } from "./domain";
import { LiveMoleculeSvg } from "./LiveMoleculeSvg";
import { fromApi } from "./live";
import type {
  AnalyzeRequest,
  AnalyzeResponse,
  ImageExtractionResponse,
  RunResponse,
} from "./schemas/analysis";
import { SourceReviewDialog } from "./SourceReviewDialog";
import { MoleculeStatusBadge } from "./StatusBadge";
import { ValidationDesk } from "./ValidationDesk";

const steps: { id: StepId; label: string; detail: string }[] = [
  { id: "source", label: "Source", detail: "Upload or paste" },
  { id: "confirm", label: "Confirm", detail: "Candidate triage" },
  { id: "validate", label: "Validate", detail: "Inspect structure" },
  { id: "compare", label: "Compare", detail: "Batch audit" },
  { id: "report", label: "Report", detail: "PDF export" },
];

const inputModes = [
  { id: "paper", label: "Paper or PDF" },
  { id: "photo", label: "Photo or screenshot" },
  { id: "smiles", label: "SMILES" },
] as const;

type InputMode = (typeof inputModes)[number]["id"];
type BrowserSource = { file: File; url: string };

function propertyValue(preview: AnalyzeResponse | null, key: string): string {
  const observation = preview?.properties.find((property) => property.key === key)?.computed;
  if (!observation || observation.value === null) return "Not computed";
  return `${observation.value}${observation.unit ? ` ${observation.unit}` : ""}`;
}

export default function App() {
  const [step, setStep] = useState<StepId>("source");
  const [run, setRun] = useState<RunResponse | null>(null);
  const [runInputs, setRunInputs] = useState<AnalyzeRequest[]>([]);
  const [molecules, setMolecules] = useState<MoleculeCandidate[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [mode, setMode] = useState<InputMode>("smiles");
  const [draftLabel, setDraftLabel] = useState("");
  const [draftSmiles, setDraftSmiles] = useState("");
  const [draftPage, setDraftPage] = useState("");
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [preview, setPreview] = useState<AnalyzeResponse | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [actionError, setActionError] = useState("");
  const [search, setSearch] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const [fileHash, setFileHash] = useState<string | null>(null);
  const [fileError, setFileError] = useState("");
  const [extracting, setExtracting] = useState(false);
  const [imageExtraction, setImageExtraction] = useState<ImageExtractionResponse | null>(null);
  const [extractionMethod, setExtractionMethod] = useState<string | null>(null);
  const [sourceFiles, setSourceFiles] = useState<Record<string, BrowserSource>>({});
  const sourceDialogRef = useRef<HTMLDialogElement>(null);
  const fileRequestRef = useRef(0);

  const selected = molecules.find((item) => item.id === selectedId) ?? molecules[0] ?? null;
  const filtered = useMemo(
    () => molecules.filter((item) => `${item.label} ${item.smiles}`.toLowerCase().includes(search.toLowerCase())),
    [molecules, search],
  );
  const validCount = molecules.filter((item) => item.status !== "invalid").length;
  const invalidCount = molecules.length - validCount;
  const selectedSource = selected?.sourceFileSha256 ? sourceFiles[selected.sourceFileSha256] : undefined;

  function clearDraft() {
    fileRequestRef.current += 1;
    setDraftLabel("");
    setDraftSmiles("");
    setDraftPage("");
    setEditingIndex(null);
    setPreview(null);
    setFile(null);
    setFileUrl(null);
    setFileHash(null);
    setFileError("");
    setExtracting(false);
    setImageExtraction(null);
    setExtractionMethod(null);
    setActionError("");
    setMode("smiles");
  }

  function startNewAnalysis() {
    Object.values(sourceFiles).forEach((source) => URL.revokeObjectURL(source.url));
    setSourceFiles({});
    setRun(null);
    setRunInputs([]);
    setMolecules([]);
    setSelectedId("");
    setSearch("");
    clearDraft();
    setStep("source");
  }

  function changeMode(next: InputMode) {
    fileRequestRef.current += 1;
    setMode(next);
    setFile(null);
    setFileUrl(null);
    setFileHash(null);
    setFileError("");
    setExtracting(false);
    setImageExtraction(null);
    setExtractionMethod(null);
    setPreview(null);
  }

  async function chooseFile(next?: File) {
    if (!next) return;
    const requestId = ++fileRequestRef.current;
    const isPaper = mode === "paper";
    const accepted = isPaper
      ? next.type === "application/pdf" || /\.pdf$/i.test(next.name)
      : ["image/png", "image/jpeg", "image/webp"].includes(next.type);
    if (!accepted) {
      setFileError(isPaper ? "Choose a PDF file." : "Choose a PNG, JPEG, or WebP image.");
      return;
    }
    if (next.size > 5 * 1024 * 1024) {
      setFileError("Choose a file smaller than 5 MB.");
      return;
    }
    const url = URL.createObjectURL(next);
    setFile(next);
    setFileUrl(url);
    setFileError("");
    setFileHash(null);
    setImageExtraction(null);
    setExtractionMethod(isPaper ? "manual-smiles-transcription" : null);
    if (!isPaper) {
      setDraftSmiles("");
      setExtracting(true);
    }
    try {
      const extractionPromise = isPaper ? null : extractMoleculeImage(next);
      const digest = await crypto.subtle.digest("SHA-256", await next.arrayBuffer());
      const hash = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
      if (requestId !== fileRequestRef.current) return;
      setFileHash(hash);
      setSourceFiles((current) => ({ ...current, [hash]: { file: next, url } }));
      if (extractionPromise) {
        try {
          const extraction = await extractionPromise;
          if (requestId !== fileRequestRef.current) return;
          if (extraction.source_sha256 !== hash) {
            throw new Error("SOURCE_HASH_MISMATCH: the uploaded image changed during extraction.");
          }
          setImageExtraction(extraction);
          setExtractionMethod(`${extraction.method} ${extraction.model_version}`);
          setDraftSmiles(extraction.candidate_smiles);
        } catch (error) {
          if (requestId !== fileRequestRef.current) return;
          setFileError(error instanceof Error ? error.message : "DECIMER could not transcribe this image.");
        } finally {
          if (requestId === fileRequestRef.current) setExtracting(false);
        }
      }
    } catch {
      if (requestId !== fileRequestRef.current) return;
      URL.revokeObjectURL(url);
      setFile(null);
      setFileUrl(null);
      setExtracting(false);
      setFileError("This file could not be hashed. Choose it again before continuing.");
    }
  }

  function buildDraftRequest(): AnalyzeRequest | null {
    const structure = draftSmiles.trim();
    if (!structure) {
      setActionError("Enter a SMILES string before reviewing the candidate.");
      return null;
    }
    if (mode !== "smiles" && (!file || !fileHash)) {
      setActionError(`Choose and finish hashing the ${mode === "paper" ? "PDF" : "image"} source first.`);
      return null;
    }
    const label = draftLabel.trim() || undefined;
    if (mode === "smiles") {
      return { structure, label, source: { source_type: "direct-smiles" } };
    }
    return {
      structure,
      label,
      source: {
        source_type: mode,
        filename: file?.name,
        media_type: file?.type,
        file_size: file?.size,
        file_sha256: fileHash ?? undefined,
        extraction_method: extractionMethod ?? "manual-smiles-transcription",
        page: mode === "paper" && draftPage ? Number(draftPage) : undefined,
      },
    };
  }

  async function reviewCandidate() {
    const request = buildDraftRequest();
    if (!request) return;
    setReviewing(true);
    setActionError("");
    try {
      setPreview(await analyzeMolecule(request));
      setStep("confirm");
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "The chemistry service could not review this input.");
    } finally {
      setReviewing(false);
    }
  }

  async function confirmCandidate() {
    const request = buildDraftRequest();
    if (!request) return;
    const nextInputs = editingIndex === null
      ? [...runInputs, request]
      : runInputs.map((item, index) => index === editingIndex ? request : item);
    setConfirming(true);
    setActionError("");
    try {
      const nextRun = await createAnalysisRun(nextInputs);
      const nextMolecules = nextRun.results.map((result, index) => fromApi(result, index));
      const selectedIndex = editingIndex ?? nextMolecules.length - 1;
      setRun(nextRun);
      setRunInputs(nextInputs);
      setMolecules(nextMolecules);
      setSelectedId(nextMolecules[selectedIndex]?.id ?? nextMolecules[0]?.id ?? "");
      clearDraft();
      setStep("validate");
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "The run could not be saved.");
    } finally {
      setConfirming(false);
    }
  }

  async function rejectReviewedCandidate() {
    if (!selected) return;
    const nextInputs = runInputs.filter((_, index) => index !== selected.inputIndex);
    sourceDialogRef.current?.close();
    if (!nextInputs.length) {
      setRun(null);
      setRunInputs([]);
      setMolecules([]);
      setSelectedId("");
      setStep("source");
      return;
    }
    setActionError("");
    try {
      const nextRun = await createAnalysisRun(nextInputs);
      const nextMolecules = nextRun.results.map((result, index) => fromApi(result, index));
      setRun(nextRun);
      setRunInputs(nextInputs);
      setMolecules(nextMolecules);
      setSelectedId(nextMolecules[Math.min(selected.inputIndex, nextMolecules.length - 1)].id);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "The structure could not be removed.");
    }
  }

  function editReviewedCandidate() {
    if (!selected) return;
    const request = runInputs[selected.inputIndex];
    const sourceType = request.source?.source_type;
    setEditingIndex(selected.inputIndex);
    setDraftLabel(request.label ?? "");
    setDraftSmiles(request.structure);
    setDraftPage(request.source?.page?.toString() ?? "");
    setMode(sourceType === "paper" || sourceType === "photo" ? sourceType : "smiles");
    setFile(selectedSource?.file ?? null);
    setFileUrl(selectedSource?.url ?? null);
    setFileHash(request.source?.file_sha256 ?? null);
    setExtractionMethod(request.source?.extraction_method ?? null);
    setImageExtraction(null);
    setExtracting(false);
    setPreview(null);
    setActionError("");
    sourceDialogRef.current?.close();
    setStep("source");
  }

  async function downloadPdf() {
    if (!run) return;
    setDownloading(true);
    setActionError("");
    try {
      await downloadRunReport(run.run_id);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "The PDF report could not be downloaded.");
    } finally {
      setDownloading(false);
    }
  }

  const pageTitle = step === "source" ? "Add a molecular source"
    : step === "confirm" ? "Confirm a candidate"
      : step === "compare" ? "Compare structures"
        : step === "report" ? "Run report"
          : molecules.length ? "Validation complete" : "No active run";
  const pageDescription = step === "source"
    ? "Choose one source type. File controls appear only when that source requires a file."
    : step === "confirm" ? "Review the real RDKit result before adding it to the run."
      : step === "compare" ? "Compare calculated values while keeping missing reference evidence explicit."
        : step === "report" ? "Export the complete validation and provenance record as a PDF."
          : molecules.length
            ? `${molecules.length} structure${molecules.length === 1 ? "" : "s"} analyzed; ${validCount} computable and ${invalidCount} invalid.`
            : "Start with a SMILES string, image, or PDF source.";

  return <div className="app-frame">
    <header className="topbar">
      <button className="brand" onClick={() => setStep(molecules.length ? "validate" : "source")} aria-label="ProvenanceLab home"><span className="brand-mark"><Atom size={21} strokeWidth={1.8} /></span><span>Provenance<span className="brand-accent">Lab</span></span></button>
      <nav className="topnav" aria-label="Main navigation"><button onClick={startNewAnalysis}>New analysis</button><button onClick={() => setStep(molecules.length ? "validate" : "source")}>Runs</button><button onClick={() => document.getElementById("about-dialog")?.showPopover()}>About</button></nav>
      <div className="topbar-right"><span className="run-chip">{run ? `RUN ${run.run_id}` : "NO ACTIVE RUN"}</span>{molecules.length ? <><span className="header-divider" /><button className="icon-button" onClick={() => { setStep("validate"); window.setTimeout(() => document.getElementById("structure-search")?.focus(), 0); }} aria-label="Search structures"><Search size={18} /></button></> : null}</div>
    </header>
    <div id="about-dialog" popover="auto" className="about-popover"><strong>About ProvenanceLab</strong><p>A deterministic molecular validation workspace. Every displayed result comes from the connected RDKit backend; missing evidence remains explicitly missing.</p></div>

    <div className="workspace-layout"><aside className="step-rail" aria-label="Analysis steps"><div className="rail-caption">WORKFLOW</div>{steps.map((item, index) => <button key={item.id} className={`step-item ${step === item.id ? "step-item--active" : ""}`} onClick={() => setStep(item.id)} aria-current={step === item.id ? "step" : undefined}><span className="step-number">{index + 1}</span><span className="step-text"><strong>{item.label}</strong><small>{item.detail}</small></span></button>)}<div className="rail-help"><CircleHelp size={18} /><span>Need help?<small>Scientific method guide</small></span></div></aside>

      <main className="main-content"><div className="page-heading"><div><p className="breadcrumb"><Home size={14} /> Workspace <ChevronRight size={13} /> {steps.find((item) => item.id === step)?.label}</p><h1>{pageTitle}</h1><p className="page-description">{pageDescription}</p></div><div className="live-notice"><ShieldCheck size={18} /><div><strong>Live deterministic analysis</strong><span>No fallback values or demonstration records are used.</span></div></div></div>
        {actionError ? <p className="page-error" role="alert"><AlertCircle size={16} /> {actionError}</p> : null}

        {step === "source" && <section className="source-screen"><div className="section-head"><div><h2>Source ingestion</h2><p>Select one input path; unrelated controls stay hidden.</p></div><span className="section-kicker">01 / SOURCE</span></div>
          <div className="input-tabs" role="tablist" aria-label="Input source">{inputModes.map((item) => <button key={item.id} role="tab" aria-selected={mode === item.id} className={mode === item.id ? "input-tab--active" : ""} onClick={() => changeMode(item.id)}>{item.label}</button>)}</div>
          <div className="source-grid"><div className="source-entry">
            {mode !== "smiles" ? <>
              <label className="dropzone" onDragOver={(event: DragEvent<HTMLLabelElement>) => event.preventDefault()} onDrop={(event: DragEvent<HTMLLabelElement>) => { event.preventDefault(); void chooseFile(event.dataTransfer.files[0]); }}>
                <input type="file" accept={mode === "paper" ? ".pdf,application/pdf" : ".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp"} onChange={(event: ChangeEvent<HTMLInputElement>) => { void chooseFile(event.target.files?.[0]); event.target.value = ""; }} />
                <UploadCloud size={30} strokeWidth={1.5} />
                <strong>{file ? file.name : mode === "paper" ? "Drop a PDF here" : "Drop a molecular structure image here"}</strong>
                <span>{file ? mode === "photo" ? "Image uploaded; DECIMER recognition runs automatically." : "PDF hashed locally; enter the structure from the selected page." : mode === "paper" ? "PDF only · up to 5 MB" : "PNG, JPEG, or WebP · up to 5 MB"}</span>
              </label>
              {mode === "photo" && extracting ? <div className="extraction-state extraction-state--working" role="status"><LoaderCircle size={18} /><div><strong>DECIMER is transcribing the structure</strong><span>The first local run also loads the recognition models and may take longer.</span></div></div> : null}
              {mode === "photo" && imageExtraction ? <div className="extraction-state extraction-state--ready"><ScanLine size={18} /><div><strong>Candidate generated by DECIMER {imageExtraction.model_version}</strong><span>{imageExtraction.confidence_mean === null || imageExtraction.confidence_mean === undefined ? "Token confidence was not reported." : `Mean token confidence ${(imageExtraction.confidence_mean * 100).toFixed(1)}%.`} Verify every atom and bond against the image.</span></div></div> : null}
              {fileError ? <p className="form-error" role="alert">{fileError}</p> : null}
            </> : <div className="direct-input-intro"><Atom size={27} /><div><strong>Direct molecular notation</strong><p>No PDF or image is required for a SMILES submission.</p></div></div>}
            <div className="source-fields">
              <label>Molecule label <span>Optional</span><input value={draftLabel} onChange={(event) => setDraftLabel(event.target.value)} maxLength={200} placeholder="e.g. Compound 7b" /></label>
              {mode === "paper" ? <label>Page number <span>Optional</span><input type="number" min="1" value={draftPage} onChange={(event) => setDraftPage(event.target.value)} placeholder="e.g. 4" /></label> : null}
              <label>{mode === "smiles" ? "SMILES string" : mode === "photo" ? "DECIMER candidate SMILES" : "SMILES transcription"} <span>{mode === "photo" ? "Editable · verify" : "Required"}</span><textarea value={draftSmiles} onChange={(event) => setDraftSmiles(event.target.value)} rows={5} maxLength={20_000} spellCheck={false} placeholder={mode === "smiles" ? "Paste or type a SMILES string" : mode === "photo" ? "Upload an image to generate a candidate automatically" : "Transcribe the structure shown on the selected page"} /></label>
              <p>{mode === "smiles" ? "The exact submitted text is hashed. Any standardization is recorded separately." : mode === "photo" ? "DECIMER output is an untrusted candidate. Compare it with the source image before review; edits are preserved." : "PDF structure recognition is not enabled yet. Confirm that the manual transcription matches the source."}</p>
              <button className="button button--primary" disabled={reviewing || extracting || !draftSmiles.trim()} onClick={() => void reviewCandidate()}>{extracting ? "Transcribing image…" : reviewing ? "Running RDKit…" : "Review candidate"} <ArrowRight size={16} /></button>
            </div>
          </div><aside className="input-guidance"><div className="example-head"><h3>Input contract</h3><p>What the pipeline will and will not do</p></div><ul><li><Check size={16} /> {mode === "photo" ? "Generate an editable SMILES candidate with DECIMER." : "Validate the submitted SMILES with RDKit."}</li><li><Check size={16} /> Preserve source metadata and hashes.</li><li><Check size={16} /> Explain invalidity and ambiguity separately.</li><li><X size={16} /> {mode === "photo" ? "Never treat image recognition as confirmed without your review." : mode === "paper" ? "Never claim that the PDF was interpreted automatically." : "Never silently repair the submitted structure."}</li><li><X size={16} /> Never fill a missing value.</li></ul></aside></div>
        </section>}

        {step === "confirm" && preview && <section className="confirmation-screen"><div className="section-head"><div><h2>Source and candidate</h2><p>Confirm the transcription only after comparing it with its source.</p></div><span className="section-kicker">02 / CONFIRM</span></div><div className="confirm-grid"><div className="source-preview"><div className="panel-title"><FileImage size={17} /><strong>Original source</strong><span>{file?.name ?? "Direct SMILES"}</span></div><div className="document-surface">{fileUrl && file?.type.startsWith("image/") ? <img src={fileUrl} alt={`Uploaded source ${file.name}`} /> : fileUrl && file?.type === "application/pdf" ? <iframe src={fileUrl} title={`Uploaded source ${file.name}`} /> : <div className="direct-source-preview"><Atom size={58} /><strong>Direct SMILES entry</strong><code>{draftSmiles}</code><small>No source document was attached to this record.</small></div>}</div></div>
          <div className="candidate-card"><div className="panel-title"><Atom size={18} /><strong>RDKit candidate</strong><MoleculeStatusBadge status={preview.status} compact /></div><div className="candidate-visual"><LiveMoleculeSvg svg={preview.depiction_svg} /></div><div className="candidate-facts"><div><span>Label</span><strong>{preview.label}</strong></div><div><span>Formula</span><strong>{propertyValue(preview, "molecular_formula")}</strong></div><div><span>Molecular weight</span><strong>{propertyValue(preview, "molecular_weight")}</strong></div><div className="candidate-smiles"><span>Submitted SMILES</span><code>{preview.raw_input}</code></div></div><p className={`candidate-warning candidate-warning--${preview.status}`}><AlertCircle size={17} /> {preview.issues[0]?.explanation ?? "No blocking issue was detected by the configured ruleset."}</p><div className="candidate-actions"><button className="button button--primary" disabled={confirming} onClick={() => void confirmCandidate()}><Check size={17} />{confirming ? "Saving run…" : editingIndex === null ? "Confirm and add to run" : "Confirm changes"}</button><button className="button button--quiet" onClick={() => setStep("source")}><Pencil size={17} /> Edit input</button><button className="button button--danger" onClick={() => { setPreview(null); setDraftSmiles(""); setStep("source"); }}><X size={16} /> Reject candidate</button></div></div></div></section>}

        {(step === "validate" || step === "compare") && (selected ? <ValidationDesk step={step} molecules={molecules} selected={selected} filtered={filtered} search={search} onSearch={setSearch} onSelect={setSelectedId} onAddSource={() => { clearDraft(); setStep("source"); }} onEdit={editReviewedCandidate} onReviewSource={() => sourceDialogRef.current?.showModal()} /> : <div className="empty-run panel"><div><strong>No analyzed structures yet.</strong><span>Submit a source to create the first real run record.</span></div><button className="button button--primary" onClick={() => setStep("source")}>Add a molecular source</button></div>)}

        {step === "report" && <section className="report-screen panel"><div className="report-heading"><ShieldCheck size={26} /><div><h2>Reproducible PDF report</h2><p>{molecules.length} structures · {validCount} computable · {invalidCount} invalid</p></div></div>{run ? <><div className="report-grid"><div><strong>Run ID</strong><code>{run.run_id}</code></div><div><strong>Reference snapshot</strong><code>{selected?.manifest.snapshotId ?? "not-configured"}</code></div><div><strong>Input SHA-256</strong><code>{run.input_sha256}</code></div><div><strong>Output SHA-256</strong><code>{run.output_sha256}</code></div></div><p className="report-caveat">The PDF is generated by the backend from the stored run. It includes validation findings, property states, standardization steps and reproducibility hashes. No unavailable value is fabricated.</p><button className="button button--primary" disabled={downloading} onClick={() => void downloadPdf()}><Download size={17} /> {downloading ? "Generating PDF…" : "Download PDF report"}</button></> : <div className="empty-report"><strong>No run is available to report.</strong><button className="button button--primary" onClick={() => setStep("source")}>Start an analysis</button></div>}</section>}
      </main></div>

    {selected ? <SourceReviewDialog dialogRef={sourceDialogRef} molecule={selected} sourceUrl={selectedSource?.url ?? null} sourceFile={selectedSource?.file ?? null} sourceHash={selected.sourceFileSha256 ?? null} onReject={() => void rejectReviewedCandidate()} onEdit={editReviewedCandidate} onConfirm={() => sourceDialogRef.current?.close()} /> : null}
  </div>;
}
