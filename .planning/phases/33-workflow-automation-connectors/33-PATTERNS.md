# Phase 33: Workflow Automation Connectors - Pattern Map

**Mapped:** 2026-07-08
**Files analyzed:** 9
**Analogs found:** 7 / 9 (2 files — the n8n and Zapier packages — have no in-repo analog; research code examples used instead)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `backend/api_key_auth.py` (NEW) | middleware (auth dependency) | request-response | `backend/authentication_service.py::get_current_user`/`get_optional_user` | role-match (extends the existing dependency-composition pattern) |
| `backend/tenant_endpoints.py::generate_api_key` (MODIFIED) | controller (route handler) | CRUD | `backend/auth_utils.py::hash_password`/`verify_password` (hash-at-rest pattern) | partial match (hash pattern only — algorithm differs, SHA-256 not bcrypt, per RESEARCH.md rationale) |
| `backend/webhook_service.py::_send_single_webhook` (MODIFIED) | service | event-driven | `backend/ticket_webhook_service.py` (its dispatch loop, signing block) | exact (same signing pattern, sibling webhook subsystem) |
| `backend/webhook_endpoints.py` (MODIFIED) | route/controller | CRUD | itself, extended with `api_key_auth.py`'s new dependency; `_WEBHOOK_SUPER_ROLES` / `auth_roles.py` for role-scoping precedent | exact (in-place modification) |
| `integrations/n8n-nodes-omniagent/` (NEW package) | integration/client package | request-response (webhook lifecycle) | none in-repo — use RESEARCH.md Pattern 1 (n8n community-node scaffold) | no analog |
| `integrations/zapier-omniagent/` (NEW package) | integration/client package | request-response (REST Hook lifecycle) | none in-repo — use RESEARCH.md Pattern 2 (Zapier CLI app scaffold) | no analog |
| `backend/tests/test_api_key_auth.py` (NEW) | test | request-response | `backend/tests/test_automation_and_baa.py` (helper block + `_app`/`_user`/`_db`/`_col` convention) | exact |
| `backend/tests/test_webhook_signing.py` (NEW) | test | event-driven | `backend/tests/test_automation_and_baa.py` (same helper convention, adapted for signature assertions) | exact |

## Pattern Assignments

### `backend/api_key_auth.py` (NEW middleware/auth dependency)

**Analog:** `backend/authentication_service.py`

**Imports pattern** (`authentication_service.py` lines 1-11):
```python
import jwt
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from auth_types import TokenData  # Token re-exported by auth_types directly
from tenant_context import set_tenant_id as _set_tenant_id
```
The new file should mirror this: `from fastapi.security import APIKeyHeader`, `from auth_types import TokenData`, `from tenant_context import set_tenant_id`, plus `hashlib` for the SHA-256 lookup, and `from authentication_service import get_current_user` (or the lower-level `verify_token_async`) for the JWT fallback branch.

**Existing dependency-composition pattern to extend** (`authentication_service.py` lines 169-181):
```python
async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Dependency to get the current user; performs async revocation check."""
    return await verify_token_async(token)

async def get_optional_user(token: Optional[str] = Depends(_oauth2_optional)):
    """Like get_current_user but returns None instead of raising 401 when no token is provided.
    Used by endpoints that accept alternative auth (e.g. one-time download tokens)."""
    if not token:
        return None
    try:
        return await verify_token_async(token)
    except HTTPException:
        return None
```
This is the codebase's existing precedent for an "alternative auth" dependency (`get_optional_user` already exists for one-time download tokens) — `get_current_user_or_api_key` follows the same shape: try one credential type, fall back to another, raise 401 only if neither is present. Compose it as a **new function in `api_key_auth.py`**, not by editing `authentication_service.py` itself (keeps the SHA-256/API-key concern isolated per CLAUDE.md's "validate input at system boundaries" + single-responsibility file layout).

**TokenData shape to construct for the API-key branch** (`backend/auth_types.py` lines 6-10):
```python
class TokenData:
    username: Optional[str] = None
    role: Optional[str] = "user"
    tenant_id: Optional[str] = None
    mfa_verified: bool = False
```

