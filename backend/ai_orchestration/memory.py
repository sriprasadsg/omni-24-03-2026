"""Persistent, tenant-scoped LangGraph checkpointer for Phase 39 (AISPEC-39-S4).

Provides an `AsyncSqliteSaver`-backed checkpointer stored on disk under
`data/` — consistent with this deployment's existing ChromaDB-on-disk
convention (`rag_service.py`'s `DB_DIR = .../data/chroma_db`) — plus
`make_thread_id(tenant_id, conversation_id)`, the mandatory tenant-prefixed
thread-id policy (39-AI-SPEC.md Section 4 State Management / Pitfall 3).

There is no existing conversation-memory pattern in this codebase to follow
here: the nearest in-process dict used for demo-flow session state is an
explicitly-documented anti-pattern for real conversation memory (vanishes on
restart, grows unbounded per process, and is not tenant-prefixed) and must
NOT be used as a template (39-AI-SPEC.md Pitfall 5). This module always
prefixes `thread_id` with the tenant id so two tenants sharing a
conversation id can never share memory, and defaults to the persistent
SQLite saver rather than any in-process structure.
"""
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# ai_orchestration/ lives one level under backend/ — data/ is a sibling of
# ai_orchestration/, matching rag_service.py's backend/data/ convention.
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "data")
CHECKPOINT_DB_PATH = os.path.join(DATA_DIR, "langgraph_checkpoints.sqlite")


def make_thread_id(tenant_id: str, conversation_id: str) -> str:
    """Return the mandatory tenant-prefixed thread_id: f"{tenant_id}:{conversation_id}".

    Two tenants sharing the same `conversation_id` MUST never resolve to the
    same `thread_id` — the tenant prefix is not optional (39-AI-SPEC.md
    Pitfall 3, the session-fixation-equivalent control for conversation
    memory). Never pass a bare `conversation_id` to a checkpointer's
    `config={"configurable": {"thread_id": ...}}`.
    """
    if not tenant_id:
        raise ValueError("make_thread_id requires a non-empty tenant_id")
    if not conversation_id:
        raise ValueError("make_thread_id requires a non-empty conversation_id")
    return f"{tenant_id}:{conversation_id}"


def _use_dev_memory_saver(dev_mode: Optional[bool]) -> bool:
    if dev_mode is not None:
        return dev_mode
    return os.getenv("LANGGRAPH_CHECKPOINTER", "").strip().lower() == "memory"


@asynccontextmanager
async def checkpointer_lifespan(dev_mode: Optional[bool] = None) -> AsyncIterator:
    """FastAPI-lifespan-friendly async context manager yielding a checkpointer.

    Defaults to the persistent `AsyncSqliteSaver` under `data/`. Set
    `dev_mode=True` (or env `LANGGRAPH_CHECKPOINTER=memory`) to use an
    in-process `InMemorySaver` instead for local development only — never in
    production, since it vanishes on restart and grows unbounded per process
    (39-AI-SPEC.md Pitfall 5).

    Usage (FastAPI lifespan)::

        async with checkpointer_lifespan() as checkpointer:
            agent = create_agent(..., checkpointer=checkpointer)
            yield  # app runs here
    """
    if _use_dev_memory_saver(dev_mode):
        logger.info("[ai_orchestration.memory] Using in-process InMemorySaver (dev mode)")
        yield InMemorySaver()
        return

    os.makedirs(DATA_DIR, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(CHECKPOINT_DB_PATH) as saver:
        logger.info("[ai_orchestration.memory] Persistent checkpointer at %s", CHECKPOINT_DB_PATH)
        yield saver
