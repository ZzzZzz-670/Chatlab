# Chatlab 仓库现状总览

更新时间：2026-05-19

本文档基于当前仓库代码、脚本、文档和本机验证结果整理。它回答两个问题：

- 这个仓库现在各个部分分别做什么。
- 当前版本在本机环境下是否能跑通。

## 1. 总体定位

这是一个面向家长的亲子沟通/孩子理解系统，当前仓库由三块主要工程组成：

- `chat-lab/`：Next.js 前端应用，同时承担一层 Web API 代理和本地集中记忆写入。
- `backend/projects/`：诊断型 Agent 后端，偏首次理解、正式诊断、学情分析、问题排查。
- `backend/talk_agent/`：日常对话 Agent 后端，偏长期陪伴、成长信号记录、纠偏、沟通预演。

整体设计上，前端负责承接用户输入、做轻量路由判断和集中记忆管理；真实的大模型 Agent 服务由后端提供 OpenAI Chat Completions 兼容接口；长期画像、记忆、知识库检索分别由后端工具和数据库/知识库能力支撑。

## 2. 根目录

### `README.md`

根目录 README 说明了推荐运行方式：WSL Ubuntu + Conda Python 3.12。它把系统分成前端、诊断 Agent、日常 Agent 三部分，并给出默认端口：

- 前端：`5000`
- 诊断 Agent：`8001`
- 日常 Agent：`8002`

注意：在当前 PowerShell 里直接读取 README 时，中文显示为乱码。这更像是 Windows 终端/文件编码读取方式不一致造成的显示问题，但建议后续统一确认所有 Markdown 和源码文件均按 UTF-8 保存。

### `setup_wsl_env.sh`

这是后端环境的一键安装脚本，面向 WSL Ubuntu。它主要做：

- 安装 Linux 编译和图形/GObject 相关系统依赖。
- 创建或复用 Conda 环境。
- 安装两个 Python 后端的依赖。
- 对主要 Agent 文件做基础语法检查。

这个脚本也解释了为什么后端更适合在 WSL/Ubuntu 中跑：后端依赖包含 `PyGObject`、`dbus-python`、`pycairo` 这类 Windows 上较难直接构建的包。

### `.gitignore`

当前忽略了：

- `.env`、`.env.*`
- `.venv/`
- `node_modules/`
- `.next/`
- `.data/`
- `__pycache__/`
- `*.pyc`
- `tsconfig.tsbuildinfo`

## 3. 前端工程 `chat-lab/`

### 技术栈

前端位于 `chat-lab/`，核心技术为：

- Next.js 16 App Router
- React 19
- TypeScript
- Tailwind CSS 4
- pnpm

`next.config.ts` 设置了 `output: "standalone"`，说明它被设计为可以用 Next 独立服务方式部署，而不是纯静态站点。

### 页面结构

主要页面在 `chat-lab/src/app/`：

- `/`：主聊天页，渲染 `DialogueLab2Prototype`，是当前最完整的产品原型入口。
- `/profile`、`/profile/detail`：孩子小档案和详情视图。
- `/records`、`/records/detail`：观察记录和记录详情。
- `/child-card`、`/child-card/form`、`/child-card/complete`、`/child-card/summary`：孩子学习小档案问卷相关流程。
- `/community`、`/qa`、`/character`、`/english`、`/schedule`、`/exam`、`/settings`：部分是占位页，部分复用原型组件切换到对应视图。

当前很多产品页面集中写在 `src/components/prototype/DialogueLab2Prototype.tsx` 中。它承担了移动端壳、聊天页、档案页、记录页、孩子问卷、设置页、底部弹窗等大量 UI 和交互逻辑。

### 组件

`chat-lab/src/components/` 中的主要组件：

