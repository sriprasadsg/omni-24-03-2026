import contextlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

import rbac_defaults
import role_contents
import role_visibility
import tenant_features
from audit_service import get_audit_service
from auth_types import TokenData
from authentication_service import get_current_user, invalidate_mfa_role_cache
from database import get_database
from rbac_service import effective_permissions
from rbac_utils import is_super_admin, verify_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/roles", tags=["Role Management"])

RENAME_REFUSED = "A role's name can't be changed. To rename, create a new role and reassign its users."


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


class RoleUpdate(BaseModel):
    """Body of PUT /api/roles/{id}. The name is fixed after creation (D-13); it may be echoed back."""
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    description: Optional[str] = Field(default=None, max_length=role_contents.MAX_DESCRIPTION)
    permissions: Optional[List[str]] = None


@router.get("", response_model=List[Role])
async def list_roles(tenantId: Optional[str] = None,
                     current_user: TokenData = Depends(_require_role_list_access)):
    """List the roles the caller can assign.

    D-15: every built-in role from the single table in ``rbac_defaults`` plus the
    role documents of the caller's own tenant (never another tenant's), each with
    permissions computed by ``rbac_service.effective_permissions``, the same
    resolver ``/api/auth/me`` uses. The platform roles (Super Admin, Platform Support,
    Platform Billing) are listed for super-admin callers only. D-16: requires
    manage:users or manage:rbac.
    """
    db = get_database()
    caller_is_super = is_super_admin(current_user.role)
    roles: List[dict] = []
    try:
        if caller_is_super:
            # D-17: without a tenantId a Super Admin gets the built-in roles only; with one,
            # that (validated, existing) tenant's custom roles too.
            tenant_id = await role_contents.resolve_target_tenant(db, current_user, tenantId) if tenantId else None
        else:
            if tenantId and tenantId != current_user.tenant_id:
                raise HTTPException(status_code=403, detail="You can only list roles of your own tenant")
            tenant_id = current_user.tenant_id
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
            for doc in await role_contents.custom_role_docs(db, tenant_id):
                name = doc["name"]
                roles.append({
                    "id": str(doc.get("id") or doc.get("_id")),
                    "name": name,
                    "description": doc.get("description") or "",
                    "permissions": await effective_permissions(db, name, tenant_id),
                    "isEditable": doc.get("isEditable", True),
                    "tenantId": tenant_id,
                    "builtIn": False,
                })
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Role list failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Role store unavailable")
    return roles


@router.get("/permission-catalogue")
async def permission_catalogue(current_user: TokenData = Depends(_require_role_write_access)):
    """What the editor may put in a custom role: the closure of its own effective set within the
    grantable vocabulary (every grantable string for a Super Admin), never manage:tenants,
    a platform-only permission or '*' (D-02, D-17)."""
    super_admin = is_super_admin(current_user.role)
    try:
        held = [] if super_admin else await effective_permissions(
            get_database(), current_user.role, current_user.tenant_id)
    except Exception as exc:
        raise _store_unavailable(exc)
    return {"permissions": role_contents.grantable_for(held, super_admin=super_admin), "superAdmin": super_admin}


@contextlib.contextmanager
def _role_write(tenant_id: str):
    """Clear the tenant's cached MFA answers once a role write was attempted, however it ends,
    so an added admin-tier permission needs MFA on the next request (77 WR-03, IN-12)."""
    try:
        yield
    finally:
        invalidate_mfa_role_cache(tenant_id)


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
        with _role_write(tenant_id):
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


