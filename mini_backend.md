# 最小化 Backend 架构方案

> 目标：在保留流式响应、AGENT_META 提取、用户信息注入、会话上下文的前提下，尽可能精简 backend。
>
> 当前问题：Coze 插件在外部 Python 环境不稳定，现有 LangGraph + OpenAI 兼容层链路太长易 500。
>
> 解决思路：让 Agent 逻辑和插件在 **Coze 平台内部** 运行，backend 只做轻量代理层，直接调用 Coze 原生 `/stream_run` HTTP 接口。

---

## 背景：Coze `/stream_run` 接口

参考官方示例（`call_api.py`）：

```python
import json, requests

url = "https://gnp8dz4r4n.coze.site/stream_run"
headers = {
    "Authorization": "Bearer <TOKEN>",
    "Content-Type": "application/json",
    "Accept": "text/event-stream",
}
payload = {
    "content": {
        "query": {
            "prompt": [
                {"type": "text", "content": {"text": "用户输入"}}
            ]
        }
    },
    "type": "query",
    "session_id": "同一 session_id 保持多轮上下文",
    "project_id": "7640760744073658402"
}

response = requests.post(url, headers=headers, json=payload, stream=True)
for line in response.iter_lines(decode_unicode=True):
    if line and line.startswith("data:"):
        parsed = json.loads(line[5:].strip())
        # parsed: {"type": "answer", "content": {"answer": "...<AGENT_META>..."}}
```

**特点**：
- SSE 流式返回，格式是 Coze 原生 JSON，不是 OpenAI 的 `/v1/chat/completions` 格式
- `session_id` 是 Coze 会话的唯一标识，复用同一个 `session_id` 即可保持上下文
- 输出文本中可能内嵌 `<AGENT_META>{...}</AGENT_META>` 结构化元数据

---

## 需求拆解

| 需求 | 技术实现 |
|------|----------|
| **流式响应 + 完整提取 AGENT_META** | SSE 流式代理 + 跨 chunk 状态机提取 `<AGENT_META>`（标签可能被 SSE chunk 截断） |
| **保留用户信息 & 个性化功能** | 接收前端的 `family_id` / `child_id` / 沟通偏好等，拼成 system prompt 注入 Coze `prompt` 数组 |
| **保证一致的会话上下文** | 维护 `(family_id, child_id)` → `session_id` 映射，同一用户复用 `session_id` |
| **暂不考虑记忆和用户画像** | 不调用 `storage/profile/`、`storage/memory/`、不持久化画像/成长记录 |

---

## 方案 A：保留独立 Python Backend（轻量 FastAPI 代理）

### 架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              前端 chat-lab                                   │
│  ┌─────────────────┐    POST /api/v1/chat (SSE)    ┌─────────────────────┐  │
│  │ DialogueLab2... │ ─────────────────────────────→ │ Next.js API Route   │  │
│  │ (React 组件)     │                               │ (透传或简单包装)      │  │
│  └─────────────────┘                               └─────────────────────┘  │
│                                                           │                  │
└───────────────────────────────────────────────────────────┼──────────────────┘
                                                            │ 转发请求
                                                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        精简 Backend (FastAPI)                                │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  POST /stream_run                                                   │    │
│  │    1. 解析 family_id / child_id / message / client_context         │    │
│  │    2. 查/生成 session_id → 复用 Coze 会话上下文                    │    │
│  │    3. 组装 system prompt（用户信息 + 沟通偏好注入）                 │    │
│  │    4. 调 Coze /stream_run (requests stream=True)                   │    │
│  │    5. AGENT_META 状态机提取（跨 chunk 拼接）                        │    │
│  │    6. 转发 SSE 给前端（文本 + event: agent_meta）                   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              │                                              │
│                    ┌─────────┴─────────┐                                    │
│                    ▼                   ▼                                    │
│              ┌──────────┐      ┌────────────┐                              │
│              │ Session  │      │ AGENT_META │                              │
│              │ 管理     │      │ 提取状态机  │                              │
│              │ (内存dict)│      │            │                              │
│              └──────────┘      └────────────┘                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                                            │
                                                            ▼
                                                  ┌─────────────────┐
                                                  │ Coze 平台        │
                                                  │ /stream_run      │
                                                  │ (Agent + 插件    │
                                                  │  在 Coze 内部跑)  │
                                                  └─────────────────┘
```

### 保留/新增的文件

```
backend/projects/
├── main.py              # 精简到 ~150 行，核心逻辑如下
├── requirements.txt     # fastapi, uvicorn, requests
└── call_api.py          # 参考保留，可整合进 main.py

