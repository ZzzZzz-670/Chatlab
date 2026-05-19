# Mini Diagnosis 完整实现文档

## 项目概述

基于 **方案 A（保留独立 Python Backend）** 实现的最小化诊断对话系统：

- **backend/diagnosis**：轻量 FastAPI 代理层，直接调用 Coze `/stream_run`，负责 SSE 流式代理、AGENT_META 跨 chunk 提取、Session 管理、用户个性化注入
- **chat-lab_mini**：精简版前端，SSE 流式消费，打字机效果显示 AI 回复

**核心链路**：
```
前端 chat-lab_mini
  → POST /api/v1/chat (SSE)
  → Next.js API Route (透传)
  → backend/diagnosis /stream_run (FastAPI)
  → Coze 平台 /stream_run
  ← SSE 流式返回（含 <AGENT_META>）
```

---

## 目录结构

```
Chatlab/
├── backend/
│   ├── projects/              # 旧版（暂时搁置）
│   ├── talk_agent/            # 旧版（暂时搁置）
│   └── diagnosis/             # ★ 新版精简 Backend
│       ├── main.py            # FastAPI 入口 + AGENT_META 状态机
│       ├── requirements.txt   # 依赖
│       └── .env.example       # 环境变量模板
│
├── chat-lab/                  # 原版前端（不变）
├── chat-lab_mini/             # ★ 新版精简前端
│   ├── src/
│   │   ├── app/
│   │   │   ├── api/v1/chat/route.ts    # ★ 改为 SSE 透传代理
│   │   │   └── ...
│   │   ├── components/
│   │   │   └── prototype/
│   │   │       └── DialogueLab2Prototype.tsx  # ★ sendMock 改为 SSE 消费
│   │   └── lib/
│   │       └── api-client.ts
│   ├── .env.local             # ★ 新增 DIAGNOSIS_BACKEND_URL
│   └── ...
│
└── call_api.py                # Coze 直连参考脚本
```

---

## 后端详解：backend/diagnosis

### 1. 核心文件

#### `main.py`

**FastAPI 路由**：

| 路由 | 方法 | 说明 |
|------|------|------|
| `POST /stream_run` | SSE | 核心接口：接收聊天请求 → 调 Coze → 返回 SSE 流 |
| `GET /health` | JSON | 健康检查，返回当前 session 数量 |
| `GET /session/{family_id}/{child_id}` | JSON | 查看指定用户的 session_id |
| `DELETE /session/{family_id}/{child_id}` | JSON | 清除指定用户的 session（重置上下文） |

**核心流程**：

```
1. 解析请求 → family_id, child_id, message, client_context
2. get_session_id(family_id, child_id) → 查内存或生成新 session_id
3. build_coze_payload() → 组装 system prompt（含用户偏好）+ user prompt
4. requests.post(COZE_STREAM_RUN_URL, stream=True)
5. event_generator() → 逐行解析 SSE
   ├── data: {"type":"answer","content":{"answer":"..."}} → MetaExtractor.feed()
   │   ├── 可见文本 → yield data: {answer}
   │   └── <AGENT_META> 完整提取 → yield event: agent_meta
   └── data: [DONE] → 结束
```

#### `MetaExtractor`（AGENT_META 跨 chunk 状态机）

**问题背景**：SSE 流中每个 chunk 是一段文本切片，`<AGENT_META>` 标签可能被截断：

```
Chunk N:   "...孩子不想写作业不一定是"
Chunk N+1: "态度问题。<AGENT"
Chunk N+2: "_META>\n{\"output_type\":...}\n</AGENT_META>"
```

**状态机设计**：

```
状态 NORMAL:
  - 在文本中查找 "<AGENT_META>" 的完整或部分前缀
  - 完整匹配 → 之前文本输出给用户，之后文本进入 meta_buffer，状态→IN_META
  - 部分前缀（如 "<AGENT"）→ 缓存到 pending，等待下一个 chunk

状态 IN_META:
  - 所有文本追加到 meta_buffer（不输出给用户）
  - 查找 "</AGENT_META>" 的完整或部分前缀
  - 完整匹配 → 解析 meta_buffer 为 JSON，输出 event: agent_meta，状态→NORMAL
  - 部分前缀 → 缓存到 pending，等待下一个 chunk
```

**关键实现**：`_find_start()` 和 `_find_end()` 方法处理跨 chunk 前缀匹配：

```python
def _find_start(self, text: str) -> tuple[str, str, bool]:
    full = self.pending + text          # 拼接上一个 chunk 的 pending
    idx = full.find(self.START_TAG)     # 查找完整标签
    if idx >= 0:
        return full[:idx], full[idx+len(tag):], True  # (可见文本, 剩余文本, 已开始)

    # 检查是否有部分前缀在末尾
    for i in range(1, min(len(self.START_TAG), len(full)) + 1):
        if full.endswith(self.START_TAG[:i]):
            self.pending = full[-i:]     # 缓存前缀，等下一个 chunk
            return full[:-i], "", False
```

