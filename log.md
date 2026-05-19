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
