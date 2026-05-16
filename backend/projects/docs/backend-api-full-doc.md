# 对话实验室 — Agent 后端完整技术文档

> 本文档描述后端 Agent 服务的完整代码逻辑、API 契约、数据流，以及与外部前端的一切交互规则。
> 不涉及任何前端页面实现。

---

## 一、项目架构总览

```
/workspace/projects/
├── config/
│   └── agent_llm_config.json        # Agent 模型配置 + 系统Prompt（完整SP）
├── src/
│   ├── main.py                      # FastAPI 服务主入口（端口 5000）
│   ├── agents/agent.py              # Agent 构建（LangChain create_agent）
│   ├── tools/knowledge_tool.py      # 知识库搜索工具 @tool
│   └── storage/memory/
│       └── memory_saver.py          # Checkpointer（PostgresSaver 优先 / MemorySaver 兜底）
├── assets/                           # 静态文件目录（旧前端，已弃用）
└── pyproject.toml                    # 依赖声明
```

---

## 二、API 接口契约（前端必读）

### 2.1 `POST /v1/chat/completions` — 核心对话接口

#### 请求格式

```json
{
  "session_id": "uuid-string",     // 【必填】唯一会话标识，后端用它维护多轮状态
  "stream": true,                  // true=流式SSE, false=JSON一次性返回
  "messages": [                    // 消息列表（后端取最后一条 user 消息）
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

**契约说明**：
- `session_id` 是**唯一**的会话标识，后端用它映射到 `thread_id` + checkpointer 维护多轮状态
- `messages` 字段存在但**后端只取最后一条 `role=user` 的消息**作为本轮输入；历史由 checkpointer 管理，前端无需发送完整历史
- 不需要 `conversation_id`，此字段如存在将被忽略
- `model` 字段可选，后端忽略（使用配置文件中的模型）

#### 流式响应（stream=true）

SSE 流中会出现三种 event 类型：

**① `event: message` — 正常内容块（OpenAI 兼容格式）**

```
event: message
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1234567890,"model":"doubao-seed-2-0-pro-260215","choices":[{"index":0,"delta":{"content":"文本片段"},"finish_reason":null}]}

event: message
data: [DONE]
```

**内容过滤保证**：所有通过 `delta.content` 输出的文本已由后端过滤，前端**无需**再做二次过滤。过滤内容包括：
- `DIAGNOSIS_READY` 标记 → 从 content 中完全剥离
- 内部分析指令（分析:/推理:/后台:/内部:/步骤N:/阶段N: 等冒号开头的行）
- 知识库检索痕迹（---结果N---、相关度:0.XX、查询到N条结果）
- Markdown 表格分隔线和行
- 内部术语（后台想判断/家长标签/不直接采信/转成分支问题 等）
- 章节标题（中文数字/阿拉伯数字/罗马数字编号的标题行）
- 判断性短句、内部规则短句
- 工具调用（tool_calls）和工具结果 → **永不**进入用户 content

**② `event: diagnosis` — 诊断卡结构化数据（与 message 并行）**

当后端检测到 AI 输出中包含 `DIAGNOSIS_READY` 标记时，会从完整文本中提取结构化诊断数据，作为独立事件发出：

```
event: diagnosis
data: {"blindSpot":"...","coreMechanism":"...","behaviorProtection":"...","prediction":"...","suggestions":"..."}
```

字段说明：
| 字段 | 说明 |
|------|------|
| `blindSpot` | 家长盲点 |
| `coreMechanism` | 核心机制 |
| `behaviorProtection` | 行为保护 |
| `prediction` | 预测验证 |
| `suggestions` | 改善建议 |

注意：
- `DIAGNOSIS_READY` 标记已从 `delta.content` 中完全剥离，不会出现在前端显示文本中
- 如果某个字段在 AI 输出中未找到，对应值为 `""`
- 前端可以安全地用此 JSON 渲染诊断卡 UI，无需从自然语言中解析

**③ `event: session` — 会话信息（流结束时发出）**

```
event: session
data: {"session_id":"uuid-string"}
```

- 前端应保存此 `session_id`，在后续多轮对话中继续使用同一个值
- 即使前端传入的 `session_id` 会被原样返回，也应使用此字段确认

#### 非流式响应（stream=false）

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "doubao-seed-2-0-pro-260215",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "完整回复文本（已过滤）"},
    "finish_reason": "stop"
  }],
  "session_id": "uuid-string",
  "diagnosis": {
    "blindSpot": "...",
    "coreMechanism": "...",
    "behaviorProtection": "...",
    "prediction": "...",
    "suggestions": "..."
  }
}
```

