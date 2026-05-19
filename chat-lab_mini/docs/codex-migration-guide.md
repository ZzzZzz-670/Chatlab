# 对话实验室 — Codex 前端迁移对接指南

> 本文档面向 Codex 前端开发者，完整描述后端 API 接口契约、数据结构、SSE 事件协议、诊断卡渲染规则，以及前后端交互的完整流程。

---

## 一、项目概览

**项目名称**：对话实验室（Dialogue Lab）  
**定位**：面向家长的 AI 伴学助手，核心能力是"深度诊断卡"——帮家长看见自己没意识到的盲点。  
**后端技术栈**：FastAPI + LangChain Agent + LangGraph + PostgresSaver（降级为 MemorySaver）  
**前端对接方式**：OpenAI Chat Completions 兼容 API（`/v1/chat/completions`），SSE 流式输出

---

## 二、API 接口契约

### 2.1 主接口：`POST /v1/chat/completions`

这是前端唯一需要调用的接口。兼容 OpenAI Chat Completions API 格式，额外增加 `session_id` 字段。

**请求格式：**

```json
{
  "session_id": "唯一会话ID（必填）",
  "stream": true,
  "messages": [
    { "role": "user", "content": "家长说的话" }
  ]
}
```

**字段说明：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `session_id` | string | **是** | 唯一会话标识，用于多轮对话状态持久化。同一 session_id 共享 checkpointer 历史 |
| `stream` | boolean | 否 | 默认 true，流式输出 |
| `messages` | array | 是 | OpenAI 标准格式，当前只发最后一条 user 消息（历史由后端 checkpointer 管理） |

**错误码：**

| 状态码 | code | 说明 |
|--------|------|------|
| 400 | 400001 | session_id 缺失 |
| 500 | - | 后端内部错误 |

---

### 2.2 健康检查：`GET /health`

```json
{
  "status": "ok",
  "message": "Service is running",
  "memory_backend": "postgres" | "memory" | "not_initialized" | "error"
}
```

`memory_backend` 含义：
- `postgres`：持久化存储，重启不丢数据
- `memory`：内存兜底，重启丢数据（日志会 WARNING）
- `not_initialized`：尚未初始化

---

### 2.3 语音接口（可选）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/tts` | POST | 文本转语音，参数 `{"text": "..."}` ，返回 `{"audio_url": "...", "audio_size": 123}` |
| `/api/asr` | POST | 语音转文本，参数 `{"url": "..."}` 或 `{"base64_data": "..."}` ，返回 `{"text": "...", "data": {...}}` |

---

## 三、SSE 流式协议（核心）

前端通过 `fetch` + `ReadableStream` 读取 SSE 流。后端输出三种事件类型：

### 3.1 `event: message`（默认，可省略 event 行）

正常 AI 回复内容，格式与 OpenAI 完全一致：

```
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1778...,"model":"default","choices":[{"index":0,"delta":{"content":"我"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1778...,"model":"default","choices":[{"index":0,"delta":{"content":"特别"},"finish_reason":null}]}
```

**关键处理：**
- 每个 chunk 的 `delta.content` 可能只有一个字，需累积拼接
- `finish_reason: "stop"` 表示本轮回复结束
- 后端已过滤内部指令/知识库痕迹/DIAGNOSIS_READY 标记，前端无需再做重度过滤
- **tool_calls 和 tool result 的 chunk 已被后端隐藏**，前端不会收到

### 3.2 `event: diagnosis`（诊断卡结构化数据）

当 AI 输出包含 `###DIAGNOSIS_READY###` 标记时，后端在流结束时发送：

```
event: diagnosis
data: {"blindSpot":"...","coreMechanism":"...","behaviorProtection":"...","possibleMeanings":[...],"evidenceBasis":"...","riskWarning":"...","suggestedReplies":{...},"suggestions":"..."}
```

**字段结构：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `blindSpot` | string | 家长盲点 |
| `coreMechanism` | string | 核心机制 |
| `behaviorProtection` | string | 行为保护 |
| `possibleMeanings` | array \| string | 可能含义（结构化时为数组，兜底为纯文本） |
| `evidenceBasis` | string | 判断依据 |
| `riskWarning` | string | 风险提示 |
| `suggestedReplies` | object \| string | 建议回复（结构化时为对象，兜底为纯文本） |
| `suggestions` | string | 改善建议 |

