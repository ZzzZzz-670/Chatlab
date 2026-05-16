import argparse
import asyncio
import json
import re
import threading
import traceback
import logging
from typing import Any, Dict, Iterable, AsyncIterable, AsyncGenerator, Optional, Tuple
import cozeloop
import uvicorn
import time
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse, JSONResponse
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from coze_coding_utils.runtime_ctx.context import new_context, Context
from coze_coding_utils.helper import graph_helper
from coze_coding_utils.log.node_log import LOG_FILE
from coze_coding_utils.log.write_log import setup_logging, request_context
from coze_coding_utils.log.config import LOG_LEVEL
from coze_coding_utils.error.classifier import ErrorClassifier, classify_error
from coze_coding_utils.helper.stream_runner import AgentStreamRunner, WorkflowStreamRunner,agent_stream_handler,workflow_stream_handler, RunOpt

setup_logging(
    log_file=LOG_FILE,
    max_bytes=100 * 1024 * 1024, # 100MB
    backup_count=5,
    log_level=LOG_LEVEL,
    use_json_format=True,
    console_output=True
)

logger = logging.getLogger(__name__)
from coze_coding_utils.helper.agent_helper import to_stream_input
from coze_coding_utils.openai.handler import OpenAIChatHandler
from coze_coding_utils.log.parser import LangGraphParser
from coze_coding_utils.log.err_trace import extract_core_stack
from coze_coding_utils.log.loop_trace import init_run_config, init_agent_config
from storage.profile import profile_service


# 超时配置常量
TIMEOUT_SECONDS = 900  # 15分钟


# =====================================================================
# 共享文本过滤逻辑 — 被 _filter_chunk（/stream_run）和
# /v1/chat/completions 的流式/非流式过滤共用
# =====================================================================

def _filter_text(text: str) -> Tuple[str, bool]:
    """
    过滤AI回复中泄露的内部指令内容。
    返回 (过滤后文本, 是否包含诊断标记)。
    与 _filter_chunk 保持完全相同的过滤规则，但操作在纯文本上。
    """
    has_diagnosis = False
    if not text or not isinstance(text, str):
        return text, has_diagnosis

    # 检测诊断标记（必须在其他过滤之前）
    if 'DIAGNOSIS_READY' in text:
        has_diagnosis = True

    # 清理标记
    f = text.replace('###DIAGNOSIS_READY###', '').replace('DIAGNOSIS_READY', '')

    # 剥离内部诊断 JSON（<!--DIAGNOSIS_JSON {...}--> 或 ```diagnosis_json...```）
    f = re.sub(r'<!--DIAGNOSIS_JSON\s*\{[\s\S]*?\}\s*-->', '', f)
    f = re.sub(r'```diagnosis_json\s*\n[\s\S]*?\n```', '', f)

    # ---- 以下规则与 _filter_chunk 完全一致 ----
    # 过滤后台分析/推理过程
    f = re.sub(r'(?i)(分析[:：]|推理[:：]|后台[:：]|内部[:：]|步骤\d+[:：]|阶段\d+[:：]|流程\d+[:：]|运行顺序[:：]|信息轴[:：]|证据轴[:：]|分支[:：]|判断[:：]|裁决[:：]|追问优先级[:：]|家长可信度[:：]|孩子可信度[:：]|进度\d+[:：])[^\n]*', '', f)
    # 过滤冒号开头的分析行
    f = re.sub(r'(?i)^\s*(分析|推理|后台|内部|步骤|阶段|流程|运行顺序|信息轴|证据轴|分支|判断|裁决|追问优先级|家长可信度|孩子可信度|进度)\s*[:：][^\n]*$', '', f, flags=re.MULTILINE)
    # 过滤包含"当前已有证据"的分析句
    f = re.sub(r'(?i)当前已有证据[^。]*。?', '', f)
    # 过滤包含"还需要裁决"的句子
    f = re.sub(r'(?i)还需要裁决[^。]*。?', '', f)
    # 过滤包含"家长已回答"的句子
    f = re.sub(r'(?i)家长已回答[^。]*。?', '', f)
    # 过滤包含"最支持分支"的句子
    f = re.sub(r'(?i)最支持[^。]*分支[^。]*。?', '', f)
    # 过滤纯指令列表
    f = re.sub(r'(?i)^\s*(前台必须|后台|内部|你不需要|你必须|你应该在心里|思考框架|输出格式|语言风格)[^\n]*$', '', f, flags=re.MULTILINE)
    # 过滤JSON格式的分析
    f = re.sub(r'(?i)\{\s*"(分支|判断|裁决|证据|轴|进度|可信度)"[^}]*\}', '', f)
    # 过滤知识库检索标记
    f = re.sub(r'(?i)---\s*结果\s*\d+.*?---', '', f)
    f = re.sub(r'(?i)相关度[:：]\s*\d+\.\d+', '', f)
    f = re.sub(r'(?i)查询到.*?条结果', '', f)
    f = re.sub(r'(?i)结果\s*\d+', '', f)
    # 过滤Markdown表格分隔线
    f = re.sub(r'(?m)^\s*\|[\s\-:|]+\|\s*$', '', f)
    # 过滤包含大量管道符的表格行
    f = re.sub(r'(?m)^\s*\|[^\n]+\|\s*$', '', f)
    # 过滤内部术语
    f = re.sub(r'(?i)(后台想判断|家长标签|不直接采信|转成分支问题|前台必须|不要问|改问|安全废话|反证边界|黑名单)', '', f)
    # 过滤章节标题编号（仅过滤中文序号：一、二、三、等内部规则区块）
    f = re.sub(r'(?m)^\s*[一二三四五六七八九十百千零〇]+[、.．]\s*[^\n]+$', '', f)
    # 注：不再过滤 1. ② 等数字编号行，因为诊断卡（判断依据、改善建议）需要编号
    # 过滤判断性短句
    f = re.sub(r'(?i)家长[^，。]{0,20}(高控制|控制|没有结束感|努力被加码|被加码|自主权不足|被评价防御|表面配合|亲子污染)[^。]*。?', '', f)
    # 过滤内部规则短句
    f = re.sub(r'(?i)家长说[^，。]{0,20}就判断[^。]*。?', '', f)
    f = re.sub(r'(?i)全部解释成[^。]*。?', '', f)
    f = re.sub(r'(?i)顺着家长说[^。]*。?', '', f)
    f = re.sub(r'(?i)就默认解释成[^。]*。?', '', f)
    f = re.sub(r'(?i)或反过来[^。]*。?', '', f)
    # 过滤内部检查语句
    f = re.sub(r'(?i)是否[^，。\n]*?(问|检查|核实|确认|判断)[^。\n]*[。\n]?', '', f)
    # 过滤章节标题（仅过滤非诊断卡字段的标题）
    # 诊断卡字段名（如 ## 家长盲点）应保留给用户看
    _diag_labels_re = '|'.join(re.escape(l) for l in _ALL_LABELS)
    f = re.sub(r'(?m)^\s*#{1,6}\s*(?!' + _diag_labels_re + r')[^\n]+$', '', f)
    # 过滤特殊标记符号
    f = re.sub(r'[▒▌█▬▭◆◇■□]', '', f)
    # 清理多余空行
    f = re.sub(r'\n{3,}', '\n\n', f)

    return f, has_diagnosis


# =====================================================================
# 流式过滤状态机 — 跟踪 tool-call 序列和诊断标记
# =====================================================================

class _StreamFilterState:
    """跟踪 /v1/chat/completions 流式输出中的过滤状态"""
    __slots__ = ('in_tool_sequence', 'diagnosis_detected', 'full_content')

    def __init__(self):
        self.in_tool_sequence = False   # True = 处于 tool_calls → tool result 序列中
        self.diagnosis_detected = False  # 是否检测到 DIAGNOSIS_READY
        self.full_content = ""          # 累积的用户可见内容（用于提取结构化诊断）


