import type { ChangeEvent, DragEvent, FormEvent } from "react";
import { ArrowRight, FileCheck2, FileSpreadsheet, UploadCloud } from "lucide-react";

import Molecule3D from "./Molecule3D";

interface SourceLandingProps {
  file: File | null;
  fileError: string;
  fileNotice: string;
  fileHash: string | null;
  label: string;
  smiles: string;
  candidateCount: number;
  extracting: boolean;
  reviewing: boolean;
  onFileSelect: (file?: File) => void | Promise<void>;
  onSmilesChange: (value: string) => void;
  onReview: () => void;
}

const DEFAULT_PREVIEW = {
  label: "Aspirin",
  smiles: "CC(=O)Oc1ccccc1C(=O)O",
};

const FORMULA_TO_SMILES: Record<string, { name: string; smiles: string }> = {
  H2O: { name: "water", smiles: "O" },
  H2SO4: { name: "sulfuric acid", smiles: "OS(=O)(=O)O" },
  O2: { name: "oxygen", smiles: "O=O" },
  CO2: { name: "carbon dioxide", smiles: "O=C=O" },
  H2O2: { name: "hydrogen peroxide", smiles: "OO" },
  NH3: { name: "ammonia", smiles: "N" },
  CH4: { name: "methane", smiles: "C" },
};

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

export function SourceLanding({
  file,
  fileError,
  fileNotice,
  fileHash,
  label,
  smiles,
  candidateCount,
  extracting,
  reviewing,
  onFileSelect,
  onSmilesChange,
  onReview,
}: SourceLandingProps) {
  const cleanSmiles = smiles.trim();
  const previewSmiles = cleanSmiles || DEFAULT_PREVIEW.smiles;
  const previewLabel = cleanSmiles ? label.trim() || "Untitled molecule" : DEFAULT_PREVIEW.label;
  const previewZoom = Math.max(0.76, Math.min(1.28, 1.42 - Math.max(0, previewSmiles.length - 5) * 0.04));
  const hashPending = Boolean(file && !fileHash && !fileError);
  const canReview = Boolean((cleanSmiles || candidateCount) && !hashPending && !extracting && !reviewing);
  const formulaSuggestion = FORMULA_TO_SMILES[cleanSmiles.toUpperCase()];
  const csvSelected = Boolean(file && (/\.csv$/i.test(file.name) || file.type === "text/csv"));

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (canReview) onReview();
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    void onFileSelect(event.dataTransfer.files[0]);
  }

  return (
    <div className="source-landing">
      <section className="source-hero" aria-labelledby="source-hero-title">
        <div className="source-hero__entry">
          <h1 className="source-hero__sr-title" id="source-hero-title">Start a molecular analysis</h1>

          <form className="source-hero__form" onSubmit={submit}>
            <label className="source-smiles-control__field">
              <span className="source-hero__sr-title">SMILES or molecular value</span>
              <textarea
                value={smiles}
                onChange={(event) => onSmilesChange(event.target.value)}
                placeholder="Type a SMILES"
                autoComplete="off"
                spellCheck={false}
                rows={2}
                wrap="soft"
              />
            </label>

            {formulaSuggestion ? <p className="source-formula-hint" role="status">
              <span><strong>{cleanSmiles}</strong> is a molecular formula. Use the structural SMILES for {formulaSuggestion.name}:</span>
              <button type="button" onClick={() => onSmilesChange(formulaSuggestion.smiles)}>
                {formulaSuggestion.smiles}
              </button>
            </p> : null}

            <div className="source-hero__actions">
              <label
                className={`source-upload${file && !csvSelected ? " source-upload--selected" : ""}`}
                onDragOver={(event) => event.preventDefault()}
                onDrop={handleDrop}
              >
                <input
                  className="source-upload__input"
                  type="file"
                  accept="application/pdf,image/png,image/jpeg,image/webp,.pdf,.png,.jpg,.jpeg,.webp"
                  aria-label="Upload a PDF or molecular image"
                  aria-describedby={fileError ? "source-file-error" : "source-file-help"}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => {
                    void onFileSelect(event.target.files?.[0]);
                    event.target.value = "";
                  }}
                />
                {file && !csvSelected ? <FileCheck2 size={18} strokeWidth={1.7} /> : <UploadCloud size={18} strokeWidth={1.7} />}
                <strong>{file && !csvSelected ? file.name : "PDF / image"}</strong>
              </label>

              <label className={`source-upload${csvSelected ? " source-upload--selected" : ""}`}>
                <input
                  className="source-upload__input"
                  type="file"
                  accept="text/csv,application/csv,.csv"
                  aria-label="Upload a CSV file"
                  aria-describedby={fileError ? "source-file-error" : "source-file-help"}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => {
                    void onFileSelect(event.target.files?.[0]);
                    event.target.value = "";
                  }}
                />
                {csvSelected ? <FileCheck2 size={18} strokeWidth={1.7} /> : <FileSpreadsheet size={18} strokeWidth={1.7} />}
                <strong>{csvSelected ? file?.name : "Upload CSV"}</strong>
              </label>

              <button className="source-hero__submit" type="submit" disabled={!canReview}>
                {extracting
                  ? "Finding molecules…"
                  : reviewing
                    ? "Checking collection…"
                    : candidateCount > 1
                      ? `Review ${candidateCount} molecules`
                      : candidateCount === 1
                        ? "Review molecule"
                        : "Review"}
                <ArrowRight size={17} strokeWidth={1.9} />
              </button>

              <span className="source-hero__sr-title" id="source-file-help">
                {file
                  ? `${formatFileSize(file.size)} · ${fileHash ? "Ready" : "Preparing…"}`
                  : "PDF up to 25 MB · image or CSV up to 5 MB"}
              </span>
            </div>
            {fileNotice ? <p className="source-hero__notice" role="status">{fileNotice}</p> : null}
            {fileError ? <p className="source-hero__error" id="source-file-error" role="alert">{fileError}</p> : null}
          </form>
        </div>

        <div className="source-hero__viewer" aria-live="polite">
          <div className="source-hero__molecule">
            <Molecule3D
              smiles={previewSmiles}
              label={previewLabel}
              autorotate
              resetSignal={0}
              zoom={previewZoom}
              appearance="hero"
            />
          </div>
          <div className="source-hero__viewer-caption">
            <strong>{previewLabel} · live 3D preview</strong>
            <span>Drag to rotate · scroll to zoom</span>
          </div>
        </div>

      </section>

      <section className="source-path" id="source-path" aria-labelledby="source-path-title">
        <h2 id="source-path-title">A careful path from source to result.</h2>
        <ol>
          <li><span>01</span><div><strong>Add a source</strong><p>Attach the original file and enter the structure you want to inspect.</p></div></li>
          <li><span>02</span><div><strong>Confirm the structure</strong><p>Compare the live sketch with your source before it enters the run.</p></div></li>
          <li><span>03</span><div><strong>Validate and compare</strong><p>Keep computed results, evidence, and provenance visibly separate.</p></div></li>
        </ol>
      </section>

    </div>
  );
}
