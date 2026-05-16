"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DiagnosisData, PossibleMeaning, SuggestedReplies } from "@/lib/diagnosis";

interface DiagnosisModalProps {
  isOpen: boolean;
  onClose: () => void;
  diagnosis: DiagnosisData | null;
  onContinue?: () => void;
}

type ReplyTab = "conservative" | "progressive" | "boundary";

const REPLY_TABS: Array<{ key: ReplyTab; label: string }> = [
  { key: "conservative", label: "稳妥版" },
  { key: "progressive", label: "推进版" },
  { key: "boundary", label: "边界版" },
];

function splitTextList(text?: string): string[] {
  return (
    text
      ?.split(/\n|[；;]/)
      .map((item) => item.replace(/^\s*(?:[-*•·]|\d+[.、)）]|[①②③④⑤⑥⑦⑧⑨⑩])\s*/, "").trim())
      .filter(Boolean) ?? []
  );
}

function isPossibleMeaningArray(value: DiagnosisData["possibleMeanings"]): value is PossibleMeaning[] {
  return Array.isArray(value);
}

function isSuggestedRepliesObject(value: DiagnosisData["suggestedReplies"]): value is SuggestedReplies {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function progressClass(percentage: number): string {
  if (percentage >= 60) return "dc-prob-fill dc-prob-fill-high";
  if (percentage >= 30) return "dc-prob-fill dc-prob-fill-mid";
  return "dc-prob-fill dc-prob-fill-low";
}

function BulletList({ items }: { items: string[] }) {
  return (
    <>
      {items.map((item) => (
        <div key={item} className="dc-bullet">
          <div className="dc-bullet-dot" />
          <div>{item}</div>
        </div>
      ))}
    </>
  );
}

export default function DiagnosisModal({ isOpen, onClose, diagnosis, onContinue }: DiagnosisModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const startY = useRef(0);
  const currentY = useRef(0);
  const [replyTab, setReplyTab] = useState<ReplyTab>("conservative");

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    startY.current = e.touches[0].clientY;
    currentY.current = startY.current;
  }, []);

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    currentY.current = e.touches[0].clientY;
    const diff = currentY.current - startY.current;
    if (diff > 0 && panelRef.current) {
      panelRef.current.style.transform = `translateY(${diff}px)`;
    }
  }, []);

  const handleTouchEnd = useCallback(() => {
    const diff = currentY.current - startY.current;
    if (diff > 80) onClose();
    if (panelRef.current) panelRef.current.style.transform = "";
  }, [onClose]);

  useEffect(() => {
    document.body.style.overflow = isOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  useEffect(() => {
    if (isOpen) setReplyTab("conservative");
  }, [isOpen, diagnosis]);

  const possibleMeanings = diagnosis?.possibleMeanings;
  const suggestedReplies = diagnosis?.suggestedReplies;
  const evidenceItems = useMemo(() => splitTextList(diagnosis?.evidenceBasis), [diagnosis?.evidenceBasis]);
  const suggestionItems = useMemo(() => splitTextList(diagnosis?.suggestions), [diagnosis?.suggestions]);

  if (!diagnosis) return null;

  return (
    <div className={`modal-overlay ${isOpen ? "active" : ""}`} onClick={onClose}>
      <div
        className="modal-panel"
        ref={panelRef}
        onClick={(e) => e.stopPropagation()}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        <div className="modal-close">
          <div className="modal-close-line" />
          <div className="modal-close-text">下滑关闭</div>
        </div>
        <div className="modal-title">诊断卡</div>

        <div className="dc-card dc-card-purple">
          <div className="dc-tag dc-tag-purple">家长盲点</div>
          <div className="dc-text">{diagnosis.blindSpot || "暂无家长盲点信息"}</div>
        </div>
        <div className="dc-card dc-card-gray">
          <div className="dc-tag dc-tag-gray">核心机制</div>
          <div className="dc-text">{diagnosis.coreMechanism || "暂无核心机制信息"}</div>
        </div>
        <div className="dc-card dc-card-orange">
          <div className="dc-tag dc-tag-orange">行为保护</div>
          <div className="dc-text">{diagnosis.behaviorProtection || "暂无行为保护信息"}</div>
        </div>

        <div className="dc-card dc-card-gray">
          <div className="dc-tag dc-tag-indigo">可能含义</div>
          {isPossibleMeaningArray(possibleMeanings) && possibleMeanings.length > 0 ? (
            <>
              {possibleMeanings.map((item) => (
                <div key={`${item.label}-${item.percentage}`} className="dc-prob-item">
                  <div className="dc-prob-header">
                    <span>{item.label}</span>
                    <span className="dc-prob-pct">{item.percentage}%</span>
                  </div>
                  <div className="dc-prob-track">
                    <div className={progressClass(item.percentage)} style={{ width: isOpen ? `${item.percentage}%` : "0%" }} />
                  </div>
                  {item.description && <div className="dc-prob-desc">{item.description}</div>}
                </div>
              ))}
              <div className="dc-prob-note">概率基于当前对话，仍存在不确定性</div>
            </>
          ) : (
            <div className="dc-text">{typeof possibleMeanings === "string" && possibleMeanings ? possibleMeanings : "暂无可能含义信息"}</div>
          )}
        </div>

        <div className="dc-card dc-card-gray">
          <div className="dc-tag dc-tag-green">判断依据</div>
          {evidenceItems.length > 1 ? <BulletList items={evidenceItems} /> : <div className="dc-text">{diagnosis.evidenceBasis || "暂无判断依据"}</div>}
        </div>

        <div className="dc-card dc-card-risk">
          <div className="dc-tag dc-tag-risk">风险提示</div>
          <div className="dc-risk-row">
            <span className="dc-risk-icon" aria-hidden="true">!</span>
            <div className="dc-text">{diagnosis.riskWarning || "暂无风险提示"}</div>
          </div>
        </div>

        <div className="dc-card dc-card-replies">
          <div className="dc-tag dc-tag-gray">建议回复</div>
          {isSuggestedRepliesObject(suggestedReplies) ? (
            <>
              <div className="dc-reply-tabs">
                {REPLY_TABS.map((tab) => (
                  <button
                    key={tab.key}
                    type="button"
                    className={`dc-reply-tab ${replyTab === tab.key ? "active" : ""}`}
                    onClick={() => setReplyTab(tab.key)}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
              <div className="dc-reply-panel">
                <div className="dc-reply-text">{suggestedReplies[replyTab]?.reply || "暂无该版本回复话术"}</div>
                {suggestedReplies[replyTab]?.reason && (
                  <div className="dc-reply-reason">
                    <span>推荐理由：</span>
                    {suggestedReplies[replyTab]?.reason}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="dc-text">{typeof suggestedReplies === "string" && suggestedReplies ? suggestedReplies : "暂无建议回复"}</div>
          )}
        </div>

        <div className="dc-card dc-card-suggestions">
          <div className="dc-tag dc-tag-suggestions">改善建议</div>
          {suggestionItems.length > 1 ? <BulletList items={suggestionItems} /> : <div className="dc-text">{diagnosis.suggestions || "暂无改善建议"}</div>}
        </div>

        <div className="dc-disclaimer">以上分析仅供参考，不构成专业心理诊断。如有需要，请咨询专业心理咨询师。</div>
        <button className="dc-continue-btn" onClick={onContinue} type="button">
          继续对话
        </button>
        <div className="dc-service-card">
          <div className="dc-service-title">清北伴学服务</div>
          <div className="dc-service-desc">由清北学长学姐1对1陪伴，帮你精准理解孩子的真实需求</div>
          <span className="dc-service-badge">1对1伴学</span>
          <span className="dc-service-badge">专业评估</span>
          <button className="dc-service-btn" type="button">了解详情</button>
        </div>
        <div className="dc-form-card">
          <div className="dc-form-title">预约伴学服务</div>
          <input className="dc-form-input" placeholder="手机号" type="tel" />
          <input className="dc-form-input" placeholder="姓名" />
          <input className="dc-form-input" placeholder="孩子年级" />
          <button className="dc-form-btn" type="button">提交预约</button>
        </div>
      </div>
    </div>
  );
}