### 2. 环境变量

复制 `.env.example` 为 `.env` 并填入真实值：

```bash
cd backend/diagnosis
cp .env.example .env
```

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `COZE_STREAM_RUN_URL` | 是 | `https://gnp8dz4r4n.coze.site/stream_run` | Coze stream_run 接口地址 |
| `COZE_TOKEN` | 是 | - | Coze Bearer Token |
| `COZE_PROJECT_ID` | 是 | `7640760744073658402` | Coze Project ID |
| `BACKEND_PORT` | 否 | `8000` | 本地服务端口 |

### 3. 安装与启动

```bash
cd backend/diagnosis

# 安装依赖
pip install -r requirements.txt

# 方式一：直接启动（带热重载）
python main.py

# 方式二：uvicorn 启动（生产推荐）
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

启动后访问：
- `http://localhost:8000/health` — 健康检查
- `http://localhost:8000/docs` — Swagger UI 自动文档

---

## 前端详解：chat-lab_mini

### 1. 改动文件清单

| 文件 | 改动内容 |
|------|----------|
| `src/app/api/v1/chat/route.ts` | 从非流式 Coze 代理 → SSE 透传代理到 backend/diagnosis |
| `src/components/prototype/DialogueLab2Prototype.tsx` | sendMock 从 `fetch + response.json()` → `fetch + ReadableStream` SSE 解析 |
| `.env.local` | 新增 `DIAGNOSIS_BACKEND_URL=http://localhost:8000` |

### 2. API Route 改动 (`route.ts`)

**旧逻辑**：
- 调用 `fetchCozeWithColdStartRetry("/v1/chat/completions")`
- `stream: false`，等待完整 JSON 响应
- 解析 `reply.content`, `frontend_cards`, `key_question`
- 返回 `Response.json({...})`

**新逻辑**：
- 转发到 `${DIAGNOSIS_BACKEND_URL}/stream_run`
- 请求头加上 `Accept: text/event-stream`
- 透传 SSE body：`return new Response(upstream.body, {headers: {...}})`

### 3. DialogueLab2Prototype.tsx 改动

**旧逻辑**（非流式）：
```typescript
const response = await fetch("/api/v1/chat", {...});
const data = await response.json();  // 等待完整响应
insertMessage({ type: "normal_reply", content: data.reply.content });
```

**新逻辑**（SSE 流式）：
```typescript
const response = await fetch("/api/v1/chat", {...});
const reader = response.body.getReader();
const decoder = new TextDecoder();

// 先插入空消息占位
setMessages(prev => [...prev, { id: aiMessageId, type: "normal_reply", content: "" }]);

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  
  buffer += decoder.decode(value, { stream: true });
  const lines = buffer.split("\n");
  buffer = lines.pop() ?? "";
  
  for (const line of lines) {
    // 解析 SSE 行：event: / data:
    if (line.startsWith("event:")) currentEvent = ...;
    if (line.startsWith("data:")) {
      const parsed = JSON.parse(dataStr);
      if (parsed.type === "answer") {
        accumulatedText += parsed.content.answer;
        // ★ 打字机效果：不断更新同一条消息
        setMessages(prev => updateMessage(aiMessageId, accumulatedText));
      }
    }
  }
}
```

**关键新增**：
- `communication_prefs: selectedPrefs` 和 `questionnaire_status: questionnaireStatus` 注入请求体
- 解析 `event: agent_meta` → 提取 `key_question_content` → 流结束后插入 key_question 消息
- 检查 `agentMeta.diagnosis_completed === true` → `setHasConfirmedProfile(true)`

### 4. 前端环境变量

```bash
# chat-lab_mini/.env.local
DIAGNOSIS_BACKEND_URL=http://localhost:8000
```

### 5. 安装与启动

```bash
cd chat-lab_mini

# 安装依赖（如未安装）
npm install

# 开发模式启动
npm run dev
```

默认端口 `5000`，访问 `http://localhost:5000`

---

## 完整运行流程

### 第一步：启动后端

```bash
cd backend/diagnosis
pip install -r requirements.txt

# 编辑 .env 填入 COZE_TOKEN
cp .env.example .env
# vim .env

python main.py
```

终端应显示：
```
INFO:     Diagnosis backend starting on port 8000
INFO:     Coze URL: https://gnp8dz4r4n.coze.site/stream_run
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 第二步：启动前端

```bash
cd chat-lab_mini
npm run dev
```

终端应显示：
```
> dialogue-lab@0.1.0 dev
> next dev -p 5000
```

### 第三步：验证

1. 打开浏览器 `http://localhost:5000`
2. 在输入框输入问题，例如"孩子不想写作业怎么办？"
3. 观察：
   - AI 回复应**逐字出现**（打字机效果），而非等全部返回后一次性显示
   - 流结束后，如果 Coze 返回了 `<AGENT_META>`，会额外出现一条 **key_question** 消息
   - 浏览器 Network 面板中，`/api/v1/chat` 请求的 Type 应为 `eventsource`

