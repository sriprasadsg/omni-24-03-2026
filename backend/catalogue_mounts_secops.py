"""SecOps slice (Phase 76-07): detection and response catalogues of "Security (SecOps)".

``MOUNTS`` guards every router whose user routes all belong to one catalogue. Routers that
also serve public, agent-capable or other-catalogue routes (EDR ingest, deception webhook,
autonomous-response tasks, alert ingest, security cases, AI threat hunting) import the named
guards below and add them per route; those public and agent routes never carry a guard (D-02).

Read permissions (view:X or its manage: twin, D-03) and write strings mirror
``shared/catalogue-access.json``; ``test_catalogue_slice_secops`` fails when the two drift.
Writes keep the strings the routes already require (Pitfall 2): nothing here demands
``manage:security``, which tenant_admin does not hold.
"""
from catalogue_guards import catalogue_guard
from catalogue_mounts_agents import ALERT_MANAGEMENT_GUARD, SECURITY_AUDIT_GUARD, SETTINGS_GUARD
from catalogue_mounts_assets import VULNERABILITY_GUARD

# Re-exported so the route files import every SecOps guard from one place.
__all__ = [
    "ALERT_MANAGEMENT_GUARD", "SECURITY_AUDIT_GUARD", "SETTINGS_GUARD", "VULNERABILITY_GUARD",
    "SECURITY_GUARD", "EDR_GUARD", "DECEPTION_GUARD", "XDR_GUARD",
    "INCIDENT_RESPONSE_GUARD", "INCIDENT_IMPACT_GUARD", "THREAT_HUNTING_GUARD",
    "THREAT_INTEL_GUARD", "MOUNTS",
]

# Console routes of /api/security/* (IP bans, key generation, encrypt) share the "security" catalogue.
SECURITY_GUARD = catalogue_guard(
    "security", read=("view:security",), write=("manage:security_cases", "manage:settings")
)
# /api/edr (telemetry console routes) and /api/response (autonomous response) are both "edr".
EDR_GUARD = catalogue_guard(
    "edr",
    read=("view:security",),
    write=("investigate:security", "manage:active_response", "manage:security_cases"),
)
DECEPTION_GUARD = catalogue_guard("deception", read=("view:security",), write=("manage:security_cases",))
XDR_GUARD = catalogue_guard("xdr", read=("view:xdr",), write=("investigate:security", "manage:security_cases"))
INCIDENT_RESPONSE_GUARD = catalogue_guard(
    "incidentResponse", read=("investigate:security",), write=("investigate:security",)
)
INCIDENT_IMPACT_GUARD = catalogue_guard(
    "incidentImpact", read=("investigate:security",), write=("investigate:security",)
)
THREAT_HUNTING_GUARD = catalogue_guard(
    "threatHunting", read=("view:threat_hunting",), write=("view:threat_hunting",)
)
THREAT_INTEL_GUARD = catalogue_guard(
    "threatIntelligence", read=("view:threat_intel",), write=("view:threat_intel",)
)

_INVESTIGATE = ("investigate:security",)
_SECURITY_READ = ("view:security",)

MOUNTS = {
    # --- Detection family ---------------------------------------------------------------
    # alert_endpoints (agent-capable POST /api/alerts) and threat_endpoints (threat hunt +
    # reputation) are guarded per route; every router below is user-authenticated end to end.
    ("siem_endpoints", "router"): catalogue_guard(
        "siem", read=_SECURITY_READ, write=("manage:security_cases", "manage:settings")
    ),
    ("mitre_endpoints", "router"): catalogue_guard("mitreAttack", read=_SECURITY_READ, write=_INVESTIGATE),
    ("threat_intel_endpoints", "router"): THREAT_INTEL_GUARD,
    ("security_intel_status_endpoints", "router"): catalogue_guard(
        "securityIntelConnectors", read=_SECURITY_READ, write=("manage:settings",)
    ),
    ("correlation_endpoints", "router"): catalogue_guard(
        "correlations", read=_SECURITY_READ, write=("manage:security_cases", "view:security")
    ),
    ("detection_rules_endpoints", "router"): catalogue_guard(
        "detectionRules", read=("view:detection_rules",), write=("manage:security_cases",)
    ),
    ("advanced_hunting_endpoints", "router"): catalogue_guard(
        "advancedHunting", read=("view:advanced_hunting",), write=_INVESTIGATE
    ),
    ("connectors_hub_endpoints", "router"): catalogue_guard(
        "connectorsHub", read=("view:connectors_hub",), write=("manage:settings",)
    ),
    ("security_copilot_endpoints", "router"): catalogue_guard(
        "securityCopilot", read=("view:security_copilot",), write=_INVESTIGATE
    ),
    ("binary_analysis_endpoints", "router"): catalogue_guard("yaraRules", read=_SECURITY_READ, write=_INVESTIGATE),
    # --- Response family ----------------------------------------------------------------
    ("mdr_endpoints", "router"): catalogue_guard("mdr", read=("view:mdr",), write=_INVESTIGATE),
    ("incident_warroom_endpoints", "router"): catalogue_guard(
        "incidentWarRoom", read=_INVESTIGATE, write=_INVESTIGATE
    ),
    ("ndr_endpoints", "router"): catalogue_guard(
        "ndr", read=_SECURITY_READ, write=("investigate:security", "manage:settings")
    ),
    ("ot_ics_endpoints", "router"): catalogue_guard(
        "ndr", read=_SECURITY_READ, write=("investigate:security", "manage:settings")
    ),
    ("ueba_endpoints", "router"): catalogue_guard("ueba", read=_SECURITY_READ, write=_INVESTIGATE),
    ("ueba_service", "router"): catalogue_guard("ueba", read=_SECURITY_READ, write=_INVESTIGATE),
    ("itdr_endpoints", "router"): catalogue_guard("ueba", read=_SECURITY_READ, write=_INVESTIGATE),
    ("insider_threat_endpoints", "router"): catalogue_guard(
        "insiderThreat", read=_SECURITY_READ, write=("investigate:security", "manage:settings")
    ),
    ("email_security_endpoints", "router"): catalogue_guard(
        "emailSecurity", read=_SECURITY_READ, write=("manage:security_cases", "manage:settings")
    ),
    ("active_response_endpoints", "router"): catalogue_guard(
        "activeResponse", read=("view:active_response",), write=("manage:active_response",)
    ),
    ("fim_endpoints", "router"): catalogue_guard("fimMonitoring", read=("view:fim",), write=("manage:agents",)),
    ("config_drift_endpoints", "router"): catalogue_guard(
        "configDrift", read=("view:config_drift",), write=("remediate:agents",)
    ),
    ("persistence_endpoints", "router"): catalogue_guard(
        "persistenceDetection", read=("view:persistence",), write=_INVESTIGATE
    ),
    ("simulation_endpoints", "router"): catalogue_guard(
        "securitySimulation", read=_SECURITY_READ, write=("remediate:agents",)
    ),
    ("agent_group_endpoints", "router"): catalogue_guard(
        "agentGroups", read=("view:agent_groups",), write=("manage:agents",)
    ),
    ("ip_ban_endpoints", "router"): SECURITY_GUARD,
}
