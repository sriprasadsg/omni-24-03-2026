"""ITAM console global settings routes — branding/theming + localization (Phase 65 Plan
04, ITAM-SET-01/02/03).

New, ITAM-console-scoped settings surface — see itam_customization_service.py's module
docstring for the add-alongside rationale (D-01). `components/TenantBrandingSettings.tsx`
and `tenant_endpoints.py` are untouched by this plan.

Reads and writes go through the raw `db._db` handle with an explicit `tenantId` filter,
exactly like `settings_endpoints.py`'s LLM routes: `system_settings` is not in
`database.py`'s tenant-isolation exemption allowlist, so the wrapped tenant-scoped
accessor would inject its own `tenantId` equality filter and make the no-`tenantId`
global-fallback document unreachable (65-RESEARCH.md Pitfall 2). That wrapped accessor is
never used in this file.
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from authentication_service import get_current_user
from auth_types import TokenData
from database import get_database
from itam_audit_service import log_itam_action
from itam_customization_service import (
    ITAM_SETTINGS_TYPE,
    merge_with_defaults,
    validate_itam_settings,
)

router = APIRouter(prefix="/api/itam/settings", tags=["ITAM Settings"])

# Copied character-for-character from settings_endpoints.py's _SETTINGS_ADMIN_ROLES
# (65-RESEARCH.md Pitfall 4 — three near-duplicate role sets already exist; this must not
# become a fourth that differs).
_SETTINGS_ADMIN_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}


def _require_admin(user: TokenData) -> None:
    if getattr(user, "role", "") not in _SETTINGS_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required to modify ITAM settings")


@router.get("")
async def get_itam_settings(current_user: TokenData = Depends(get_current_user)):
    """Tenant-scoped read with global fallback. A user with no tenant id skips straight
    to the global-fallback document. Never 404s — an unconfigured tenant gets the
    built-in defaults."""
    db = get_database()
    raw = db._db if hasattr(db, "_db") else db
    tenant_id: Optional[str] = getattr(current_user, "tenant_id", None)

    doc = None
    if tenant_id:
        doc = await raw.system_settings.find_one(
            {"type": ITAM_SETTINGS_TYPE, "tenantId": tenant_id}, {"_id": 0}
        )
    if not doc:
        doc = await raw.system_settings.find_one(
            {"type": ITAM_SETTINGS_TYPE, "tenantId": {"$exists": False}}, {"_id": 0}
        )
    return merge_with_defaults(doc)


@router.post("")
async def save_itam_settings(
    settings: Dict[str, Any],
    current_user: TokenData = Depends(get_current_user),
):
    """Admin-gated write. Rejects with 400 + a problems[] list naming each offending
    field; otherwise upserts the tenant-scoped document and records the change in the
    ITAM audit ledger."""
    _require_admin(current_user)

    normalised, problems = validate_itam_settings(settings)
    if problems:
        raise HTTPException(
            status_code=400,
            detail={"message": "Invalid ITAM settings", "problems": problems},
        )

    db = get_database()
    raw = db._db if hasattr(db, "_db") else db
    tenant_id = getattr(current_user, "tenant_id", None)

    await raw.system_settings.update_one(
        {"type": ITAM_SETTINGS_TYPE, "tenantId": tenant_id},
        {"$set": {**normalised, "type": ITAM_SETTINGS_TYPE, "tenantId": tenant_id}},
        upsert=True,
    )

    await log_itam_action(
        current_user,
        action="itam_settings.update",
        resource_type="itam_settings",
        resource_id=tenant_id or "global",
        details=f"Updated ITAM settings: {sorted(normalised.keys())}",
    )

    return normalised
