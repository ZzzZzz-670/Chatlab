export type AgentType = "diagnosis_agent" | "daily_agent";

export type MemoryTier =
  | "low_verified_profile"
  | "high_verified_profile"
  | "growth_records"
  | "pending_observations"
  | "long_term_goals"
  | "correction_logs"
  | "rehearsal_records"
  | "parent_profile"
  | "family_interaction_patterns";

export interface RouteDecision {
  agent: AgentType;
  scenario:
    | "diagnosis"
    | "troubleshooting"
    | "study_assessment"
    | "communication_rehearsal"
    | "growth_record"
    | "correction"
    | "casual_chat";
  confidence: number;
  reasons: string[];
}

export interface MemoryCandidate {
  tier: MemoryTier;
  category: string;
  content: string;
  confidence: number;
  source: "frontend_judgement" | "agent_output" | "backend_rule";
  status?: "pending" | "confirmed";
  evidence?: string[];
}

const DIAGNOSIS_PATTERNS = [
  /诊断|分析|判断|原因|为什么|问题在哪|怎么办|怎么处理|排查|复盘|总结/,
  /学情|成绩|考试|作业|拖延|磨蹭|学习|听课|错题|不会|卡住/,
  /不自觉|没内驱|沉迷|叛逆|玻璃心|厌学|摆烂|不沟通/,
];

const DAILY_PATTERNS = [
  /哈哈|嘿嘿|早上好|晚上好|你好|随便聊|有点累|今天很烦|吐槽|闲聊/,
  /没啥|还好|路过|想聊聊/,
];

const REHEARSAL_PATTERNS = [/怎么说|该怎么跟|我想跟.*说|沟通|谈谈|开口|表达|劝/];
const CORRECTION_PATTERNS = [/不太像|不是这样|你理解错|我补充|其实不是|改一下|纠正/];
const GROWTH_PATTERNS = [/主动|第一次|最近|变化|进步|愿意|开始|自己|比以前/];
const LONG_TERM_GOAL_PATTERNS = [/希望.*心理健康|希望.*责任感|长期|目标|人格|自律|抗压|亲子信任|主动性/];
const STUDY_PATTERNS = [/学情|成绩|考试|作业|学习|错题|不会|卡住/];

function hasAny(text: string, patterns: RegExp[]) {
  return patterns.some((pattern) => pattern.test(text));
}

export function routeAgent(text: string, hasConfirmedProfile: boolean): RouteDecision {
  const normalized = text.trim();
  const reasons: string[] = [];

  if (!hasConfirmedProfile) reasons.push("尚未形成高验证孩子画像");
  if (hasAny(normalized, REHEARSAL_PATTERNS)) reasons.push("识别到沟通预演诉求");
  if (hasAny(normalized, CORRECTION_PATTERNS)) reasons.push("识别到纠偏或补充信息");
  if (hasAny(normalized, DIAGNOSIS_PATTERNS)) reasons.push("识别到正式诊断/排查类需求");
  if (hasAny(normalized, DAILY_PATTERNS)) reasons.push("识别到轻松交流场景");

  if (!hasConfirmedProfile || hasAny(normalized, DIAGNOSIS_PATTERNS)) {
    return {
      agent: "diagnosis_agent",
      scenario: hasAny(normalized, STUDY_PATTERNS) ? "study_assessment" : "diagnosis",
      confidence: !hasConfirmedProfile ? 0.86 : 0.78,
      reasons,
    };
  }

  if (hasAny(normalized, REHEARSAL_PATTERNS)) {
    return { agent: "daily_agent", scenario: "communication_rehearsal", confidence: 0.82, reasons };
  }

  if (hasAny(normalized, CORRECTION_PATTERNS)) {
    return { agent: "daily_agent", scenario: "correction", confidence: 0.82, reasons };
  }

  if (hasAny(normalized, DAILY_PATTERNS)) {
    return { agent: "daily_agent", scenario: "casual_chat", confidence: 0.72, reasons };
  }

  return {
    agent: "daily_agent",
    scenario: hasAny(normalized, GROWTH_PATTERNS) ? "growth_record" : "troubleshooting",
    confidence: 0.68,
    reasons: reasons.length ? reasons : ["默认进入日常对话 Agent"],
  };
}

export function judgeMemoryCandidates(text: string): MemoryCandidate[] {
  const normalized = text.trim();
  if (!normalized) return [];

  const candidates: MemoryCandidate[] = [];

  if (hasAny(normalized, CORRECTION_PATTERNS)) {
    candidates.push({
      tier: "correction_logs",
      category: "correction",
      content: normalized,
      confidence: 0.74,
      source: "frontend_judgement",
      status: "confirmed",
      evidence: [normalized],
    });
  }

  if (hasAny(normalized, GROWTH_PATTERNS)) {
    candidates.push({
      tier: "growth_records",
      category: "recent_change",
      content: normalized,
      confidence: 0.66,
      source: "frontend_judgement",
      status: "pending",
      evidence: [normalized],
    });
  }

  if (hasAny(normalized, LONG_TERM_GOAL_PATTERNS)) {
    candidates.push({
      tier: "long_term_goals",
      category: "parent_goal",
      content: normalized,
      confidence: 0.7,
      source: "frontend_judgement",
      status: "confirmed",
      evidence: [normalized],
    });
  }

  if (/孩子|他|她|儿子|女儿/.test(normalized) && !/懒|没救|自私|废/.test(normalized)) {
    candidates.push({
      tier: "low_verified_profile",
      category: "child_observation",
      content: normalized,
      confidence: 0.52,
      source: "frontend_judgement",
      status: "pending",
      evidence: [normalized],
    });
  }

  if (/懒|不自觉|没救|自私|叛逆|玻璃心/.test(normalized)) {
    candidates.push({
      tier: "pending_observations",
      category: "label_to_verify",
      content: `需要把家长评价拆成可验证事实：${normalized}`,
      confidence: 0.48,
      source: "frontend_judgement",
      status: "pending",
      evidence: [normalized],
    });
  }

  return candidates;
}