def _filter_sse_chunk(sse_str: str, state: _StreamFilterState) -> Optional[str]:
    """
    对单个 SSE data 行做过滤。
    返回 None 表示整行跳过；返回字符串为过滤后内容。
    同时维护 state 中的工具序列追踪和诊断检测。

    注意：DIAGNOSIS_READY 可能被拆分到多个 chunk 中，
    因此内容过滤在单个 chunk 上做，标记检测在 state.full_content 上做。
    """
    if not sse_str or not sse_str.strip():
        return sse_str

    # 只处理 data: 开头的行
    stripped = sse_str.strip()
    if not stripped.startswith("data: "):
        return sse_str

    data_str = stripped[6:]
    if data_str.strip() == "[DONE]":
        return sse_str  # [DONE] 不做任何处理

    # 解析 JSON
    try:
        chunk_data = json.loads(data_str)
    except (json.JSONDecodeError, ValueError):
        return sse_str

    choices = chunk_data.get("choices", [])
    if not choices:
        return sse_str

    choice = choices[0]
    delta = choice.get("delta", {})
    finish_reason = choice.get("finish_reason")

    # ---- P1: 隐藏工具调用/结果 ----
    # 1) 工具调用发起（AI 请求调用工具）
    if delta.get("tool_calls"):
        state.in_tool_sequence = True
        return None  # 跳过

    # 2) finish_reason=tool_calls（工具调用完成信号）
    if finish_reason == "tool_calls":
        return None  # 跳过

    # 3) 工具返回结果
    if delta.get("role") == "tool":
        return None  # 跳过

    # 4) 工具结果后的 stop（不是最终 stop，跳过）
    if finish_reason == "stop" and state.in_tool_sequence:
        state.in_tool_sequence = False
        return None  # 跳过

    # ---- 内容过滤 ----
    content = delta.get("content")
    if content and isinstance(content, str):
        # 先累积原始内容（用于跨 chunk 检测 DIAGNOSIS_READY）
        state.full_content += content
        # 在累积内容中检测标记（跨 chunk 安全）
        if 'DIAGNOSIS_READY' in state.full_content:
            state.diagnosis_detected = True

        # 对当前 chunk 内容做文本过滤
        filtered, _ = _filter_text(content)
        if filtered:
            delta["content"] = filtered
            state.in_tool_sequence = False  # 有用户可见内容 = 不在工具序列中
        else:
            # 内容被完全过滤，移除 content
            if "content" in delta:
                del delta["content"]
            # 如果 delta 只剩 role，仍保留（有些客户端依赖 role 字段）
            if not delta.get("role") and finish_reason is None:
                return None  # 空 delta 无意义，跳过

    # 重新序列化（添加 event: message 前缀，保持与文档一致）
    return f"event: message\ndata: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"


# =====================================================================
# 结构化诊断提取 — 从 AI 完整回复中提取 7 个字段
# =====================================================================

_DIAGNOSIS_FIELDS = [
    ("blindSpot",            "家长盲点"),
    ("coreMechanism",        "核心机制"),
    ("behaviorProtection",   "行为保护"),
    ("possibleMeanings",     "可能含义"),
    ("evidenceBasis",         "判断依据"),
    ("riskWarning",           "风险提示"),
    ("suggestedReplies",      "建议回复"),
    ("suggestions",          "改善建议"),
]

# 所有字段标签（用于构建"下一个标签"的正则边界）
_ALL_LABELS = [lbl for _, lbl in _DIAGNOSIS_FIELDS]


def _extract_section(text: str, label: str) -> str:
    """
    从文本中提取诊断卡某个字段的内容。
    支持以下格式（按优先级）：
    1. **字段名**：内容  （加粗+冒号）
    2. **字段名**\n内容  （加粗+换行，无冒号）
    3. ## 字段名\n内容    （Markdown标题）
    4. 字段名：内容       （纯文本+冒号）
    5. 字段名\n内容       （纯文本+换行，无冒号）
    """
    next_labels_pattern = '|'.join(re.escape(l) for l in _ALL_LABELS if l != label)

    # 构建一个通用的"下一个标签"边界
    next_boundary = (
        r'(?='
        r'\*\*(?:' + next_labels_pattern + r')\*\*'   # 下一个 **标签**
        r'|#{1,6}\s*(?:' + next_labels_pattern + r')'  # 下一个 ## 标签
        r'|(?:' + next_labels_pattern + r')\s*[：:\n]'  # 下一个纯标签
        r'|###DIAGNOSIS_READY###'
        r'|DIAGNOSIS_READY'
        r'|$)'
    )

    # 模式1: **字段名**后跟冒号（含标签和冒号间可能的额外文字）
    p1 = re.compile(
        r'\*\*' + re.escape(label) + r'\*\*[^：:\n]*[：:]\s*([\s\S]*?)' + next_boundary,
        re.IGNORECASE
    )
    m = p1.search(text)
    if m and m.group(1).strip():
        return m.group(1).strip()

    # 模式2: **字段名**后换行（无冒号）
    p2 = re.compile(
        r'\*\*' + re.escape(label) + r'\*\*\s*\n\s*([\s\S]*?)' + next_boundary,
        re.IGNORECASE
    )
    m = p2.search(text)
    if m and m.group(1).strip():
        return m.group(1).strip()

    # 模式3: ## 字段名（Markdown标题）
    p3 = re.compile(
        r'#{1,6}\s*' + re.escape(label) + r'\s*\n\s*([\s\S]*?)' + next_boundary,
        re.IGNORECASE
    )
    m = p3.search(text)
    if m and m.group(1).strip():
        return m.group(1).strip()

    # 模式4: 纯字段名后跟冒号
    p4 = re.compile(
        r'(?<!\*)' + re.escape(label) + r'\s*[：:]\s*([\s\S]*?)' + next_boundary,
        re.IGNORECASE
    )
    m = p4.search(text)
    if m and m.group(1).strip():
        return m.group(1).strip()

    # 模式5: 纯字段名后换行（无冒号，无加粗）
    p5 = re.compile(
        r'(?<!\*|#)' + re.escape(label) + r'\s*\n\s*([\s\S]*?)' + next_boundary,
        re.IGNORECASE
    )
    m = p5.search(text)
    if m and m.group(1).strip():
        return m.group(1).strip()

    return ""


def _parse_diagnosis(text: str) -> Dict[str, Any]:
    """
    从 AI 完整回复中提取结构化诊断数据。
    优先从 <!--DIAGNOSIS_JSON {...}--> 内部 JSON 提取（最稳定），
    如果没有则回退到正则切文本（兜底）。
    """
    # ---- 优先：内部 JSON 提取 ----
    json_data = _extract_diagnosis_json(text)
    if json_data:
        return json_data

    # ---- 兜底：正则切文本 ----
    result = {}
    for key, label in _DIAGNOSIS_FIELDS:
        val = _extract_section(text, label)
        if val:
            result[key] = val

    # 可能含义特殊解析：提取每条的百分比和描述
    if "possibleMeanings" in result:
        items = _parse_possible_meanings(result["possibleMeanings"])
        if items:
            result["possibleMeanings"] = items

    # 建议回复特殊解析：提取稳妥版/推进版/边界版
    if "suggestedReplies" in result:
        replies = _parse_suggested_replies(result["suggestedReplies"])
        if replies:
            result["suggestedReplies"] = replies

    return result


