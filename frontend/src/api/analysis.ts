import type {
  AnalyzeRequest,
  AnalyzeResponse,
  ApiErrorResponse,
  BatchAnalyzeResponse,
  ImageExtractionResponse,
  RunResponse,
} from "../schemas/analysis";

const JSON_HEADERS = { "Content-Type": "application/json" } as const;

async function readApiError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as ApiErrorResponse & { detail?: string };
    if (body.error) {
      const field = body.error.field ? ` (${body.error.field})` : "";
      return `${body.error.code}${field}: ${body.error.message}`;
    }
    return body.detail ?? `Request failed with status ${response.status}`;
  } catch {
    return `Request failed with status ${response.status}`;
  }
}

export async function createAnalysisRun(
  molecules: AnalyzeRequest[],
  signal?: AbortSignal,
): Promise<RunResponse> {
  const response = await fetch("/api/runs", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ molecules }),
    signal,
  });
  if (!response.ok) throw new Error(await readApiError(response));
  return (await response.json()) as RunResponse;
}

export async function downloadRunReport(runId: string): Promise<void> {
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/report.pdf`);
  if (!response.ok) throw new Error(await readApiError(response));
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${runId}-report.pdf`;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
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

export async function extractMoleculeImage(
  image: File,
  options: { handDrawn?: boolean; signal?: AbortSignal } = {},
): Promise<ImageExtractionResponse> {
  const body = new FormData();
  body.append("image", image, image.name);
  body.append("hand_drawn", String(options.handDrawn ?? false));
  const response = await fetch("/api/extract/image", {
    method: "POST",
    body,
    signal: options.signal,
  });
  if (!response.ok) throw new Error(await readApiError(response));
  return (await response.json()) as ImageExtractionResponse;
}
