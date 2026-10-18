import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

import rbac_defaults
import role_contents
from audit_service import get_audit_service
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
    builtIn: bool = False  # D-18: true for the table roles, false for tenant documents


class RoleCreate(BaseModel):
    """Body of POST /api/roles. Unknown fields (id, isEditable, builtIn ...) are refused (T-77-09)."""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=64)
    description: str = Field(default="", max_length=role_contents.MAX_DESCRIPTION)
    permissions: List[str] = Field(default_factory=list)
    tenantId: Optional[str] = None  # honoured for a Super Admin only


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


async def _require_role_write_access(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """D-02: creating, editing and deleting roles needs manage:rbac (Super Admin passes)."""
    if await verify_permission(current_user, "manage:rbac"):
        return current_user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing required permission: manage:rbac")


def _role_response(doc: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
    return {
        "id": str(doc.get("id") or doc.get("_id")),
        "name": doc["name"],
        "description": doc.get("description") or "",
        "permissions": sorted(doc.get("permissions") or []),
        "isEditable": doc.get("isEditable", True),
        "tenantId": tenant_id,
        "builtIn": False,
    }


async def _audit_role(action: str, actor: str, doc: Dict[str, Any], tenant_id: str,
                      previous_state: Optional[Dict[str, Any]] = None) -> None:
    """Hash-chained audit entry for a role change; a failure is logged, never raised (T-77-11)."""
    try:
        await get_audit_service().log_action_async(
            user_name=actor, action=action, resource_type="role", resource_id=str(doc.get("id")),
            details=f"{action}: {doc.get('name')}", previous_state=previous_state, tenant_id=tenant_id,
        )
    except Exception as exc:
        logger.error("Audit log write failed for %s: %s", action, exc)


def _store_unavailable(exc: Exception) -> HTTPException:
    logger.error("Role store failure: %s", exc)
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Role store unavailable")


@router.get("", response_model=List[Role])
async def list_roles(current_user: TokenData = Depends(_require_role_list_access)):
    """List the roles the caller can assign.

    D-15: every built-in role from the single table in ``rbac_defaults`` plus the
    role documents of the caller's own tenant (never another tenant's), each with
    permissions computed by ``rbac_service.effective_permissions``, the same
    resolver ``/api/auth/me`` uses. The platform roles (Super Admin, Platform Support,
    Platform Billing) are listed for super-admin callers only. D-16: requires
    manage:users or manage:rbac.
    """
    db = get_database()
    tenant_id = current_user.tenant_id
    caller_is_super = is_super_admin(current_user.role)
    roles: List[dict] = []
    try:
        for builtin in rbac_defaults.BUILTIN_ROLES:
            if builtin.key in rbac_defaults.PLATFORM_ROLE_KEYS and not caller_is_super:
                continue  # platform roles (spec C1) are listed and assignable by the owner only
            roles.append({
                "id": builtin.role_id,
                "name": builtin.name,
                "description": builtin.description,
                "permissions": await effective_permissions(db, builtin.name, tenant_id),
                "isEditable": builtin.is_editable,
                "tenantId": builtin.doc_tenant_id,
                "builtIn": True,
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
                    "builtIn": False,
                })
    except Exception as exc:
        logger.error("Role list failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Role store unavailable")
    return roles


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Role)
async def create_role(body: RoleCreate, current_user: TokenData = Depends(_require_role_write_access)):
    """D-01: create a custom role in the caller's tenant (a Super Admin names the tenant).

    Name rules D-18, permissions D-17, editor ceiling D-02. No unique index exists, so a
    duplicate name is refused by a check before the insert and a read-after-write check
    after it (the losing insert is removed and answers 409).
    """
    db = get_database()
    try:
        tenant_id = await role_contents.resolve_target_tenant(db, current_user, body.tenantId)
        docs = await role_contents.custom_role_docs(db, tenant_id)
        if len(docs) >= role_contents.MAX_CUSTOM_ROLES_PER_TENANT:
            raise HTTPException(status_code=400, detail="This tenant has reached the custom role limit.")
        name = role_contents.validate_role_name(body.name, docs)
        permissions = role_contents.validate_permissions(body.permissions)
        await role_contents.assert_can_edit_contents(db, current_user, [], permissions)
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "id": f"role-{uuid.uuid4()}", "name": name, "nameKey": rbac_defaults.normalize_role(name),
            "description": body.description, "permissions": permissions, "isEditable": True,
            "tenantId": tenant_id, "createdBy": current_user.username, "createdAt": now,
            "updatedBy": current_user.username, "updatedAt": now,
        }
        await db._db.roles.insert_one(dict(doc))
        same = [d for d in await role_contents.custom_role_docs(db, tenant_id)
                if rbac_defaults.normalize_role(d.get("name")) == doc["nameKey"]]
        if len(same) > 1:
            await db._db.roles.delete_one({"id": doc["id"], "tenantId": tenant_id})
            raise HTTPException(status_code=409, detail="A role with this name already exists.")
    except HTTPException:
        raise
    except Exception as exc:
        raise _store_unavailable(exc)
    await _audit_role("role.created", current_user.username or "", doc, tenant_id, previous_state={"permissions": []})
    return _role_response(doc, tenant_id)