- `ChatArea.tsx`：较早的聊天消息展示组件，包含 AI/用户消息、复制、TTS 播放按钮、加载态。
- `InputBar.tsx`：输入栏组件。
- `Sidebar.tsx`：侧边导航。
- `NavBar.tsx`：顶部导航。
- `DiagnosisModal.tsx`：诊断弹窗。
- `SubPageHeader.tsx`、`SubPagePlaceholder.tsx`：子页面占位结构。
- `prototype/DialogueLab2Prototype.tsx`：当前主原型容器，实际承载最多业务 UI。

### 前端 API 路由

`chat-lab/src/app/api/` 下有几类服务端路由：

- `/api/chat`：把请求代理到后端 `/v1/chat/completions`，保留流式响应。
- `/api/asr`：把语音识别请求代理到后端 `/api/asr`。
- `/api/tts`：把语音合成请求代理到后端 `/api/tts`。
- `/api/v1/chat`：当前统一聊天入口，包含前端路由判断、记忆上下文读取、候选记忆写入、后端 Agent 调用和兜底回复。
- `/v1/chat`：复用 `/api/v1/chat` 的 POST 处理，提供另一个兼容入口。

### 前端路由和记忆逻辑

核心文件：

- `src/lib/agent-router.ts`
- `src/lib/memory-store.ts`
- `src/lib/coze-server.ts`
- `src/lib/api-client.ts`

`agent-router.ts` 做轻量文本规则判断：

- 根据关键词判断走 `diagnosis_agent` 还是 `daily_agent`。
- 判断场景，例如 `diagnosis`、`study_assessment`、`communication_rehearsal`、`growth_record`、`correction`、`casual_chat`。
- 抽取一些前端可判断的记忆候选，例如成长变化、长期目标、纠偏信息、待观察点。

`memory-store.ts` 是本地集中记忆存储：

- 文件位置：`chat-lab/.data/central-memory-store.json`
- `.data/` 已被 git 忽略。
- 存储两类数据：`memories` 和 `events`。
- 记忆层级包括 `low_verified_profile`、`high_verified_profile`、`growth_records`、`pending_observations`、`long_term_goals`、`correction_logs`、`rehearsal_records`、`parent_profile`、`family_interaction_patterns`。
- 有简单的相似内容合并和 pending 升级 confirmed 的逻辑。

`coze-server.ts` 负责读取服务端环境变量：

- `COZE_API_BASE_URL`
- `COZE_API_TOKEN`
- `COZE_COLD_START_RETRIES`
- `COZE_CHAT_TIMEOUT_MS`

它还实现了后端冷启动重试。

### 统一聊天链路

当前 `/api/v1/chat` 的主要流程是：

1. 接收 `family_id`、`child_id`、`conversation_id`、`message.text`。
2. 从 `.data/central-memory-store.json` 读取当前家庭/孩子的记忆上下文。
3. 用 `routeAgent()` 判断当前应该是诊断 Agent 还是日常 Agent。
4. 把用户消息写入本地 conversation events。
5. 构造 OpenAI Chat Completions 风格请求，向 `COZE_API_BASE_URL/v1/chat/completions` 转发。
6. 如果后端不可用或超时，返回前端内置的 `fallbackReply()`。
7. 汇总前端规则、后端规则、Agent 输出中的记忆候选并写入本地 memory store。
8. 返回标准化的 `reply`、`actions`、`memory_note`、`memory_write_results`。

一个重要现状：`routeAgent()` 会返回 `diagnosis_agent` 或 `daily_agent`，但真正调用哪个后端服务仍取决于 `COZE_API_BASE_URL` 指向哪里。也就是说，它目前不会自动在 `8001` 和 `8002` 之间切换 URL，而是把路由结果放进 payload/context 里。

## 4. 诊断 Agent 后端 `backend/projects/`

### 定位

`backend/projects/` 是诊断型 Agent 服务，偏正式分析和结构化诊断。它适合处理：

- 首次进入系统时建立初始理解。
- 家长希望做正式分析、诊断、复盘。
- 学情、作业、拖延、考试等问题排查。
- 形成诊断卡、候选画像、handoff 摘要。

