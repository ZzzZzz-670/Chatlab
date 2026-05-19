# 本地 ASR 环境安装指南

> 基于 faster-whisper，纯本地运行，不连 coze/国外 API。

---

## 一、ffmpeg（音频格式转换）

项目已自带静态 ffmpeg，位于 `backend/projects/ffmpeg`，**通常无需额外安装**。

如需系统级 ffmpeg：
```bash
sudo apt update && sudo apt install -y ffmpeg
```

验证：
```bash
backend/projects/ffmpeg -version
```

---

## 二、Python 依赖安装

### 2.1 diagnosis 后端（端口 8000）

```bash
cd backend/diagnosis
pip install -r requirements.txt
```

或 uv 用户：
```bash
cd backend/diagnosis
uv pip install -r requirements.txt
```

### 2.2 daily_talk 后端（端口 8001）

```bash
cd backend/daily_talk
pip install -r requirements.txt
```

或 uv 用户：
```bash
cd backend/daily_talk
uv pip install -r requirements.txt
```

### 2.3 projects 后端（如有使用）

```bash
cd backend/projects
uv pip install -e "."
```

---

## 三、模型下载（首次运行自动下载）

faster-whisper 首次运行时会自动从 HuggingFace 下载模型：

- `small` 模型（默认）：约 **500MB**，中文识别效果较好
- `base` 模型（可选）：约 **150MB**，速度更快但准确度稍低

如需切换模型，设置环境变量：
```bash
export WHISPER_MODEL=base   # 或 small / medium
```

### 国内网络加速

如果 HuggingFace 下载慢或连不上，设置国内镜像：
```bash
export HF_ENDPOINT=https://hf-mirror.com
```

模型缓存位置：`~/.cache/whisper/`

---

## 四、启动验证

### 4.1 启动 diagnosis 后端

```bash
cd backend/diagnosis
python main.py
# 或: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 4.2 测试 ASR 接口

```bash
curl -X POST http://localhost:8000/api/asr \
  -H "Content-Type: application/json" \
  -d '{"base64_data":"你的音频base64","mime_type":"audio/webm"}'
```

预期返回：
```json
{"status": "success", "text": "识别出的文字"}
```

### 4.3 运行本地测试脚本

```bash
cd backend/diagnosis
python test_local_asr.py
```

---

## 五、前端无需改动

Next.js 的 `/api/asr` 路由已修改为转发到本地后端（`localhost:8000/api/asr`），前端代码完全不用改。

---

## 六、常见问题

**Q: pip install faster-whisper 报错？**
- 确保 Python >= 3.10
- 如有编译错误，先安装：`sudo apt install python3-dev build-essential`

**Q: 模型下载卡住？**
- 检查 HuggingFace 连通性
- 使用 `HF_ENDPOINT=https://hf-mirror.com` 镜像
- 或手动下载模型放到 `~/.cache/whisper/`

**Q: 识别速度很慢？**
- CPU 运行 small 模型，1-2 秒音频约需 0.5-1 秒
- 如需更快，切换为 `WHISPER_MODEL=base`
- 有 NVIDIA GPU 可改为 `WHISPER_DEVICE=cuda WHISPER_COMPUTE_TYPE=float16`

**Q: 中文识别效果一般？**
- base 模型对中文支持一般，建议用 small
- 确保音频采样率正常（ffmpeg 会自动转 16kHz）
