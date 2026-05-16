import { NextRequest } from "next/server";
import { buildCozeHeaders, fetchCozeWithColdStartRetry, proxyErrorResponse } from "@/lib/coze-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    const upstream = await fetchCozeWithColdStartRetry("/v1/chat/completions", {
      method: "POST",
      headers: buildCozeHeaders(),
      body: await request.text(),
      signal: request.signal,
    });

    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: {
        "Content-Type": upstream.headers.get("Content-Type") ?? "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
      },
    });
  } catch (error) {
    return proxyErrorResponse(error);
  }
}
