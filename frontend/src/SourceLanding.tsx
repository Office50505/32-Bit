import type { ChangeEvent, DragEvent, FormEvent } from "react";
import { ArrowDown, ArrowRight, FileCheck2, UploadCloud } from "lucide-react";

import Molecule3D from "./Molecule3D";

interface SourceLandingProps {
  file: File | null;
  fileError: string;
  fileHash: string | null;
  label: string;
  smiles: string;
  onFileSelect: (file?: File) => void | Promise<void>;
  onSmilesChange: (value: string) => void;
  onReview: () => void;
}

const DEFAULT_PREVIEW = {
  label: "Aspirin",
  smiles: "CC(=O)Oc1ccccc1C(=O)O",
};

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

export function SourceLanding({
  file,
  fileError,
  fileHash,
  label,
  smiles,
  onFileSelect,
  onSmilesChange,
  onReview,
}: SourceLandingProps) {
  const cleanSmiles = smiles.trim();
  const previewSmiles = cleanSmiles || DEFAULT_PREVIEW.smiles;
  const previewLabel = cleanSmiles ? label.trim() || "Untitled molecule" : DEFAULT_PREVIEW.label;
  const previewZoom = Math.max(0.76, Math.min(1.28, 1.42 - Math.max(0, previewSmiles.length - 5) * 0.04));
  const hashPending = Boolean(file && !fileHash && !fileError);
  const canReview = Boolean(cleanSmiles && !hashPending);

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

            <div className="source-hero__actions">
              <label
                className={`source-upload${file ? " source-upload--selected" : ""}`}
                onDragOver={(event) => event.preventDefault()}
                onDrop={handleDrop}
              >
                <input
                  className="source-upload__input"
                  type="file"
                  aria-describedby={fileError ? "source-file-error" : "source-file-help"}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => {
                    void onFileSelect(event.target.files?.[0]);
                    event.target.value = "";
                  }}
                />
                {file ? <FileCheck2 size={18} strokeWidth={1.7} /> : <UploadCloud size={18} strokeWidth={1.7} />}
                <strong>{file?.name ?? "Upload file"}</strong>
              </label>

              <button className="source-hero__submit" type="submit" disabled={!canReview}>
                Review <ArrowRight size={17} strokeWidth={1.9} />
              </button>

              <span className="source-hero__sr-title" id="source-file-help">
                {file
                  ? `${formatFileSize(file.size)} · ${fileHash ? "Ready" : "Preparing…"}`
                  : "PDF or any file · 5 MB max"}
              </span>
            </div>
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

        <a className="source-hero__down" href="#source-path" aria-label="See how the analysis works">
          <ArrowDown size={21} strokeWidth={1.7} />
        </a>
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
