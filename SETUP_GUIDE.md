# ChatLab 项目运行指南

> 本指南涵盖 `chat-lab`（前端）、`diagnosis`（诊断后端）、`daily_talk`（日常对话后端）、`asr_standalone`（本地语音服务）四个模块的配置与启动。
>
> **语音方案**：已替换为本地 faster-whisper，不再依赖 Coze ASR 或浏览器语音识别。

---

## 一、项目结构

```
Chatlab/
├── chat-lab/              # Next.js 前端（端口 5000）
│   ├── .env.local         # 前端环境变量（需创建）
│   └── package.json
├── backend/
│   ├── diagnosis/         # FastAPI 诊断后端（端口 8000）
│   │   ├── .env
│   │   ├── main.py
│   │   ├── local_asr.py   # ASR 识别模块（与 asr_standalone 共用）
│   │   └── requirements.txt
│   ├── daily_talk/        # FastAPI 日常对话后端（端口 8001）
│   │   ├── .env
│   │   ├── main.py
│   │   ├── local_asr.py
│   │   └── requirements.txt
│   ├── asr_standalone.py  # ASR 独立服务（端口 8002）
│   ├── asr_deploy.sh      # ASR 一键部署脚本
│   └── projects/ffmpeg    # 静态 ffmpeg 二进制（音频格式转换）
```

---

## 二、环境要求

| 模块 | 技术栈 | 最低版本 |
|------|--------|----------|
| chat-lab | Node.js + Next.js | Node 18+ |
| diagnosis | Python + FastAPI | Python 3.10+ |
| daily_talk | Python + FastAPI | Python 3.10+ |
| asr_standalone | Python + faster-whisper | Python 3.10+ |

---

## 三、环境变量配置

### 3.1 前端 `chat-lab/.env.local`

创建文件 `chat-lab/.env.local`：

```bash
# ── 后端路由 ──
DIAGNOSIS_BACKEND_URL=http://localhost:8000
DAILY_TALK_BACKEND_URL=http://localhost:8001

# ── ASR 独立服务（前端 /api/asr 会优先走这个端口）─
ASR_STANDALONE_URL=http://localhost:8002

# ── 前端 API 代理（可选，如使用 nginx 反向代理则配置）─
NEXT_PUBLIC_API_PROXY_BASE_URL=

# ── Coze 相关（语音已走本地，聊天如仍用 Coze 则保留）─
COZE_API_BASE_URL=
COZE_API_TOKEN=
```

> `.env.local` 不会提交到 git，已存在于 `.gitignore` 中。

### 3.2 诊断后端 `backend/diagnosis/.env`

创建文件 `backend/diagnosis/.env`：

```bash
# Coze 配置（从你的 Coze 控制台获取）
COZE_STREAM_RUN_URL=https://gnp8dz4r4n.coze.site/stream_run
COZE_TOKEN=pat_xxxxxxxxxxxxxxxxxxxxxxxx
COZE_PROJECT_ID=7640760744073658402

# 服务端口
BACKEND_PORT=8000
```

### 3.3 日常对话后端 `backend/daily_talk/.env`

创建文件 `backend/daily_talk/.env`：

```bash
# Coze 配置（需替换为你的 daily_talk Agent 配置）
COZE_STREAM_RUN_URL=https://your-daily-talk.coze.site/stream_run
COZE_TOKEN=pat_xxxxxxxxxxxxxxxxxxxxxxxx
COZE_PROJECT_ID=REPLACE_WITH_DAILY_TALK_PROJECT_ID

# 服务端口（与 diagnosis 错开）
BACKEND_PORT=8001
```

> **注意**：`daily_talk` 的 `COZE_STREAM_RUN_URL` 和 `COZE_PROJECT_ID` 需要替换为你自己的 daily_talk Coze Agent 配置。

---

## 四、依赖安装

### 4.1 前端

```bash
cd chat-lab
npm install
# 或 yarn install / pnpm install
```

### 4.2 后端（三个后端依赖相同）

```bash
# diagnosis 后端
cd backend/diagnosis
pip install -r requirements.txt

# daily_talk 后端
cd backend/daily_talk
pip install -r requirements.txt
```

或使用 uv：

```bash
cd backend/diagnosis && uv pip install -r requirements.txt
cd backend/daily_talk && uv pip install -r requirements.txt
```

### 4.3 ffmpeg（音频格式转换）

项目已自带静态 ffmpeg，位于 `backend/projects/ffmpeg`，**通常无需额外安装**。

