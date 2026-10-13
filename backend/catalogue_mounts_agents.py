"""Agents slice (Phase 76-05): agent console, capabilities, remote access, chat, jobs, service catalog.

``MOUNTS`` guards only routers whose every route is a console (user) route. Most agent
routers also serve agent-key, agent-capable or public routes (enrollment, heartbeat,
downloads, instructions), so they import the named guards below and add them per route;
those agent and public routes never carry a guard (D-02).

Every route here uses ``get_current_user``, so the guards keep the default auth. The
permission strings mirror ``shared/catalogue-access.json``; ``test_catalogue_slice_agents``
fails when the two drift. ``platform_endpoints`` also serves alert rules, data sources and
CSPM findings, so their owning catalogues' guards live here too.
"""
from catalogue_guards import catalogue_exempt, catalogue_guard

AGENTS_READ = ("view:agents",)
AGENTS_WRITE = ("investigate:security", "manage:agents", "manage:compliance", "remediate:agents")
AGENT_CAPABILITIES_READ = ("view:agent_capabilities",)
AGENT_CAPABILITIES_WRITE = ("manage:agents",)
REMOTE_ACCESS_READ = ("view:remote_access",)
REMOTE_ACCESS_WRITE = ("view:remote_access",)
CHAT_READ = ("manage:agents",)
CHAT_WRITE = ("manage:agents",)
JOBS_READ = ("view:jobs",)
JOBS_WRITE = ("manage:automation",)
SERVICE_CATALOG_READ = ("view:service_catalog",)
SERVICE_CATALOG_WRITE = ("manage:automation",)
ALERT_MANAGEMENT_READ = ("view:security",)
ALERT_MANAGEMENT_WRITE = ("manage:security_cases",)
SETTINGS_READ = ("manage:settings",)
SETTINGS_WRITE = ("manage:settings",)
CLOUD_SECURITY_READ = ("view:cloud_security",)
CLOUD_SECURITY_WRITE = ("investigate:security", "manage:security_cases")
SECURITY_AUDIT_READ = ("view:security_audit",)
SECURITY_AUDIT_WRITE = ("investigate:security", "manage:security_cases")

AGENTS_GUARD = catalogue_guard("agents", read=AGENTS_READ, write=AGENTS_WRITE)
AGENT_CAPABILITIES_GUARD = catalogue_guard(
    "agentCapabilities", read=AGENT_CAPABILITIES_READ, write=AGENT_CAPABILITIES_WRITE
)
REMOTE_ACCESS_GUARD = catalogue_guard("remoteAccess", read=REMOTE_ACCESS_READ, write=REMOTE_ACCESS_WRITE)
CHAT_GUARD = catalogue_guard("chat", read=CHAT_READ, write=CHAT_WRITE)
JOBS_GUARD = catalogue_guard("jobs", read=JOBS_READ, write=JOBS_WRITE)
SERVICE_CATALOG_GUARD = catalogue_guard(
    "serviceCatalog", read=SERVICE_CATALOG_READ, write=SERVICE_CATALOG_WRITE
)
ALERT_MANAGEMENT_GUARD = catalogue_guard(
    "alertManagement", read=ALERT_MANAGEMENT_READ, write=ALERT_MANAGEMENT_WRITE
)
SETTINGS_GUARD = catalogue_guard("settings", read=SETTINGS_READ, write=SETTINGS_WRITE)
CLOUD_SECURITY_GUARD = catalogue_guard("cloudSecurity", read=CLOUD_SECURITY_READ, write=CLOUD_SECURITY_WRITE)
SECURITY_AUDIT_GUARD = catalogue_guard("securityAudit", read=SECURITY_AUDIT_READ, write=SECURITY_AUDIT_WRITE)

# Support chat is open to every signed-in user (sidebar badge, global chat window, the
# supportChat view on view:dashboard); each route already scopes to the caller's own
# conversations, so these stay outside the chat catalogue guard.
SUPPORT_OWN_CONVERSATION = catalogue_exempt("self-service: caller's own support conversation")
SUPPORT_PRESENCE = catalogue_exempt("self-service: online status of the caller's support-chat partners")

MOUNTS = {
    ("agent_analyze_endpoints", "router"): AGENTS_GUARD,
    ("agent_quarantine_endpoints", "router"): AGENTS_GUARD,
    ("agent_uptime_endpoints", "router"): AGENTS_GUARD,
    ("jobs_endpoints", "router"): JOBS_GUARD,
}
