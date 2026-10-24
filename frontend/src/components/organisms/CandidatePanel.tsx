import { AlertTriangle, Check, FlaskConical, PenLine, Trash2 } from "lucide-react";

import type { AnalyzeResponse } from "../../schemas/analysis";
import { Button } from "../atoms/Button";
import { Spinner } from "../atoms/Spinner";
import { MoleculeSvg } from "../molecules/MoleculeSvg";

interface CandidatePanelProps {
  candidate?: AnalyzeResponse;
  isLoading: boolean;
  error?: Error | null;
  onConfirm: () => void;
  onEdit: () => void;
  onReject: () => void;
}

export function CandidatePanel({
  candidate,
  isLoading,
  error,
  onConfirm,
  onEdit,
  onReject,
}: CandidatePanelProps) {
  const formula = candidate?.properties.find((item) => item.key === "molecular_formula")?.computed;
  const weight = candidate?.properties.find((item) => item.key === "molecular_weight")?.computed;
  const isPhotoSource = candidate?.source?.source_type === "photo";

  return (
    <section className="candidate-panel" aria-label="Molecular structure preview">
      <header className="panel-header">
        <h2>Structure preview</h2>
        <span className="panel-kicker">RDKit depiction</span>
      </header>

      {candidate ? (
        <div className="confirmation-notice">
          <AlertTriangle size={22} aria-hidden="true" />
          <strong>Review before analysis</strong>
          <span>
            {isPhotoSource
              ? "Confirm that the rendered structure matches both the source image and your SMILES transcription."
              : "Confirm that the rendered structure matches the SMILES you entered."}
          </span>
        </div>
      ) : null}

      {isLoading ? (
        <div className="candidate-loading"><Spinner label="Rendering molecular structure" /> Rendering structure…</div>
      ) : error ? (
        <div className="api-error" role="alert">
          <strong>Chemistry service unavailable</strong>
          <span>{error.message}</span>
          <small>Start the FastAPI backend on port 8000; no value has been guessed.</small>
        </div>
      ) : candidate ? (
        <>
          <div className="candidate-structure">
            <MoleculeSvg svg={candidate.depiction_svg} label={`${candidate.label} structure`} />
            <strong>{candidate.label}</strong>
          </div>
          <dl className="candidate-metadata">
            <div><dt>Molecular formula</dt><dd>{formula?.value ?? "Unknown"}</dd></div>
            <div><dt>Molecular weight</dt><dd>{weight?.value ?? "Unknown"} {weight?.unit}</dd></div>
            <div><dt>Submitted SMILES</dt><dd><code>{candidate.raw_input}</code></dd></div>
            <div>
              <dt>Input source</dt>
              <dd>{isPhotoSource ? `Photo or screenshot · ${candidate.source?.filename ?? "Unnamed image"}` : "Direct SMILES entry"}</dd>
            </div>
          </dl>
        </>
      ) : (
        <div className="candidate-empty">
          <span><FlaskConical size={30} aria-hidden="true" /></span>
          <h3>No structure entered</h3>
          <p>Enter a SMILES string to generate a molecular depiction and validation preview.</p>
        </div>
      )}

      {candidate ? (
        <div className="candidate-actions">
          <Button icon={<PenLine size={18} />} onClick={onEdit}>Edit input</Button>
          <Button icon={<Trash2 size={18} />} onClick={onReject}>Clear</Button>
          <Button
            variant="primary"
            icon={<Check size={18} />}
            onClick={onConfirm}
            disabled={isLoading || Boolean(error)}
          >
            Confirm and analyze
          </Button>
        </div>
      ) : null}
    </section>
  );
}
