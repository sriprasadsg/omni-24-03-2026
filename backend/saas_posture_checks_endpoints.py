from fastapi import APIRouter, Depends, HTTPException
from database import get_db
from authentication_service import get_current_user
import saas_posture_checks_service as svc
import logging

router = APIRouter(prefix="/api/saas/posture-checks", tags=["SaaS Posture Checks"])
logger = logging.getLogger(__name__)

@router.post("/{connection_id}/run")
async def run_posture_checks(
    connection_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Trigger posture checks for a SaaS connection."""
    connection = await db.saas_connections.find_one({"id": connection_id})
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    # Tenant isolation — super_admin can run any connection
    role = getattr(current_user, "role", None)
    user_tenant = getattr(current_user, "tenant_id", None)
    if role not in ("super_admin", "platform_admin"):
        if connection.get("tenant_id") != user_tenant:
            raise HTTPException(status_code=403, detail="Access denied: cross-tenant access not allowed")

    result = await svc.saas_posture_checks_service.run_posture_checks(connection, db)
    return result

@router.get("/{connection_id}/results")
async def list_posture_results(
    connection_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_db),
):
    """List posture check results for a SaaS connection."""
    connection = await db.saas_connections.find_one({"id": connection_id})
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    # Tenant isolation
    role = getattr(current_user, "role", None)
    user_tenant = getattr(current_user, "tenant_id", None)
    if role not in ("super_admin", "platform_admin"):
        if connection.get("tenant_id") != user_tenant:
            raise HTTPException(status_code=403, detail="Access denied")

    # WR-03: results are stored under the connection's own tenant (see
    # saas_posture_checks_service.run_posture_checks), not the caller's —
    # a super_admin/platform_admin running checks against another tenant's
    # connection would otherwise never see the results it just wrote.
    results = await db.saas_check_results.find(
        {"tenantId": connection.get("tenant_id"), "connectionId": connection_id}, {"_id": 0}
    ).to_list(length=100)
    return {"items": results, "count": len(results)}
