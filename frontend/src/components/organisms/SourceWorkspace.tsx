import {
  Database,
  FileText,
  Image,
  Info,
  PenLine,
} from "lucide-react";

import { Button } from "../atoms/Button";
import { InputModeTab, type InputMode } from "../molecules/InputModeTab";

interface SourceWorkspaceProps {
  mode: InputMode;
  structure: string;
  label: string;
  onModeChange: (mode: InputMode) => void;
  onStructureChange: (structure: string) => void;
  onLabelChange: (label: string) => void;
}

const INPUT_MODES = [
  { mode: "paper" as const, label: "Paper or PDF", badge: "Planned", icon: FileText },
  { mode: "photo" as const, label: "Photo or screenshot", badge: "Planned", icon: Image },
  { mode: "draw" as const, label: "Draw molecule", badge: "Planned", icon: PenLine },
  { mode: "data" as const, label: "SMILES", badge: "Available", icon: Database },
];

export function SourceWorkspace({
  mode,
  structure,
  label,
  onModeChange,
  onStructureChange,
  onLabelChange,
}: SourceWorkspaceProps) {
  return (
    <section className="source-workspace" aria-label="Source input">
      <div className="input-mode-list" role="tablist" aria-label="Input type">
        {INPUT_MODES.map((item) => (
          <InputModeTab
            key={item.mode}
            active={mode === item.mode}
            icon={item.icon}
            label={item.label}
            badge={item.badge}
            mode={item.mode}
            onSelect={onModeChange}
          />
        ))}
      </div>

      {mode !== "data" ? (
        <div className="capability-notice" role="status">
          <span className="capability-notice__icon"><Info size={24} aria-hidden="true" /></span>
          <div>
            <span className="eyebrow">Not available in this build</span>
            <h2>
              {mode === "draw" ? "The molecule editor is not connected yet." : "Document recognition is not connected yet."}
            </h2>
            <p>
              {mode === "draw"
                ? "No drawing canvas is simulated here. Use a SMILES string for the working validation flow."
                : "No file will be uploaded or interpreted. Paper and image inputs will be added only when extracted structures can be shown as untrusted candidates for your confirmation."}
            </p>
            <Button variant="primary" onClick={() => onModeChange("data")}>Use SMILES input</Button>
          </div>
        </div>
      ) : (
        <div className="structure-editor">
          <div className="structure-editor__intro">
            <span className="eyebrow">Working input</span>
            <h2>Enter a molecular structure</h2>
            <p>The exact text is hashed and preserved. Standardization is recorded separately.</p>
          </div>
          <label htmlFor="molecule-label">Molecule label <span>Optional</span></label>
          <input
            id="molecule-label"
            value={label}
            onChange={(event) => onLabelChange(event.target.value)}
            placeholder="Example: Compound 7b"
            maxLength={200}
          />
          <label htmlFor="structure-input">SMILES <span>Required</span></label>
          <textarea
            id="structure-input"
            value={structure}
            onChange={(event) => onStructureChange(event.target.value)}
            placeholder="Example: CC(=O)Oc1ccccc1C(=O)O"
            spellCheck={false}
            required
          />
          <p>Nothing is silently corrected. Invalid and ambiguous inputs receive distinct explanations.</p>
        </div>
      )}
    </section>
  );
}