- `diagnosis` 字段：仅在 AI 回复中包含 `DIAGNOSIS_READY` 时才出现，否则不存在
- `session_id` 字段：始终存在

---

### 2.2 `GET /health` — 健康检查

```json
{
  "status": "ok",
  "message": "Service is running",
  "memory_backend": "postgres"    // 或 "memory"
}
```

- `memory_backend`:
  - `"postgres"` — 使用 PostgreSQL 持久化，重启后历史不丢失
  - `"memory"` — 退化为内存存储，**重启后历史会丢失**，前端应降低"可恢复历史"的承诺
  - `"not_initialized"` — 尚未初始化（首次 Agent 调用前）

---

### 2.3 `POST /api/tts` — 文本转语音（预留接口）

```json
// 请求
{"text": "要转换的文本", "voice": "default"}

// 响应
音频流 (audio/mpeg)
```

---

### 2.4 `POST /api/asr` — 语音转文本（预留接口）

```json
// 请求
FormData: audio_file=<wav/mp3>

// 响应
{"text": "识别出的文本"}
```

---

## 三、数据流全景图

### 3.1 流式对话完整流程

```
前端                           后端 (src/main.py)                     Agent
 │                                │                                    │
 │──POST /v1/chat/completions───>│                                    │
 │  {session_id, stream:true,    │                                    │
 │   messages: [...]}            │──invoke agent.ainvoke()──────────>│
 │                               │  config={thread_id: session_id}   │
 │                               │                                    │──LLM调用
 │                               │                                    │──tool_call
 │                               │  <──_filter_sse_chunk()──────────│  (knowledge_tool)
 │                               │    过滤每个delta.content            │
 │                               │    检测DIAGNOSIS_READY             │
 │                               │    跳过tool_calls/tool results     │
 │                               │                                    │
 │<──event: message─────────────│                                    │
 │  {delta:{content:"你好"}}     │                                    │
 │                               │                                    │
 │<──event: message─────────────│                                    │
 │  {delta:{content:"想问下"}}   │                                    │
 │                               │                                    │
 │  ...                          │                                    │
 │                               │    ┌──DIAGNOSIS_READY检测────┐      │
 │                               │    │ 从累积文本提取诊断字段  │      │
 │                               │    └─────────────────────────┘      │
 │                               │                                    │
 │<──event: diagnosis───────────│                                    │
 │  {blindSpot,coreMechanism..} │                                    │
 │                               │                                    │
 │<──event: session─────────────│                                    │
 │  {session_id}                 │                                    │
 │                               │                                    │
 │<──event: message─────────────│                                    │
 │  data: [DONE]                 │                                    │
```

### 3.2 过滤逻辑详解

`_filter_sse_chunk()` 对每个 SSE chunk 执行：

1. **类型判断**：只处理 `delta.content` 类型，跳过 `tool_calls`/`role`/空内容
2. **累积缓冲**：将所有 content 拼接到 `_accumulated_text`，支持跨 chunk 的行级过滤
3. **文本过滤** (`_filter_text()`)：
   - 剥离 `DIAGNOSIS_READY` / `###DIAGNOSIS_READY###` 标记
   - 过滤 15 类正则模式（分析行、推理行、知识库痕迹、Markdown表格、内部术语等）
   - 行级过滤：只过滤匹配的行，保留其他内容
4. **诊断检测**：累积文本包含 `DIAGNOSIS_READY` → 流结束时触发 `event: diagnosis`
5. **Tool call 屏蔽**：`finish_reason=tool_calls` 的 chunk 不输出，等待工具执行完成后的内容

---

## 四、后端完整代码

### 4.1 `src/main.py` — FastAPI 服务主入口

