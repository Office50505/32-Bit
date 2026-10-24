import { ChevronRight } from "lucide-react";

import type { AnalyzeResponse } from "../../schemas/analysis";
import { StatusLabel } from "../atoms/StatusLabel";
import { toneForStatus } from "../atoms/StatusMark";
import { MoleculeSvg } from "./MoleculeSvg";

const STATUS_COPY = {
  valid: "Verified",
  ambiguous: "Ambiguous stereochemistry",
  invalid: "Invalid input",
} as const;

interface MoleculeListItemProps {
  result: AnalyzeResponse;
  selected: boolean;
  onSelect: () => void;
}

export function MoleculeListItem({ result, selected, onSelect }: MoleculeListItemProps) {
  return (
    <button
      type="button"
      className={`molecule-list-item ${selected ? "molecule-list-item--selected" : ""}`}
      aria-pressed={selected}
      onClick={onSelect}
    >
      <MoleculeSvg svg={result.depiction_svg} label={`${result.label} structure`} compact />
      <span className="molecule-list-item__copy">
        <strong>{result.label}</strong>
        <StatusLabel tone={toneForStatus(result.status)}>{STATUS_COPY[result.status]}</StatusLabel>
      </span>
      <ChevronRight size={18} strokeWidth={1.75} aria-hidden="true" />
    </button>
  );
}
