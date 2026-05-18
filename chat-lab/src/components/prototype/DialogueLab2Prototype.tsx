"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { buildApiHeaders, buildApiUrl } from "@/lib/api-client";

type AppView =
  | "chat"
  | "profile"
  | "profile-detail"
  | "records"
  | "record-detail"
  | "child-card"
  | "child-form"
  | "child-complete"
  | "child-summary"
  | "settings";

type QuestionnaireStatus = "not_started" | "link_created" | "completed" | "skipped";

type MessageType =
  | "user"
  | "normal_reply"
  | "growth_signal_card"
  | "child_understanding_card"
  | "communication_rehearsal_card"
  | "correction_reply";

interface PrototypeMessage {
  id: string;
  type: MessageType;
  content?: string;
  memoryNote?: string;
  memoryDetail?: string;
  showPrecision?: boolean;
}

interface PrototypeAppProps {
  initialView?: AppView;
}

const routeByView: Record<AppView, string> = {
  chat: "/",
  profile: "/profile",
  "profile-detail": "/profile/detail",
  records: "/records",
  "record-detail": "/records/detail",
  "child-card": "/child-card",
  "child-form": "/child-card/form",
  "child-complete": "/child-card/complete",
  "child-summary": "/child-card/summary",
  settings: "/settings",
};

function viewFromPath(pathname: string): AppView {
  const found = (Object.entries(routeByView) as Array<[AppView, string]>)
    .sort((a, b) => b[1].length - a[1].length)
    .find(([, route]) => pathname === route);
  return found?.[0] ?? "chat";
}

const precisionText =
  "目前主要基于家长描述进行判断。孩子填写学习小档案后，后续分析会更贴近本人。";

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  const candidates = ["audio/mp4", "audio/webm;codecs=opus", "audio/webm", "audio/wav"];
  return candidates.find((type) => MediaRecorder.isTypeSupported(type));
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const result = reader.result;
      if (typeof result !== "string") {
        reject(new Error("Failed to read audio"));
        return;
      }
      resolve(result.split(",")[1] ?? result);
    };
    reader.onerror = () => reject(new Error("Failed to read audio"));
    reader.readAsDataURL(blob);
  });
}

const initialMessages: PrototypeMessage[] = [
  {
    id: "m_welcome",
    type: "normal_reply",
    content:
      "可以从孩子最近的一件小事说起。\n开心的、别扭的、说不清的都可以。\n我会陪你慢慢把孩子的状态和相处节奏看清楚。",
  },
  {
    id: "m_user_1",
    type: "user",
    content: "昨天他没有被催，自己写了一会儿作业，但写完一段以后又拿手机，我们又差点吵起来。",
  },
  {
    id: "m_ai_1",
    type: "normal_reply",
    content:
      "这个变化挺值得记一下。\n如果他平时不太主动开始学习，这次愿意先写一段，至少说明当时的启动窗口是打开的。\n我想先看一个细节：他拿手机是在完全不想写之前，还是已经完成了一小段之后？",
    memoryNote: "已记录一个近期变化",
    memoryDetail: "这次记下的是：孩子在没有被连续催促的情况下出现过主动启动。后面再聊作业、拖延和手机时，我会一起参考。",
  },
  { id: "m_growth", type: "growth_signal_card", showPrecision: true },
  {
    id: "m_ai_intro",
    type: "normal_reply",
    content: "你刚才说的这些，已经能看出一个比较清楚的方向了。我先整理成一版孩子理解卡，你看看像不像你家情况。",
    memoryNote: "已加入后续观察",
    memoryDetail: "后续会继续观察：孩子拖得最明显的时刻，是开始前，还是完成一段之后。",
  },
  { id: "m_understanding", type: "child_understanding_card", showPrecision: true },
  { id: "m_rehearsal", type: "communication_rehearsal_card", showPrecision: true },
  { id: "m_correction", type: "correction_reply", showPrecision: true },
];

const profileSections = [
  {
    title: "最近的成长变化",
    count: 3,
    items: [
      ["近期变化｜主动启动", "孩子在没有被连续催促时，出现过自己开始写作业的情况。", "来源：5 月 14 日作业记录", "中等"],
      ["近期变化｜主动提学校", "孩子最近有一次主动提到学校里的小事，沟通窗口曾经打开。", "来源：5 月 13 日晚间对话", "待观察"],
    ],
  },
  {
    title: "我目前记得的孩子",
    count: 2,
    items: [
      ["稳定特点｜边界敏感", "孩子比较在意“完成一件事以后，能不能真的结束”。", "来源：作业与手机冲突复盘", "较高"],
      ["稳定特点｜先慢后进", "启动前阻力较大，但进入状态后并非完全不能做。", "来源：多次作业记录", "中等"],
    ],
  },
  {
    title: "学习状态",
    count: 3,
    items: [
      ["学习状态｜启动方式", "孩子在压力较低、边界清楚时更容易开始学习。", "来源：5 月 14 日作业记录、5 月 16 日手机冲突复盘", "较高"],
      ["学习状态｜任务追加", "临时追加任务容易让孩子降低启动意愿。", "来源：睡前检查冲突", "中等"],
    ],
  },
  {
    title: "情绪反应",
    count: 2,
    items: [
      ["情绪反应｜被催促", "连续追问时更容易沉默或转向手机。", "来源：5 月 16 日复盘", "中等"],
    ],
  },
  {
    title: "沟通特点",
    count: 2,
    items: [
      ["沟通特点｜轻松时更愿意说", "轻松场景里更容易表达学校和同伴相关内容。", "来源：饭后聊天记录", "待观察"],
    ],
  },
  {
    title: "有效经验",
    count: 2,
    items: [
      ["有效经验｜提前约定", "提前说清边界，比临时提醒更容易被接受。", "来源：手机规则预演", "中等"],
    ],
  },
  {
    title: "还需要继续看的点",
    count: 4,
    items: [
      ["待观察｜休息边界", "他在意的是手机本身，还是完成后的休息确认。", "来源：后续观察点", "待观察"],
    ],
  },
  {
    title: "最近调整过的理解",
    count: 1,
    items: [
      ["判断调整｜手机场景", "手机相关判断从“逃避学习”调整为“休息边界”方向继续观察。", "来源：纠偏记录", "中等"],
    ],
  },
  {
    title: "重要卡片",
    count: 3,
    items: [
      ["孩子理解卡｜第一次整理", "已经形成一版关于启动阻力、任务边界和休息确认的理解。", "来源：首次深聊", "较高"],
    ],
  },
];

const records = [
  ["成长信号卡｜5月14日", "记录到：孩子主动开始写作业"],
  ["沟通预演｜5月16日", "主题：手机规则怎么说更稳"],
  ["判断调整｜5月18日", "手机问题从“逃避学习”调整为“休息边界”"],
  ["周小观察｜本周", "本周更值得看的是启动前的压力，而不是只看完成量"],
  ["收藏回复｜5月18日", "保存了一段更稳一点的沟通说法"],
];