# 以下全部可以移除：
# src/agents/      (LangGraph Agent 编排)
# src/tools/       (Coze 插件/工具调用)
# src/graphs/      (状态图)
# src/storage/     (画像/记忆持久化)
# coze_coding_utils 相关依赖
```

### `main.py` 核心结构（示意）

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import requests, json, uuid

app = FastAPI()

# ── Session 管理（内存版，可换 Redis/SQLite） ──
SESSION_MAP: dict[tuple[str, str], str] = {}

def get_session_id(family_id: str, child_id: str) -> str:
    key = (family_id, child_id)
    if key not in SESSION_MAP:
        SESSION_MAP[key] = str(uuid.uuid4())
    return SESSION_MAP[key]

# ── AGENT_META 状态机 ──
class MetaExtractor:
    """
    跨 SSE chunk 提取 <AGENT_META>...</AGENT_META>。
    标签可能被截断到相邻 chunk 中，需要用状态机处理。
    """
    def __init__(self):
        self.state = "NORMAL"       # NORMAL | IN_META
        self.meta_buffer = ""
        self.pending = ""           # 跨 chunk 的前缀缓冲

    def feed(self, text: str) -> tuple[str, dict | None]:
        """
        输入当前 chunk 的 answer 文本。
        返回 (visible_text, meta_dict_or_None)
        """
        visible = []
        meta_obj = None
        # 实际实现需处理：
        # 1. NORMAL 状态下检测 <AGENT_META> 的任意前缀匹配
        # 2. 部分前缀跨 chunk 时缓存到 self.pending
        # 3. IN_META 状态下累积内容，检测 </AGENT_META>
        # 4. 完整提取后 json.loads() 解析并切换回 NORMAL
        return "".join(visible), meta_obj

# ── 用户信息注入 ──
def build_prompt(user_message: str, family_id: str, child_id: str,
                 prefs: list[str], questionnaire_status: str) -> list[dict]:
    system_text = (
        f"你是家庭教育助手。当前用户：family_id={family_id}, child_id={child_id}\n"
        f"沟通偏好：{', '.join(prefs)}\n"
        f"问卷状态：{questionnaire_status}\n"
        "请根据以上信息调整回复风格。"
    )
    return [
        {"type": "text", "content": {"text": system_text}},
        {"type": "text", "content": {"text": user_message}},
    ]

# ── 核心路由 ──
@app.post("/stream_run")
async def stream_run(request: Request):
    body = await request.json()
    family_id = body.get("family_id", "family_demo")
    child_id = body.get("child_id", "child_demo")
    user_text = body.get("message", {}).get("text", "")
    prefs = body.get("client_context", {}).get("communication_prefs", [])
    q_status = body.get("client_context", {}).get("questionnaire_status", "not_started")

    session_id = get_session_id(family_id, child_id)
    prompts = build_prompt(user_text, family_id, child_id, prefs, q_status)

    payload = {
        "content": {"query": {"prompt": prompts}},
        "type": "query",
        "session_id": session_id,
        "project_id": "7640760744073658402",
    }

    coze_resp = requests.post(
        "https://gnp8dz4r4n.coze.site/stream_run",
        headers={"Authorization": "Bearer <TOKEN>", "Content-Type": "application/json"},
        json=payload,
        stream=True,
    )

    def event_generator():
        extractor = MetaExtractor()
        for line in coze_resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                yield "data: [DONE]\n\n"
                continue
            try:
                parsed = json.loads(data)
            except Exception:
                continue
            if parsed.get("type") == "answer":
                answer = parsed.get("content", {}).get("answer", "")
                visible, meta = extractor.feed(answer)
                if visible:
                    yield f"data: {json.dumps({'type':'answer','content':{'answer':visible}}, ensure_ascii=False)}\n\n"
                if meta:
                    yield f"event: agent_meta\ndata: {json.dumps(meta, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

### 优缺点

| 优点 | 缺点 |
|------|------|
| Backend 可控，Coze Token 不暴露给前端 | 多一层服务，需要部署和维护 |
| 可以在 backend 做统一的日志、监控、限流 | 需要处理 Python 服务的部署/扩容 |
| Session 管理、用户信息注入逻辑集中 | |
| 前端改动最小，Next.js API Route 几乎不用改 | |

---

## 方案 B：Next.js API Route 直接代理（无独立 Python Backend）

### 架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              前端 chat-lab                                   │
│  ┌─────────────────┐    POST /api/v1/chat (SSE)    ┌─────────────────────┐  │
│  │ DialogueLab2... │ ─────────────────────────────→ │ Next.js API Route   │  │
│  │ (React 组件)     │    SSE 流式消费                │ (/api/v1/chat)      │  │
│  └─────────────────┘                               └─────────────────────┘  │
│                                                           │                  │
└───────────────────────────────────────────────────────────┼──────────────────┘
                                                            │ 直接调 Coze
                                                            ▼
                                                  ┌─────────────────┐
                                                  │ Coze 平台        │
                                                  │ /stream_run      │
                                                  │ (Agent + 插件    │
                                                  │  在 Coze 内部跑)  │
                                                  └─────────────────┘
```

### 保留/新增的文件

```
chat-lab/src/app/api/v1/chat/route.ts    # 重写为 SSE 流式 + AGENT_META 提取
chat-lab/src/lib/meta-extractor.ts       # AGENT_META 跨 chunk 状态机（TS 版）

# backend/projects 整个目录可暂时搁置，后续如需再加入
```

### `route.ts` 核心结构（示意）

