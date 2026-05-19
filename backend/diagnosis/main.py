"""
diagnosis - 轻量 FastAPI 代理层
直接调用 Coze /stream_run，负责：
1. SSE 流式代理
2. 跨 chunk AGENT_META 状态机提取
3. Session 管理（family_id+child_id → session_id）
4. 用户信息 & 个性化注入
"""

import json
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from typing import Any, Optional

from dotenv import load_dotenv
load_dotenv()

import requests
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

# ── 日志 ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── 环境变量 ──
COZE_STREAM_RUN_URL = os.getenv("COZE_STREAM_RUN_URL", "https://gnp8dz4r4n.coze.site/stream_run")
COZE_TOKEN = os.getenv("COZE_TOKEN", "")
COZE_PROJECT_ID = os.getenv("COZE_PROJECT_ID", "7640760744073658402")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))

# ── Session 管理（内存版） ──
SESSION_MAP: dict[tuple[str, str], str] = {}


def get_session_id(family_id: str, child_id: str) -> str:
    key = (family_id, child_id)
    if key not in SESSION_MAP:
        SESSION_MAP[key] = str(uuid.uuid4())
        logger.info("New session created: %s for family=%s child=%s", SESSION_MAP[key], family_id, child_id)
    return SESSION_MAP[key]


# ── AGENT_META 跨 chunk 状态机 ──
class MetaExtractor:
    """
    在 SSE 流中跨 chunk 提取 <AGENT_META>...</AGENT_META>。
    标签可能被拆分到相邻 chunk 中，因此需要状态机处理部分匹配。
    """

    START_TAG = "<AGENT_META>"
    END_TAG = "</AGENT_META>"

    def __init__(self):
        self.state: str = "NORMAL"          # NORMAL | IN_META
        self.meta_buffer: str = ""          # AGENT_META 内部累积内容
        self.pending: str = ""              # 跨 chunk 的前缀缓冲

    def _find_start(self, text: str) -> tuple[str, str, bool]:
        """
        在 text 中查找 <AGENT_META> 的完整或部分前缀。
        返回 (visible_before, remaining_after, started)
        - started=True: 找到了完整 <AGENT_META>
        - started=False: 可能找到部分前缀，存入 pending
        """
        full = self.pending + text
        idx = full.find(self.START_TAG)
        if idx >= 0:
            visible = full[:idx]
            after = full[idx + len(self.START_TAG):]
            self.pending = ""
            return visible, after, True

        # 没有找到完整标签，检查是否有部分前缀在末尾
        # 检查 START_TAG 的所有后缀是否出现在 full 末尾
        for i in range(1, min(len(self.START_TAG), len(full)) + 1):
            if full.endswith(self.START_TAG[:i]):
                self.pending = full[-i:]
                return full[:-i], "", False

        self.pending = ""
        return full, "", False

    def _find_end(self, text: str) -> tuple[Optional[str], str, bool]:
        """
        在 text 中查找 </AGENT_META> 的完整或部分前缀。
        返回 (meta_content_if_complete, remaining_after, ended)
        """
        full = self.pending + text
        idx = full.find(self.END_TAG)
        if idx >= 0:
            meta_content = full[:idx]
            after = full[idx + len(self.END_TAG):]
            self.pending = ""
            return meta_content, after, True

        # 检查部分前缀
        for i in range(1, min(len(self.END_TAG), len(full)) + 1):
            if full.endswith(self.END_TAG[:i]):
                self.pending = full[-i:]
                return None, "", False

        self.pending = ""
        return None, full, False

    def feed(self, text: str) -> tuple[str, Optional[dict]]:
        """
        输入当前 chunk 的 answer 文本。
        返回 (visible_text_for_user, meta_dict_or_None)
        """
        visible_parts: list[str] = []
        meta_obj: Optional[dict] = None

        remaining = text

        while remaining:
            if self.state == "NORMAL":
                v, remaining, started = self._find_start(remaining)
                if v:
                    visible_parts.append(v)
                if started:
                    self.state = "IN_META"
                    self.meta_buffer = ""
                else:
                    break

            elif self.state == "IN_META":
                meta_content, remaining, ended = self._find_end(remaining)
                if meta_content is not None:
                    self.meta_buffer += meta_content
                elif remaining:
                    self.meta_buffer += remaining
                    remaining = ""
                    break

                if ended:
                    # 尝试解析 JSON
                    raw = self.meta_buffer.strip()
                    # 有时标签内可能有换行或多余空白
                    try:
                        meta_obj = json.loads(raw)
                        logger.info("AGENT_META extracted: %s", meta_obj.get("output_type", "unknown"))
                    except json.JSONDecodeError:
                        logger.warning("AGENT_META JSON parse failed, raw=%r", raw[:200])
                    self.state = "NORMAL"
                    self.meta_buffer = ""
                else:
                    break

        return "".join(visible_parts), meta_obj

    def finalize(self) -> Optional[dict]:
        """流结束时调用，处理未闭合的 meta"""
        if self.state == "IN_META":
            raw = self.meta_buffer.strip()
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Unclosed AGENT_META at stream end, raw=%r", raw[:200])
        return None


