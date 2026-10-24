import { FileCheck2, ImageUp, LoaderCircle } from "lucide-react";
import type { ChangeEvent, DragEvent } from "react";

import { formatFileSize, type PhotoSourceDraft } from "../../utils/photoSource";
import { MolecularStructureFields } from "../molecules/MolecularStructureFields";

interface PhotoSourceInputProps {
  photo: PhotoSourceDraft | null;
  isReading: boolean;
  error: string | null;
  label: string;
  structure: string;
  autoFocusStructure?: boolean;
  onPhotoSelect: (file: File) => void;
  onLabelChange: (label: string) => void;
  onStructureChange: (structure: string) => void;
}

export function PhotoSourceInput({
  photo,
  isReading,
  error,
  label,
  structure,
  autoFocusStructure = false,
  onPhotoSelect,
  onLabelChange,
  onStructureChange,
}: PhotoSourceInputProps) {
  const acceptFile = (file?: File) => {
    if (file) onPhotoSelect(file);
  };

  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    acceptFile(event.target.files?.[0]);
    event.target.value = "";
  };

  const handleDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    acceptFile(event.dataTransfer.files?.[0]);
  };

  return (
    <div className="structure-editor photo-source-editor">
      <div className="structure-editor__intro">
        <span className="eyebrow">Image-backed input</span>
        <h2>Add the source image</h2>
        <p>Upload the diagram, then transcribe its SMILES. The image is preserved only in this browser session and is never silently interpreted.</p>
      </div>

      <label
        className={`photo-dropzone ${photo ? "photo-dropzone--filled" : ""}`}
        htmlFor="photo-source-input"
        onDragOver={(event) => event.preventDefault()}
        onDrop={handleDrop}
      >
        <input
          id="photo-source-input"
          type="file"
          accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp"
          onChange={handleChange}
          disabled={isReading}
        />
        {isReading ? (
          <>
            <LoaderCircle className="photo-dropzone__spinner" size={28} aria-hidden="true" />
            <strong>Reading and hashing image…</strong>
          </>
        ) : photo ? (
          <>
            <img src={photo.dataUrl} alt={`Source preview: ${photo.filename}`} />
            <span className="photo-dropzone__details">
              <FileCheck2 size={18} aria-hidden="true" />
              <span><strong>{photo.filename}</strong><small>{formatFileSize(photo.fileSize)} · SHA-256 {photo.sha256.slice(0, 12)}…</small></span>
              <em>Change</em>
            </span>
          </>
        ) : (
          <>
            <span className="photo-dropzone__icon"><ImageUp size={26} aria-hidden="true" /></span>
            <strong>Choose or drop a molecular structure image</strong>
            <small>PNG, JPEG, or WebP · maximum 2 MB</small>
          </>
        )}
      </label>
      {error ? <p className="photo-source-error" role="alert">{error}</p> : null}

      <MolecularStructureFields
        label={label}
        structure={structure}
        structureLabel="SMILES transcribed from image"
        structurePlaceholder="Enter the SMILES represented by the uploaded diagram"
        helpText="The submitted image hash and transcription are recorded separately. Confirm the generated structure against the source image before analysis."
        autoFocusStructure={autoFocusStructure}
        onLabelChange={onLabelChange}
        onStructureChange={onStructureChange}
      />
    </div>
  );
}
