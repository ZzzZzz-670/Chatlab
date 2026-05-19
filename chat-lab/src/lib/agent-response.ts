import type { MemoryCandidate } from "@/lib/agent-router";

export interface FrontendCardSection {
  title: string;
  content: string;
}

export interface FrontendCard {
  type?: string;
  card_type?: string;
  title?: string;
  subtitle?: string;
  content?: string;
  sections?: FrontendCardSection[] | Record<string, unknown>;
  script?: string;
  actions?: Array<{ label: string; action?: string }>;
  [key: string]: unknown;
}

export interface AgentOutput {
  reply?: {
    message_type?: string;
    content?: string;
    ui_badge?: string;
    key_question?: string | null;
  };
  actions?: Array<{ label: string; action: string }>;
  key_question?: string | null;
  keyQuestion?: string | null;
  frontend_cards?: FrontendCard[];
  frontendCards?: FrontendCard[];
  cards?: FrontendCard[];
  memory_note_suggestion?: { show?: boolean; text?: string; detail?: string };
  profile_update_candidates?: MemoryCandidate[];
  growth_record_candidates?: MemoryCandidate[];
  pending_observation_candidates?: MemoryCandidate[];
  long_term_goal_updates?: MemoryCandidate[];
  parent_profile_candidates?: MemoryCandidate[];
  family_interaction_candidates?: MemoryCandidate[];
  correction_candidates?: MemoryCandidate[];
  rehearsal_save_candidate?: MemoryCandidate | null;
}

function tidyText(text: string): string {
  return text
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function isInternalFieldName(name: string): boolean {
  return /^(?:_?meta(?:data)?|output_?type|outputType|debug_?id|trace_?id|raw_.*|understanding_engine)$/i.test(name.trim());
}

export function cleanVisibleText(text: string): string {
  let cleaned = text;
  cleaned = cleaned.replace(/<!--(?!DIAGNOSIS_JSON\b)[\s\S]*?-->/gi, "");
  cleaned = cleaned.replace(/```(?:json|meta|metadata|debug)\s*\n[\s\S]*?\n```/gi, "");
  cleaned = cleaned.replace(/<\s*(meta|metadata|output_type|outputType|internal|debug|json)\b[^>]*>[\s\S]*?<\/\s*\1\s*>/gi, "");
  cleaned = cleaned.replace(/^\s*(?:JSON|Meta|metadata|output_type|outputType|debug_id|trace_id|_meta|raw_agent_output)\s*[:=].*$/gim, "");
  cleaned = cleaned.replace(/^\s*"(?:output_type|outputType|metadata|meta|debug_id|trace_id)"\s*:\s*.*[,]?$/gim, "");
  return tidyText(cleaned);
}

function tryJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i)?.[1];
    if (fenced) {
      try {
        return JSON.parse(fenced);
      } catch {
        return null;
      }
    }
    return null;
  }
}

export function normalizeKeyQuestion(value: unknown): string | undefined {
  if (!value) return undefined;
  if (typeof value === "string") {
    const cleaned = cleanVisibleText(value);
    return cleaned || undefined;
  }
  if (typeof value !== "object") return undefined;

  const record = value as Record<string, unknown>;
  return normalizeKeyQuestion(record.question ?? record.text ?? record.content);
}

export function extractKeyQuestionTags(text: string): { text: string; keyQuestion?: string } {
  const questions: string[] = [];
  const cleanText = text.replace(/<key_question\b[^>]*>([\s\S]*?)<\/key_question>/gi, (_match, content: string) => {
    const question = normalizeKeyQuestion(content);
    if (question) questions.push(question);
    return "";
  });

  return {
    text: cleanVisibleText(cleanText),
    keyQuestion: questions[0],
  };
}