const childQuestions: Array<[string, string[]]> = [
  ["最不想开始学习的时候，通常更像哪种情况？", ["不知道从哪开始", "怕一开始就停不下来", "觉得做完还会有新的", "只是当时太累了"]],
  ["写作业最容易卡住的是哪一步？", ["刚开始", "写到一半", "检查订正", "快结束的时候"]],
  ["大人一直催你时，你通常会怎样？", ["更烦", "沉默", "想快点应付", "能接受但希望少一点"]],
  ["写完一件事后，你最希望大人怎么做？", ["让我休息一下", "先别马上检查", "可以简单认可", "提前说下一步"]],
  ["考差后，你更想自己待一会儿，还是希望有人聊？", ["先自己待一会儿", "希望有人听我说", "看当时情况", "不太想提"]],
  ["大人怎么说，你比较愿意听？", ["提前约定", "语气轻一点", "给我选择", "直接说重点"]],
  ["鼓励、规则、自由、目标、同伴，哪种对你更有用？", ["鼓励", "规则", "自由", "目标"]],
  ["什么事情会让你感觉恢复一点？", ["安静一会儿", "运动", "听歌或看视频", "有人轻松地聊聊"]],
];

function cn(type: string, active?: boolean) {
  return active ? `${type} active` : type;
}

