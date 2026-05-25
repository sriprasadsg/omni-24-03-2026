from fastapi import APIRouter, Depends
from typing import List
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData

router = APIRouter(prefix="/api/cloud-accounts", tags=["Cloud Accounts"])

_SUPER_ADMIN_ROLES = {"Super Admin", "superadmin", "super_admin", "platform-admin"}

@router.get("")
async def get_cloud_accounts(current_user: TokenData = Depends(get_current_user)):
    """Get all cloud accounts scoped to the caller's tenant."""
    db = get_database()
    role = getattr(current_user, "role", "") or ""
    if role in _SUPER_ADMIN_ROLES:
        query: dict = {}
    else:
        tenant_id = getattr(current_user, "tenant_id", None)
        query = {"tenantId": tenant_id} if tenant_id else {"tenantId": {"$exists": False}}
    accounts = await db.cloud_accounts.find(query, {"_id": 0}).to_list(length=100)
    return accounts