```python
import argparse
import asyncio
import json
import re
import threading
import traceback
import logging
from typing import Any, Dict, Iterable, AsyncIterable, AsyncGenerator, Optional
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

from coze_coding_utils.openai.handler import OpenAIChatHandler, RequestConverter, ResponseConverter
from coze_coding_utils.openai.types.request import ChatCompletionRequest, ChatMessage
from coze_coding_utils.openai.types.response import (
    ChatCompletionChunk, ChatCompletionResponse, Delta, ChunkChoice, ChatCompletionResponseChoice, ChatCompletionResponseMessage
)
from storage.memory.memory_saver import get_memory_saver
from agents.agent import build_agent, LLM_CONFIG

# ==================== Configuration ====================

parser = argparse.ArgumentParser()
parser.add_argument("-m", "--mode", default="http", help="Service mode")
parser.add_argument("-p", "--port", type=int, default=5000, help="HTTP port")
args, _ = parser.parse_known_args()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Dialogue Lab Agent API")

# ==================== Shared Text Filtering ====================

def _filter_text(text: str) -> str:
    """
    过滤 AI 回复中的内部指令/标记/知识库痕迹，返回用户可见文本。
    此函数同时被 _filter_chunk（/stream_run）和 _filter_sse_chunk（/v1/chat/completions）使用。
    """
    if not text:
        return text
    original = text

    # 1) 剥离 DIAGNOSIS_READY 标记
    text = re.sub(r'#{0,3}\s*DIAGNOSIS_READY\s*#{0,3}', '', text)

    # 2) 过滤冒号开头的分析行
    text = re.sub(
        r'(?i)(分析[:：]|推理[:：]|后台[:：]|内部[:：]|步骤\d+[:：]|阶段\d+[:：]|流程\d+[:：]'
        r'|运行顺序[:：]|信息轴[:：]|证据轴[:：]|分支[:：]|判断[:：]|裁决[:：]'
        r'|追问优先级[:：]|家长可信度[:：]|孩子可信度[:：]|进度\d+[:：])[^\n]*', '', text)

    # 3) 过滤分析句
    for pat in [
        r'当前已有证据[：:].*?(?:\n|$)',
        r'还需要裁决[：:].*?(?:\n|$)',
        r'家长已回答[：:].*?(?:\n|$)',
        r'最支持分支[：:].*?(?:\n|$)',
    ]:
        text = re.sub(pat, '', text, flags=re.IGNORECASE)

    # 4) 过滤纯指令列表
    text = re.sub(r'^\s*(前台必须|后台|内部|你不需要|你必须|你应该在心里|思考框架|输出格式|语言风格)\b[^\n]*$', '', text, flags=re.MULTILINE)

    # 5) 过滤 JSON 分析
    text = re.sub(r'\{[^}]*"(分析|推理|判断|分支|方向|步骤|阶段)"[^}]*\}', '', text)

    # 6) 过滤知识库检索标记
    text = re.sub(r'---\s*结果\s*\d+.*?---', '', text, flags=re.DOTALL)
    text = re.sub(r'相关度[:：]\s*\d+\.\d+', '', text)
    text = re.sub(r'查询到.*?条结果', '', text)

    # 7) 过滤 Markdown 表格
    text = re.sub(r'^\s*\|[\s\-:|]+\|\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\|.*\|\s*$', '', text, flags=re.MULTILINE)

    # 8) 过滤内部术语
    for term in ['后台想判断', '家长标签', '不直接采信', '转成分支问题',
                  '前台必须', '不要问', '改问', '安全废话', '反证边界', '黑名单']:
        text = text.replace(term, '')

    # 9) 过滤章节标题
    text = re.sub(r'^\s*(#{1,6}\s*)?([一二三四五六七八九十]+[、.．]|\d+[、.．]|第[一二三四五六七八九十\d]+[章节步阶部分]|[IVX]+[、.．])\s*[^\n]{0,50}$', '', text, flags=re.MULTILINE)

    # 10) 过滤判断性短句
    text = re.sub(r'^\s*(家长\w{0,6}(高控制|控制|没有结束感)|孩子\w{0,6}(反抗|回避|依赖))\s*[。！？!?.]*\s*$', '', text, flags=re.MULTILINE)

    # 11) 过滤内部规则短句
    text = re.sub(r'^\s*(家长说\w+就判断|全部解释成|顺着家长说|就默认解释成|或反过来)\s*[。！？!?.]*\s*$', '', text, flags=re.MULTILINE)

    # 12) 清理空行
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip() if text.strip() != original.strip() else text


# ==================== Diagnosis Extraction ====================

def _parse_diagnosis(text: str) -> Optional[Dict[str, str]]:
    """
    从 AI 完整回复中提取结构化诊断卡数据。
    返回各字段字典，提取失败返回 None。
    """
    if 'DIAGNOSIS_READY' not in text:
        return None

    def _extract(label: str) -> str:
        # 优先 **label** 格式
        m = re.search(rf'\*\*{re.escape(label)}\*\*[：:]\s*(.*?)(?=\n\*\*|\Z)', text, re.DOTALL)
        if m:
            return m.group(1).strip()
        # 兜底 label： 格式
        m = re.search(rf'{re.escape(label)}[：:]\s*(.*?)(?=\n\S[^\n]*[：:]|\Z)', text, re.DOTALL)
        if m:
            return m.group(1).strip()
        return ""

    fields = {
        "blindSpot": "家长盲点",
        "coreMechanism": "核心机制",
        "behaviorProtection": "行为保护",
        "prediction": "预测验证",
        "suggestions": "改善建议",
    }

    result = {}
    for key, label in fields.items():
        val = _extract(label)
        result[key] = val

    # 如果所有字段都为空，返回 None
    if not any(result.values()):
        return None

    return result


# ==================== SSE Stream Filter State ====================

class _StreamFilterState:
    """维护单个 SSE 流的过滤状态"""
    def __init__(self):
        self._accumulated_text = ""
        self._has_diagnosis = False
        self._last_emitted_len = 0


def _filter_sse_chunk(chunk_data: dict, state: _StreamFilterState) -> list:
    """
    过滤单个 SSE chunk，返回要发送的 SSE event 列表。
    每个 event 是 (event_type, data_dict) 元组。
    返回空列表表示跳过此 chunk。
    """
    events = []
    choices = chunk_data.get("choices", [])
    if not choices:
        return []

    choice = choices[0]
    delta = choice.get("delta", {})
    finish_reason = choice.get("finish_reason")

    # --- 处理 tool_calls / role:tool --- 跳过不输出
    if "tool_calls" in delta or delta.get("role") == "tool":
        return []

    content = delta.get("content", "")
    if content is None:
        content = ""

    # 累积全文
    state._accumulated_text += content

    # 过滤 content
    filtered = _filter_text(content)

    # 行级过滤：如果过滤后内容被清空（整行都是内部指令），跳过此 chunk
    if content.strip() and not filtered.strip():
        return []

    # 构建过滤后的 chunk
    new_chunk = dict(chunk_data)
    new_chunk["choices"] = [dict(choice)]
    new_chunk["choices"][0]["delta"] = dict(delta)
    new_chunk["choices"][0]["delta"]["content"] = filtered

    # 跳过 finish_reason=tool_calls 的 chunk（等待工具执行后的内容）
    if finish_reason == "tool_calls":
        return []

    events.append(("message", new_chunk))
    return events


# ==================== GraphService ====================

class GraphService:
    def __init__(self):
        self._agent = None
        self._agent_lock = threading.Lock()

    def _get_agent(self, ctx: Context = None):
        with self._agent_lock:
            if self._agent is None:
                self._agent = build_agent(ctx=ctx)
            return self._agent

    def _filter_chunk(self, chunk, has_diagnosis_flag=None):
        """旧路径过滤（/stream_run 使用），保持兼容"""
        return _filter_text(str(chunk)), False

    async def stream(self, session_id: str, message: str, ctx: Context = None):
        agent = self._get_agent(ctx=ctx)
        config = {"configurable": {"thread_id": session_id}}
        input_msg = {"messages": [("user", message)]}

        runner = AgentStreamRunner(agent, input_msg, config)
        async for chunk in runner.stream():
            filtered, _ = self._filter_chunk(chunk)
            if filtered:
                yield filtered


# ==================== AgentStreamRunner ====================

class AgentStreamRunner:
    def __init__(self, agent, input_msg, config):
        self.agent = agent
        self.input_msg = input_msg
        self.config = config

    async def stream(self):
        async for event in self.agent.astream_events(
            self.input_msg,
            version="v2",
            config=self.config,
        ):
            kind = event.get("event", "")
            if kind == "on_chat_model_stream":
                token = event.get("data", {}).get("chunk")
                if token and hasattr(token, "content") and token.content:
                    yield token.content
            elif kind == "on_tool_end":
                pass


# ==================== Memory Manager Singleton ====================

class _MemoryManager:
    """管理 checkpointer 单例，供 /health 查询后端类型"""
    def __init__(self):
        self._checkpointer = None
        self._backend_type = "not_initialized"

    def get_checkpointer(self):
        if self._checkpointer is None:
            try:
                self._checkpointer = get_memory_saver()
                # 判断类型
                from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
                if isinstance(self._checkpointer, AsyncPostgresSaver):
                    self._backend_type = "postgres"
                else:
                    self._backend_type = "memory"
            except Exception:
                from langgraph.checkpoint.memory import MemorySaver
                self._checkpointer = MemorySaver()
                self._backend_type = "memory"
                logger.warning("PostgreSQL checkpointer failed, falling back to MemorySaver. History will be lost on restart.")
        return self._checkpointer

    @property
    def backend_type(self):
        return self._backend_type


_memory_manager = _MemoryManager()


# ==================== API Routes ====================

graph_service = GraphService()


@app.get("/health")
async def health_check():
    return JSONResponse({
        "status": "ok",
        "message": "Service is running",
        "memory_backend": _memory_manager.backend_type,
    })


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """
    OpenAI 兼容接口，支持流式/非流式。
    - 所有 delta.content 经过 _filter_text() 过滤
    - DIAGNOSIS_READY 从 content 剥离，改为 event: diagnosis 独立输出
    - tool_calls/tool results 不进入用户可见流
    - 流末尾输出 event: session {session_id}
    - 非流式返回包含 session_id 和 diagnosis 字段
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # 提取 session_id
    session_id = body.get("session_id")
    if not session_id:
        import uuid
        session_id = str(uuid.uuid4())

    stream = body.get("stream", True)

    # 提取最后一条 user 消息
    messages = body.get("messages", [])
    user_message = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_message = msg.get("content", "")
            break

    if not user_message:
        raise HTTPException(status_code=400, detail="No user message found")

    ctx = new_context(method="chat_completions")

    if stream:
        return StreamingResponse(
            _filtered_sse_stream(session_id, user_message, ctx),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
    else:
        # 非流式：收集完整回复后过滤
        full_text = ""
        agent = graph_service._get_agent(ctx=ctx)
        config = {"configurable": {"thread_id": session_id}}
        input_msg = {"messages": [("user", user_message)]}

        async for event in agent.astream_events(input_msg, version="v2", config=config):
            kind = event.get("event", "")
            if kind == "on_chat_model_stream":
                token = event.get("data", {}).get("chunk")
                if token and hasattr(token, "content") and token.content:
                    full_text += token.content

        filtered_text = _filter_text(full_text)
        diagnosis = _parse_diagnosis(full_text)

        response = {
            "id": f"chatcmpl-{session_id[:8]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "doubao-seed-2-0-pro-260215",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": filtered_text},
                "finish_reason": "stop",
            }],
            "session_id": session_id,
        }
        if diagnosis:
            response["diagnosis"] = diagnosis

        return JSONResponse(response)


async def _filtered_sse_stream(session_id: str, user_message: str, ctx: Context) -> AsyncGenerator[str, None]:
    """
    过滤后的 SSE 流生成器。
    1) 每个内容 chunk 经过 _filter_sse_chunk() 过滤
    2) DIAGNOSIS_READY 从 content 剥离
    3) 流结束时如检测到诊断标记，输出 event: diagnosis
    4) 流末尾输出 event: session {session_id}
    """
    filter_state = _StreamFilterState()
    agent = graph_service._get_agent(ctx=ctx)
    config = {"configurable": {"thread_id": session_id}}
    input_msg = {"messages": [("user", user_message)]}

    try:
        async for event in agent.astream_events(input_msg, version="v2", config=config):
            kind = event.get("event", "")

            if kind == "on_chat_model_stream":
                token = event.get("data", {}).get("chunk")
                if token and hasattr(token, "content") and token.content:
                    chunk_data = {
                        "id": f"chatcmpl-{session_id[:8]}",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": "doubao-seed-2-0-pro-260215",
                        "choices": [{
                            "index": 0,
                            "delta": {"content": token.content},
                            "finish_reason": None,
                        }],
                    }
                    filtered_events = _filter_sse_chunk(chunk_data, filter_state)
                    for evt_type, evt_data in filtered_events:
                        yield f"event: {evt_type}\ndata: {json.dumps(evt_data, ensure_ascii=False)}\n\n"

            elif kind == "on_chat_model_end":
                # 检查是否有 tool_calls
                output = event.get("data", {}).get("output")
                if output and hasattr(output, "tool_calls") and output.tool_calls:
                    # 不输出，等待工具执行后继续
                    pass

        # 流结束 — 输出 finish chunk
        finish_chunk = {
            "id": f"chatcmpl-{session_id[:8]}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "doubao-seed-2-0-pro-260215",
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "stop",
            }],
        }
        yield f"event: message\ndata: {json.dumps(finish_chunk, ensure_ascii=False)}\n\n"

        # 输出诊断卡（如有）
        if "DIAGNOSIS_READY" in filter_state._accumulated_text:
            diagnosis = _parse_diagnosis(filter_state._accumulated_text)
            if diagnosis:
                yield f"event: diagnosis\ndata: {json.dumps(diagnosis, ensure_ascii=False)}\n\n"

        # 输出 session 信息
        yield f"event: session\ndata: {json.dumps({'session_id': session_id})}\n\n"

        # 结束标记
        yield "event: message\ndata: [DONE]\n\n"

    except Exception as e:
        logger.error(f"SSE stream error: {traceback.format_exc()}")
        error_chunk = {
            "id": f"chatcmpl-{session_id[:8]}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "doubao-seed-2-0-pro-260215",
            "choices": [{
                "index": 0,
                "delta": {"content": f"\n[服务异常，请重试]"},
                "finish_reason": "stop",
            }],
        }
        yield f"event: message\ndata: {json.dumps(error_chunk, ensure_ascii=False)}\n\n"
        yield "event: message\ndata: [DONE]\n\n"


# ==================== TTS / ASR Stubs ====================

@app.post("/api/tts")
async def tts(request: Request):
    body = await request.json()
    text = body.get("text", "")
    return Response(content=f"TTS not implemented for: {text}", media_type="text/plain")


@app.post("/api/asr")
async def asr(request: Request):
    form = await request.form()
    return JSONResponse({"text": "ASR not implemented"})


# ==================== Static Files ====================

assets_path = Path(__file__).parent.parent / "assets"
if assets_path.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(assets_path), html=True), name="assets")


# ==================== Entry Point ====================

if __name__ == "__main__":
    cozeloop.start()
    uvicorn.run(app, host="0.0.0.0", port=args.port)
```

