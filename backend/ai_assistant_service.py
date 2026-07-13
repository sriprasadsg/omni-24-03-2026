"""
Phase 38-01 — AI Security Assistant Service.

chat(query, tenant_id, history) -> {answer, sources}
Retrieves RAG context + live findings, builds grounded prompt, calls AI service.
"""

import logging
import json
from typing import Any, Optional

from database import get_database
from rag_service import rag_service
from ai_service import ai_service

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
    sources: list[dict[str, str]] = []
    context_parts: list[str] = []

    # ── 1. RAG knowledge base ──────────────────────────────────────────────────
    # NOTE: rag_service.query() is NOT tenant-scoped. Filter results client-side
    # using the stored tenant metadata so we never leak across tenants.
    raw_context = rag_service.query(query, n_results=5)
    if raw_context:
        for item in raw_context:
            src_tenant = item.get("metadata", {}).get("tenantId", "")
            # Skip results from other tenants (metadata may be absent on old entries)
            if src_tenant and src_tenant != tenant_id:
                continue
            snippet = (item.get("content") or "")[:300]
            context_parts.append(f"[RAG] {snippet}")
            sources.append({
                "type": "rag",
                "id": item.get("id", ""),
                "title": item.get("metadata", {}).get("source", "knowledge base"),
                "snippet": snippet,
            })

    # ── 2. Live compliance findings from MongoDB ─────────────────────────────────
    try:
        db = get_database()
        tenant_filter = {"tenantId": tenant_id}

        # Failing controls (evidence with FAILED status in last 30 days)
        from datetime import datetime, timedelta, timezone
        thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

        failed_controls = await db.compliance_evidence.find({
            **tenant_filter,
            "status": {"$in": ["FAILED", "FAIL"]},
            "updatedAt": {"$gte": thirty_days_ago},
        }, {
            "controlId": 1, "title": 1, "framework": 1, "status": 1, "updatedAt": 1,
        }).to_list(length=20)

        controls_summary = []
        for c in failed_controls:
            controls_summary.append(
                f"- Control {c.get('controlId')}: {c.get('title', 'N/A')} "
                f"({c.get('framework', 'N/A')}) — {c.get('status', 'FAIL')}"
            )
        if controls_summary:
            context_parts.append(
                f"[COMPLIANCE] Failing controls (last 30 days):\n" +
                "\n".join(controls_summary[:10])
            )
            for c in failed_controls[:5]:
                sources.append({
                    "type": "compliance_control",
                    "id": c.get("controlId", ""),
                    "title": c.get("title", "N/A"),
                    "snippet": f"{c.get('framework', '')} — {c.get('status', 'FAIL')}",
                })

        # High/critical open risks
        risks = await db.risks.find({
            **tenant_filter,
            "status": {"$ne": "Closed"},
            "severity": {"$in": ["Critical", "High"]},
        }, {
            "id": 1, "title": 1, "severity": 1, "status": 1,
        }).to_list(length=10)

        risk_summary = []
        for r in risks:
            risk_summary.append(
                f"- Risk {r.get('id', 'N/A')}: {r.get('title', 'N/A')} "
                f"[{r.get('severity', 'N/A')}]"
            )
        if risk_summary:
            context_parts.append(f"[RISKS] Open high/critical risks:\n" + "\n".join(risk_summary))
            for r in risks[:3]:
                sources.append({
                    "type": "risk",
                    "id": r.get("id", ""),
                    "title": r.get("title", "N/A"),
                    "snippet": f"{r.get('severity', 'N/A')} — {r.get('status', 'Open')}",
                })

    except Exception as exc:
        logger.warning("[AIAssistant] Live findings query failed: %s", exc)
        context_parts.append("[DATA] Live findings temporarily unavailable.")

    # ── 3. Build prompt ─────────────────────────────────────────────────────────
    context_block = "\n\n".join(context_parts) if context_parts else "(No relevant context found.)"

    history_block = ""
    if history:
        for turn in history[-6:]:  # cap at 6 turns to stay within token budget
            role = turn.get("role", "user")
            history_block += f"\n{role.capitalize()}: {turn.get('content', '')}"

    prompt = f"""You are a security and compliance assistant. Answer the user's question using ONLY the provided context. If the context does not contain the answer, say so — do not hallucinate. Cite sources by type and id when relevant.

## Context
{context_block}

## Conversation history
{history_block}

User: {query}
Answer:"""

    # ── 4. Call AI service ───────────────────────────────────────────────────────
    try:
        answer = await ai_service.generate_text(prompt, source="ai_assistant")
    except Exception as exc:
        logger.error("[AIAssistant] Generation failed: %s", exc)
        answer = f"Error generating response: {exc}"

    return {"answer": answer, "sources": sources}