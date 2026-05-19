import { NextRequest } from "next/server";
import { judgeMemoryCandidates, routeAgent, type MemoryCandidate } from "@/lib/agent-router";
import { normalizeAgentOutput, normalizeFrontendCards, normalizeKeyQuestion, type AgentOutput, type FrontendCard } from "@/lib/agent-response";
import { buildCozeHeaders, fetchCozeWithColdStartRetry } from "@/lib/coze-server";
import { loadMemoryContext, saveConversationEvent, writeMemoryCandidates } from "@/lib/memory-store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const COZE_CHAT_TIMEOUT_MS = Number(process.env.COZE_CHAT_TIMEOUT_MS ?? "8000");

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
    route_hint?: ReturnType<typeof routeAgent>;
    memory_candidates?: MemoryCandidate[];
  };
}

function extractContentFromCoze(data: unknown): string {
  if (!data || typeof data !== "object") return "";
  const root = data as Record<string, unknown>;
  const choices = Array.isArray(root.choices) ? root.choices : [];
  const first = choices[0] as Record<string, unknown> | undefined;
  const message = first?.message as Record<string, unknown> | undefined;
  const content = message?.content ?? first?.text ?? root.content;
  return typeof content === "string" ? content : "";
}

function extractFrontendCardsFromCoze(data: unknown): FrontendCard[] {
  if (!data || typeof data !== "object") return [];
  const root = data as Record<string, unknown>;
  const cards = normalizeFrontendCards(root.frontend_cards ?? root.frontendCards ?? root.cards);
  const diagnosis = root.diagnosis;

  if (diagnosis && typeof diagnosis === "object") {
    cards.push({
      ...(diagnosis as Record<string, unknown>),
      card_type: "diagnosis_card",
      title: "孩子理解卡",
      subtitle: "基于当前诊断结构化整理",
    });
  }

  return cards;
}

function mapAgentCandidates(output: AgentOutput): MemoryCandidate[] {
  const groups = [
    output.profile_update_candidates,
    output.growth_record_candidates,
    output.pending_observation_candidates,
    output.long_term_goal_updates,
    output.parent_profile_candidates,
    output.family_interaction_candidates,
    output.correction_candidates,
    output.rehearsal_save_candidate ? [output.rehearsal_save_candidate] : [],
  ];

  return groups
    .flatMap((items) => items ?? [])
    .filter((item): item is MemoryCandidate => Boolean(item?.tier && item?.content))
    .map((item) => ({ ...item, source: "agent_output" }));
}

function fallbackReply(text: string, agent: string) {
  const rehearsal = /怎么说|沟通|谈谈|表达|劝/.test(text);
  const content = rehearsal
    ? "这件事可以先不急着说服孩子。更稳的方向是先确认：这件安排在他那里最容易被理解成什么，是任务增加，还是休息被压缩。先把这个点问清，后面的表达会顺很多。"
    : agent === "diagnosis_agent"
      ? "我先不急着下结论。您说的这件事里，最关键的是把孩子的具体行为、发生时机和您的判断分开看。还想问一个细节：这种情况更常出现在开始前，还是已经做了一段以后？"
      : "我先把这件事放进孩子最近的状态里看。这里最值得留意的不是单次表现好不好，而是他在什么条件下更容易往前走一步、什么条件下又退回去。";

  return {
    reply: {
      message_type: rehearsal ? "communication_rehearsal" : "normal_reply",
      content,
    },
    key_question: rehearsal
      ? "如果先不谈时长，孩子最在意的是休息被压缩，还是手机被拿走？"
      : "这种情况更常出现在开始前，还是已经做了一段以后？",
    actions: rehearsal
      ? [
          { label: "复制", action: "copy" },
          { label: "存到预演记录", action: "save_rehearsal" },
          { label: "进一步解释", action: "further_explanation" },
        ]
      : [],
    frontend_cards: rehearsal
      ? [
          {
            card_type: "communication_rehearsal",
            title: "先帮你过一遍",
            subtitle: "把准备说的话先放在孩子视角里看一看",
            sections: [
              {
                title: "孩子可能怎么接",
                content: "如果他最近比较在意完成后能不能真的休息，他可能先感到休息时间又被压缩了。",
              },
              {
                title: "需要避免的一点",
                content: "不要把开头放在“你就是自控力差”上，先确认他真正担心的是什么。",
              },
            ],
            script: "我不是想一下子把手机全收掉，我想先和你确认一件事：你每天真正能休息的时间应该怎么安排，手机也在里面，但不能把睡觉和第二天状态拖垮。",
          },
        ]
      : /主动|变化|进步|自己/.test(text)
        ? [
            {
              card_type: "growth_signal",
              title: "这次记录到的信号",
              subtitle: "基于这次描述整理，后面可以继续调整",
              sections: [
                {
                  title: "这次记录到的变化",
                  content: "孩子出现过自己往前走一步的行为，这比单看结果更值得先记下来。",
                },
                {
                  title: "值得继续观察的点",
                  content: "接下来可以看，这种主动更容易出现在压力低、边界清楚的时候，还是需要某种提醒才能出现。",
                },
              ],
            },
          ]
        : [],
  } satisfies AgentOutput;
}

