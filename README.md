# 家庭沟通系统 README

这是一个面向家长的家庭沟通/孩子理解系统，包含：

- `chat-lab/`：Next.js 前端 + 网页后端代理。
- `backend/projects/`：诊断型 Agent，负责首次理解、正式诊断、学情诊断、问题排查。
- `backend/talk_agent/`：日常对话 Agent，负责日常交流、持续记录、沟通预演、长期陪伴。

推荐最终运行环境：

```text
WSL Ubuntu + Conda Python 3.12
```

## 0. 一键配置后端环境

先进入 WSL Ubuntu，不要在 Windows PowerShell 里执行下面命令。

```bash
cd /mnt/d/LESSON/工作/创业/家庭沟通系统
chmod +x setup_wsl_env.sh
./setup_wsl_env.sh
```

这个脚本会自动完成：

- 安装 Ubuntu 编译依赖；
- 创建或复用 Conda 环境 `family-comm`；
- 安装 Python 3.12；
- 安装 `backend/projects` 依赖；
- 安装 `backend/talk_agent` 依赖；
- 对两个 Agent 文件做基础语法检查。

如果你还没有安装 Conda，先执行：

```bash
cd ~
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh
source ~/.bashrc
```

如果创建 Conda 环境时提示 Terms of Service，执行：

```bash
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
```

然后重新运行一键脚本：

```bash
cd /mnt/d/LESSON/工作/创业/家庭沟通系统
./setup_wsl_env.sh
```

## 1. 手动配置后端环境

如果你不想用一键脚本，可以手动执行。

```bash
conda create -n family-comm python=3.12 -y
conda activate family-comm
```

安装 Ubuntu 编译依赖：

```bash
sudo apt update
sudo apt install -y \
  build-essential \
  pkg-config \
  libcairo2-dev \
  libgirepository1.0-dev \
  gobject-introspection \
  libdbus-1-dev \
  libglib2.0-dev \
  gir1.2-gtk-3.0 \
  libpq-dev \
  curl \
  git
```

安装诊断 Agent 依赖：

```bash
cd /mnt/d/LESSON/工作/创业/家庭沟通系统/backend/projects
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

安装日常 Agent 依赖：

```bash
cd /mnt/d/LESSON/工作/创业/家庭沟通系统/backend/talk_agent
python -m pip install -e .
```

## 2. 后端环境变量

两个 Agent 通常需要下面这些变量。可以写到 WSL 的 `~/.bashrc`、当前终端，或你自己的 `.env` 管理方式里。

```bash
export COZE_WORKLOAD_IDENTITY_API_KEY="你的模型 API Key"
export COZE_INTEGRATION_MODEL_BASE_URL="你的模型 Base URL"

# 可选：如果你使用外部 Postgres/知识库/画像库
export PGDATABASE_URL="postgresql://user:password@host:5432/dbname"
```

运行诊断 Agent 时建议：

```bash
export COZE_WORKSPACE_PATH="/mnt/d/LESSON/工作/创业/家庭沟通系统/backend/projects"
```

运行日常 Agent 时建议：

```bash
export COZE_WORKSPACE_PATH="/mnt/d/LESSON/工作/创业/家庭沟通系统/backend/talk_agent"
```

## 3. 启动诊断型 Agent

适用场景：

- 首次进入；
- 用户想做正式分析；
- 用户咨询学情诊断；
- 用户排查孩子问题；
- 当前没有高验证画像。

启动：

```bash
conda activate family-comm
cd /mnt/d/LESSON/工作/创业/家庭沟通系统/backend/projects
export COZE_WORKSPACE_PATH="$(pwd)"
python src/main.py -m http -p 8001
```

健康检查：

```bash
curl http://localhost:8001/health
```

## 4. 启动日常对话 Agent

适用场景：

- 日常闲聊；
- 轻松交流；
- 持续记录孩子变化；
- 沟通预演；
- 后续陪伴。

启动：

```bash
conda activate family-comm
cd /mnt/d/LESSON/工作/创业/家庭沟通系统/backend/talk_agent
export COZE_WORKSPACE_PATH="$(pwd)"
python src/main.py -m http -p 8002
```

健康检查：

```bash
curl http://localhost:8002/health
```

## 5. 配置前端连接哪个 Agent

前端配置文件在：

```text
chat-lab/.env.local
```

如果没有这个文件，先复制：

```bash
cd /mnt/d/LESSON/工作/创业/家庭沟通系统/chat-lab
cp .env.local.example .env.local
```

连接诊断 Agent：

```env
COZE_API_BASE_URL=http://localhost:8001
COZE_API_TOKEN=
COZE_COLD_START_RETRIES=0
COZE_CHAT_TIMEOUT_MS=8000
```

连接日常 Agent：

```env
COZE_API_BASE_URL=http://localhost:8002
COZE_API_TOKEN=
COZE_COLD_START_RETRIES=0
COZE_CHAT_TIMEOUT_MS=8000
```

注意：前端统一聊天入口会做 Agent Router 和集中记忆写入，但真实 Coze Agent 调用仍由 `COZE_API_BASE_URL` 指向的后端服务完成。

## 6. 启动前端

推荐在 Windows 或 WSL 里都可以启动前端。已有 `node_modules` 时可直接：

```bash
cd /mnt/d/LESSON/工作/创业/家庭沟通系统/chat-lab
./node_modules/.bin/next dev -p 5000
```

如果还没安装前端依赖：

```bash
cd /mnt/d/LESSON/工作/创业/家庭沟通系统/chat-lab
corepack pnpm install
corepack pnpm dev
```

Windows PowerShell 也可以：

```powershell
cd D:\LESSON\工作\创业\家庭沟通系统\chat-lab
.\node_modules\.bin\next.CMD dev -p 5000
```

访问：

```text
http://localhost:5000
```

## 7. 正常使用顺序

1. 在 WSL 里激活 Conda 环境：

```bash
conda activate family-comm
```

2. 启动一个 Agent 后端：

```bash
# 诊断 Agent
cd /mnt/d/LESSON/工作/创业/家庭沟通系统/backend/projects
export COZE_WORKSPACE_PATH="$(pwd)"
python src/main.py -m http -p 8001
```

或：

```bash
# 日常 Agent
cd /mnt/d/LESSON/工作/创业/家庭沟通系统/backend/talk_agent
export COZE_WORKSPACE_PATH="$(pwd)"
python src/main.py -m http -p 8002
```

3. 修改 `chat-lab/.env.local`，让 `COZE_API_BASE_URL` 指向当前启动的后端。

4. 启动前端：

```bash
cd /mnt/d/LESSON/工作/创业/家庭沟通系统/chat-lab
./node_modules/.bin/next dev -p 5000
```

5. 打开：

```text
http://localhost:5000
```

6. 在主聊天页输入家长描述。

前端会经过：

```text
用户输入
前端 Agent Router 判别
前端记忆候选筛选
POST /api/v1/chat
网页后端读取集中记忆库
调用后端 Agent
标准化输出
写入分级记忆库
返回 reply + memory_note
原 UI 渲染消息
```

## 8. 统一聊天接口

前端新增统一入口：

```text
POST /api/v1/chat
POST /v1/chat
```

快速测试：

```bash
curl -X POST http://localhost:5000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "family_id": "family_demo",
    "child_id": "child_demo",
    "conversation_id": "conv_demo",
    "message": {
      "text": "昨天他自己开始写了一会作业，比以前主动了一点",
      "attachments": [],
      "source": "chat_input"
    },
    "client_context": {
      "page": "chat",
      "entry_mode": "daily_chat"
    }
  }'