---

### 4.2 `src/agents/agent.py` — Agent 构建

```python
import os
import json
from typing import Annotated
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.graph import MessagesState
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage
from coze_coding_utils.runtime_ctx.context import default_headers
from storage.memory.memory_saver import get_memory_saver

LLM_CONFIG = "config/agent_llm_config.json"
MAX_MESSAGES = 40

def _windowed_messages(old, new):
    return add_messages(old, new)[-MAX_MESSAGES:]

class AgentState(MessagesState):
    messages: Annotated[list[AnyMessage], _windowed_messages]

def build_agent(ctx=None):
    workspace_path = os.getenv("COZE_WORKSPACE_PATH", "/workspace/projects")
    config_path = os.path.join(workspace_path, LLM_CONFIG)
    with open(config_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)

    api_key = os.getenv("COZE_WORKLOAD_IDENTITY_API_KEY")
    base_url = os.getenv("COZE_INTEGRATION_MODEL_BASE_URL")

    llm = ChatOpenAI(
        model=cfg['config'].get("model"),
        api_key=api_key,
        base_url=base_url,
        temperature=cfg['config'].get('temperature', 0.7),
        streaming=True,
        timeout=cfg['config'].get('timeout', 600),
        extra_body={
            "thinking": {
                "type": cfg['config'].get('thinking', 'disabled')
            }
        },
        default_headers=default_headers(ctx) if ctx else {},
    )

    from tools.knowledge_tool import search_knowledge_base

    return create_agent(
        model=llm,
        system_prompt=cfg.get("sp"),
        tools=[search_knowledge_base],
        checkpointer=get_memory_saver(),
        state_schema=AgentState,
    )
```

