"use client";

import React, { memo, useCallback, useEffect, useMemo, useRef } from "react";

export interface Message {
  id: string;
  role: "user" | "ai";
  content: string;
  timestamp: string;
}

interface ChatAreaProps {
  messages: Message[];
  isLoading: boolean;
  showWelcome: boolean;
  retrievalText?: string;
  onPlayTTS?: (text: string, msgId: string) => void;
  playingMsgId?: string | null;
}

function stripHtml(html: string): string {
  if (typeof document === "undefined") return html.replace(/<[^>]+>/g, "");
  const el = document.createElement("div");
  el.innerHTML = html;
  return el.textContent ?? "";
}

function CopyIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="8" y="8" width="12" height="12" rx="2" />
      <path d="M4 16V6a2 2 0 0 1 2-2h10" />
    </svg>
  );
}

function SpeakerIcon({ active }: { active: boolean }) {
  return active ? (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="6" y="4" width="4" height="16" />
      <rect x="14" y="4" width="4" height="16" />
    </svg>
  ) : (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 9v6h4l5 4V5L8 9H4z" />
      <path d="M16 9.5a4 4 0 0 1 0 5" />
      <path d="M18.5 7a7 7 0 0 1 0 10" />
    </svg>
  );
}

const MessageItem = memo(function MessageItem({
  msg,
  onPlayTTS,
  isPlaying,
}: {
  msg: Message;
  onPlayTTS?: (text: string, msgId: string) => void;
  isPlaying: boolean;
}) {
  const plainText = useMemo(() => (msg.role === "ai" ? stripHtml(msg.content) : msg.content), [msg.content, msg.role]);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(plainText);
    } catch {
      // Clipboard permission can fail on some browsers; silently keep the UI stable.
    }
  }, [plainText]);

  return (
    <div className={`msg-row ${msg.role}`}>
      <div className="msg-content-wrap">
        <div className="msg-bubble">
          {msg.role === "ai" ? (
            <div className="msg-content" dangerouslySetInnerHTML={{ __html: msg.content }} />
          ) : (
            msg.content
          )}
        </div>
        {msg.role === "ai" && msg.content && (
          <div className="msg-actions" aria-label="消息操作">
            {onPlayTTS && (
              <button
                className={`msg-action-btn ${isPlaying ? "active" : ""}`}
                onClick={() => onPlayTTS(msg.content, msg.id)}
                type="button"
                aria-label={isPlaying ? "停止播放" : "播放语音"}
              >
                <SpeakerIcon active={isPlaying} />
              </button>
            )}
            <button className="msg-action-btn" onClick={handleCopy} type="button" aria-label="复制">
              <CopyIcon />
            </button>
          </div>
        )}
        <div className="msg-meta">{msg.timestamp}</div>
      </div>
    </div>
  );
});

export default function ChatArea({ messages, isLoading, showWelcome, retrievalText, onPlayTTS, playingMsgId }: ChatAreaProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    });
    return () => cancelAnimationFrame(frame);
  }, [messages, isLoading]);

  return (
    <div className="chat-area" ref={scrollRef}>
      {showWelcome && (
        <div className="welcome-hint">
          <div className="welcome-icon">Hi</div>
          <div className="welcome-title">可以从孩子最近的一件小事说起</div>
          <div>开心的、别扭的、说不清的都可以。</div>
          <div>我会陪你慢慢把孩子的状态和家庭相处节奏看清楚。</div>
        </div>
      )}

      {messages.map((msg) => (
        <MessageItem key={msg.id} msg={msg} onPlayTTS={onPlayTTS} isPlaying={playingMsgId === msg.id} />
      ))}

      {isLoading && (
        <div className="msg-row ai">
          <div className="msg-content-wrap">
            <div className="retrieval-bubble">
              <span>{retrievalText || "正在查询清北学生资料，已查询 1 位"}</span>
              <span className="retrieval-dots" aria-hidden="true">
                <i />
                <i />
                <i />
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
