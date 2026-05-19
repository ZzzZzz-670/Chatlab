#!/usr/bin/env python3
"""
ASR 独立服务 — 只负责语音转文字，模型启动时加载并常驻内存。

用法:
    python backend/asr_standalone.py

默认端口 8002，启动后会看到详细的模型加载日志。
加载完成后服务保持运行，可通过 http://localhost:8002/api/asr 调用。
"""

import base64
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

# 确保能找到 local_asr（兼容从项目根目录或 backend/ 下启动）
SCRIPT_DIR = Path(__file__).resolve().parent
for d in (SCRIPT_DIR / "diagnosis", SCRIPT_DIR / "projects/src", SCRIPT_DIR):
    if (d / "local_asr.py").exists():
        sys.path.insert(0, str(d))
        break

from local_asr import LocalASR

# ── 日志配置 ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

PORT = int(os.getenv("ASR_PORT", "8002"))


def print_memory_info():
    """打印当前进程的内存占用。"""
    try:
        import psutil
        proc = psutil.Process()
        mem = proc.memory_info()
        logger.info("[memory] RSS=%.1f MB | VMS=%.1f MB", mem.rss / 1024 / 1024, mem.vms / 1024 / 1024)
    except ImportError:
        logger.info("[memory] 安装 psutil 后可查看内存占用: pip install psutil")


def preload_with_detail() -> bool:
    """加载模型并输出详细过程。"""
    logger.info("=" * 60)
    logger.info("ASR Standalone Service")
    logger.info("=" * 60)
    logger.info("[1/3] 准备加载 faster-whisper 模型...")
    logger.info("      model=%s device=%s compute_type=%s",
                LocalASR._model_size, LocalASR._device, LocalASR._compute_type)

    print_memory_info()

    t0 = time.time()
    ok = LocalASR.preload()
    t1 = time.time()

    if not ok:
        logger.error("[2/3] 模型加载失败！耗时 %.1fs", t1 - t0)
        return False

    logger.info("[2/3] 模型加载成功！耗时 %.1fs", t1 - t0)
    logger.info("[3/3] 验证模型对象...")
    logger.info("      model object: %s", LocalASR._model)
    logger.info("      model size: %s", LocalASR._model_size)
    logger.info("      model is in memory: YES")

    print_memory_info()
    logger.info("=" * 60)
    logger.info("Service READY at http://localhost:%s/api/asr", PORT)
    logger.info("=" * 60)
    return True


def handle_request(environ, start_response):
    """极简 WSGI handler — 只处理 POST /api/asr"""
    path = environ.get("PATH_INFO", "")
    method = environ.get("REQUEST_METHOD", "")

    if method == "GET" and path == "/health":
        start_response("200 OK", [("Content-Type", "application/json")])
        return [json.dumps({"status": "ok", "asr_ready": LocalASR._model is not None}).encode()]

    if method != "POST" or path != "/api/asr":
        start_response("404 Not Found", [("Content-Type", "application/json")])
        return [json.dumps({"error": "Only POST /api/asr is supported"}).encode()]

    try:
        content_length = int(environ.get("CONTENT_LENGTH", 0))
        body = environ["wsgi.input"].read(content_length)
        payload = json.loads(body)
        base64_data = payload.get("base64_data") or payload.get("base64Data")
        mime_type = payload.get("mime_type") or payload.get("mimeType")

        if not base64_data:
            start_response("400 Bad Request", [("Content-Type", "application/json")])
            return [json.dumps({"error": "base64_data is required"}).encode()]

        t0 = time.time()
        text = LocalASR.recognize(base64_data=base64_data, mime_type=mime_type)
        t1 = time.time()

        logger.info("[recognize] 识别耗时 %.2fs, text='%s'", t1 - t0, text[:50] if text else "(empty)")

        start_response("200 OK", [("Content-Type", "application/json")])
        return [json.dumps({"status": "success", "text": text}, ensure_ascii=False).encode()]

    except Exception as e:
        logger.error("[recognize] error: %s", e)
        start_response("500 Internal Server Error", [("Content-Type", "application/json")])
        return [json.dumps({"error": str(e)}).encode()]


def main():
    if not preload_with_detail():
        sys.exit(1)

    from wsgiref.simple_server import make_server
    logger.info("Starting HTTP server on port %s...", PORT)
    httpd = make_server("0.0.0.0", PORT, handle_request)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("\nShutting down...")
        httpd.shutdown()


if __name__ == "__main__":
    main()
