"""The only role-to-permission table in the backend (Phase 75, ACC-02).

Every consumer reads this module through ``rbac_service.effective_permissions``:
request-time enforcement (``rbac_utils.verify_permission``), ``RBACService`` and
the permission list delivered by ``/api/auth/login`` and ``/api/auth/me``.
Startup mirrors ``seed_role_documents()`` into the shared ``roles`` documents,
so those documents are a projection of this table, never a second source. A
drift test (Phase 75 plan 05) fails if a second role-to-permission literal
appears elsewhere in ``backend/*.py``.

Pure data and pure helpers: standard library only. This module must not import
``database``, ``fastapi``, ``rbac_service`` or ``rbac_utils`` (``rbac_utils``
imports ``rbac_service`` which imports ``database``; an import here would form a
cycle). Role-name normalization stays in ``RBACService._normalize_role``; every
``normalized_key`` argument below must be an output of that method.
"""
from typing import Dict, FrozenSet, Iterable, List, NamedTuple, Optional, Tuple

SUPER_ADMIN_KEY = "super_admin"

# Spec C1: three platform roles. The owner keeps the internal key super_admin
# ("Platform Owner" in the UI), so every is_super_admin check keeps meaning
# "owner"; support and billing are new, read-only or narrowly writing tiers.
PLATFORM_SUPPORT_KEY = "platform_support"
PLATFORM_BILLING_KEY = "platform_billing"
PLATFORM_ROLE_KEYS: FrozenSet[str] = frozenset({SUPER_ADMIN_KEY, PLATFORM_SUPPORT_KEY, PLATFORM_BILLING_KEY})
_PLATFORM_TIERS: Dict[str, str] = {
    SUPER_ADMIN_KEY: "owner", PLATFORM_SUPPORT_KEY: "support", PLATFORM_BILLING_KEY: "billing",
}
# Platform staff live in this tenant; its context makes the DB wrapper skip tenant scoping.
PLATFORM_TENANT_ID = "platform-admin"
TENANT_ADMIN_KEY = "tenant_admin"

