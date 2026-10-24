import { AlertTriangle, Check, CircleMinus, X } from "lucide-react";

import type { MoleculeStatus, ResultStatus, Severity } from "../../schemas/analysis";

export type StatusTone = "verified" | "ambiguous" | "invalid" | "unknown" | "info";

export function toneForStatus(
  status: MoleculeStatus | ResultStatus | Severity,
): StatusTone {
  if (status === "valid" || status === "AVAILABLE" || status === "info") return "verified";
  if (status === "ambiguous" || status === "warning" || status === "CONFLICTING_EVIDENCE") return "ambiguous";
  if (
    status === "invalid" ||
    status === "error" ||
    status === "INVALID_INPUT" ||
    status === "COMPUTATION_ERROR"
  ) return "invalid";
  return "unknown";
}

export function StatusMark({ tone, label }: { tone: StatusTone; label: string }) {
  const Icon =
    tone === "verified"
      ? Check
      : tone === "ambiguous"
        ? AlertTriangle
        : tone === "invalid"
          ? X
          : CircleMinus;
  return (
    <span className={`status-mark status-mark--${tone}`} aria-label={label} title={label}>
      <Icon size={13} strokeWidth={2.25} aria-hidden="true" />
    </span>
  );
}
