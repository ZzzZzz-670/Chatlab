"""
日常对话 Agent - 孩子成长陪伴顾问
核心逻辑：读取诊断 Agent 交接 + 孩子画像 + 记忆库 → 日常对话 → 抽取成长信号 → 更新画像候选 → 识别纠偏 → 支持沟通预演
"""
import os
import json
import re
import logging
from typing import Annotated, Literal

from langchain_openai import ChatOpenAI
from langchain_core.messages import AnyMessage, AIMessage, HumanMessage, ToolMessage
from langgraph.graph import MessagesState, StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from coze_coding_utils.runtime_ctx.context import default_headers
from tools.daily_agent_tools import (
    # 查询类
    query_child_profile,
    query_diagnosis_handoff,
    query_growth_records,
    query_pending_observations,
    query_long_term_goals,
    query_parent_profile,
    query_family_interaction_patterns,
    query_questionnaire,
    query_correction_logs,
    # 写入类
    save_growth_record,
    save_profile_entry,
    save_pending_observation,
    save_correction,
    save_parent_profile_entry,
    save_family_interaction_pattern,
    save_long_term_goal,
    save_rehearsal_record,
    resolve_pending_observation,
    # 元信息提交
    submit_response_meta,
    # 核心理解库
    search_child_parent_understanding_library,
    search_parent_narrative_library,
    search_child_behavior_library,
    search_family_cycle_library,
    # 功能辅助库
    search_signal_memory_library,
    search_function_rule_library,
    search_style_example_library,
    search_backend_contract_library,
    # 核心聚合工具
    search_core_understanding_pack,
)

logger = logging.getLogger(__name__)

LLM_CONFIG = "config/agent_llm_config.json"

# 默认保留最近 20 轮对话 (40 条消息)
MAX_MESSAGES = 40


def _windowed_messages(old, new):
    """滑动窗口: 只保留最近 MAX_MESSAGES 条消息"""
    return add_messages(old, new)[-MAX_MESSAGES:]  # type: ignore


class AgentState(MessagesState):
    messages: Annotated[list[AnyMessage], _windowed_messages]


# ======================== 工具列表 ========================

ALL_TOOLS = [
    # 查询类
    query_child_profile,
    query_diagnosis_handoff,
    query_growth_records,
    query_pending_observations,
    query_long_term_goals,
    query_parent_profile,
    query_family_interaction_patterns,
    query_questionnaire,
    query_correction_logs,
    # 写入类
    save_growth_record,
    save_profile_entry,
    save_pending_observation,
    save_correction,
    save_parent_profile_entry,
    save_family_interaction_pattern,
    save_long_term_goal,
    save_rehearsal_record,
    resolve_pending_observation,
    # 元信息提交
    submit_response_meta,
    # 核心理解库（A/B/C/D）
    search_child_parent_understanding_library,
    search_parent_narrative_library,
    search_child_behavior_library,
    search_family_cycle_library,
    # 功能辅助库
    search_signal_memory_library,
    search_function_rule_library,
    search_style_example_library,
    search_backend_contract_library,
    # 核心聚合工具（优先使用）
    search_core_understanding_pack,
]


# ======================== JSON 输出提取 ========================

def _extract_natural_language(text: str) -> str:
    """从模型的文本输出中提取自然语言内容。
    
    模型有时会把回复包裹在 JSON 结构中输出，此函数负责提取其中的自然语言文本。
    """
    if not text or not isinstance(text, str):
        return text or ""
    
    stripped = text.strip()
    
    # 如果不是 JSON 格式，直接返回
    if not stripped.startswith('{') and not stripped.startswith('```'):
        return text
    
    # 尝试提取 ```json ... ``` 代码块
    json_block_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', stripped, re.DOTALL)
    if json_block_match:
        json_str = json_block_match.group(1).strip()
    else:
        json_str = stripped
    
    # 尝试解析 JSON
    try:
        data = json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        return text
    
    if not isinstance(data, dict):
        return text
    
    # 结构1: {"reply": {"content": "...", ...}, ...}
    reply = data.get('reply', {})
    if isinstance(reply, dict):
        content = reply.get('content', '')
        if content and isinstance(content, str):
            return content
    
    # 结构2: {"content": "...", ...}
    content = data.get('content', '')
    if content and isinstance(content, str):
        return content
    
    return text


# ======================== System Prompt 加载 ========================