# Keyed by the RBACService._normalize_role output. Tuples are sorted and unique.
ROLE_DEFAULTS: Dict[str, Tuple[str, ...]] = {
    # Tenant administrator (alias: admin, D-01). Excludes manage:tenants (D-06) and the D-03 catalogues.
    "tenant_admin": (
        "control:remote_access", "export:reports", "investigate:security",
        "manage:active_response", "manage:advanced_hunting", "manage:agent_groups",
        "manage:agents", "manage:ai_risks", "manage:android_enterprise", "manage:api_keys",
        "manage:app_catalog", "manage:approvals", "manage:asset_intelligence", "manage:assets",
        "manage:automation", "manage:automl", "manage:autopilot", "manage:branch_sites", "manage:compliance",
        "manage:compliance_evidence", "manage:conditional_access", "manage:config_drift",
        "manage:connectors_hub", "manage:dashboards", "manage:detection_rules",
        "manage:device_config_profiles", "manage:devsecops", "manage:experiments", "manage:fim",
        "manage:finance",
        "manage:firmware_drivers", "manage:itam", "manage:licenses", "manage:mam", "manage:mdm",
        "manage:mlops", "manage:mssp", "manage:patches", "manage:playbooks",
        "manage:procurement", "manage:rbac", "manage:retention_policies", "manage:sbom",
        "manage:sca", "manage:secrets", "manage:security_cases", "manage:security_playbooks",
        "manage:settings", "manage:tracing", "manage:users", "remediate:agents", "request:assets",
        "view:active_response", "view:advanced_bi", "view:advanced_hunting",
        "view:agent_capabilities", "view:agent_groups", "view:agent_logs", "view:agents",
        "view:ai_governance", "view:analytics", "view:android_enterprise", "view:app_catalog",
        "view:approvals", "view:asset_intelligence", "view:assets", "view:attack_path",
        "view:attack_timeline", "view:audit_log", "view:automation", "view:automl",
        "view:autopilot", "view:branch_sites", "view:chaos", "view:cloud_security",
        "view:compliance", "view:conditional_access", "view:config_drift", "view:connectors_hub",
        "view:cxo_dashboard", "view:dashboard", "view:detection_rules", "view:developer_hub",
        "view:device_config_profiles", "view:devsecops", "view:dora_metrics", "view:dspm",
        "view:fim", "view:finops", "view:firmware_drivers", "view:geographic_map",
        "view:governance", "view:insights", "view:integrations", "view:itam", "view:licenses",
        "view:llmops", "view:logs", "view:mam", "view:mdm", "view:mdr", "view:mlops", "view:mssp",
        "view:network", "view:patching", "view:persistence", "view:profile", "view:remote_access",
        "view:reporting", "view:retention_policies", "view:sbom", "view:sca", "view:secrets",
        "view:security", "view:security_audit", "view:security_copilot", "view:service_catalog",
        "view:software_deployment", "view:software_updates", "view:sustainability", "view:swarm",
        "view:threat_hunting", "view:threat_intel", "view:tracing", "view:unified_ops",
        "view:vulnerabilities", "view:web_monitoring", "view:xai", "view:xdr", "view:zero_trust",
    ),
    # Standard platform user: read-only access to core modules.
    "user": (
        "view:agent_capabilities", "view:agents", "view:ai_governance", "view:assets",
        "view:audit_log", "view:automation", "view:cloud_security", "view:compliance",
        "view:dashboard", "view:developer_hub", "view:devsecops", "view:finops", "view:insights",
        "view:logs", "view:mdr", "view:patching", "view:profile", "view:reporting",
        "view:security", "view:threat_hunting", "view:tracing", "view:xdr",
    ),
    # Security analyst: investigation and threat-hunting access.
    "analyst": (
        "investigate:security", "view:agents", "view:assets", "view:attack_path", "view:audit_log",
        "view:compliance", "view:dashboard", "view:devsecops", "view:dspm", "view:logs",
        "view:mdr", "view:profile", "view:reporting", "view:security", "view:threat_hunting",
        "view:threat_intel", "view:tracing", "view:vulnerabilities", "view:xdr",
    ),
    # Deep security investigation with case management.
    "security_analyst": (
        "investigate:security", "manage:security_cases", "view:assets", "view:attack_path",
        "view:audit_log", "view:compliance", "view:dashboard", "view:dspm", "view:logs",
        "view:mdr", "view:profile", "view:security", "view:threat_hunting", "view:threat_intel",
        "view:tracing", "view:vulnerabilities", "view:xdr",
    ),
    # Incident triage and security case management.
    "incident_responder": (
        "investigate:security", "manage:security_cases", "view:agents", "view:assets",
        "view:audit_log", "view:dashboard", "view:logs", "view:mdr", "view:profile",
        "view:security", "view:threat_hunting", "view:xdr",
    ),
    # Read-only access to dashboards and reports.
    "viewer": (
        "view:ai_governance", "view:assets", "view:cloud_security", "view:compliance",
        "view:dashboard", "view:finops", "view:profile", "view:reporting",
    ),
    # ITAM administrator (D-11, D-21): assets, licenses, procurement, finance, users.
    "itam_admin": (
        "manage:assets", "manage:finance", "manage:itam", "manage:licenses", "manage:procurement",
        "manage:users", "view:itam", "view:profile",
    ),
    # ITAM user: views assets and licenses and requests assets.
    "itam_user": (
        "request:assets", "view:assets", "view:itam", "view:licenses", "view:profile",
    ),
    # ITAM viewer: read-only assets and licenses.
    "itam_viewer": (
        "view:assets", "view:itam", "view:licenses", "view:profile",
    ),
    # Platform Support (spec C1): reads every tenant, changes nothing. Every view: permission
    # in shared/catalogue-access.json except the super-admin-only screens and
    # view:remote_access (watching a customer's screen is an action, not a read).
    "platform_support": (
        "view:active_response", "view:advanced_bi", "view:advanced_hunting",
        "view:agent_capabilities", "view:agent_groups", "view:agents", "view:ai_governance",
        "view:analytics", "view:android_enterprise", "view:app_catalog", "view:asset_intelligence",
        "view:assets", "view:attack_path", "view:attack_timeline", "view:audit_log",
        "view:automation", "view:automl", "view:autopilot", "view:branch_sites", "view:chaos",
        "view:cloud_security", "view:compliance", "view:conditional_access", "view:config_drift",
        "view:connectors_hub", "view:cxo_dashboard", "view:dashboard", "view:detection_rules",
        "view:developer_hub", "view:device_config_profiles", "view:devsecops", "view:dora_metrics",
        "view:dspm", "view:fim", "view:finops", "view:firmware_drivers", "view:geographic_map",
        "view:governance", "view:insights", "view:integrations", "view:itam", "view:llmops",
        "view:logs", "view:mam", "view:mdm", "view:mdr", "view:mlops", "view:mssp", "view:network",
        "view:patching", "view:persistence", "view:platform_alerts", "view:profile",
        "view:reporting", "view:retention_policies", "view:sbom", "view:sca", "view:secrets",
        "view:security", "view:security_audit", "view:security_copilot", "view:service_catalog",
        "view:software_deployment", "view:software_updates", "view:sustainability", "view:swarm",
        "view:tenants", "view:threat_hunting", "view:threat_intel", "view:tracing",
        "view:unified_ops", "view:vulnerabilities", "view:web_monitoring", "view:xai", "view:xdr",
        "view:zero_trust",
    ),
    # Platform Billing (spec C1): reads tenants; writes only seat licenses and Pending agents.
    "platform_billing": (
        "manage:pending_agents", "manage:tenant_license", "view:audit_log", "view:platform_alerts",
        "view:platform_cost", "view:profile", "view:tenants",
    ),
}