**`possibleMeanings` 结构化格式（数组）：**

```json
[
  {
    "label": "学校+家庭双重安全感缺失",
    "percentage": 85,
    "description": "在学校被排挤已经很难受，回家求助还被骂..."
  },
  {
    "label": "青春期自我价值感受挫",
    "percentage": 10,
    "description": "融不进集体+被家长骂..."
  },
  {
    "label": "求助无门",
    "percentage": 5,
    "description": "之前可能也跟老师提过..."
  }
]
```

**`suggestedReplies` 结构化格式（对象）：**

```json
{
  "conservative": {
    "reply": "（隔着门说）之前是我不对，不该没听你说完就骂你...",
    "reason": "先道歉退一步，完全不提学习和上学的事..."
  },
  "progressive": {
    "reply": "（等他愿意开门后说）你愿意跟我说说，是哪些同学排挤你吗？...",
    "reason": "等孩子情绪稳定后，主动引导他说出具体细节..."
  },
  "boundary": {
    "reply": "（如果他还是不愿意说）没关系，你不想说就不说...",
    "reason": "直接告诉他你已经在行动解决问题..."
  }
}
```

### 3.3 `event: session`（session_id 确认）

每次请求流结束时发送，确认后端使用的 session_id：

```
event: session
data: {"session_id": "xxx"}
```

前端应更新本地 `sessionId` 状态。

### 3.4 流结束标记

```
data: [DONE]
```

---

## 四、SSE 事件时序图

```
客户端请求 POST /v1/chat/completions
    │
    ├── event: message  ──→  delta.content 逐字流式输出（AI 回复）
    ├── event: message  ──→  ...（多轮追问场景）
    ├── event: message  ──→  finish_reason: "stop"
    ├── event: diagnosis ──→  结构化诊断卡数据（仅当 AI 输出诊断卡时）
    ├── event: session  ──→  {"session_id": "xxx"}
    └── data: [DONE]
```

**注意**：`event: diagnosis` 一定在 `data: [DONE]` 之前发送。

---

## 五、前端 SSE 解析参考代码

```javascript
async function callAPI(userText) {
  var payload = {
    session_id: state.sessionId,
    stream: true,
    messages: [{ role: 'user', content: userText }]
  };

  var currentEvent = 'message';
  var diagnosisData = null;
  var fullContent = '';

  var resp = await fetch(API_BASE + '/v1/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  var reader = resp.body.getReader();
  var decoder = new TextDecoder('utf-8');
  var buffer = '';

  function processLines(raw) {
    var lines = raw.split(/\r?\n/);
    for (var line of lines) {
      if (!line.trim()) continue;
      
      // 解析 event 类型
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim();
        continue;
      }
      
      if (!line.startsWith('data:')) continue;
      var data = line.slice(5).trim();
      if (data === '[DONE]') continue;

      // 处理 diagnosis 事件
      if (currentEvent === 'diagnosis') {
        try { diagnosisData = JSON.parse(data); } catch(e) {}
        currentEvent = 'message';
        continue;
      }

      // 处理 session 事件
      if (currentEvent === 'session') {
        try {
          var sess = JSON.parse(data);
          if (sess.session_id) state.sessionId = sess.session_id;
        } catch(e) {}
        currentEvent = 'message';
        continue;
      }

      // 处理 message 事件（正常内容）
      try {
        var parsed = JSON.parse(data);
        var delta = parsed.choices?.[0]?.delta;
        if (delta?.content) {
          fullContent += delta.content;
          // 渲染到 UI...
        }
      } catch(e) {}
    }
  }

  while (true) {
    var { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    var lines = buffer.split(/\r?\n/);
    buffer = lines.pop() || '';
    if (lines.length) processLines(lines.join('\n'));
  }
  if (buffer.trim()) processLines(buffer);

  // 流结束后，如果有诊断数据则弹出诊断卡
  if (diagnosisData) {
    showDiagnosisCard(diagnosisData);
  }
}
```

---

## 六、诊断卡渲染规则

### 6.1 触发条件