---

### 4.3 `src/tools/knowledge_tool.py` — 知识库搜索工具

```python
import re
import logging
from langchain.tools import tool
from coze_coding_utils.log.write_log import request_context
from coze_coding_utils.runtime_ctx.context import new_context

logger = logging.getLogger(__name__)

_REMOVE_TITLES = [
    '后台想判断', '不要问', '改问', '家长标签',
    '不直接采信', '转成分支问题', '前台必须', '黑名单',
    '安全废话', '反证边界',
]

_INTERNAL_TITLE_MAP = {
    '家长标签': '家长误区',
    '不直接采信': '需要验证的说法',
    '转成分支问题': '需要细化的问题',
    '后台想判断': '核心关注点',
    '反证边界': '条件边界',
}

def _clean_chunk(text: str) -> str:
    """清洗知识库片段，移除内部术语和格式"""
    if not text:
        return text
    for term in _REMOVE_TITLES:
        text = text.replace(term, '')
    text = re.sub(r'---\s*结果\s*\d+.*?---', '', text, flags=re.DOTALL)
    text = re.sub(r'相关度[:：]\s*\d+\.\d+', '', text)
    text = re.sub(r'查询到.*?条结果', '', text)
    text = re.sub(r'^\s*\|[\s\-:|]+\|\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\|.*\|\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

@tool
def search_knowledge_base(query: str) -> str:
    """搜索教育知识库，获取与家长教育问题相关的专业知识。当需要专业教育理论、案例或方法时使用。"""
    ctx = request_context.get() or new_context(method="search_knowledge_base")
    try:
        from coze_coding_dev_sdk import KnowledgeClient
        client = KnowledgeClient()
        results = client.search(query=query, top_k=5, min_score=0.3)
        if not results:
            return ""
        output_parts = []
        for i, item in enumerate(results, 1):
            title = item.get('title', '')
            content = item.get('content', '')
            score = item.get('score', 0)
            # 清洗内容
            content = _clean_chunk(content)
            if not content:
                continue
            output_parts.append(f"--- 结果{i} ---\n标题: {title}\n相关度: {score:.2f}\n{content}")
        return "\n\n".join(output_parts) if output_parts else ""
    except Exception as e:
        logger.error(f"Knowledge base search error: {e}")
        return ""
```