### 技术栈

核心依赖在 `pyproject.toml`：

- FastAPI + Uvicorn
- LangChain / LangGraph
- langchain-openai
- coze-coding-utils
- coze-workload-identity
- cozeloop
- SQLAlchemy / psycopg / psycopg2
- boto3
- pandas / Pillow / opencv-python
- PyGObject / dbus-python / pycairo

`requires-python = ">=3.12"`，README 推荐 Python 3.12。

### 服务入口

主入口是 `backend/projects/src/main.py`，提供：

- `/run`：普通工作流/Agent 执行。
- `/stream_run`：SSE 流式执行。
- `/cancel/{run_id}`：取消运行。
- `/node_run/{node_id}`：单节点运行。
- `/v1/chat/completions`：OpenAI Chat Completions 兼容接口。
- `/health`：健康检查。
- `/graph_parameter`：输入输出 schema。
- `/api/questionnaire`、`/api/questionnaire/{family_id}`：孩子问卷提交和读取。
- `/api/profile/{family_id}`、`/api/profile/{family_id}/updates`：孩子画像和更新日志。
- `/api/agent-state/{family_id}`：当前 Agent 路由状态。

这个后端还在 `/v1/chat/completions` 周围做了较多包装：

- 过滤内部推理、工具调用、知识库痕迹。
- 检测 `DIAGNOSIS_READY`。
- 从回复中抽取结构化诊断字段。
- 在流式模式下通过 side-channel 发出 `event: diagnosis`。
- 诊断完成后写入画像候选、handoff、family state。

### Agent

核心文件是 `backend/projects/src/agents/agent.py`。

它会：

- 从 `COZE_WORKSPACE_PATH/config/agent_llm_config.json` 读取模型配置和 system prompt。
- 从环境变量读取 `COZE_WORKLOAD_IDENTITY_API_KEY`、`COZE_INTEGRATION_MODEL_BASE_URL`。
- 用 `ChatOpenAI` 构造模型。
- 绑定知识库检索工具。
- 使用 `create_agent()` 创建 LangChain Agent。
- 当前不启用 Agent 侧 checkpointer，长期记忆交给 Web 后端统一读写。

### 知识库工具

`backend/projects/src/tools/` 中主要有：

- `knowledge_tool.py`：通过 Coze dev SDK 的 KnowledgeClient 搜索默认知识库，并对检索片段做清洗。
- `knowledge_lib_tools.py`：按 A/B/C/D/E 分库检索，直接查询 PostgreSQL/pgvector，并调用 embedding 客户端生成向量。

A/B/C/D/E 的语义大致是：

- A：原因分支库。
- B：家长叙述到事实问题的转换库。
- C：前台表达与诊断卡库。
- D：典型案例库。
- E：黑名单与反证边界库。

### 画像和数据库

`backend/projects/src/storage/profile/profile_service.py` 负责：

- `family_state`
- `profile_entries`
- `long_term_goals`
- `handoff_summaries`
- `child_questionnaires`
- `profile_update_log`

数据库 URL 优先来自 `PGDATABASE_URL`，否则尝试通过 `coze_workload_identity` 获取。

### 资产和文档

`backend/projects/assets/` 中有：

- A/B/C/D/E 知识库 txt。
- 后端对接说明。
- 日常对话 Agent 总说明。
- 多张截图和图片资产。

`backend/projects/docs/` 中有：

- 诊断 Agent prompt。
- 诊断 Agent 接口规范。
- 后端 API 完整文档。
- Codex 迁移指南和 handbook。

## 5. 日常对话 Agent 后端 `backend/talk_agent/`

### 定位

`backend/talk_agent/` 是日常陪伴型 Agent。它偏长期使用场景：

