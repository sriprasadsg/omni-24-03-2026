"""AI multi-agent supervisor endpoint.

POST /api/assistant/route — classify a free-form request and dispatch it to the
right Phase-39 agent surface (chat / auditor / questionnaire / narrative),
degrading to chat when a structured surface lacks its required inputs.

Thin wrapper over `ai_orchestration.agents.supervisor.route_request`; the
routing, guardrails, fail-closed degrade, tracing, and decision logging all
live in that module. Mirrors ai_assistant_endpoints.py's auth/tenant shape.
"""
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends

from ai_orchestration.agents.supervisor import route_request
from ai_orchestration.models import MODELS_REVISION, describe_model_for_tenant
from rbac_service import rbac_service
from tenant_context import get_tenant_id
from auth_types import TokenData

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/assistant", tags=["AI Security Assistant"])

_DIAGNOSTIC_SURFACES = ["chat", "auditor", "questionnaire", "narrative", "supervisor"]


@router.get("/model-diagnostics")
async def model_diagnostics(
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> dict[str, Any]:
    """Report which provider/URL each AI surface resolves to — no model is
    invoked, only built and introspected. `revision` confirms the running code
    version (compare to ai_orchestration.models.MODELS_REVISION); a stale value
    means the backend was not restarted after a model-routing change."""
    from database import get_database

    tenant_id = get_tenant_id()
    db = get_database()
    surfaces: dict[str, Any] = {}
    for surface in _DIAGNOSTIC_SURFACES:
        try:
            surfaces[surface] = await describe_model_for_tenant(tenant_id, db, surface=surface)
        except Exception as exc:  # diagnostics must never 500
            surfaces[surface] = {"error": str(exc)}
    return {
        "revision": MODELS_REVISION,
        "anthropic_base_url_set": bool(os.getenv("ANTHROPIC_BASE_URL")),
        "router_url_set": bool(os.getenv("AI_ROUTER_URL")),
        "surfaces": surfaces,
    }


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