---

### 4.4 `src/storage/memory/memory_saver.py` — 检查点管理

```python
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_saver_instance = None
_saver_type = None

def get_db_url() -> Optional[str]:
    url = os.getenv("DATABASE_URL")
    if not url:
        host = os.getenv("DB_HOST", "")
        port = os.getenv("DB_PORT", "5432")
        user = os.getenv("DB_USER", "")
        password = os.getenv("DB_PASSWORD", "")
        dbname = os.getenv("DB_NAME", "")
        if all([host, user, password, dbname]):
            url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}?sslmode=require"
    return url

def get_memory_saver():
    global _saver_instance, _saver_type
    if _saver_instance is not None:
        return _saver_instance

    db_url = get_db_url()
    if db_url:
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            import asyncio

            async def _init_postgres():
                saver = AsyncPostgresSaver.from_conn_string(db_url + "&search_path=memory")
                for attempt in range(2):
                    try:
                        await asyncio.wait_for(saver.__aenter__(), timeout=15)
                        await saver.setup()
                        return saver
                    except Exception:
                        if attempt == 0:
                            continue
                        raise
                return None

            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    _saver_instance = loop.run_in_executor(pool, lambda: asyncio.run(_init_postgres()))
                    _saver_instance = asyncio.run(_init_postgres())
            else:
                _saver_instance = asyncio.run(_init_postgres())
            _saver_type = "postgres"
            logger.info("Using PostgreSQL checkpointer")
            return _saver_instance
        except Exception as e:
            logger.warning(f"PostgreSQL init failed: {e}, falling back to MemorySaver")

    from langgraph.checkpoint.memory import MemorySaver
    _saver_instance = MemorySaver()
    _saver_type = "memory"
    logger.info("Using in-memory checkpointer (data lost on restart)")
    return _saver_instance

def get_saver_type():
    return _saver_type or "not_initialized"
```

