import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

import rbac_defaults
from auth_types import TokenData
from authentication_service import get_current_user
from database import get_database
from rbac_service import RBACService, effective_permissions
from rbac_utils import is_super_admin, verify_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/roles", tags=["Role Management"])


class Role(BaseModel):
    id: str
    name: str
    description: str
    permissions: List[str]
    isEditable: bool
    tenantId: str


async def _require_role_list_access(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """D-16: the role catalogue is for people who manage users or RBAC.

    Super-admins pass through verify_permission's bypass.
    """
    if await verify_permission(current_user, "manage:users") or await verify_permission(current_user, "manage:rbac"):
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Missing required permission: manage:users or manage:rbac",
    )


@router.get("", response_model=List[Role])
async def list_roles(current_user: TokenData = Depends(_require_role_list_access)):
    """List the roles the caller can assign.

    D-15: every built-in role from the single table in ``rbac_defaults`` plus the
    role documents of the caller's own tenant (never another tenant's), each with
    permissions computed by ``rbac_service.effective_permissions``, the same
    resolver ``/api/auth/me`` uses. Super Admin is listed for super-admin callers
    only. D-16: requires manage:users or manage:rbac.
    """
    db = get_database()
    tenant_id = current_user.tenant_id
    caller_is_super = is_super_admin(current_user.role)
    roles: List[dict] = []
    try:
        for builtin in rbac_defaults.BUILTIN_ROLES:
            if builtin.key == rbac_defaults.SUPER_ADMIN_KEY and not caller_is_super:
                continue
            roles.append({
                "id": builtin.role_id,
                "name": builtin.name,
                "description": builtin.description,
                "permissions": await effective_permissions(db, builtin.name, tenant_id),
                "isEditable": builtin.is_editable,
                "tenantId": builtin.doc_tenant_id,
            })
        if tenant_id:
            builtin_keys = rbac_defaults.builtin_role_keys()
            docs = await db._db.roles.find({"tenantId": tenant_id}).to_list(500)
            for doc in docs:
                name = doc.get("name")
                if not name or RBACService._normalize_role(name) in builtin_keys:
                    continue
                roles.append({
                    "id": str(doc.get("id") or doc.get("_id")),
                    "name": name,
                    "description": doc.get("description") or "",
                    "permissions": await effective_permissions(db, name, tenant_id),
                    "isEditable": doc.get("isEditable", True),
                    "tenantId": tenant_id,
                })
    except Exception as exc:
        logger.error("Role list failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Role store unavailable")
    return roles
