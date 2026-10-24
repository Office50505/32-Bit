import type { ApiErrorResponse } from "../schemas/analysis";
import type { BenzoChatResponse } from "../schemas/benzo";

const REQUEST_TIMEOUT_MS = 60_000;

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
): Promise<BenzoChatResponse> {
  const controller = new AbortController();
  const forwardAbort = () => controller.abort(signal?.reason);
  signal?.addEventListener("abort", forwardAbort, { once: true });
  const timeout = window.setTimeout(
    () => controller.abort(new DOMException("Request timed out", "TimeoutError")),
    REQUEST_TIMEOUT_MS,
  );
  try {
    const response = await fetch("/api/benzo/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, current_smiles: currentSmiles || null }),
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(await benzoError(response));
    return (await response.json()) as BenzoChatResponse;
  } finally {
    window.clearTimeout(timeout);
    signal?.removeEventListener("abort", forwardAbort);
  }
}