def _process_diagnosis_completion(family_id: str, diagnosis_data: dict, session_id: str):
    """诊断完成后：写入画像候选 + handoff摘要 + 更新路由状态 + 生成前端提示"""
    try:
        # 1) 生成 handoffSummary
        handoff = _generate_handoff_summary(diagnosis_data)

        # 2) 生成 profileUpdateCandidates
        profile_candidates = _extract_profile_candidates(diagnosis_data)

        # 3) 生成 pendingObservationCandidates
        pending = _extract_pending_observations(diagnosis_data)

        # 4) 写入数据库（异步不阻塞流）
        if profile_service:
            try:
                # 保存 handoff
                profile_service.save_handoff_summary(family_id, diagnosis_data.get("card_id", ""), handoff)

                # 保存 profile candidates（内部处理查重合并）
                update_results = profile_service.merge_profile_candidates(family_id, session_id, profile_candidates)

                # 保存 pending observations（作为低权重 entry 写入）
                for p in pending:
                    q_text = p.get("question", "") if isinstance(p, dict) else str(p)
                    dim = p.get("relatedDimension", "other") if isinstance(p, dict) else "other"
                    profile_service.insert_entry(family_id, {
                        "category": dim,
                        "content": f"[待观察] {q_text}",
                        "source": "diagnosis",
                        "weight": 0.5,
                        "confidence": "low",
                        "status": "pending_observation"
                    })

                # 更新 family_state: diagnosis_completed = True
                profile_service.mark_diagnosis_completed(family_id, diagnosis_data.get("card_id", ""))

                # 记录更新日志
                for r in update_results:
                    profile_service._log_update(family_id, session_id, r.get("action", "unknown"),
                                           "profile_entries", None, r.get("detail", ""))
            except Exception as e:
                logger.warning(f"Post-diagnosis write failed: {e}")

        logger.info(f"Post-diagnosis: family={family_id}, candidates={len(profile_candidates)}, "
                    f"pending={len(pending)}")
    except Exception as e:
        logger.error(f"Post-diagnosis processing error for family {family_id}: {e}", exc_info=True)


def _generate_handoff_summary(diagnosis_data: dict) -> dict:
    """从诊断数据生成交接摘要给日常 Agent"""
    return {
        "initialUnderstanding": diagnosis_data.get("blindSpot", "")[:200],
        "keyChildPatterns": [
            diagnosis_data.get("behaviorProtection", "")
        ] if diagnosis_data.get("behaviorProtection") else [],
        "parentConcern": [],  # 从对话中提取，诊断卡不直接包含
        "familyInteractionHypotheses": [
            diagnosis_data.get("coreMechanism", "")
        ] if diagnosis_data.get("coreMechanism") else [],
        "pendingObservations": [],  # 后续由日常 Agent 补充
        "suggestedDailyMode": "memory_aware_daily_chat"
    }


def _extract_profile_candidates(diagnosis_data: dict) -> list:
    """从诊断数据提取画像候选"""
    candidates = []

    # 从 blindSpot 提取 family_dynamic
    bs = diagnosis_data.get("blindSpot", "")
    if bs:
        candidates.append({
            "dimension": "parent_child_interaction",
            "summary": bs[:300],
            "evidence": [bs[:100]],
            "source": "diagnosis_agent",
            "confidence": "high",
            "status": "initial_hypothesis"
        })

    # 从 coreMechanism 提取 behavioral pattern
    cm = diagnosis_data.get("coreMechanism", "")
    if cm:
        candidates.append({
            "dimension": "emotion_response",
            "summary": cm[:300],
            "evidence": [cm[:100]],
            "source": "diagnosis_agent",
            "confidence": "high",
            "status": "initial_hypothesis"
        })

    # 从 behaviorProtection 提取
    bp = diagnosis_data.get("behaviorProtection", "")
    if bp:
        candidates.append({
            "dimension": "communication_style",
            "summary": bp[:300],
            "evidence": [bp[:100]],
            "source": "diagnosis_agent",
            "confidence": "medium",
            "status": "initial_hypothesis"
        })

    # 从 possibleMeanings 提取
    pm = diagnosis_data.get("possibleMeanings", [])
    if pm:
        top = pm[0] if isinstance(pm, list) and pm else {}
        label = top.get("label", "") if isinstance(top, dict) else ""
        if label:
            candidates.append({
                "dimension": "other",
                "summary": f"最可能含义: {label}",
                "evidence": [str(top.get("description", ""))[:100]],
                "source": "diagnosis_agent",
                "confidence": "high" if top.get("percentage", 0) >= 70 else "medium",
                "status": "initial_hypothesis"
            })

    # 从 evidenceBasis 提取
    eb = diagnosis_data.get("evidenceBasis", "")
    if eb:
        candidates.append({
            "dimension": "learning_start",
            "summary": f"判断依据: {eb[:300]}",
            "evidence": [eb[:100]],
            "source": "diagnosis_agent",
            "confidence": "medium",
            "status": "initial_hypothesis"
        })

    # 从 riskWarning 提取
    rw = diagnosis_data.get("riskWarning", "")
    if rw:
        candidates.append({
            "dimension": "parent_child_interaction",
            "summary": f"风险提示: {rw[:300]}",
            "evidence": [rw[:100]],
            "source": "diagnosis_agent",
            "confidence": "high",
            "status": "initial_hypothesis"
        })

    return candidates


def _extract_pending_observations(diagnosis_data: dict) -> list:
    """从诊断数据提取待观察点候选"""
    pending = []

    # 从 possibleMeanings 的低概率项生成待观察
    pm = diagnosis_data.get("possibleMeanings", [])
    if isinstance(pm, list):
        for item in pm:
            if isinstance(item, dict) and item.get("percentage", 0) < 30:
                pending.append({
                    "question": f"是否可能是: {item.get('label', '')}",
                    "relatedDimension": "other",
                    "reason": f"概率较低({item.get('percentage', 0)}%)但不可忽略"
                })

    # 从 suggestions 生成待观察
    suggestions = diagnosis_data.get("suggestions", "")
    if suggestions:
        pending.append({
            "question": "改善建议执行效果如何",
            "relatedDimension": "parent_child_interaction",
            "reason": "需要持续观察改善建议的实际效果"
        })

    return pending


def _build_profile_context(family_id: str) -> str:
    """构建画像上下文注入文本（用于 prompt 注入）"""
    parts = []

    # 1) 家庭状态
    fs = profile_service.get_family_state(family_id)
    if fs:
        parts.append("[家庭状态]")
        if fs.get("child_grade"):
            parts.append(f"- 孩子年级: {fs['child_grade']}")
        parts.append(f"- 诊断已完成: {'是' if fs.get('diagnosis_completed') else '否'}")

    # 2) 画像条目（weight >= 0.3）
    entries = profile_service.get_active_entries(family_id)
    if entries:
        parts.append("\n[孩子画像记录]")
        for e in entries[:10]:
            status_tag = "待观察" if e.get("status") == "initial_hypothesis" else "已确认"
            parts.append(f"- [{e.get('category', '?')}|权重{e.get('weight', 0):.1f}|{status_tag}] {e.get('content', '')[:80]}")

    # 3) 问卷摘要
    q = profile_service.get_questionnaire(family_id)
    if q and q.get("status") == "completed":
        parts.append("\n[孩子自述摘要]")
        if q.get("child_self_report_summary"):
            parts.append(q["child_self_report_summary"][:500])
        if q.get("conflicts_with_parent"):
            parts.append("⚠️ 与家长描述有出入，需持续观察")

    # 4) handoff摘要
    handoff = profile_service.get_latest_handoff(family_id)
    if handoff:
        parts.append("\n[诊断交接摘要]")
        if handoff.get("initial_understanding"):
            parts.append(f"- 初步理解: {handoff['initial_understanding'][:200]}")
        if handoff.get("key_child_patterns"):
            for p in handoff["key_child_patterns"][:3]:
                if p:
                    parts.append(f"- 核心模式: {p[:100]}")

    # 5) 长期关注目标
    goals = profile_service.get_active_goals(family_id)
    if goals:
        parts.append("\n[长期关注目标]")
        for g in goals[:5]:
            parts.append(f"- {g.get('goal_name', '')}（权重{g.get('weight', 0):.1f}）")

    return "\n".join(parts) if parts else ""


