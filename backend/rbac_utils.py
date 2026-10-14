import logging
from enum import Enum
from typing import List, Optional
from fastapi import HTTPException, status, Depends
from auth_types import TokenData
from authentication_service import get_current_user
from database import get_database
import rbac_defaults
from rbac_service import rbac_service as _rbac_service, granted_permissions
import tenant_features

logger = logging.getLogger(__name__)


def is_super_admin(role: Optional[str]) -> bool:
    """Return True if the given role string represents a super-admin.

    Routes through rbac_service._normalize_role() — the single normalization
    source of truth (RESEARCH.md Pitfall 3 / ITAM-USR-02) — instead of a
    second hardcoded literal set, so raw variants ("platform-admin",
    "platform_admin", "SUPER_ADMIN", "Super Admin", ...) all resolve
    consistently with auth_roles.SUPER_ROLES and rbac_service's own
    has_permission/require_role/get_user_permissions dependency factories.
    """
    return _rbac_service._normalize_role(role) == "super_admin"


# Spec C1 platform tiers: owner (the super_admin key), support, billing.
platform_tier = rbac_defaults.platform_tier
is_platform_role = rbac_defaults.is_platform_role
is_tenant_admin = rbac_defaults.is_tenant_admin


def _tenant_of(user) -> Optional[str]:
    return getattr(user, "tenant_id", None) or getattr(user, "tenantId", None)


def can_read_all_tenants(user) -> bool:
    """True for platform staff: the owner anywhere, support and billing in the platform tenant."""
    role = getattr(user, "role", None)
    if is_super_admin(role):
        return True
    return is_platform_role(role) and _tenant_of(user) == rbac_defaults.PLATFORM_TENANT_ID


async def has_platform_permission(user, permission: str) -> bool:
    """True when platform staff hold ``permission`` (the owner always does).

    A tenant user never passes, whatever its role documents say, so platform-wide
    routes (licenses, Pending decisions, the tenant list) stay platform-only.
    """
    if is_super_admin(getattr(user, "role", None)):
        return True
    return can_read_all_tenants(user) and await verify_permission(user, permission)


class Permission(str, Enum):
    # Dashboard & reporting
    VIEW_DASHBOARD = "view:dashboard"
    VIEW_REPORTS = "view:reports"
    # Assets
    VIEW_ASSETS = "view:assets"
    MANAGE_ASSETS = "manage:assets"
    # Security & alerts
    VIEW_SECURITY = "view:security"
    MANAGE_SECURITY = "manage:security"
    VIEW_ALERTS = "view:alerts"
    MANAGE_ALERTS = "manage:alerts"
    # Compliance
    VIEW_COMPLIANCE = "view:compliance"
    MANAGE_COMPLIANCE = "manage:compliance"
    # SBOM
    VIEW_SBOM = "view:sbom"
    MANAGE_SBOM = "manage:sbom"
    # Users & roles
    MANAGE_USERS = "manage:users"
    MANAGE_ROLES = "manage:roles"
    # Agents
    VIEW_AGENTS = "view:agents"
    MANAGE_AGENTS = "manage:agents"
    # Settings & billing
    MANAGE_SETTINGS = "manage:settings"
    VIEW_BILLING = "view:billing"
    MANAGE_BILLING = "manage:billing"
    # AI / LLM
    VIEW_AI = "view:ai"
    MANAGE_AI = "manage:ai"
    # ITAM
    VIEW_ITAM = "view:itam"
    MANAGE_ITAM = "manage:itam"

# Helper function to avoid RBACService class instantiation loops
async def verify_permission(user: TokenData, required_permission: str) -> bool:
    if isinstance(user, dict):  # some callers still pass the decoded-claims dict
        user = TokenData(username=user.get("username") or user.get("sub"), role=user.get("role"),
                         tenant_id=user.get("tenant_id") or user.get("tenantId"))
    # Super Admin bypass
    if is_super_admin(user.role):
        return True

    # ACC-01/ACC-02: the role table lives in rbac_defaults and the full answer
    # (defaults plus the tenant's role documents, minus the tenant's switched-off
    # features, spec C6) in granted_permissions, the same resolver /login and /me
    # deliver. Defaults are checked first so the common case needs no database
    # round-trip, except for a permission a tenant's feature switches can remove.
    defaults = rbac_defaults.defaults_for(_rbac_service._normalize_role(user.role or ""))
    if "*" in defaults:
        return True
    if required_permission in defaults:
        if not (tenant_features.applies_to(user.role) and tenant_features.is_switchable(required_permission)):
            return True
        # The role holds it by default, so only the tenant's switches can take it away.
        try:
            enabled = await tenant_features.enabled_features(user.tenant_id, get_database)
        except Exception as exc:  # fail closed: the tenant's switches are unknown
            logger.warning("Tenant feature lookup failed for %s (denying %s): %s",
                           user.tenant_id, required_permission, exc)
            return False
        return bool(tenant_features.narrow([required_permission], enabled))

    if not user.role:
        return False
    try:
        perms = await granted_permissions(get_database(), user.role, user.tenant_id)
    except Exception as exc:  # fail closed: no grant if the role store is unreachable
        logger.warning("Role lookup failed for %s (denying %s): %s", user.role, required_permission, exc)
        return False
    return "*" in perms or required_permission in perms

# Dependency Injection Helper
def require_permission(permission: str):
    async def dependency(user: TokenData = Depends(get_current_user)):
        allowed = await verify_permission(user, permission)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}"
            )
        return user
    return dependency

async def require_super_admin(user: TokenData = Depends(get_current_user)):
    """Platform-wide operations (shared models, server-side tooling) — super-admins only."""
    if not is_super_admin(user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform super-admin access required"
        )
    return user

def require_role(allowed_roles: List[str]):
    async def dependency(user: TokenData = Depends(get_current_user)):
        if is_super_admin(user.role):
            return user
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role not allowed. Required one of: {allowed_roles}"
            )
        return user
    return dependency
