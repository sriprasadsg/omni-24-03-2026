"""Rules for tenant custom-role documents (Phase 77: D-01, D-02, D-13, D-15, D-17, D-18).

``role_endpoints`` writes tenant custom roles; this module holds the rules it applies:
which names are allowed (D-18), which permission strings a custom role may contain
(D-17), how far an editor may reach (D-02, the D-11 closure of the editor's own
effective set), which tenant a request acts on, and who still holds a role (D-03, D-15).

Every role document read or write goes through the raw handle (``db._db.roles``) with an
explicit ``tenantId``: the wrapper would rewrite an unscoped read to the caller's own
tenant, and a Super Admin must be able to name another one. Only the tenant resolved by
``resolve_target_tenant`` is ever queried, so one tenant's documents are never read or
written on behalf of another.
"""
import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import HTTPException

import permission_vocabulary
import rbac_defaults
from auth_types import TokenData
from authentication_service import AGENT_ROLE
from rbac_service import effective_permissions
from rbac_utils import is_super_admin

logger = logging.getLogger(__name__)

# Tenant ids that name shared catalogues or the platform tenant, never a customer tenant.
SENTINEL_TENANTS = frozenset({rbac_defaults.PLATFORM_TENANT_ID, "all", "platform"})

# Never grantable by a custom role, whoever edits it (D-02, 75 D-06, spec C1).
BANNED_PERMISSIONS = (frozenset({"*"}) | rbac_defaults.SUPER_ADMIN_ONLY_PERMISSIONS
                      | rbac_defaults.PLATFORM_ONLY_PERMISSIONS)

# D-17: only strings the role table, manifest or switch catalogue already names.
GRANTABLE_PERMISSIONS = frozenset(permission_vocabulary.KNOWN_PERMISSIONS - BANNED_PERMISSIONS)

NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{1,63}$")
MAX_DESCRIPTION = 500
MAX_CUSTOM_ROLES_PER_TENANT = 200
MAX_LISTED = 50  # holders and mappings echoed in the delete refusal

STORE_UNAVAILABLE = "Role store unavailable; role change refused"


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _builtin_name_for(key: str) -> Optional[str]:
    """Display name of the built-in role a normalized key refers to, else None."""
    if key not in rbac_defaults.builtin_role_keys():
        return None
    target = key if key in {b.key for b in rbac_defaults.BUILTIN_ROLES} else rbac_defaults.canonical_key(key)
    for builtin in rbac_defaults.BUILTIN_ROLES:
        if builtin.key == target:
            return builtin.display_name or builtin.name
    return key


def validate_role_name(name: Optional[str], existing_docs: Iterable[Dict[str, Any]] = ()) -> str:
    """The stripped name, or 400 (empty, characters, reserved) / 409 (duplicate in the tenant).

    D-18: a name whose ``normalize_role`` key is a built-in key (any spelling), the agent
    role or empty is refused, so a custom role can never shadow or impersonate one.
    """
    clean = (name or "").strip()
    if not clean:
        raise _bad_request("A role name is required.")
    if not NAME_PATTERN.match(clean):
        raise _bad_request("Role names are 2 to 64 characters: letters, numbers, spaces, '_', '.' and '-', "
                           "starting with a letter or number.")
    key = rbac_defaults.normalize_role(clean)
    if not key:
        raise _bad_request("A role name is required.")
    if key == AGENT_ROLE:
        raise _bad_request(f"The name '{AGENT_ROLE}' is reserved.")
    builtin = _builtin_name_for(key)
    if builtin:
        raise _bad_request(f'That name matches the built-in role "{builtin}". Choose a different name.')
    for doc in existing_docs:
        if rbac_defaults.normalize_role(doc.get("name")) == key:
            raise HTTPException(status_code=409, detail="A role with this name already exists.")
    return clean


def validate_permissions(perms: Optional[Iterable[str]]) -> List[str]:
    """Sorted unique permission list, or 400 naming every unknown or banned string (D-17, D-02)."""
    given = list(perms or [])
    if len(given) > len(GRANTABLE_PERMISSIONS):
        raise _bad_request("Too many permissions.")
    unique = list(dict.fromkeys(given))
    refused = sorted(p for p in unique if not isinstance(p, str) or p not in GRANTABLE_PERMISSIONS)
    if refused:
        raise _bad_request("These permissions cannot be granted by a custom role: " + ", ".join(map(str, refused)))
    return sorted(unique)