def _extract_diagnosis_json(text: str) -> Dict[str, Any]:
    """
    从 <!--DIAGNOSIS_JSON {...}--> 标记中提取结构化诊断 JSON。
    这是模型在诊断完成时输出的内部数据，后端直接解析，
    不依赖正则切文本，最稳定可靠。
    返回空 dict 表示未找到有效 JSON。
    """
    # 模式1: <!--DIAGNOSIS_JSON {...}-->
    m = re.search(r'<!--DIAGNOSIS_JSON\s*(\{[\s\S]*?\})\s*-->', text)
    if not m:
        # 模式2: ```diagnosis_json\n{...}\n```
        m = re.search(r'```diagnosis_json\s*\n([\s\S]*?)\n```', text)
    if not m:
        return {}

    json_str = m.group(1).strip()
    try:
        data = json.loads(json_str)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to parse DIAGNOSIS_JSON: {e}, raw: {json_str[:200]}")
        return {}

    if not isinstance(data, dict):
        return {}

    # 映射中文 key 到英文 key（模型可能输出中文 key 或英文 key）
    cn_to_en = {lbl: key for key, lbl in _DIAGNOSIS_FIELDS}
    result = {}
    for k, v in data.items():
        en_key = cn_to_en.get(k, k)  # 中文→英文，或保持原英文
        if v:  # 跳过空值
            result[en_key] = v

    # 可能含义：如果是字符串则解析为结构化
    if "possibleMeanings" in result and isinstance(result["possibleMeanings"], str):
        items = _parse_possible_meanings(result["possibleMeanings"])
        if items:
            result["possibleMeanings"] = items

    # 建议回复：如果是字符串则解析为结构化
    if "suggestedReplies" in result and isinstance(result["suggestedReplies"], str):
        replies = _parse_suggested_replies(result["suggestedReplies"])
        if replies:
            result["suggestedReplies"] = replies

    return result


def _parse_possible_meanings(text: str) -> list:
    """解析可能含义中的条目，提取百分比和描述
    支持格式：
    - "1. 描述 — 70%：详细说明"
    - "1. 描述（70%）：详细说明"
    - "1. 70% 描述：详细说明"
    过滤规则：
    - 过滤掉"概率基于当前对话..."等声明文本
    - 不生成 percentage=0 的兜底项
    """
    # 先过滤声明文本
    text = re.sub(r'概率基于当前对话[^。\n]*[。.]?', '', text)
    text = re.sub(r'仍存在不确定性[^。\n]*[。.]?', '', text)

    items = []
    # 按编号拆分
    parts = re.split(r'\n\s*(?:\d+)[\.、）)]\s*', text)
    for part in parts:
        part = part.strip()
        if not part:
            continue

        # 跳过纯声明行
        if re.match(r'^概率基于|^仍存在不确定', part):
            continue

        # 模式1: "描述 — 70%：详细" 或 "描述 - 70%：详细"
        m = re.match(r'(.+?)\s*[—\-–]\s*(\d+)\s*%\s*[：:]\s*(.+)', part, re.DOTALL)
        if m:
            pct = int(m.group(2))
            if pct > 0:
                items.append({"label": m.group(1).strip(), "percentage": pct, "description": m.group(3).strip()})
            continue

        # 模式2: "描述（70%）：详细" 或 "描述(70%)：详细"
        m = re.match(r'(.+?)\s*[（(]\s*(\d+)\s*%\s*[）)]\s*[：:]*\s*(.*)', part, re.DOTALL)
        if m:
            pct = int(m.group(2))
            if pct > 0:
                items.append({"label": m.group(1).strip(), "percentage": pct, "description": m.group(3).strip()})
            continue

        # 模式3: "70% 描述：详细" 或 "70%：描述"
        m = re.match(r'(\d+)\s*%\s*[：:]*\s*(.+)', part, re.DOTALL)
        if m:
            pct = int(m.group(1))
            if pct > 0:
                items.append({"label": "", "percentage": pct, "description": m.group(2).strip()})
            continue

        # 兜底：无百分比的条目 → 不生成 0% 项，跳过

    return items


def _parse_suggested_replies(text: str) -> dict:
    """解析建议回复中的稳妥版/推进版/边界版
    支持格式：
    - 【稳妥版】内容\n推荐理由：xxx
    - 稳妥版：内容（推荐理由：xxx）
    """
    result = {}
    versions = {"稳妥版": "conservative", "推进版": "progressive", "边界版": "boundary"}

    for cn_name, en_key in versions.items():
        # 模式1: 【稳妥版】内容 \n 推荐理由：xxx
        m = re.search(
            r'[【\[]' + re.escape(cn_name) + r'[】\]]\s*([\s\S]*?)(?=[【\[](?:稳妥版|推进版|边界版)[】\]]|$)',
            text
        )
        if m:
            content = m.group(1).strip()
            # 分离推荐理由
            reason_match = re.search(r'推荐理由[：:]\s*(.+?)(?=$|[【\[](?:稳妥版|推进版|边界版))', content, re.DOTALL)
            if reason_match:
                reply_text = content[:reason_match.start()].strip()
                reason = reason_match.group(1).strip()
            else:
                reply_text = content
                reason = ""
            result[en_key] = {"reply": reply_text, "reason": reason}
            continue

        # 模式2: 稳妥版：内容（推荐理由：xxx）
        m = re.search(
            re.escape(cn_name) + r'[：:]\s*([\s\S]*?)(?=' + '|'.join(re.escape(v) for v in versions) + r'[：:]|$)',
            text
        )
        if m:
            content = m.group(1).strip()
            reason_match = re.search(r'推荐理由[：:]\s*(.+)', content, re.DOTALL)
            if reason_match:
                reply_text = content[:reason_match.start()].strip()
                reason = reason_match.group(1).strip()
            else:
                reply_text = content
                reason = ""
            result[en_key] = {"reply": reply_text, "reason": reason}

    return result if result else {}


