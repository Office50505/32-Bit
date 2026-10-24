interface MolecularStructureFieldsProps {
  label: string;
  structure: string;
  structureLabel?: string;
  structurePlaceholder?: string;
  helpText: string;
  autoFocusStructure?: boolean;
  onLabelChange: (label: string) => void;
  onStructureChange: (structure: string) => void;
}

export function MolecularStructureFields({
  label,
  structure,
  structureLabel = "SMILES",
  structurePlaceholder = "Example: CC(=O)Oc1ccccc1C(=O)O",
  helpText,
  autoFocusStructure = false,
  onLabelChange,
  onStructureChange,
}: MolecularStructureFieldsProps) {
  return (
    <>
      <label htmlFor="molecule-label">Molecule label <span>Optional</span></label>
      <input
        id="molecule-label"
        value={label}
        onChange={(event) => onLabelChange(event.target.value)}
        placeholder="Example: Compound 7b"
        maxLength={200}
      />
      <label htmlFor="structure-input">{structureLabel} <span>Required</span></label>
      <textarea
        id="structure-input"
        value={structure}
        onChange={(event) => onStructureChange(event.target.value)}
        placeholder={structurePlaceholder}
        spellCheck={false}
        required
        autoFocus={autoFocusStructure}
      />
      <p>{helpText}</p>
    </>
  );
}