# ── Pydantic 模型 ──
class ChatMessage(BaseModel):
    text: str = ""
    attachments: list = []
    source: str = "chat_input"


class ClientContext(BaseModel):
    page: str = "chat"
    entry_mode: str = "daily_chat"
    communication_prefs: list[str] = []
    questionnaire_status: str = "not_started"


class ChatRequest(BaseModel):
    family_id: str = "family_demo"
    child_id: str = "child_demo"
    conversation_id: str = ""
    message: ChatMessage = ChatMessage()
    client_context: ClientContext = ClientContext()


# ── FastAPI ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Diagnosis backend starting on port %s", BACKEND_PORT)
    logger.info("Coze URL: %s", COZE_STREAM_RUN_URL)
    yield
    logger.info("Diagnosis backend shutting down")


app = FastAPI(title="Diagnosis Backend", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发环境放宽，生产需限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 组装 Coze payload ──
def build_coze_payload(req: ChatRequest, session_id: str) -> dict:
    family_id = req.family_id
    child_id = req.child_id
    prefs = req.client_context.communication_prefs
    q_status = req.client_context.questionnaire_status

    system_text = (
        f"你是家庭教育助手。当前用户信息：\n"
        f"- 家庭ID: {family_id}\n"
        f"- 孩子ID: {child_id}\n"
    )
    if prefs:
        system_text += f"- 沟通偏好: {', '.join(prefs)}\n"
    system_text += f"- 问卷状态: {q_status}\n"
    system_text += "请根据以上信息调整回复风格。"

    user_text = req.message.text.strip()

    return {
        "content": {
            "query": {
                "prompt": [
                    {"type": "text", "content": {"text": system_text}},
                    {"type": "text", "content": {"text": user_text}},
                ]
            }
        },
        "type": "query",
        "session_id": session_id,
        "project_id": COZE_PROJECT_ID,
    }


# ── 核心路由：SSE 流式 ──
@app.post("/stream_run")
async def stream_run(req: ChatRequest):
    if not COZE_TOKEN:
        return JSONResponse({"error": "COZE_TOKEN not configured"}, status_code=500)

    session_id = get_session_id(req.family_id, req.child_id)
    payload = build_coze_payload(req, session_id)

    logger.info("Stream run: family=%s child=%s session=%s", req.family_id, req.child_id, session_id)

    headers = {
        "Authorization": f"Bearer {COZE_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    try:
        coze_resp = requests.post(
            COZE_STREAM_RUN_URL,
            headers=headers,
            json=payload,
            stream=True,
            timeout=300,
        )
        coze_resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error("Coze request failed: %s", e)
        return JSONResponse({"error": f"Coze request failed: {str(e)}"}, status_code=502)

    def event_generator():
        extractor = MetaExtractor()
        try:
            for line in coze_resp.iter_lines(decode_unicode=True):
                if not line:
                    continue

                # SSE 格式: data: {...}
                if line.startswith("data:"):
                    data_str = line[5:].strip()

                    if data_str == "[DONE]":
                        yield "data: [DONE]\n\n"
                        continue

                    try:
                        parsed = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    if parsed.get("type") == "answer":
                        answer = parsed.get("content", {}).get("answer", "")
                        visible, meta = extractor.feed(answer)

                        if visible:
                            out = json.dumps(
                                {"type": "answer", "content": {"answer": visible}},
                                ensure_ascii=False,
                            )
                            yield f"data: {out}\n\n"

                        if meta:
                            yield f"event: agent_meta\ndata: {json.dumps(meta, ensure_ascii=False)}\n\n"

                # 保留其他 SSE 事件（如 event: message）
                elif line.startswith("event:"):
                    yield f"{line}\n"

            # 流结束，检查是否有未闭合的 meta
            remaining_meta = extractor.finalize()
            if remaining_meta:
                yield f"event: agent_meta\ndata: {json.dumps(remaining_meta, ensure_ascii=False)}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error("Stream error: %s", e)
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        finally:
            coze_resp.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── 健康检查 ──
@app.get("/health")
async def health():
    return {"status": "ok", "sessions": len(SESSION_MAP)}


# ── 获取/重置 session（调试用） ──
@app.get("/session/{family_id}/{child_id}")
async def get_session(family_id: str, child_id: str):
    return {
        "family_id": family_id,
        "child_id": child_id,
        "session_id": get_session_id(family_id, child_id),
    }


@app.delete("/session/{family_id}/{child_id}")
async def clear_session(family_id: str, child_id: str):
    key = (family_id, child_id)
    if key in SESSION_MAP:
        del SESSION_MAP[key]
        return {"cleared": True}
    return {"cleared": False}


# ── 主入口 ──
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=BACKEND_PORT, reload=True)
