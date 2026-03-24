from fastapi import APIRouter, HTTPException, Depends, Body
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from database import get_database
from notification_service import get_notification_service

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])

from authentication_service import get_current_user
from auth_types import TokenData
from tenant_context import get_tenant_id
from rbac_service import rbac_service

@router.get("")
async def get_notifications(current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")), limit: int = 50):
    """Get recent notifications for a tenant"""
    db = get_database()
    tenant_id = get_tenant_id()
    notifications = await db.notifications.find(
        {"tenantId": tenant_id},
        {"_id": 0}
    ).sort("sent_at", -1).to_list(length=limit)
    return notifications

@router.put("/{notification_id}/read")
async def mark_as_read(notification_id: str, current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))):
    """Mark a notification as read"""
    db = get_database()
    tenant_id = get_tenant_id()
    result = await db.notifications.update_one(
        {"alert_id": notification_id, "tenantId": tenant_id},
        {"$set": {"read": True, "read_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"success": True}

@router.put("/read-all")
async def mark_all_as_read(
    notification_ids: Optional[List[str]] = Body(default=None),
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))
):
    """Mark all (or specific) notifications as read"""
    db = get_database()
    tenant_id = get_tenant_id()
    
    if notification_ids:
        query = {"alert_id": {"$in": notification_ids}, "tenantId": tenant_id}
    else:
        # Mark ALL notifications for tenant as read
        query = {"tenantId": tenant_id}
        
    result = await db.notifications.update_many(
        query,
        {"$set": {"read": True, "read_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"success": True, "modified_count": result.modified_count}

@router.delete("/{notification_id}")
async def delete_notification(notification_id: str, current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))):
    """Delete a notification"""
    db = get_database()
    tenant_id = get_tenant_id()
    result = await db.notifications.delete_one({"alert_id": notification_id, "tenantId": tenant_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"success": True}

@router.get("/config")
async def get_notification_config(current_user: TokenData = Depends(rbac_service.has_permission("manage:settings"))):
    """Get notification configuration (Slack, etc.)"""
    db = get_database()
    tenant_id = get_tenant_id()
    configs = await db.notification_config.find(
        {"tenantId": tenant_id},
        {"_id": 0}
    ).to_list(length=100)
    return configs

@router.post("/config")
async def update_notification_config(config: Dict[str, Any] = Body(...), current_user: TokenData = Depends(rbac_service.has_permission("manage:settings"))):
    """Update notification configuration"""
    db = get_database()
    tenant_id = get_tenant_id()
    config_type = config.get("type")
    
    if not config_type:
        raise HTTPException(status_code=400, detail="Config type is required")
        
    await db.notification_config.update_one(
        {"tenantId": tenant_id, "type": config_type},
        {"$set": {**config, "tenantId": tenant_id, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )
    return {"success": True}
