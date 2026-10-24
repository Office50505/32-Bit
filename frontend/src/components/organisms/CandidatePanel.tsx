import { AlertTriangle, Check, ChevronLeft, ChevronRight, Copy, PenLine, Trash2 } from "lucide-react";

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

  return (
    <section className="candidate-panel" aria-label="Extracted structure candidate">
      <header className="panel-header">
        <h2>Extracted structure</h2>
        <div className="candidate-pagination">
          <button type="button" aria-label="Previous candidate"><ChevronLeft size={18} /></button>
          <span>1 of 1</span>
          <button type="button" aria-label="Next candidate"><ChevronRight size={18} /></button>
        </div>
      </header>

      <div className="confirmation-notice">
        <AlertTriangle size={22} aria-hidden="true" />
        <strong>Needs confirmation</strong>
        <span>We found a structure. Please confirm it matches the source.</span>
      </div>

      {isLoading ? (
        <div className="candidate-loading"><Spinner label="Rendering molecular structure" /> Rendering structure…</div>
      ) : error ? (
        <div className="api-error" role="alert">
          <strong>Chemistry service unavailable</strong>
          <span>{error.message}</span>
          <small>Start the FastAPI backend on port 8000; no value has been guessed.</small>
        </div>
      ) : (
        <>
          <div className="candidate-structure">
            <MoleculeSvg svg={candidate?.depiction_svg} label={`${candidate?.label ?? "Candidate"} structure`} />
            <strong>{candidate?.label ?? "Candidate molecule"}</strong>
          </div>
          <dl className="candidate-metadata">
            <div><dt>Molecular formula</dt><dd>{formula?.value ?? "Unknown"}</dd></div>
            <div><dt>Molecular weight</dt><dd>{weight?.value ?? "Unknown"} {weight?.unit}</dd></div>
            <div><dt>SMILES</dt><dd><code>{candidate?.raw_input}</code><Copy size={15} /></dd></div>
            <div><dt>Candidate source</dt><dd>Bundled development fixture</dd></div>
          </dl>
        </>
      )}

      <div className="candidate-actions">
        <Button icon={<PenLine size={18} />} onClick={onEdit}>Edit structure</Button>
        <Button icon={<Trash2 size={18} />} onClick={onReject}>Reject</Button>
        <Button
          variant="primary"
          icon={<Check size={18} />}
          onClick={onConfirm}
          disabled={!candidate || isLoading || Boolean(error)}
        >
          Confirm structure
        </Button>
      </div>
    </section>
  );
}