export default function DialogueLab2Prototype({ initialView = "chat" }: PrototypeAppProps) {
  const [view, setView] = useState<AppView>(initialView);
  const [messages, setMessages] = useState(initialMessages);
  const [input, setInput] = useState("");
  const [placeholder, setPlaceholder] = useState("从孩子最近的一件小事说起");
  const [toast, setToast] = useState("");
  const [sheet, setSheet] = useState<"actions" | "message" | "feedback" | "link" | "confirm" | null>(null);
  const [miniNote, setMiniNote] = useState<string | null>(null);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [questionnaireStatus, setQuestionnaireStatus] = useState<QuestionnaireStatus>("not_started");
  const [generatedLink, setGeneratedLink] = useState("");
  const [questionIndex, setQuestionIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [selectedPrefs, setSelectedPrefs] = useState(["多解释一点", "建议具体一点"]);
  const [reminderEnabled, setReminderEnabled] = useState(true);
  const [hasConfirmedProfile, setHasConfirmedProfile] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [sendDebug, setSendDebug] = useState<string | null>(null);

  useEffect(() => {
    setView(initialView);
  }, [initialView]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (initialView === "chat" && questionnaireStatus === "not_started") setShowOnboarding(true);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [initialView, questionnaireStatus]);

  useEffect(() => {
    const onPop = () => setView(viewFromPath(window.location.pathname));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const navigate = useCallback((next: AppView) => {
    setView(next);
    window.history.pushState({}, "", routeByView[next]);
  }, []);

  const showToast = useCallback((text: string) => {
    setToast(text);
    window.setTimeout(() => setToast(""), 1400);
  }, []);

  const copyText = useCallback(async (text: string, toastText = "已复制") => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Prototype keeps feedback even when clipboard permission is unavailable.
    }
    showToast(toastText);
  }, [showToast]);

  const insertMessage = useCallback((message: PrototypeMessage) => {
    setMessages((prev) => [...prev, { ...message, id: `${message.type}_${Date.now()}` }]);
  }, []);

  const handleAction = useCallback((action: string) => {
    setSheet(null);
    if (action === "record") {
      setPlaceholder("记录一次孩子最近的变化");
      insertMessage({
        id: "record_prompt",
        type: "normal_reply",
        content: "你可以直接说一件很小的变化：比如他今天有没有主动开始、有没有更愿意说话，或者某个反应和平时不太一样。",
      });
      showToast("已切换到成长记录");
    }
    if (action === "rehearsal") {
      setPlaceholder("把你准备和孩子说的话发给我");
      insertMessage({ id: "rehearsal_new", type: "communication_rehearsal_card", showPrecision: questionnaireStatus !== "completed" });
      showToast("已进入沟通预演");
    }
    if (action === "child-card") navigate("child-card");
    if (action === "continue") {
      insertMessage({
        id: "continue",
        type: "normal_reply",
        content: "我们可以继续看上次那个点：孩子拿手机更像是在逃避，还是在确认完成一段以后能不能真的休息。",
        memoryNote: "已接上上次话题",
        memoryDetail: "上次聊到的核心线索是：手机更常出现在完成一段之后，而不是完全开始前。",
      });
      showToast("已继续上次话题");
    }
    if (action === "profile") navigate("profile");
  }, [insertMessage, navigate, questionnaireStatus, showToast]);

  const sendMock = useCallback((overrideText?: string) => {
    const text = (overrideText ?? input).trim();
    if (!text) {
      showToast("先输入一点内容");
      return;
    }
    const requestId = Date.now();
    const setStage = (stage: string, detail?: unknown) => {
      const label = `[chat:${requestId}] ${stage}`;
      setSendDebug(stage);
      console.log(label, detail ?? "");
    };

    setMessages((prev) => [...prev, { id: `user_${Date.now()}`, type: "user", content: text }]);
    setInput("");
    setIsSending(true);
    setSendDebug("准备发送");

    void (async () => {
      let timeoutId: number | undefined;
      try {
        setStage("已触发发送", { text });
        const controller = new AbortController();
        timeoutId = window.setTimeout(() => controller.abort(), 15000);

        setStage("开始请求 /api/v1/chat");
        const response = await window.fetch("/api/v1/chat", {
          method: "POST",
          headers: buildApiHeaders(),
          cache: "no-store",
          signal: controller.signal,
          body: JSON.stringify({
            family_id: "family_demo",
            child_id: "child_demo",
            conversation_id: "conv_demo",
            message: {
              text,
              attachments: [],
              source: "chat_input",
            },
            client_context: {
              entry_mode: "daily_chat",
              page: "chat",
            },
          }),
        });
        setStage(`收到响应 ${response.status}`);
        const data = (await response.json()) as {
          reply?: { message_type?: string; content?: string };
          memory_note?: string | null;
          memory_detail?: string | null;
          memory_write_results?: { promoted_count?: number };
          error?: string;
        };
        setStage("响应解析完成");
        if (!response.ok || data.error) throw new Error(data.error ?? "chat failed");
        if ((data.memory_write_results?.promoted_count ?? 0) > 0 || data.memory_note === "已更新孩子小档案") {
          setHasConfirmedProfile(true);
        }
        insertMessage({
          id: "reply",
          type: "normal_reply",
          content: data.reply?.content ?? "我先记下这件事，后面会结合孩子小档案一起看。",
          memoryNote: data.memory_note ?? undefined,
          memoryDetail: data.memory_detail ?? undefined,
        });
        setStage("发送完成");
      } catch (error) {
        const message = error instanceof DOMException && error.name === "AbortError"
          ? "请求超时，请确认 Next 终端是否收到 POST"
          : error instanceof Error
            ? error.message
            : "未知错误";
        setSendDebug(`发送失败：${message}`);
        console.error(`[chat:${requestId}] error`, error);
        insertMessage({
          id: "reply",
          type: "normal_reply",
          content: "刚才这条没有连上后端。我先接住这件事：它值得放到孩子最近的状态里继续看，尤其是发生在开始前，还是已经做了一段以后。",
        });
        showToast("对话服务暂时不可用");
      } finally {
        if (timeoutId !== undefined) window.clearTimeout(timeoutId);
        setIsSending(false);
      }
    })();
  }, [input, insertMessage, showToast]);

  const generateLink = useCallback(() => {
    setGeneratedLink("https://demo.yihe.site/child-card/abc123");
    setQuestionnaireStatus("link_created");
    showToast("已生成填写链接");
  }, [showToast]);

  const finishQuestionnaire = useCallback(() => {
    setQuestionnaireStatus("completed");
    navigate("child-complete");
  }, [navigate]);

  const page = useMemo(() => {
    if (view === "profile") {
      return <ChildProfilePage status={questionnaireStatus} navigate={navigate} showToast={showToast} />;
    }
    if (view === "profile-detail") {
      return <ProfileDetailPage navigate={navigate} showToast={showToast} />;
    }
    if (view === "records") {
      return <ObservationRecordsPage navigate={navigate} />;
    }
    if (view === "record-detail") {
      return <RecordDetailPage navigate={navigate} copyText={copyText} showToast={showToast} />;
    }
    if (view === "child-card") {
      return (
        <ChildQuestionnaireParentPage
          navigate={navigate}
          status={questionnaireStatus}
          link={generatedLink}
          generateLink={generateLink}
          copyText={copyText}
          showToast={showToast}
        />
      );
    }
    if (view === "child-form") {
      return (
        <ChildQuestionnaireForm
          navigate={navigate}
          index={questionIndex}
          setIndex={setQuestionIndex}
          answers={answers}
          setAnswers={setAnswers}
          finish={finishQuestionnaire}
        />
      );
    }
    if (view === "child-complete") {
      return <ChildQuestionnaireCompletePage navigate={navigate} />;
    }
    if (view === "child-summary") {
      return <ChildPerspectiveSummary navigate={navigate} />;
    }
    if (view === "settings") {
      return (
        <SettingsPage
          navigate={navigate}
          showToast={showToast}
          selectedPrefs={selectedPrefs}
          setSelectedPrefs={setSelectedPrefs}
          reminderEnabled={reminderEnabled}
          setReminderEnabled={setReminderEnabled}
          openConfirm={() => setSheet("confirm")}
        />
      );
    }
    return (
      <ChatPage
        messages={messages}
        isSending={isSending}
        sendDebug={sendDebug}
        input={input}
        setInput={setInput}
        placeholder={placeholder}
        setPlaceholder={setPlaceholder}
        questionnaireStatus={questionnaireStatus}
        navigate={navigate}
        openActionSheet={() => setSheet("actions")}
        openMessageMenu={() => setSheet("message")}
        openFeedback={() => setSheet("feedback")}
        openChildCard={() => navigate("child-card")}
        copyText={copyText}
        showToast={showToast}
        setMiniNote={setMiniNote}
        sendMock={sendMock}
      />
    );
  }, [
    answers,
    copyText,
    finishQuestionnaire,
    generateLink,
    generatedLink,
    input,
    isSending,
    sendDebug,
    messages,
    navigate,
    placeholder,
    questionIndex,
    questionnaireStatus,
    reminderEnabled,
    selectedPrefs,
    sendMock,
    showToast,
    view,
  ]);

  return (
    <div className="dl2-shell">
      {page}
      <Toast text={toast} />
      <BottomActionSheet isOpen={sheet === "actions"} onClose={() => setSheet(null)} onAction={handleAction} />
      <MessageActionSheet
        isOpen={sheet === "message"}
        onClose={() => setSheet(null)}
        onCopy={() => copyText("这个变化挺值得记一下。")}
        onFeedback={(type) => {
          setSheet(null);
          if (type === "like") showToast("已记录反馈");
          if (type === "unlike") setSheet("feedback");
          if (type === "add") {
            setPlaceholder("补充一点具体情况");
            showToast("可以继续补充");
          }
          if (type === "save") showToast("已存到小档案");
        }}
      />
      <FeedbackSheet isOpen={sheet === "feedback"} onClose={() => setSheet(null)} showToast={showToast} />
      <ConfirmSheet isOpen={sheet === "confirm"} onClose={() => setSheet(null)} showToast={showToast} />
      <MiniMemoryNote detail={miniNote} onClose={() => setMiniNote(null)} />
      <OnboardingQuestionnaireModal
        isOpen={showOnboarding}
        onChildCard={() => {
          setShowOnboarding(false);
          setQuestionnaireStatus("link_created");
          navigate("child-card");
        }}
        onSkip={() => {
          setShowOnboarding(false);
          setQuestionnaireStatus("skipped");
        }}
      />
    </div>
  );
}

function ChatPage({
  messages,
  isSending,
  sendDebug,
  input,
  setInput,
  placeholder,
  setPlaceholder,
  questionnaireStatus,
  navigate,
  openActionSheet,
  openMessageMenu,
  openFeedback,
  openChildCard,
  copyText,
  showToast,
  setMiniNote,
  sendMock,
}: {
  messages: PrototypeMessage[];
  isSending: boolean;
  sendDebug: string | null;
  input: string;
  setInput: (value: string) => void;
  placeholder: string;
  setPlaceholder: (value: string) => void;
  questionnaireStatus: QuestionnaireStatus;
  navigate: (view: AppView) => void;
  openActionSheet: () => void;
  openMessageMenu: () => void;
  openFeedback: () => void;
  openChildCard: () => void;
  copyText: (text: string, toastText?: string) => void;
  showToast: (text: string) => void;
  setMiniNote: (detail: string) => void;
  sendMock: (overrideText?: string) => void;
}) {
  const scrollRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const scrollEl = scrollRef.current;
      if (scrollEl) scrollEl.scrollTop = scrollEl.scrollHeight;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [isSending, messages.length]);

  return (
    <div className="dl2-phone">
      <TopBar title="对话实验室" subtitle="记录孩子的变化，慢慢看懂孩子。" navigate={navigate} />
      <main className="dl2-chat-scroll" ref={scrollRef}>
        {messages.map((message) => (
          <MessageRenderer
            key={message.id}
            message={message}
            showPrecision={questionnaireStatus !== "completed" && Boolean(message.showPrecision)}
            openMessageMenu={openMessageMenu}
            openFeedback={openFeedback}
            openChildCard={openChildCard}
            copyText={copyText}
            showToast={showToast}
            setMiniNote={setMiniNote}
          />
        ))}
        {isSending && (
          <div className="dl2-message ai">
            <div className="dl2-ai-bubble">
              <TextBlock text="正在发送..." />
            </div>
          </div>
        )}
      </main>
      {process.env.NODE_ENV !== "production" && sendDebug && (
        <div className="dl2-debug-line" aria-live="polite">调试：{sendDebug}</div>
      )}
      <ChatInput
        value={input}
        setValue={setInput}
        placeholder={placeholder}
        setPlaceholder={setPlaceholder}
        openActionSheet={openActionSheet}
        onSend={sendMock}
        showToast={showToast}
      />
    </div>
  );
}

function TopBar({ title, subtitle, navigate, backTo }: { title: string; subtitle?: string; navigate: (view: AppView) => void; backTo?: AppView }) {
  return (
    <header className="dl2-topbar">
      <button className="dl2-icon-btn" type="button" onClick={() => (backTo ? navigate(backTo) : navigate("records"))} aria-label={backTo ? "返回" : "观察记录"}>
        {backTo ? "‹" : "≡"}
      </button>
      <div className="dl2-topbar-copy">
        <div className="dl2-topbar-title">{title}</div>
        {subtitle && <div className="dl2-topbar-subtitle">{subtitle}</div>}
      </div>
      <div className="dl2-topbar-actions">
        <button className="dl2-profile-pill" type="button" onClick={() => navigate("profile")} aria-label="打开孩子小档案">
          <BookmarkIcon />
          <span>小档案</span>
        </button>
        <button className="dl2-icon-btn" type="button" onClick={() => navigate("settings")} aria-label="更多">···</button>
      </div>
    </header>
  );
}