class GraphService:
    def __init__(self):
        # 用于跟踪正在运行的任务（使用asyncio.Task）
        self.running_tasks: Dict[str, asyncio.Task] = {}
        # 错误分类器
        self.error_classifier = ErrorClassifier()
        # stream runner
        self._agent_stream_runner = AgentStreamRunner()
        self._workflow_stream_runner = WorkflowStreamRunner()
        self._graph = None
        self._graph_lock = threading.Lock()

    def _get_graph(self, ctx=Context):
        if graph_helper.is_agent_proj():
            return graph_helper.get_agent_instance("agents.agent", ctx)

        if self._graph is not None:
            return self._graph
        with self._graph_lock:
            if self._graph is not None:
                return self._graph
            self._graph = graph_helper.get_graph_instance("graphs.graph")
            return self._graph

    @staticmethod
    def _sse_event(data: Any, event_id: Any = None) -> str:
        id_line = f"id: {event_id}\n" if event_id else ""
        return f"{id_line}event: message\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"

    @staticmethod
    def _filter_chunk(chunk: Any) -> tuple[Any, bool]:
        """过滤AI回复中泄露的内部指令内容，返回(过滤后的chunk, 是否包含诊断标记)"""
        has_diagnosis = False
        if not isinstance(chunk, dict):
            return chunk, has_diagnosis

        # AgentStreamRunner 返回 ServerMessage 格式，不是 OpenAI 格式
        # 结构: {"type": "answer", "content": {"answer": "文本..."}, ...}
        msg_type = chunk.get("type")
        if msg_type != "answer":
            return chunk, has_diagnosis

        content_obj = chunk.get("content")
        if not isinstance(content_obj, dict):
            return chunk, has_diagnosis

        original = content_obj.get("answer")
        if not original or not isinstance(original, str):
            return chunk, has_diagnosis

        # 委托给共享过滤函数
        filtered, has_diagnosis = _filter_text(original)

        if filtered != original:
            content_obj["answer"] = filtered
        return chunk, has_diagnosis

    def _get_stream_runner(self):
        if graph_helper.is_agent_proj():
            return self._agent_stream_runner
        else:
            return self._workflow_stream_runner

    # 流式运行（原始迭代器）：本地调用使用
    def stream(self, payload: Dict[str, Any], run_config: RunnableConfig, ctx=Context) -> Iterable[Any]:
        graph = self._get_graph(ctx)
        stream_runner = self._get_stream_runner()
        for chunk in stream_runner.stream(payload, graph, run_config, ctx):
            yield chunk

    # 同步运行：本地/HTTP 通用
    async def run(self, payload: Dict[str, Any], ctx=None) -> Dict[str, Any]:
        if ctx is None:
            ctx = new_context("run")

        run_id = ctx.run_id
        logger.info(f"Starting run with run_id: {run_id}")

        try:
            graph = self._get_graph(ctx)
            # custom tracer
            run_config = init_run_config(graph, ctx)
            run_config["configurable"] = {"thread_id": ctx.run_id}

            # 直接调用，LangGraph会在当前任务上下文中执行
            # 如果当前任务被取消，LangGraph的执行也会被取消
            return await graph.ainvoke(payload, config=run_config, context=ctx)

        except asyncio.CancelledError:
            logger.info(f"Run {run_id} was cancelled")
            return {"status": "cancelled", "run_id": run_id, "message": "Execution was cancelled"}
        except Exception as e:
            # 使用错误分类器分类错误
            err = self.error_classifier.classify(e, {"node_name": "run", "run_id": run_id})
            # 记录详细的错误信息和堆栈跟踪
            logger.error(
                f"Error in GraphService.run: [{err.code}] {err.message}\n"
                f"Category: {err.category.name}\n"
                f"Traceback:\n{extract_core_stack()}"
            )
            # 保留原始异常堆栈，便于上层返回真正的报错位置
            raise
        finally:
            # 清理任务记录
            self.running_tasks.pop(run_id, None)

    # 流式运行（SSE 格式化）：HTTP 路由使用
    async def stream_sse(self, payload: Dict[str, Any], ctx=None, run_opt: Optional[RunOpt] = None) -> AsyncGenerator[str, None]:
        if ctx is None:
            ctx = new_context(method="stream_sse")
        if run_opt is None:
            run_opt = RunOpt()

        run_id = ctx.run_id
        logger.info(f"Starting stream with run_id: {run_id}")
        graph = self._get_graph(ctx)
        if graph_helper.is_agent_proj():
            run_config = init_agent_config(graph, ctx)
        else:
            run_config = init_run_config(graph, ctx)  # vibeflow

        is_workflow = not graph_helper.is_agent_proj()

        diagnosis_ready = False
        try:
            try:
                async for chunk in self.astream(payload, graph, run_config=run_config, ctx=ctx, run_opt=run_opt):
                    if is_workflow and isinstance(chunk, tuple):
                        event_id, data = chunk
                        yield self._sse_event(data, event_id)
                    else:
                        # 过滤内部指令泄露，同时检测诊断标记
                        chunk, has_diag = self._filter_chunk(chunk)
                        if has_diag:
                            diagnosis_ready = True
                        if chunk:
                            yield self._sse_event(chunk)
            except BrokenPipeError:
                logger.warning("Client disconnected (BrokenPipe) during stream")
                return
            # 流式输出结束后，如果检测到诊断标记，发送自定义SSE事件通知前端弹窗
            if diagnosis_ready:
                yield "event: diagnosis_ready\ndata: {}\n\n"
        finally:
            # 清理任务记录
            self.running_tasks.pop(run_id, None)
            cozeloop.flush()

    # 取消执行 - 使用asyncio的标准方式
    def cancel_run(self, run_id: str, ctx: Optional[Context] = None) -> Dict[str, Any]:
        """
        取消指定run_id的执行

        使用asyncio.Task.cancel()来取消任务,这是标准的Python异步取消机制。
        LangGraph会在节点之间检查CancelledError,实现优雅的取消。
        """
        logger.info(f"Attempting to cancel run_id: {run_id}")

        # 查找对应的任务
        if run_id in self.running_tasks:
            task = self.running_tasks[run_id]
            if not task.done():
                # 使用asyncio的标准取消机制
                # 这会在下一个await点抛出CancelledError
                task.cancel()
                logger.info(f"Cancellation requested for run_id: {run_id}")
                return {
                    "status": "success",
                    "run_id": run_id,
                    "message": "Cancellation signal sent, task will be cancelled at next await point"
                }
            else:
                logger.info(f"Task already completed for run_id: {run_id}")
                return {
                    "status": "already_completed",
                    "run_id": run_id,
                    "message": "Task has already completed"
                }
        else:
            logger.warning(f"No active task found for run_id: {run_id}")
            return {
                "status": "not_found",
                "run_id": run_id,
                "message": "No active task found with this run_id. Task may have already completed or run_id is invalid."
            }

    # 运行指定节点：本地/HTTP 通用
    async def run_node(self, node_id: str, payload: Dict[str, Any], ctx=None) -> Any:
        if ctx is None or Context.run_id == "":
            ctx = new_context(method="node_run")

        _graph = self._get_graph()
        node_func, input_cls, output_cls = graph_helper.get_graph_node_func_with_inout(_graph.get_graph(), node_id)
        if node_func is None or input_cls is None:
            raise KeyError(f"node_id '{node_id}' not found")

        parser = LangGraphParser(_graph)
        metadata = parser.get_node_metadata(node_id) or {}

        _g = StateGraph(input_cls, input_schema=input_cls, output_schema=output_cls)
        _g.add_node("sn", node_func, metadata=metadata)
        _g.set_entry_point("sn")
        _g.add_edge("sn", END)
        _graph = _g.compile()

        run_config = init_run_config(_graph, ctx)
        return await _graph.ainvoke(payload, config=run_config)

    def graph_inout_schema(self) -> Any:
        if graph_helper.is_agent_proj():
            return {"input_schema": {}, "output_schema": {}}
        builder = getattr(self._get_graph(), 'builder', None)
        if builder is not None:
            input_cls = getattr(builder, 'input_schema', None) or self.graph.get_input_schema()
            output_cls = getattr(builder, 'output_schema', None) or self.graph.get_output_schema()
        else:
            logger.warning(f"No builder input schema found for graph_inout_schema, using graph input schema instead")
            input_cls = self.graph.get_input_schema()
            output_cls = self.graph.get_output_schema()

        return {
            "input_schema": input_cls.model_json_schema(), 
            "output_schema": output_cls.model_json_schema(),
            "code":0,
            "msg":""
        }

    async def astream(self, payload: Dict[str, Any], graph: CompiledStateGraph, run_config: RunnableConfig, ctx=Context, run_opt: Optional[RunOpt] = None) -> AsyncIterable[Any]:
        stream_runner = self._get_stream_runner()
        async for chunk in stream_runner.astream(payload, graph, run_config, ctx, run_opt):
            yield chunk


service = GraphService()
# profile_service is imported as module above; all calls use profile_service.func()
app = FastAPI()

# CORS支持，允许前端跨域调用
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "对话实验室 API 服务运行中", "docs": "/docs"}

# OpenAI 兼容接口处理器
openai_handler = OpenAIChatHandler(service)