# D-01: `admin` and `Tenant Admin` carry the identical permission set.
ROLE_ALIASES: Dict[str, str] = {"admin": "tenant_admin"}

# D-03 / D-06: reachable only through the super-admin wildcard, never granted
# by this table to any other role.
SUPER_ADMIN_ONLY_PERMISSIONS: FrozenSet[str] = frozenset({
    # HA/DR backs up and restores the platform database itself, so it is never a tenant screen.
    "manage:backups",
    "manage:pricing",  # service pricing applies to every tenant (QA ISSUE-005, user decision D6)
    "manage:tenants",
    "view:backups",
    "view:federated_learning",
    "view:goal_system",
    "view:jobs",
    "view:predictive_health",
    "view:vector_db",
    "view:webgpu_inference",
})


# Spec C1: held only by the platform roles above, never by a tenant role, and never
# added by a role document (effective_permissions drops them like the set above).
PLATFORM_ONLY_PERMISSIONS: FrozenSet[str] = frozenset({
    "manage:pending_agents",
    "manage:tenant_license",
    "view:platform_alerts",
    "view:platform_cost",
    "view:tenants",
})


# D-14: the one admin-tier definition. A role whose effective permissions hold "*" or any of
# these must pass MFA. Over the built-in table it selects exactly super_admin, tenant_admin
# (and its alias admin), itam_admin, platform_support and platform_billing.
ADMIN_TIER_PERMISSIONS: FrozenSet[str] = frozenset({
    "manage:users",
    "manage:rbac",
    "manage:settings",
    "manage:api_keys",
    "control:remote_access",
}) | PLATFORM_ONLY_PERMISSIONS


def requires_mfa(perms: Iterable[str]) -> bool:
    """True when ``perms`` holds the wildcard or any admin-tier permission (D-14)."""
    return any(p == "*" or p in ADMIN_TIER_PERMISSIONS for p in perms)


class BuiltinRole(NamedTuple):
    key: str
    name: str
    role_id: str
    display_name: Optional[str]
    description: str
    is_editable: bool
    doc_tenant_id: str


# D-13 / D-25: metadata for the shared role documents mirrored at startup.
BUILTIN_ROLES: Tuple[BuiltinRole, ...] = (
    BuiltinRole("super_admin", "Super Admin", "role-super-admin", None,
                "Has all permissions across all tenants.", False, "platform"),
    BuiltinRole("tenant_admin", "Tenant Admin", "role-tenant-admin", None,
                "Administrator for a specific tenant with full permissions except cross-tenant management.",
                False, "all"),
    BuiltinRole("admin", "admin", "role-admin", "Admin",
                "Alias of Tenant Admin with identical permissions.", False, "all"),
    BuiltinRole("analyst", "analyst", "role-analyst", "Analyst",
                "Security analyst with investigation and threat-hunting access.", True, "all"),
    BuiltinRole("security_analyst", "security_analyst", "role-security-analyst", "Security Analyst",
                "Deep security investigation with case management access.", True, "all"),
    BuiltinRole("incident_responder", "incident_responder", "role-incident-responder",
                "Incident Responder", "Incident triage and security case management.", True, "all"),
    BuiltinRole("user", "user", "role-user", "User",
                "Standard platform user with read-only access to core modules.", True, "all"),
    BuiltinRole("viewer", "viewer", "role-viewer", "Viewer",
                "Read-only access to dashboards and reports.", True, "all"),
    BuiltinRole("itam_admin", "itam_admin", "role-itam-admin", "ITAM Admin",
                "IT asset management administrator for assets, licenses, procurement, finance and ITAM users.",
                False, "all"),
    BuiltinRole("itam_user", "itam_user", "role-itam-user", "ITAM User",
                "Views assets and licenses and requests assets.", False, "all"),
    BuiltinRole("itam_viewer", "itam_viewer", "role-itam-viewer", "ITAM Viewer",
                "Read-only access to assets and licenses.", False, "all"),
    BuiltinRole("platform_support", "Platform Support", "role-platform-support", None,
                "Platform staff: reads every tenant and changes nothing.", False, "platform"),
    BuiltinRole("platform_billing", "Platform Billing", "role-platform-billing", None,
                "Platform staff: reads tenants and manages agent seat licenses and Pending agents.",
                False, "platform"),
)