def _build_system_prompt(workspace_path: str) -> str:
    """构建系统提示词：只使用01号文档的完整内容，知识库通过 search_knowledge 工具按需检索"""
    config_path = os.path.join(workspace_path, LLM_CONFIG)

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    base_sp = cfg.get("sp", "")

    # 知识库通过 search_knowledge 工具按需检索，不再全量拼接到 Prompt
    # 当你需要规则指导时，主动调用 search_knowledge 工具搜索

    logger.info(f"Built system prompt with {len(base_sp)} chars (knowledge via tool)")
    return base_sp


# ======================== Agent 图构建 ========================

def _should_continue(state: AgentState) -> Literal["tools", "format_output"]:
    """判断 agent 是否需要继续调用工具，还是输出结果"""
    messages = state["messages"]
    last_message = messages[-1]
    
    # 如果模型调用了工具，继续执行工具（只有 AIMessage 才可能有 tool_calls）
    if isinstance(last_message, AIMessage) and getattr(last_message, 'tool_calls', None):
        return "tools"
    
    # 否则进入格式化输出节点
    return "format_output"


def _format_output(state: AgentState) -> dict:
    """后处理节点：提取所有 AI 消息中的自然语言内容。
    
    如果模型输出了 JSON 格式的文本（尽管 Prompt 要求不要这样做），
    此节点会从中提取自然语言内容，确保前端只看到纯自然语言。
    同时处理带有 tool_calls 的 AIMessage（它们的 content 也可能是 JSON）。
    """
    messages = state["messages"]
    new_messages = []
    changed = False
    
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.content:
            extracted = _extract_natural_language(msg.content)
            if extracted != msg.content:
                changed = True
                tool_calls = getattr(msg, 'tool_calls', None)
                if tool_calls:
                    # 带有 tool_calls 的消息：替换 content 但保留 tool_calls
                    new_msg = AIMessage(
                        content=extracted,
                        tool_calls=tool_calls,
                        additional_kwargs=getattr(msg, 'additional_kwargs', {}),
                        id=getattr(msg, 'id', None),
                    )
                else:
                    new_msg = AIMessage(
                        content=extracted,
                        additional_kwargs=getattr(msg, 'additional_kwargs', {}),
                        id=getattr(msg, 'id', None),
                    )
                new_messages.append(new_msg)
            else:
                new_messages.append(msg)
        else:
            new_messages.append(msg)
    
    if changed:
        logger.info("Extracted natural language from JSON output in format_output node")
    
    return {"messages": new_messages}


def build_agent(ctx=None):
    """构建日常对话 Agent（使用自定义 LangGraph 图，含输出格式化节点）"""
    workspace_path = os.getenv("COZE_WORKSPACE_PATH", "/workspace/projects")
    config_path = os.path.join(workspace_path, LLM_CONFIG)

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    api_key = os.getenv("COZE_WORKLOAD_IDENTITY_API_KEY")
    base_url = os.getenv("COZE_INTEGRATION_MODEL_BASE_URL")

    # 构建系统提示词（知识库通过工具按需检索）
    system_prompt = _build_system_prompt(workspace_path)

    llm = ChatOpenAI(
        model=cfg["config"].get("model"),
        api_key=api_key,
        base_url=base_url,
        temperature=cfg["config"].get("temperature", 0.7),
        streaming=True,
        timeout=cfg["config"].get("timeout", 600),
        extra_body={
            "thinking": {
                "type": cfg["config"].get("thinking", "disabled"),
            }
        },
        default_headers=default_headers(ctx) if ctx else {},
    )

    # 将工具绑定到模型
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    # 定义 agent 节点
    def agent_node(state: AgentState):
        """Agent 主节点：调用 LLM 生成回复"""
        response = llm_with_tools.invoke(state["messages"])
        return {"messages": [response]}

    # 创建工具节点
    tool_node = ToolNode(ALL_TOOLS)

    # 构建图
    graph = StateGraph(AgentState)

    # 添加节点
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_node("format_output", _format_output)

    # 设置入口
    graph.add_edge(START, "agent")

    # 条件路由：agent → tools 或 format_output
    graph.add_conditional_edges(
        "agent",
        _should_continue,
        {
            "tools": "tools",
            "format_output": "format_output",
        }
    )

    # tools 执行完后回到 agent
    graph.add_edge("tools", "agent")

    # format_output 是终点
    graph.add_edge("format_output", END)

    # 长期记忆由网页后端统一读取、注入和写入；Agent 侧保持无状态，
    # 避免双 Agent 各自持有独立会话记忆。
    compiled = graph.compile(checkpointer=None)

    logger.info("Built daily agent with custom graph (3 nodes: agent, tools, format_output)")
    return compiled