---

### 4.5 `config/agent_llm_config.json` — 模型配置 + 系统Prompt

```json
{
  "config": {
    "model": "doubao-seed-2-0-pro-260215",
    "temperature": 0.7,
    "top_p": 0.9,
    "max_completion_tokens": 10000,
    "timeout": 600,
    "thinking": "disabled"
  },
  "sp": "（完整系统Prompt，约2000字，包含角色定义、核心目标、绝对红线、每轮内部判断、追问原则、诊断卡质量标准、诊断卡格式、语言风格、禁止内容、知识库使用规则等。末尾标记为 ###DIAGNOSIS_READY###）",
  "tools": ["search_knowledge_base"]
}
```

> 注：`sp` 字段的完整内容过长，此处省略。核心要点：
> - 角色为清北学生伴学助手
> - 追问原则：一次一问，问可回忆的生活事实
> - 诊断卡格式：家长盲点/核心机制/行为保护/可解释的三个行为/预测验证/边界与轻验证/改善建议
> - 诊断卡末尾必须输出 `###DIAGNOSIS_READY###` 标记
> - 绝对红线：禁止输出后台分析/推理过程/分支名称/内部步骤/知识库痕迹

---

## 五、前端对接指南

### 5.1 SSE 事件监听

前端使用 `EventSource` 或 `fetch` + `ReadableStream` 连接 SSE，需处理三种 event：

