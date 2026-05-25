"""
ITDR API Endpoints
REST API to surface Identity Threat Detection & Response alerts.
Also hooks into auth login events via hooks called at login/role-change time.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from itdr_service import itdr_service
from integration_service import get_integration_service

router = APIRouter(prefix="/api/itdr", tags=["ITDR - Identity Threat Detection"])


@router.get("/alerts")
async def get_itdr_alerts(
    unack_only: bool = Query(default=False),
    limit: int = Query(default=100, le=500),
    current_user: TokenData = Depends(get_current_user)
):
    """Get ITDR threat alerts."""
    return await itdr_service.get_alerts(limit=limit, unack_only=unack_only)


@router.patch("/alerts/{alert_id}/acknowledge")
async def acknowledge_itdr_alert(
    alert_id: str,
    current_user: TokenData = Depends(get_current_user)
):
    """Acknowledge an ITDR alert."""
    success = await itdr_service.acknowledge_alert(alert_id, by=current_user.username)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "acknowledged", "alert_id": alert_id}


_ITDR_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}


@router.get("/summary")
async def get_itdr_summary(current_user: TokenData = Depends(get_current_user)):
    """Get ITDR summary stats."""
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    caller_role = getattr(current_user, "role", None)
    base = {} if caller_role in _ITDR_SUPER_ROLES else {"tenantId": tenant_id}

    by_type = {}
    pipeline = [
        {"$match": base},
        {"$group": {"_id": "$type", "count": {"$sum": 1}}},
    ]
    async for doc in db.itdr_alerts.aggregate(pipeline):
        by_type[doc["_id"]] = doc["count"]

    total = await db.itdr_alerts.count_documents(base)
    unack = await db.itdr_alerts.count_documents({**base, "acknowledged": False})
    critical = await db.itdr_alerts.count_documents({**base, "severity": "critical", "acknowledged": False})
    return {
        "total_alerts": total,
        "unacknowledged": unack,
        "critical_unacknowledged": critical,
        "by_type": by_type,
    }

class SuspendUserRequest(BaseModel):
    idp_provider: str  # 'okta' or 'entra'
    tenant_id: str

@router.post("/suspend-user/{user_email}")
async def suspend_user_in_idp(
    user_email: str,
    request: SuspendUserRequest,
    current_user: TokenData = Depends(get_current_user)
):
    """Suspend a user account directly in Okta or Entra ID based on ITDR alert."""
    db = get_database()
    integration_service = get_integration_service(db)
    
    # Get IDP config
    config = await integration_service._get_integration_config("idp", request.idp_provider)
    if not config:
        # Fallback to check if it's configured under 'sso'
        config = await integration_service._get_integration_config("sso", request.idp_provider)
    
    if not config:
        raise HTTPException(status_code=400, detail=f"Integration for {request.idp_provider} is not configured.")
        
    if request.idp_provider.lower() == "okta":
        result = await integration_service.suspend_okta_user(user_email, config)
    elif request.idp_provider.lower() in ["entra", "azure", "entra_id"]:
        result = await integration_service.suspend_entra_user(user_email, config)
    else:
        raise HTTPException(status_code=400, detail="Unsupported IDP provider.")
        
    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to suspend user")
        
    return {"status": "suspended", "user": user_email, "idp": request.idp_provider}
