import { AlertCircle, FileText, PenLine } from "lucide-react";

import type { AnalyzeResponse } from "../../schemas/analysis";
import { Button } from "../atoms/Button";
import { MoleculeListItem } from "../molecules/MoleculeListItem";
import { MoleculeSvg } from "../molecules/MoleculeSvg";

interface ValidationWorkspaceProps {
  results: AnalyzeResponse[];
  selectedIndex: number;
  onSelect: (index: number) => void;
  onReviewSource: () => void;
}

export function ValidationWorkspace({
  results,
  selectedIndex,
  onSelect,
  onReviewSource,
}: ValidationWorkspaceProps) {
  const selected = results[selectedIndex] ?? results[0];
  const primaryIssue = selected.issues[0];

  return (
    <section className="validation-workspace">
      <aside className="molecule-list" aria-label="Submitted structures">
        <h2>Submitted structures ({results.length})</h2>
        {results.map((result, index) => (
          <MoleculeListItem
            key={result.analysis_id}
            result={result}
            selected={index === selectedIndex}
            onSelect={() => onSelect(index)}
          />
        ))}
      </aside>

      <div className="molecule-detail">
        <div className="molecule-detail__visual">
          <h2>{selected.label}</h2>
          <MoleculeSvg svg={selected.depiction_svg} label={`${selected.label} annotated structure`} />
          <Button variant="quiet" icon={<PenLine size={17} />} onClick={onReviewSource}>Edit structure</Button>
        </div>

        <article className={`issue-detail issue-detail--${primaryIssue?.severity ?? "info"}`}>
          {primaryIssue ? (
            <>
              <div className="issue-detail__summary">
                <AlertCircle size={24} aria-hidden="true" />
                <div>
                  <span className="issue-code">{primaryIssue.code}</span>
                  <h2>{primaryIssue.title}</h2>
                  <p>{primaryIssue.explanation}</p>
                  {selected.status === "invalid" ? <small>No property values were calculated for this structure.</small> : null}
                </div>
              </div>
              <div className="issue-detail__section">
                <h3>Why this matters</h3>
                <p>{primaryIssue.why_it_matters}</p>
              </div>
              <div className="issue-detail__section">
                <h3>Next step</h3>
                <p>{primaryIssue.next_step}</p>
                <Button icon={<FileText size={17} />} onClick={onReviewSource}>Review source</Button>
              </div>
            </>
          ) : (
            <div className="issue-detail__verified">
              <h2>Structure verified</h2>
              <p>No blocking validation issue was detected. Review standardization and evidence before interpreting the values.</p>
            </div>
          )}
        </article>
      </div>
    </section>
  );
}