- 家长日常聊天。
- 记录孩子近期变化。
- 抽取成长信号。
- 维护孩子画像、家长画像、家庭互动模式。
- 识别纠偏触发。
- 做沟通预演。

### 服务入口

主入口是 `backend/talk_agent/src/main.py`。它和诊断后端的基础服务框架相似，提供：

- `/run`
- `/stream_run`
- `/cancel/{run_id}`
- `/node_run/{node_id}`
- `/v1/chat/completions`
- `/health`
- `/graph_parameter`

相比诊断后端，日常 Agent 的 main.py 没有诊断 side-channel 和诊断后处理那一整套逻辑，更多是标准 Agent 服务入口。

### Agent 图

核心文件是 `backend/talk_agent/src/agents/agent.py`。

它不是简单 `create_agent()`，而是手写 LangGraph：

- `agent` 节点：调用绑定工具后的 LLM。
- `tools` 节点：执行工具调用。
- `format_output` 节点：尝试从模型可能输出的 JSON 中抽取自然语言内容，避免前端直接看到结构化包装。

图结构是：

```text
START -> agent -> tools -> agent -> format_output -> END
```

如果模型没有工具调用，则直接从 `agent` 进入 `format_output`。

### 工具

`backend/talk_agent/src/tools/daily_agent_tools.py` 中包含大量工具，分为几类：

- 查询类：孩子画像、诊断 handoff、成长记录、待观察点、长期目标、家长画像、家庭互动模式、问卷、纠偏记录。
- 写入类：成长记录、画像条目、待观察点、纠偏、家长画像、家庭互动模式、长期目标、沟通预演记录、解决待观察点。
- 元信息类：提交回复类型、UI badge、记忆提示、按钮动作。
- 知识库类：04A/04B/04C/04D 核心理解库、成长信号/记忆沉淀/长期关注库、纠偏/沟通预演规则、文风示例、后端 contract。
- 聚合类：`search_core_understanding_pack()`，按场景自动选择多个核心知识库检索。

### 存储

`backend/talk_agent/src/storage/database/` 中有：

- `supabase_client.py`：Supabase/PostgREST 客户端。
- `memory_service.py`：成长记录、待观察点、长期目标、纠偏、诊断 handoff、问卷、沟通预演、对话事件。
- `profile_service.py`：孩子画像、家长画像、家庭互动模式等。
- `db.py`：Postgres SQLAlchemy 连接逻辑。

这里同时存在 Supabase 风格服务和 SQLAlchemy/Postgres 风格连接，说明数据层可能仍处于迁移或并存阶段。

### 资产

`backend/talk_agent/assets/` 是日常 Agent 的完整知识/规则文档，包含：

- `00_日常对话Agent总说明.md`
- `01_日常对话Agent系统提示词.md`
- `02_日常对话Agent输出格式.md`
- `03_日常Agent输入上下文规范.md`
- `04A` 到 `04D` 的理解与规则库。
- `05_成长信号抽取规则.md`
- `06_记忆沉淀规则.md`
- `07_家长长期关注库规则.md`
- `08_纠偏触发规则.md`
- `09_沟通预演规则.md`
- `10_禁止事项与文风规范.md`
- `11_示例对话库.md`
- `12_后端对接说明.md`

## 6. 前后端协作方式

当前设计可以理解为三层：

```text
浏览器 UI
  -> Next.js 页面和 API Route
  -> chat-lab 本地统一入口 /api/v1/chat
  -> 根据 COZE_API_BASE_URL 转发到某一个 Python Agent 服务
  -> Python Agent 调模型、查知识库、读写数据库
```

前端本地统一入口做了两件重要的事：

- 在真实 Agent 调用前后维护 `.data/central-memory-store.json`。
- 即使后端暂时不可用，也能给用户一个兜底回复，避免 UI 完全中断。