function ChatInput({
  value,
  setValue,
  placeholder,
  setPlaceholder,
  openActionSheet,
  onSend,
  showToast,
}: {
  value: string;
  setValue: (value: string) => void;
  placeholder: string;
  setPlaceholder: (value: string) => void;
  openActionSheet: () => void;
  onSend: (overrideText?: string) => void;
  showToast: (text: string) => void;
}) {
  const [inputMode, setInputMode] = useState<"text" | "voice">("text");
  const [isPressingVoice, setIsPressingVoice] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState("按住说话");
  const pressTimerRef = useRef<number | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const recordingRef = useRef(false);

  const clearPressTimer = useCallback(() => {
    if (pressTimerRef.current) {
      window.clearTimeout(pressTimerRef.current);
      pressTimerRef.current = null;
    }
  }, []);

  const cleanupVoice = useCallback(() => {
    recordingRef.current = false;
    setIsPressingVoice(false);
    setVoiceStatus("按住说话");
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
    mediaRecorderRef.current = null;
  }, []);

  const finishVoice = useCallback(() => {
    clearPressTimer();
    if (!recordingRef.current) {
      setIsPressingVoice(false);
      return;
    }
    setVoiceStatus("正在整理语音...");
    const recorder = mediaRecorderRef.current;
    if (!recorder) {
      cleanupVoice();
      showToast("录音没有启动，请检查麦克风权限");
      return;
    }
    if (recorder.state !== "inactive") recorder.stop();
  }, [clearPressTimer, cleanupVoice, showToast]);

  const startVoice = useCallback(async () => {
    clearPressTimer();
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      showToast("当前浏览器不支持录音，请使用文字输入");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = pickMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      chunksRef.current = [];
      mediaStreamRef.current = stream;
      mediaRecorderRef.current = recorder;
      recordingRef.current = true;
      setIsPressingVoice(true);
      setVoiceStatus("正在听你说话...");
      navigator.vibrate?.(10);

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onerror = () => {
        cleanupVoice();
        showToast("录音失败，请检查麦克风权限");
      };
      recorder.onstop = () => {
        const chunks = chunksRef.current;
        chunksRef.current = [];
        const type = recorder.mimeType || mimeType || "audio/webm";
        cleanupVoice();
        void (async () => {
          const blob = new Blob(chunks, { type });
          if (blob.size < 800) {
            showToast("录音时间太短，请重新说一次");
            return;
          }
          setVoiceStatus("正在转文字...");
          try {
            const base64Data = await blobToBase64(blob);
            const resp = await fetch(buildApiUrl("/api/asr"), {
              method: "POST",
              headers: buildApiHeaders(),
              body: JSON.stringify({
                base64Data,
                base64_data: base64Data,
                mimeType: type,
                mime_type: type,
              }),
            });
            const data = (await resp.json()) as { text?: string; error?: string };
            if (!resp.ok || data.error) throw new Error(data.error ?? "ASR failed");
            const text = data.text?.trim();
            if (!text) {
              showToast("没有听清，请再说一次");
              return;
            }
            setInputMode("text");
            setValue(text);
            onSend(text);
          } catch (error) {
            console.error("ASR error:", error);
            showToast("语音识别失败，请稍后重试");
          } finally {
            setVoiceStatus("按住说话");
          }
        })();
      };
      recorder.start(300);
    } catch {
      cleanupVoice();
      showToast("无法启动麦克风，请允许录音权限");
    }
  }, [cleanupVoice, clearPressTimer, onSend, setValue, showToast]);

  const beginLongPress = useCallback((event: React.PointerEvent<HTMLElement>) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    clearPressTimer();
    pressTimerRef.current = window.setTimeout(() => {
      startVoice();
    }, 350);
  }, [clearPressTimer, startVoice]);

  const endLongPress = useCallback(() => {
    if (pressTimerRef.current) {
      clearPressTimer();
      return;
    }
    finishVoice();
  }, [clearPressTimer, finishVoice]);

  const handleSend = useCallback(() => {
    const text = value.trim();
    if (!text) {
      showToast("先输入一点内容");
      return;
    }
    onSend(text);
  }, [onSend, showToast, value]);

  const handleTextKeyDown = useCallback((event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    handleSend();
  }, [handleSend]);

  useEffect(() => {
    return () => {
      clearPressTimer();
      try {
        mediaRecorderRef.current?.stop();
      } catch {
        // Ignore cleanup errors from platform recording APIs.
      }
      mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, [clearPressTimer]);

  return (
    <footer className={cn("dl2-composer", inputMode === "voice")}>
      <button className="dl2-round-btn" type="button" onClick={openActionSheet} aria-label="打开更多入口">+</button>
      {inputMode === "text" ? (
        <textarea
          value={value}
          rows={1}
          placeholder={placeholder}
          onChange={(e) => setValue(e.target.value)}
          onFocus={() => {
            if (placeholder === "补充一点具体情况") return;
            setPlaceholder("从孩子最近的一件小事说起");
          }}
          onKeyDown={handleTextKeyDown}
        />
      ) : (
        <button
          className={cn("dl2-voice-bar", isPressingVoice)}
          type="button"
          onPointerDown={beginLongPress}
          onPointerUp={endLongPress}
          onPointerCancel={endLongPress}
          onPointerLeave={endLongPress}
          aria-label="按住说话"
        >
          <span className="dl2-voice-wave" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <span>{voiceStatus}</span>
        </button>
      )}
      <button
        className="dl2-round-btn muted"
        type="button"
        onClick={() => setInputMode(inputMode === "text" ? "voice" : "text")}
        aria-label={inputMode === "text" ? "切换到语音输入条" : "切换到文本输入框"}
      >
        {inputMode === "text" ? <MicIcon /> : <KeyboardIcon />}
      </button>
      <button className={cn("dl2-send-btn", Boolean(value.trim()))} type="button" onClick={handleSend} aria-label="发送">↑</button>
    </footer>
  );
}

function MessageRenderer(props: {
  message: PrototypeMessage;
  showPrecision: boolean;
  openMessageMenu: () => void;
  openFeedback: () => void;
  openChildCard: () => void;
  copyText: (text: string, toastText?: string) => void;
  showToast: (text: string) => void;
  setMiniNote: (detail: string) => void;
}) {
  const { message } = props;
  if (message.type === "user") return <div className="dl2-message user"><div className="dl2-user-bubble">{message.content}</div></div>;
  if (message.type === "growth_signal_card") return <GrowthSignalCard {...props} />;
  if (message.type === "child_understanding_card") return <ChildUnderstandingCard {...props} />;
  if (message.type === "communication_rehearsal_card") return <RehearsalCard {...props} />;
  if (message.type === "correction_reply") return <CorrectionMessage {...props} />;
  return (
    <div className="dl2-message ai">
      <div className="dl2-ai-bubble">
        <TextBlock text={message.content ?? ""} />
        <MessageTools text={message.content ?? ""} copyText={props.copyText} openMenu={props.openMessageMenu} />
      </div>
      {message.memoryNote && (
        <button className="dl2-memory-note" type="button" onClick={() => props.setMiniNote(message.memoryDetail ?? message.memoryNote ?? "")}>
          {message.memoryNote}
        </button>
      )}
    </div>
  );
}

function TextBlock({ text }: { text: string }) {
  return (
    <div className="dl2-text-block">
      {text.split("\n").map((line) => (
        <p key={line}>{line}</p>
      ))}
    </div>
  );
}

function MessageTools({ text, copyText, openMenu }: { text: string; copyText: (text: string, toastText?: string) => void; openMenu: () => void }) {
  return (
    <div className="dl2-message-tools">
      <button type="button" onClick={() => copyText(text)} aria-label="复制"><CopyIcon /></button>
      <button type="button" onClick={openMenu} aria-label="更多操作"><MoreIcon /></button>
    </div>
  );
}

function PrecisionWarning({ onAction }: { onAction: () => void }) {
  return (
    <div className="dl2-precision">
      <strong>孩子视角待补充</strong>
      <div>{precisionText}</div>
      <button type="button" onClick={onAction}>发给孩子填写</button>
    </div>
  );
}

function CardActions({ labels, showToast, openFeedback }: { labels: string[]; showToast: (text: string) => void; openFeedback: () => void }) {
  return (
    <div className="dl2-card-actions">
      {labels.map((label) => (
        <button
          key={label}
          type="button"
          onClick={() => {
            if (label.includes("不像") || label.includes("不太像")) openFeedback();
            else if (label.includes("补充")) showToast("可以继续补充");
            else if (label.includes("存") || label.includes("保存")) showToast("已存到小档案");
            else showToast("已记录反馈");
          }}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function GrowthSignalCard({ showPrecision, openChildCard, showToast, openFeedback }: Parameters<typeof MessageRenderer>[0]) {
  return (
    <div className="dl2-message ai">
      <article className="dl2-card">
        <CardHeader title="这次记录到的信号" subtitle="基于这次描述整理，后面可以继续调整" mark="记" />
        <CardSection title="这次记录到的变化">孩子今天没有被催就自己写了一会儿作业，这是一个积极信号，说明他并不是完全没有行动能力。</CardSection>
        <CardSection title="可能说明什么">相比“被盯着做”，他可能更容易在压力较低、边界清楚的时候进入状态。</CardSection>
        <CardSection title="值得继续观察的点">接下来可以看，他是不是在“没有被连续催促”的情况下更容易开始。</CardSection>
        <CardSection title="可以轻轻做的一步">今晚先不急着追加任务，也不用表扬太满，只让他感受到“主动开始”这件事被看见了。</CardSection>
        <CardActions labels={["有点像", "不太像", "补充一点", "存到小档案"]} showToast={showToast} openFeedback={openFeedback} />
      </article>
      {showPrecision && <PrecisionWarning onAction={openChildCard} />}
    </div>
  );
}

function ChildUnderstandingCard({ showPrecision, openChildCard, showToast, openFeedback }: Parameters<typeof MessageRenderer>[0]) {
  return (
    <div className="dl2-message ai">
      <article className="dl2-card featured">
        <CardHeader title="孩子理解卡" subtitle="基于目前聊到的信息整理，后面可以继续调整" mark="档" />
        <CardSection title="我目前看到的孩子状态">孩子更像是“启动前阻力很大，但进入状态后并非完全不能做”。这件事先不宜简单看成懒或不自觉。</CardSection>
        <CardSection title="容易被误解的地方">表面看是拖作业，背后更值得看的是：他可能已经默认“做完一件事不代表真的结束”，所以开始前会先拖住一点主动权。</CardSection>
        <CardSection title="孩子可能真正看重的东西">他比较在意任务边界：什么叫完成，完成后能不能休息，会不会又被临时追加。</CardSection>
        <CardSection title="你们容易卡住的场景">家长越担心漏洞越想补，孩子越觉得“反正做完还有新的”，于是启动更慢。</CardSection>
        <CardSection title="接下来先观察一个点">先看：他拖得最明显的时候，是开始前，还是已经写了一段之后。</CardSection>
        <CardActions labels={["有点像我家孩子", "有些地方不像", "我补充一点", "保存到小档案"]} showToast={showToast} openFeedback={openFeedback} />
      </article>
      {showPrecision && <PrecisionWarning onAction={openChildCard} />}
    </div>
  );
}

function RehearsalCard({ showPrecision, openChildCard, copyText, showToast }: Parameters<typeof MessageRenderer>[0]) {
  const script =
    "我不是想一下子把手机全收掉，我想先和你确认一件事：你每天真正能休息的时间应该怎么安排，手机也在里面，但不能把睡觉和第二天状态拖垮。我们先试一个你也能接受的版本。";
  return (
    <div className="dl2-message ai">
      <article className="dl2-card">
        <CardHeader title="先帮你过一遍" subtitle="把准备说的话先放在孩子视角里看一看" mark="预" />
        <CardSection title="孩子可能怎么接">如果他最近比较在意“写完后能不能真的休息”，他可能不会先听到“半小时规则”，而是先感觉自己的休息时间又被压缩了。</CardSection>
        <CardSection title="这句话哪里容易卡住">一上来直接定时长，容易让他把这件事理解成“家长又要控制我”。</CardSection>
        <div className="dl2-script-box">
          <div className="dl2-script-head">
            <span>更稳一点的说法</span>
            <button type="button" onClick={() => copyText(script, "已复制这段话")}>复制</button>
          </div>
          <p>{script}</p>
        </div>
        <CardSection title="需要避免的一点">不要把这次谈话开头放在“你就是自控力差”上。</CardSection>
        <CardActions labels={["有点像", "不太像", "补充一点", "存到小档案"]} showToast={showToast} openFeedback={() => showToast("可以补充孩子的反应")} />
      </article>
      {showPrecision && <PrecisionWarning onAction={openChildCard} />}
    </div>
  );
}

function CorrectionMessage({ showPrecision, openChildCard, setMiniNote }: Parameters<typeof MessageRenderer>[0]) {
  return (
    <div className="dl2-message ai">
      <div className="dl2-ai-bubble correction">
        <div className="dl2-capsule">我改一下前面的看法</div>
        <TextBlock text="前面我更倾向于把手机看成逃避学习，但最近几次记录放在一起看，它更常出现在“完成一段任务之后”。这个点会改变判断：它可能不只是逃避，更像是在确认自己有没有真正的休息时间。" />
      </div>
      <button className="dl2-memory-note" type="button" onClick={() => setMiniNote("这次调整的是：手机相关判断从“逃避学习”改为“休息边界”方向继续观察。")}>
        已调整：手机相关判断从“逃避学习”改为“休息边界”方向继续观察
      </button>
      {showPrecision && <PrecisionWarning onAction={openChildCard} />}
    </div>
  );
}

function CardHeader({ title, subtitle, mark }: { title: string; subtitle: string; mark: string }) {
  return (
    <div className="dl2-card-head">
      <div className="dl2-card-mark"><CardMarkIcon mark={mark} /></div>
      <div>
        <h3>{title}</h3>
        <p>{subtitle}</p>
      </div>
    </div>
  );
}

function CardSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="dl2-card-section">
      <h4>{title}</h4>
      <p>{children}</p>
    </section>
  );
}

function ChildProfilePage({ status, navigate, showToast }: { status: QuestionnaireStatus; navigate: (view: AppView) => void; showToast: (text: string) => void }) {
  const expandedSections = profileSections.slice(0, 3);
  const foldedSections = profileSections.slice(3);
  return (
    <div className="dl2-phone">
      <TopBar title="孩子小档案" subtitle="这些内容会随着对话和记录慢慢更新，也可以随时修正。" navigate={navigate} backTo="chat" />
      <main className="dl2-page-scroll dl2-profile-page">
        <div className="dl2-status-strip">
          <div className="dl2-status-main">已慢慢记下 18 次变化</div>
          <div className="dl2-status-sub">其中 6 个特点正在变清楚，4 个点还在观察中。</div>
          <span className={status === "completed" ? "done" : "pending"}>{status === "completed" ? "孩子视角已补充" : "孩子视角待补充"}</span>
        </div>
        {expandedSections.map((section) => (
          <section className="dl2-profile-section" key={section.title}>
            <div className="dl2-section-title"><span>{section.title}</span><em>{section.count}</em></div>
            {section.items.map((item) => (
              <ProfileItemCard key={item[0]} item={item} navigate={navigate} showToast={showToast} />
            ))}
          </section>
        ))}
        <section className="dl2-profile-section">
          <div className="dl2-section-title"><span>更多观察</span><em>{foldedSections.length}</em></div>
          <div className="dl2-folded-grid">
            {foldedSections.map((section) => (
              <button className="dl2-folded-section" key={section.title} type="button" onClick={() => showToast("已保留折叠分区，后续可展开")}>
                <span>{section.title}</span>
                <em>{section.count} 条</em>
              </button>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}

function ProfileItemCard({ item, navigate, showToast }: { item: string[]; navigate: (view: AppView) => void; showToast: (text: string) => void }) {
  const [showMore, setShowMore] = useState(false);
  const statusLabel = item[3] === "较高" ? "基本稳定" : item[3] === "中等" ? "还在观察" : "需要再看几次";
  return (
    <article className="dl2-profile-card">
      <div className="dl2-profile-head">
        <div className="dl2-profile-kicker">{item[0]}</div>
        <button type="button" onClick={() => setShowMore((prev) => !prev)} aria-label="更多校准操作"><MoreIcon /></button>
      </div>
      <p>{item[1]}</p>
      <div className="dl2-profile-source">{item[2]}</div>
      <div className="dl2-profile-confidence">{statusLabel}</div>
      <div className="dl2-card-actions">
        <button type="button" onClick={() => navigate("profile-detail")}>查看来源</button>
      </div>
      {showMore && (
        <div className="dl2-card-actions quiet">
          <button type="button" onClick={() => showToast("已打开反馈")}>不太准确</button>
          <button type="button" onClick={() => showToast("可以补充一点")}>补充一点</button>
          <button type="button" onClick={() => showToast("已暂时降低参考权重")}>先不参考</button>
        </div>
      )}
    </article>
  );
}

function ProfileDetailPage({ navigate, showToast }: { navigate: (view: AppView) => void; showToast: (text: string) => void }) {
  return (
    <div className="dl2-phone">
      <TopBar title="观察详情" subtitle="这条理解可以继续修正，不是一锤定音。" navigate={navigate} backTo="profile" />
      <main className="dl2-page-scroll dl2-profile-page dl2-detail-page">
        <DetailBlock title="当前理解">孩子在压力较低、边界清楚时更容易开始学习。</DetailBlock>
        <DetailBlock title="相关场景">作业启动、手机使用、睡前安排。</DetailBlock>
        <DetailBlock title="怎么看出来的">
          相关记录 1｜5 月 14 日
          {"\n"}你提到：孩子没有被催就自己写了一会儿作业。
          {"\n"}系统记录：低压力状态下，孩子存在主动启动能力。
          {"\n\n"}相关记录 2｜5 月 16 日
          {"\n"}你提到：孩子写完一段后拿手机，被提醒后明显不高兴。
          {"\n"}系统记录：孩子可能在意完成后的休息边界。
        </DetailBlock>
        <DetailBlock title="目前可信度">较高</DetailBlock>
        <DetailBlock title="还要继续看的点">是所有任务都这样，还是只对临时追加任务敏感。</DetailBlock>
        <DetailBlock title="影响哪些判断">后续沟通预演、作业安排、手机规则建议都会参考。</DetailBlock>
        <div className="dl2-page-actions">
          {["不太准确", "补充一点", "先不参考", "删除这条观察"].map((item) => (
            <button key={item} type="button" onClick={() => showToast(item === "删除这条观察" ? "已进入删除确认" : "已记录操作")}>{item}</button>
          ))}
        </div>
      </main>
    </div>
  );
}

function ObservationRecordsPage({ navigate }: { navigate: (view: AppView) => void }) {
  const filters = ["全部", "成长信号", "沟通预演", "判断调整", "周小观察"];
  return (
    <div className="dl2-phone">
      <TopBar title="观察记录" subtitle="这里保存的是对孩子变化的阶段性整理。" navigate={navigate} backTo="chat" />
      <main className="dl2-page-scroll dl2-records-page timeline">
        <div className="dl2-record-filters">
          {filters.map((filter, index) => (
            <button className={cn("dl2-mini-chip", index === 0)} key={filter} type="button">{filter}</button>
          ))}
        </div>
        {records.map((record) => (
          <button className="dl2-timeline-card" key={record[0]} type="button" onClick={() => navigate("record-detail")}>
            <small>{record[0].split("｜")[0]}</small>
            <strong>{record[0]}</strong>
            <span>{record[1]}</span>
            <em>查看详情 ›</em>
          </button>
        ))}
      </main>
    </div>
  );
}

function RecordDetailPage({ navigate, copyText, showToast }: { navigate: (view: AppView) => void; copyText: (text: string, toastText?: string) => void; showToast: (text: string) => void }) {
  const text = "孩子主动开始写作业，这说明低压力状态下存在启动能力。";
  return (
    <div className="dl2-phone">
      <TopBar title="记录详情" subtitle="这条记录已经沉淀到孩子小档案。" navigate={navigate} backTo="records" />
      <main className="dl2-page-scroll dl2-records-page dl2-detail-page">
        <DetailBlock title="原始记录">昨天他没有被催，自己写了一会儿作业。</DetailBlock>
        <DetailBlock title="AI 整理">{text}</DetailBlock>
        <DetailBlock title="已沉淀标签">主动启动、低压力、任务边界、待观察</DetailBlock>
        <DetailBlock title="相关小档案">学习状态｜启动方式；有效经验｜提前约定。</DetailBlock>
        <div className="dl2-page-actions">
          <button type="button" onClick={() => copyText(text)}>复制</button>
          <button type="button" onClick={() => showToast("已打开修正面板")}>修正</button>
          <button type="button" onClick={() => showToast("已进入删除确认")}>删除</button>
        </div>
      </main>
    </div>
  );
}

function ChildQuestionnaireParentPage({
  navigate,
  status,
  link,
  generateLink,
  copyText,
  showToast,
}: {
  navigate: (view: AppView) => void;
  status: QuestionnaireStatus;
  link: string;
  generateLink: () => void;
  copyText: (text: string, toastText?: string) => void;
  showToast: (text: string) => void;
}) {
  return (
    <div className="dl2-phone">
      <TopBar title="孩子学习小档案" subtitle="用几个轻问题，补充孩子自己的感受。" navigate={navigate} backTo="chat" />
      <main className="dl2-page-scroll">
        <article className="dl2-large-card">
          <h2>这不是测评，也不会给孩子贴标签。</h2>
          <p>它只是帮助后续判断更贴近孩子自己。问题会围绕学习启动、被催反应、压力恢复和沟通偏好展开。</p>
          <div className="dl2-status-strip">{status === "link_created" ? "等待孩子填写" : status === "completed" ? "孩子视角已补充" : "未生成填写链接"}</div>
          {link && <div className="dl2-link-box">{link}</div>}
          <div className="dl2-page-actions stacked">
            <button type="button" onClick={generateLink}>生成填写链接</button>
            <button type="button" onClick={() => copyText(link || "https://demo.yihe.site/child-card/abc123")}>复制链接</button>
            <button type="button" onClick={() => showToast("已生成二维码")}>生成二维码</button>
            <button type="button" onClick={() => showToast("已打开微信分享提示")}>分享到微信</button>
            <button type="button" onClick={() => navigate("child-form")}>预览孩子端填写</button>
            <button type="button" onClick={() => navigate("child-summary")}>查看孩子视角摘要</button>
          </div>
        </article>
      </main>
    </div>
  );
}

function ChildQuestionnaireForm({
  navigate,
  index,
  setIndex,
  answers,
  setAnswers,
  finish,
}: {
  navigate: (view: AppView) => void;
  index: number;
  setIndex: (index: number) => void;
  answers: Record<number, string>;
  setAnswers: React.Dispatch<React.SetStateAction<Record<number, string>>>;
  finish: () => void;
}) {
  const [question, options] = childQuestions[index];
  const pct = Math.round(((index + 1) / childQuestions.length) * 100);
  return (
    <div className="dl2-phone child">
      <TopBar title="我的学习小档案" subtitle="没有标准答案，选你更像的情况就行。" navigate={navigate} backTo="child-card" />
      <main className="dl2-page-scroll">
        <div className="dl2-progress"><span style={{ width: `${pct}%` }} /></div>
        <article className="dl2-large-card">
          <p className="dl2-child-note">这不是考试，也不会给你贴标签。它只是帮助大人更准确地理解你。</p>
          <h2>{question}</h2>
          <div className="dl2-options">
            {options.map((option) => (
              <button key={option} className={cn("dl2-option", answers[index] === option)} type="button" onClick={() => setAnswers((prev) => ({ ...prev, [index]: option }))}>
                {option}
              </button>
            ))}
          </div>
        </article>
        <div className="dl2-page-actions">
          <button type="button" disabled={index === 0} onClick={() => setIndex(Math.max(0, index - 1))}>上一步</button>
          {index < childQuestions.length - 1 ? (
            <button type="button" onClick={() => setIndex(index + 1)}>下一步</button>
          ) : (
            <button type="button" onClick={finish}>完成</button>
          )}
        </div>
      </main>
    </div>
  );
}

function ChildQuestionnaireCompletePage({ navigate }: { navigate: (view: AppView) => void }) {
  return (
    <div className="dl2-phone child">
      <main className="dl2-page-scroll center">
        <article className="dl2-large-card complete">
          <div className="dl2-card-mark">好</div>
          <h2>已完成你的学习小档案。</h2>
          <p>后面大人在和你沟通时，会更容易知道哪些方式你更能接受，哪些方式可能会让你更烦。</p>
          <button type="button" onClick={() => navigate("child-summary")}>完成</button>
        </article>
      </main>
    </div>
  );
}

function ChildPerspectiveSummary({ navigate }: { navigate: (view: AppView) => void }) {
  return (
    <div className="dl2-phone">
      <TopBar title="孩子学习小档案已完成" subtitle="孩子视角会帮助后续判断更贴近他本人。" navigate={navigate} backTo="child-card" />
      <main className="dl2-page-scroll">
        <article className="dl2-card">
          <CardHeader title="已补充 4 条孩子视角信息" subtitle="这些内容会进入孩子小档案" mark="孩" />
          {["孩子更在意完成后的休息边界", "对临时加任务比较敏感", "更能接受提前约定", "考试前更容易表现为话少"].map((item) => (
            <div className="dl2-summary-row" key={item}>{item}</div>
          ))}
          <button className="dl2-memory-note summary" type="button">已更新孩子小档案 4 条</button>
        </article>
      </main>
    </div>
  );
}

function SettingsPage({
  navigate,
  showToast,
  selectedPrefs,
  setSelectedPrefs,
  reminderEnabled,
  setReminderEnabled,
  openConfirm,
}: {
  navigate: (view: AppView) => void;
  showToast: (text: string) => void;
  selectedPrefs: string[];
  setSelectedPrefs: React.Dispatch<React.SetStateAction<string[]>>;
  reminderEnabled: boolean;
  setReminderEnabled: (value: boolean) => void;
  openConfirm: () => void;
}) {
  const prefs = ["简洁一点", "多解释一点", "建议具体一点", "先判断，少安慰", "温和一点", "可以指出盲点"];
  return (
    <div className="dl2-phone">
      <TopBar title="设置" subtitle="把系统调整成更适合你的陪伴方式。" navigate={navigate} backTo="chat" />
      <main className="dl2-page-scroll">
        <section className="dl2-settings-card">
          <h2>我的沟通偏好</h2>
          <p>你可以调整我和你说话的方式。</p>
          <div className="dl2-chip-grid">
            {prefs.map((pref) => (
              <button
                key={pref}
                className={cn("dl2-chip", selectedPrefs.includes(pref))}
                type="button"
                onClick={() =>
                  setSelectedPrefs((prev) => (prev.includes(pref) ? prev.filter((item) => item !== pref) : [...prev, pref]))
                }
              >
                {pref}
              </button>
            ))}
          </div>
          <div className="dl2-style-preview">当前风格：我会多说明判断依据，建议会尽量具体，但不会每次都给行动清单。</div>
        </section>
        <section className="dl2-settings-card">
          <h2>轻提醒</h2>
          <p>只在你愿意的时候，帮你记得回来看看。</p>
          <label className="dl2-toggle-row">
            <span>是否开启</span>
            <input type="checkbox" checked={reminderEnabled} onChange={(e) => setReminderEnabled(e.target.checked)} />
          </label>
          <SettingChoice title="提醒频率" options={["不主动提醒", "每周一次", "只在保存建议后提醒"]} showToast={showToast} />
          <SettingChoice title="提醒类型" options={["观察变化", "预演反馈", "周小观察"]} showToast={showToast} />
          <SettingChoice title="提醒时间" options={["晚上", "周末", "自定义"]} showToast={showToast} />
          <div className="dl2-reminder-preview">上次说到孩子对“完成后能不能真的休息”比较敏感。这两天如果有类似情况，可以回来简单记一句。</div>
        </section>
        <section className="dl2-settings-card">
          <h2>数据与隐私</h2>
          {["导出我的对话", "导出孩子小档案", "删除单条记录", "清空孩子小档案", "关闭孩子小卡链接", "删除全部家庭数据"].map((item) => (
            <button className="dl2-privacy-btn" type="button" key={item} onClick={item.includes("删除") || item.includes("清空") ? openConfirm : () => showToast("已处理")}>
              {item}
            </button>
          ))}
        </section>
      </main>
    </div>
  );
}

function SettingChoice({ title, options, showToast }: { title: string; options: string[]; showToast: (text: string) => void }) {
  const [selected, setSelected] = useState(options[0]);
  return (
    <div className="dl2-setting-choice">
      <div>{title}</div>
      <div>
        {options.map((option) => (
          <button
            key={option}
            className={cn("dl2-mini-chip", selected === option)}
            type="button"
            onClick={() => {
              setSelected(option);
              showToast("已更新设置");
            }}
          >
            {option}
          </button>
        ))}
      </div>
    </div>
  );
}

function DetailBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="dl2-detail-block">
      <h2>{title}</h2>
      <p>{children}</p>
    </section>
  );
}

function BottomActionSheet({ isOpen, onClose, onAction }: { isOpen: boolean; onClose: () => void; onAction: (action: string) => void }) {
  const actions = [
    ["record", "记", "记录一次孩子最近的变化", "把一件小事整理成成长信号"],
    ["rehearsal", "预", "我想和孩子说一件事，先帮我过一遍", "提前看看孩子可能怎么接"],
    ["child-card", "孩", "发给孩子填写学习小档案", "补充孩子自己的感受"],
    ["continue", "续", "继续上次聊到的事", "接上之前的线索继续看"],
    ["profile", "档", "看看最近记下了什么", "进入孩子小档案"],
  ];
  return (
    <Sheet isOpen={isOpen} onClose={onClose}>
      <div className="dl2-sheet-title">你想先做哪件事？</div>
      {actions.map(([key, mark, title, desc]) => (
        <button className="dl2-sheet-row" type="button" key={key} onClick={() => onAction(key)}>
          <span><CardMarkIcon mark={mark} /></span>
          <div><strong>{title}</strong><em>{desc}</em></div>
        </button>
      ))}
    </Sheet>
  );
}

function MessageActionSheet({
  isOpen,
  onClose,
  onCopy,
  onFeedback,
}: {
  isOpen: boolean;
  onClose: () => void;
  onCopy: () => void;
  onFeedback: (type: "like" | "unlike" | "add" | "save") => void;
}) {
  return (
    <Sheet isOpen={isOpen} onClose={onClose}>
      <div className="dl2-sheet-title">这条回复</div>
      <button className="dl2-sheet-simple" type="button" onClick={onCopy}>复制</button>
      <button className="dl2-sheet-simple" type="button" onClick={() => onFeedback("like")}>有点像</button>
      <button className="dl2-sheet-simple" type="button" onClick={() => onFeedback("unlike")}>不太像</button>
      <button className="dl2-sheet-simple" type="button" onClick={() => onFeedback("add")}>补充一点</button>
      <button className="dl2-sheet-simple" type="button" onClick={() => onFeedback("save")}>存到小档案</button>
    </Sheet>
  );
}

function FeedbackSheet({ isOpen, onClose, showToast }: { isOpen: boolean; onClose: () => void; showToast: (text: string) => void }) {
  return (
    <Sheet isOpen={isOpen} onClose={onClose}>
      <div className="dl2-sheet-title">哪里不太像？</div>
      <textarea className="dl2-feedback-input" placeholder="比如：他不是不想开始，是最近真的太累了..." />
      <button className="dl2-primary-btn" type="button" onClick={() => { onClose(); showToast("已记录反馈"); }}>提交反馈</button>
    </Sheet>
  );
}

function ConfirmSheet({ isOpen, onClose, showToast }: { isOpen: boolean; onClose: () => void; showToast: (text: string) => void }) {
  return (
    <Sheet isOpen={isOpen} onClose={onClose}>
      <div className="dl2-sheet-title">确认这个操作？</div>
      <p className="dl2-sheet-desc">原型中不会真的删除数据，只展示确认流程。</p>
      <button className="dl2-primary-btn" type="button" onClick={() => { onClose(); showToast("已确认"); }}>确认</button>
    </Sheet>
  );
}

function Sheet({ isOpen, onClose, children }: { isOpen: boolean; onClose: () => void; children: React.ReactNode }) {
  if (!isOpen) return null;
  return (
    <div className="dl2-sheet-mask" onClick={onClose}>
      <div className="dl2-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="dl2-sheet-handle" />
        {children}
      </div>
    </div>
  );
}

function OnboardingQuestionnaireModal({ isOpen, onChildCard, onSkip }: { isOpen: boolean; onChildCard: () => void; onSkip: () => void }) {
  if (!isOpen) return null;
  return (
    <div className="dl2-sheet-mask onboarding">
      <div className="dl2-sheet onboarding-panel">
        <div className="dl2-card-mark"><CardMarkIcon mark="档" /></div>
        <h2>先补一点孩子自己的感受</h2>
        <p className="lead">孩子填写后，后续判断会更贴近他本人。</p>
        <p>问题不会给孩子贴标签，也不会生成“好/不好”的评价，只是了解孩子面对学习、压力、催促和沟通时更像哪种反应。</p>
        <strong>可以先聊；补充孩子视角后，孩子理解卡、成长记录和沟通预演会更稳。</strong>
        <small>未填写时，系统仍可根据家长描述进行初步判断，但准确度会受限。</small>
        <button className="dl2-primary-btn" type="button" onClick={onChildCard}>发给孩子填写</button>
        <button className="dl2-secondary-btn" type="button" onClick={onSkip}>我先自己聊，稍后再填</button>
      </div>
    </div>
  );
}

function MiniMemoryNote({ detail, onClose }: { detail: string | null; onClose: () => void }) {
  if (!detail) return null;
  return (
    <div className="dl2-mini-note" onClick={onClose}>
      <strong>这次记下的是：</strong>
      <span>{detail}</span>
    </div>
  );
}

function Toast({ text }: { text: string }) {
  if (!text) return null;
  return <div className="dl2-toast">{text}</div>;
}

function CopyIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="8" y="8" width="11" height="11" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

function MoreIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 12h.01M12 12h.01M19 12h.01" />
    </svg>
  );
}

function BookmarkIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M7 4h10a1 1 0 0 1 1 1v15l-6-3-6 3V5a1 1 0 0 1 1-1Z" />
    </svg>
  );
}

function CardMarkIcon({ mark }: { mark: string }) {
  if (mark === "预") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M5 5h14v10H8l-3 3V5Z" />
        <path d="M9 9h6M9 12h4" />
      </svg>
    );
  }
  if (mark === "记") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M6 4h12v16H6z" />
        <path d="M9 8h6M9 12h6M9 16h3" />
      </svg>
    );
  }
  return <BookmarkIcon />;
}

function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Z" />
      <path d="M18 11v1a6 6 0 0 1-12 0v-1M12 18v3M9 21h6" />
    </svg>
  );
}

function KeyboardIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="3" y="6" width="18" height="12" rx="2" />
      <path d="M7 10h.01M10 10h.01M13 10h.01M16 10h.01M7 14h10" />
    </svg>
  );
}
