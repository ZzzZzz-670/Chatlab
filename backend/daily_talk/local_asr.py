"""
本地 ASR 服务 — 基于 faster-whisper，纯本地运行，不依赖外部 API。

使用方式:
    from local_asr import LocalASR
    # 启动时预加载（推荐）
    LocalASR.preload()
    # 识别
    text = LocalASR.recognize(base64_data="...", mime_type="audio/webm")

安装依赖:
    uv pip install faster-whisper
    # 或 pip install faster-whisper

模型:
    - base  : ~150MB, 加载快, 适合短语音/ prototyping
    - small : ~500MB, 中文效果更好
    通过环境变量 WHISPER_MODEL 切换，默认 base。
"""

import base64
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _find_ffmpeg() -> str:
    """优先使用项目自带的 ffmpeg，否则找系统 PATH 中的。"""
    script_dir = Path(__file__).resolve().parent
    for rel in ("..", "../..", "../../.."):
        candidate = (script_dir / rel / "ffmpeg").resolve()
        if candidate.exists():
            return str(candidate)
    for rel in ("../projects", "../../projects", "../../../projects"):
        candidate = (script_dir / rel / "ffmpeg").resolve()
        if candidate.exists():
            return str(candidate)
    for name in ("ffmpeg", "ffmpeg.exe"):
        path = os.popen(f"which {name} 2>/dev/null").read().strip()
        if path:
            return path
    raise RuntimeError("ffmpeg not found. 请安装 ffmpeg 或将其放入 PATH。")


class LocalASR:
    """faster-whisper 本地识别封装（单例，支持预加载）。"""

    _model = None
    _model_size: str = os.getenv("WHISPER_MODEL", "small")
    _device: str = os.getenv("WHISPER_DEVICE", "cpu")
    _compute_type: str = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
    _ffmpeg: str = _find_ffmpeg()

    @classmethod
    def preload(cls) -> bool:
        """
        启动时预加载模型，避免第一次请求时才加载导致超时。
        返回是否加载成功。
        """
        if cls._model is not None:
            logger.info("[ASR] Model already loaded, skip preload.")
            return True

        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            logger.error("[ASR] faster-whisper not installed: %s", exc)
            return False

        logger.info(
            "[ASR] >>> Start loading model=%s device=%s compute_type=%s ...",
            cls._model_size,
            cls._device,
            cls._compute_type,
        )
        start = time.time()
        try:
            # local_files_only=True: 优先用本地缓存，不强制联网
            cls._model = WhisperModel(
                cls._model_size,
                device=cls._device,
                compute_type=cls._compute_type,
                local_files_only=True,
            )
            elapsed = time.time() - start
            logger.info(
                "[ASR] <<< Model loaded OK (%.1fs). model_size=%s",
                elapsed,
                cls._model_size,
            )
            return True
        except Exception as exc:
            elapsed = time.time() - start
            logger.error("[ASR] <<< Model load FAILED after %.1fs: %s", elapsed, exc)
            return False

    @classmethod
    def _load_model(cls):
        if cls._model is not None:
            return cls._model
        cls.preload()
        if cls._model is None:
            raise RuntimeError("ASR model not available")
        return cls._model

    @classmethod
    def _convert_to_wav(cls, input_path: str, output_path: str) -> None:
        """用 ffmpeg 把任意浏览器录音格式转成 16kHz mono wav。"""
        cmd = [
            cls._ffmpeg,
            "-y",
            "-i", input_path,
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            output_path,
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="ignore")[:500]
            raise RuntimeError(f"ffmpeg convert failed: {err}")

    @classmethod
    def recognize(
        cls,
        base64_data: str,
        mime_type: Optional[str] = None,
    ) -> str:
        """
        识别 base64 编码的音频，返回文本。
        模型未加载时会自动加载（但推荐 startup 时 preload）。
        """
        model = cls._load_model()

        try:
            audio_bytes = base64.b64decode(base64_data)
        except Exception as exc:
            raise ValueError("Invalid base64 audio data") from exc

        if len(audio_bytes) < 100:
            raise ValueError("Audio data too short")

        suffix = ".webm"
        if mime_type:
            if "mp4" in mime_type or "m4a" in mime_type:
                suffix = ".mp4"
            elif "wav" in mime_type:
                suffix = ".wav"
            elif "ogg" in mime_type:
                suffix = ".ogg"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_in:
            tmp_in.write(audio_bytes)
            input_path = tmp_in.name

        if suffix == ".wav":
            output_path = input_path
        else:
            output_path = input_path.replace(suffix, ".wav")

        try:
            if input_path != output_path:
                cls._convert_to_wav(input_path, output_path)
            segments, info = model.transcribe(
                output_path,
                language="zh",
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500),
            )
            logger.debug("Detected language=%s, prob=%.2f", info.language, info.language_probability)
            texts = [seg.text for seg in segments]
            result = "".join(texts).strip()
            return result
        finally:
            for p in (input_path, output_path):
                try:
                    os.remove(p)
                except OSError:
                    pass
