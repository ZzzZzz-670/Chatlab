export interface PossibleMeaning {
  label: string;
  percentage: number;
  description?: string;
}

export interface SuggestedReply {
  reply: string;
  reason?: string;
}

export interface SuggestedReplies {
  conservative?: SuggestedReply;
  progressive?: SuggestedReply;
  boundary?: SuggestedReply;
}

export interface DiagnosisData {
  blindSpot?: string;
  coreMechanism?: string;
  behaviorProtection?: string;
  possibleMeanings?: PossibleMeaning[] | string;
  evidenceBasis?: string;
  riskWarning?: string;
  suggestedReplies?: SuggestedReplies | string;
  suggestions?: string;
}

const FIELD_ALIASES: Record<string, keyof DiagnosisData> = {
  家长盲点: "blindSpot",
  核心判断: "blindSpot",
  核心机制: "coreMechanism",
  行为保护: "behaviorProtection",
  行为意义: "behaviorProtection",
  可能含义: "possibleMeanings",
  可能性分布: "possibleMeanings",
  可能性: "possibleMeanings",
  概率: "possibleMeanings",
  判断依据: "evidenceBasis",
  依据: "evidenceBasis",
  证据: "evidenceBasis",
  风险提示: "riskWarning",
  风险提醒: "riskWarning",
  风险: "riskWarning",
  建议回复: "suggestedReplies",
  回复建议: "suggestedReplies",
  改善建议: "suggestions",
  沟通建议: "suggestions",
  应对建议: "suggestions",
};

const REPLY_VERSION_ALIASES: Record<string, keyof SuggestedReplies> = {
  稳妥版: "conservative",
  保守版: "conservative",
  推进版: "progressive",
  进阶版: "progressive",
  边界版: "boundary",
};

const FIELD_ORDER = [
  "家长盲点",
  "核心判断",
  "核心机制",
  "行为保护",
  "行为意义",
  "可能含义",
  "可能性分布",
  "可能性",
  "概率",
  "判断依据",
  "依据",
  "证据",
  "风险提示",
  "风险提醒",
  "风险",
  "建议回复",
  "回复建议",
  "改善建议",
  "沟通建议",
  "应对建议",
].sort((a, b) => b.length - a.length);

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function buildKeywordRegex(): RegExp {
  const labels = FIELD_ORDER.map(escapeRegex).join("|");
  return new RegExp(
    String.raw`(?:^|\n)\s*(?:#{1,6}\s*)?(?:[-*+>]\s*)?(?:\*\*|__)?(?:【)?(${labels})(?:】)?(?:\*\*|__)?\s*(?:[：:]\s*)?`,
    "g",
  );
}

