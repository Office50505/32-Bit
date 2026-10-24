import {
  ChevronLeft,
  ChevronRight,
  Database,
  FileImage,
  FileText,
  Image,
  PenLine,
  Search,
  Upload,
} from "lucide-react";
import { useRef } from "react";

import { Button } from "../atoms/Button";
import { InputModeTab, type InputMode } from "../molecules/InputModeTab";

interface SourceWorkspaceProps {
  mode: InputMode;
  fileName: string;
  structure: string;
  label: string;
  onModeChange: (mode: InputMode) => void;
  onFileSelect: (file: File) => void;
  onStructureChange: (structure: string) => void;
  onLabelChange: (label: string) => void;
}

const INPUT_MODES = [
  { mode: "paper" as const, label: "Paper or PDF", icon: FileText },
  { mode: "photo" as const, label: "Photo or screenshot", icon: Image },
  { mode: "draw" as const, label: "Draw molecule", icon: PenLine },
  { mode: "data" as const, label: "Structure data", icon: Database },
];

export function SourceWorkspace({
  mode,
  fileName,
  structure,
  label,
  onModeChange,
  onFileSelect,
  onStructureChange,
  onLabelChange,
}: SourceWorkspaceProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const acceptsImage = mode === "photo";

  const handleFile = (file?: File) => {
    if (file) onFileSelect(file);
  };

  return (
    <section className="source-workspace" aria-label="Source input">
      <div className="input-mode-list" role="tablist" aria-label="Input type">
        {INPUT_MODES.map((item) => (
          <InputModeTab
            key={item.mode}
            active={mode === item.mode}
            icon={item.icon}
            label={item.label}
            mode={item.mode}
            onSelect={onModeChange}
          />
        ))}
      </div>

      {mode === "paper" || mode === "photo" ? (
        <>
          <div
            className="dropzone"
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              handleFile(event.dataTransfer.files[0]);
            }}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept={acceptsImage ? "image/png,image/jpeg" : "application/pdf,image/png,image/jpeg"}
              onChange={(event) => handleFile(event.target.files?.[0])}
              hidden
            />
            <Upload size={30} strokeWidth={1.5} aria-hidden="true" />
            <strong>{acceptsImage ? "Drop a photo or screenshot here" : "Drop a paper or image here"}</strong>
            <span>{acceptsImage ? "PNG or JPG" : "PDF, PNG or JPG"} · up to 25 MB</span>
            <Button variant="secondary" onClick={() => fileInputRef.current?.click()}>Browse files</Button>
          </div>

          <div className="recent-source">
            <div className="section-label">Source preview <span>development fixture</span></div>
            <button type="button" className="source-file-row">
              <FileText size={20} aria-hidden="true" />
              <span>{fileName}</span>
              <small>3.8 MB</small>
              <ChevronRight size={18} aria-hidden="true" />
            </button>
          </div>

          <div className="paper-preview" aria-label="Example source preview">
            <div className="paper-preview__toolbar">
              <span><FileImage size={16} /> Page 3 of 12</span>
              <span><ChevronLeft size={16} /><ChevronRight size={16} /><Search size={16} /></span>
              <span>150%</span>
            </div>
            <div className="paper-preview__page">
              <small>B. Representative examples</small>
              <div className="paper-preview__formula">O=C(O)—C₆H₄—O—C(=O)—CH₃</div>
              <strong>Compound 7b</strong>
              <p><b>Figure 2.</b> Representative examples of the synthesized compounds. Source content is preserved with the run.</p>
            </div>
          </div>
        </>
      ) : (
        <div className="structure-editor">
          <label htmlFor="molecule-label">Molecule label</label>
          <input
            id="molecule-label"
            value={label}
            onChange={(event) => onLabelChange(event.target.value)}
            placeholder="e.g. Compound 7b"
          />
          <label htmlFor="structure-input">{mode === "draw" ? "Editable structure notation" : "SMILES"}</label>
          <textarea
            id="structure-input"
            value={structure}
            onChange={(event) => onStructureChange(event.target.value)}
            spellCheck={false}
          />
          <p>
            {mode === "draw"
              ? "The visual editor is the next lazy-loaded input module. This notation remains editable in the current milestone."
              : "The original text is preserved exactly; any standardized representation is stored separately."}
          </p>
        </div>
      )}
    </section>
  );
}
