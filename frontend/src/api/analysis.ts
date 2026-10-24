import type {
  AnalyzeRequest,
  AnalyzeResponse,
  ApiErrorResponse,
  BatchAnalyzeResponse,
  ExtractionEngineStatus,
  ImageExtractionResponse,
  RunResponse,
} from "../schemas/analysis";

const JSON_HEADERS = { "Content-Type": "application/json" } as const;

async function fetchWithTimeout(
  input: RequestInfo | URL,
  init: RequestInit,
  timeoutMs: number,
): Promise<Response> {
  const controller = new AbortController();
  const upstreamSignal = init.signal;
  const forwardAbort = () => controller.abort(upstreamSignal?.reason);
  upstreamSignal?.addEventListener("abort", forwardAbort, { once: true });
  const timeout = window.setTimeout(
    () => controller.abort(new DOMException("Request timed out", "TimeoutError")),
    timeoutMs,
  );
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } finally {
    window.clearTimeout(timeout);
    upstreamSignal?.removeEventListener("abort", forwardAbort);
  }
}

function wait(milliseconds: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(signal.reason ?? new DOMException("Aborted", "AbortError"));
      return;
    }
    const handleAbort = () => {
      window.clearTimeout(timeout);
      reject(signal?.reason ?? new DOMException("Aborted", "AbortError"));
    };
    const timeout = window.setTimeout(() => {
      signal?.removeEventListener("abort", handleAbort);
      resolve();
    }, milliseconds);
    signal?.addEventListener("abort", handleAbort, { once: true });
  });
}

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
  const response = await fetchWithTimeout("/api/extract/image", {
    method: "POST",
    body,
    signal: options.signal,
  }, 120_000);
  if (!response.ok) throw new Error(await readApiError(response));
  return (await response.json()) as ImageExtractionResponse;
}

async function readExtractionEngine(
  handDrawn: boolean,
  signal?: AbortSignal,
): Promise<ExtractionEngineStatus> {
  const response = await fetchWithTimeout(
    `/api/extract/image/engine?hand_drawn=${String(handDrawn)}`,
    { signal },
    15_000,
  );
  if (!response.ok) throw new Error(await readApiError(response));
  return (await response.json()) as ExtractionEngineStatus;
}

export async function prepareImageExtractionEngine(options: {
  handDrawn?: boolean;
  signal?: AbortSignal;
  onStatus?: (status: ExtractionEngineStatus) => void;
  timeoutMs?: number;
} = {}): Promise<ExtractionEngineStatus> {
  const handDrawn = options.handDrawn ?? false;
  const startedAt = Date.now();
  const prepare = async () => {
    const response = await fetchWithTimeout(
      `/api/extract/image/engine/prepare?hand_drawn=${String(handDrawn)}`,
      { method: "POST", signal: options.signal },
      15_000,
    );
    if (!response.ok) throw new Error(await readApiError(response));
    return (await response.json()) as ExtractionEngineStatus;
  };
  let status = await prepare();
  options.onStatus?.(status);

  while (!status.ready) {
    if (status.stage === "error") {
      throw new Error(`${status.error_code ?? "EXTRACTION_ENGINE_ERROR"}: ${status.message}`);
    }
    if (Date.now() - startedAt > (options.timeoutMs ?? 10 * 60_000)) {
      throw new Error(
        "EXTRACTION_ENGINE_TIMEOUT: MolNexTR did not finish loading within 10 minutes. Retry after checking the local engine.",
      );
    }
    await wait(750, options.signal);
    status = await readExtractionEngine(handDrawn, options.signal);
    if (status.stage === "not_ready") status = await prepare();
    options.onStatus?.(status);
  }
  return status;
}
