from enum import Enum
from typing import List, Optional
from fastapi import HTTPException, status, Depends
from auth_types import TokenData
from authentication_service import get_current_user
from database import get_database

# Single source of truth for elevated-admin role variants
_SUPER_ADMIN_ROLES: frozenset[str] = frozenset({"super_admin", "Super Admin", "superadmin", "platform-admin"})


def is_super_admin(role: Optional[str]) -> bool:
    """Return True if the given role string represents a super-admin."""
    return role in _SUPER_ADMIN_ROLES


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
    if is_super_admin(user.role):
        return True
        
    db = get_database()
    
    # 1. Check DB Roles first
    if user.role:
        role_doc = await db.roles.find_one({"name": user.role, "tenantId": user.tenant_id})
        if role_doc:
            perms = role_doc.get("permissions", [])
            if "*" in perms or required_permission in perms:
                return True

    # 2. Fallback to hardcoded defaults — kept in sync with rbac_service.default_roles
    DEFAULT_PERMISSIONS: dict[str, list[str]] = {
        # Super-admin tier (all variants) — wildcard bypass
        "Super Admin":    ["*"],
        "super_admin":    ["*"],
        "superadmin":     ["*"],
        "platform-admin": ["*"],
        # Tenant-scoped admin
        "admin": [
            "view:dashboard", "view:cxo_dashboard", "view:reporting", "export:reports",
            "view:agents", "view:agent_capabilities", "view:software_deployment",
            "view:agent_logs", "remediate:agents", "view:assets", "view:patching",
            "manage:patches", "view:security", "manage:security_cases",
            "manage:security_playbooks", "investigate:security", "view:compliance",
            "manage:compliance", "manage:compliance_evidence", "view:ai_governance",
            "manage:ai_risks", "manage:settings", "view:cloud_security", "view:finops",
            "view:audit_log", "manage:rbac", "manage:api_keys", "view:logs",
            "view:threat_hunting", "view:profile", "view:automation", "manage:automation",
            "view:devsecops", "view:developer_hub", "view:insights", "view:tracing",
            "view:dspm", "view:attack_path", "view:service_catalog", "view:dora_metrics",
            "view:chaos", "view:network", "manage:pricing", "manage:playbooks",
            "view:software_updates", "view:sbom", "manage:sbom", "view:mdr", "view:xdr",
            "view:secrets", "manage:agents", "view:approvals", "view:remote_access",
        ],
        "Tenant Admin": [
            "view:dashboard", "view:cxo_dashboard", "view:reporting", "export:reports",
            "view:agents", "view:agent_capabilities", "view:software_deployment",
            "view:agent_logs", "remediate:agents", "view:assets", "view:patching",
            "manage:patches", "view:security", "manage:security_cases",
            "manage:security_playbooks", "investigate:security", "view:compliance",
            "manage:compliance", "manage:compliance_evidence", "view:ai_governance",
            "manage:ai_risks", "manage:settings", "manage:tenants", "view:cloud_security",
            "view:finops", "view:audit_log", "manage:rbac", "manage:api_keys", "view:logs",
            "view:threat_hunting", "view:profile", "view:automation", "manage:automation",
            "view:devsecops", "manage:devsecops", "view:developer_hub", "view:insights",
            "view:tracing", "view:dspm", "view:attack_path", "view:service_catalog",
            "view:dora_metrics", "view:chaos", "view:network", "manage:pricing",
            "manage:playbooks", "view:software_updates", "view:sbom", "manage:sbom",
            "view:mdr", "view:xdr", "view:agent_capabilities", "manage:agents",
            "view:unified_ops", "view:advanced_bi", "view:sustainability",
            "view:threat_intel", "view:vulnerabilities", "view:security_audit",
            "view:mlops", "view:llmops", "view:automl", "manage:experiments",
            "view:xai", "view:governance", "view:swarm", "view:integrations",
            "view:secrets", "manage:secrets", "view:approvals", "manage:approvals", "view:remote_access",
        ],
        "tenant_admin": [],  # normalized variant — resolved via Tenant Admin above
        # Standard user
        "user": [
            "view:dashboard", "view:reporting", "view:agents", "view:agent_capabilities",
            "view:assets", "view:patching", "view:security", "view:compliance",
            "view:ai_governance", "view:cloud_security", "view:finops", "view:audit_log",
            "view:logs", "view:threat_hunting", "view:profile", "view:automation",
            "view:devsecops", "view:developer_hub", "view:insights", "view:tracing",
            "view:mdr", "view:xdr",
        ],
        # Analyst — security-focused read + investigate access
        "analyst": [
            "view:dashboard", "view:reporting", "view:agents", "view:assets",
            "view:security", "investigate:security", "view:compliance",
            "view:threat_hunting", "view:threat_intel", "view:vulnerabilities",
            "view:audit_log", "view:logs", "view:attack_path", "view:dspm",
            "view:mdr", "view:xdr", "view:devsecops", "view:tracing",
            "view:profile",
        ],
        "Analyst": [],  # resolved via analyst above
        "security_analyst": [
            "view:dashboard", "view:security", "investigate:security",
            "manage:security_cases", "view:threat_hunting", "view:threat_intel",
            "view:vulnerabilities", "view:attack_path", "view:audit_log",
            "view:logs", "view:mdr", "view:xdr", "view:dspm", "view:tracing",
            "view:compliance", "view:assets", "view:profile",
        ],
        "incident_responder": [
            "view:dashboard", "view:security", "investigate:security",
            "manage:security_cases", "view:threat_hunting", "view:audit_log",
            "view:logs", "view:mdr", "view:xdr", "view:profile",
            "view:agents", "view:assets",
        ],
        # Read-only
        "viewer": [
            "view:dashboard", "view:reporting", "view:assets", "view:compliance",
            "view:ai_governance", "view:cloud_security", "view:finops", "view:profile",
        ],
    }

    effective_role = user.role or ""
    # Normalize tenant_admin → Tenant Admin for lookup
    if effective_role == "tenant_admin":
        effective_role = "Tenant Admin"
    # Normalize analyst variants
    if effective_role == "Analyst":
        effective_role = "analyst"

    perms = DEFAULT_PERMISSIONS.get(effective_role, [])
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
        if is_super_admin(user.role):
            return user
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role not allowed. Required one of: {allowed_roles}"
            )
        return user
    return dependency
