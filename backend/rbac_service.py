import logging
from fastapi import HTTPException, status, Depends
from authentication_service import get_current_user
from auth_types import TokenData
from database import get_database
from typing import Dict, List, Optional

import rbac_defaults

logger = logging.getLogger(__name__)


async def find_role_doc(db, role_name: str, tenant_id: Optional[str]) -> Optional[dict]:
    """Look up a role document by name, trying the caller's own tenant first
    and falling back to the platform-wide sentinels ("all", "platform").

    DB-F10 (2026-08-25 audit): `roles` used to be exempt from the tenant-
    isolation wrapper entirely, so any of these lookups worked with a bare
    `db.roles.find_one({"name": role_name})` — but that also meant any
    tenant could enumerate every OTHER tenant's custom role definitions.
    Now that `roles` is wrapped like every other collection, an unscoped
    query auto-injects the caller's own tenant_id, which correctly finds a
    tenant-specific role but can never match a genuinely global one (real
    tenantId "all"/"platform" != the caller's own tenant_id). The `db._db`
    accesses below intentionally bypass the wrapper for those two sentinel
    values only — they are not tenant secrets, they're the shared platform
    role catalog every tenant is meant to see.
    """
    own_tenant = await db.roles.find_one({"name": role_name, "tenantId": tenant_id}) if tenant_id else None
    if own_tenant:
        return own_tenant
    raw_db = db._db
    return (
        await raw_db.roles.find_one({"name": role_name, "tenantId": "all"})
        or await raw_db.roles.find_one({"name": role_name, "tenantId": "platform"})
    )

async def _role_docs(db, name: str, tenant_id: Optional[str]) -> List[dict]:
    """Role documents named ``name`` visible to ``tenant_id``: its own tenant's,
    then the shared "all" and "platform" catalogues.

    Reads through the raw handle with an explicit tenantId (D-23) because /login
    is a public path with no tenant ContextVar, so a wrapper read would be
    rewritten to the emergency sentinel and never see a tenant-scoped document.
    Only the caller's own tenantId and the two sentinels are ever queried, never
    another tenant's.
    """
    if not name:
        return []
    docs: List[dict] = []
    for scope in dict.fromkeys(t for t in (tenant_id, "all", "platform") if t):
        doc = await db._db.roles.find_one({"name": name, "tenantId": scope})
        if doc:
            docs.append(doc)
    return docs


def _role_document_names(role: Optional[str], key: str) -> List[str]:
    """Every spelling under which a role's documents may be stored (WR-06).

    The raw string and its normalized key, plus, for a built-in role, the
    seeded ``name`` and ``display_name`` of every built-in that shares its
    canonical key (so ``tenant_admin``, ``Tenant Admin`` and ``admin`` all
    see the same documents and the ceiling evaluates them the same way).
    """
    canonical = rbac_defaults.canonical_key(key)
    names = [role, key]
    for builtin in rbac_defaults.BUILTIN_ROLES:
        if rbac_defaults.canonical_key(builtin.key) == canonical and builtin.key != rbac_defaults.SUPER_ADMIN_KEY:
            names.extend((builtin.name, builtin.display_name))
    return list(dict.fromkeys(n for n in names if n))


async def effective_permissions(db, role: Optional[str], tenant_id: Optional[str]) -> List[str]:
    """The one answer to "what may this role do for this tenant" (ACC-01/ACC-02).

    ``["*"]`` for the super-admin tier; otherwise the built-in defaults from
    ``rbac_defaults`` followed by the permissions of the matching role documents
    (own tenant, then "all", then "platform"), de-duplicated in first-seen order.
    A missing role, or an unknown role with no document, resolves to ``[]``.
    Role documents can only add ordinary permissions: a ``*`` or a
    ``SUPER_ADMIN_ONLY_PERMISSIONS`` entry found in a document is ignored, so the
    super-admin tier stays reachable only through the super-admin role name (D-03/D-06);
    a ``PLATFORM_ONLY_PERMISSIONS`` entry is ignored on every non-platform role (spec C1).
    Documents are matched under every spelling of a built-in role (see
    ``_role_document_names``), so a tenant override applies however the user's role
    was typed. Merging is union-only: a document adds permissions, never removes them.
    Role-store errors propagate; callers decide whether to fail closed or degrade.
    """
    key = RBACService._normalize_role(role or "")
    if key == rbac_defaults.SUPER_ADMIN_KEY:
        return ["*"]
    if not key:
        return []
    perms: List[str] = list(rbac_defaults.defaults_for(key))
    banned = rbac_defaults.SUPER_ADMIN_ONLY_PERMISSIONS | {"*"}
    if key not in rbac_defaults.PLATFORM_ROLE_KEYS:
        banned |= rbac_defaults.PLATFORM_ONLY_PERMISSIONS  # spec C1: never on a tenant role
    for name in _role_document_names(role, key):
        for doc in await _role_docs(db, name, tenant_id):
            perms.extend(p for p in (doc.get("permissions") or []) if p and p not in banned)
    return list(dict.fromkeys(perms))


