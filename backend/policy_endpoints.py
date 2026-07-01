"""
Automation Policy endpoints — CRUD for tenant automation/remediation policies.
Used by PolicyManager.tsx frontend component.
"""

from fastapi import APIRouter, HTTPException, Depends, Body
from typing import Dict, Any
from datetime import datetime, timezone
import uuid

from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from tenant_context import get_tenant_id
from rbac_service import rbac_service

router = APIRouter(prefix="/api/policies", tags=["Automation Policies"])


_POLICY_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}


@router.get("")
async def list_policies(
    _current_user: TokenData = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id),
):
    """List all automation policies for the current tenant."""
    db = get_database()
    user_role = getattr(_current_user, "role", "")
    effective_tenant = None if user_role in _POLICY_SUPER_ROLES else tenant_id
    query: dict = {} if effective_tenant is None else {"tenant_id": effective_tenant}
    cursor = db.automation_policies.find(query, {"_id": 0}).sort("priority", 1).limit(200)
    policies = await cursor.to_list(length=200)
    return {"policies": policies, "count": len(policies)}


@router.post("")
async def create_policy(
    data: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(rbac_service.has_permission("manage:automation")),
    tenant_id: str = Depends(get_tenant_id),
):
    """Create a new automation policy."""
    name = data.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Policy name is required")

    db = get_database()
    policy_id = f"pol-{uuid.uuid4().hex[:10]}"
    policy = {
        "id": policy_id,
        "name": name,
        "tenant_id": tenant_id,
        "conditions": data.get("conditions", {}),
        "actions": data.get("actions", []),
        "enabled": data.get("enabled", True),
        "priority": int(data.get("priority", 0)),
        "execution_count": 0,
        "last_executed": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": getattr(current_user, "username", "system"),
    }
    await db.automation_policies.insert_one(policy)
    policy.pop("_id", None)
    return {"success": True, "policy": policy}


@router.put("/{policy_id}")
async def update_policy(
    policy_id: str,
    data: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(rbac_service.has_permission("manage:automation")),
    tenant_id: str = Depends(get_tenant_id),
):
    """Update an existing automation policy (supports partial updates)."""
    db = get_database()
    allowed_fields = {"name", "conditions", "actions", "enabled", "priority"}
    update = {k: v for k, v in data.items() if k in allowed_fields}
    if not update:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.automation_policies.update_one(
        {"id": policy_id, "tenant_id": tenant_id},
        {"$set": update},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Policy not found")
    return {"success": True}


@router.delete("/{policy_id}")
async def delete_policy(
    policy_id: str,
    current_user: TokenData = Depends(rbac_service.has_permission("manage:automation")),
    tenant_id: str = Depends(get_tenant_id),
):
    """Delete an automation policy."""
    db = get_database()
    result = await db.automation_policies.delete_one({"id": policy_id, "tenant_id": tenant_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Policy not found")
    return {"success": True}