HEADER_X_RUN_ID = "x-run-id"
@app.post("/run")
async def http_run(request: Request) -> Dict[str, Any]:
    global result
    raw_body = await request.body()
    try:
        body_text = raw_body.decode("utf-8")
    except Exception as e:
        body_text = str(raw_body)
        raise HTTPException(status_code=400,
                            detail=f"Invalid JSON format: {body_text}, traceback: {traceback.format_exc()}, error: {e}")

    ctx = new_context(method="run", headers=request.headers)
    # 优先使用上游指定的 run_id，保证 cancel 能精确匹配
    upstream_run_id = request.headers.get(HEADER_X_RUN_ID)
    if upstream_run_id:
        ctx.run_id = upstream_run_id
    run_id = ctx.run_id
    request_context.set(ctx)

    logger.info(
        f"Received request for /run: "
        f"run_id={run_id}, "
        f"query={dict(request.query_params)}, "
        f"body={body_text}"
    )

    try:
        payload = await request.json()

        # 创建任务并记录 - 这是关键，让我们可以通过run_id取消任务
        task = asyncio.create_task(service.run(payload, ctx))
        service.running_tasks[run_id] = task

        try:
            result = await asyncio.wait_for(task, timeout=float(TIMEOUT_SECONDS))
        except asyncio.TimeoutError:
            logger.error(f"Run execution timeout after {TIMEOUT_SECONDS}s for run_id: {run_id}")
            task.cancel()
            try:
                result = await task
            except asyncio.CancelledError:
                return {
                    "status": "timeout",
                    "run_id": run_id,
                    "message": f"Execution timeout: exceeded {TIMEOUT_SECONDS} seconds"
                }

        if not result:
            result = {}
        if isinstance(result, dict):
            result["run_id"] = run_id
        return result

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in http_run: {e}, traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON format, {extract_core_stack()}")

    except asyncio.CancelledError:
        logger.info(f"Request cancelled for run_id: {run_id}")
        result = {"status": "cancelled", "run_id": run_id, "message": "Execution was cancelled"}
        return result

    except Exception as e:
        # 使用错误分类器获取错误信息
        error_response = service.error_classifier.get_error_response(e, {"node_name": "http_run", "run_id": run_id})
        logger.error(
            f"Unexpected error in http_run: [{error_response['error_code']}] {error_response['error_message']}, "
            f"traceback: {traceback.format_exc()}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": error_response["error_code"],
                "error_message": error_response["error_message"],
                "stack_trace": extract_core_stack(),
            }
        )
    finally:
        cozeloop.flush()


HEADER_X_WORKFLOW_STREAM_MODE = "x-workflow-stream-mode"


def _register_task(run_id: str, task: asyncio.Task):
    service.running_tasks[run_id] = task


@app.post("/stream_run")
async def http_stream_run(request: Request):
    ctx = new_context(method="stream_run", headers=request.headers)
    # 优先使用上游指定的 run_id，保证 cancel 能精确匹配
    upstream_run_id = request.headers.get(HEADER_X_RUN_ID)
    if upstream_run_id:
        ctx.run_id = upstream_run_id
    workflow_stream_mode = request.headers.get(HEADER_X_WORKFLOW_STREAM_MODE, "").lower()
    workflow_debug = workflow_stream_mode == "debug"
    request_context.set(ctx)
    raw_body = await request.body()
    try:
        body_text = raw_body.decode("utf-8")
    except Exception as e:
        body_text = str(raw_body)
        raise HTTPException(status_code=400,
                            detail=f"Invalid JSON format: {body_text}, traceback: {extract_core_stack()}, error: {e}")
    run_id = ctx.run_id
    is_agent = graph_helper.is_agent_proj()
    logger.info(
        f"Received request for /stream_run: "
        f"run_id={run_id}, "
        f"is_agent_project={is_agent}, "
        f"query={dict(request.query_params)}, "
        f"body={body_text}"
    )
    try:
        payload = await request.json()
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in http_stream_run: {e}, traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON format:{extract_core_stack()}")

    if is_agent:
        stream_generator = agent_stream_handler(
            payload=payload,
            ctx=ctx,
            run_id=run_id,
            stream_sse_func=service.stream_sse,
            sse_event_func=service._sse_event,
            error_classifier=service.error_classifier,
            register_task_func=_register_task,
        )
    else:
        stream_generator = workflow_stream_handler(
            payload=payload,
            ctx=ctx,
            run_id=run_id,
            stream_sse_func=service.stream_sse,
            sse_event_func=service._sse_event,
            error_classifier=service.error_classifier,
            register_task_func=_register_task,
            run_opt=RunOpt(workflow_debug=workflow_debug),
        )

    response = StreamingResponse(stream_generator, media_type="text/event-stream")
    return response

@app.post("/cancel/{run_id}")
async def http_cancel(run_id: str, request: Request):
    """
    取消指定run_id的执行

    使用asyncio.Task.cancel()实现取消,这是Python标准的异步任务取消机制。
    LangGraph会在节点之间的await点检查CancelledError,实现优雅取消。
    """
    ctx = new_context(method="cancel", headers=request.headers)
    request_context.set(ctx)
    logger.info(f"Received cancel request for run_id: {run_id}")
    result = service.cancel_run(run_id, ctx)
    return result


# ===== 语音模块 =====
try:
    from coze_coding_dev_sdk import TTSClient, ASRClient
    AUDIO_SDK_AVAILABLE = True
except ImportError:
    AUDIO_SDK_AVAILABLE = False
    logger.warning("coze-coding-dev-sdk not available, audio features disabled")


@app.post("/api/tts")
async def http_tts(request: Request):
    """文本转语音接口"""
    if not AUDIO_SDK_AVAILABLE:
        raise HTTPException(status_code=501, detail="Audio SDK not available")
    
    ctx = new_context(method="tts", headers=request.headers)
    request_context.set(ctx)
    
    try:
        payload = await request.json()
        text = payload.get("text", "")
        if not text:
            raise HTTPException(status_code=400, detail="Text is required")
        
        client = TTSClient(ctx=ctx)
        audio_url, audio_size = client.synthesize(
            uid="dialogue_lab_user",
            text=text,
            speaker="zh_female_xiaohe_uranus_bigtts"
        )
        
        return {
            "status": "success",
            "audio_url": audio_url,
            "audio_size": audio_size
        }
    except Exception as e:
        logger.error(f"TTS error: {e}, traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/asr")
async def http_asr(request: Request):
    """语音转文本接口"""
    if not AUDIO_SDK_AVAILABLE:
        raise HTTPException(status_code=501, detail="Audio SDK not available")
    
    ctx = new_context(method="asr", headers=request.headers)
    request_context.set(ctx)
    
    try:
        payload = await request.json()
        url = payload.get("url")
        base64_data = payload.get("base64_data")
        
        if not url and not base64_data:
            raise HTTPException(status_code=400, detail="Either url or base64_data is required")
        
        client = ASRClient(ctx=ctx)
        text, data = client.recognize(
            uid="dialogue_lab_user",
            url=url,
            base64_data=base64_data
        )
        
        return {
            "status": "success",
            "text": text,
            "data": data
        }
    except Exception as e:
        logger.error(f"ASR error: {e}, traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post(path="/node_run/{node_id}")
async def http_node_run(node_id: str, request: Request):
    raw_body = await request.body()
    try:
        body_text = raw_body.decode("utf-8")
    except UnicodeDecodeError:
        body_text = str(raw_body)
        raise HTTPException(status_code=400, detail=f"Invalid JSON format: {body_text}")
    ctx = new_context(method="node_run", headers=request.headers)
    request_context.set(ctx)
    logger.info(
        f"Received request for /node_run/{node_id}: "
        f"query={dict(request.query_params)}, "
        f"body={body_text}",
    )

    try:
        payload = await request.json()
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in http_node_run: {e}, traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON format:{extract_core_stack()}")
    try:
        return await service.run_node(node_id, payload, ctx)
    except KeyError:
        raise HTTPException(status_code=404,
                            detail=f"node_id '{node_id}' not found or input miss required fields, traceback: {extract_core_stack()}")
    except Exception as e:
        # 使用错误分类器获取错误信息
        error_response = service.error_classifier.get_error_response(e, {"node_name": node_id})
        logger.error(
            f"Unexpected error in http_node_run: [{error_response['error_code']}] {error_response['error_message']}, "
            f"traceback: {traceback.format_exc()}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": error_response["error_code"],
                "error_message": error_response["error_message"],
                "stack_trace": extract_core_stack(),
            }
        )
    finally:
        cozeloop.flush()


