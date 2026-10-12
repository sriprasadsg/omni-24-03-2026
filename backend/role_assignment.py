"""Role-assignment ceiling (Phase 75, D-18 refined by D-20, made workable for ITAM by D-21).

The one shared ceiling helper for user CRUD (``user_endpoints``) and for
LDAP/SAML mapping writes. ``RBACService.can_assign_role`` remains the table-only
variant; this helper additionally sees tenant-scoped role documents because both
sides of the comparison come from ``rbac_service.effective_permissions``.
"""
import logging
from typing import Optional

from fastapi import HTTPException

import rbac_defaults
from auth_types import TokenData
from rbac_service import RBACService, effective_permissions

logger = logging.getLogger(__name__)


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
      1. The super-admin tier is assignable only by a super-admin, decided by role-name
         normalization and never by a ``*`` inside a role document.
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

    if target_key == super_key and not caller_is_super:
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