```javascript
const response = await fetch('/v1/chat/completions', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    session_id: sessionId,   // 必填，多轮对话标识
    stream: true,
    messages: [{ role: 'user', content: userInput }]
  })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = '';

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });

  // 解析 SSE
  const lines = buffer.split('\n');
  buffer = lines.pop();  // 保留未完成的行

  let currentEvent = 'message';
  for (const line of lines) {
    if (line.startsWith('event: ')) {
      currentEvent = line.slice(7).trim();
    } else if (line.startsWith('data: ')) {
      const data = line.slice(6);
      if (data === '[DONE]') break;

      const parsed = JSON.parse(data);

      switch (currentEvent) {
        case 'message':
          // 正常内容 - 已过滤，可直接显示
          const content = parsed.choices?.[0]?.delta?.content || '';
          appendToChat(content);
          break;

        case 'diagnosis':
          // 结构化诊断卡数据 - 渲染为卡片 UI
          renderDiagnosisCard(parsed);
          // parsed = { blindSpot, coreMechanism, behaviorProtection, prediction, suggestions }
          break;

        case 'session':
          // 会话信息 - 保存 session_id
          sessionId = parsed.session_id;
          break;
      }
    }
  }
}
```

### 5.2 前端不再需要的逻辑

由于后端已完成过滤和诊断提取，前端**无需**实现以下逻辑：

| 旧逻辑 | 现状 |
|--------|------|
| 前端正则过滤（15类模式） | ❌ 不需要，后端 `_filter_text()` 已处理 |
| 前端检测 `DIAGNOSIS_READY` 标记 | ❌ 不需要，后端剥离并转为 `event: diagnosis` |
| 前端 `extractSection()` 解析诊断卡 | ❌ 不需要，后端 `_parse_diagnosis()` 提供结构化数据 |
| 发送完整消息历史 | ❌ 不需要，后端靠 checkpointer 管理历史 |
| `conversation_id` | ❌ 不需要，`session_id` 是唯一标识 |

### 5.3 多轮对话流程

```
1. 前端生成 UUID 作为 session_id
2. 每轮对话：POST /v1/chat/completions { session_id, stream:true, messages:[{role:user,content:...}] }
3. 后端通过 thread_id=session_id 查找 checkpointer 中的历史
4. 后端只取 messages 最后一条 user 消息作为本轮输入
5. 后端返回 event:session { session_id } 确认
6. 前端保持同一 session_id 继续下一轮
7. 新对话：前端生成新 UUID
```

### 5.4 诊断卡 UI 渲染

```javascript
function renderDiagnosisCard(data) {
  // data = {
  //   blindSpot: "家长盲点内容",
  //   coreMechanism: "核心机制内容",
  //   behaviorProtection: "行为保护内容",
  //   prediction: "预测验证内容",
  //   suggestions: "改善建议内容"
  // }

  // 渲染为底部抽屉卡片
  // 每个字段一个区块，字段名作为标题
  // 非空字段才渲染
}
```

### 5.5 错误处理

- HTTP 400：请求体无效（无 user 消息）
- HTTP 500：服务异常，SSE 流中会输出 `[服务异常，请重试]`
- `/health` 中 `memory_backend: "memory"` 时，前端应提示用户历史可能不持久

---

## 六、已知限制与优化方向

1. **`_filter_text` 行级过滤可能误伤**：部分正则过于宽泛（如章节标题过滤），可能误删正常内容。建议后续增加白名单机制。
2. **诊断卡解析依赖 Prompt 格式**：`_parse_diagnosis` 依赖 AI 输出 `**家长盲点**：` 格式，若模型格式偏移则提取失败。建议 Prompt 中更严格约束输出格式。
3. **checkpointer 退化无前端感知**：虽已增加 `/health` 的 `memory_backend` 字段，但前端需主动轮询才能发现。建议首次连接时检查。
4. **TTS/ASR 未实现**：当前为 stub，需要接入语音服务。
5. **并发安全**：`_memory_manager` 和 `graph_service` 使用线程锁，但高并发下可能有性能瓶颈。