function stripDiagnosisMarker(text: string): string {
  return text.replace(/###\s*DIAGNOSIS_READY\s*###/gi, "").replace(/DIAGNOSIS_READY/gi, "");
}

export function cleanMarkdown(text: string): string {
  return stripDiagnosisMarker(text)
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/__(.*?)__/g, "$1")
    .replace(/^#{1,6}\s*/gm, "")
    .replace(/^[*-]\s*/gm, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function removeIntroBeforeFirstKeyword(text: string): string {
  const regex = buildKeywordRegex();
  const match = regex.exec(text);
  return match ? text.slice(match.index) : text;
}

function cleanSection(text: string): string {
  return cleanMarkdown(text)
    .replace(/^[\s：:，,。；;、-]+/, "")
    .replace(/["“”]+$/g, "")
    .trim();
}

function clampPercent(value: number): number {
  if (Number.isNaN(value)) return 0;
  return Math.max(0, Math.min(100, value));
}

function splitList(text: string): string[] {
  return cleanMarkdown(text)
    .split(/\n|[；;]/)
    .map((item) => item.replace(/^\s*(?:[-*•·]|\d+[.、)）]|[①②③④⑤⑥⑦⑧⑨⑩])\s*/, "").trim())
    .filter(Boolean);
}

export function normalizePossibleMeanings(value: DiagnosisData["possibleMeanings"]): PossibleMeaning[] | string | undefined {
  if (!value) return undefined;
  if (Array.isArray(value)) {
    const items = value
      .map((item) => ({
        label: cleanMarkdown(item.label ?? ""),
        percentage: clampPercent(Number(item.percentage)),
        description: item.description ? cleanMarkdown(item.description) : undefined,
      }))
      .filter((item) => item.label || item.description);
    return items.length ? items : undefined;
  }

  const raw = cleanMarkdown(value);
  const items: PossibleMeaning[] = [];
  const lines = splitList(raw);

  for (const line of lines) {
    const match = line.match(/(.+?)(?:[：:：\s\-–—]+)(\d{1,3})\s*%([\s\S]*)/);
    if (!match) continue;
    const beforePercent = match[1].trim();
    const pct = clampPercent(Number(match[2]));
    const description = match[3]?.replace(/^[-–—：:\s]+/, "").trim();
    const labelParts = beforePercent.split(/[：:]/);
    const label = (labelParts[0] ?? beforePercent).replace(/\d{1,3}\s*%/g, "").trim();
    const fallbackDesc = labelParts.slice(1).join("：").trim();
    items.push({
      label: label || beforePercent,
      percentage: pct,
      description: description || fallbackDesc || undefined,
    });
  }

  return items.length ? items : raw;
}

function parseReplyBlock(raw: string): SuggestedReply {
  const cleaned = cleanMarkdown(raw).replace(/^["“”'‘’\s]+|["“”'‘’\s]+$/g, "").trim();
  const reasonMatch = cleaned.match(/(?:推荐理由|理由)\s*[：:]\s*([\s\S]*)/);
  const reply = (reasonMatch ? cleaned.slice(0, reasonMatch.index).trim() : cleaned)
    .replace(/^(?:回复话术|回复|话术)\s*[：:]\s*/, "")
    .replace(/^["“”'‘’\s]+|["“”'‘’\s]+$/g, "")
    .trim();
  const reason = reasonMatch?.[1]?.trim();
  return { reply, reason };
}

export function parseSuggestedReplies(text: string): SuggestedReplies | string | undefined {
  const raw = cleanMarkdown(text);
  if (!raw) return undefined;

  const markerRegex = /(?:^|\n)\s*(?:#{1,6}\s*)?(?:[-*+>]\s*)?(?:\*\*|__)?【?\s*(稳妥版|保守版|推进版|进阶版|边界版)\s*】?(?:\*\*|__)?\s*(?:[：:]\s*)?/g;
  const matches: Array<{ version: keyof SuggestedReplies; start: number; contentStart: number }> = [];
  let match: RegExpExecArray | null;

  while ((match = markerRegex.exec(raw)) !== null) {
    matches.push({
      version: REPLY_VERSION_ALIASES[match[1]],
      start: match.index,
      contentStart: match.index + match[0].length,
    });
  }

  if (!matches.length) return raw;

  const replies: SuggestedReplies = {};
  for (let i = 0; i < matches.length; i += 1) {
    const current = matches[i];
    const next = matches[i + 1];
    const content = raw.slice(current.contentStart, next?.start ?? raw.length).trim();
    const parsed = parseReplyBlock(content);
    if (parsed.reply || parsed.reason) replies[current.version] = parsed;
  }

  return Object.keys(replies).length ? replies : raw;
}

function normalizeStructuredDiagnosis(input: DiagnosisData): DiagnosisData {
  const possibleMeanings = normalizePossibleMeanings(input.possibleMeanings);
  const suggestedReplies =
    typeof input.suggestedReplies === "string"
      ? parseSuggestedReplies(input.suggestedReplies)
      : input.suggestedReplies;

  return {
    blindSpot: input.blindSpot ? cleanMarkdown(input.blindSpot) : undefined,
    coreMechanism: input.coreMechanism ? cleanMarkdown(input.coreMechanism) : undefined,
    behaviorProtection: input.behaviorProtection ? cleanMarkdown(input.behaviorProtection) : undefined,
    possibleMeanings,
    evidenceBasis: input.evidenceBasis ? cleanMarkdown(input.evidenceBasis) : undefined,
    riskWarning: input.riskWarning ? cleanMarkdown(input.riskWarning) : undefined,
    suggestedReplies,
    suggestions: input.suggestions ? cleanMarkdown(input.suggestions) : undefined,
  };
}

export function parseDiagnosisFromText(text: string): DiagnosisData | null {
  const cleaned = removeIntroBeforeFirstKeyword(cleanMarkdown(text));
  const regex = buildKeywordRegex();
  const matches: Array<{ field: keyof DiagnosisData; start: number; contentStart: number }> = [];
  let match: RegExpExecArray | null;

  while ((match = regex.exec(cleaned)) !== null) {
    const field = FIELD_ALIASES[match[1]];
    if (!field) continue;
    matches.push({
      field,
      start: match.index,
      contentStart: match.index + match[0].length,
    });
  }

  const extracted: Partial<Record<keyof DiagnosisData, string>> = {};
  for (let i = 0; i < matches.length; i += 1) {
    const current = matches[i];
    if (extracted[current.field]) continue;
    const next = matches.find((candidate, index) => index > i && candidate.field !== current.field);
    const content = cleanSection(cleaned.slice(current.contentStart, next?.start ?? cleaned.length));
    if (content) extracted[current.field] = content;
  }

  const versionReplies = parseSuggestedReplies(cleaned);
  const data = normalizeStructuredDiagnosis({
    blindSpot: extracted.blindSpot,
    coreMechanism: extracted.coreMechanism,
    behaviorProtection: extracted.behaviorProtection,
    possibleMeanings: normalizePossibleMeanings(extracted.possibleMeanings),
    evidenceBasis: extracted.evidenceBasis,
    riskWarning: extracted.riskWarning,
    suggestedReplies: extracted.suggestedReplies ? parseSuggestedReplies(extracted.suggestedReplies) : versionReplies,
    suggestions: extracted.suggestions,
  });

  const hasAnyField = Object.values(data).some((value) => {
    if (Array.isArray(value)) return value.length > 0;
    if (value && typeof value === "object") return Object.keys(value).length > 0;
    return Boolean(value);
  });

  return hasAnyField ? data : null;
}

export function normalizeDiagnosis(input: unknown): DiagnosisData | null {
  if (!input || typeof input !== "object") return null;
  return normalizeStructuredDiagnosis(input as DiagnosisData);
}