```typescript
import { NextRequest } from "next/server";

// ── Session 管理（文件/Redis/Edge Config） ──
const sessionMap = new Map<string, string>();

function getSessionId(familyId: string, childId: string): string {
  const key = `${familyId}:${childId}`;
  if (!sessionMap.has(key)) {
    sessionMap.set(key, crypto.randomUUID());
  }
  return sessionMap.get(key)!;
}

// ── AGENT_META 状态机（TS 版） ──
class MetaExtractor {
  private state: "NORMAL" | "IN_META" = "NORMAL";
  private metaBuffer = "";
  private pending = "";

  feed(text: string): { visible: string; meta?: Record<string, unknown> } {
    // 同 Python 版逻辑：跨 chunk 匹配 <AGENT_META>...</AGENT_META>
    return { visible: text }; // 简化示意
  }
}

// ── 组装 Coze payload ──
function buildCozePayload(body: any) {
  const familyId = body.family_id || "family_demo";
  const childId = body.child_id || "child_demo";
  const sessionId = getSessionId(familyId, childId);
  const prefs = body.client_context?.communication_prefs ?? [];
  const qStatus = body.client_context?.questionnaire_status ?? "not_started";

  const systemText = `你是家庭教育助手。当前用户：family_id=${familyId}, child_id=${childId}
沟通偏好：${prefs.join(",")}
问卷状态：${qStatus}
请根据以上信息调整回复风格。`;

  return {
    content: {
      query: {
        prompt: [
          { type: "text", content: { text: systemText } },
          { type: "text", content: { text: body.message?.text ?? "" } },
        ],
      },
    },
    type: "query",
    session_id: sessionId,
    project_id: "7640760744073658402",
  };
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const payload = buildCozePayload(body);

  const upstream = await fetch("https://gnp8dz4r4n.coze.site/stream_run", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${process.env.COZE_TOKEN}`,
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(payload),
  });

  const extractor = new MetaExtractor();

  const stream = new ReadableStream({
    async start(controller) {
      const reader = upstream.body!.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        // 按行解析 SSE data:
        for (const line of chunk.split("\n")) {
          if (!line.startsWith("data:")) continue;
          const data = line.slice(5).trim();
          if (data === "[DONE]") {
            controller.enqueue(new TextTextEncoder().encode("data: [DONE]\n\n"));
            continue;
          }
          try {
            const parsed = JSON.parse(data);
            if (parsed.type === "answer") {
              const answer = parsed.content?.answer ?? "";
              const { visible, meta } = extractor.feed(answer);
              if (visible) {
                const out = JSON.stringify({ type: "answer", content: { answer: visible } });
                controller.enqueue(new TextEncoder().encode(`data: ${out}\n\n`));
              }
              if (meta) {
                controller.enqueue(new TextEncoder().encode(
                  `event: agent_meta\ndata: ${JSON.stringify(meta)}\n\n`
                ));
              }
            }
          } catch {
            // skip invalid json
          }
        }
      }
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
```

### 优缺点

| 优点 | 缺点 |
|------|------|
| **完全省去 Python backend**，架构最简单 | Coze Token 需在服务端环境变量管理（Vercel/服务器） |
| 减少一层网络跳转，延迟更低 | Next.js API Route 运行在 Edge/Node，长时间 SSE 连接可能有超时限制 |
| 不需要部署维护 Python 服务 | AGENT_META 状态机用 TS 实现，需要仔细测试跨 chunk 截断 |
| 前后端技术栈统一（全 TS） | 如果需要把 Coze Token 隐藏得更好，还是需要中间层 |

---

## 方案对比总览

| 维度 | 方案 A：精简 Python Backend | 方案 B：Next.js 直接代理 |
|------|---------------------------|------------------------|
| **后端服务** | 保留轻量 FastAPI (~150 行) | 完全移除 Python backend |
| **前端改动** | 极小，几乎不改 | 重写 `route.ts` 为 SSE 流式 |
| **Coze Token 暴露** | 不暴露，backend 持有 | 在服务端环境变量，不暴露给浏览器 |
| **Session 管理** | Python dict / Redis | Next.js Map / Edge Config / 文件 |
| **AGENT_META 提取** | Python 状态机 | TypeScript 状态机 |
| **部署复杂度** | 需部署 Python 服务 + Next.js | 只需部署 Next.js |
| **链路延迟** | 多一层转发 | 更直接 |
| **可扩展性** | backend 可随时加逻辑（限流、日志、缓存） | 加逻辑需改 Next.js API Route |

---

## 建议

- **如果追求最快速度验证、先让流式跑通** → **方案 B**，把 `backend/projects` 完全搁置，专注在 `chat-lab/src/app/api/v1/chat/route.ts` 里用 TS 实现 SSE 代理 + AGENT_META 提取。
- **如果后续还需要 backend 做更多事情（记忆、画像、多种模型路由、敏感数据过滤）** → **方案 A**，保留一个轻量 Python 代理层作为扩展点。

无论选哪个，**核心新增逻辑只有一个：AGENT_META 跨 chunk 状态机提取器**。这是两个方案共通的重难点。
