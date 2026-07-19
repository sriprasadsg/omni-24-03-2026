"""AI multi-agent supervisor endpoint.

POST /api/assistant/route — classify a free-form request and dispatch it to the
right Phase-39 agent surface (chat / auditor / questionnaire / narrative),
degrading to chat when a structured surface lacks its required inputs.

Thin wrapper over `ai_orchestration.agents.supervisor.route_request`; the
routing, guardrails, fail-closed degrade, tracing, and decision logging all
live in that module. Mirrors ai_assistant_endpoints.py's auth/tenant shape.
"""
import logging
from typing import Any

from fastapi import APIRouter, Depends

from ai_orchestration.agents.supervisor import route_request
from rbac_service import rbac_service
from tenant_context import get_tenant_id
from auth_types import TokenData

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/assistant", tags=["AI Security Assistant"])


@router.post("/route")
async def route_assistant_request(
    body: dict[str, Any],
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> dict[str, Any]:
    """Route a request to the best specialist agent surface.

    Body: {
        "query":   str,        # required — the natural-language request
        "history": [ ... ],    # optional — prior chat turns [{role, content}]
        "context": { ... },    # optional — structured data enabling an auditor/
                               #   narrative handoff (evidence_text, framework_name,
                               #   score, failing_controls, period, control_id, ...)
    }

    Returns {surface, routed_to, degraded, blocked, reason, result} where
    `result` is the invoked surface's own payload (e.g. {answer, sources} for
    chat).
    """
    query = (body.get("query") or "").strip()
    if not query:
        return {
            "surface": "chat", "routed_to": "chat", "degraded": False,
            "blocked": False, "reason": "no query provided",
            "result": {"answer": "No request provided.", "sources": []},
        }

    tenant_id = get_tenant_id()
    outcome = await route_request(
        query,
        tenant_id,
        history=body.get("history") or [],
        context=body.get("context") or {},
    )
    return {
        "surface": outcome.surface,
        "routed_to": outcome.routed_to,
        "degraded": outcome.degraded,
        "blocked": outcome.blocked,
        "reason": outcome.reason,
        "extracted": outcome.extracted,
        "result": outcome.result,
    }
