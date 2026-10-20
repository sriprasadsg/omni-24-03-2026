"""Settings and platform-operations slice (Phase 76-10): settings, system health, cache, maintenance,
HA/DR, secrets, retention, geo-security, cloud integrations, integrations, MSSP, fleet views,
native security ops, ticketing, notifications, data warehouse/ETL and webhooks.

``MOUNTS`` guards every router whose routes are all user routes of one catalogue. The routers
that mix catalogues, carry public receivers or serve other modules' routes import the named
guards below and add them per route; public, agent-only and out-of-scope routes never carry a
guard (D-02, D-01).

Read permissions and write strings mirror ``shared/catalogue-access.json``;
``test_catalogue_slice_settings_ops`` fails when the two drift.
"""
from fastapi import Depends, Request

from api_key_auth import get_current_user_or_api_key
from auth_types import TokenData
from catalogue_guards import catalogue_guard, check_catalogue_access

__all__ = [
    "SETTINGS_GUARD", "SYSTEM_HEALTH_GUARD", "API_STATUS_GUARD", "GEO_SECURITY_GUARD",
    "INTEGRATIONS_GUARD", "NOTIFICATIONS_GUARD", "TICKET_WEBHOOKS_GUARD", "WEBHOOKS_GUARD",
    "WEBHOOKS_SESSION_GUARD",
    "AGENTS_GUARD", "MOUNTS",
]

_SETTINGS = ("manage:settings",)

# --- Settings and platform operations ---------------------------------------------------
SETTINGS_GUARD = catalogue_guard("settings", read=_SETTINGS, write=_SETTINGS)
SYSTEM_HEALTH_GUARD = catalogue_guard("systemHealth", read=_SETTINGS, write=_SETTINGS)
API_STATUS_GUARD = catalogue_guard("apiStatus", read=_SETTINGS, write=_SETTINGS)
GEO_SECURITY_GUARD = catalogue_guard("geoSecurity", read=_SETTINGS, write=_SETTINGS)
CLOUD_INTEGRATIONS_GUARD = catalogue_guard("cloudIntegrations", read=_SETTINGS, write=_SETTINGS)
HADR_GUARD = catalogue_guard("hadr", read=("view:backups",), write=("manage:backups",))  # platform only
RETENTION_POLICY_GUARD = catalogue_guard("retentionPolicy", read=_SETTINGS, write=_SETTINGS)
RETENTION_POLICIES_GUARD = catalogue_guard(
    "retentionPolicies", read=("view:retention_policies",), write=_SETTINGS
)
SECRETS_GUARD = catalogue_guard(
    "secretsManagement", read=_SETTINGS, write=("manage:secrets", "view:secrets")
)

# --- Integrations, ticketing, notifications, webhooks -----------------------------------
INTEGRATIONS_GUARD = catalogue_guard(
    "integrations", read=_SETTINGS, write=("manage:security_cases", "manage:settings")
)
TICKETING_GUARD = catalogue_guard(
    "ticketing", read=_SETTINGS, write=("investigate:security", "manage:settings")
)
TICKET_WEBHOOKS_GUARD = catalogue_guard("ticketWebhooks", read=_SETTINGS, write=_SETTINGS)
NOTIFICATIONS_GUARD = catalogue_guard(
    "notifications", read=("view:dashboard",), write=("manage:settings", "view:dashboard")
)
WEBHOOKS_SESSION_GUARD = catalogue_guard("webhooks", read=_SETTINGS, write=_SETTINGS)

# Four webhook management routes (list, create, delete, deliveries) also accept a tenant
# integration key (role "api-integration"), which tenant admins issue for exactly this job and
# which has no role document to hold manage:settings. That identity keeps working as today; every
# other caller (sessions and user-scoped API keys) goes through the catalogue check.
_INTEGRATION_KEY_ROLE = "api-integration"


def _webhooks_guard_with_integration_keys():
    meta = WEBHOOKS_SESSION_GUARD.__catalogue_guard__

    async def _require_webhooks(
        request: Request, user: TokenData = Depends(get_current_user_or_api_key)
    ) -> TokenData:
        if getattr(user, "role", "") == _INTEGRATION_KEY_ROLE:
            return user
        await check_catalogue_access(user, request.method, tuple(meta["read"]), tuple(meta["write"]))
        return user

    _require_webhooks.__catalogue_guard__ = dict(meta)  # type: ignore[attr-defined]
    return _require_webhooks


WEBHOOKS_GUARD = _webhooks_guard_with_integration_keys()

# --- Fleet, MSSP, native security ops, data warehouse -----------------------------------
FLEET_GEO_GUARD = catalogue_guard("fleetGeoMap", read=("manage:agents",), write=("manage:agents",))
FLEET_OBSERVABILITY_GUARD = catalogue_guard(
    "fleetObservability", read=("manage:agents",), write=("manage:agents",)
)
MSSP_GUARD = catalogue_guard("msspMonitoring", read=("view:mssp",), write=("manage:mssp",))
NATIVE_SECURITY_GUARD = catalogue_guard(
    "nativeSecurity", read=("manage:active_response",), write=("manage:active_response",)
)
DATA_WAREHOUSE_GUARD = catalogue_guard(
    "dataWarehouse", read=("view:reporting",), write=("manage:settings", "view:reporting")
)

# agents catalogue: only the agent location-history read (a route of the agent detail view)
AGENTS_GUARD = catalogue_guard(
    "agents",
    read=("view:agents",),
    write=("investigate:security", "manage:agents", "manage:compliance", "remediate:agents"),
)

MOUNTS = {
    ("settings_endpoints", "router"): SETTINGS_GUARD,
    ("email_endpoints", "router"): SETTINGS_GUARD,
    ("system_health_endpoints", "router"): SYSTEM_HEALTH_GUARD,
    ("cache_endpoints", "router"): SYSTEM_HEALTH_GUARD,
    ("maintenance_endpoints", "router"): SYSTEM_HEALTH_GUARD,
    ("hadr_endpoints", "router"): HADR_GUARD,
    ("secrets_endpoints", "router"): SECRETS_GUARD,
    ("retention_endpoints", "router"): RETENTION_POLICY_GUARD,
    ("retention_tiers_endpoints", "router"): RETENTION_POLICIES_GUARD,
    ("geo_security_endpoints", "router"): GEO_SECURITY_GUARD,
    ("cloud_integrations_endpoints", "router"): CLOUD_INTEGRATIONS_GUARD,
    ("integration_endpoints", "router"): INTEGRATIONS_GUARD,
    ("integrations_v2", "router"): INTEGRATIONS_GUARD,
    ("ticketing_endpoints", "router"): TICKETING_GUARD,
    ("notification_endpoints", "router"): NOTIFICATIONS_GUARD,
    ("mssp_endpoints", "router"): MSSP_GUARD,
    ("agent_fleet_geo_endpoints", "router"): FLEET_GEO_GUARD,
    ("agent_fleet_observability_endpoints", "router"): FLEET_OBSERVABILITY_GUARD,
    ("native_security_ops_endpoints", "router"): NATIVE_SECURITY_GUARD,
    ("etl_endpoints", "router"): DATA_WAREHOUSE_GUARD,
    ("warehouse_endpoints", "router"): DATA_WAREHOUSE_GUARD,
    ("data_lake_endpoints", "router"): DATA_WAREHOUSE_GUARD,
}
