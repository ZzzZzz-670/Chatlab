# 项目运行指南

## 架构说明

- **后端**：只用 `diagnosis`（8000）+ `daily_talk`（8001）
- **前端**：`chat-lab`（5000，Next.js dev server）
- **ASR**：可直接用 `diagnosis`（8000）自带的 `/api/asr`，也可额外启动独立 ASR 服务（8002）
- **projects / talk_agent 已弃用**，无需启动

---

## 1. 环境准备

### 前端依赖

```bash
cd chat-lab
npm install
# 或 pnpm install
```

### 后端依赖

```bash
# diagnosis
cd backend/diagnosis
pip install -r requirements.txt  # 或 uv pip install

# daily_talk
cd backend/daily_talk
pip install -r requirements.txt  # 或 uv pip install
```

### 讯飞 ASR 额外依赖（如使用讯飞模式）

```bash
pip install websocket-client
# 或 uv pip install websocket-client
```

---

## 2. 环境变量配置

在 `backend/.env` 写入（**只需写一次，所有后端服务共享**）：

```bash
# 讯飞 ASR 配置（在讯飞开放平台控制台获取）
XUNFEI_APPID=your_appid
XUNFEI_API_KEY=your_apikey
XUNFEI_API_SECRET=your_apisecret

# ASR 模式切换: xunfei（默认） | local
ASR_PROVIDER=xunfei
```

在 `chat-lab/.env.local` 写入（前端代理配置）：

```bash
DIAGNOSIS_BACKEND_URL=http://localhost:8000
DAILY_TALK_BACKEND_URL=http://localhost:8001
ASR_STANDALONE_URL=http://localhost:8002
```

> 如果你还没有 `chat-lab/.env.local`，直接复制 `chat-lab/.env.local.example` 修改即可。

---

## 3. 启动服务

需要 **3 个终端窗口**（或后台运行）：

### 终端 1：diagnosis 后端（8000）

```bash
cd backend/diagnosis
python main.py
```

### 终端 2：daily_talk 后端（8001）

```bash
cd backend/daily_talk
python main.py
```

### 终端 3：前端（5000）

```bash
cd chat-lab
npm run dev
```

前端打开 http://localhost:5000 即可使用。

---

## 4. 可选：独立 ASR 服务（8002）

如果你想把 ASR 从 diagnosis 里拆出来单独跑：

```bash
cd backend
python asr_standalone.py
```

此时前端 `ASR_STANDALONE_URL` 配置会生效；若 8002 未启动，前端 ASR 请求会自动 fallback 到 diagnosis:8000。

---

## 5. 接口测试（无需启动前端）

### 语音转文字

```bash
curl -X POST http://localhost:8000/api/asr \
  -H "Content-Type: application/json" \
  -d '{"base64_data":"<base64_audio>","mime_type":"audio/webm"}'
```

### 聊天流式接口（diagnosis）

```bash
curl -X POST http://localhost:8000/stream_run \
  -H "Content-Type: application/json" \
  -d '{"family_id":"demo","child_id":"demo","message":{"text":"你好"}}'
```

### 聊天流式接口（daily_talk）

```bash
curl -X POST http://localhost:8001/stream_run \
  -H "Content-Type: application/json" \
  -d '{"family_id":"demo","child_id":"demo","message":{"text":"你好"}}'
```

---

## 6. 故障排查

| 现象 | 原因 | 解决 |
|------|------|------|
| `ASR not available` | `websocket-client` 未装或 `asr_client` 导入失败 | 安装依赖；或切到 `ASR_PROVIDER=local` |
| `讯飞 ASR 缺少必要配置` | 环境变量未设置 | 检查 `backend/.env` 是否包含讯飞密钥 |
| `无法建立讯飞 WebSocket 连接` | 网络或鉴权失败 | 检查密钥与系统时间（误差需 <300s） |
| 前端 5000 端口被占 | Next.js dev server 冲突 | `DEPLOY_RUN_PORT=3000 npm run dev` |
| 后端启动时预加载很慢 | faster-whisper 首次加载模型 | 正常现象，或切到讯飞模式跳过加载 |

---

## 7. 文件清单（ASR 相关改动）

| 文件 | 说明 |
|------|------|
| `backend/asr_client.py` | **新增**，统一 ASR 客户端，含讯飞实现 + 本地分发 |
| `backend/diagnosis/main.py` | 修改 `/api/asr` 路由，接入 `asr_client` |
| `backend/daily_talk/main.py` | 同上 |
| `backend/asr_standalone.py` | 接入 `asr_client`，支持 provider 感知启动 |
| `backend/diagnosis/local_asr.py` | **未修改**，原本地 ASR 保留 |
| `backend/daily_talk/local_asr.py` | **未修改**，原本地 ASR 保留 |
| `chat-lab/.env.local.example` | 补充 `DIAGNOSIS_BACKEND_URL` 等配置示例 |
