import { NextRequest } from "next/server";

const DIAGNOSIS_BACKEND_URL = process.env.DIAGNOSIS_BACKEND_URL?.replace(/\/+$/, "") ?? "http://localhost:8000";
const ASR_STANDALONE_URL = process.env.ASR_STANDALONE_URL?.replace(/\/+$/, "") ?? "http://localhost:8002";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function proxyTo(url: string, body: string, signal: AbortSignal | undefined) {
  const resp = await fetch(`${url}/api/asr`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    signal,
  });
  const data = await resp.json();
  return { status: resp.status, data };
}

export async function POST(request: NextRequest) {
  const payload = await request.text();

  // 优先尝试独立的 ASR 服务（模型常驻内存，响应更快）
  try {
    const { status, data } = await proxyTo(ASR_STANDALONE_URL, payload, request.signal);
    if (status === 200 && data.status === "success") {
      return Response.json(data, { status: 200, headers: { "Cache-Control": "no-store" } });
    }
  } catch {
    // 独立 ASR 服务不可用，fallback 到 diagnosis 后端
  }

  // Fallback 到 diagnosis 后端
  try {
    const { status, data } = await proxyTo(DIAGNOSIS_BACKEND_URL, payload, request.signal);
    return Response.json(data, { status, headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    const message = error instanceof Error ? error.message : "ASR proxy error";
    return Response.json({ error: message }, { status: 500 });
  }
}
