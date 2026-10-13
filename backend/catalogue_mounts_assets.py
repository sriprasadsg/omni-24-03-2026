"""Assets slice (Phase 76-04): asset, ITAM and certificate routers.

``MOUNTS`` guards every router whose user routes all belong to one catalogue. The
named guards below are also imported by the few modules that mix catalogues on one
router (``itam_lifecycle_endpoints``, ``itam_label_endpoints``, the compliance and scan
modules) and add them as route-level ``dependencies``.

Each guard takes the auth dependency its routes already use: ``get_current_user_or_api_key``
for the ITAM routes that accept API keys (D-02), ``get_current_user`` for the rest. The
permission strings mirror ``shared/catalogue-access.json``; ``test_catalogue_slice_assets``
fails when the two drift.
"""
from api_key_auth import get_current_user_or_api_key
from authentication_service import get_current_user
from catalogue_guards import catalogue_guard

ASSETS_READ = ("view:assets",)
ASSETS_WRITE = ("manage:assets", "manage:compliance_evidence")
ITAM_READ = ("view:itam",)
ITAM_WRITE = ("manage:assets", "manage:procurement", "request:assets")
CERTIFICATES_READ = ("view:assets",)
CERTIFICATES_WRITE = ("manage:settings",)
VULNERABILITY_READ = ("view:vulnerabilities",)
VULNERABILITY_WRITE = ("investigate:security", "manage:patches", "manage:security_cases", "view:security")

ASSETS_GUARD = catalogue_guard("assetManagement", read=ASSETS_READ, write=ASSETS_WRITE)
ASSETS_API_KEY_GUARD = catalogue_guard(
    "assetManagement", read=ASSETS_READ, write=ASSETS_WRITE, auth=get_current_user_or_api_key
)
ITAM_GUARD = catalogue_guard("itam", read=ITAM_READ, write=ITAM_WRITE)
ITAM_API_KEY_GUARD = catalogue_guard(
    "itam", read=ITAM_READ, write=ITAM_WRITE, auth=get_current_user_or_api_key
)
CERTIFICATES_GUARD = catalogue_guard("certificates", read=CERTIFICATES_READ, write=CERTIFICATES_WRITE)
VULNERABILITY_GUARD = catalogue_guard(
    "vulnerabilityManagement", read=VULNERABILITY_READ, write=VULNERABILITY_WRITE
)

MOUNTS = {
    # Assets (assetManagement). Routes use get_current_user unless noted.
    ("asset_endpoints", "router"): ASSETS_GUARD,
    ("asset_metrics_endpoints", "router"): ASSETS_GUARD,
    # ITAM routers whose every route lives under /api/assets/{id}/... (assetManagement) and
    # whose handlers authenticate through _require_itam_*: sessions and API keys.
    ("itam_asset_endpoints", "router"): ASSETS_API_KEY_GUARD,
    ("itam_finance_endpoints", "router"): ASSETS_API_KEY_GUARD,
    ("itam_component_endpoints", "asset_components_router"): ASSETS_API_KEY_GUARD,
    # ITAM catalogue: API-key capable routers (D-02).
    ("itam_catalog_endpoints", "router"): ITAM_API_KEY_GUARD,
    ("itam_component_endpoints", "router"): ITAM_API_KEY_GUARD,
    ("itam_consumable_endpoints", "router"): ITAM_API_KEY_GUARD,
    ("itam_license_endpoints", "router"): ITAM_API_KEY_GUARD,
    ("itam_data_endpoints", "router"): ITAM_API_KEY_GUARD,
    ("itam_kpi_endpoints", "router"): ITAM_API_KEY_GUARD,
    ("itam_reporting_endpoints", "router"): ITAM_API_KEY_GUARD,
    ("itam_ticketing_endpoints", "router"): ITAM_API_KEY_GUARD,
    # ITAM catalogue: session-only routers.
    ("itam_asset_request_endpoints", "router"): ITAM_GUARD,
    ("itam_procurement_endpoints", "router"): ITAM_GUARD,
    ("itam_customization_endpoints", "router"): ITAM_GUARD,
    # Certificates.
    ("certificate_endpoints", "router"): CERTIFICATES_GUARD,
}