1. **优先**：后端发送 `event: diagnosis` → `diagnosisData` 不为 null → 使用结构化数据渲染
2. **兜底**：后端未发送 diagnosis event，但 `fullContent` 中包含关键词 `家长盲点|核心机制|行为保护|深度诊断|诊断卡` → 用纯文本解析渲染

### 6.2 渲染顺序与样式

诊断卡共 8 个板块，按以下顺序渲染：

| 序号 | 字段 | 标签名 | 背景色 | 标签色 |
|------|------|--------|--------|--------|
| 1 | blindSpot | 家长盲点 | 渐变蓝紫 `rgba(47,107,255,0.08)→rgba(109,91,208,0.08)` | 渐变 `#2F6BFF→#6D5BD0` 白字 |
| 2 | coreMechanism | 核心机制 | 白 `rgba(255,255,255,0.9)` | 浅蓝底 `#EAF2FF` 蓝字 `#2F6BFF` |
| 3 | behaviorProtection | 行为保护 | 橙底 `#FFF7ED` | 浅橙底 `#FFEDD5` 橙字 `#F97316` |
| 4 | possibleMeanings | 可能含义 | 白 `rgba(255,255,255,0.9)` | 浅紫底 `#E0E7FF` 紫字 `#4338CA` |
| 5 | evidenceBasis | 判断依据 | 白 `rgba(255,255,255,0.9)` | 浅绿底 `#ECFDF5` 绿字 `#16A34A` |
| 6 | riskWarning | 风险提示 | 浅紫 `#F1F0FF` | 浅紫底 `#DDD6FE` 紫字 `#6D5BD0` |
| 7 | suggestedReplies | 建议回复 | 浅灰 `#F8FAFC` | 浅灰底 `#E2E8F0` 灰字 `#475569` |
| 8 | suggestions | 改善建议 | 渐变绿蓝 `rgba(22,163,74,0.06)→rgba(47,107,255,0.06)` | 渐变 `#16A34A→#2F6BFF` 白字 |

### 6.3 可能含义（possibleMeanings）特殊渲染

当 `possibleMeanings` 为数组时，每条渲染为：
- 右侧显示百分比数字（大字加粗）
- 下方显示彩色进度条
- 进度条颜色梯度：
  - ≥60%：紫色渐变 `#4338CA→#6D5BD0`
  - ≥30%：蓝色渐变 `#2F6BFF→#60A5FA`
  - <30%：灰色渐变 `#94A3B8→#CBD5E1`
- 百分比数字颜色同进度条主色
- 底部声明文字："概率基于当前对话，仍存在不确定性"

### 6.4 风险提示（riskWarning）特殊渲染

- 整体浅紫背景 `#F1F0FF`
- ⚠️ 图标 + 深色文字
- 内容通常以"最大的风险是误读____"开头

### 6.5 建议回复（suggestedReplies）特殊渲染

当 `suggestedReplies` 为对象时，使用 **Tab 切换 UI**：

```
[稳妥版] [推进版] [边界版]    ← 三个 Tab 按钮
─────────────────────────
当前选中版本的内容
推荐理由：xxx
```

**Tab 样式：**
- 默认态：浅灰背景 `#F1F5F9`，灰色字 `#64748B`
- 选中态：紫色背景 `#4338CA`，白色字
- 点击切换显示对应版本内容

**字段映射：**
- `conservative` → 稳妥版
- `progressive` → 推进版
- `boundary` → 边界版

每个版本包含：
- `reply`：回复话术
- `reason`：推荐理由

**Tab 切换函数参考：**

```javascript
function switchReplyTab(btn, tabId, version) {
  // 更新按钮样式
  var buttons = btn.parentElement.querySelectorAll('button');
  buttons.forEach(function(b) {
    b.style.background = '#F1F5F9';
    b.style.color = '#64748B';
  });
  btn.style.background = '#4338CA';
  btn.style.color = '#fff';

  // 切换面板
  var labels = ['稳妥版', '推进版', '边界版'];
  for (var i = 0; i < labels.length; i++) {
    var panel = document.getElementById(tabId + '_' + labels[i]);
    if (panel) panel.style.display = labels[i] === version ? 'block' : 'none';
  }
}
```

### 6.6 兜底文本解析

当 `diagnosisData` 为纯文本（非结构化对象）时，需从文本中提取各板块：

