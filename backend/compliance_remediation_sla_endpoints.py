"""Remediation SLA endpoints — escalation history read + at-risk-window settings.

Serves two URL spaces:
  - GET /api/compliance/remediation-tasks/{task_id}/escalations  (SLA-02)
  - GET/PATCH /api/settings/remediation-sla  (D-02)

No PATCH/DELETE/PUT route exists for the escalations resource. That absence
is SLA-02's immutability enforcement — the remediation_escalations
collection is append-only, written exclusively by
compliance_remediation_sla_service.run_sla_pass (44-02).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from database import get_database
from authentication_service import get_current_user
from compliance_remediation_sla_service import get_sla_at_risk_window
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Admin roles for settings-mutation gating — this file's own convention
# (cloned from compliance_evidence_lifecycle_endpoints._SETTINGS_ADMIN_ROLES),
# not notification_manager.py's _ADMIN_ROLES set (that set is reserved for
# escalation notification recipients, a different purpose).
_SETTINGS_ADMIN_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin", "Tenant Admin"}


def _require_admin(user) -> None:
    """Raise 403 if the caller does not have an admin role."""
    if getattr(user, "role", "") not in _SETTINGS_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required to modify settings")


class SlaWindowUpdate(BaseModel):
    windowDays: int = Field(ge=1, le=365)


# ---------------------------------------------------------------------------
# GET /api/compliance/remediation-tasks/{task_id}/escalations  (SLA-02)
# ---------------------------------------------------------------------------

@router.get("/api/compliance/remediation-tasks/{task_id}/escalations")
async def get_remediation_escalations(
    task_id: str,
    current_user=Depends(get_current_user),
):
    """Return the append-only escalation history for a remediation task.

    Tenant-scoped: the read query is always AND'd with tenantId when present
    (T-44-06) — never rely solely on the sweep's write-time tenant
    correctness. No PATCH/DELETE/PUT route is defined for this resource
    anywhere; that omission is the immutability enforcement (SLA-02).
    """
    try:
        db = get_database()
        raw = db._db if hasattr(db, "_db") else db
        tenant_id = getattr(current_user, "tenant_id", None)

        query: dict = {"task_id": task_id}
        if tenant_id:
            query["tenantId"] = tenant_id

        entries = await raw.remediation_escalations.find(
            query, {"_id": 0}
        ).sort("created_at", 1).to_list(length=500)

        # Belt-and-braces (T-44-06): re-check tenantId in application code too,
        # never trusting the query filter alone to have been honored.
        if tenant_id:
            entries = [e for e in entries if e.get("tenantId") == tenant_id]

        return {"task_id": task_id, "entries": entries}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_remediation_escalations error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# GET /api/settings/remediation-sla  (D-02)
# ---------------------------------------------------------------------------

@router.get("/api/settings/remediation-sla")
async def get_remediation_sla_settings(current_user=Depends(get_current_user)):
    """Return the current remediation SLA at-risk window for the caller's
    tenant. No admin gate — the window value is non-sensitive configuration.
    """
    try:
        tenant_id = getattr(current_user, "tenant_id", None)
        db = get_database()
        window = await get_sla_at_risk_window(db, tenant_id)
        return {"windowDays": window}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_remediation_sla_settings error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# PATCH /api/settings/remediation-sla  (D-02)
# ---------------------------------------------------------------------------

@router.patch("/api/settings/remediation-sla")
async def patch_remediation_sla_settings(
    body: SlaWindowUpdate,
    current_user=Depends(get_current_user),
):
    """Persist the remediation SLA at-risk window for this tenant. Admin-only.

    Pydantic validates windowDays in [1, 365]; out-of-range bodies return 422.
    """
    try:
        _require_admin(current_user)
        db = get_database()
        raw = db._db if hasattr(db, "_db") else db
        tenant_id = getattr(current_user, "tenant_id", None)

        doc = {"type": "remediation_sla_at_risk", "windowDays": body.windowDays}
        if tenant_id:
            doc["tenantId"] = tenant_id
            await raw.system_settings.update_one(
                {"type": "remediation_sla_at_risk", "tenantId": tenant_id},
                {"$set": doc},
                upsert=True,
            )
        else:
            await raw.system_settings.update_one(
                {"type": "remediation_sla_at_risk", "tenantId": {"$exists": False}},
                {"$set": doc},
                upsert=True,
            )

        return {"windowDays": body.windowDays}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("patch_remediation_sla_settings error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
