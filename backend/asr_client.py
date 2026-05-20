"""
统一 ASR 客户端 — 支持讯飞 ASR（默认）与本地 faster-whisper 切换。

使用方式:
    from asr_client import recognize
    text = await recognize(base64_data="...", mime_type="audio/webm")

切换方式:
    修改本文件顶部 ASR_PROVIDER 常量:
        ASR_PROVIDER = "xunfei"   # 走讯飞 ASR（默认）
        ASR_PROVIDER = "local"    # 走本地 faster-whisper

环境变量（讯飞模式必需）:
    XUNFEI_APPID      — 讯飞应用 ID
    XUNFEI_API_KEY    — 讯飞 API Key
    XUNFEI_API_SECRET — 讯飞 API Secret

本地模式依赖:
    需要同目录或 Python 路径中存在 local_asr.LocalASR
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode
from wsgiref.handlers import format_date_time

import websocket

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# 方便修改的 TAG — 决定 ASR  Provider
# ═══════════════════════════════════════════════════════════════════════════════
ASR_PROVIDER: str = os.getenv("ASR_PROVIDER", "xunfei")  # "xunfei" | "local"

# ── 讯飞配置 ──
XUNFEI_APPID = os.getenv("XUNFEI_APPID", "")
XUNFEI_API_KEY = os.getenv("XUNFEI_API_KEY", "")
XUNFEI_API_SECRET = os.getenv("XUNFEI_API_SECRET", "")
XUNFEI_WS_URL = "wss://iat.xf-yun.com/v1"

# ── 本地 ASR 懒加载标记 ──
_LOCAL_ASR_AVAILABLE: Optional[bool] = None


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


_FFMPEG: str = _find_ffmpeg()


def _convert_to_pcm(input_path: str, output_path: str) -> None:
    """用 ffmpeg 把任意浏览器录音格式转成 16kHz mono 16bit PCM (s16le raw)。"""
    cmd = [
        _FFMPEG,
        "-y",
        "-i", input_path,
        "-ar", "16000",
        "-ac", "1",
        "-f", "s16le",
        output_path,
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        err = result.stderr.decode("utf-8", errors="ignore")[:500]
        raise RuntimeError(f"ffmpeg convert to pcm failed: {err}")


def _convert_to_wav(input_path: str, output_path: str) -> None:
    """用 ffmpeg 把任意浏览器录音格式转成 16kHz mono wav。"""
    cmd = [
        _FFMPEG,
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
        raise RuntimeError(f"ffmpeg convert to wav failed: {err}")


# ═══════════════════════════════════════════════════════════════════════════════
# 讯飞 ASR 实现（同步 WebSocket）
# ═══════════════════════════════════════════════════════════════════════════════

class _XunfeiASR:
    """讯飞中英识别大模型 — WebSocket 流式识别（≤60秒）。"""

    STATUS_FIRST = 0
    STATUS_CONTINUE = 1
    STATUS_LAST = 2

    def __init__(self):
        if not all((XUNFEI_APPID, XUNFEI_API_KEY, XUNFEI_API_SECRET)):
            raise RuntimeError(
                "讯飞 ASR 缺少必要配置，请设置环境变量: "
                "XUNFEI_APPID, XUNFEI_API_KEY, XUNFEI_API_SECRET"
            )

    def _create_url(self) -> str:
        now = time.localtime()
        date = format_date_time(time.mktime(now))
        signature_origin = (
            "host: " + "iat.xf-yun.com" + "\n"
            + "date: " + date + "\n"
            + "GET " + "/v1 " + "HTTP/1.1"
        )
        signature_sha = hmac.new(
            XUNFEI_API_SECRET.encode("utf-8"),
            signature_origin.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        signature = base64.b64encode(signature_sha).decode("utf-8")
        authorization_origin = (
            f'api_key="{XUNFEI_API_KEY}", '
            f'algorithm="hmac-sha256", '
            f'headers="host date request-line", '
            f'signature="{signature}"'
        )
        authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")
        v = {
            "authorization": authorization,
            "date": date,
            "host": "iat.xf-yun.com",
        }
        return XUNFEI_WS_URL + "?" + urlencode(v)

    def recognize(self, audio_bytes: bytes) -> str:
        """
        识别原始音频字节（任意格式），内部先转 pcm 再发送。
        返回识别文本。
        """
        if len(audio_bytes) < 100:
            raise ValueError("Audio data too short")

        # 1) 先写入临时文件
        suffix = ".webm"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_in:
            tmp_in.write(audio_bytes)
            input_path = tmp_in.name

        pcm_path = input_path.replace(suffix, ".pcm")
        try:
            _convert_to_pcm(input_path, pcm_path)
            pcm_data = open(pcm_path, "rb").read()
            return self._recognize_pcm(pcm_data)
        finally:
            for p in (input_path, pcm_path):
                try:
                    os.remove(p)
                except OSError:
                    pass

    def _recognize_pcm(self, pcm_data: bytes) -> str:
        """发送已转好的 pcm raw 数据到讯飞并返回文本。"""
        frame_size = 1280  # 每帧字节数
        interval = 0.04    # 发包间隔（秒）

        results: list[str] = []
        ws_conn: Optional[websocket.WebSocket] = None
        closed = False
        error_msg: Optional[str] = None

        def on_message(ws, message):
            nonlocal error_msg
            try:
                msg = json.loads(message)
            except json.JSONDecodeError:
                return
            code = msg.get("header", {}).get("code", -1)
            status = msg.get("header", {}).get("status")
            if code != 0:
                error_msg = f"讯飞 ASR 错误码: {code}"
                ws.close()
                return
            payload = msg.get("payload")
            if not payload:
                return
            text_b64 = payload.get("result", {}).get("text")
            if not text_b64:
                return
            try:
                text_json = json.loads(base64.b64decode(text_b64).decode("utf-8"))
            except Exception:
                return
            ws_list = text_json.get("ws", [])
            seg_text = ""
            for w_item in ws_list:
                for cw in w_item.get("cw", []):
                    seg_text += cw.get("w", "")
            if seg_text:
                results.append(seg_text)
            if status == 2:
                ws.close()

        def on_error(ws, error):
            nonlocal error_msg
            error_msg = str(error)

        def on_close(ws, *args):
            nonlocal closed
            closed = True

        # 使用 websocket-client 的同步接口
        ws_url = self._create_url()
        ws_conn = websocket.WebSocketApp(
            ws_url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )

        import ssl
        import threading

        # 在独立线程中跑 websocket 事件循环
        wst = threading.Thread(target=ws_conn.run_forever, kwargs={"sslopt": {"cert_reqs": ssl.CERT_NONE}})
        wst.daemon = True
        wst.start()

        # 等待连接建立（简单轮询）
        for _ in range(100):
            if ws_conn.sock is not None:
                break
            time.sleep(0.01)
        else:
            raise RuntimeError("无法建立讯飞 WebSocket 连接")

        # 分帧发送
        total_len = len(pcm_data)
        offset = 0
        seq = 0
        first_sent = False

        while offset < total_len or not first_sent:
            buf = pcm_data[offset:offset + frame_size]
            if not buf:
                break
            offset += len(buf)
            audio_b64 = base64.b64encode(buf).decode("utf-8")

            if not first_sent:
                status_flag = self.STATUS_FIRST
                first_sent = True
            elif offset >= total_len:
                status_flag = self.STATUS_LAST
            else:
                status_flag = self.STATUS_CONTINUE

            d = {
                "header": {
                    "app_id": XUNFEI_APPID,
                    "status": status_flag,
                },
                "parameter": {
                    "iat": {
                        "domain": "slm",
                        "language": "zh_cn",
                        "accent": "mandarin",
                        "dwa": "wpgs",
                        "result": {
                            "encoding": "utf8",
                            "compress": "raw",
                            "format": "plain",
                        },
                    }
                },
                "payload": {
                    "audio": {
                        "encoding": "raw",
                        "sample_rate": 16000,
                        "channels": 1,
                        "bit_depth": 16,
                        "seq": seq,
                        "status": status_flag,
                        "audio": audio_b64,
                    }
                },
            }
            seq += 1
            ws_conn.send(json.dumps(d))
            time.sleep(interval)

        # 等待关闭或超时
        for _ in range(3000):  # 最多 30 秒
            if closed:
                break
            time.sleep(0.01)
        else:
            ws_conn.close()

        if error_msg:
            raise RuntimeError(error_msg)

        return "".join(results)


# ═══════════════════════════════════════════════════════════════════════════════
# 本地 ASR 封装
# ═══════════════════════════════════════════════════════════════════════════════

class _LocalASRWrapper:
    """封装本地 faster-whisper，接口与讯飞统一。"""

    @staticmethod
    def recognize(base64_data: str, mime_type: Optional[str] = None) -> str:
        global _LOCAL_ASR_AVAILABLE
        if _LOCAL_ASR_AVAILABLE is None:
            try:
                from local_asr import LocalASR  # type: ignore
                _LOCAL_ASR_AVAILABLE = True
            except ImportError:
                _LOCAL_ASR_AVAILABLE = False

        if not _LOCAL_ASR_AVAILABLE:
            raise RuntimeError("Local ASR (faster-whisper) not available")

        from local_asr import LocalASR  # type: ignore
        return LocalASR.recognize(base64_data=base64_data, mime_type=mime_type)


# ═══════════════════════════════════════════════════════════════════════════════
# 统一对外接口
# ═══════════════════════════════════════════════════════════════════════════════

def _sync_recognize(base64_data: str, mime_type: Optional[str] = None) -> str:
    """同步识别入口，根据 ASR_PROVIDER 分发。"""
    provider = ASR_PROVIDER.lower().strip()
    logger.info("[ASR] provider=%s, mime_type=%s", provider, mime_type)

    if provider == "local":
        return _LocalASRWrapper.recognize(base64_data, mime_type)

    # 默认 / xunfei
    try:
        audio_bytes = base64.b64decode(base64_data)
    except Exception as exc:
        raise ValueError("Invalid base64 audio data") from exc

    xunfei = _XunfeiASR()
    return xunfei.recognize(audio_bytes)


async def recognize(base64_data: str, mime_type: Optional[str] = None) -> str:
    """
    异步识别入口（供 FastAPI async 路由调用）。
    根据 ASR_PROVIDER 决定走讯飞还是本地模型。
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_recognize, base64_data, mime_type)


def recognize_sync(base64_data: str, mime_type: Optional[str] = None) -> str:
    """同步识别入口（供非 async 代码调用，如 asr_standalone）。"""
    return _sync_recognize(base64_data, mime_type)