async def assert_can_edit_contents(db, caller: TokenData, old: Iterable[str], new: Iterable[str]) -> None:
    """403 unless every permission added or removed is inside the editor's own closure (D-02).

    The symmetric difference is checked, so a holder cannot strip a permission it does
    not hold either. A Super Admin passes (the banned set still applies through
    ``validate_permissions``). A role-store error refuses the write (503, fail closed).
    """
    if is_super_admin(caller.role):
        return
    try:
        caller_perms = await effective_permissions(db, caller.role, caller.tenant_id)
    except Exception as exc:
        logger.error("Role ceiling lookup failed for %s: %s", caller.role, exc)
        raise HTTPException(status_code=503, detail=STORE_UNAVAILABLE)
    if not rbac_defaults.ceiling_allows(caller_perms, set(old) ^ set(new)):
        raise HTTPException(status_code=403, detail="You can only grant permissions you hold yourself")


async def resolve_target_tenant(db, caller: TokenData, requested: Optional[str]) -> str:
    """The tenant a role request acts on (T-77-06, T-77-07).

    A non-Super-Admin always acts on its own tenant (naming another is 403). A Super Admin
    must name an existing customer tenant; the platform tenant and the shared "all" and
    "platform" catalogues are never targets.
    """
    if not is_super_admin(caller.role):
        if requested and requested != caller.tenant_id:
            raise HTTPException(status_code=403, detail="You can only manage roles of your own tenant")
        tenant = caller.tenant_id
        if not tenant:
            raise HTTPException(status_code=403, detail="No tenant for this account")
    else:
        tenant = requested
        if not tenant:
            raise _bad_request("tenantId is required for a Super Admin")
    if tenant in SENTINEL_TENANTS:
        raise _bad_request("That tenant cannot own custom roles")
    if is_super_admin(caller.role) and await db._db.tenants.find_one({"id": tenant}) is None:
        raise _bad_request("Unknown tenant")
    return tenant


async def custom_role_docs(db, tenant_id: str) -> List[Dict[str, Any]]:
    """The tenant's custom role documents.

    Legacy documents whose name normalizes to a built-in key extend that built-in (75 D-15)
    and are not custom roles, so they are skipped here.
    """
    builtin_keys = rbac_defaults.builtin_role_keys()
    docs = await db._db.roles.find({"tenantId": tenant_id}).to_list(500)
    return [d for d in docs
            if d.get("name") and rbac_defaults.normalize_role(d["name"]) not in builtin_keys]


async def find_custom_role(db, tenant_id: str, *, role_id: Optional[str] = None,
                           name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """The tenant's custom role with this id, or with this name (compared after normalize_role)."""
    key = rbac_defaults.normalize_role(name) if name is not None else None
    for doc in await custom_role_docs(db, tenant_id):
        if role_id is not None and doc.get("id") == role_id:
            return doc
        if key is not None and rbac_defaults.normalize_role(doc.get("name")) == key:
            return doc
    return None


async def role_usage(db, tenant_id: str, name: str) -> Tuple[int, List[Dict[str, str]], int, List[Dict[str, str]]]:
    """Who still holds a role: (holder count, holders, mapping count, mappings), D-03 and D-15.

    Users of the tenant are compared after ``normalize_role`` (users store the role by
    name, in any spelling); the tenant's LDAP and SAML group mappings likewise. Counts are
    exact, the lists are capped at ``MAX_LISTED``.
    """
    key = rbac_defaults.normalize_role(name)
    users = await db._db.users.find({"tenantId": tenant_id}, {"role": 1, "email": 1, "full_name": 1}).to_list(5000)
    holders = [{"name": u.get("full_name") or u.get("name") or u.get("email") or "", "email": u.get("email") or ""}
               for u in users if rbac_defaults.normalize_role(u.get("role")) == key]
    mappings: List[Dict[str, str]] = []
    for collection, field, source in (("ldap_group_mappings", "group_dn", "LDAP"),
                                      ("saml_group_mappings", "group_value", "SAML")):
        docs = await getattr(db._db, collection).find({"tenant_id": tenant_id}).to_list(5000)
        mappings.extend({"group": d.get(field) or "", "source": source}
                        for d in docs if rbac_defaults.normalize_role(d.get("role")) == key)
    return len(holders), holders[:MAX_LISTED], len(mappings), mappings[:MAX_LISTED]


def grantable_for(caller_perms: Iterable[str], *, super_admin: bool) -> List[str]:
    """What an editor may put in a custom role: the closure of its set within the grantable vocabulary."""
    if super_admin:
        return sorted(GRANTABLE_PERMISSIONS)
    return sorted(rbac_defaults.implied_closure(caller_perms) & GRANTABLE_PERMISSIONS)
