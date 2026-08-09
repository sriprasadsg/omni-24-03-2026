"""Tenant-scoped retrieval tools for LangChain agents (39-05).

Wraps rag_service.query in an @tool, closing tenant_id server-side
so the model never holds a tenant parameter it could be injected into.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def make_search_evidence(tenant_id: str):
    """Return an @tool that searches tenant evidence via rag_service.

    tenant_id is closed over at factory time — NEVER passed as a tool
    argument the LLM fills in (AI-SPEC Pitfall 3).
    """
    from langchain.tools import tool

    @tool
    async def search_evidence(query: str) -> str:
        """Search the tenant's compliance evidence and shared standards KB.
        Input: a natural-language query string.
        Output: relevant evidence chunks with [source] and [id] tags, or
        a "No matching evidence found" message if nothing matches."""
        try:
            from rag_service import rag_service
            hits = await rag_service.query(query, n_results=5, tenant_id=tenant_id)
            if not hits:
                return "No matching evidence found."
            return "\n\n".join(
                f"[source: {h['source']} | id: {h['id']}]\n{h['content']}" for h in hits
            )
        except ImportError:
            logger.warning("rag_service not available; search_evidence degraded")
            return "Evidence search is temporarily unavailable."
        except Exception as exc:
            logger.error("search_evidence error for tenant=%s: %s", tenant_id, exc)
            return "No matching evidence found."

    return search_evidence