**Core pattern — full dependency to write** (from RESEARCH.md Pattern 3, verbatim, this is the concrete target implementation):
```python
# backend/api_key_auth.py — NEW verification dependency
import hashlib
from typing import Optional
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from auth_types import TokenData
from tenant_context import set_tenant_id
from database import mongodb
from authentication_service import verify_token_async, _oauth2_optional

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_current_user_or_api_key(
    api_key: Optional[str] = Security(_api_key_header, auto_error=False),
    token: Optional[str] = Depends(_oauth2_optional),
):
    if api_key:
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        tenant = await mongodb.db.tenants.find_one(
            {"apiKeys.keyHash": key_hash}, {"id": 1, "apiKeys.$": 1}
        )
        if not tenant:
            raise HTTPException(status_code=401, detail="Invalid API key")
        set_tenant_id(tenant["id"])   # non-JWT auth path — must explicitly set tenant context
        return TokenData(tenant_id=tenant["id"], role="api-integration", username="api-key")
    if token:
        return await verify_token_async(token)
    raise HTTPException(status_code=401, detail="Authentication required")
```

**Tenant-context precedent this must follow** — confirm `tenant_context.set_tenant_id` signature/import path used elsewhere before wiring (grep `set_tenant_id` call sites in `webhook_endpoints.py`/other non-JWT paths if any exist, per RESEARCH.md's reference to Phase 29's established mandatory pattern for `TenantIsolatedCollection`).

**Role scoping (Pitfall 2 — must apply):** the `role="api-integration"` value must be added to any RBAC branch `webhook_endpoints.py` touches (`_WEBHOOK_SUPER_ROLES` check in `get_webhooks`) — confirm `"api-integration"` is NOT accidentally treated as a super role and is NOT silently 403'd on the routes it legitimately needs (`POST`/`DELETE`/`GET /api/webhooks`, `GET /api/webhooks/{id}/deliveries`).

---

### `backend/tenant_endpoints.py::generate_api_key` (MODIFIED)

**Analog for storage-of-hash pattern:** `backend/auth_utils.py` (`hash_password`/`verify_password`, lines 16-46) — read for the "hash at rest, never store plaintext" shape, but **do not reuse bcrypt** — see RESEARCH.md Standard Stack → Alternatives Considered (SHA-256 is correct for high-entropy random tokens, bcrypt/Argon2 is for low-entropy human passwords).

**Current implementation to modify** (`backend/tenant_endpoints.py` lines 272-305, full function read this session):
```python
async def generate_api_key(
    tenant_id: str,
    data: Dict[str, Any],
    current_user=Depends(get_current_user),
):
    """Generate a new API key for the tenant. Returns the plaintext key once — store it safely."""
    _is_super_admin = is_super_admin(getattr(current_user, "role", ""))
    is_own_admin = (
        getattr(current_user, "tenant_id", None) == tenant_id
        and getattr(current_user, "role", "") in ("Admin", "Tenant Admin", "tenant_admin")
    )
    if not _is_super_admin and not is_own_admin:
        raise HTTPException(status_code=403, detail="Not authorized to manage API keys for this tenant")

    tenant = await mongodb.db.tenants.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    plaintext = f"omni_sk_{secrets.token_urlsafe(32)}"
    key_id = f"key-{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc).isoformat()

    key_doc = {
        "id": key_id,
        "name": data.get("name", "API Key"),
        "key": plaintext[:12] + "••••••••••••",   # store only prefix for display
        "createdAt": now,
        "userId": data.get("userId") or getattr(current_user, "username", ""),
    }
    await mongodb.db.tenants.update_one(
        {"id": tenant_id},
        {"$push": {"apiKeys": key_doc}},
    )
    return {"id": key_id, "name": key_doc["name"], "key": plaintext, "createdAt": now}
```
**Fix** — add one line (`import hashlib` at file top) and one field to `key_doc`:
```python
key_hash = hashlib.sha256(plaintext.encode()).hexdigest()   # NEW
key_doc = {
    "id": key_id,
    "name": data.get("name", "API Key"),
    "key": plaintext[:12] + "••••••••••••",   # unchanged — display prefix only
    "keyHash": key_hash,                       # NEW — enables verification
    "createdAt": now,
    "userId": data.get("userId") or getattr(current_user, "username", ""),
}
```
**RBAC pattern already in this function to preserve unchanged** — the `_is_super_admin`/`is_own_admin` check (lines 278-284) uses `rbac_utils.is_super_admin` — this is the existing tenant-admin-or-super-admin gate for key issuance itself; not to be confused with the new `api-integration` role, which is what a *generated* key authenticates as, not who is allowed to generate one.

**Sibling function that must stay consistent** — `revoke_api_key` (lines 416-436) uses the same RBAC gate; no changes needed there (revocation still keys off `id`, not `keyHash`).

