from fastapi import APIRouter, Depends
from typing import List
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData

router = APIRouter(prefix="/api/automation-policies", tags=["Automation"])

_AUTOMATION_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}


@router.get("")
async def get_automation_policies(current_user: TokenData = Depends(get_current_user)):
    """Get automation policies"""
    db = get_database()
    caller_role = getattr(current_user, "role", "")
    caller_tenant = getattr(current_user, "tenant_id", None)
    query: dict = {} if caller_role in _AUTOMATION_SUPER_ROLES else {"tenantId": caller_tenant}
    policies = await db.automation_policies.find(query, {"_id": 0}).to_list(length=100)
    return policies
