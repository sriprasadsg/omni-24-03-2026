from fastapi import HTTPException, status, Depends
from authentication_service import get_current_user
from auth_types import TokenData
from database import get_database
from typing import Dict, List

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
