# TODO 实施日志

## 2026-05-19

### TODO 1：预设产品功能展示和真实使用分开
- 改动：
  - 将真实聊天初始消息拆成 `realInitialMessages`，只保留欢迎引导。
  - 将原有预设对话和卡片移入 `demoMessages`。
  - 新增 `/demo` 页面和 `ProductDemoPage`，设置页提供“查看预设演示”入口。
  - 演示页不使用真实聊天输入框，避免预设展示写入真实对话。
- 验证：
  - `rg` 确认 `/demo` 路由、`realInitialMessages`、`demoMessages` 和演示入口存在。
  - Node 检查确认 `realInitialMessages` 中不包含“昨天他没有被催”等演示对话文本。
  - TypeScript `transpileModule` 对 `DialogueLab2Prototype.tsx` 和 `src/app/demo/page.tsx` 做 TSX 语法诊断，通过。
  - `git diff --check` 通过。
- 备注：
  - 当前 Windows PATH 没有 `python` / `py`，因此未运行 `backend/projects/src/main.py` 的 `py_compile`；本项未改后端逻辑。

### TODO 2：实现后端返回的 `<key_question>` 关键追问渲染
- 改动：
  - 新增 `chat-lab/src/lib/agent-response.ts`，集中解析 Agent 输出。
  - 支持从普通文本或 `reply.content` 中提取 `<key_question>...</key_question>`。
  - Next API `/api/v1/chat` 返回新增 `key_question` 字段，并保证正文中剥离标签。
  - 前端新增 `key_question` 消息类型和 `KeyQuestionMessage` 渲染。
  - 增加 `.dl2-key-question` 样式，作为独立“关键追问”卡片展示。
- 验证：
  - Node + TypeScript transpile 后实际执行 `normalizeAgentOutput`：
    - 普通文本含 `<key_question>`：正文剥离成功，`key_question` 提取成功。
    - JSON `reply.content` 含 `<key_question>`：正文剥离成功，`key_question` 提取成功。
  - TypeScript `transpileModule` 对 `agent-response.ts`、`route.ts`、`DialogueLab2Prototype.tsx` 做语法诊断，通过。
  - `rg` 确认 API 返回字段和前端渲染路径存在。
  - `git diff --check` 通过。

### TODO 3：实现基础卡片渲染
- 改动：
  - 在 `agent-response.ts` 中新增 `FrontendCard` / `FrontendCardSection` 与 `normalizeFrontendCards`。
  - Next API 支持返回 `frontend_cards`。
  - 如果后端 `/v1/chat/completions` 返回 side-channel `diagnosis`，Next API 会转换成 `diagnosis_card`。
  - fallback 路径补充基础 `growth_signal` / `communication_rehearsal` 卡片，便于无真实 Agent 时也能验证渲染链路。
  - 前端新增动态 `DiagnosisCard`，并让 `GrowthSignalCard` / `RehearsalCard` 优先使用后端卡片数据，保留原静态演示兜底。
- 验证：
  - Node + TypeScript transpile 后实际执行 `normalizeAgentOutput` / `normalizeFrontendCards`，确认 `frontend_cards` 可以被归一化。
  - TypeScript `transpileModule` 对 `agent-response.ts`、`route.ts`、`DialogueLab2Prototype.tsx` 做语法诊断，通过。
  - `rg` 确认 API、helper、前端渲染路径存在。
  - `git diff --check` 通过。

### TODO 4：对前端隐藏 JSON / Meta / output_type 等内部字段
- 改动：
  - `agent-response.ts` 新增 `cleanVisibleText`，清理 JSON code block、`Meta:`、`output_type:`、`debug_id:`、`<meta>` 等内部内容。
  - `normalizeAgentOutput`、`normalizeKeyQuestion`、卡片 section 归一化均接入可见文本清理。
  - `normalizeFrontendCards` 会移除卡片上的 `output_type`、`metadata`、`raw_*`、`understanding_engine` 等内部字段。
  - `backend/projects/src/main.py` 的 `_filter_text` 同步增加 JSON / Meta / output_type 过滤规则。
- 验证：
  - Node + TypeScript transpile 后实际执行 `cleanVisibleText`，确认内部行和 `<meta>` 不会进入可见文本。
  - Node helper 测试确认 `normalizeAgentOutput` 仍能保留正文和 `key_question`，并清理内部字段。
  - TypeScript `transpileModule` 对相关前端文件做语法诊断，通过。
  - 使用内置 Python 执行 `python.exe -m py_compile backend/projects/src/main.py`，通过。
  - `git diff --check` 通过。

### TODO 5：加 loading 状态
- 改动：
  - 将聊天等待气泡改成“模型正在思考中哦”。
  - 增加三个跳动圆点的 loading 动画。
  - 发送中禁用发送按钮，避免重复提交。
  - 移除页面可见的调试状态条，仅保留控制台日志。
