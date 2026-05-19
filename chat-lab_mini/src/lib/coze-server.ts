const API_BASE_URL = process.env.COZE_API_BASE_URL?.replace(/\/+$/, "") ?? "";
const API_TOKEN = process.env.COZE_API_TOKEN ?? "";
const COLD_START_RETRIES = Number(process.env.COZE_COLD_START_RETRIES ?? "4");
const RETRY_DELAYS_MS = [1200, 2500, 5000, 8000];

export function buildCozeUrl(path: string): string {
  if (!API_BASE_URL) {
    throw new Error("Missing COZE_API_BASE_URL");
  }
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
}

export function buildCozeHeaders(extra?: HeadersInit): HeadersInit {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (API_TOKEN) {
    headers.Authorization = API_TOKEN.startsWith("Bearer ") ? API_TOKEN : `Bearer ${API_TOKEN}`;
  }

  if (extra instanceof Headers) {
    extra.forEach((value, key) => {
      headers[key] = value;
    });
  } else if (Array.isArray(extra)) {
    for (const [key, value] of extra) headers[key] = value;
  } else if (extra) {
    Object.assign(headers, extra);
  }

  return headers;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }

    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

async function shouldRetryColdStart(response: Response): Promise<boolean> {
  if ([502, 503, 504, 522, 524].includes(response.status)) return true;

  if (response.status !== 404) return false;

  try {
    const body = await response.clone().text();
    return /instance_not_found|sandbox\s+not\s+found|cold\s*start|container/i.test(body);
  } catch {
    return false;
  }
}

export async function fetchCozeWithColdStartRetry(path: string, init: RequestInit): Promise<Response> {
  const attempts = Math.max(1, COLD_START_RETRIES + 1);
  let lastError: unknown;

  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await fetch(buildCozeUrl(path), init);
      const shouldRetry = attempt < attempts - 1 && (await shouldRetryColdStart(response));
      if (!shouldRetry) return response;
    } catch (error) {
      if (isAbortError(error) || attempt >= attempts - 1) throw error;
      lastError = error;
    }

    const delayMs = RETRY_DELAYS_MS[Math.min(attempt, RETRY_DELAYS_MS.length - 1)];
    await sleep(delayMs, init.signal instanceof AbortSignal ? init.signal : undefined);
  }

  throw lastError instanceof Error ? lastError : new Error("Coze backend cold start retry failed");
}

export function proxyErrorResponse(error: unknown): Response {
  const message = error instanceof Error ? error.message : "Backend proxy error";
  return Response.json({ error: message }, { status: 500 });
}
