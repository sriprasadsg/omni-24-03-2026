"""Role-assignment ceiling (Phase 75, D-18 refined by D-20, made workable for ITAM by D-21).

The one shared ceiling helper for user CRUD (``user_endpoints``) and for
LDAP/SAML mapping writes. ``RBACService.can_assign_role`` remains the table-only
variant; this helper additionally sees tenant-scoped role documents because both
sides of the comparison come from ``rbac_service.effective_permissions``.
"""
import logging
from typing import Any, Dict, Optional

from fastapi import HTTPException

import rbac_defaults
from auth_types import TokenData
from rbac_service import RBACService, effective_permissions

logger = logging.getLogger(__name__)

# Every stored spelling that normalizes to the platform owner (super_admin key).
_OWNER_ROLE_PATTERN = r"^\s*(super[\s_-]*admin|platform[\s_-]*(admin|owner))\s*$"

# Stored name for each platform role, whatever spelling the request used, so raw
# role-name checks across the backend keep recognising the account (spec C1).
_PLATFORM_ROLE_STORED_NAME = {
    builtin.key: builtin.name for builtin in rbac_defaults.BUILTIN_ROLES if builtin.key in rbac_defaults.PLATFORM_ROLE_KEYS
}


def stored_role_name(role: str) -> str:
    """``role`` as it is written to a user document: platform roles get their built-in name."""
    return _PLATFORM_ROLE_STORED_NAME.get(rbac_defaults.normalize_role(role), role)


async def resolve_assignable_role(db, typed: Optional[str], tenant_id: Optional[str]) -> str:
    """The canonical stored name for a role typed into a user or directory-mapping write (77 D-04).

    A built-in key keeps ``stored_role_name``. Anything else must be a custom role of
    ``tenant_id`` itself: its stored (canonical) name is returned, so the ceiling check and
    storage see the same spelling (Pitfall 6). Another tenant's role, an unknown name, a
    sentinel or missing tenant is 400; a role-store error refuses the assignment (503).
    """
    if rbac_defaults.normalize_role(typed) in rbac_defaults.builtin_role_keys():
        return stored_role_name(typed)
    import role_contents  # lazy: role_contents imports authentication_service
    invalid = HTTPException(status_code=400, detail=f"Invalid role '{typed}'")
    if not tenant_id or tenant_id in role_contents.SENTINEL_TENANTS:
        raise invalid
    try:
        doc = await role_contents.find_custom_role(db, tenant_id, name=typed)
    except Exception as exc:  # fail closed
        logger.warning("Role store error while resolving role %r in tenant %r: %s", typed, tenant_id, exc)
        raise HTTPException(status_code=503, detail="Role store unavailable; role assignment refused")
    if doc is None:
        raise invalid
    return doc["name"]


def assert_role_fits_tenant(role: Optional[str], tenant_id: Optional[str]) -> None:
    """400 unless platform roles live in the platform tenant and tenant roles outside it (spec C1).

    The platform tenant's context switches off the DB wrapper's tenant scoping, so a
    tenant role there would act on every tenant, and a platform role anywhere else
    would hold platform powers inside one customer's tenant.
    """
    in_platform_tenant = tenant_id == rbac_defaults.PLATFORM_TENANT_ID
    if rbac_defaults.is_platform_role(role) and not in_platform_tenant:
        raise HTTPException(status_code=400,
                            detail=f"Role '{role}' is a platform role and can only be held in the Platform tenant")
    if in_platform_tenant and not rbac_defaults.is_platform_role(role):
        raise HTTPException(status_code=400,
                            detail="Users in the Platform tenant must hold a platform role")


def refuse_directory_platform_role(role: Optional[str]) -> None:
    """400 for an LDAP/SAML mapping to a platform role: directory sync writes users into a
    customer tenant, and platform roles are only held in the Platform tenant (spec C1)."""
    if rbac_defaults.is_platform_role(role):
        raise HTTPException(status_code=400,
                            detail=f"Role '{role}' is a platform role and cannot be mapped from a directory")


def _is_active_owner(user: Dict[str, Any]) -> bool:
    from authentication_service import account_is_active
    return rbac_defaults.platform_tier(user.get("role")) == "owner" and account_is_active(user)


