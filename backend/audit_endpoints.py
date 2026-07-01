from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Dict, Any
from audit_service import get_audit_service
from auth_types import TokenData
from tenant_context import get_tenant_id
from rbac_utils import require_permission

router = APIRouter(
    prefix="/api/audit-logs",
    tags=["Audit & Rollback"]
)

_SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}


@router.get("", response_model=List[Dict[str, Any]])
async def get_audit_logs(
    limit: int = Query(100, le=1000),
    skip: int = Query(0, ge=0),
    current_user: TokenData = Depends(require_permission("view:audit_log"))
):
    """
    Fetch system audit logs for the timeline view.
    """
    tenant_id = get_tenant_id()
    is_super_admin = getattr(current_user, "role", "") in _SUPER_ROLES
    return await get_audit_service().get_logs(tenant_id=tenant_id, is_super_admin=is_super_admin)

@router.post("/{log_id}/rollback")
async def rollback_action(
    log_id: str,
    current_user: TokenData = Depends(require_permission("manage:settings"))
):
    """
    Trigger a rollback for a specific action (if supported).
    """
    try:
        tenant_id = get_tenant_id()
        result = await get_audit_service().rollback(
            log_id, 
            current_user=current_user.username,
            tenant_id=tenant_id
        )
        return {"success": True, "restored_state": result}

    except Exception:
        raise HTTPException(status_code=400, detail="Bad request")

@router.post("/integrity-check")
async def verify_integrity(
    current_user: TokenData = Depends(require_permission("view:audit_log"))
):
    """
    Verify the cryptographic integrity of the audit chain.
    """
    tenant_id = get_tenant_id()
    report = await get_audit_service().verify_integrity(tenant_id)
    return report
