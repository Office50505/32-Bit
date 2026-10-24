import { DEMO_COMPARISON_INPUTS, RUN_DRAFT_STORAGE_KEY } from "../data/demo";
import type { AnalyzeRequest } from "../schemas/analysis";

interface StoredRunDraft {
  version: 1;
  molecules: AnalyzeRequest[];
}

export function saveRunDraft(molecules: AnalyzeRequest[]): void {
  const payload: StoredRunDraft = { version: 1, molecules };
  sessionStorage.setItem(RUN_DRAFT_STORAGE_KEY, JSON.stringify(payload));
}

export function loadRunDraft(): AnalyzeRequest[] {
  const raw = sessionStorage.getItem(RUN_DRAFT_STORAGE_KEY);
  if (!raw) {
    return DEMO_COMPARISON_INPUTS;
  }
  try {
    const parsed = JSON.parse(raw) as Partial<StoredRunDraft>;
    if (parsed.version !== 1 || !Array.isArray(parsed.molecules) || parsed.molecules.length === 0) {
      return DEMO_COMPARISON_INPUTS;
    }
    return parsed.molecules;
  } catch {
    return DEMO_COMPARISON_INPUTS;
  }
}
