import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const DIAGNOSIS_BACKEND_URL = process.env.DIAGNOSIS_BACKEND_URL?.replace(/\/+$/, "") ?? "http://localhost:8000";

interface ChatRequest {
  family_id?: string;
  child_id?: string;
  conversation_id?: string;
  message?: {
    text?: string;
    attachments?: unknown[];
    source?: string;
  };
  client_context?: {
    page?: string;
    entry_mode?: string;
    communication_prefs?: string[];
    questionnaire_status?: string;
  };
}

export async function POST(request: NextRequest) {
  let payload: ChatRequest;
  try {
    payload = (await request.json()) as ChatRequest;
  } catch {
    return Response.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const text = payload.message?.text?.trim() ?? "";
  if (!text) return Response.json({ error: "message.text is required" }, { status: 400 });

  const familyId = payload.family_id || "family_demo";
  const childId = payload.child_id || "child_demo";

  const upstreamPayload = {
    family_id: familyId,
    child_id: childId,
    conversation_id: payload.conversation_id || `conv_${familyId}_${childId}`,
    message: {
      text,
      attachments: payload.message?.attachments ?? [],
      source: payload.message?.source ?? "chat_input",
    },
    client_context: {
      page: payload.client_context?.page ?? "chat",
      entry_mode: payload.client_context?.entry_mode ?? "daily_chat",
      communication_prefs: payload.client_context?.communication_prefs ?? [],
      questionnaire_status: payload.client_context?.questionnaire_status ?? "not_started",
    },
  };

  try {
    const upstream = await fetch(`${DIAGNOSIS_BACKEND_URL}/stream_run`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(upstreamPayload),
      signal: request.signal,
    });

    if (!upstream.ok) {
      const body = await upstream.text().catch(() => "unknown error");
      return Response.json({ error: `Backend error ${upstream.status}: ${body}` }, { status: 502 });
    }

    // 透传 SSE
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Backend proxy error";
    return Response.json({ error: message }, { status: 500 });
  }
}
