"""Geo-security detector settings endpoints — Phase 47 Plan 04 (D-06).

Admin-gated GET/PATCH /api/settings/geo-security: per-tenant config surface
for the impossible-travel (GSEC-02) and geo-fence (GSEC-03) detectors —
detector on/off toggles plus the country-code allowlist GSEC-03 checks
check-ins against. Clones agent_location_history_endpoints.py's admin-gated
GET/PATCH toggle pattern (D-06) rather than folding into that file — this is
a distinct Security settings surface, separate from Phase 46's privacy
config.

Storage: system_settings type-keyed doc (type: "geo_security_detectors"),
same tenant -> global -> default convention as track_agent_location, read
via geo_security_service.get_geo_security_settings (47-02).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from typing import List, Optional
from database import get_database
from authentication_service import get_current_user
from geo_security_service import get_geo_security_settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Admin roles for settings-mutation gating (cloned verbatim from
# agent_location_history_endpoints.py per T-47-04-E — V4 access control).
_SETTINGS_ADMIN_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin", "Tenant Admin"}


def _require_admin(user) -> None:
    """Raise 403 if the caller does not have an admin role."""
    if getattr(user, "role", "") not in _SETTINGS_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required to modify settings")


class GeoSecuritySettingsUpdate(BaseModel):
    impossible_travel_enabled: Optional[bool] = None
    geo_fence_enabled: Optional[bool] = None
    allowed_country_codes: Optional[List[str]] = None

    @field_validator("allowed_country_codes")
    @classmethod
    def _validate_country_codes(cls, value):
        """D-03/T-47-04-T: reject anything that isn't a 2-letter alpha code
        at the boundary — never silently accept garbage that would then
        never match a real country_code downstream. Normalizes case."""
        if value is None:
            return value
        normalized = []
        for code in value:
            if not isinstance(code, str):
                raise ValueError(f"invalid country code: {code!r}")
            upper = code.strip().upper()
            if len(upper) != 2 or not upper.isalpha():
                raise ValueError(f"invalid ISO 3166 alpha-2 country code: {code!r}")
            normalized.append(upper)
        return normalized


# ---------------------------------------------------------------------------
# GET/PATCH /api/settings/geo-security (D-06)
# ---------------------------------------------------------------------------

@router.get("/api/settings/geo-security")
async def get_geo_security_settings_endpoint(current_user=Depends(get_current_user)):
    try:
        db = get_database()
        tenant_id = getattr(current_user, "tenant_id", None)
        settings = await get_geo_security_settings(db, tenant_id)
        return settings
    except Exception as e:
        logger.error("get_geo_security_settings_endpoint error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/api/settings/geo-security")
async def patch_geo_security_settings(
    body: GeoSecuritySettingsUpdate, current_user=Depends(get_current_user)
):
    try:
        _require_admin(current_user)
        db = get_database()
        raw = db._db if hasattr(db, "_db") else db
        tenant_id = getattr(current_user, "tenant_id", None)

        fields = body.model_dump(exclude_none=True)
        doc = {"type": "geo_security_detectors", **fields}

        if tenant_id:
            doc["tenantId"] = tenant_id
            await raw.system_settings.update_one(
                {"type": "geo_security_detectors", "tenantId": tenant_id},
                {"$set": doc}, upsert=True,
            )
        else:  # Global setting
            await raw.system_settings.update_one(
                {"type": "geo_security_detectors", "tenantId": {"$exists": False}},
                {"$set": doc}, upsert=True,
            )

        return await get_geo_security_settings(raw, tenant_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("patch_geo_security_settings error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