async def _load_custom_role(db, current_user: TokenData, role_id: str, tenant_query: Optional[str]):
    """(tenant id, document) of a custom role of the target tenant; 404 for anything else.

    Built-in ids, legacy documents named like a built-in and other tenants' ids all answer
    404 because the lookup only ever sees the resolved tenant's custom documents (T-77-06).
    """
    tenant_id = await role_contents.resolve_target_tenant(db, current_user, tenant_query)
    doc = await role_contents.find_custom_role(db, tenant_id, role_id=role_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Role not found")
    return tenant_id, doc


@router.put("/{role_id}", response_model=Role)
async def update_role(role_id: str, body: RoleUpdate, tenantId: Optional[str] = None,
                      current_user: TokenData = Depends(_require_role_write_access)):
    """Edit a custom role's description and permissions (D-13: the name never changes).

    The editor ceiling (D-02) is checked on the symmetric difference of the old and new
    permissions. The change reaches holders on their next permission read (ACC-08).
    """
    db = get_database()
    try:
        tenant_id, doc = await _load_custom_role(db, current_user, role_id, tenantId)
        if body.name is not None and rbac_defaults.normalize_role(body.name.strip()) != \
                rbac_defaults.normalize_role(doc.get("name")):
            raise HTTPException(status_code=400, detail=RENAME_REFUSED)
        old_permissions = sorted(doc.get("permissions") or [])
        permissions = (role_contents.validate_permissions(body.permissions)
                       if body.permissions is not None else old_permissions)
        await role_contents.assert_can_edit_contents(db, current_user, old_permissions, permissions)
        changes = {"permissions": permissions, "updatedBy": current_user.username,
                   "updatedAt": datetime.now(timezone.utc).isoformat()}
        if body.description is not None:
            changes["description"] = body.description
        with _role_write(tenant_id):
            await db._db.roles.update_one({"id": role_id, "tenantId": tenant_id}, {"$set": changes})
    except HTTPException:
        raise
    except Exception as exc:
        raise _store_unavailable(exc)
    updated = {**doc, **changes}
    await _audit_role("role.updated", current_user.username or "", updated, tenant_id,
                      previous_state={"description": doc.get("description") or "", "permissions": old_permissions})
    return _role_response(updated, tenant_id)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(role_id: str, tenantId: Optional[str] = None,
                      current_user: TokenData = Depends(_require_role_write_access)):
    """Delete a custom role nobody holds (D-03, D-15).

    Refused with 409 ``role_in_use`` while users of the tenant hold it or the tenant's
    LDAP/SAML group mappings name it: nobody silently loses access (PROH-77-04).
    """
    db = get_database()
    try:
        tenant_id, doc = await _load_custom_role(db, current_user, role_id, tenantId)
        holder_count, holders, mapping_count, mappings = await role_contents.role_usage(db, tenant_id, doc["name"])
        if holder_count or mapping_count:
            raise HTTPException(status_code=409, detail={
                "code": "role_in_use", "holderCount": holder_count, "holders": holders,
                "mappingCount": mapping_count, "mappings": mappings,
            })
        with _role_write(tenant_id):
            await db._db.roles.delete_one({"id": role_id, "tenantId": tenant_id})
    except HTTPException:
        raise
    except Exception as exc:
        raise _store_unavailable(exc)
    await _audit_role("role.deleted", current_user.username or "", doc, tenant_id,
                      previous_state={"description": doc.get("description") or "",
                                      "permissions": sorted(doc.get("permissions") or [])})


async def _tenant_name(db, tenant_id: str) -> str:
    doc = await db._db.tenants.find_one({"id": tenant_id})
    return (doc or {}).get("name") or tenant_id


@router.get("/{role_id}/visibility")
async def role_visibility_view(role_id: str, tenantId: Optional[str] = None,
                               current_user: TokenData = Depends(_require_role_list_access)):
    """D-09/D-10: what a role can see, computed by the delivery pipeline (SC3).

    Built-in and custom roles of the caller's own tenant; a Super Admin may name a tenant
    (D-17: without one a built-in tenant role is shown unnarrowed, a custom role is refused).
    Platform roles are visible to a Super Admin only and are never narrowed. The marker on each
    screen (view or manage) comes only from the server.
    """
    db = get_database()
    caller_is_super = is_super_admin(current_user.role)
    try:
        if caller_is_super:
            tenant_id = await role_contents.resolve_target_tenant(db, current_user, tenantId) if tenantId else None
        else:
            if tenantId and tenantId != current_user.tenant_id:
                raise HTTPException(status_code=403, detail="You can only view roles of your own tenant")
            tenant_id = current_user.tenant_id
            if not tenant_id:
                raise HTTPException(status_code=403, detail="No tenant for this account")
        builtin = next((b for b in rbac_defaults.BUILTIN_ROLES if b.role_id == role_id), None)
        enabled: List[str] = []
        if builtin is not None and builtin.key in rbac_defaults.PLATFORM_ROLE_KEYS:
            if not caller_is_super:
                raise HTTPException(status_code=404, detail="Role not found")
            name, built_in, narrowed = builtin.name, True, False
            effective = await effective_permissions(db, builtin.name, None)
            basis = {"kind": "platform_role", "tenantId": None, "tenantName": None}
        else:
            if builtin is not None:
                name, built_in = builtin.name, True
            else:
                if not tenant_id:
                    raise HTTPException(status_code=400, detail="Select a tenant to see a custom role")
                doc = await role_contents.find_custom_role(db, tenant_id, role_id=role_id)
                if doc is None:
                    raise HTTPException(status_code=404, detail="Role not found")
                name, built_in = doc["name"], False
            effective = await effective_permissions(db, name, tenant_id)
            narrowed = tenant_id is not None
            if tenant_id:
                enabled = await tenant_features.enabled_features(tenant_id, get_database)
                basis = {"kind": "tenant", "tenantId": tenant_id, "tenantName": await _tenant_name(db, tenant_id)}
            else:
                basis = {"kind": "no_tenant", "tenantId": None, "tenantName": None}
    except HTTPException:
        raise
    except Exception as exc:
        raise _store_unavailable(exc)
    return role_visibility.build_visibility(
        role_id=role_id, role_name=name, built_in=built_in, effective=effective,
        enabled=enabled, narrowed=narrowed, basis=basis)