### 第四步：调试 Session

```bash
# 查看当前 session
curl http://localhost:8000/session/family_demo/child_demo

# 重置 session（清空上下文）
curl -X DELETE http://localhost:8000/session/family_demo/child_demo
```

---

## 接口文档

### `POST /stream_run` (backend/diagnosis)

**请求体** (`application/json`)：

```json
{
  "family_id": "family_demo",
  "child_id": "child_demo",
  "conversation_id": "conv_demo",
  "message": {
    "text": "孩子不想写作业怎么办？",
    "attachments": [],
    "source": "chat_input"
  },
  "client_context": {
    "page": "chat",
    "entry_mode": "daily_chat",
    "communication_prefs": ["多解释一点", "建议具体一点"],
    "questionnaire_status": "not_started"
  }
}
```

**SSE 响应**：

```
data: {"type": "answer", "content": {"answer": "您先别着急"}}
data: {"type": "answer", "content": {"answer": "，孩子不想写作业"}}
data: {"type": "answer", "content": {"answer": "不一定是态度问题..."}}
event: agent_meta
data: {"output_type": "key_question", "key_question_content": "他是所有科目的作业都不想写...", "diagnosis_completed": false}
data: [DONE]
```

**字段说明**：

| SSE 事件 | 说明 |
|----------|------|
| `data: {"type":"answer",...}` | AI 回复文本片段，前端累加显示 |
| `event: agent_meta` | 结构化元数据，含 `output_type`, `key_question_content`, `diagnosis_completed` 等 |
| `data: [DONE]` | 流结束标记 |

---

## 常见问题与调试

### 1. 前端看不到打字机效果

**排查**：
- Network 面板确认 `/api/v1/chat` 响应头 `Content-Type` 是否为 `text/event-stream`
- 确认 backend/diagnosis 是否正常启动（`curl http://localhost:8000/health`）
- 检查 `.env.local` 中 `DIAGNOSIS_BACKEND_URL` 是否正确

### 2. AGENT_META 没有正确提取

**排查**：
- 直接调用 backend：`curl -N -X POST http://localhost:8000/stream_run -H "Content-Type: application/json" -d '{...}'`
- 观察终端日志：`MetaExtractor` 会打印 `AGENT_META extracted: ...`
- 如果日志没有打印，可能是标签跨了超过 2 个 chunk 的极端情况，检查 `_find_start`/`_find_end` 的 pending 逻辑

### 3. Session 上下文没有保持

**排查**：
- 确认 family_id + child_id 组合一致（当前硬编码为 `family_demo` / `child_demo`）
- 检查 `SESSION_MAP` 中是否有对应的 session_id：
  ```bash
  curl http://localhost:8000/health
  curl http://localhost:8000/session/family_demo/child_demo
  ```
- 如果 Coze 返回了新的 session，说明 Coze 端没有识别到相同的 session_id，检查 payload 中的 `session_id` 是否正确传递

### 4. Coze 返回 401/403

**排查**：
- 确认 `.env` 中 `COZE_TOKEN` 已正确设置
- 确认 Token 没有过期
- 直接测试 Coze：`python call_api.py --terminal`

---

## 扩展方向

当前实现是最小化版本，后续可按需扩展：

| 扩展点 | 说明 |
|--------|------|
| **Session 持久化** | 内存 `dict` → Redis / SQLite / PostgreSQL，重启后 session 不丢失 |
| **用户信息持久化** | 将 family_id/child_id 对应的真实用户资料、沟通偏好存入数据库 |
| **记忆/画像** | 在 backend 中接入 `storage/profile/` 和 `storage/memory/`，恢复原有画像功能 |
| **多 Agent 路由** | 根据对话内容自动路由到不同 Coze Project（诊断 Agent / 日常 Agent） |
| **语音支持** | 保留旧版 TTS/ASR 路由，前端语音输入输出 |
| **日志与监控** | 添加请求日志、延迟统计、错误告警 |

---

## 附录：前后端完整代码位置

| 代码 | 路径 |
|------|------|
| Backend 入口 | `backend/diagnosis/main.py` |
| Backend 依赖 | `backend/diagnosis/requirements.txt` |
| Backend 环境模板 | `backend/diagnosis/.env.example` |
| 前端 API Route | `chat-lab_mini/src/app/api/v1/chat/route.ts` |
| 前端对话组件 | `chat-lab_mini/src/components/prototype/DialogueLab2Prototype.tsx` |
| 前端环境配置 | `chat-lab_mini/.env.local` |
