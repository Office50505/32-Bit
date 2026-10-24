import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  Atom,
  Check,
  ChevronRight,
  Download,
  FileImage,
  Home,
  Pencil,
  ShieldCheck,
  X,
} from "lucide-react";

import { BenzoAssistant } from "./BenzoAssistant";
import {
  analyzeMolecule,
  createAnalysisRun,
  downloadRunReport,
  extractMoleculeImage,
  prepareImageExtractionEngine,
} from "./api/analysis";
import type { MoleculeCandidate, StepId } from "./domain";
import { LiveMoleculeSvg } from "./LiveMoleculeSvg";
import { fromApi } from "./live";
import Molecule3D from "./Molecule3D";
import type {
  AnalyzeRequest,
  AnalyzeResponse,
  ExtractionEngineStatus,
  ImageExtractionResponse,
  RunResponse,
} from "./schemas/analysis";
import { SourceReviewDialog } from "./SourceReviewDialog";
import { SourceLanding } from "./SourceLanding";
import { MoleculeStatusBadge } from "./StatusBadge";
import { ValidationDesk } from "./ValidationDesk";
import { parseCsvMolecule } from "./utils/csvMolecule";

const steps: { id: StepId; label: string; detail: string }[] = [
  { id: "source", label: "Source", detail: "Upload or paste" },
  { id: "confirm", label: "Confirm", detail: "Candidate triage" },
  { id: "validate", label: "Validate", detail: "Inspect structure" },
  { id: "compare", label: "Compare", detail: "Batch audit" },
  { id: "report", label: "Report", detail: "PDF export" },
];

type InputMode = "csv" | "paper" | "photo" | "smiles";
type BrowserSource = { file: File; url: string };

function propertyValue(preview: AnalyzeResponse | null, key: string): string {
  const observation = preview?.properties.find((property) => property.key === key)?.computed;
  if (!observation || observation.value === null) return "Not computed";
  return `${observation.value}${observation.unit ? ` ${observation.unit}` : ""}`;
}

