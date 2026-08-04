"""Thread ID factory for tenant-isolated conversation memory (39-03)."""

from typing import Optional


def make_thread_id(tenant_id: str, conversation_id: str) -> str:
    """Prefix thread_id with tenant to prevent cross-tenant memory sharing.

    Per AI-SPEC Pitfall 3: thread_id must be tenant-scoped so two tenants
    sharing a conversation_id do not share LangGraph checkpointer state.
    """
    return f"{tenant_id}:{conversation_id}"