如需手动下载：

```bash
cd backend/projects
curl -sL https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz \
  | tar -xJ --strip-components=1 --wildcards "*/ffmpeg"
chmod +x ffmpeg
```

验证：
```bash
backend/projects/ffmpeg -version
```

---

## 五、ASR 模型预下载（首次部署必做）

faster-whisper 模型默认使用 `small`（约 500MB，中文效果较好），首次启动时会自动下载并缓存。

**建议提前下载**，避免启动时等待：

```bash
# 国内网络建议设镜像加速
export HF_ENDPOINT=https://hf-mirror.com

# 预下载 small 模型
python3 -c "
from faster_whisper import WhisperModel
print('>>> 下载模型...')
WhisperModel('small', device='cpu', compute_type='int8')
print('<<< 完成，已缓存')
"
```

缓存位置：`~/.cache/huggingface/hub/models--Systran--faster-whisper-small/`

> 缓存后断网也能用。如需更小模型：`export WHISPER_MODEL=base`（约 150MB）。

---

## 六、启动顺序

需要开 **4 个终端窗口**（ASR 服务建议单独启动，避免阻塞 diagnosis）。

### 终端 1：ASR 独立服务（:8002）【建议先启动】

```bash
cd backend
python asr_standalone.py
```

预期输出：
```
[ASR] >>> Start loading model=small device=cpu compute_type=int8 ...
[ASR] <<< Model loaded OK (0.9s). model_size=small
      model is in memory: YES
Service READY at http://localhost:8002/api/asr
```

**保持这个窗口运行**，模型已常驻内存。

### 终端 2：诊断后端（:8000）

```bash
cd backend/diagnosis
python main.py
# 或: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

预期输出：
```
Diagnosis backend starting on port 8000
Coze URL: https://gnp8dz4r4n.coze.site/stream_run
[startup] ASR model preloaded and ready.
```

### 终端 3：日常对话后端（:8001）

```bash
cd backend/daily_talk
python main.py
# 或: uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

预期输出：
```
Daily Talk backend starting on port 8001
Coze URL: https://your-daily-talk.coze.site/stream_run
[startup] ASR model preloaded and ready.
```

### 终端 4：前端（:5000）

```bash
cd chat-lab
npm run dev
```

预期输出：
```
▲ Next.js 16.x (Turbopack)
- Local:    http://localhost:5000
- Network:  http://10.x.x.x:5000
```

---

## 七、访问与验证

1. 打开浏览器访问 `http://localhost:5000`
2. 按住麦克风按钮说话，松开后约 0.5-1 秒出文字结果
3. 语音流程：浏览器录音 → 前端 `/api/asr` → 本地 ASR 服务 `:8002` → 返回文字

---

## 八、一键部署（可选）

如果嫌步骤多，直接运行：

```bash
bash backend/asr_deploy.sh
```

它会自动完成：环境检查 → ffmpeg 确认 → faster-whisper 安装 → 模型预下载 → 启动 ASR 服务。

---

## 九、常见问题

### Q1: 前端报 `Backend error 502`
检查后端是否已启动，且端口正确（8000 / 8001 / 8002）。

### Q2: ASR 服务启动后模型加载很久？
- 首次启动需要下载模型（约 500MB），参考 **五、ASR 模型预下载** 提前下载
- 之后加载约 1 秒，模型常驻内存

### Q3: 模型加载报 `Network is unreachable`？
模型缓存损坏或缺失。删除缓存后重新下载：
```bash
rm -rf ~/.cache/huggingface/hub/models--Systran--faster-whisper-small
export HF_ENDPOINT=https://hf-mirror.com
python3 -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"
```

### Q4: 如何测试后端是否健康？
```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8002/health
```

### Q5: 诊断完成后自动切换到日常对话，怎么生效？
当后端返回 `diagnosis_completed: true` 时，前端会自动将 `backendTarget` 设为 `"daily_talk"`。设置页面的按钮也会同步切换。

### Q6: 开启新对话后，后端 session 会重置吗？
会。`handleNewChat` 会生成新的 `familyId` 和 `childId`，后端会根据新的 ID 创建全新的 session。

### Q7: 不想启动独立 ASR 服务，只跑 diagnosis 可以吗？
可以。diagnosis/daily_talk 各自内置了 `/api/asr` 路由，启动时会预加载模型。但独立服务 `:8002` 响应更快，且后端重启不影响 ASR。
