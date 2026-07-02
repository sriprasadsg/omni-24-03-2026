"""Evidence Lifecycle endpoints — staleness settings and chain-of-custody reads.

Serves two URL spaces:
  - GET/PATCH /api/settings/evidence-staleness  (STALE-02)
  - GET /api/compliance/evidence/{evidence_id}/audit-log  (COC-02)
  - GET /api/compliance/controls/{control_id}/audit-log   (COC-02 control-level)
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from database import get_database
from authentication_service import get_current_user
from evidence_staleness import get_staleness_threshold
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Admin roles — copied verbatim from settings_endpoints.py (self-contained, do not import)
_SETTINGS_ADMIN_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin", "Tenant Admin"}

# Super roles — for CoC tenant-isolation gate
# Kept in sync with compliance_evidence_endpoints._SUPER_ROLES (WR-02): both
# files must treat the same set of roles as super/admin so a caller isn't
# granted a tenant bypass in one endpoint file but denied in the other.
_SUPER_ROLES = {"Super Admin", "superadmin", "super_admin", "admin", "platform-admin"}


def _require_admin(user) -> None:
    """Raise 403 if the caller does not have an admin role."""
    if getattr(user, "role", "") not in _SETTINGS_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required to modify settings")


class StalenessThresholdUpdate(BaseModel):
    thresholdDays: int = Field(ge=1, le=365)


# ---------------------------------------------------------------------------
# GET /api/settings/evidence-staleness
# ---------------------------------------------------------------------------

@router.get("/api/settings/evidence-staleness")
async def get_evidence_staleness(current_user=Depends(get_current_user)):
    """Return the current evidence staleness threshold for the caller's tenant.

    No admin gate — the threshold value is non-sensitive configuration.
    """
    try:
        tenant_id = getattr(current_user, "tenant_id", None)
        db = get_database()
        threshold = await get_staleness_threshold(db, tenant_id)
        return {"thresholdDays": threshold}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_evidence_staleness error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# PATCH /api/settings/evidence-staleness
# ---------------------------------------------------------------------------

@router.patch("/api/settings/evidence-staleness")
async def patch_evidence_staleness(
    body: StalenessThresholdUpdate,
    current_user=Depends(get_current_user),
):
    """Persist the evidence staleness threshold for this tenant. Admin-only.

    Pydantic validates thresholdDays in [1, 365]; out-of-range bodies return 422.
    """
    try:
        _require_admin(current_user)
        db = get_database()
        raw = db._db if hasattr(db, "_db") else db
        tenant_id = getattr(current_user, "tenant_id", None)

        doc = {"type": "evidence_staleness", "thresholdDays": body.thresholdDays}
        if tenant_id:
            doc["tenantId"] = tenant_id
            await raw.system_settings.update_one(
                {"type": "evidence_staleness", "tenantId": tenant_id},
                {"$set": doc},
                upsert=True,
            )
        else:
            await raw.system_settings.update_one(
                {"type": "evidence_staleness", "tenantId": {"$exists": False}},
                {"$set": doc},
                upsert=True,
            )

        return {"thresholdDays": body.thresholdDays}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("patch_evidence_staleness error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# GET /api/compliance/evidence/{evidence_id}/audit-log  (COC-02)
# ---------------------------------------------------------------------------

@router.get("/api/compliance/evidence/{evidence_id}/audit-log")
async def get_evidence_audit_log(
    evidence_id: str,
    current_user=Depends(get_current_user),
):
    """Return CoC entries for a single evidence item, scoped to the caller's tenant."""
    try:
        db = get_database()
        raw = db._db if hasattr(db, "_db") else db
        is_super = getattr(current_user, "role", "") in _SUPER_ROLES
        tenant_id = getattr(current_user, "tenant_id", None)

        query: dict = {"evidenceId": evidence_id}
        if not is_super:
            if not tenant_id:
                raise HTTPException(status_code=403, detail="Tenant context required")
            query["tenantId"] = tenant_id

        entries = await raw.evidence_audit_log.find(
            query, {"_id": 0}
        ).sort("timestamp", 1).to_list(length=500)

        return {"evidence_id": evidence_id, "entries": entries}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_evidence_audit_log error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# GET /api/compliance/controls/{control_id}/audit-log  (COC-02 control-level)
# ---------------------------------------------------------------------------

@router.get("/api/compliance/controls/{control_id}/audit-log")
async def get_control_audit_log(
    control_id: str,
    current_user=Depends(get_current_user),
):
    """Return CoC entries for all evidence belonging to a control, tenant-scoped."""
    try:
        db = get_database()
        raw = db._db if hasattr(db, "_db") else db
        is_super = getattr(current_user, "role", "") in _SUPER_ROLES
        tenant_id = getattr(current_user, "tenant_id", None)

        if not is_super and not tenant_id:
            raise HTTPException(status_code=403, detail="Tenant context required")

        # Collect evidence IDs belonging to this control from both collections.
        evidence_ids: list[str] = []

        # control_evidence collection (direct control uploads)
        ce_query: dict = {"controlId": control_id}
        if not is_super:
            ce_query["tenantId"] = tenant_id
        async for doc in raw.control_evidence.find(ce_query, {"id": 1, "_id": 0}):
            eid = doc.get("id")
            if eid:
                evidence_ids.append(eid)

        # asset_compliance collection (system-generated evidence array)
        ac_query: dict = {"controlId": control_id}
        if not is_super:
            ac_query["tenantId"] = tenant_id
        pipeline = [
            {"$match": ac_query},
            {"$unwind": "$evidence"},
            {"$project": {"evidence.id": 1, "_id": 0}},
            {"$limit": 500},
        ]
        async for doc in raw.asset_compliance.aggregate(pipeline):
            eid = doc.get("evidence", {}).get("id")
            if eid:
                evidence_ids.append(eid)

        if not evidence_ids:
            return {"control_id": control_id, "entries": []}

        query: dict = {"evidenceId": {"$in": evidence_ids}}
        if not is_super:
            query["tenantId"] = tenant_id

        entries = await raw.evidence_audit_log.find(
            query, {"_id": 0}
        ).sort("timestamp", 1).to_list(length=500)

        return {"control_id": control_id, "entries": entries}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_control_audit_log error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