export function highlightQuestion(text: string): string {
  if (!text.trim() || text.includes("highlight-question")) return text;

  const questionPrefixes = [
    "想跟您确认下",
    "想确认一下",
    "想请教一下",
    "想问问",
    "想问",
    "请问",
    "想了解一下",
    "能不能告诉我",
    "可以问一下",
    "问一下",
    "能不能说说",
    "能不能分享",
    "能不能描述",
    "能不能具体",
    "能不能",
  ];

  const lastQuestionMark = Math.max(text.lastIndexOf("?"), text.lastIndexOf("？"));
  if (lastQuestionMark === -1) return text;

  // 从最后一个问号往前，找最靠后的提问开头词
  let keywordIndex = -1;
  for (const prefix of questionPrefixes) {
    const idx = text.lastIndexOf(prefix, lastQuestionMark);
    if (idx !== -1 && idx > keywordIndex) {
      keywordIndex = idx;
    }
  }

  // 确定高亮起始位置：如果找到了关键词，往前找句子边界；否则从句子边界开始
  let startIndex: number;
  if (keywordIndex !== -1) {
    // 从关键词位置往前找句子边界
    const beforeKeyword = text.slice(0, keywordIndex);
    const enders = /[。！；.!;\n]/g;
    let lastEnder = -1;
    let match;
    while ((match = enders.exec(beforeKeyword)) !== null) {
      lastEnder = match.index;
    }
    startIndex = lastEnder !== -1 ? lastEnder + 1 : 0;
  } else {
    // 没找到提问开头词时，找最后一个问号之前的句子边界
    const beforeQuestion = text.slice(0, lastQuestionMark);
    const enders = /[。！；.!;\n]/g;
    let lastEnder = -1;
    let match;
    while ((match = enders.exec(beforeQuestion)) !== null) {
      lastEnder = match.index;
    }
    startIndex = lastEnder !== -1 ? lastEnder + 1 : 0;
  }

  const questionPart = text.slice(startIndex, lastQuestionMark + 1);
  const before = text.slice(0, startIndex);
  const after = text.slice(lastQuestionMark + 1);

  return before + '<span class="highlight-question">' + questionPart + "</span>" + after;
}

function normalizeCardSection(value: unknown): FrontendCardSection | undefined {
  if (!value) return undefined;
  if (typeof value === "string") return { title: "", content: cleanVisibleText(value) };
  if (typeof value !== "object") return undefined;

  const record = value as Record<string, unknown>;
  const title = typeof record.title === "string" ? record.title : typeof record.label === "string" ? record.label : "";
  const content =
    typeof record.content === "string"
      ? record.content
      : typeof record.text === "string"
        ? record.text
        : typeof record.description === "string"
          ? record.description
          : "";
  const cleaned = cleanVisibleText(content);
  return cleaned ? { title: tidyText(title), content: cleaned } : undefined;
}

function normalizeCard(value: unknown): FrontendCard | undefined {
  if (!value || typeof value !== "object") return undefined;
  const record = value as FrontendCard & Record<string, unknown>;
  const cleanRecord = Object.fromEntries(Object.entries(record).filter(([key]) => !isInternalFieldName(key))) as FrontendCard & Record<string, unknown>;
  const rawSections = cleanRecord.sections;
  let sections: FrontendCard["sections"] = rawSections;

  if (Array.isArray(rawSections)) {
    sections = rawSections.map(normalizeCardSection).filter((item): item is FrontendCardSection => Boolean(item));
  } else if (rawSections && typeof rawSections === "object") {
    sections = Object.fromEntries(
      Object.entries(rawSections)
        .filter(([key]) => !isInternalFieldName(key))
        .map(([key, content]) => [key, cleanVisibleText(String(content ?? ""))])
        .filter(([, content]) => content)
    );
  }

  return {
    ...cleanRecord,
    sections,
  };
}

export function normalizeFrontendCards(value: unknown): FrontendCard[] {
  if (!value) return [];
  const list = Array.isArray(value) ? value : [value];
  return list.map(normalizeCard).filter((item): item is FrontendCard => Boolean(item));
}

export function normalizeAgentOutput(rawContent: string): AgentOutput {
  const tagged = extractKeyQuestionTags(rawContent);
  const parsed = tryJson(tagged.text);

  if (parsed && typeof parsed === "object") {
    const output = parsed as AgentOutput & Record<string, unknown>;
    const reply = output.reply && typeof output.reply === "object" ? output.reply : undefined;
    const replyContent = typeof reply?.content === "string" ? extractKeyQuestionTags(reply.content) : undefined;
    const keyQuestion =
      normalizeKeyQuestion(output.key_question) ??
      normalizeKeyQuestion(output.keyQuestion) ??
      normalizeKeyQuestion(reply?.key_question) ??
      replyContent?.keyQuestion ??
      tagged.keyQuestion;

    const frontendCards = normalizeFrontendCards(output.frontend_cards ?? output.frontendCards ?? output.cards);

    return {
      ...output,
      reply: reply
        ? {
            ...reply,
            content: replyContent?.text ?? reply.content,
          }
        : output.reply,
      key_question: keyQuestion,
      frontend_cards: frontendCards,
    };
  }

  return {
    reply: {
      message_type: "normal_reply",
      content: tagged.text,
    },
    actions: [],
    key_question: tagged.keyQuestion,
  };
}
