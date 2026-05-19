#!/usr/bin/env python3
"""
ASR 一键测试脚本 — 生成测试音频并调用本地 /api/asr

用法:
    python test_audio.py                  # 生成 3 秒测试音频并识别
    python test_audio.py /path/to/voice.wav   # 识别指定音频文件

需要后端已启动: python backend/diagnosis/main.py
"""

import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

API_URL = "http://localhost:8000/api/asr"


def find_ffmpeg() -> str:
    """找 ffmpeg（优先项目自带）。"""
    script_dir = Path(__file__).resolve().parent
    for rel in ("backend/projects", "backend/projects/ffmpeg"):
        p = (script_dir / rel).resolve()
        if p.is_file():
            return str(p)
    for name in ("ffmpeg", "ffmpeg.exe"):
        path = os.popen(f"which {name} 2>/dev/null").read().strip()
        if path:
            return path
    raise RuntimeError("ffmpeg not found")


def generate_test_audio(output_path: str, duration: int = 3) -> None:
    """生成测试音频 — 用人声频段更丰富的信号模拟语音。"""
    ffmpeg = find_ffmpeg()
    # 用多个正弦波叠加模拟人声频谱，比单一频率更像语音
    cmd = [
        ffmpeg, "-y", "-f", "lavfi",
        "-i", f"aevalsrc=0.3*sin(200*2*PI*t)+0.3*sin(400*2*PI*t)+0.2*sin(800*2*PI*t):s=16000:d={duration}",
        "-ar", "16000", "-ac", "1",
        output_path,
    ]
    print(f"[1/5] 生成测试音频 ({duration}s) ...")
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        err = r.stderr.decode("utf-8", errors="ignore")[:300]
        raise RuntimeError(f"ffmpeg 生成音频失败: {err}")
    size = os.path.getsize(output_path)
    print(f"[2/5] 音频已生成: {output_path} ({size} bytes)")


def call_asr(audio_path: str) -> dict:
    """读取音频文件并调用 ASR API。"""
    print(f"[3/5] 读取音频并 base64 编码 ...")
    with open(audio_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    data = json.dumps({
        "base64_data": b64,
        "mime_type": "audio/wav",
    }).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={"Content-Type": "application/json"},
    )

    print(f"[4/5] 发送请求到 {API_URL} ...")
    start = time.time()
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        elapsed = time.time() - start
        body = resp.read().decode("utf-8")
        print(f"[5/5] 收到响应 ({elapsed:.2f}s) status={resp.status}")
        return {"status": resp.status, "body": body, "elapsed": elapsed}
    except urllib.error.HTTPError as e:
        elapsed = time.time() - start
        body = e.read().decode("utf-8") if e.fp else ""
        print(f"[5/5] 请求失败 ({elapsed:.2f}s) status={e.code}")
        return {"status": e.code, "body": body, "elapsed": elapsed, "error": str(e)}
    except Exception as e:
        elapsed = time.time() - start
        print(f"[5/5] 请求异常 ({elapsed:.2f}s): {e}")
        return {"status": -1, "body": str(e), "elapsed": elapsed, "error": str(e)}


def main():
    print("=" * 60)
    print("ASR 一键测试")
    print("=" * 60)

    if len(sys.argv) >= 2:
        audio_path = sys.argv[1]
        if not os.path.exists(audio_path):
            print(f"错误: 文件不存在: {audio_path}")
            sys.exit(1)
        print(f"使用指定音频: {audio_path}")
    else:
        # 自动生成测试音频
        audio_path = "/tmp/test_asr_audio.wav"
        generate_test_audio(audio_path, duration=3)

    result = call_asr(audio_path)

    print("\n" + "-" * 60)
    print("响应详情:")
    print("-" * 60)
    try:
        parsed = json.loads(result["body"])
        print(json.dumps(parsed, ensure_ascii=False, indent=2))
    except Exception:
        print(result["body"])

    # 清理临时文件
    if audio_path == "/tmp/test_asr_audio.wav" and os.path.exists(audio_path):
        os.remove(audio_path)

    print("=" * 60)


if __name__ == "__main__":
    main()
