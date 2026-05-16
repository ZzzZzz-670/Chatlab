const API_PROXY_BASE_URL = process.env.NEXT_PUBLIC_API_PROXY_BASE_URL?.replace(/\/+$/, "") ?? "";

export function getApiBaseUrl(): string {
  return API_PROXY_BASE_URL;
}

export function buildApiUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_PROXY_BASE_URL}${normalizedPath}`;
}

export function buildApiHeaders(extra?: HeadersInit): HeadersInit {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

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
