"""
Phase 38-01 — AI Security Assistant Endpoints.

POST /api/assistant/chat       — non-streaming JSON response
POST /api/assistant/chat/stream — SSE streaming (text/event-stream)
"""

import json as _json
import logging
from fastapi import APIRouter, Depends, Body
from fastapi.responses import StreamingResponse
from typing import Any, AsyncIterator

from ai_assistant_service import ai_assistant_service
from authentication_service import get_current_user
from tenant_context import get_tenant_id
from rbac_service import rbac_service
from auth_types import TokenData

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/assistant", tags=["AI Security Assistant"])


# ── Request models ────────────────────────────────────────────────────────────

class ChatRequestBody(BaseModel):
    """Shared request shape — imported lazily below via __init__ guard."""

    class __init__:
        pass


# ── Chat (non-streaming) ─────────────────────────────────────────────────────

@router.post("/chat")
async def chat_with_assistant(
    body: dict[str, Any],
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> dict[str, Any]:
    """
    Answer a security/compliance question with grounded sources.

    Body: {
        "query": str,       # required — the user's question
        "history": [        # optional — prior turns [{role, content}, ...]
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "..."},
        ],
    }
    """
    query = body.get("query", "").strip()
    if not query:
        return {"answer": "No question provided.", "sources": []}

    history = body.get("history", [])
    tenant_id = get_tenant_id()

    result = await ai_assistant_service.chat(query, tenant_id, history)
    return result


# ── Chat (SSE streaming) ──────────────────────────────────────────────────────

async def _stream_answer(
    query: str,
    tenant_id: str,
    history: list[dict[str, str]] | None,
) -> AsyncIterator[str]:
    """Yield SSE frames for the chat stream."""
    import asyncio as _asyncio

    # Fetch the full result first; stream the answer token-by-token
    try:
        result = await ai_assistant_service.chat(query, tenant_id, history)
    except Exception as exc:
        logger.error("[Assistant/stream] chat() failed: %s", exc)
        yield f"data: {_json.dumps({'error': str(exc)})}\n\n"
        yield "data: [DONE]\n\n"
        return

    answer: str = result.get("answer", "")
    sources: list[dict] = result.get("sources", [])

    # Stream answer word-by-word so the UI can animate progressively
    words = answer.split()
    for i, word in enumerate(words):
        yield f"data: {_json.dumps({'chunk': word + (' ' if i < len(words) - 1 else '')})}\n\n"
        await _asyncio.sleep(0.02)  # ~50 tokens/s feel

    # Final frame carries sources
    yield f"data: {_json.dumps({'sources': sources})}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/chat/stream")
async def chat_with_assistant_stream(
    body: dict[str, Any],
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> StreamingResponse:
    """
    Stream a security/compliance answer via Server-Sent Events.

    Frames:
      data: {"chunk": "word "}    — streamed answer tokens
      data: {"sources": [...]}    — final frame with citations
      data: [DONE]               — stream end sentinel
    """
    query = body.get("query", "").strip()
    if not query:
        return StreamingResponse(
            iter([f"data: {_json.dumps({'error': 'No query provided.'})}\n\n",
                  "data: [DONE]\n\n"]),
            media_type="text/event-stream",
        )

    history = body.get("history", [])
    tenant_id = get_tenant_id()

    return StreamingResponse(
        _stream_answer(query, tenant_id, history),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering for real-time
        },
    )


# ── Pydantic import must happen after Body is defined ─────────────────────────
from pydantic import BaseModel


class ChatRequestBody(BaseModel):
    query: str
    history: list[dict[str, str]] = []