- 验证：
  - `rg` 确认 `sendDebug` / `.dl2-debug-line` / `正在发送` 已不在前端代码中，新的 loading 文案存在。
  - TypeScript `transpileModule` 对相关前端文件做语法诊断，通过。
  - 使用内置 Python 执行 `python.exe -m py_compile backend/projects/src/main.py`，通过。
  - `git diff --check` 通过。

### 最终验证
- `agent-response.ts` 集成测试通过：同时覆盖正文清理、`key_question` 提取、`frontend_cards` 保留、内部 `metadata` 移除。
- TypeScript `transpileModule` 最终检查通过：
  - `chat-lab/src/lib/agent-response.ts`
  - `chat-lab/src/app/api/v1/chat/route.ts`
  - `chat-lab/src/components/prototype/DialogueLab2Prototype.tsx`
  - `chat-lab/src/app/demo/page.tsx`
- 后端语法检查通过：
  - `python.exe -m py_compile backend/projects/src/main.py`
- `git diff --check` 通过。


## 2026-05-20

### TODO：新增讯飞 ASR 统一接口，保留本地 faster-whisper 能力
- 改动：
  - 新建 `backend/asr_client.py`，作为统一 ASR 客户端。
    - 支持 `ASR_PROVIDER` 一键切换：`"xunfei"`（默认）或 `"local"`。
    - 讯飞实现：基于官方 WebSocket 接口（`wss://iat.xf-yun.com/v1`），完整实现鉴权签名、分帧发送（1280 字节/40ms）、结果解析。
    - 本地实现：透传 `local_asr.LocalASR.recognize`，完全复用旧逻辑。
    - 提供 `recognize()`（async，供 FastAPI 用）和 `recognize_sync()`（同步，供 asr_standalone 用）。
  - 修改 `backend/diagnosis/main.py`、`backend/daily_talk/main.py`：
    - `/api/asr` 路由优先调用 `asr_client.recognize()`。
    - 讯飞失败且 `ASR_PROVIDER=xunfei` 时，自动 fallback 到本地 ASR（若可用）。
    - 若 `asr_client` 未安装/导入失败，完全回退到旧本地 ASR 逻辑，不破坏原有功能。
  - 修改 `backend/projects/src/main.py`：
    - `/api/asr` 路由同样优先 `asr_client`。
    - 保留原有三级 fallback 链：asr_client → local ASR → coze SDK `ASRClient`。
  - 修改 `backend/asr_standalone.py`：
    - 接入 `asr_client.recognize_sync()`。
    - 启动时根据 `ASR_PROVIDER` 决定是否预加载 faster-whisper 模型；讯飞模式下跳过本地加载，直接启动。
- 验证：
  - `python -m py_compile` 通过：
    - `backend/asr_client.py`
    - `backend/asr_standalone.py`
    - `backend/diagnosis/main.py`
    - `backend/daily_talk/main.py`
    - `backend/projects/src/main.py`
  - `rg` 确认 `ASR_PROVIDER`、`asr_client`、`XUNFEI_APPID` 等新增关键字在各文件位置正确。
  - `git diff --check` 通过。
- 备注：
  - 所有 `local_asr.py`（diagnosis / daily_talk / projects/src 三份）**完全未修改**，本地 ASR 能力完整保留。
  - 讯飞模式需额外安装 `websocket-client` 并配置 `XUNFEI_APPID`、`XUNFEI_API_KEY`、`XUNFEI_API_SECRET`。


## 2026-05-20

### TODO：确认前端与 projects/talk_agent 解耦，只依赖 daily_talk + diagnosis
- 调查：
  - 全局搜索 `chat-lab/src` 内所有后端请求：`/api/v1/chat` → 转发到 diagnosis/daily_talk；`/api/asr` → 转发到 ASR standalone 或 diagnosis。
  - 零引用 `projects`、`talk_agent`、`project` 关键字。
  - 前端自身端口 5000 是 Next.js dev server，与 `backend/projects` 服务无关。
  - `/api/chat`、`/api/tts` 两个路由虽存在，但**无任何前端组件调用**，不影响解耦结论。
- 结论：
  - **前端已完全解耦 projects 和 talk_agent**，当前只需启动 `diagnosis:8000` + `daily_talk:8001` + `chat-lab:5000` 即可完整运行。
  - ASR 可独立启动（8002），也可让 diagnosis:8000 兼任 ASR fallback。
- 改动：
  - 更新 `chat-lab/.env.local.example`，补充 `DIAGNOSIS_BACKEND_URL`、`DAILY_TALK_BACKEND_URL`、`ASR_STANDALONE_URL` 示例。
- 验证：
  - `rg` 确认前端代码中无 projects/talk_agent 引用。
  - `git diff --check` 通过。