# =====================================================================
# Agent Router — 根据 family_state 决定调用哪个 Agent
# =====================================================================

def _get_agent_type(family_id: str) -> str:
    """
    路由逻辑：
    - diagnosis_completed == False → diagnosis_agent
    - diagnosis_completed == True  → daily_agent
    默认 family_id = session_id（首次使用无独立 family_id）
    """
    state = profile_service.get_family_state(family_id)
    if not state or not state.get("diagnosis_completed"):
        return "diagnosis_agent"
    return "daily_agent"


def _build_context_injection(family_id: str) -> str:
    """
    为日常 Agent 构建画像上下文注入文本，拼入 system prompt 末尾。
    诊断型 Agent 只注入问卷上下文（如果有）。
    """
    parts = []

    # 1. 问卷上下文（两种 Agent 都注入）
    q = profile_service.get_questionnaire(family_id)
    if q and q.get("status") == "completed":
        parts.append("[孩子自述问卷摘要]")
        if q.get("child_self_report_summary"):
            parts.append(q["child_self_report_summary"])
        if q.get("conflicts_with_parent"):
            parts.append("⚠️ 与家长描述不一致：" + "；".join(q["conflicts_with_parent"]))

    # 2. 画像 + 交接摘要（仅日常 Agent 注入）
    state = profile_service.get_family_state(family_id)
    if state and state.get("diagnosis_completed"):
        # 孩子画像
        entries = profile_service.get_active_entries(family_id, limit=10)
        if entries:
            parts.append("[孩子小档案]")
            if state.get("child_name"):
                parts.append(f"孩子：{state['child_name']}")
            if state.get("child_grade"):
                parts.append(f"年级：{state['child_grade']}")
            for e in entries:
                cat_map = {"behavioral": "行为", "emotional": "情绪", "social": "社交",
                           "academic": "学业", "family_dynamic": "家庭互动", "other": "其他"}
                cat_label = cat_map.get(e["category"], e["category"])
                parts.append(f"- [{cat_label}] {e['content']}（来源:{e['source']}，佐证:{e['evidence_count']}次）")

        # 交接摘要
        handoff = profile_service.get_latest_handoff(family_id)
        if handoff:
            parts.append("[交接摘要]")
            if handoff.get("initial_understanding"):
                parts.append(f"初步理解：{handoff['initial_understanding']}")
            if handoff.get("pending_observations"):
                parts.append("待观察：" + "；".join(handoff["pending_observations"]))

        # 长期关注
        goals = profile_service.get_active_goals(family_id, limit=5)
        if goals:
            parts.append("[长期关注目标]")
            for g in goals:
                parts.append(f"- {g['goal_name']}（权重:{g['weight']:.1f}，提及:{g['trigger_count']}次）")

    return "\n".join(parts) if parts else ""


# =====================================================================
# 问卷 API
# =====================================================================

@app.post("/api/questionnaire")
async def submit_questionnaire(request: Request):
    """提交孩子学习小档案问卷"""
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    family_id = payload.get("family_id", "")
    if not family_id:
        raise HTTPException(status_code=400, detail="family_id is required")

    structured_answers = payload.get("structured_answers", [])
    child_self_report_summary = payload.get("child_self_report_summary", "")
    conflicts = payload.get("conflicts_with_parent", [])

    result = profile_service.save_questionnaire(
        family_id=family_id,
        data={
            "status": "completed",
            "structured_answers": structured_answers,
            "child_self_report_summary": child_self_report_summary,
            "conflicts_with_parent": conflicts,
        }
    )
    return JSONResponse(content=result)


@app.get("/api/questionnaire/{family_id}")
async def get_questionnaire(family_id: str):
    """获取问卷状态"""
    result = profile_service.get_questionnaire(family_id)
    if not result:
        return JSONResponse(content={"status": "not_started"})
    return JSONResponse(content=result)


# =====================================================================
# 画像 API
# =====================================================================

@app.get("/api/profile/{family_id}")
async def get_profile(family_id: str):
    """获取孩子画像（含基础信息、条目、长期关注、交接摘要）"""
    state = profile_service.get_family_state(family_id)
    entries = profile_service.get_active_entries(family_id, limit=20)
    goals = profile_service.get_active_goals(family_id, limit=10)
    handoff = profile_service.get_latest_handoff(family_id)
    updates = profile_service.get_recent_updates(family_id, limit=10)

    return JSONResponse(content={
        "family_state": state,
        "entries": entries,
        "goals": goals,
        "handoff": handoff,
        "recent_updates": updates,
    })


@app.get("/api/profile/{family_id}/updates")
async def get_profile_updates(family_id: str):
    """获取画像更新日志（前端"已记录/已加入/已调整"的数据源）"""
    updates = profile_service.get_recent_updates(family_id, limit=20)
    return JSONResponse(content={"updates": updates})


# =====================================================================
# Agent 状态 API
# =====================================================================

@app.get("/api/agent-state/{family_id}")
async def get_agent_state(family_id: str):
    """获取当前 Agent 路由状态"""
    state = profile_service.get_family_state(family_id)
    agent_type = _get_agent_type(family_id)
    return JSONResponse(content={
        "family_id": family_id,
        "agent_type": agent_type,
        "diagnosis_completed": state.get("diagnosis_completed", False) if state else False,
        "questionnaire_status": state.get("questionnaire_status", "not_started") if state else "not_started",
    })


