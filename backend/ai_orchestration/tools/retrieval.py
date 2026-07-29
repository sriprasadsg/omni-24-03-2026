"""Phase 39-05 — Tenant-closed retrieval tool.

`make_search_evidence(tenant_id, n_results=5)` returns a LangChain
`@tool`-decorated function that wraps `rag_service.query(...)` unchanged
(never rewrapped — no alternate LangChain vectorstore integration is used
here, RESEARCH.md Pattern 2) with `tenant_id` closed over from the factory
argument. `tenant_id` is NEVER a tool parameter and this module never reads
the acting tenant from ambient request-scoped context inside the tool body
(RESEARCH.md Pitfall B) — the returned tool's only model-facing argument is
`query`.

Preserves both isolation layers `ai_assistant_service.chat()` already uses:
- the server-side `$or` filter inside `rag_service.query` itself
- the client-side belt-and-braces skip of any chunk whose `tenantId` is
  neither the acting tenant nor `"global"` (defense-in-depth against
  untagged/legacy chunks)
"""
from langchain_core.tools import tool

from rag_service import rag_service

NO_EVIDENCE_FOUND = "No matching evidence found."


def make_search_evidence(tenant_id: str, n_results: int = 5):
    """Build a tenant-closed `search_evidence` @tool bound to `tenant_id`.

    `tenant_id` is captured in this factory's closure only — the returned
    tool exposes just `query` to the model, so a prompt-injected document
    cannot redirect retrieval to another tenant.
    """

    @tool
    def search_evidence(query: str) -> str:
        """Search the tenant's compliance evidence and shared standards knowledge base.

        Returns evidence chunks tagged "[source: <source> | id: <id>]" so the
        model can cite them, or an explicit "no evidence" message when
        nothing relevant is found.
        """
        hits = rag_service.query(query, n_results=n_results, tenant_id=tenant_id)
        if not hits:
            return NO_EVIDENCE_FOUND

        blocks = []
        for item in hits:
            src_tenant = item.get("tenantId") or item.get("metadata", {}).get("tenantId", "")
            # Defense-in-depth: skip anything not belonging to this tenant or
            # "global" (mirrors ai_assistant_service.chat()'s client-side filter).
            if src_tenant and src_tenant not in (tenant_id, "global"):
                continue
            content = item.get("content") or ""
            source = item.get("source") or item.get("metadata", {}).get("source", "unknown")
            chunk_id = item.get("id", "")
            blocks.append(f"[source: {source} | id: {chunk_id}]\n{content}")

        if not blocks:
            return NO_EVIDENCE_FOUND
        return "\n\n".join(blocks)

    return search_evidence
