"""User-facing and admin API token management endpoints (ITAM-USR-05).

These user-scoped routes (`/api/api-keys`) are new in this plan and are
independent of the pre-existing tenant-scoped routes at
`POST/DELETE /api/tenants/{tenantId}/api-keys` (tenant_endpoints.py), which
remain untouched and continue to serve `SettingsApiKeysTab.tsx` per this
plan's `<frontend_scope>` constraint. Exposing the new scope/expiry fields in
that tab's UI is deferred to the Phase 65 ITAM console work.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth_types import TokenData
from authentication_service import get_current_user
# Deliberately excluded from the D-02 API-key swap (Phase 73): letting an
# API key manage API keys is a privilege-escalation surface — this stays
# session-auth-only.
from itam_asset_endpoints import _require_itam_admin_session_only as _require_itam_admin
from api_key_auth import AVAILABLE_SCOPES, api_key_service
from database import mongodb

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/api-keys", tags=["API Tokens"])
admin_router = APIRouter(prefix="/api/admin/api-keys", tags=["API Tokens - Admin"])


class APIKeyCreateRequest(BaseModel):
    name: str
    scopes: List[str] = Field(default_factory=list)
    expires_in_days: Optional[int] = None
    rate_limit: int = 60


def _validate_scopes(scopes: List[str]) -> None:
    unknown = [s for s in scopes if s not in AVAILABLE_SCOPES]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown scope(s): {', '.join(unknown)}")


# ── User-scoped routes ────────────────────────────────────────────────────────

@router.post("")
async def create_api_key(
    body: APIKeyCreateRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Create a new API token for the calling user. The plaintext key is
    returned ONCE in this response — it cannot be recovered afterwards."""
    _validate_scopes(body.scopes)
    try:
        model, plaintext = await api_key_service.create_key(
            user_id=current_user.username,
            name=body.name,
            scopes=body.scopes,
            expires_in_days=body.expires_in_days,
            rate_limit=body.rate_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return {
        "id": model.id,
        "name": model.name,
        "key": plaintext,
        "prefix": model.keyPrefix,
        "scopes": model.scopes,
        "expires_at": model.expiresAt,
        "rate_limit": model.rateLimit,
        "created_at": model.createdAt,
    }


@router.get("")
async def list_api_keys(current_user: TokenData = Depends(get_current_user)):
    """List the calling user's own tokens. Never includes keyHash."""
    keys = await api_key_service.list_keys(current_user.username)
    return [k.to_public_dict() for k in keys]


@router.get("/scopes")
async def list_available_scopes(current_user: TokenData = Depends(get_current_user)):
    """Catalog of scopes a token may be created with."""
    return [{"scope": scope, "description": desc} for scope, desc in AVAILABLE_SCOPES.items()]


@router.delete("/{key_id}")
async def revoke_api_key_route(
    key_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    revoked = await api_key_service.revoke_key(current_user.username, key_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"success": True}


# ── Admin routes ──────────────────────────────────────────────────────────────

@admin_router.get("")
async def admin_list_api_keys(current_user: TokenData = Depends(_require_itam_admin)):
    """List every user-scoped token across all tenants, with owner info."""
    results: List[dict] = []
    cursor = mongodb.db.users.find(
        {"apiKeys.0": {"$exists": True}},
        {"email": 1, "username": 1, "tenantId": 1, "apiKeys": 1},
    )
    async for user_doc in cursor:
        owner = user_doc.get("email") or user_doc.get("username")
        for key_doc in user_doc.get("apiKeys", []):
            entry = {
                "id": key_doc.get("id"),
                "name": key_doc.get("name"),
                "prefix": key_doc.get("keyPrefix"),
                "scopes": key_doc.get("scopes", []),
                "expires_at": key_doc.get("expiresAt"),
                "rate_limit": key_doc.get("rateLimit"),
                "created_at": key_doc.get("createdAt"),
                "last_used_at": key_doc.get("lastUsedAt"),
                "revoked_at": key_doc.get("revokedAt"),
                "owner": owner,
                "tenant_id": user_doc.get("tenantId"),
            }
            results.append(entry)
    return results


@admin_router.delete("/{key_id}")
async def admin_revoke_api_key(
    key_id: str,
    current_user: TokenData = Depends(_require_itam_admin),
):
    result = await mongodb.db.users.update_one(
        {"apiKeys.id": key_id},
        {"$set": {"apiKeys.$.revokedAt": datetime.now(timezone.utc).isoformat()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"success": True}