async def session_permissions(db, role: Optional[str], tenant_id: Optional[str], *,
                              warn_if_empty: bool = False) -> List[str]:
    """effective_permissions for delivery to the UI (/login, /me): never raises.

    If the role store is unreachable the built-in defaults are delivered instead
    (never more than the table). ``warn_if_empty`` logs when a role resolves to
    nothing so an operator can spot a stranded account (D-19).
    """
    try:
        perms = await effective_permissions(db, role, tenant_id)
    except Exception as exc:
        logger.warning("Role store unavailable while resolving %r; delivering built-in defaults only: %s",
                       role, exc)
        perms = list(rbac_defaults.defaults_for(RBACService._normalize_role(role or "")))
    if warn_if_empty and not perms:
        logger.warning("Role %r resolved to no permissions; login allowed with an empty permission list", role)
    return perms


# ITAM-USR-05 (Phase 64-05): roles whose require_role()-gated endpoints are
# additionally narrowed to a specific scope when the caller authenticated via
# an api_key TokenData (auth_source == "api_key"). Session/JWT-authenticated
# requests (auth_source == "session", the default) are never subject to this
# extra check — it exists purely to stop a scoped API token from riding an
# admin role's require_role() bypass.
_ROLE_ADMIN_GATING_SCOPE: Dict[str, str] = {
    "admin": "admin:itam",
    "tenant_admin": "admin:itam",
    "super_admin": "admin:itam",
    "itam_admin": "admin:itam",
}