但也要注意：这套本地 `.data` 记忆和 Python 后端数据库记忆并不是同一个存储。前端统一入口强调“集中记忆由 Web 后端统一读写”，而两个 Python Agent 里仍然保留了数据库/画像服务代码。这里后续需要确认最终以哪一层为准，避免记忆双写或数据口径不一致。

## 7. 当前版本验证结果

### 前端

已在当前机器上验证通过。

执行过的关键步骤：

```powershell
cd C:\Users\boshe\code\my_project\Chatlab\chat-lab
corepack pnpm install --frozen-lockfile
.\node_modules\.bin\tsc.CMD --noEmit
.\node_modules\.bin\next.CMD build
.\node_modules\.bin\next.CMD start -p 5050
```

结果：

- 依赖安装成功。
- TypeScript 检查通过。
- Next.js 生产构建通过。
- 短暂启动 `next start -p 5050` 后访问 `http://127.0.0.1:5050/` 返回 200。

因此，前端在依赖安装完成后可以构建并启动。

### 前端构建警告

构建成功，但 Next.js 给出 workspace root 推断警告：

```text
Next.js inferred your workspace root, but it may not be correct.
We detected multiple lockfiles and selected the directory of
C:\Users\boshe\code\my_project\Chatlab\package-lock.json
as the root directory.
Detected additional lockfiles:
* C:\Users\boshe\code\my_project\Chatlab\chat-lab\pnpm-workspace.yaml
```

当前 `git status --short` 显示根目录有未跟踪文件：

```text
?? package-lock.json
?? package.json
```

这两个文件内容很空：

- 根目录 `package.json` 是 `{}`。
- 根目录 `package-lock.json` 只声明了空 packages。

它们会干扰 Next.js 对 workspace root 的判断。当前不影响构建通过，但建议确认是不是误生成文件。如果不是有意保留，后续应清理；如果要保留，则应在 `next.config.ts` 中显式配置 `turbopack.root`。

### 后端

当前 Windows PowerShell 环境下，两个后端都没有完整跑通。

验证过程和结果：

```powershell
cd C:\Users\boshe\code\my_project\Chatlab\backend\projects
uv sync --offline --cache-dir C:\Users\boshe\code\my_project\Chatlab\.uv-cache
```

离线同步失败，原因是当前环境没有 Python >=3.12，`uv --offline` 不能下载解释器。

继续联网同步：

```powershell
uv sync --cache-dir C:\Users\boshe\code\my_project\Chatlab\.uv-cache
```

`backend/projects` 和 `backend/talk_agent` 都失败在同一个依赖：

```text
Failed to build pygobject==3.48.2
ERROR: Unknown compiler(s): [['icl'], ['cl'], ['cc'], ['gcc'], ['clang'], ['clang-cl'], ['pgcc']]
Could not find Visual Studio vswhere.exe
```

也就是说，本机 Windows 环境缺少构建 `PyGObject` 所需的编译器和相关系统库。仓库 README 推荐 WSL Ubuntu + Conda Python 3.12 是合理的。

不过，使用 `uv` 已创建出的 Python 解释器做了语法级检查：

```powershell
cd backend\projects
.\.venv\Scripts\python.exe -m py_compile src\main.py src\agents\agent.py src\tools\knowledge_tool.py src\tools\knowledge_lib_tools.py

cd backend\talk_agent
.\.venv\Scripts\python.exe -m py_compile src\main.py src\agents\agent.py src\tools\daily_agent_tools.py
```

结果：

- 两个后端的主要入口、Agent 文件、工具文件都通过 `py_compile`。
- 这只能说明语法解析通过，不能说明依赖、数据库、模型服务、知识库服务都能正常运行。

### 后端完整运行还需要的条件

要真正跑通 Python 后端，需要：

