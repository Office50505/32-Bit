import {
  Database,
  FileText,
  Image,
  Info,
  PenLine,
} from "lucide-react";

import type { PhotoSourceDraft } from "../../utils/photoSource";
import { Button } from "../atoms/Button";
import { InputModeTab, type InputMode } from "../molecules/InputModeTab";
import { MolecularStructureFields } from "../molecules/MolecularStructureFields";
import { PhotoSourceInput } from "./PhotoSourceInput";

interface SourceWorkspaceProps {
  mode: InputMode;
  structure: string;
  label: string;
  photo: PhotoSourceDraft | null;
  photoError: string | null;
  isPhotoReading: boolean;
  autoFocusStructure?: boolean;
  onModeChange: (mode: InputMode) => void;
  onStructureChange: (structure: string) => void;
  onLabelChange: (label: string) => void;
  onPhotoSelect: (file: File) => void;
}

const INPUT_MODES = [
  { mode: "paper" as const, label: "Paper or PDF", badge: "Planned", icon: FileText },
  { mode: "photo" as const, label: "Photo or screenshot", badge: "Available", icon: Image },
  { mode: "draw" as const, label: "Draw molecule", badge: "Planned", icon: PenLine },
  { mode: "data" as const, label: "SMILES", badge: "Available", icon: Database },
];

export function SourceWorkspace({
  mode,
  structure,
  label,
  photo,
  photoError,
  isPhotoReading,
  autoFocusStructure = false,
  onModeChange,
  onStructureChange,
  onLabelChange,
  onPhotoSelect,
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

      {mode === "photo" ? (
        <PhotoSourceInput
          photo={photo}
          isReading={isPhotoReading}
          error={photoError}
          label={label}
          structure={structure}
          autoFocusStructure={autoFocusStructure}
          onPhotoSelect={onPhotoSelect}
          onLabelChange={onLabelChange}
          onStructureChange={onStructureChange}
        />
      ) : mode !== "data" ? (
        <div className="capability-notice" role="status">
          <span className="capability-notice__icon"><Info size={24} aria-hidden="true" /></span>
          <div>
            <span className="eyebrow">Not available in this build</span>
            <h2>
              {mode === "draw" ? "The molecule editor is not connected yet." : "PDF extraction is not connected yet."}
            </h2>
            <p>
              {mode === "draw"
                ? "No drawing canvas is simulated here. Use a SMILES string for the working validation flow."
                : "PDF files are not uploaded or interpreted in this build. Use a screenshot of the molecular diagram or enter its SMILES directly."}
            </p>
            <Button variant="primary" onClick={() => onModeChange(mode === "paper" ? "photo" : "data")}>
              {mode === "paper" ? "Use a screenshot" : "Use SMILES input"}
            </Button>
          </div>
        </div>
      ) : (
        <div className="structure-editor">
          <div className="structure-editor__intro">
            <span className="eyebrow">Working input</span>
            <h2>Enter a molecular structure</h2>
            <p>The exact text is hashed and preserved. Standardization is recorded separately.</p>
          </div>
          <MolecularStructureFields
            label={label}
            structure={structure}
            helpText="Nothing is silently corrected. Invalid and ambiguous inputs receive distinct explanations."
            autoFocusStructure={autoFocusStructure}
            onLabelChange={onLabelChange}
            onStructureChange={onStructureChange}
          />
        </div>
      )}
    </section>
  );
}