**tenant_endpoints.py imports** (lines 1-10, for reference — no new imports needed beyond stdlib `hashlib`):
```python
from fastapi import APIRouter, HTTPException, Depends, Request, Response
from typing import List, Any, Dict, Optional
from pydantic import BaseModel
from database import get_database, mongodb
from authentication_service import get_current_user
from rbac_utils import is_super_admin
from rate_limiter import limiter
from datetime import datetime, timezone
import uuid
import secrets
```

---

### `backend/webhook_service.py::_send_single_webhook` (MODIFIED)

**Analog:** `backend/ticket_webhook_service.py` — the sibling webhook subsystem that already signs correctly.

**Analog's imports** (`ticket_webhook_service.py` lines 1-13):
```python
"""Outbound webhook dispatch for ticket events."""
import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx
from database import mongodb

logger = logging.getLogger(__name__)
```

**Signing pattern to clone** (`ticket_webhook_service.py`, dispatch loop):
```python
for hook in webhooks:
    try:
        body = json.dumps({
            "event": event,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "X-Webhook-Event": event,
        }
        if hook.get("secret"):
            sig = hmac.new(
                hook["secret"].encode(), body.encode(), hashlib.sha256
            ).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={sig}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(hook["url"], content=body, headers=headers)
```

**Current `webhook_service.py::_send_single_webhook` to modify** (full function, lines 84-131 of `backend/webhook_service.py`):
```python
async def _send_single_webhook(self, client, hook, payload, db):
    url = hook.get('url')
    if not url or not _is_safe_webhook_url(url):
        logger.warning("[WebhookService] Blocked delivery to unsafe URL: %s", url)
        return
    headers = hook.get('headers', {})

    # Default headers
    headers['Content-Type'] = 'application/json'
    headers['User-Agent'] = 'Omni-Agent-Platform/1.0'

    try:
        response = await client.post(url, json=payload, headers=headers, timeout=10.0)
        success = response.status_code >= 200 and response.status_code < 300
        # ... (update_doc / failureCount tracking unchanged below)
```
**Fix** — insert HMAC signing between the header defaults and the `client.post` call. Note: this function uses `client.post(url, json=payload, ...)` (httpx serializes `payload` itself) rather than `ticket_webhook_service.py`'s manual `json.dumps` + `content=body` — **the signature must be computed over the exact same serialized bytes httpx will send**, so switch to `body = json.dumps(payload)` + `content=body` (matching the analog) rather than signing a value httpx re-serializes independently, to avoid a signature/body mismatch:
```python
import json, hmac, hashlib   # add to file-top imports (hashlib/hmac not currently imported in webhook_service.py)
...
headers = hook.get('headers', {})
headers['Content-Type'] = 'application/json'
headers['User-Agent'] = 'Omni-Agent-Platform/1.0'
body = json.dumps(payload)
if hook.get('secret'):
    sig = hmac.new(hook['secret'].encode(), body.encode(), hashlib.sha256).hexdigest()
    headers['X-Webhook-Signature'] = f"sha256={sig}"
try:
    response = await client.post(url, content=body, headers=headers, timeout=10.0)
    ...
```
**Confirmed current top-of-file imports in `webhook_service.py`** (lines 1-6): `ipaddress`, `logging`, `re`, `httpx`, `from datetime import datetime`, `from database import get_database` — `hmac`/`hashlib`/`json` are NOT yet imported there and must be added.

**Where the secret already exists to sign with** — `webhook_endpoints.py::create_webhook` (lines 111-140, unchanged by this phase):
```python
new_webhook = {
    "id": webhook_id,
    "name": webhook_data.get("name"),
    "url": url,
    "events": webhook_data.get("events", []),
    "status": "Active",
    "secret": f"whsec_{uuid.uuid4().hex[:24]}", # Auto-generated secret
    "tenantId": current_user.tenant_id,
    "createdBy": current_user.username,
    "createdAt": datetime.now(timezone.utc).isoformat(),
    "failureCount": 0,
    "lastResult": None
}
```

---

### `backend/webhook_endpoints.py` (MODIFIED — add API-key auth path)

**Current imports** (lines 1-15):
```python
import ipaddress
import socket
from urllib.parse import urlparse as _wh_urlparse
from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Dict, Any
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from datetime import datetime, timezone
import uuid
import hmac
import hashlib
import httpx
from intent_parser_service import intent_parser_service
from integration_service import get_integration_service
```
Add: `from api_key_auth import get_current_user_or_api_key`