async def assert_not_last_platform_owner(db, target_user: Dict[str, Any], *, deleting: bool = False,
                                         new_role: Optional[str] = None, new_status: Optional[str] = None,
                                         new_tenant_id: Optional[str] = None) -> None:
    """409 ``last_platform_owner`` when the change leaves no active Platform Owner (spec C1).

    Deleting, demoting, disabling or moving the account out of the platform tenant all
    count as removing an owner. Two simultaneous removals of the last two owners can
    both pass this check (it is read-then-write); the next one is refused.
    """
    if not _is_active_owner(target_user):
        return
    after = dict(target_user)
    if new_role is not None:
        after["role"] = new_role
    if new_status is not None:
        after["status"] = new_status
    if new_tenant_id is not None:
        after["tenantId"] = new_tenant_id
    still_owner = (not deleting and _is_active_owner(after)
                   and after.get("tenantId") == target_user.get("tenantId"))
    if still_owner:
        return
    users = getattr(db, "_db", db).users
    candidates = await users.find(
        {"role": {"$regex": _OWNER_ROLE_PATTERN, "$options": "i"}},
        {"_id": 1, "role": 1, "status": 1, "is_active": 1},
    ).to_list(length=1000)
    others = [u for u in candidates if u.get("_id") != target_user.get("_id") and _is_active_owner(u)]
    if not others:
        raise HTTPException(status_code=409, detail="last_platform_owner")


async def assert_can_assign_role(
    db,
    caller: TokenData,
    target_role: str,
    *,
    target_tenant_id: Optional[str],
    target_email: Optional[str] = None,
    current_role: Optional[str] = None,
) -> None:
    """Raise ``HTTPException`` unless ``caller`` may give ``target_role`` to the target user.

    Rules, in order:
      1. The platform roles (super-admin tier, Platform Support, Platform Billing) are
         assignable only by a super-admin, decided by role-name normalization and never
         by a ``*`` inside a role document.
      2. Nobody changes their own account's role (re-sending the same role is not a change).
      3. A super-admin caller may assign any other role.
      4. Otherwise the target's effective permissions must be a subset of the caller's
         under the manage:X implies view:X and request:X closure.
    A role-store error refuses the assignment (fail closed, 503).
    """
    normalize = RBACService._normalize_role
    super_key = rbac_defaults.SUPER_ADMIN_KEY
    target_key = normalize(target_role or "")
    caller_is_super = normalize(caller.role or "") == super_key

    if target_key in rbac_defaults.PLATFORM_ROLE_KEYS and not caller_is_super:
        raise HTTPException(status_code=403,
                            detail=f"Only a platform super-admin can assign role '{target_role}'")

    if (target_email and caller.username
            and target_email.strip().lower() == caller.username.strip().lower()
            and current_role is not None
            and target_key != normalize(current_role)):
        raise HTTPException(status_code=403, detail="You cannot change your own role")

    if caller_is_super:
        return

    try:
        caller_perms = await effective_permissions(db, caller.role, caller.tenant_id)
        target_perms = await effective_permissions(db, target_role, target_tenant_id)
    except Exception as exc:  # fail closed
        logger.warning("Role store error while checking assignment of %r by %r: %s",
                       target_role, caller.role, exc)
        raise HTTPException(status_code=503,
                            detail="Role store unavailable; role assignment refused")

    if not rbac_defaults.ceiling_allows(caller_perms, target_perms):
        raise HTTPException(
            status_code=403,
            detail=f"Not authorized to assign role '{target_role}': it grants permissions you do not hold")


async def assert_can_manage_account(
    db,
    caller: TokenData,
    target_role: Optional[str],
    *,
    target_tenant_id: Optional[str],
) -> None:
    """Raise ``HTTPException`` unless ``caller`` may modify or delete an account that holds ``target_role``.

    The account-side twin of ``assert_can_assign_role`` (D-18/D-20): resetting
    a password, disabling, moving or deleting an account is as powerful as
    handing out its role, so the same ceiling applies to the account's
    *current* role. Rules, in order:
      1. A super-admin caller may manage any account.
      2. A platform-role account (owner, support, billing) is managed only by a
         super-admin, decided by role-name normalization, never by a ``*`` in a document.
      3. Otherwise the account's effective permissions must be a subset of the
         caller's under the manage:X implies view:X and request:X closure
         (an account of an equal role is manageable; a higher one is not).
    A role-store error refuses the operation (fail closed, 503).
    """
    normalize = RBACService._normalize_role
    super_key = rbac_defaults.SUPER_ADMIN_KEY
    if normalize(caller.role or "") == super_key:
        return

    if normalize(target_role or "") in rbac_defaults.PLATFORM_ROLE_KEYS:
        raise HTTPException(status_code=403,
                            detail="Only a platform super-admin can modify a platform account")

    try:
        caller_perms = await effective_permissions(db, caller.role, caller.tenant_id)
        target_perms = await effective_permissions(db, target_role, target_tenant_id)
    except Exception as exc:  # fail closed
        logger.warning("Role store error while checking management of a %r account by %r: %s",
                       target_role, caller.role, exc)
        raise HTTPException(status_code=503,
                            detail="Role store unavailable; account change refused")

    if not rbac_defaults.ceiling_allows(caller_perms, target_perms):
        raise HTTPException(
            status_code=403,
            detail="Not authorized to modify this account: its role grants permissions you do not hold")