class RBACService:
    def __init__(self):
        # Read-only view of the single table in rbac_defaults (ACC-02): one list
        # per role key, the `admin` alias and the legacy `Tenant Admin` display
        # key kept for back-compat (user_endpoints._VALID_ROLE_KEYS, ldap/saml
        # role validation, tests). Never edit permissions here; edit the table.
        self.default_roles = {
            key: list(rbac_defaults.defaults_for(key))
            for key in sorted(rbac_defaults.builtin_role_keys())
        }
        self.default_roles["Tenant Admin"] = list(rbac_defaults.defaults_for("tenant_admin"))

    @staticmethod
    def _normalize_role(name: str) -> str:
        """Canonicalize role names to snake_case, e.g. 'Super Admin' / 'superadmin' → 'super_admin'.

        Delegates to ``rbac_defaults.normalize_role``, the single normalization rule
        (RESEARCH.md Pitfall 3 / ITAM-USR-02), which lives in the pure module so
        stdlib-only callers (auth_roles, tenant_middleware) agree with this method:
        "platform-admin", "superadmin" and "Platform Owner" all fold into "super_admin".
        """
        return rbac_defaults.normalize_role(name)

    def get_permissions_for_role(self, role: str) -> List[str]:
        """Static (non-DB) permission list for a role name, for frontend UI role-matrix rendering.

        Reads the built-in table only (no DB call); the role is normalized first
        so Title-Case variants (e.g. the /api/roles stub's "Admin"/"User") resolve.
        For request-time enforcement use `has_permission`/`require_role`/
        `get_user_permissions`, which also consult the `roles` collection.
        """
        return list(rbac_defaults.defaults_for(self._normalize_role(role)))

    def can_assign_role(self, caller_role: str, target_role: str) -> bool:
        """Table-only form of the D-20 assignment ceiling.

        A platform-role target needs a super-admin caller (decided by role name,
        never by a `*` appearing in a document); a super-admin caller may assign
        anything; otherwise the target's defaults must fit the caller's defaults
        under the manage:X implies view:X and request:X closure. The request-time
        helper `role_assignment.assert_can_assign_role` (Phase 75 plan 04) adds
        the self-change rule and tenant-scoped role documents on top of this.
        """
        target_key = self._normalize_role(target_role)
        caller_key = self._normalize_role(caller_role)
        if target_key in rbac_defaults.PLATFORM_ROLE_KEYS:
            return caller_key == rbac_defaults.SUPER_ADMIN_KEY
        if caller_key == rbac_defaults.SUPER_ADMIN_KEY:
            return True
        return rbac_defaults.ceiling_allows(
            rbac_defaults.defaults_for(caller_key), rbac_defaults.defaults_for(target_key))

    async def get_user_permissions(self, user: TokenData) -> List[str]:
        """Effective permissions for the current user, from the shared resolver."""
        try:
            return await effective_permissions(get_database(), user.role, user.tenant_id)
        except Exception as exc:
            # Never more than the built-in table when the role store is unreachable.
            logger.warning("Role store unavailable while resolving %r; using built-in defaults only: %s",
                           user.role, exc)
            return list(rbac_defaults.defaults_for(self._normalize_role(user.role or "")))

    def _scopes_allow(self, user: TokenData, required_permission: str) -> bool:
        """ITAM-USR-05 (Task 3): a token's scopes can only narrow what its
        owning user's role already permits, never grant more. `user.scopes`
        is None for session/JWT auth (unrestricted — role is the only bound);
        a populated list narrows the request to exactly those scopes (or the
        "*" wildcard). An empty list denies every permission.

        `scopes` is read via getattr + an explicit `list` type check (not a
        bare `user.scopes is None` check) because a large portion of the
        existing test suite injects the current-user dependency as a bare
        `unittest.mock.MagicMock()` rather than a real TokenData — attribute
        access on those doubles auto-vivifies a truthy child Mock instead of
        raising AttributeError or returning None, which would incorrectly
        trip scope-narrowing for callers that never carry real scopes.
        """
        scopes = getattr(user, "scopes", None)
        if not isinstance(scopes, list):
            return True
        return required_permission in scopes or "*" in scopes

    def has_permission(self, required_permission: str):
        """Dependency factory to check for a specific permission.

        Enforcement order (ITAM-USR-05 T-64-20 — role is the outer bound,
        scopes only narrow):
          1. Resolve role permissions via get_user_permissions(user). If the
             required permission is absent (and no "*" wildcard), deny —
             this is evaluated identically for session and api_key auth.
          2. Only once the role check passes, apply the scope-narrowing
             check. This ordering means a super_admin's "*" role wildcard
             still gets narrowed by an api_key token's scopes.
        """
        async def dependency(user: TokenData = Depends(get_current_user)):
            permissions = await self.get_user_permissions(user)

            if "*" not in permissions and required_permission not in permissions:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Missing required permission: {required_permission}"
                )

            if not self._scopes_allow(user, required_permission):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"API key scope does not permit: {required_permission}"
                )
            return user
        return dependency

    def require_role(self, allowed_roles: List[str]):
        """Dependency factory to check for specific roles"""
        # Normalize the allowed list once so callers don't need to enumerate variants
        normalized_allowed = {self._normalize_role(r) for r in allowed_roles}

        async def dependency(user: TokenData = Depends(get_current_user)):
            normalized_role = self._normalize_role(user.role)
            if normalized_role != "super_admin":
                if normalized_role not in normalized_allowed and user.role not in allowed_roles:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Role not allowed. Required one of: {allowed_roles}"
                    )

            # ITAM-USR-05 (Task 3): api_key-authenticated requests additionally
            # need the role's gating scope — an admin-role key without
            # "admin:itam" cannot exercise require_role()'s admin bypass.
            # getattr (not direct attribute access) so user doubles lacking
            # auth_source entirely (older test fakes) fall through as
            # "session" rather than raising AttributeError.
            if getattr(user, "auth_source", "session") == "api_key":
                gating_scope = _ROLE_ADMIN_GATING_SCOPE.get(normalized_role)
                if gating_scope:
                    scopes = getattr(user, "scopes", None)
                    scopes = scopes if isinstance(scopes, list) else []
                    if gating_scope not in scopes and "*" not in scopes:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"API key scope does not permit this role: requires '{gating_scope}'"
                        )
            return user
        return dependency

rbac_service = RBACService()