def normalize_role(name: Optional[str]) -> str:
    """Canonicalize a role name to its snake_case key, e.g. 'Super Admin' -> 'super_admin'.

    The single normalization rule (RESEARCH.md Pitfall 3 / ITAM-USR-02);
    ``RBACService._normalize_role`` delegates here. Every super-admin spelling,
    including "platform-admin" and "Platform Owner", folds into super_admin.
    """
    normalized = (name or "").lower().strip().replace(" ", "_").replace("-", "_")
    if normalized in ("superadmin", "platform_admin", "platform_owner"):
        return SUPER_ADMIN_KEY
    return normalized


def platform_tier(role: Optional[str]) -> Optional[str]:
    """"owner", "support" or "billing" for a platform role; None for every tenant role."""
    return _PLATFORM_TIERS.get(normalize_role(role))


def is_platform_role(role: Optional[str]) -> bool:
    return platform_tier(role) is not None


def is_tenant_admin(role: Optional[str]) -> bool:
    """True for the tenant administrator under any spelling (admin, Admin, Tenant Admin)."""
    return canonical_key(normalize_role(role)) == TENANT_ADMIN_KEY


def canonical_key(normalized_key: str) -> str:
    """Resolve a role alias (``admin``) to its table key (``tenant_admin``)."""
    return ROLE_ALIASES.get(normalized_key, normalized_key)


def defaults_for(normalized_key: str) -> Tuple[str, ...]:
    """Built-in permissions for a role.

    ``normalized_key`` must already be an ``RBACService._normalize_role`` output.
    Returns ``("*",)`` for the super-admin key and ``()`` for an unknown role.
    """
    if normalized_key == SUPER_ADMIN_KEY:
        return ("*",)
    return ROLE_DEFAULTS.get(canonical_key(normalized_key), ())


def builtin_role_keys() -> FrozenSet[str]:
    """Every built-in normalized role key: table keys, aliases and super_admin."""
    return frozenset(ROLE_DEFAULTS) | frozenset(ROLE_ALIASES) | {SUPER_ADMIN_KEY}


def seed_role_documents() -> List[dict]:
    """One shared ``roles`` document per built-in role, in BUILTIN_ROLES order."""
    docs: List[dict] = []
    for role in BUILTIN_ROLES:
        doc = {
            "id": role.role_id,
            "name": role.name,
            "description": role.description,
            "permissions": list(defaults_for(role.key)),
            "isEditable": role.is_editable,
            "tenantId": role.doc_tenant_id,
        }
        if role.display_name:
            doc["display_name"] = role.display_name
        docs.append(doc)
    return docs


def implied_closure(perms: Iterable[str]) -> FrozenSet[str]:
    """D-20: add ``view:X`` and ``request:X`` for every ``manage:X``.

    Nothing else is derived: never a ``control:`` string and never anything from
    a ``view:`` string, so ``view:remote_access`` and ``control:remote_access``
    stay independent (Phase 74 D-06).
    """
    closed = set(perms)
    for perm in list(closed):
        if perm.startswith("manage:"):
            suffix = perm[len("manage:"):]
            closed.add("view:" + suffix)
            closed.add("request:" + suffix)
    return frozenset(closed)


def deliverable_closure(perms: Iterable[str], vocabulary: Iterable[str]) -> List[str]:
    """D-11: ``perms`` plus the ``view:X``/``request:X`` implied by each ``manage:X``, as a list.

    The input keeps its order (de-duplicated); the derived strings follow, sorted, and
    only those that are in ``vocabulary`` (so an unknown resource adds nothing). Uses the
    same ``implied_closure`` rule as ``ceiling_allows``: never a ``control:`` string and
    nothing derived from a ``view:`` string (PROH-77-01). Pure, standard library only.
    """
    given = list(dict.fromkeys(perms))
    derived = implied_closure(given) - set(given)
    return given + sorted(derived & set(vocabulary))


def ceiling_allows(caller_perms: Iterable[str], target_perms: Iterable[str]) -> bool:
    """True when a caller holding ``caller_perms`` may hand out ``target_perms``.

    A caller with ``*`` may assign anything; otherwise the target set must be a
    subset of the caller's closure. The super-admin tier is decided by role name
    in the callers, never by ``*`` here (D-20 rule 1).
    """
    caller = set(caller_perms)
    if "*" in caller:
        return True
    return set(target_perms) <= implied_closure(caller)
