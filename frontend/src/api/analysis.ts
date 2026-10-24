import type {
  AnalyzeRequest,
  AnalyzeResponse,
  BatchAnalyzeResponse,
} from "../schemas/analysis";

const JSON_HEADERS = { "Content-Type": "application/json" } as const;

async function readApiError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail ?? `Request failed with status ${response.status}`;
  } catch {
    return `Request failed with status ${response.status}`;
  }
}

export async function analyzeMolecule(
  request: AnalyzeRequest,
  signal?: AbortSignal,
): Promise<AnalyzeResponse> {
  const response = await fetch("/api/analyze", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(request),
    signal,
  });
  if (!response.ok) {
    throw new Error(await readApiError(response));
  }
  return (await response.json()) as AnalyzeResponse;
}

export async function analyzeBatch(
  molecules: AnalyzeRequest[],
  signal?: AbortSignal,
): Promise<BatchAnalyzeResponse> {
  const response = await fetch("/api/analyze/batch", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ molecules }),
    signal,
  });
  if (!response.ok) {
    throw new Error(await readApiError(response));
  }
  return (await response.json()) as BatchAnalyzeResponse;
}
