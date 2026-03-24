from fastapi import HTTPException, status, Depends
from authentication_service import get_current_user
from auth_types import TokenData
from database import get_database
from typing import List, Optional

class RBACService:
    def __init__(self):
        # Default roles and permissions if not in DB
        self.default_roles = {
            "super_admin": ["*"], # All permissions
            "admin": [
                "view:dashboard", "view:cxo_dashboard", "view:reporting", "export:reports",
                "view:agents", "view:software_deployment", "view:agent_logs", "remediate:agents",
                "view:assets", "view:patching", "manage:patches", "view:security",
                "manage:security_cases", "manage:security_playbooks", "investigate:security",
                "view:compliance", "manage:compliance_evidence", "view:ai_governance",
                "manage:ai_risks", "manage:settings", "view:cloud_security", "view:finops",
                "view:audit_log", "manage:rbac", "manage:api_keys", "view:logs",
                "view:threat_hunting", "view:profile", "view:automation", "manage:automation",
                "view:devsecops", "view:developer_hub", "view:insights", "view:tracing",
                "view:dspm", "view:attack_path", "view:service_catalog", "view:dora_metrics",
                "view:chaos", "view:network", "manage:pricing", "manage:playbooks",
                "view:software_updates", "view:sbom", "manage:sbom"
            ],
            "Tenant Admin": [
                "view:dashboard", "view:cxo_dashboard", "view:reporting", "export:reports",
                "view:agents", "view:software_deployment", "view:agent_logs", "remediate:agents",
                "view:assets", "view:patching", "manage:patches", "view:security",
                "manage:security_cases", "manage:security_playbooks", "investigate:security",
                "view:compliance", "manage:compliance_evidence", "view:ai_governance",
                "manage:ai_risks", "manage:settings", "manage:tenants", "view:cloud_security", "view:finops",
                "view:audit_log", "manage:rbac", "manage:api_keys", "view:logs",
                "view:threat_hunting", "view:profile", "view:automation", "manage:automation",
                "view:devsecops", "view:developer_hub", "view:insights", "view:tracing",
                "view:dspm", "view:attack_path", "view:service_catalog", "view:dora_metrics",
                "view:chaos", "view:network", "manage:pricing", "manage:playbooks",
                "view:software_updates", "view:sbom", "manage:sbom"
            ],
            "user": [
                "view:dashboard", "view:reporting", "view:agents", "view:assets",
                "view:patching", "view:security", "view:compliance", "view:ai_governance",
                "view:cloud_security", "view:finops", "view:audit_log", "view:logs",
                "view:threat_hunting", "view:profile", "view:automation", "view:devsecops",
                "view:developer_hub", "view:insights", "view:tracing"
            ],
            "viewer": [
                "view:dashboard", "view:reporting", "view:assets", "view:compliance",
                "view:ai_governance", "view:cloud_security", "view:finops"
            ]
        }

    async def get_user_permissions(self, user: TokenData) -> List[str]:
        """Fetch permissions for the current user based on their role"""
        # FIX: Allow 'superadmin' (lowercase) which is what the frontend/auth service is providing
        if user.role in ["super_admin", "Super Admin", "superadmin"]:
            return ["*"]
        
        db = get_database()
        # Try to find role in DB first (for custom roles scoped to tenant)
        role_doc = await db.roles.find_one({"name": user.role, "tenantId": user.tenant_id})
        
        # Fallback to global role definition in DB (e.g. Tenant Admin uses 'all' or 'platform')
        if not role_doc:
            role_doc = await db.roles.find_one({"name": user.role, "tenantId": "all"})
            
        if not role_doc:
            role_doc = await db.roles.find_one({"name": user.role, "tenantId": "platform"})
            
        if not role_doc:
            # Absolute fallback to in-memory default roles
            return self.default_roles.get(user.role, [])
        
        return role_doc.get("permissions", [])

    def has_permission(self, required_permission: str):
        """Dependency factory to check for a specific permission"""
        async def dependency(user: TokenData = Depends(get_current_user)):
            permissions = await self.get_user_permissions(user)
            
            if "*" in permissions:
                return user
                
            if required_permission not in permissions:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Missing required permission: {required_permission}"
                )
            return user
        return dependency

    def require_role(self, allowed_roles: List[str]):
        """Dependency factory to check for specific roles"""
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

rbac_service = RBACService()
