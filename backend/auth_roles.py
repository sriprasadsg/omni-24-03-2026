"""Canonical role sets for tenant-isolation guards across all endpoints."""
from typing import Callable, Iterable, Iterator, Optional, Tuple

import rbac_defaults

# "platform_admin" (underscore) is the _normalize_role()-canonical form of
# "platform-admin" (hyphen) — both must be present here, since many callers
# do a raw `role in SUPER_ROLES` membership check without normalizing first.
# Omitting the underscore form was the "platform-admin gap" (RESEARCH.md
# Pitfall 3 / ITAM-USR-02): a caller comparing a normalized role string
# against this set would silently fail the super-admin check.
SUPER_ROLES: frozenset = frozenset({"Super Admin", "superadmin", "super_admin", "platform-admin", "platform_admin",
                                    "Platform Owner", "platform_owner"})

# Stored spellings of the tenant administrator, for queries that look users up by
# role (notification recipients). Tenant names only: never a platform role (spec C1).
TENANT_ADMIN_ROLE_NAMES: Tuple[str, ...] = ("admin", "Admin", "Tenant Admin", "tenant_admin")


class RoleSet:
    """Role membership decided by tier, usable wherever a literal role set was (spec C1).

    ``role in X`` normalizes ``role`` first, so every spelling of a role answers
    the same way and a new spelling cannot slip past a literal. Iterating yields
    readable names for error messages.
    """

    def __init__(self, label: str, predicate: Callable[[Optional[str]], bool],
                 names: Iterable[str], extras: Iterable[str] = ()):
        self._label = label
        self._predicate = predicate
        self._extras = frozenset(rbac_defaults.normalize_role(e) for e in extras)
        self._names = tuple(dict.fromkeys(list(names) + list(extras)))

    def __contains__(self, role: object) -> bool:
        if not isinstance(role, str) or not role:
            return False
        return self._predicate(role) or rbac_defaults.normalize_role(role) in self._extras

    def __iter__(self) -> Iterator[str]:
        return iter(self._names)

    def __repr__(self) -> str:
        return f"RoleSet({self._label}: {', '.join(self._names)})"


def platform_scope_roles(*extras: str) -> RoleSet:
    """Roles that see every tenant: the platform owner, support and billing (plus ``extras``).

    For guards that skip the caller's tenant filter. A tenant admin is never in it.
    Support and billing reach writes only through their permissions; the
    read-only guard in tenant_middleware refuses their other writes.
    """
    return RoleSet("platform", rbac_defaults.is_platform_role,
                   ("Super Admin", "Platform Support", "Platform Billing"), extras)


def platform_owner_roles(*extras: str) -> RoleSet:
    """The platform owner only (the super_admin key), plus ``extras``."""
    return RoleSet("owner", lambda r: rbac_defaults.platform_tier(r) == "owner", ("Super Admin",), extras)


def tenant_admin_roles(*extras: str) -> RoleSet:
    """A tenant administrator acting in its own tenant, the platform owner, plus ``extras``.

    For "403 unless admin" guards: the request stays scoped to the caller's
    tenant by the DB wrapper, so a tenant admin keeps the power for its tenant only.
    """
    return RoleSet("tenant admin",
                   lambda r: rbac_defaults.is_tenant_admin(r) or rbac_defaults.platform_tier(r) == "owner",
                   ("Tenant Admin", "Super Admin"), extras)
