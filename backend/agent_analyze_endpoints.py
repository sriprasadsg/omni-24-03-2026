"""Incident impact analysis — POST /api/agent/analyze.

Backs the Incident Impact dashboard's "Analyze with Agentic AI" action. Fetches
the target alert or case, asks the AI service for a blast-radius summary, and
returns the structured assessment the UI renders. Degrades to a deterministic
summary when no AI provider is configured, so the endpoint never hard-fails.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from authentication_service import get_current_user
from auth_types import TokenData
from database import get_database

router = APIRouter(prefix="/api/agent", tags=["Agentic AI"])

_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin", "admin"}


class AnalyzeRequest(BaseModel):
    type: str  # 'alert' | 'case'
    id: str


def _scoped_filter(current_user: TokenData, entity_id: str) -> dict:
    filt = {"id": entity_id}
    if getattr(current_user, "role", "") not in _SUPER_ROLES:
        filt["tenantId"] = getattr(current_user, "tenant_id", None)
    return filt


@router.post("/analyze")
async def analyze_incident(
    body: AnalyzeRequest,
    current_user: TokenData = Depends(get_current_user),
):
    if body.type not in ("alert", "case"):
        raise HTTPException(status_code=422, detail="type must be 'alert' or 'case'")

    db = get_database()
    collection = "security_cases" if body.type == "case" else "alerts"
    entity = await db[collection].find_one(_scoped_filter(current_user, body.id), {"_id": 0})
    if not entity:
        raise HTTPException(status_code=404, detail=f"{body.type.capitalize()} not found")

    title = entity.get("title") or entity.get("message") or entity.get("description") or body.id
    severity = (entity.get("severity") or "medium").lower()
    description = entity.get("description") or entity.get("message") or ""

    prompt = (
        f"You are a SOC analyst. Summarize the blast radius and business impact of this "
        f"security {body.type} in 2-3 sentences. Title: {title}. Severity: {severity}. "
        f"Details: {description}."
    )

    summary: Optional[str] = None
    try:
        from ai_service import ai_service
        if getattr(ai_service, "is_configured", False):
            summary = await ai_service.generate_text(prompt, source="incident_analysis")
    except Exception:
        summary = None
    if not summary:
        summary = (
            f"{severity.capitalize()}-severity {body.type} '{title}'. "
            "Automated impact assessment (AI provider not configured): review the affected "
            "asset and related events to scope the blast radius."
        )

    mitigation = [
        "Isolate or restrict the affected asset(s) pending triage.",
        "Rotate any credentials or tokens exposed by this event.",
        "Correlate with related events on the same asset over the last 24 hours.",
        "Escalate to incident response if lateral movement or exfiltration is suspected.",
    ]
    if severity in ("critical", "high"):
        mitigation.insert(0, "Open an incident record and page the on-call responder immediately.")

    return {
        "severityAssessment": f"{severity.capitalize()} Severity",
        "summary": summary,
        "rootCauseAnalysis": (
            f"Derived from the {body.type}'s recorded signals: {description or 'no detailed description available'}."
        ),
        "mitigationSteps": mitigation,
    }
