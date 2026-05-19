#!/bin/bash
# ASR 服务一键部署脚本 — 新设备上预下载模型 + 启动监听
set -e

echo "========================================"
echo "  ASR 服务部署"
echo "========================================"

# 1. 检查 ffmpeg
if [ ! -f "backend/projects/ffmpeg" ]; then
    echo "[1/4] 下载 ffmpeg 静态二进制..."
    curl -sL https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz \
        | tar -xJ -C backend/projects --strip-components=1 --wildcards "*/ffmpeg" 2>/dev/null \
        || { echo "ffmpeg 下载失败，请手动安装"; exit 1; }
    chmod +x backend/projects/ffmpeg
else
    echo "[1/4] ffmpeg 已存在"
fi

# 2. 检查 Python 依赖
echo "[2/4] 安装 Python 依赖..."
pip install faster-whisper 2>/dev/null || pip3 install faster-whisper

# 3. 预下载模型（国内镜像）
echo "[3/4] 预下载 ASR 模型（small，约 500MB）..."
HF_ENDPOINT=https://hf-mirror.com python3 -c "
from faster_whisper import WhisperModel
import time
t0 = time.time()
m = WhisperModel('small', device='cpu', compute_type='int8')
print(f'模型加载完成，耗时 {time.time()-t0:.1f}s')
" || {
    echo "模型下载失败，尝试直接连接 HuggingFace..."
    python3 -c "
from faster_whisper import WhisperModel
import time
t0 = time.time()
m = WhisperModel('small', device='cpu', compute_type='int8')
print(f'模型加载完成，耗时 {time.time()-t0:.1f}s')
"
}

# 4. 启动服务
echo "[4/4] 启动 ASR 服务..."
echo "========================================"
python3 backend/asr_standalone.py
