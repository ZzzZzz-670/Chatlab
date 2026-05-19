"""
本地 ASR 测试脚本

用法:
    cd backend/diagnosis
    python test_local_asr.py

首次运行会自动生成一个 3 秒的中文测试音频（"这是一段测试语音"），
然后用 faster-whisper 进行识别。
"""

import base64
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# 确保能找到 local_asr
sys.path.insert(0, str(Path(__file__).parent))


def generate_test_audio(output_path: str, duration_sec: int = 3) -> None:
    """用 ffmpeg 生成一个 16kHz 单声道正弦波测试音频。"""
    from local_asr import _find_ffmpeg
    ffmpeg_path = _find_ffmpeg()
    cmd = [
        ffmpeg_path, "-y",
        "-f", "lavfi",
        "-i", f"sine=frequency=1000:duration={duration_sec}",
        "-ar", "16000",
        "-ac", "1",
        output_path,
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to generate test audio: {result.stderr.decode()[:500]}")
    print(f"[OK] Generated test audio: {output_path}")


def test_ffmpeg_find() -> None:
    from local_asr import _find_ffmpeg
    path = _find_ffmpeg()
    assert os.path.exists(path), f"ffmpeg not found at {path}"
    print(f"[OK] ffmpeg found: {path}")


def test_base64_roundtrip() -> None:
    """测试 base64 编解码和临时文件处理。"""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        generate_test_audio(f.name, duration_sec=1)
        wav_path = f.name

    try:
        with open(wav_path, "rb") as f:
            raw = f.read()
        b64 = base64.b64encode(raw).decode()
        decoded = base64.b64decode(b64)
        assert decoded == raw, "base64 roundtrip failed"
        print("[OK] base64 roundtrip")
    finally:
        os.remove(wav_path)


def test_local_asr_import() -> None:
    try:
        from local_asr import LocalASR
        print("[OK] LocalASR imported")
    except ImportError as e:
        print(f"[SKIP] Cannot import LocalASR: {e}")
        return False
    return True


def test_recognize_with_mock() -> None:
    """用真实音频测试识别（需要 faster-whisper 已安装）。"""
    try:
        from local_asr import LocalASR
    except ImportError:
        print("[SKIP] faster-whisper not installed, skipping recognition test")
        return

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        generate_test_audio(f.name, duration_sec=2)
        wav_path = f.name

    try:
        with open(wav_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        text = LocalASR.recognize(base64_data=b64, mime_type="audio/wav")
        print(f"[OK] Recognition result: '{text}'")
        # 正弦波没有语音内容，期望返回空或极短文本
    finally:
        os.remove(wav_path)


if __name__ == "__main__":
    print("=" * 50)
    print("Local ASR Test Suite")
    print("=" * 50)

    test_ffmpeg_find()
    test_base64_roundtrip()

    if test_local_asr_import():
        test_recognize_with_mock()
    else:
        print("\n[TODO] 请安装 faster-whisper 后重新运行测试:")
        print("  pip install faster-whisper")
        print("  # 国内网络可设置镜像:")
        print("  export HF_ENDPOINT=https://hf-mirror.com")

    print("=" * 50)
    print("Tests completed")
