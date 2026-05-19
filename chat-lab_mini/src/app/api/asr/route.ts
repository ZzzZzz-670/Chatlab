import { NextRequest } from "next/server";
import { buildCozeHeaders, fetchCozeWithColdStartRetry, proxyErrorResponse } from "@/lib/coze-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    const upstream = await fetchCozeWithColdStartRetry("/api/asr", {
      method: "POST",
      headers: buildCozeHeaders(),
      body: await request.text(),
      signal: request.signal,
    });

    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: {
        "Content-Type": upstream.headers.get("Content-Type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    return proxyErrorResponse(error);
  }
}
