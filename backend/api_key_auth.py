"""API Key (access token) authentication and lifecycle (ITAM-USR-05).

This module owns TWO independent key mechanisms that must both keep working:

1. **Legacy tenant-scoped keys** (`tenants.apiKeys`, managed by
   `tenant_endpoints.py`'s `generate_api_key`/`revoke_api_key` routes and
   consumed by `SettingsApiKeysTab.tsx`). Untouched by this plan — the
   original lookup in `get_current_user_or_api_key` below is preserved
   verbatim as a fallback.
2. **New user-scoped tokens** (`users.apiKeys`, this plan's actual scope):
   full lifecycle (create/list/revoke), bcrypt-hashed storage, scopes,
   expiration, and per-key rate limiting, added via `APIKeyService` below and
   exposed through `api_key_endpoints.py`'s `/api/api-keys` routes.

`get_current_user_or_api_key` tries the new user-scoped mechanism first (it
returns a scope-carrying `TokenData` — see auth_types.TokenData.scopes /
auth_source, and rbac_service.py's scope-narrowing enforcement) and falls
back to the legacy tenant-scoped mechanism so already-issued tenant keys
keep authenticating.
"""
import hashlib
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from auth_types import TokenData
from authentication_service import verify_token_async, _oauth2_optional
from auth_utils import hash_password, verify_password
from database import mongodb
from tenant_context import set_tenant_id

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# ── Scopes ──────────────────────────────────────────────────────────────────
# Predefined scopes matching ITAM permissions (mirrors rbac_service's ITAM
# permission strings so a key's scopes compose naturally with role
# permissions in rbac_service._scopes_allow / has_permission).
AVAILABLE_SCOPES: Dict[str, str] = {
    "read:assets": "Read ITAM assets",
    "write:assets": "Create and update ITAM assets",
    "read:licenses": "Read software licenses",
    "write:licenses": "Create and update software licenses",
    "manage:users": "Manage users",
    "view:itam": "View ITAM console data",
    "manage:itam": "Manage ITAM console data",
    "admin:itam": "Full ITAM administrative access",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class APIKeyModel:
    id: str
    name: str
    keyHash: str
    keyPrefix: str
    scopes: List[str] = field(default_factory=list)
    expiresAt: Optional[str] = None
    rateLimit: int = 60
    createdAt: str = ""
    lastUsedAt: Optional[str] = None
    revokedAt: Optional[str] = None
    createdBy: str = ""

    def to_public_dict(self) -> Dict[str, Any]:
        """Serializable form excluding keyHash — safe for list/display responses."""
        return {
            "id": self.id,
            "name": self.name,
            "prefix": self.keyPrefix,
            "scopes": self.scopes,
            "expires_at": self.expiresAt,
            "rate_limit": self.rateLimit,
            "created_at": self.createdAt,
            "last_used_at": self.lastUsedAt,
            "revoked_at": self.revokedAt,
        }


# ── Rate limiting (in-process, sliding 60s window per key) ───────────────────
# Single-process, in-memory approach — same documented tradeoff RESEARCH.md
# flags for mfa_service.py's session store (Pitfall 1): acceptable for a
# single-worker deployment, would need Redis for multi-worker production.
_usage_windows: Dict[str, deque] = defaultdict(deque)


def _check_rate_limit(key_id: str, rate_limit: int) -> bool:
    """Sliding 60s window request counter. Returns True if under the limit."""
    if not rate_limit or rate_limit <= 0:
        return True
    window = _usage_windows[key_id]
    now = time.monotonic()
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= rate_limit:
        return False
    window.append(now)
    return True


_MODEL_FIELDS = set(APIKeyModel.__dataclass_fields__.keys())


class APIKeyService:
    """User-scoped API token lifecycle: create, list, revoke, validate, authenticate."""

    @staticmethod
    def _user_filter(user_id: str) -> Dict[str, Any]:
        return {"$or": [{"email": user_id}, {"username": user_id}]}

    async def create_key(
        self,
        user_id: str,
        name: str,
        scopes: Optional[List[str]] = None,
        expires_in_days: Optional[int] = None,
        rate_limit: int = 60,
    ) -> "tuple[APIKeyModel, str]":
        """Create a new token for user_id. Returns (model, plaintext) — the
        plaintext key is returned ONCE and never recoverable again."""
        scopes = list(scopes or [])
        plaintext = f"omni_pat_{secrets.token_urlsafe(32)}"
        key_prefix = plaintext[:12]
        key_hash = hash_password(plaintext)
        now = _now_iso()
        expires_at = None
        if expires_in_days:
            expires_at = (datetime.now(timezone.utc) + timedelta(days=expires_in_days)).isoformat()

        model = APIKeyModel(
            id=f"pat-{secrets.token_hex(8)}",
            name=name,
            keyHash=key_hash,
            keyPrefix=key_prefix,
            scopes=scopes,
            expiresAt=expires_at,
            rateLimit=rate_limit or 60,
            createdAt=now,
            createdBy=user_id,
        )

        result = await mongodb.db.users.update_one(
            self._user_filter(user_id),
            {"$push": {"apiKeys": dict(model.__dict__)}},
        )
        if result.matched_count == 0:
            raise ValueError(f"User not found: {user_id}")

        return model, plaintext

    async def list_keys(self, user_id: str) -> List[APIKeyModel]:
        """List all tokens for user_id (including revoked/expired, so the UI
        can show history) — keyHash is never included on the model's public
        serialization (see APIKeyModel.to_public_dict)."""
        user_doc = await mongodb.db.users.find_one(self._user_filter(user_id), {"apiKeys": 1})
        if not user_doc:
            return []
        return [self._to_model(k) for k in user_doc.get("apiKeys", [])]

    async def revoke_key(self, user_id: str, key_id: str) -> bool:
        result = await mongodb.db.users.update_one(
            {**self._user_filter(user_id), "apiKeys.id": key_id},
            {"$set": {"apiKeys.$.revokedAt": _now_iso()}},
        )
        return result.matched_count > 0

    @staticmethod
    def _to_model(key_doc: Dict[str, Any]) -> APIKeyModel:
        return APIKeyModel(**{k: v for k, v in key_doc.items() if k in _MODEL_FIELDS})

    async def _validate_and_touch(self, api_key: str) -> Optional[Dict[str, Any]]:
        """Internal: prefix lookup + bcrypt verify + revoked/expired check +
        rate limit + lastUsedAt touch, in one DB round trip. Returns
        {"key": APIKeyModel, "owner_email": str, "owner_role": str,
        "owner_tenant_id": str} or None. Raises HTTPException 429 if the key
        is otherwise valid but over its rate limit."""
        if not api_key or len(api_key) < 12:
            return None
        prefix = api_key[:12]
        user_doc = await mongodb.db.users.find_one(
            {"apiKeys.keyPrefix": prefix},
            {"apiKeys.$": 1, "email": 1, "username": 1, "role": 1, "tenantId": 1},
        )
        if not user_doc or not user_doc.get("apiKeys"):
            return None
        key_doc = user_doc["apiKeys"][0]

        if key_doc.get("revokedAt"):
            return None
        if not verify_password(api_key, key_doc.get("keyHash", "")):
            return None

        expires_at = key_doc.get("expiresAt")
        if expires_at:
            try:
                exp = datetime.fromisoformat(expires_at)
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp < datetime.now(timezone.utc):
                    return None
            except ValueError:
                pass

        if not _check_rate_limit(key_doc["id"], key_doc.get("rateLimit", 60)):
            raise HTTPException(status_code=429, detail="API key rate limit exceeded")

        touched_at = _now_iso()
        await mongodb.db.users.update_one(
            {"apiKeys.id": key_doc["id"]},
            {"$set": {"apiKeys.$.lastUsedAt": touched_at}},
        )
        key_doc["lastUsedAt"] = touched_at

        return {
            "key": self._to_model(key_doc),
            "owner_email": user_doc.get("email") or user_doc.get("username"),
            "owner_role": user_doc.get("role", "user"),
            "owner_tenant_id": user_doc.get("tenantId"),
        }

    async def validate_key(self, api_key: str) -> Optional[APIKeyModel]:
        """Find the key by prefix, verify bcrypt, check not revoked/expired,
        enforce rate limit, and update lastUsedAt on success."""
        found = await self._validate_and_touch(api_key)
        return found["key"] if found else None

    async def authenticate(self, api_key: str) -> Optional[TokenData]:
        """Validate api_key and build the TokenData used for request
        authentication: scopes narrowed to exactly the key's own scopes,
        auth_source='api_key' — rbac_service.has_permission()/require_role()
        intersect these with the owning user's role permissions (Task 3)."""
        found = await self._validate_and_touch(api_key)
        if not found:
            return None
        return TokenData(
            username=found["owner_email"],
            role=found["owner_role"],
            tenant_id=found["owner_tenant_id"],
            scopes=found["key"].scopes,
            auth_source="api_key",
        )


api_key_service = APIKeyService()


async def get_current_user_or_api_key(
    api_key: Optional[str] = Security(_api_key_header),
    token: Optional[str] = Depends(_oauth2_optional)
) -> TokenData:
    if api_key:
        # New user-scoped tokens (ITAM-USR-05) — tried first.
        token_data = await api_key_service.authenticate(api_key)
        if token_data is not None:
            set_tenant_id(token_data.tenant_id or "platform-admin")
            return token_data

        # Legacy tenant-scoped keys (tenant_endpoints.py generate_api_key) —
        # unchanged fallback so already-issued tenant keys keep working.
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        tenant_doc = await mongodb.db.tenants.find_one({"apiKeys.keyHash": key_hash}, {"id": 1, "apiKeys.$": 1})

        if not tenant_doc:
            raise HTTPException(status_code=401, detail="Invalid or expired API Key")

        # Check if the key is revoked (apiKeys.$ operator ensures we only get the matched element)
        matched_key = tenant_doc["apiKeys"][0] if "apiKeys" in tenant_doc and tenant_doc["apiKeys"] else None
        if not matched_key or matched_key.get("revoked", False):
             raise HTTPException(status_code=401, detail="Invalid or expired API Key")

        set_tenant_id(tenant_doc["id"])
        return TokenData(tenant_id=tenant_doc["id"], role="api-integration", username="api-key")
    elif token:
        return await verify_token_async(token)
    else:
        raise HTTPException(status_code=401, detail="Authentication required")
