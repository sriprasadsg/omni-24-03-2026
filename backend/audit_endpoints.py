import csv
import io
import re
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import audit_ledger
from audit_service import get_audit_service
from auth_types import TokenData
from database import mongodb
from rbac_utils import can_read_all_tenants, is_super_admin, require_permission
from tenant_context import get_tenant_id

router = APIRouter(
    prefix="/api/audit-logs",
    tags=["Audit & Rollback"]
)

MAX_EXPORT_ROWS = 50_000
_CSV_FIELDS = ("timestamp", "seq", "tenantId", "action", "outcome", "statusCode", "catalogue", "resourceId",
               "actor.email", "actor.role", "ip", "durationMs", "bodyKeys", "requestId", "hash")


def _scope(current_user: TokenData, tenant_id_param: Optional[str]) -> Dict[str, Any]:
    """Tenant users see their own tenant only, whatever tenantId they pass; platform staff
    see all tenants or the one they name (spec C5, C1)."""
    if can_read_all_tenants(current_user):
        ambient = get_tenant_id()
        tenant = tenant_id_param or (None if ambient == "platform-admin" else ambient)
        return {"tenant_id": tenant, "is_super_admin": True}
    return {"tenant_id": get_tenant_id() or getattr(current_user, "tenant_id", None), "is_super_admin": False}


def _filters(actor: Optional[str], action: Optional[str], outcome: Optional[str], catalogue: Optional[str],
             since: Optional[datetime], until: Optional[datetime]) -> Dict[str, Any]:
    f: Dict[str, Any] = {}
    if actor:
        rx = {"$regex": re.escape(actor), "$options": "i"}
        f["$or"] = [{"actor.email": rx}, {"actor.userId": rx}, {"userName": rx}]
    if action:
        f["action"] = {"$regex": re.escape(action), "$options": "i"}
    if outcome:
        f["outcome"] = outcome
    if catalogue:
        f["catalogue"] = catalogue
    if since or until:
        f["timestamp"] = {**({"$gte": since.isoformat()} if since else {}), **({"$lte": until.isoformat()} if until else {})}
    return f


@router.get("", response_model=List[Dict[str, Any]])
async def get_audit_logs(
    limit: int = Query(100, le=1000),
    skip: int = Query(0, ge=0),
    resourceType: Optional[str] = Query(None),
    resourceId: Optional[str] = Query(None),
    actor: Optional[str] = Query(None, max_length=200),
    action: Optional[str] = Query(None, max_length=200),
    outcome: Optional[Literal["success", "denied", "error"]] = None,
    catalogue: Optional[str] = Query(None, max_length=80),
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = None,
    tenantId: Optional[str] = Query(None, max_length=100),
    current_user: TokenData = Depends(require_permission("view:audit_log"))
):
    """Audit entries, newest first. resourceType / resourceId / actor / action / outcome /
    catalogue / from / to narrow the result; they never widen the tenant scope."""
    return await get_audit_service().get_logs(
        **_scope(current_user, tenantId), resource_type=resourceType, resource_id=resourceId,
        limit=limit, skip=skip, filters=_filters(actor, action, outcome, catalogue, from_, to))


def _cell(entry: Dict[str, Any], field: str) -> str:
    value: Any = entry
    for part in field.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    if isinstance(value, list):
        return ";".join(map(str, value))
    return "" if value is None else str(value)


@router.get("/export.csv")
async def export_audit_logs(
    request: Request,
    actor: Optional[str] = Query(None, max_length=200),
    action: Optional[str] = Query(None, max_length=200),
    outcome: Optional[Literal["success", "denied", "error"]] = None,
    catalogue: Optional[str] = Query(None, max_length=80),
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = None,
    tenantId: Optional[str] = Query(None, max_length=100),
    current_user: TokenData = Depends(require_permission("view:audit_log")),
):
    """The same filters as the list, as CSV (at most 50,000 rows). The export is audited."""
    scope = _scope(current_user, tenantId)
    rows = await get_audit_service().get_logs(**scope, limit=MAX_EXPORT_ROWS,
                                              filters=_filters(actor, action, outcome, catalogue, from_, to))
    await audit_ledger.event(
        "export.audit_log", scope["tenant_id"] or "platform-admin",
        actor={"email": current_user.username, "role": current_user.role, "tenantId": current_user.tenant_id},
        ip=request.client.host if request.client else None, rows=len(rows),
        filters={k: v for k, v in {"actor": actor, "action": action, "outcome": outcome, "catalogue": catalogue,
                                   "from": from_ and from_.isoformat(), "to": to and to.isoformat(),
                                   "tenantId": scope["tenant_id"]}.items() if v})
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(_CSV_FIELDS)
    for entry in rows:
        writer.writerow([_cell(entry, f) for f in _CSV_FIELDS])
    headers = {"Content-Disposition": 'attachment; filename="audit-log.csv"'}
    if len(rows) >= MAX_EXPORT_ROWS:
        headers["X-Export-Truncated"] = "true"
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv", headers=headers)


class RetentionUpdate(BaseModel):
    tenantId: str = Field(..., max_length=100)
    days: int = Field(..., ge=30, le=3650)


@router.put("/retention")
async def set_retention(body: RetentionUpdate, current_user: TokenData = Depends(require_permission("view:audit_log"))):
    """Days of audit history kept for a tenant (default 365). Platform Owner only (spec C1)."""
    if not is_super_admin(getattr(current_user, "role", "")):
        raise HTTPException(status_code=403, detail="Only the Platform Owner can change audit retention")
    res = await mongodb.db.tenants.update_one({"id": body.tenantId}, {"$set": {"auditRetentionDays": body.days}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"tenantId": body.tenantId, "auditRetentionDays": body.days}


@router.post("/{log_id}/rollback")
async def rollback_action(
    log_id: str,
    current_user: TokenData = Depends(require_permission("manage:settings"))
):
    """Trigger a rollback for a specific action (if supported)."""
    try:
        result = await get_audit_service().rollback(log_id, current_user=current_user.username,
                                                    tenant_id=get_tenant_id())
        return {"success": True, "restored_state": result}
    except Exception:
        raise HTTPException(status_code=400, detail="Bad request")


@router.post("/integrity-check")
async def verify_integrity(
    current_user: TokenData = Depends(require_permission("view:audit_log"))
):
    """Verify the cryptographic integrity of the caller's tenant's audit chain."""
    return await get_audit_service().verify_integrity(get_tenant_id())