async function callCozeAgent(payload: unknown, signal: AbortSignal): Promise<AgentOutput | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), COZE_CHAT_TIMEOUT_MS);
  signal.addEventListener("abort", () => controller.abort(), { once: true });

  try {
    const upstream = await fetchCozeWithColdStartRetry("/v1/chat/completions", {
      method: "POST",
      headers: buildCozeHeaders(),
      body: JSON.stringify(payload),
      signal: controller.signal,
    });

    if (!upstream.ok) return null;
    const data = (await upstream.json()) as unknown;
    const output = normalizeAgentOutput(extractContentFromCoze(data));
    output.frontend_cards = [
      ...normalizeFrontendCards(output.frontend_cards),
      ...extractFrontendCardsFromCoze(data),
    ];
    return output;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
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
  const conversationId = payload.conversation_id || `conv_${familyId}_${childId}`;
  const memoryContext = await loadMemoryContext(familyId, childId);
  const routeDecision = routeAgent(text, memoryContext.hasConfirmedProfile);
  const frontendCandidates = payload.client_context?.memory_candidates ?? [];
  const backendCandidates = judgeMemoryCandidates(text).map((item) => ({ ...item, source: "backend_rule" as const }));

  await saveConversationEvent({
    family_id: familyId,
    child_id: childId,
    conversation_id: conversationId,
    role: "user",
    content: text,
    agent: routeDecision.agent,
    message_type: routeDecision.scenario,
  });

  const agentPayload = {
    session_id: conversationId,
    family_id: familyId,
    child_id: childId,
    stream: false,
    messages: [
      {
        role: "system",
        content: JSON.stringify({
          runtime_context: {
            family_id: familyId,
            child_id: childId,
            conversation_id: conversationId,
            current_agent: routeDecision.agent,
            scenario: routeDecision.scenario,
          },
          memory_context: memoryContext,
          output_contract: {
            must_return_json: true,
            include_reply: true,
            include_memory_candidates: true,
            frontend_should_show_internal_fields: false,
            max_next_question_count: 1,
          },
        }),
      },
      { role: "user", content: text },
    ],
  };

  const agentOutput = (await callCozeAgent(agentPayload, request.signal)) ?? fallbackReply(text, routeDecision.agent);
  const agentCandidates = mapAgentCandidates(agentOutput);
  const writeResult = await writeMemoryCandidates(familyId, childId, [
    ...frontendCandidates,
    ...backendCandidates,
    ...agentCandidates,
  ]);

  const reply: NonNullable<AgentOutput["reply"]> = agentOutput.reply ?? { message_type: "normal_reply", content: "" };
  const keyQuestion = normalizeKeyQuestion(agentOutput.key_question ?? agentOutput.keyQuestion ?? reply.key_question);
  const messageId = `msg_${Date.now()}`;

  await saveConversationEvent({
    family_id: familyId,
    child_id: childId,
    conversation_id: conversationId,
    role: "assistant",
    content: reply.content ?? "",
    agent: routeDecision.agent,
    message_type: reply.message_type,
  });

  return Response.json({
    message_id: messageId,
    conversation_id: conversationId,
    route: routeDecision,
    reply: {
      message_type: reply.message_type ?? "normal_reply",
      ui_badge: reply.ui_badge ?? (memoryContext.hasConfirmedProfile ? "已参考孩子小档案" : undefined),
      content: reply.content ?? "",
    },
    key_question: keyQuestion ?? null,
    frontend_cards: normalizeFrontendCards(agentOutput.frontend_cards),
    actions: agentOutput.actions ?? [],
    memory_note: writeResult.memory_note,
    memory_detail: writeResult.memory_detail,
    memory_write_results: {
      written_count: writeResult.written.length,
      promoted_count: writeResult.promoted.length,
    },
  });
}
