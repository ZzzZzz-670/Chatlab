import { promises as fs } from "fs";
import path from "path";
import type { MemoryCandidate, MemoryTier } from "@/lib/agent-router";

export interface StoredMemory {
  id: string;
  family_id: string;
  child_id: string;
  tier: MemoryTier;
  category: string;
  content: string;
  confidence: number;
  status: "pending" | "confirmed" | "archived";
  evidence_count: number;
  evidence: string[];
  source: string;
  created_at: string;
  updated_at: string;
  confirmed_at?: string;
}

export interface ConversationEvent {
  id: string;
  family_id: string;
  child_id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  agent?: string;
  message_type?: string;
  created_at: string;
}

interface MemoryStoreData {
  memories: StoredMemory[];
  events: ConversationEvent[];
}

export interface MemoryContext {
  hasConfirmedProfile: boolean;
  low_verified_profile: StoredMemory[];
  high_verified_profile: StoredMemory[];
  growth_records: StoredMemory[];
  pending_observations: StoredMemory[];
  long_term_goals: StoredMemory[];
  correction_logs: StoredMemory[];
  rehearsal_records: StoredMemory[];
  parent_profile: StoredMemory[];
  family_interaction_patterns: StoredMemory[];
  recent_conversation: ConversationEvent[];
}

const DATA_DIR = path.join(process.cwd(), ".data");
const DATA_FILE = path.join(DATA_DIR, "central-memory-store.json");
const ALL_TIERS: MemoryTier[] = [
  "low_verified_profile",
  "high_verified_profile",
  "growth_records",
  "pending_observations",
  "long_term_goals",
  "correction_logs",
  "rehearsal_records",
  "parent_profile",
  "family_interaction_patterns",
];

function nowIso() {
  return new Date().toISOString();
}

function makeId(prefix: string) {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

async function readStore(): Promise<MemoryStoreData> {
  try {
    const raw = await fs.readFile(DATA_FILE, "utf8");
    const parsed = JSON.parse(raw) as Partial<MemoryStoreData>;
    return {
      memories: Array.isArray(parsed.memories) ? parsed.memories : [],
      events: Array.isArray(parsed.events) ? parsed.events : [],
    };
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code !== "ENOENT") throw error;
    return { memories: [], events: [] };
  }
}

async function writeStore(data: MemoryStoreData) {
  await fs.mkdir(DATA_DIR, { recursive: true });
  await fs.writeFile(DATA_FILE, JSON.stringify(data, null, 2), "utf8");
}

function normalizeForCompare(text: string) {
  return text.toLowerCase().replace(/\s+/g, "").slice(0, 80);
}

function isSimilar(a: string, b: string) {
  const left = normalizeForCompare(a);
  const right = normalizeForCompare(b);
  if (!left || !right) return false;
  return left.includes(right.slice(0, 24)) || right.includes(left.slice(0, 24));
}

function emptyContext(recent: ConversationEvent[]): MemoryContext {
  return {
    hasConfirmedProfile: false,
    low_verified_profile: [],
    high_verified_profile: [],
    growth_records: [],
    pending_observations: [],
    long_term_goals: [],
    correction_logs: [],
    rehearsal_records: [],
    parent_profile: [],
    family_interaction_patterns: [],
    recent_conversation: recent,
  };
}

export async function loadMemoryContext(familyId: string, childId: string): Promise<MemoryContext> {
  const store = await readStore();
  const scoped = store.memories.filter((item) => item.family_id === familyId && item.child_id === childId);
  const recent = store.events
    .filter((item) => item.family_id === familyId && item.child_id === childId)
    .slice(-10);
  const context = emptyContext(recent);

  for (const tier of ALL_TIERS) {
    context[tier] = scoped
      .filter((item) => item.tier === tier && item.status !== "archived")
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
      .slice(0, 12);
  }

  context.hasConfirmedProfile = context.high_verified_profile.length > 0;
  return context;
}

export async function saveConversationEvent(event: Omit<ConversationEvent, "id" | "created_at">) {
  const store = await readStore();
  store.events.push({ ...event, id: makeId("evt"), created_at: nowIso() });
  store.events = store.events.slice(-300);
  await writeStore(store);
}

export interface MemoryWriteResult {
  written: StoredMemory[];
  promoted: StoredMemory[];
  memory_note: string | null;
  memory_detail: string | null;
}

function noteFor(memory: StoredMemory): string {
  const map: Record<MemoryTier, string> = {
    growth_records: "已记录一个近期变化",
    low_verified_profile: "已加入后续观察",
    high_verified_profile: "已更新孩子小档案",
    pending_observations: "已加入后续观察",
    long_term_goals: "已加入长期观察",
    correction_logs: "已调整前面的一个判断",
    rehearsal_records: "已存到预演记录",
    parent_profile: "已更新沟通理解",
    family_interaction_patterns: "已更新沟通理解",
  };
  return map[memory.tier];
}

export async function writeMemoryCandidates(
  familyId: string,
  childId: string,
  candidates: MemoryCandidate[],
): Promise<MemoryWriteResult> {
  const store = await readStore();
  const scoped = store.memories.filter((item) => item.family_id === familyId && item.child_id === childId);
  const written: StoredMemory[] = [];
  const promoted: StoredMemory[] = [];

  for (const candidate of candidates) {
    if (!candidate.content.trim()) continue;

    const existing = scoped.find(
      (item) =>
        item.tier === candidate.tier &&
        item.category === candidate.category &&
        item.status !== "archived" &&
        isSimilar(item.content, candidate.content),
    );
    const timestamp = nowIso();

    if (existing) {
      existing.evidence_count += 1;
      existing.confidence = Math.min(0.96, Math.max(existing.confidence, candidate.confidence) + 0.08);
      existing.evidence = Array.from(new Set([...existing.evidence, ...(candidate.evidence ?? [candidate.content])])).slice(-8);
      existing.updated_at = timestamp;

      if (existing.status === "pending" && existing.evidence_count >= 2) {
        existing.status = "confirmed";
        existing.confirmed_at = timestamp;
        if (existing.tier === "low_verified_profile") existing.tier = "high_verified_profile";
        promoted.push(existing);
      }
      written.push(existing);
      continue;
    }

    const status = candidate.status ?? (candidate.confidence >= 0.72 ? "confirmed" : "pending");
    const memory: StoredMemory = {
      id: makeId("mem"),
      family_id: familyId,
      child_id: childId,
      tier: status === "confirmed" && candidate.tier === "low_verified_profile" ? "high_verified_profile" : candidate.tier,
      category: candidate.category,
      content: candidate.content,
      confidence: candidate.confidence,
      status,
      evidence_count: 1,
      evidence: candidate.evidence ?? [candidate.content],
      source: candidate.source,
      created_at: timestamp,
      updated_at: timestamp,
      confirmed_at: status === "confirmed" ? timestamp : undefined,
    };
    store.memories.push(memory);
    scoped.push(memory);
    written.push(memory);
  }

  await writeStore(store);

  const primary = promoted[0] ?? written.find((item) => item.status === "confirmed") ?? written[0];
  return {
    written,
    promoted,
    memory_note: primary ? noteFor(primary) : null,
    memory_detail: primary ? `这次记下的是：${primary.content}` : null,
  };
}