@app.post("/v1/chat/completions")
async def openai_chat_completions(request: Request):
    """
    OpenAI Chat Completions API 兼容接口（带过滤）。

    改进点（vs 原始 openai_handler.handle）：
    - P0: 对每个 delta.content 应用 _filter_text 过滤，剥离内部分析/知识库痕迹
    - P0: DIAGNOSIS_READY 从 content 中剥离，改为独立 SSE event: diagnosis
    - P0: session_id 唯一负责多轮；接口返回 session_id 确认
    - P1: tool_calls / tool result / finish_reason=tool_calls 永不进入用户 content
    - P1: 流结束时输出结构化 diagnosis side-channel
    """
    ctx = new_context(method="openai_chat", headers=request.headers)
    request_context.set(ctx)

    logger.info(f"Received request for /v1/chat/completions: run_id={ctx.run_id}")

    try:
        payload = await request.json()
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in openai_chat_completions: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON format")

    session_id = payload.get("session_id", "")

    if not session_id:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "message": "session_id is required",
                    "type": "invalid_request_error",
                    "code": "400001",
                }
            },
        )

    # ---- Agent Router + 上下文注入 ----
    family_id = payload.get("family_id", session_id)  # 默认 family_id = session_id
    agent_type = _get_agent_type(family_id)
    context_injection = _build_context_injection(family_id)

    # 将上下文注入为 system 消息（放在 messages 最前面）
    if context_injection:
        messages = payload.get("messages", [])
        # 查找是否已有 system 消息，有的话追加到后面，没有则新建
        has_system = False
        for msg in messages:
            if msg.get("role") == "system":
                msg["content"] = msg.get("content", "") + "\n\n" + context_injection
                has_system = True
                break
        if not has_system:
            messages.insert(0, {"role": "system", "content": context_injection})
        payload["messages"] = messages

    # 将 agent_type 和 family_id 存入 payload，供后续诊断后处理使用
    payload["_agent_type"] = agent_type
    payload["_family_id"] = family_id

    try:
        response = await openai_handler.handle(payload, ctx)
    except Exception as e:
        logger.error(f"Error from openai_handler.handle: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    # ---- 流式响应：包装过滤 ----
    if isinstance(response, StreamingResponse):
        return StreamingResponse(
            _filtered_openai_stream(response, session_id, family_id=family_id),
            media_type="text/event-stream",
        )

    # ---- 非流式响应：过滤 JSON ----
    if isinstance(response, JSONResponse):
        return _filtered_json_response(response, session_id, family_id=family_id)

    # 其他类型直接返回
    return response


async def _filtered_openai_stream(
    original_response: StreamingResponse,
    session_id: str,
    family_id: str = "",
) -> AsyncGenerator[str, None]:
    """
    包装 OpenAI 流式响应的 body_iterator，逐 chunk 过滤：
    1. delta.content 经过 _filter_text 过滤
    2. tool_calls / tool result 被隐藏
    3. DIAGNOSIS_READY 从 content 剥离
    4. 流结束时发射 event: diagnosis（结构化）+ event: session + data: [DONE]
    """
    state = _StreamFilterState()
    state._family_id = family_id
    done_buffered = False  # 是否已缓存但未发射 [DONE]

    try:
        async for raw_item in original_response.body_iterator:
            if isinstance(raw_item, bytes):
                raw_item = raw_item.decode("utf-8")

            # 原始 handler 的 generator 每次产出一条完整 SSE 事件
            # 格式: "data: {...}\n\n"
            # 但也可能一次产出多行或 [DONE]
            # 逐行处理
            lines = raw_item.split("\n")
            for line in lines:
                line_stripped = line.strip()
                if not line_stripped:
                    continue

                # 缓存 [DONE]，最后再发射
                if line_stripped == "data: [DONE]":
                    done_buffered = True
                    continue

                # 过滤 SSE data 行
                filtered = _filter_sse_chunk(line_stripped + "\n\n", state)
                if filtered:
                    yield filtered

        # ---- 流结束，发射 side-channel 事件 ----

        # 1) 结构化诊断数据（仅当检测到 DIAGNOSIS_READY 时）
        if state.diagnosis_detected and state.full_content:
            # 清理累积内容中的诊断标记（可能跨 chunk 拆分，单 chunk 过滤无法捕获）
            clean_content = state.full_content.replace('###DIAGNOSIS_READY###', '').replace('DIAGNOSIS_READY', '')
            diagnosis_data = _parse_diagnosis(clean_content)
            if diagnosis_data:
                yield f"event: diagnosis\ndata: {json.dumps(diagnosis_data, ensure_ascii=False)}\n\n"

                # ---- 诊断后处理：写入画像候选 + handoff + 更新路由状态 ----
                try:
                    family_id = getattr(state, '_family_id', session_id)
                    _process_diagnosis_completion(family_id, diagnosis_data, session_id)
                except Exception as e:
                    logger.error(f"Post-diagnosis processing error: {e}", exc_info=True)

        # 2) session_id 确认
        yield f"event: session\ndata: {json.dumps({'session_id': session_id})}\n\n"

        # 3) [DONE]
        yield "data: [DONE]\n\n"

    except asyncio.CancelledError:
        logger.info(f"Filtered stream cancelled for session_id: {session_id}")
        raise
    except BrokenPipeError:
        logger.warning(f"Client disconnected (BrokenPipe) for session_id: {session_id}")


def _filtered_json_response(
    original_response: JSONResponse,
    session_id: str,
    family_id: str = "",
) -> JSONResponse:
    """过滤非流式 JSON 响应的 content，并附加 session_id / diagnosis"""
    try:
        body_bytes = original_response.body
        if isinstance(body_bytes, memoryview):
            body_bytes = bytes(body_bytes)
        body = json.loads(body_bytes)
    except Exception:
        # 解析失败则原样返回
        return original_response

    diagnosis_data = {}

    # 过滤 choices 中的 content
    for choice in body.get("choices", []):
        msg = choice.get("message", {})
        content = msg.get("content")
        if content and isinstance(content, str):
            filtered, has_diag = _filter_text(content)
            if has_diag:
                diagnosis_data = _parse_diagnosis(filtered)
            msg["content"] = filtered

    # 附加 session_id
    body["session_id"] = session_id

    # 附加结构化诊断（如果有）
    if diagnosis_data:
        body["diagnosis"] = diagnosis_data
        # 诊断后处理：写入画像候选 + handoff + 更新路由状态
        try:
            _process_diagnosis_completion(family_id or session_id, diagnosis_data, session_id)
        except Exception as e:
            logger.error(f"Post-diagnosis processing error (non-streaming): {e}", exc_info=True)

    return JSONResponse(content=body, status_code=original_response.status_code)


@app.get("/health")
async def health_check():
    try:
        # 检测 memory backend 类型
        memory_backend = "unknown"
        try:
            from storage.memory.memory_saver import _memory_manager
            if _memory_manager is not None and _memory_manager._checkpointer is not None:
                from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
                from langgraph.checkpoint.memory import MemorySaver
                if isinstance(_memory_manager._checkpointer, AsyncPostgresSaver):
                    memory_backend = "postgres"
                elif isinstance(_memory_manager._checkpointer, MemorySaver):
                    memory_backend = "memory"
                    logger.warning("Health check: memory backend is MemorySaver (in-memory, data lost on restart)")
                else:
                    memory_backend = type(_memory_manager._checkpointer).__name__
            else:
                memory_backend = "not_initialized"
        except Exception as e:
            logger.warning(f"Health check: failed to detect memory backend: {e}")
            memory_backend = "error"

        return {
            "status": "ok",
            "message": "Service is running",
            "memory_backend": memory_backend,
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get(path="/graph_parameter")
async def http_graph_inout_parameter(request: Request):
    return service.graph_inout_schema()

def parse_args():
    parser = argparse.ArgumentParser(description="Start FastAPI server")
    parser.add_argument("-m", type=str, default="http", help="Run mode, support http,flow,node")
    parser.add_argument("-n", type=str, default="", help="Node ID for single node run")
    parser.add_argument("-p", type=int, default=5000, help="HTTP server port")
    parser.add_argument("-i", type=str, default="", help="Input JSON string for flow/node mode")
    return parser.parse_args()


def parse_input(input_str: str) -> Dict[str, Any]:
    """Parse input string, support both JSON string and plain text"""
    if not input_str:
        return {"text": "你好"}

    # Try to parse as JSON first
    try:
        return json.loads(input_str)
    except json.JSONDecodeError:
        # If not valid JSON, treat as plain text
        return {"text": input_str}

def start_http_server(port):
    workers = 1
    reload = False
    # 强制禁用reload模式，确保服务稳定运行
    # if graph_helper.is_dev_env():
    #     reload = True

    logger.info(f"Start HTTP Server, Port: {port}, Workers: {workers}, Reload: {reload}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload, workers=workers)

if __name__ == "__main__":
    args = parse_args()
    if args.m == "http":
        start_http_server(args.p)
    elif args.m == "flow":
        payload = parse_input(args.i)
        result = asyncio.run(service.run(payload))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.m == "node" and args.n:
        payload = parse_input(args.i)
        result = asyncio.run(service.run_node(args.n, payload))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.m == "agent":
        agent_ctx = new_context(method="agent")
        for chunk in service.stream(
                {
                    "type": "query",
                    "session_id": "1",
                    "message": "你好",
                    "content": {
                        "query": {
                            "prompt": [
                                {
                                    "type": "text",
                                    "content": {"text": "现在几点了？请调用工具获取当前时间"},
                                }
                            ]
                        }
                    },
                },
                run_config={"configurable": {"session_id": "1"}},
                ctx=agent_ctx,
        ):
            print(chunk)
