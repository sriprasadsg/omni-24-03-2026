"""AI Security Assistant Service — LangChain compatibility shim (Phase 39-07).

`chat(query, tenant_id, history=None) -> {answer, sources}` keeps its exact
pre-existing signature and return shape so `ai_assistant_endpoints.py`'s
both JSON (`/api/assistant/chat`) and SSE (`/api/assistant/chat/stream`)
routes need no change (39-CONTEXT.md: "internals swap to LangChain paths;
no route/frontend changes"). Internally this now delegates to
`ai_orchestration.agents.chat.chat` — a `create_agent`-based agent with the
tenant-closed `search_evidence` tool, a persistent tenant-prefixed
checkpointer (39-04), guardrails, and provenance (Phase 39-07) — replacing
the old inline RAG-context-building + `ai_service.generate_text(prompt)`
call.

Fail-closed contract preserved: any agent exception here returns
`{answer: <error string>, sources: []}` rather than raising, mirroring the
prior `except` path — `ai_orchestration.agents.chat.chat` already resolves
its own internal failures (guardrail blocks, agent invocation errors) to
this same safe shape, so this outer `try/except` is a second line of
defense against an error surfacing before that point (e.g. resolving `db`).
"""

import logging
from typing import Any, Optional

from database import get_database

logger = logging.getLogger(__name__)


async def chat(
    query: str,
    tenant_id: str,
    history: Optional[list[dict[str, str]]] = None,
) -> dict[str, Any]:
    """
    Answer a tenant-scoped security/compliance question with grounded sources.

    Returns
    -------
    {
        "answer": str,          # LLM response text
        "sources": [            # citations used
            {"type": str, "id": str, "title": str, "snippet": str},
            ...
        ],
    }
    """
    try:
        from ai_orchestration.agents.chat import chat as agent_chat

        db = get_database()
        return await agent_chat(query, tenant_id, history=history, db=db)
    except Exception as exc:
        logger.error("[AIAssistant] LangChain agent chat failed: %s", exc)
        return {"answer": f"Error generating response: {exc}", "sources": []}