```javascript
function extractSection(text, label) {
  // 优先匹配 **标签**：格式
  var boldPattern = new RegExp('\\*\\*' + label + '\\*\\*[^：:]*[：:]\\s*([\\s\\S]*?)(?=\\*\\*[^*]+\\*\\*[^：:]*[：:]|$)', 'i');
  var m = text.match(boldPattern);
  if (m && m[1].trim()) return m[1].trim();

  // 兜底：标签：格式
  var nextLabels = ['家长盲点','核心机制','行为保护','可能含义','判断依据','风险提示','建议回复','改善建议']
    .filter(l => l !== label)
    .join('|');
  var plainPattern = new RegExp(label + '\\s*[：:]\\s*([\\s\\S]*?)(?=' + nextLabels + '|$)', 'i');
  m = text.match(plainPattern);
  if (m && m[1].trim()) return m[1].trim();

  return '';
}
```

**提取标签列表**：`['家长盲点','核心机制','行为保护','可能含义','判断依据','风险提示','建议回复','改善建议']`

---

## 七、多轮对话机制

### 7.1 session_id 是唯一标识

- 前端生成唯一 `session_id`（如 UUID），每次请求必传
- 后端用 `session_id` 作为 LangGraph checkpointer 的 `thread_id`
- **不需要**传 `conversation_id`（已废弃）
- 前端只发当前这条 user 消息，历史由后端 checkpointer 管理

### 7.2 对话流程

```
第1轮：家长描述问题 → AI 追问1个问题
第2轮：家长补充信息 → AI 继续追问或开始分析
第3轮：家长再补充  → AI 判断洞察成熟 → 输出诊断卡
```

**判断逻辑在 AI 侧**（系统提示词控制），前端无需判断何时出卡。

### 7.3 诊断卡出现后

- 诊断卡作为弹窗/底部卡片展示
- 用户关闭弹窗后可继续对话
- AI 不会重复输出诊断卡（除非有重大新信息）
- `state.diagnosisShown` 标志位防止重复弹出

---

## 八、后端过滤机制（前端无需处理的内容）

后端已在 SSE 流中过滤以下内容，前端不会收到：

1. **内部指令痕迹**：`分析：`、`推理：`、`后台：`、`步骤1：`、`分支：` 等
2. **知识库检索标记**：`--- 结果 1 ---`、`相关度：0.85`、`查询到3条结果`
3. **Markdown 表格**：`| xxx | yyy |` 格式
4. **内部术语**：`后台想判断`、`家长标签`、`不直接采信`、`前台必须` 等
5. **DIAGNOSIS_READY 标记**：`###DIAGNOSIS_READY###`
6. **tool_calls / tool result**：工具调用和返回结果
7. **章节标题**：中文数字标题、阿拉伯数字标题等
8. **判断性短句**：`家长高控制`、`自主权不足` 等

前端只需做轻量兜底过滤（6条核心正则）：

```javascript
chunkText = chunkText.replace(/###\s*DIAGNOSIS_READY\s*###/gi, '');
chunkText = chunkText.replace(/DIAGNOSIS_READY/gi, '');
chunkText = chunkText.replace(/---\s*结果\s*\d+.*?---/gi, '');
chunkText = chunkText.replace(/相关度[:：]\s*\d+\.\d+/gi, '');
chunkText = chunkText.replace(/查询到.*?条结果/gi, '');
chunkText = chunkText.replace(/后台想判断|家长标签|不直接采信|转成分支问题|前台必须/gi, '');
```

---

## 九、后端核心代码结构

### 9.1 文件目录

```
src/
├── main.py                 # FastAPI 主入口，所有 HTTP 路由 + 过滤/解析逻辑
├── agents/
│   └── agent.py            # LangChain Agent 构建（create_agent + 滑动窗口）
├── tools/
│   └── knowledge_tool.py   # @tool 知识库搜索工具
└── storage/
    └── memory/
        └── memory_saver.py # PostgresSaver / MemorySaver checkpointer
config/
└── agent_llm_config.json   # 模型配置 + 系统提示词
assets/
└── index.html              # 前端单页应用（当前版本）
```

### 9.2 main.py 关键函数

