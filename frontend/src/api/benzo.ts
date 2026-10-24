import type { ApiErrorResponse } from "../schemas/analysis";
import type { BenzoEvidenceResponse } from "../schemas/benzo";

// Local Qwen inference on a 16 GB machine can legitimately take more than one
// minute for evidence-heavy claims. Keep the UI request alive long enough for
// the pinned model to finish instead of surfacing a false network failure.
const REQUEST_TIMEOUT_MS = 120_000;

async function benzoError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as ApiErrorResponse & { detail?: string };
    if (body.error) return `${body.error.code}: ${body.error.message}`;
    return body.detail ?? `Benzo request failed with status ${response.status}`;
  } catch {
    return `Benzo request failed with status ${response.status}`;
  }
}

export async function askBenzo(
  question: string,
  currentSmiles?: string | null,
  signal?: AbortSignal,
): Promise<BenzoEvidenceResponse> {
  const controller = new AbortController();
  const forwardAbort = () => controller.abort(signal?.reason);
  signal?.addEventListener("abort", forwardAbort, { once: true });
  const timeout = window.setTimeout(
    () => controller.abort(new DOMException("Request timed out", "TimeoutError")),
    REQUEST_TIMEOUT_MS,
  );
  try {
    const contextualClaim = currentSmiles && /\b(?:this|current|shown|displayed)\b/i.test(question)
      ? `${question}\nCurrent molecule SMILES: ${currentSmiles}`
      : question;
    const response = await fetch("/api/evidence/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ claim: contextualClaim, run_record_ids: [] }),
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(await benzoError(response));
    return (await response.json()) as BenzoEvidenceResponse;
  } finally {
    window.clearTimeout(timeout);
    signal?.removeEventListener("abort", forwardAbort);
  }
}
