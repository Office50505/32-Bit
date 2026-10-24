import type { ApiErrorResponse } from "../schemas/analysis";
import type { ClaimCheckResponse } from "../schemas/evidence";

const REQUEST_TIMEOUT_MS = 180_000;

async function evidenceError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as ApiErrorResponse & { detail?: string };
    if (body.error) return `${body.error.code}: ${body.error.message}`;
    return body.detail ?? `Evidence request failed with status ${response.status}`;
  } catch {
    return `Evidence request failed with status ${response.status}`;
  }
}

export async function checkEvidenceClaim(
  claim: string,
  signal?: AbortSignal,
): Promise<ClaimCheckResponse> {
  const controller = new AbortController();
  const forwardAbort = () => controller.abort(signal?.reason);
  signal?.addEventListener("abort", forwardAbort, { once: true });
  const timeout = window.setTimeout(
    () => controller.abort(new DOMException("Request timed out", "TimeoutError")),
    REQUEST_TIMEOUT_MS,
  );
  try {
    const response = await fetch("/api/evidence/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ claim }),
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(await evidenceError(response));
    return (await response.json()) as ClaimCheckResponse;
  } finally {
    window.clearTimeout(timeout);
    signal?.removeEventListener("abort", forwardAbort);
  }
}