**Existing role-scoping precedent to compose with** (line ~35): `from auth_roles import SUPER_ROLES as _WEBHOOK_SUPER_ROLES`, used in `get_webhooks`:
```python
@router.get("")
async def get_webhooks(current_user: TokenData = Depends(get_current_user)):
    """Get all configured webhooks"""
    db = get_database()
    caller_role = getattr(current_user, "role", "")
    caller_tenant = getattr(current_user, "tenant_id", None)
    query = {} if caller_role in _WEBHOOK_SUPER_ROLES else {"tenantId": caller_tenant}
    cursor = db.webhooks.find(query, {"_id": 0})
    return await cursor.to_list(length=100)
```
The `"api-integration"` role will fall into the `else` branch (tenant-scoped query) automatically since it's not in `_WEBHOOK_SUPER_ROLES` — correct, least-privilege behavior, no code change needed to this branch's logic, only the `Depends(get_current_user)` swap.

**Fix — swap dependency on the routes both connectors need** (`create_webhook` at line 111, `delete_webhook` at line 142, `get_webhooks` at line 101; leave `update_webhook`/`test_webhook`/inbound provider webhooks as-is unless the plan decides otherwise):
```python
# Before:
async def create_webhook(webhook_data: Dict[str, Any], current_user: TokenData = Depends(get_current_user)):
# After:
async def create_webhook(webhook_data: Dict[str, Any], current_user: TokenData = Depends(get_current_user_or_api_key)):
```
Apply the same swap to `get_webhooks`, `delete_webhook`, and `get_webhook_deliveries` (needed by Zapier's `performList`, per RESEARCH.md Pattern 2).

**SSRF guard to leave untouched** (lines 17-30) — `_is_safe_webhook_url` already applies unconditionally regardless of auth method; do not modify.

---

### `integrations/n8n-nodes-omniagent/` (NEW package — no in-repo analog)

Use RESEARCH.md **Pattern 1** verbatim as the scaffold source (`OmniAgentTrigger` class, `webhookMethods.create/delete/checkExists`, credential wiring via `X-API-Key` header). No codebase analog exists for an n8n node; do not invent a different shape — the research pattern was sourced from n8n's own official community-node docs.

Key structural facts to carry into the plan (from `.planning/phases/33-workflow-automation-connectors/33-RESEARCH.md` "Recommended Project Structure"):
```
integrations/n8n-nodes-omniagent/
├── package.json                # name: n8n-nodes-omniagent, n8n block, n8n-workflow peerDependency
├── credentials/OmniAgentApi.credentials.ts
├── nodes/OmniAgentTrigger/OmniAgentTrigger.node.ts   # webhookMethods.create/delete/checkExists
├── tsconfig.json / tsconfig.build.json
├── eslint.config.mjs
└── README.md
```

---

### `integrations/zapier-omniagent/` (NEW package — no in-repo analog)

Use RESEARCH.md **Pattern 2** verbatim (`subscribeHook`/`unsubscribeHook`/`performList` functions, `module.exports` trigger definition). No codebase analog; sourced from Zapier's own official CLI/REST Hook docs.

```
integrations/zapier-omniagent/
├── index.js                    # App definition export
├── authentication.js           # API key field
├── triggers/grc_event.js       # performSubscribe / performUnsubscribe / performList
├── test/triggers/grc_event.test.js
└── package.json                # zapier-platform-core dependency
```

---

### `backend/tests/test_api_key_auth.py` and `backend/tests/test_webhook_signing.py` (NEW)

**Analog:** `backend/tests/test_automation_and_baa.py` — clone its full helper block verbatim (this is this repo's established per-test-file convention, also followed by Phase 29's tests).

**Imports + helpers to clone** (`test_automation_and_baa.py` lines 1-53):
```python
"""
Tests for automation_endpoints.py and baa_endpoints.py.
...
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from authentication_service import get_current_user
from auth_types import TokenData


# ─── helpers ─────────────────────────────────────────────────────────────────

def _col(**overrides):
    col = MagicMock()
    col.find_one   = AsyncMock(return_value=None)
    col.insert_one = AsyncMock()
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    col.delete_one = AsyncMock()
    col.find       = MagicMock()
    col.find.return_value.to_list = AsyncMock(return_value=[])
    col.find.return_value.sort    = MagicMock(return_value=MagicMock())
    col.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
    for k, v in overrides.items():
        setattr(col, k, v)
    return col


def _db(**collections):
    db = MagicMock()
    db.__getitem__ = lambda self, name: getattr(self, name, _col())
    for name, col in collections.items():
        setattr(db, name, col)
    return db


def _user(role="security_analyst", tenant_id="t1"):
    return TokenData(username="test@example.com", role=role, tenant_id=tenant_id, mfa_verified=True)


def _app(router, user):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    return app
```

**For `test_api_key_auth.py`:** override `app.dependency_overrides[get_current_user_or_api_key]` (not `get_current_user`) when testing routes through `webhook_endpoints.py`; write dedicated unit tests that call `get_current_user_or_api_key` directly (bypassing FastAPI's DI) with a mocked `mongodb.db.tenants.find_one` to test the hash-lookup/401/tenant-context-set behavior in isolation, per RESEARCH.md's Phase Requirements → Test Map (`hash_verify`, `webhook_route` test cases).

**For `test_webhook_signing.py`:** mock `httpx.AsyncClient.post` (as an `AsyncMock`) and assert the `X-Webhook-Signature` header value equals `hmac.new(secret, body, hashlib.sha256).hexdigest()` computed independently in the test — mirrors how a receiving connector would verify it.

## Shared Patterns

### Non-JWT auth must explicitly set tenant context
**Source:** RESEARCH.md Pattern 3, citing Phase 29's precedent (`tenant_context.set_tenant_id`)
**Apply to:** `api_key_auth.py`'s `get_current_user_or_api_key` — any dependency issuing a `TokenData` outside the standard JWT `verify_token_async` path must call `set_tenant_id(...)` explicitly before returning, or downstream `TenantIsolatedCollection` queries silently fail closed/open incorrectly.

### HMAC-SHA256 outbound webhook signing
**Source:** `backend/ticket_webhook_service.py` (dispatch loop shown above)
**Apply to:** `backend/webhook_service.py::_send_single_webhook` — clone the `hmac.new(hook["secret"].encode(), body.encode(), hashlib.sha256).hexdigest()` / `X-Webhook-Signature: sha256=...` pattern exactly; do not invent a different header name or algorithm.

### Narrow, explicit role for machine credentials
**Source:** RESEARCH.md Pitfall 2, `backend/auth_roles.py` (`SUPER_ROLES` frozenset pattern)
**Apply to:** any RBAC branch in `webhook_endpoints.py` — API-key-authenticated `TokenData` must carry `role="api-integration"`, which must never match `_WEBHOOK_SUPER_ROLES`/`SUPER_ROLES`/`SUPER_AND_ADMIN_ROLES` (`backend/auth_roles.py`: `frozenset({"Super Admin", "superadmin", "super_admin", "platform-admin"})`) and must resolve to the tenant-scoped query branch, not the unrestricted one.

### SHA-256 (not bcrypt) for high-entropy token hashing
**Source:** RESEARCH.md Standard Stack → Alternatives Considered; `backend/auth_utils.py` (bcrypt is the *wrong* analog to copy the algorithm from, but *right* analog for "always hash, never store plaintext")
**Apply to:** `tenant_endpoints.py::generate_api_key` and `api_key_auth.py`'s lookup — both must use `hashlib.sha256(...).hexdigest()`, matched by equality lookup (`{"apiKeys.keyHash": key_hash}`), not `bcrypt.checkpw`.

### Test-file helper convention
**Source:** `backend/tests/test_automation_and_baa.py` (`_col`/`_db`/`_user`/`_app` helpers, `app.dependency_overrides[...]` pattern)
**Apply to:** `test_api_key_auth.py`, `test_webhook_signing.py` — clone the four helper functions verbatim; do not write a new mocking convention.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `integrations/n8n-nodes-omniagent/**` | integration package | request-response (webhook lifecycle) | No n8n or any community-node package exists anywhere in this repo; use RESEARCH.md Pattern 1 (sourced from n8n's official docs) as the concrete scaffold instead of an in-repo analog |
| `integrations/zapier-omniagent/**` | integration package | request-response (REST Hook lifecycle) | No Zapier CLI app or similar external-platform package exists in this repo; use RESEARCH.md Pattern 2 (sourced from Zapier's official docs) as the concrete scaffold instead of an in-repo analog |

## Metadata

**Analog search scope:** `backend/` (authentication_service.py, tenant_endpoints.py, webhook_service.py, webhook_endpoints.py, ticket_webhook_service.py, auth_utils.py, auth_roles.py, auth_types.py, tests/test_automation_and_baa.py)
**Files scanned:** 9 backend source files + 1 test file, full or targeted reads
**Pattern extraction date:** 2026-07-08