| 函数 | 作用 |
|------|------|
| `_filter_text(text)` | 12 类正则过滤，返回 (过滤后文本, 是否包含诊断标记) |
| `_StreamFilterState` | 流式过滤状态机，跟踪 tool 序列和诊断检测 |
| `_filter_sse_chunk(chunk, state)` | 对单个 SSE chunk 做过滤 |
| `_parse_diagnosis(text)` | 从 AI 完整回复提取 8 个结构化字段 |
| `_parse_possible_meanings(text)` | 解析可能含义（3 种格式兼容） |
| `_parse_suggested_replies(text)` | 解析建议回复（稳妥版/推进版/边界版） |
| `_extract_section(text, label)` | 从文本提取 **label**： 后的内容 |
| `_filtered_openai_stream()` | 流式响应包装器，逐 chunk 过滤 + 侧信道事件 |
| `_filtered_json_response()` | 非流式响应过滤 |
| `openai_chat_completions()` | `/v1/chat/completions` 路由 |

### 9.3 _DIAGNOSIS_FIELDS 字段映射

```python
_DIAGNOSIS_FIELDS = [
    ("blindSpot",            "家长盲点"),
    ("coreMechanism",        "核心机制"),
    ("behaviorProtection",   "行为保护"),
    ("possibleMeanings",     "可能含义"),
    ("evidenceBasis",        "判断依据"),
    ("riskWarning",          "风险提示"),
    ("suggestedReplies",     "建议回复"),
    ("suggestions",          "改善建议"),
]
```

---

## 十、Agent 配置

### 10.1 模型配置（config/agent_llm_config.json）

```json
{
  "config": {
    "model": "doubao-seed-2-0-pro-260215",
    "temperature": 0.7,
    "top_p": 0.9,
    "max_completion_tokens": 10000,
    "timeout": 600,
    "thinking": "disabled"
  }
}
```

### 10.2 Agent 构建（agent.py）

- 使用 `langchain.agents.create_agent` 构建
- 滑动窗口：保留最近 40 条消息（20 轮对话）
- Checkpointer：优先 PostgresSaver（持久化），降级 MemorySaver（内存）
- 工具：`search_knowledge_base`（知识库检索）

### 10.3 系统提示词核心规则

- 普通轮次：80-150 字，温暖陪伴语气，追问 1 个问题
- 诊断卡：8 个板块，家长盲点用克制冷静语气，其余用温暖语气
- 诊断卡触发：AI 自行判断"洞察成熟度"后输出，末尾标记 `###DIAGNOSIS_READY###`
- 禁止输出：后台分析、知识库痕迹、JSON、表格、内部术语

---

## 十一、典型前端交互流程

```
1. 用户输入 → callAPI()
2. fetch POST /v1/chat/completions (session_id + messages)
3. 逐 chunk 读取 SSE 流：
   a. event:message → 累积 delta.content → 实时渲染到聊天气泡
   b. event:diagnosis → 缓存 diagnosisData
   c. event:session → 更新 sessionId
4. 流结束 (data:[DONE])
5. 如果 diagnosisData 不为空 → 弹出诊断卡弹窗
6. 用户关闭弹窗 → 可继续对话
```

---

## 十二、注意事项 & 已知问题

### 12.1 CORS

后端已配置 `allow_origins=["*"]`，前端可跨域调用。

### 12.2 session_id 缓存

- 同一 `session_id` 共享对话历史（checkpointer）
- 如果模型在旧 session 中输出过旧格式（如"可解释的三个行为"），历史上下文可能引导模型继续用旧格式
- **解决方案**：新用户用新 session_id；如需重置，更换 session_id 即可

### 12.3 诊断卡字段名（当前版本）

| 正确名称（当前） | 禁止名称（旧版） |
|------------------|------------------|
| 判断依据 | ~~可解释的三个行为~~、~~可解释的四个行为~~ |
| 风险提示 | ~~预测验证~~、~~可验证的预测~~ |
| 建议回复 | ~~边界与轻验证~~、~~下一步验证~~ |

前端渲染标签必须使用正确名称。

### 12.4 风险提示格式

正确：`最大的风险是误读____。如果将____误读为____并采取____，极有可能触发____`

禁止：`如果这个判断成立，它能解释为什么____`

### 12.5 建议回复三版本

必须包含 `【稳妥版】【推进版】【边界版】`，每个附推荐理由，缺一不可。

---

