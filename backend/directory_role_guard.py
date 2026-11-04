"""Apply-time checks for LDAP/SAML group-to-role mappings (Phase 75 WR-04).

The mapping endpoints hold the role ceiling when a mapping is written or deleted
(``role_assignment.assert_can_assign_role``). The checks here run when a mapping is
applied, on an LDAP sync or login and on a SAML login, shared by ``ldap_service`` and
``saml_mapping``:

- ``writer_fields`` records who wrote a mapping. ``mapping_still_assignable`` re-checks
  that writer at apply time: a mapping whose writer was demoted, disabled, deleted or moved
  to another tenant is skipped, logged and audited. A mapping written before writers were
  recorded has no ``writtenBy`` and applies as before, so existing directory logins keep
  working until an admin re-saves the mapping.
- ``role_to_apply`` never lets a mapping replace the role of an existing account that holds
  permissions the mapping's role lacks, unless the directory gave the account that role
  (``directoryRole``). A directory demotion therefore still takes effect for a role the
  directory assigned, but never demotes or replaces a higher-privileged local account that
  shares an email with a directory entry, nor a role an admin raised by hand.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

import audit_ledger
import rbac_defaults
from auth_types import TokenData

logger = logging.getLogger(__name__)

# Stored on a user document: the role the directory last offered the account.
DIRECTORY_ROLE_FIELD = "directoryRole"


def writer_fields(writer: Optional[TokenData]) -> dict:
    """The fields that record a mapping's writer (empty when there is none)."""
    if writer is None:
        return {}
    return {"writtenBy": writer.username, "writtenByRole": writer.role,
            "writtenByTenantId": writer.tenant_id, "writtenAt": datetime.now(timezone.utc).isoformat()}


async def _writer_refusal(db, mapping: dict, tenant_id: Optional[str]) -> Optional[str]:
    """Why the mapping's writer may no longer assign its role, or None when they still may."""
    from fastapi import HTTPException
    from authentication_service import account_is_active
    from role_assignment import assert_can_assign_role, refuse_directory_platform_role

    writer = await getattr(db, "_db", db).users.find_one(
        {"email": mapping["writtenBy"]}, {"_id": 0, "email": 1, "role": 1, "tenantId": 1, "status": 1, "is_active": 1})
    if writer is None:
        return "the writer's account no longer exists"
    if not account_is_active(writer):
        return "the writer's account is disabled"
    is_super = rbac_defaults.normalize_role(writer.get("role")) == rbac_defaults.SUPER_ADMIN_KEY
    if not is_super and writer.get("tenantId") != mapping.get("writtenByTenantId"):
        return "the writer has moved to another tenant"
    caller = TokenData(username=writer["email"], role=writer.get("role"), tenant_id=writer.get("tenantId"))
    try:
        refuse_directory_platform_role(mapping.get("role"))
        await assert_can_assign_role(db, caller, mapping.get("role") or "", target_tenant_id=tenant_id)
    except HTTPException as exc:
        return str(exc.detail)
    return None


async def mapping_still_assignable(db, mapping: dict, tenant_id: Optional[str], provider: str) -> bool:
    """False (logged and audited) when the mapping's recorded writer can no longer assign its role.

    A legacy mapping with no ``writtenBy`` returns True. A lookup error refuses the mapping
    (fail closed): the account keeps its role, or gets the default role when it is new.
    """
    if not mapping.get("writtenBy"):
        return True  # written before writers were recorded: applied as before (WR-04)
    try:
        reason = await _writer_refusal(db, mapping, tenant_id)
    except Exception as exc:
        reason = f"the writer could not be checked ({type(exc).__name__})"
    if reason is None:
        return True
    logger.warning("%s mapping %s -> %r in tenant %s skipped: %s (written by %s)", provider.upper(),
                   mapping.get("_id"), mapping.get("role"), tenant_id, reason, mapping.get("writtenBy"))
    await audit_ledger.event(
        "directory_mapping.skipped", tenant_id, actor={"email": "system"}, outcome="denied",
        db=getattr(db, "_db", db), provider=provider, resourceType="directory_mapping",
        resourceId=str(mapping.get("_id") or ""), role=mapping.get("role"),
        writtenBy=mapping.get("writtenBy"), reason=reason,
    )
    return False


def _directory_owns_role(existing: dict, provider: str) -> bool:
    if DIRECTORY_ROLE_FIELD in existing:
        return existing[DIRECTORY_ROLE_FIELD] == existing.get("role")
    # Synced before directoryRole was recorded: the directory created or already manages the
    # account, so its mappings keep applying as they did (WR-04 legacy accounts).
    return existing.get("source") == provider


async def role_to_apply(db, existing: Optional[dict], role: Optional[str], tenant_id: str,
                        provider: str) -> Optional[str]:
    """``role`` when a mapping may write it onto ``existing``, else None (keep the current role)."""
    if not role or not existing or role == existing.get("role") or _directory_owns_role(existing, provider):
        return role
    from rbac_service import effective_permissions
    try:
        held = await effective_permissions(db, existing.get("role"), tenant_id)
        offered = await effective_permissions(db, role, tenant_id)
    except Exception as exc:  # fail closed: an unverifiable change is not written
        logger.warning("Role store error while applying %s mapping role %r to %s: %s; keeping its role",
                       provider.upper(), role, existing.get("email"), exc)
        return None
    if rbac_defaults.ceiling_allows(offered, held):
        return role
    logger.warning("%s mapping resolved %s to role %r, but the account's role %r holds permissions it lacks; "
                   "keeping its role", provider.upper(), existing.get("email"), role, existing.get("role"))
    return None


def directory_role_update(existing: Optional[dict], offered: Optional[str], provider: str) -> dict:
    """The ``directoryRole`` value to store on a sync of ``existing``.

    Records the role the directory offered, applied or not. A local account linked for the
    first time with no role offered records None, so linking alone never hands the
    directory ownership of its role.
    """
    if offered:
        return {DIRECTORY_ROLE_FIELD: offered}
    if existing is not None and DIRECTORY_ROLE_FIELD not in existing and existing.get("source") != provider:
        return {DIRECTORY_ROLE_FIELD: None}
    return {}
