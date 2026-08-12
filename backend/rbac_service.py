from fastapi import HTTPException, status, Depends
from authentication_service import get_current_user
from auth_types import TokenData
from database import get_database
from typing import List

class RBACService:
    def __init__(self):
        # Default roles and permissions if not in DB
        self.default_roles = {
            "super_admin": ["*"], # All permissions
            "admin": [
                "manage:assets", # Added for ITAM Phase 56-01
                "view:itam", # Added for ITAM Phase 61-01
                "manage:itam", # Added for ITAM Phase 61-01
                "view:dashboard", "view:cxo_dashboard", "view:reporting", "export:reports",
                "view:agents", "view:agent_capabilities", "view:software_deployment", "view:agent_logs", "remediate:agents",
                "view:assets", "view:patching", "manage:patches", "view:security",
                "manage:security_cases", "manage:security_playbooks", "investigate:security",
                "view:compliance", "manage:compliance_evidence", "view:ai_governance",
                "manage:ai_risks", "manage:settings", "view:cloud_security", "view:finops",
                "view:audit_log", "manage:rbac", "manage:api_keys", "view:logs",
                "view:threat_hunting", "view:profile", "view:automation", "manage:automation",
                "view:devsecops", "view:developer_hub", "view:insights", "view:tracing",
                "view:dspm", "view:attack_path", "view:service_catalog", "view:dora_metrics",
                "view:chaos", "view:network", "manage:pricing", "manage:playbooks",
                "view:software_updates", "view:sbom", "manage:sbom",
                "view:mdr", "view:xdr"
            ],
            "Tenant Admin": [
                "manage:assets", # Added for ITAM Phase 56-01
                "view:itam", # Added for ITAM Phase 61-01
                "manage:itam", # Added for ITAM Phase 61-01
                "view:dashboard", "view:cxo_dashboard", "view:reporting", "export:reports",
                "view:agents", "view:agent_capabilities", "view:software_deployment", "view:agent_logs", "remediate:agents",
                "view:assets", "view:patching", "manage:patches", "view:security",
                "manage:security_cases", "manage:security_playbooks", "investigate:security",
                "view:compliance", "manage:compliance_evidence", "view:ai_governance",
                "manage:ai_risks", "manage:settings", "manage:tenants", "view:cloud_security", "view:finops",
                "view:audit_log", "manage:rbac", "manage:api_keys", "view:logs",
                "view:threat_hunting", "view:profile", "view:automation", "manage:automation",
                "view:devsecops", "view:developer_hub", "view:insights", "view:tracing",
                "view:dspm", "view:attack_path", "view:service_catalog", "view:dora_metrics",
                "view:chaos", "view:network", "manage:pricing", "manage:playbooks",
                "view:software_updates", "view:sbom", "manage:sbom",
                "view:mdr", "view:xdr"
            ],
            "user": [
                "view:dashboard", "view:reporting", "view:agents", "view:agent_capabilities", "view:assets",
                "view:patching", "view:security", "view:compliance", "view:ai_governance",
                "view:cloud_security", "view:finops", "view:audit_log", "view:logs",
                "view:threat_hunting", "view:profile", "view:automation", "view:devsecops",
                "view:developer_hub", "view:insights", "view:tracing",
                "view:mdr", "view:xdr"
            ],
            "viewer": [
                "view:dashboard", "view:reporting", "view:assets", "view:compliance",
                "view:ai_governance", "view:cloud_security", "view:finops", "view:profile",
            ],
            # Analyst — security-focused investigation access
            "analyst": [
                "view:dashboard", "view:reporting", "view:agents", "view:assets",
                "view:security", "investigate:security", "view:compliance",
                "view:threat_hunting", "view:threat_intel", "view:vulnerabilities",
                "view:audit_log", "view:logs", "view:attack_path", "view:dspm",
                "view:mdr", "view:xdr", "view:devsecops", "view:tracing", "view:profile",
            ],
            "Analyst": [],  # alias — normalized to "analyst" by _normalize_role
            # Security analyst — deeper threat response
            "security_analyst": [
                "view:dashboard", "view:security", "investigate:security",
                "manage:security_cases", "view:threat_hunting", "view:threat_intel",
                "view:vulnerabilities", "view:attack_path", "view:audit_log",
                "view:logs", "view:mdr", "view:xdr", "view:dspm", "view:tracing",
                "view:compliance", "view:assets", "view:profile",
            ],
            # Incident responder — triage and case management
            "incident_responder": [
                "view:dashboard", "view:security", "investigate:security",
                "manage:security_cases", "view:threat_hunting", "view:audit_log",
                "view:logs", "view:mdr", "view:xdr", "view:profile",
                "view:agents", "view:assets",
            ],
            # ITAM-specific roles (ITAM-USR-02) — scoped access to the ITAM
            # console independent of the broader security-platform roles above.
            "itam_admin": [
                "manage:assets", "manage:licenses", "manage:users",
                "view:itam", "manage:procurement", "manage:finance",
            ],
            "itam_user": [
                "view:assets", "view:licenses", "view:itam", "request:assets",
            ],
            "itam_viewer": [
                "view:assets", "view:licenses", "view:itam",
            ],
        }

    @staticmethod
    def _normalize_role(name: str) -> str:
        """Canonicalize role names to snake_case, e.g. 'Super Admin' / 'superadmin' → 'super_admin'.

        Single source of truth for role normalization (RESEARCH.md Pitfall 3 /
        ITAM-USR-02): "platform-admin" is treated as a super-admin role variant
        everywhere else in the codebase (auth_roles.SUPER_ROLES, rbac_utils),
        but previously normalized to the distinct key "platform_admin" here —
        the "platform-admin gap" — instead of "super_admin". Folding it in here
        means every caller that routes through this method (has_permission,
        require_role, get_user_permissions, rbac_utils.is_super_admin) now
        agrees on a single answer for platform-admin callers.
        """
        normalized = (name or "").lower().strip().replace(" ", "_").replace("-", "_")
        if normalized in ("superadmin", "platform_admin"):
            return "super_admin"
        return normalized

    def get_permissions_for_role(self, role: str) -> List[str]:
        """Static (non-DB) permission list for a role name — for frontend UI role-matrix rendering.

        Looks up `default_roles` only (no DB call), trying the raw role string
        first and falling back to its normalized form so Title-Case variants
        (e.g. the /api/roles stub's "Admin"/"User"/"Viewer") resolve correctly.
        For actual request-time enforcement use `has_permission`/`require_role`/
        `get_user_permissions`, which also consult the `roles` collection.
        """
        normalized = self._normalize_role(role)
        if normalized == "super_admin":
            return ["*"]
        return self.default_roles.get(role) or self.default_roles.get(normalized) or []

    def can_assign_role(self, caller_role: str, target_role: str) -> bool:
        """Only super-admins may assign the super-admin role to a user (ITAM-USR-02 T-64-04)."""
        if self._normalize_role(target_role) == "super_admin":
            return self._normalize_role(caller_role) == "super_admin"
        return True

    async def get_user_permissions(self, user: TokenData) -> List[str]:
        """Fetch permissions for the current user based on their role"""
        normalized = self._normalize_role(user.role)
        if normalized == "super_admin":
            return ["*"]

        db = get_database()
        # Try exact match scoped to tenant first, then platform-wide fallbacks
        role_doc = (
            await db.roles.find_one({"name": user.role, "tenantId": user.tenant_id})
            or await db.roles.find_one({"name": user.role, "tenantId": "all"})
            or await db.roles.find_one({"name": user.role, "tenantId": "platform"})
            # Also try normalized name for DB records that may use snake_case
            or await db.roles.find_one({"name": normalized, "tenantId": user.tenant_id})
            or await db.roles.find_one({"name": normalized, "tenantId": "all"})
        )

        if not role_doc:
            # Absolute fallback to in-memory default roles (try both raw and normalized)
            return (
                self.default_roles.get(user.role)
                or self.default_roles.get(normalized)
                or []
            )

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
        # Normalize the allowed list once so callers don't need to enumerate variants
        normalized_allowed = {self._normalize_role(r) for r in allowed_roles}

        async def dependency(user: TokenData = Depends(get_current_user)):
            if self._normalize_role(user.role) == "super_admin":
                return user
            if self._normalize_role(user.role) not in normalized_allowed and user.role not in allowed_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Role not allowed. Required one of: {allowed_roles}"
                )
            return user
        return dependency

rbac_service = RBACService()