## 十三、完整诊断卡 JSON 示例

```json
{
  "blindSpot": "咱们做家长的一听初二孩子说不想上学，第一反应就是他怕学习苦、偷懒、矫情……但孩子的真实状态是：他正在经历在学校被排挤后的社交孤立，其核心诉求是获得基本的安全感和归属感，以应对每天面对被孤立的尴尬。这更像是孩子在用回避保护自己仅剩的心理空间，而非矫情偷懒。",
  
  "coreMechanism": "初二青春期敏感阶段，孩子鼓起勇气求助 → 被家长骂矫情 → 觉得委屈不被理解 → 只能把自己关在房间隔绝压力 → 家长越催越骂越抵触 → 形成'被孤立→求助被骂→封闭自己→更不想上学'的恶性循环。本质是家庭本应是安全港却变成了第二个压力源，孩子的求助通道被彻底堵死。",
  
  "behaviorProtection": "他把自己关在房间里，其实是在搭建一个暂时安全的小空间，保护自己不用再面对被排挤的难堪，也不用再承受你不理解的指责。",
  
  "possibleMeanings": [
    {
      "label": "学校+家庭双重安全感缺失",
      "percentage": 85,
      "description": "在学校被排挤已经很难受，回家求助还被骂，觉得没有任何人能站在自己这边，只能用封闭自己的方式逃避"
    },
    {
      "label": "青春期自我价值感受挫",
      "percentage": 10,
      "description": "融不进集体+被家长骂，让他觉得自己'确实不够好、是个麻烦'，更怕面对任何人的眼光"
    },
    {
      "label": "求助无门",
      "percentage": 5,
      "description": "之前可能也跟老师提过被排挤但没被重视，现在跟家长说又被骂，觉得没人能帮自己，只能彻底放弃沟通"
    }
  ],
  
  "evidenceBasis": "1. 初二最近突然说不想上学，正值青春期敏感阶段\n2. 明确提到在学校没朋友、被排挤，想融入但融不进去\n3. 被家长骂矫情后更不愿意去学校\n4. 把自己关在房间里，不愿和家长沟通",
  
  "riskWarning": "最大的风险是误读孩子关房间的行为。如果将'关房间躲情绪'误读为'故意闹脾气抗议'并采取砸门、说教、逼他上学的应对，极有可能触发孩子彻底放弃沟通，甚至出现更极端的逃避行为。",
  
  "suggestedReplies": {
    "conservative": {
      "reply": "（隔着门说）'之前是我不对，不该没听你说完就骂你矫情，你在学校受了那么大委屈肯定特别难受吧？我不催你上学，也不骂你，饭给你放门口了，什么时候想说话了随时找我。'",
      "reason": "先道歉退一步，完全不提学习和上学的事，只传递'我懂你的委屈、我不会逼你'的信号，先让孩子放下防备，不会激起他的抵触。"
    },
    "progressive": {
      "reply": "（等他愿意开门后说）'你愿意跟我说说，是哪些同学排挤你吗？是因为什么事呀？你不用怕，不管怎么样我都站在你这边，咱们一起想办法解决。'",
      "reason": "等孩子情绪稳定后，主动引导他说出具体细节，明确传递'你不是一个人扛，我是你的靠山'的态度，帮他把憋了很久的委屈倒出来。"
    },
    "boundary": {
      "reply": "（如果他还是不愿意说）'没关系，你不想说就不说，我已经找老师问过情况了，老师会帮你调整座位，下周我帮你约以前小学玩得好的同学来家里吃饭，你不想去学校就先在家歇两天，怎么舒服怎么来。'",
      "reason": "直接告诉他你已经在行动解决问题，不用他自己费力求助，给足他安全感，让他知道就算不说，你也能懂他的难处，帮他兜底。"
    }
  },
  
  "suggestions": "1. 最近一周先别提上学的事，也别催他出房间，每天按时把他爱吃的饭放门口，让他慢慢放下对你的防备，等他愿意主动跟你说话了，再聊学校的事。\n2. 私下找班主任沟通一下情况，请老师帮忙先调整个座位，安排他和性格温和、不怎么参与小团体的同学坐同桌，分组活动的时候多帮他搭个桥，先帮他在学校找到一个能说话的人，比逼他融入大集体有用得多。"
}
```