- 在 WSL Ubuntu 或等价 Linux 环境中安装系统依赖。
- 使用 Python 3.12/Conda 环境安装 `pyproject.toml` 依赖。
- 配置 `COZE_WORKSPACE_PATH` 指向对应后端目录。
- 配置模型服务变量：`COZE_WORKLOAD_IDENTITY_API_KEY`、`COZE_INTEGRATION_MODEL_BASE_URL`。
- 如果启用画像、记忆、知识库直连，需要配置 `PGDATABASE_URL` 或 Coze workload identity 中的数据库环境变量。
- 如果使用前端代理，需要在 `chat-lab/.env.local` 配置 `COZE_API_BASE_URL` 指向当前启动的后端。

## 8. 当前能否跑通的结论

结论分层看：

- 前端：可以跑通。依赖安装后，TypeScript、Next build、`next start` 首页访问都已通过。
- 诊断后端：当前 Windows PowerShell 环境未跑通。主要阻塞是 `PyGObject` 等系统依赖构建失败；源码主要文件语法检查通过。
- 日常后端：当前 Windows PowerShell 环境未跑通。阻塞原因与诊断后端相同；源码主要文件语法检查通过。
- 全链路：当前本机没有完成端到端跑通。原因是 Python 后端未能在 Windows 环境完整安装启动，并且模型、数据库、知识库相关环境变量也需要真实配置。

换句话说：当前版本“前端可运行，后端需要 WSL/Linux + 正确环境变量后再验证，全链路暂未在当前机器上跑通”。

## 9. 推荐启动方式

### 前端

```powershell
cd C:\Users\boshe\code\my_project\Chatlab\chat-lab
corepack pnpm install --frozen-lockfile
Copy-Item .env.local.example .env.local
.\node_modules\.bin\next.CMD dev -p 5000
```

`.env.local` 示例：

```env
COZE_API_BASE_URL=http://localhost:8001
COZE_API_TOKEN=
COZE_COLD_START_RETRIES=0
COZE_CHAT_TIMEOUT_MS=8000
```

如果要连日常 Agent，把 `COZE_API_BASE_URL` 改成：

```env
COZE_API_BASE_URL=http://localhost:8002
```

### 诊断 Agent

建议在 WSL Ubuntu 中：

```bash
conda activate family-comm
cd /path/to/Chatlab/backend/projects
export COZE_WORKSPACE_PATH="$(pwd)"
export COZE_WORKLOAD_IDENTITY_API_KEY="your_key"
export COZE_INTEGRATION_MODEL_BASE_URL="your_base_url"
python src/main.py -m http -p 8001
```

健康检查：

```bash
curl http://localhost:8001/health
```

### 日常 Agent

建议在 WSL Ubuntu 中：

```bash
conda activate family-comm
cd /path/to/Chatlab/backend/talk_agent
export COZE_WORKSPACE_PATH="$(pwd)"
export COZE_WORKLOAD_IDENTITY_API_KEY="your_key"
export COZE_INTEGRATION_MODEL_BASE_URL="your_base_url"
python src/main.py -m http -p 8002
```

健康检查：

```bash
curl http://localhost:8002/health
```

## 10. 当前风险和后续建议

- 清理或确认根目录 `package.json`、`package-lock.json`。它们目前会触发 Next workspace root 警告。
- 统一确认中文文件编码。当前 PowerShell 输出中大量中文显示为乱码，至少会影响维护体验。
- 明确最终记忆数据源。现在前端 `.data` 本地记忆和 Python 后端数据库记忆并存，需要确定生产方案。
- 后端依赖建议固定到推荐运行平台。当前 pyproject 允许 Python `>=3.12`，`uv` 在 Windows 下载了 3.14.4，但 README 推荐 3.12；建议明确 `.python-version` 或文档里固定 3.12。
- 如果目标是 Windows 原生运行，需要重新评估 `PyGObject`、`dbus-python`、`pycairo` 是否必要，或提供 Windows 可安装方案。
- 后端启动验证应在 WSL 中继续完成，至少包括 `/health`、`/v1/chat/completions` 非流式、流式、前端 `/api/v1/chat` 端到端四类检查。

