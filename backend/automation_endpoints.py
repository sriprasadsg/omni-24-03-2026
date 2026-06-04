import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel, Field
from typing import List, Optional
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData

router = APIRouter(prefix="/api/automation-policies", tags=["Automation"])

_AUTOMATION_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}
_AUTOMATION_MANAGE_ROLES = _AUTOMATION_SUPER_ROLES | {"Tenant Admin", "admin", "security_analyst"}

_VALID_TRIGGERS = {"agent.error", "alert.critical"}
_VALID_ACTIONS = {"remediate.agent", "create.case"}
_VALID_OPERATORS = {"contains", "equals"}


class PolicyCondition(BaseModel):
    field: str = Field(..., max_length=100)
    operator: str = Field(..., max_length=20)
    value: str = Field(..., max_length=500)


class AutomationPolicyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=1000)
    trigger: str = Field(..., max_length=50)
    action: str = Field(..., max_length=50)
    conditions: List[PolicyCondition] = Field(default_factory=list)
    isEnabled: bool = True


class AutomationPolicyUpdate(AutomationPolicyCreate):
    id: str = Field(..., max_length=100)


def _get_tenant(current_user: TokenData) -> Optional[str]:
    return getattr(current_user, "tenant_id", None)


def _validate_policy(data: AutomationPolicyCreate) -> None:
    if data.trigger not in _VALID_TRIGGERS:
        raise HTTPException(status_code=400, detail=f"Invalid trigger. Must be one of: {_VALID_TRIGGERS}")
    if data.action not in _VALID_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid action. Must be one of: {_VALID_ACTIONS}")
    for cond in data.conditions:
        if cond.operator not in _VALID_OPERATORS:
            raise HTTPException(status_code=400, detail=f"Invalid operator '{cond.operator}'")


@router.get("")
async def get_automation_policies(current_user: TokenData = Depends(get_current_user)):
    """Get automation policies scoped to caller's tenant."""
    db = get_database()
    caller_role = getattr(current_user, "role", "")
    caller_tenant = _get_tenant(current_user)
    query: dict = {} if caller_role in _AUTOMATION_SUPER_ROLES else {"tenantId": caller_tenant}
    policies = await db.automation_policies.find(query, {"_id": 0}).to_list(length=100)
    return policies


@router.post("")
async def create_automation_policy(
    data: AutomationPolicyCreate = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    """Create a new automation policy. Requires manage:automation permission."""
    caller_role = getattr(current_user, "role", "")
    if caller_role not in _AUTOMATION_MANAGE_ROLES:
        raise HTTPException(status_code=403, detail="Insufficient permissions to create automation policies")
    _validate_policy(data)
    db = get_database()
    tenant_id = _get_tenant(current_user)
    policy = {
        "id": str(uuid.uuid4()),
        "tenantId": tenant_id,
        "name": data.name,
        "description": data.description,
        "trigger": data.trigger,
        "action": data.action,
        "conditions": [c.model_dump() for c in data.conditions],
        "isEnabled": data.isEnabled,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "createdBy": getattr(current_user, "email", str(current_user)),
    }
    await db.automation_policies.insert_one(policy)
    policy.pop("_id", None)
    return policy


@router.put("")
async def update_automation_policy(
    data: AutomationPolicyUpdate = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    """Update an existing automation policy (including toggle isEnabled)."""
    caller_role = getattr(current_user, "role", "")
    if caller_role not in _AUTOMATION_MANAGE_ROLES:
        raise HTTPException(status_code=403, detail="Insufficient permissions to update automation policies")
    _validate_policy(data)
    db = get_database()
    caller_tenant = _get_tenant(current_user)

    # Tenant isolation: non-super-admins can only update their own tenant's policies
    existing = await db.automation_policies.find_one({"id": data.id}, {"_id": 0, "tenantId": 1})
    if not existing:
        raise HTTPException(status_code=404, detail="Policy not found")
    if caller_role not in _AUTOMATION_SUPER_ROLES:
        if existing.get("tenantId") != caller_tenant:
            raise HTTPException(status_code=403, detail="Not authorized to update this policy")

    update_fields = {
        "name": data.name,
        "description": data.description,
        "trigger": data.trigger,
        "action": data.action,
        "conditions": [c.model_dump() for c in data.conditions],
        "isEnabled": data.isEnabled,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "updatedBy": getattr(current_user, "email", str(current_user)),
    }
    await db.automation_policies.update_one({"id": data.id}, {"$set": update_fields})
    updated = await db.automation_policies.find_one({"id": data.id}, {"_id": 0})
    return updated