function SiteMenuMark() {
  return (
    <svg viewBox="0 0 74 78" aria-hidden="true">
      <path d="M17 5 58 1 72 46 39 76 2 50Z" />
      <g>
        <circle cx="29" cy="24" r="2.35" />
        <circle cx="46" cy="22" r="2.35" />
        <circle cx="31" cy="40" r="2.35" />
        <circle cx="48" cy="38" r="2.35" />
        <circle cx="33" cy="56" r="2.35" />
        <circle cx="50" cy="53" r="2.35" />
      </g>
    </svg>
  );
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
  const [, setReviewing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [actionError, setActionError] = useState("");
  const [search, setSearch] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const [fileHash, setFileHash] = useState<string | null>(null);
  const [fileError, setFileError] = useState("");
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [, setExtracting] = useState(false);
  const [, setExtractionStatus] = useState<ExtractionEngineStatus | null>(null);
  const [, setImageExtraction] = useState<ImageExtractionResponse | null>(null);
  const [extractionMethod, setExtractionMethod] = useState<string | null>(null);
  const [sourceFiles, setSourceFiles] = useState<Record<string, BrowserSource>>({});
  const sourceDialogRef = useRef<HTMLDialogElement>(null);
  const fileRequestRef = useRef(0);
  const extractionAbortRef = useRef<AbortController | null>(null);

  useEffect(() => () => extractionAbortRef.current?.abort(), []);

  useEffect(() => {
    if (!mobileMenuOpen) return;
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileMenuOpen(false);
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [mobileMenuOpen]);

  const selected = molecules.find((item) => item.id === selectedId) ?? molecules[0] ?? null;
  const filtered = useMemo(
    () => molecules.filter((item) => `${item.label} ${item.smiles}`.toLowerCase().includes(search.toLowerCase())),
    [molecules, search],
  );
  const validCount = molecules.filter((item) => item.status !== "invalid").length;
  const invalidCount = molecules.length - validCount;
  const selectedSource = selected?.sourceFileSha256 ? sourceFiles[selected.sourceFileSha256] : undefined;

  function clearDraft() {
    extractionAbortRef.current?.abort();
    extractionAbortRef.current = null;
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
    setExtractionStatus(null);
    setImageExtraction(null);
    setExtractionMethod(null);
    setActionError("");
    setMode("smiles");
  }

  async function chooseFile(next?: File, sourceMode: InputMode = mode) {
    if (!next) return;
    extractionAbortRef.current?.abort();
    const requestId = ++fileRequestRef.current;
    const isPaper = sourceMode === "paper";
    const isCsv = sourceMode === "csv";
    const accepted = isPaper
      ? next.type === "application/pdf" || /\.pdf$/i.test(next.name)
      : isCsv
        ? ["text/csv", "application/csv", "application/vnd.ms-excel", ""].includes(next.type) && /\.csv$/i.test(next.name)
        : ["image/png", "image/jpeg", "image/webp"].includes(next.type);
    if (!accepted) {
      setFileError(isPaper ? "Choose a PDF file." : isCsv ? "Choose a CSV file." : "Choose a PNG, JPEG, or WebP image.");
      return;
    }
    setMode(sourceMode);
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
    setExtractionStatus(null);
    setExtractionMethod(isPaper ? "manual-smiles-transcription" : isCsv ? "csv-smiles-column" : null);
    if (!isPaper && !isCsv) {
      setDraftSmiles("");
      setExtracting(true);
    }
    const extractionController = isPaper || isCsv ? null : new AbortController();
    extractionAbortRef.current = extractionController;
    try {
      const csvCandidate = isCsv ? parseCsvMolecule(await next.text()) : null;
      const extractionPromise = isPaper || isCsv ? null : prepareImageExtractionEngine({
        signal: extractionController?.signal,
        onStatus: (status) => {
          if (requestId === fileRequestRef.current) setExtractionStatus(status);
        },
      }).then(() => extractMoleculeImage(next, { signal: extractionController?.signal }));
      const digest = await crypto.subtle.digest("SHA-256", await next.arrayBuffer());
      const hash = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
      if (requestId !== fileRequestRef.current) return;
      setFileHash(hash);
      setSourceFiles((current) => ({ ...current, [hash]: { file: next, url } }));
      if (csvCandidate) {
        setDraftSmiles(csvCandidate.smiles);
        if (csvCandidate.label) setDraftLabel(csvCandidate.label);
      }
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
          if (error instanceof DOMException && error.name === "AbortError") return;
          setFileError(error instanceof Error ? error.message : "MolNexTR could not transcribe this image.");
        } finally {
          if (requestId === fileRequestRef.current) {
            setExtracting(false);
            extractionAbortRef.current = null;
          }
        }
      }
    } catch (error) {
      if (requestId !== fileRequestRef.current) return;
      URL.revokeObjectURL(url);
      setFile(null);
      setFileUrl(null);
      setExtracting(false);
      setExtractionStatus(null);
      setFileError(
        isCsv && error instanceof Error
          ? error.message
          : "This file could not be hashed. Choose it again before continuing.",
      );
    }
  }

  function chooseLandingFile(next?: File) {
    if (!next) return;
    const isPaper = next.type === "application/pdf" || /\.pdf$/i.test(next.name);
    const isCsv = /\.csv$/i.test(next.name) || ["text/csv", "application/csv"].includes(next.type);
    void chooseFile(next, isPaper ? "paper" : isCsv ? "csv" : "photo");
  }

  function navigate(next: StepId) {
    setMobileMenuOpen(false);
    setStep(next);
  }

  function buildDraftRequest(): AnalyzeRequest | null {
    const structure = draftSmiles.trim();
    if (!structure) {
      setActionError("Enter a SMILES string before reviewing the candidate.");
      return null;
    }
    if (mode !== "smiles" && (!file || !fileHash)) {
      setActionError(`Choose and finish hashing the ${mode === "paper" ? "PDF" : mode === "csv" ? "CSV" : "image"} source first.`);
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
        media_type: mode === "csv" ? "text/csv" : file?.type,
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
    setMode(sourceType === "paper" || sourceType === "photo" || sourceType === "csv" ? sourceType : "smiles");
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
  const sourceEntryTitle = mode === "csv" ? "CSV SMILES entry" : "Direct SMILES entry";
  const sourceEntryNote = mode === "csv" && file
    ? `Imported from ${file.name}.`
    : "No source document was attached to this record.";

  return <div className={`app-frame${step === "source" ? " app-frame--landing" : ""}`}>
    <header className={`site-chrome${mobileMenuOpen ? " site-chrome--open" : ""}`}>
      <button className="brand" onClick={() => navigate("source")} aria-label="ProvenanceLab home"><span className="brand-mark"><Atom size={21} strokeWidth={1.8} /></span><span>Provenance<span className="brand-accent">Lab</span></span></button>
      <button className="site-menu-trigger" type="button" aria-expanded={mobileMenuOpen} aria-controls="site-menu-panel" onClick={() => setMobileMenuOpen((current) => !current)}><span>{mobileMenuOpen ? "Close" : "Menu"}</span><span className="site-menu-trigger__mark"><SiteMenuMark /></span></button>
    </header>

    {mobileMenuOpen ? <div className="site-menu-panel" id="site-menu-panel" role="dialog" aria-modal="true" aria-label="Site menu">
      <div className="site-menu-panel__ambient" aria-hidden="true"><Molecule3D smiles={draftSmiles.trim() || "CC(=O)Oc1ccccc1C(=O)O"} label={draftLabel.trim() || "Aspirin"} autorotate resetSignal={0} zoom={0.82} appearance="hero" /></div>
      <nav className="site-menu-panel__nav" aria-label="Main navigation">
        <button className={step === "source" ? "site-menu-panel__link--active" : ""} onClick={() => navigate("source")}><span>01</span><strong>Home</strong></button>
        <button className={step !== "source" ? "site-menu-panel__link--active" : ""} onClick={() => navigate(molecules.length ? "validate" : "source")}><span>02</span><strong>Runs</strong></button>
        <button onClick={() => { setMobileMenuOpen(false); window.setTimeout(() => document.getElementById("about-dialog")?.showPopover(), 0); }}><span>03</span><strong>About</strong></button>
      </nav>
    </div> : null}
    <div id="about-dialog" popover="auto" className="about-popover"><strong>About ProvenanceLab</strong><p>A deterministic molecular validation workspace. Every displayed result comes from the connected RDKit backend; missing evidence remains explicitly missing.</p></div>

    <div className="workspace-layout">
      <main className="main-content">{step !== "source" ? <div className="page-heading"><div><p className="breadcrumb"><Home size={14} /> Workspace <ChevronRight size={13} /> {steps.find((item) => item.id === step)?.label}</p><h1>{pageTitle}</h1><p className="page-description">{pageDescription}</p></div><div className="live-notice"><ShieldCheck size={18} /><div><strong>Live deterministic analysis</strong><span>No fallback values or demonstration records are used.</span></div></div></div> : null}
        {actionError ? <p className="page-error" role="alert"><AlertCircle size={16} /> {actionError}</p> : null}

        {step === "source" ? <SourceLanding file={file} fileError={fileError} fileHash={fileHash} label={draftLabel} smiles={draftSmiles} onFileSelect={chooseLandingFile} onSmilesChange={(value) => { setDraftSmiles(value); setMode("smiles"); setActionError(""); }} onReview={() => void reviewCandidate()} /> : null}


        {step === "confirm" && preview && <section className="confirmation-screen"><div className="section-head"><div><h2>Source and candidate</h2><p>Confirm the transcription only after comparing it with its source.</p></div><span className="section-kicker">02 / CONFIRM</span></div><div className="confirm-grid"><div className="source-preview"><div className="panel-title"><FileImage size={17} /><strong>Original source</strong><span>{file?.name ?? "Direct SMILES"}</span></div><div className="document-surface">{fileUrl && file?.type.startsWith("image/") ? <img src={fileUrl} alt={`Uploaded source ${file.name}`} /> : fileUrl && file?.type === "application/pdf" ? <iframe src={fileUrl} title={`Uploaded source ${file.name}`} /> : <div className="direct-source-preview"><Atom size={58} /><strong>{sourceEntryTitle}</strong><code>{draftSmiles}</code><small>{sourceEntryNote}</small></div>}</div></div>
          <div className="candidate-card"><div className="panel-title"><Atom size={18} /><strong>RDKit candidate</strong><MoleculeStatusBadge status={preview.status} compact /></div><div className="candidate-visual"><LiveMoleculeSvg svg={preview.depiction_svg} /></div><div className="candidate-facts"><div><span>Label</span><strong>{preview.label}</strong></div><div><span>Formula</span><strong>{propertyValue(preview, "molecular_formula")}</strong></div><div><span>Molecular weight</span><strong>{propertyValue(preview, "molecular_weight")}</strong></div><div className="candidate-smiles"><span>Submitted SMILES</span><code>{preview.raw_input}</code></div></div><p className={`candidate-warning candidate-warning--${preview.status}`}><AlertCircle size={17} /> {preview.issues[0]?.explanation ?? "No blocking issue was detected by the configured ruleset."}</p><div className="candidate-actions"><button className="button button--primary" disabled={confirming} onClick={() => void confirmCandidate()}><Check size={17} />{confirming ? "Saving run…" : editingIndex === null ? "Confirm and add to run" : "Confirm changes"}</button><button className="button button--quiet" onClick={() => setStep("source")}><Pencil size={17} /> Edit input</button><button className="button button--danger" onClick={() => { setPreview(null); setDraftSmiles(""); setStep("source"); }}><X size={16} /> Reject candidate</button></div></div></div></section>}

        {(step === "validate" || step === "compare") && (selected ? <ValidationDesk step={step} molecules={molecules} selected={selected} filtered={filtered} search={search} onSearch={setSearch} onSelect={setSelectedId} onAddSource={() => { clearDraft(); setStep("source"); }} onEdit={editReviewedCandidate} onReviewSource={() => sourceDialogRef.current?.showModal()} /> : <div className="empty-run panel"><div><strong>No analyzed structures yet.</strong><span>Submit a source to create the first real run record.</span></div><button className="button button--primary" onClick={() => setStep("source")}>Add a molecular source</button></div>)}

        {step === "report" && <section className="report-screen panel"><div className="report-heading"><ShieldCheck size={26} /><div><h2>Reproducible PDF report</h2><p>{molecules.length} structures · {validCount} computable · {invalidCount} invalid</p></div></div>{run ? <><div className="report-grid"><div><strong>Run ID</strong><code>{run.run_id}</code></div><div><strong>Reference snapshot</strong><code>{selected?.manifest.snapshotId ?? "not-configured"}</code></div><div><strong>Input SHA-256</strong><code>{run.input_sha256}</code></div><div><strong>Output SHA-256</strong><code>{run.output_sha256}</code></div></div><p className="report-caveat">The PDF is generated by the backend from the stored run. It includes validation findings, property states, standardization steps and reproducibility hashes. No unavailable value is fabricated.</p><button className="button button--primary" disabled={downloading} onClick={() => void downloadPdf()}><Download size={17} /> {downloading ? "Generating PDF…" : "Download PDF report"}</button></> : <div className="empty-report"><strong>No run is available to report.</strong><button className="button button--primary" onClick={() => setStep("source")}>Start an analysis</button></div>}</section>}
      </main></div>

    {selected ? <SourceReviewDialog dialogRef={sourceDialogRef} molecule={selected} sourceUrl={selectedSource?.url ?? null} sourceFile={selectedSource?.file ?? null} sourceHash={selected.sourceFileSha256 ?? null} onReject={() => void rejectReviewedCandidate()} onEdit={editReviewedCandidate} onConfirm={() => sourceDialogRef.current?.close()} /> : null}
    <BenzoAssistant currentSmiles={draftSmiles.trim() || selected?.smiles || null} />
  </div>;
}
