import type { EvidenceStatus, MoleculeStatus } from "./domain";

const moleculeLabels: Record<MoleculeStatus, string> = {
  valid: "Verified",
  ambiguous: "Ambiguous stereochemistry",
  invalid: "Invalid input",
};

const evidenceLabels: Record<EvidenceStatus, string> = {
  MATCH: "Match",
  DIFFERENCE: "Difference",
  NOT_AVAILABLE: "Not available",
  NOT_APPLICABLE: "Not applicable",
  NOT_COMPUTED: "Not computed",
  OUTSIDE_SNAPSHOT_COVERAGE: "Outside snapshot coverage",
};

export function MoleculeStatusBadge({ status, compact = false }: { status: MoleculeStatus; compact?: boolean }) {
  return <span className={`status-badge status-badge--${status}`}><i />{compact ? status === "valid" ? "Verified" : status === "ambiguous" ? "Ambiguous" : "Invalid" : moleculeLabels[status]}</span>;
}

export function EvidenceStatusBadge({ status }: { status: EvidenceStatus }) {
  return <span className={`evidence-badge evidence-badge--${status.toLowerCase()}`}>{evidenceLabels[status]}</span>;
}
