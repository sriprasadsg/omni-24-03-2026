from enum import Enum
from typing import List, Optional
from fastapi import HTTPException, status, Depends
from auth_types import TokenData
from authentication_service import get_current_user
from database import get_database


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

# Helper function to avoid RBACService class instantiation loops
async def verify_permission(user: TokenData, required_permission: str) -> bool:
    # Super Admin bypass
    if user.role in ["super_admin", "Super Admin", "superadmin", "platform-admin"]:
        return True
        
    db = get_database()
    
    # 1. Check DB Roles first
    if user.role:
        role_doc = await db.roles.find_one({"name": user.role, "tenantId": user.tenant_id})
        if role_doc:
            perms = role_doc.get("permissions", [])
            if "*" in perms or required_permission in perms:
                return True

    # 2. Fallback to hardcoded defaults (copied from rbac_service to avoid import)
    # Ideally should be in a shared constant file
    DEFAULT_PERMISSIONS = {
        "admin": ["*"], 
        "Tenant Admin": ["*"], # Simplified for now
        "user": ["view:dashboard", "view:assets", "view:security"],
        "viewer": ["view:dashboard"]
    }
    
    perms = DEFAULT_PERMISSIONS.get(user.role, [])
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

def require_role(allowed_roles: List[str]):
    async def dependency(user: TokenData = Depends(get_current_user)):
        if user.role in ["super_admin", "Super Admin", "superadmin"]:
            return user
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role not allowed. Required one of: {allowed_roles}"
            )
        return user
    return dependency
