"""
ASR API 完整调试测试 — 生成真实音频并调用本地 /api/asr
"""
import base64
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

# 确保 local_asr 可被导入
sys.path.insert(0, str(Path(__file__).parent))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def _find_ffmpeg():
    from local_asr import _find_ffmpeg as ff
    return ff()


def generate_wav(path: str, duration: int = 2) -> None:
    ffmpeg = _find_ffmpeg()
    cmd = [
        ffmpeg, "-y", "-f", "lavfi",
        "-i", f"sine=frequency=1000:duration={duration}",
        "-ar", "16000", "-ac", "1", path
    ]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg gen failed: {r.stderr.decode()[:500]}")
    print(f"[OK] 生成测试音频: {path} ({os.path.getsize(path)} bytes)")


def test_decode_invalid_base64():
    print("\n--- 测试1: 非法 base64 ---")
    resp = client.post("/api/asr", json={
        "base64_data": "音频base64字符串",
        "mime_type": "audio/webm"
    })
    print(f"Status: {resp.status_code}")
    print(f"Body: {resp.text}")


def test_empty_audio():
    print("\n--- 测试2: 空音频 ---")
    resp = client.post("/api/asr", json={
        "base64_data": base64.b64encode(b"\x00" * 50).decode(),
        "mime_type": "audio/wav"
    })
    print(f"Status: {resp.status_code}")
    print(f"Body: {resp.text}")


def test_real_wav():
    print("\n--- 测试3: 真实 WAV 音频（正弦波，无语音内容）---")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
    try:
        generate_wav(wav_path, duration=1)
        with open(wav_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        resp = client.post("/api/asr", json={
            "base64_data": b64,
            "mime_type": "audio/wav"
        })
        print(f"Status: {resp.status_code}")
        print(f"Body: {resp.text}")
    finally:
        os.remove(wav_path)


def test_local_asr_directly():
    print("\n--- 测试4: 直接调用 LocalASR（绕过 FastAPI）---")
    from local_asr import LocalASR
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
    try:
        generate_wav(wav_path, duration=1)
        with open(wav_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        text = LocalASR.recognize(base64_data=b64, mime_type="audio/wav")
        print(f"[OK] 识别结果: '{text}'")
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        traceback.print_exc()
    finally:
        os.remove(wav_path)


def test_model_load():
    print("\n--- 测试5: 模型加载 ---")
    from local_asr import LocalASR
    try:
        model = LocalASR._load_model()
        print(f"[OK] 模型加载成功: {model}")
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    print("=" * 60)
    print("ASR API Debug Test")
    print("=" * 60)

    test_model_load()
    test_local_asr_directly()
    test_decode_invalid_base64()
    test_empty_audio()
    test_real_wav()

    print("\n" + "=" * 60)
    print("Debug completed")
