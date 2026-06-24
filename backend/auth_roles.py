"""Canonical role sets for tenant-isolation guards across all endpoints."""
SUPER_ROLES: frozenset = frozenset({"Super Admin", "superadmin", "super_admin", "platform-admin"})
SUPER_AND_ADMIN_ROLES: frozenset = SUPER_ROLES | frozenset({"admin"})
