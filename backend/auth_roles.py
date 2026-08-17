"""Canonical role sets for tenant-isolation guards across all endpoints."""
# "platform_admin" (underscore) is the _normalize_role()-canonical form of
# "platform-admin" (hyphen) — both must be present here, since many callers
# do a raw `role in SUPER_ROLES` membership check without normalizing first.
# Omitting the underscore form was the "platform-admin gap" (RESEARCH.md
# Pitfall 3 / ITAM-USR-02): a caller comparing a normalized role string
# against this set would silently fail the super-admin check.
SUPER_ROLES: frozenset = frozenset({"Super Admin", "superadmin", "super_admin", "platform-admin", "platform_admin"})
SUPER_AND_ADMIN_ROLES: frozenset = SUPER_ROLES | frozenset({"admin"})
