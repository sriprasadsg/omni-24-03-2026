"""ITAM console global settings — branding/theming + localization (Phase 65 Plan 04,
ITAM-SET-01/02/03).

Pure, DB-I/O-free module mirroring itam_catalog_service.py's convention: every function
here takes plain dicts and returns plain values so the endpoints module (and any future
caller) can validate/merge without touching the database.

This is a NEW, ITAM-console-scoped settings surface — explicitly separate from the
pre-existing platform-level white-labelling feature (components/TenantBrandingSettings.tsx
+ backend/tenant_endpoints.py's `/api/tenants/{id}/branding`). See 65-04-PLAN.md's D-01
assumption delta for the add-alongside rationale. The field vocabulary
(companyName/logoUrl/primaryColor) is reused deliberately so the two surfaces don't
diverge visually, but the storage, routes, and admin gating are entirely independent.
"""
import copy
import re
from typing import Any, Dict, List, Optional, Tuple

ITAM_SETTINGS_TYPE = "itam_settings"

# The only locales this phase actually ships dictionaries for
# (components/itam/itamI18n.tsx) — no aspirational entries.
SUPPORTED_LOCALES = ("en", "es")

# That hex is the console's current cyan accent, so an unconfigured tenant looks exactly
# as it does today.
DEFAULT_ITAM_SETTINGS: Dict[str, Any] = {
    "branding": {
        "companyName": "",
        "logoUrl": "",
        "primaryColor": "#0891b2",
    },
    "locale": "en",
}

_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_ALLOWED_LOGO_SCHEMES = ("http://", "https://", "data:image/")
_MAX_COMPANY_NAME_LEN = 120


def validate_itam_settings(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Normalise a caller-supplied settings payload and collect problems.

    Returns `(normalised, problems)`. `normalised` keeps only the `branding` and `locale`
    top-level keys (and, within `branding`, only `companyName`/`logoUrl`/`primaryColor`) —
    any other caller-supplied key is discarded rather than persisted. Each violation
    appends a problem naming the offending field. A missing key falls back to
    `DEFAULT_ITAM_SETTINGS`'s value rather than becoming a problem, so a partial save is
    allowed.
    """
    problems: List[str] = []
    payload = payload if isinstance(payload, dict) else {}
    branding_in = payload.get("branding")
    branding_in = branding_in if isinstance(branding_in, dict) else {}

    default_branding = DEFAULT_ITAM_SETTINGS["branding"]

    company_name = branding_in.get("companyName", default_branding["companyName"])
    if not isinstance(company_name, str):
        problems.append("companyName must be a string.")
        company_name = default_branding["companyName"]
    elif len(company_name) > _MAX_COMPANY_NAME_LEN:
        problems.append(f"companyName must be at most {_MAX_COMPANY_NAME_LEN} characters.")
        company_name = default_branding["companyName"]

    logo_url = branding_in.get("logoUrl", default_branding["logoUrl"])
    if not isinstance(logo_url, str):
        problems.append("logoUrl must be a string.")
        logo_url = default_branding["logoUrl"]
    elif logo_url and not logo_url.startswith(_ALLOWED_LOGO_SCHEMES):
        problems.append("logoUrl must be empty or begin with http://, https://, or data:image/.")
        logo_url = default_branding["logoUrl"]

    primary_color = branding_in.get("primaryColor", default_branding["primaryColor"])
    if not isinstance(primary_color, str) or not _COLOR_RE.match(primary_color):
        problems.append("primaryColor must be a six-digit hex color (e.g. #0891b2).")
        primary_color = default_branding["primaryColor"]

    locale = payload.get("locale", DEFAULT_ITAM_SETTINGS["locale"])
    if locale not in SUPPORTED_LOCALES:
        problems.append(f"locale must be one of {', '.join(SUPPORTED_LOCALES)}.")
        locale = DEFAULT_ITAM_SETTINGS["locale"]

    normalised = {
        "branding": {
            "companyName": company_name,
            "logoUrl": logo_url,
            "primaryColor": primary_color,
        },
        "locale": locale,
    }
    return normalised, problems


def merge_with_defaults(doc: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Deep-merge a stored document over `DEFAULT_ITAM_SETTINGS`, so a document written
    before a field existed still returns a complete shape."""
    merged = copy.deepcopy(DEFAULT_ITAM_SETTINGS)
    if not isinstance(doc, dict):
        return merged

    branding = doc.get("branding")
    if isinstance(branding, dict):
        for key in merged["branding"]:
            if key in branding:
                merged["branding"][key] = branding[key]

    if doc.get("locale") in SUPPORTED_LOCALES:
        merged["locale"] = doc["locale"]

    return merged
