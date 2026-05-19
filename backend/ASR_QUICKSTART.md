# ASR 服务快速部署（新设备）

> 目标：预下载模型 → 常驻内存 → 端口监听 → 接收识别请求

---

## 1. 环境准备（一次）

```bash
# 进入项目目录
cd /path/to/Chatlab

# 安装 ffmpeg（项目已自带，如无则下载）
[ -f backend/projects/ffmpeg ] || (
  curl -sL https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz \
    | tar -xJ -C backend/projects --strip-components=1 --wildcards "*/ffmpeg"
  chmod +x backend/projects/ffmpeg
)

# 安装 Python 依赖
pip install faster-whisper
```

---

## 2. 预下载模型（一次，约 500MB）

```bash
# 国内网络加镜像
export HF_ENDPOINT=https://hf-mirror.com

# 执行预下载（模型会自动缓存到 ~/.cache/huggingface/hub/）
python3 -c "
from faster_whisper import WhisperModel
print('>>> 开始下载模型...')
WhisperModel('small', device='cpu', compute_type='int8')
print('<<< 模型已缓存')
"
```

> 缓存位置：`~/.cache/huggingface/hub/models--Systran--faster-whisper-small/`
> 之后断网也能用。

---

## 3. 启动服务（常驻内存 + 端口监听）

```bash
python3 backend/asr_standalone.py
```

输出示例：
```
[ASR] >>> Start loading model=small ...
[ASR] <<< Model loaded OK (0.9s). model_size=small
      model is in memory: YES
Service READY at http://localhost:8002/api/asr
```

**保持这个窗口运行**，模型已常驻内存。

---

## 4. 验证

```bash
# 生成测试音频
backend/projects/ffmpeg -y -f lavfi -i sine=frequency=1000:duration=2 \
  -ar 16000 -ac 1 /tmp/test.wav

# 调用接口
curl -X POST http://localhost:8002/api/asr \
  -H "Content-Type: application/json" \
  -d "{\"base64_data\":\"$(base64 /tmp/test.wav | tr -d '\n')\",\"mime_type\":\"audio/wav\"}"
```

预期返回：
```json
{"status": "success", "text": ""}
```

---

## 5. 接入前端

前端 Next.js 的 `/api/asr` 已配置为**优先转发到 8002**，无需改动。

启动前端后，按住麦克风说话即可识别。

---

## 核心文件说明

| 文件 | 作用 |
|---|---|
| `backend/asr_standalone.py` | ASR 独立服务（加载模型 + HTTP 监听） |
| `backend/asr_deploy.sh` | 一键部署脚本（环境 + 下载 + 启动） |
| `backend/projects/ffmpeg` | 音频格式转换工具 |

---

## 可选：换更小模型

如果设备性能差或想更快：

```bash
export WHISPER_MODEL=base   # 150MB，加载更快
python3 backend/asr_standalone.py
```