```

Agent 原始 OpenAI 兼容接口：

```bash
curl -X POST http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test_session",
    "stream": false,
    "messages": [
      {
        "role": "user",
        "content": "孩子最近作业总是拖，我想知道原因。"
      }
    ]
  }'
```

## 9. 集中记忆存储

网页后端的本地集中记忆文件：

```text
chat-lab/.data/central-memory-store.json
```

`.data/` 已被 `.gitignore` 忽略。

记忆分级：

- `low_verified_profile`：低验证画像。
- `high_verified_profile`：高验证画像。
- `growth_records`：成长变化记录。
- `pending_observations`：待验证观察点。
- `long_term_goals`：家长期待和长期目标。
- `correction_logs`：纠偏记录。
- `rehearsal_records`：沟通预演记录。
- `parent_profile`：家长侧偏好和关注。
- `family_interaction_patterns`：家庭互动模式。

Agent 侧不再保留独立长期记忆；长期记忆由网页后端统一读取、注入和写入。

## 10. 常见问题

### `ModuleNotFoundError: No module named 'cozeloop'`

说明你还没有在当前 Conda 环境安装项目依赖。

```bash
conda activate family-comm
cd /mnt/d/LESSON/工作/创业/家庭沟通系统/backend/projects
python -m pip install -e .
```

### Conda 提示 Terms of Service

执行：

```bash
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
```

然后重新创建环境或重新运行：

```bash
./setup_wsl_env.sh
```

### 安装 `dbus-python` / `PyGObject` 报错

先安装系统依赖：

```bash
sudo apt update
sudo apt install -y \
  build-essential \
  pkg-config \
  libcairo2-dev \
  libgirepository1.0-dev \
  gobject-introspection \
  libdbus-1-dev \
  libglib2.0-dev \
  gir1.2-gtk-3.0
```

然后重新安装：

```bash
python -m pip install -e .
```

### 前端打开了，但没有真实 Agent 回复

检查：

```bash
curl http://localhost:8001/health
curl http://localhost:8002/health
```

再检查 `chat-lab/.env.local` 里的：

```env
COZE_API_BASE_URL=http://localhost:8001
```

或：

```env
COZE_API_BASE_URL=http://localhost:8002
```

### 端口冲突

默认端口：

- 前端：`5000`
- 诊断 Agent：`8001`
- 日常 Agent：`8002`

换端口后，要同步修改 `COZE_API_BASE_URL`。

## 11. 验证命令

后端：

```bash
conda activate family-comm

cd /mnt/d/LESSON/工作/创业/家庭沟通系统/backend/projects
python -m py_compile src/agents/agent.py

cd /mnt/d/LESSON/工作/创业/家庭沟通系统/backend/talk_agent
python -m py_compile src/agents/agent.py
```

前端：

```bash
cd /mnt/d/LESSON/工作/创业/家庭沟通系统/chat-lab
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/next build
```
