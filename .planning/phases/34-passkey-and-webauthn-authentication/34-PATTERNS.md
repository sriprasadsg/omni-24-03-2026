# Phase 34: Passkey and WebAuthn Authentication - Pattern Map

**Mapped:** 2026-07-08
**Files analyzed:** 7 (2 new backend, 1 new test, 4 modified)
**Analogs found:** 7 / 7

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/passkey_service.py` | service | CRUD + event-driven (challenge ceremony) | `backend/mfa_service.py` | exact |
| `backend/passkey_endpoints.py` | controller/route | request-response | `backend/mfa_endpoints.py` | exact |
| `backend/router_registry.py` | config | request-response (route registration) | itself (existing `_load(...)` calls for `mfa_endpoints`/`sso_endpoints`) | exact |
| `components/LoginPage.tsx` | component | request-response | itself (existing SSO conditional button + MFA step-up branch) | exact |
| `components/UserProfilePage.tsx` (Security card) + `components/MFASetupWizard.tsx` | component | request-response | `components/MFASetupWizard.tsx` (for new `PasskeySetupModal.tsx`) / `UserProfilePage.tsx` Security card (for the new row) | exact |
| `services/apiService.ts` | utility (API client) | request-response | `services/apiService.ts` MFA client functions (lines 291-322) + `login()` (lines 366-391) | exact |
| `backend/tests/test_passkey_auth.py` | test | request-response | `backend/tests/test_auth_mfa.py` | exact |

## Pattern Assignments

### `backend/passkey_service.py` (service, CRUD + challenge ceremony)

**Analog:** `backend/mfa_service.py` (full file read, 261 lines)

**Imports pattern** (lines 1-20 of mfa_service.py):
```python
import pyotp
import qrcode
import io
import base64
import secrets
import hashlib
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from database import get_database
```
Passkey equivalent will swap `pyotp`/`qrcode` for `webauthn` (`generate_registration_options`, `verify_registration_response`, `generate_authentication_options`, `verify_authentication_response`, `options_to_json` — per RESEARCH.md Code Examples) and keep `uuid`, `datetime`, `get_database`.

**In-memory TTL challenge-store pattern — THIRD INSTANCE** (mfa_service.py lines 25-27, 198-218, structurally identical to `sso_service._oidc_states`):
```python
# In-memory store for short-lived MFA session tokens
# { session_token: { "email": str, "expires": datetime } }
_mfa_sessions: dict = {}

def _purge_expired_mfa_sessions() -> None:
    """Remove all expired entries from _mfa_sessions to prevent unbounded growth."""
    now = datetime.now(timezone.utc)
    expired = [k for k, v in _mfa_sessions.items() if v["expires"] < now]
    for k in expired:
        del _mfa_sessions[k]

def create_mfa_session(email: str) -> str:
    _purge_expired_mfa_sessions()
    token = str(uuid.uuid4())
    _mfa_sessions[token] = {
        "email": email,
        "expires": datetime.now(timezone.utc) + timedelta(seconds=MFA_SESSION_TTL_SECONDS),
    }
    return token

def validate_mfa_session(session_token: str) -> Optional[str]:
    entry = _mfa_sessions.get(session_token)
    if not entry:
        return None
    if datetime.now(timezone.utc) > entry["expires"]:
        del _mfa_sessions[session_token]
        return None
    return entry["email"]

def consume_mfa_session(session_token: str):
    """Delete the session token after successful MFA verification."""
    _mfa_sessions.pop(session_token, None)
```
`passkey_service.py` clones this exactly as `_webauthn_challenges` / `_prune_expired_challenges` / `store_challenge` / `consume_challenge` (RESEARCH.md Pattern 3 already gives the concrete target shape — TTL 90s, single-use pop-on-verify, keyed by `session_id` not `challenge`/user email pair).

**Nested-document credential storage pattern** (mfa_service.py `enroll_mfa`, lines 147-157 — the `$set` on `mfa.*` fields):
```python
await db.users.update_one(
    {"email": email},
    {"$set": {
        "mfa.enabled": True,
        "mfa.secret_encrypted": pending,
        "mfa.backup_codes_hashed": backup_hashes,
        "mfa.enrolled_at": datetime.now(timezone.utc).isoformat(),
        "mfa.pending_secret": None,
    }}
)
```
Passkey equivalent uses `$push` onto a new `webauthn_credentials` array (RESEARCH.md Pattern 2 gives the exact target shape: `credential_id`, `public_key` (base64), `sign_count`, `device_name`, `transports`, `created_at`, `last_used_at`).

**Status/read pattern** (mfa_service.py `get_mfa_status`, lines 183-193):
```python
async def get_mfa_status(email: str) -> dict:
    db = get_database()
    user = await db.users.find_one({"email": email})
    if not user:
        return {"enabled": False, "enrolled_at": None, "backup_codes_remaining": 0}
    mfa = user.get("mfa", {})
    return {
        "enabled": mfa.get("enabled", False),
        "enrolled_at": mfa.get("enrolled_at"),
        "backup_codes_remaining": len(mfa.get("backup_codes_hashed", [])),
    }
```
Passkey equivalent: `list_credentials(email)` returning filtered `{credential_id (partial), device_name, created_at, last_used_at}` per RESEARCH.md Pitfall 4 — never return raw `public_key`.

---

### `backend/passkey_endpoints.py` (controller, request-response)

**Analog:** `backend/mfa_endpoints.py` (full file read, 133 lines)

**Imports + router declaration** (lines 1-13):
```python
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from authentication_service import get_current_user, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from database import get_database
from rate_limiter import limiter
from datetime import timedelta
import mfa_service

router = APIRouter(prefix="/api/mfa", tags=["MFA"])
```
Passkey equivalent: `import passkey_service`; `router = APIRouter(prefix="/api/passkey", tags=["Passkeys"])`; import `create_refresh_token` too since passkey login mints both tokens (see RESEARCH.md Pattern 4).

**Authenticated setup/enroll endpoint (no rate limit)** (lines 32-60, `setup_mfa`):
```python
@router.post("/setup")
async def setup_mfa(current_user=Depends(get_current_user)):
    ...
    return {
        "secret": secret,
        "qr_uri": uri,
        "qr_base64": qr_base64,
        "app_name": mfa_service.APP_NAME,
    }
```
Direct analog for `POST /register/options` (`Depends(get_current_user)`, no rate limit — registration only runs while authenticated).

**Rate-limited login/verify endpoint — THE `response: Response` REQUIREMENT** (lines 75-77, exact signature to copy):
```python
@router.post("/verify")
@limiter.limit("5/minute")
async def verify_mfa_at_login(request: Request, response: Response, req: MFAVerifyLoginRequest):
```
Every new `passkey_endpoints.py` route decorated with `@limiter.limit(...)` (both `/login/options` and `/login/verify` per RESEARCH.md Pitfall 2) MUST include `response: Response` in its signature exactly like this, or it 500s at runtime (invisible to unit tests that call the function directly — must be verified with `TestClient`).

**JWT-minting + sensitive-field filtering pattern at login** (lines 97-117, `verify_mfa_at_login` tail):
```python
db = get_database()
user = await db.users.find_one({"email": email})
if not user:
    raise HTTPException(status_code=404, detail="User not found")

role = user.get("role", "user")
tenant_id = user.get("tenantId") or None
access_token = create_access_token(
    data={"sub": email, "role": role, "tenant_id": tenant_id},
    expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
)
user_data = {k: v for k, v in user.items() if k not in ("password", "_id", "mfa")}
user_data["id"] = str(user.get("_id", ""))

return {
    "access_token": access_token,
    "token_type": "bearer",
    "success": True,
    "user": user_data,
}
```
Passkey login (`POST /login/verify`) reuses this exact shape, additionally calling `create_refresh_token(data={"sub": email})` (per RESEARCH.md Pattern 4) and excluding `"webauthn_credentials"` from `user_data` alongside `"mfa"` (RESEARCH.md Pitfall 4). Token payload keys are `sub`/`role`/`tenant_id` — identical across every login path in this codebase; do not deviate.

**Error-handling pattern** (repeated throughout, e.g. lines 69-72, 93-95, 124-126): every service-layer `{"success": False, "error": ...}` result is converted to `raise HTTPException(status_code=400 or 401, detail=result["error"])` in the endpoint layer; success results are returned as-is. Passkey endpoints follow this identically (400 for setup/registration failures, 401 for authentication/login failures per RESEARCH.md's ceremony flow).

---

### `backend/router_registry.py` (config, MODIFIED)

**Analog:** existing adjacent `_load(...)` calls, lines 91-92 (both read this session):
```python
_load(app, "mfa_endpoints",            "router")
_load(app, "sso_endpoints",            "router")
```
Add directly below, in the same auth-adjacent grouping block (lines 86-92, which also contains `authentication_endpoints`, `auth_password_reset_endpoints`):
```python
_load(app, "passkey_endpoints",        "router")   # NEW
```
`_load(app, module_name, attr="router", **kwargs)` is defined at line 41 and is resilient (swallows import/attach errors and logs, per the comment at line 34) — no special handling needed beyond the one-line call.

---

### `components/LoginPage.tsx` (component, MODIFIED)

**Analog:** itself — full file read (282 lines). Existing patterns to extend:

**Two-phase MFA step-up branch in `handleLogin`** (lines 54-81):
```typescript
const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);
    try {
        const data = await api.login(email, password);
        // Two-phase MFA login: password verified, TOTP challenge next
        if (data.mfa_required && data.mfa_session_token) {
            setMfaSessionToken(data.mfa_session_token);
            return;
        }
        if (onLogin) {
            await onLogin(email, password);
        } else {
            window.location.reload();
        }
    } catch (err) {
        console.error('Login error:', err);
        setError('Invalid email or password.');
    } finally {
        setIsLoading(false);
    }
};
```

**Conditional-alternative-login-method rendering pattern (SSO button)** (lines 30-37, 225-249) — the pattern to clone for "Sign in with a passkey":
```typescript
const [ssoEnabled, setSsoEnabled] = useState(false);
useEffect(() => {
    api.fetchSsoProviders().then((p: any) => {
        setSsoEnabled(Array.isArray(p?.providers) && p.providers.length > 0);
    }).catch(() => {});
}, []);
...
{ssoEnabled && (
    <>
        <div className="mt-5 flex items-center gap-3">...or continue with...</div>
        <a href="/api/sso/google/login" className="...">Sign in with Google</a>
    </>
)}
```
Per RESEARCH.md's resolved Open Question (email-first flow), the passkey button is NOT unconditional like SSO — it should appear once an email is entered (or as a static "Sign in with a passkey" button that calls `api.loginPasskeyOptions(email)` on click, guarding on `email` being non-empty since `AUTH-01`'s login flow requires the email to look up `allow_credentials`). Structurally it slots into the same divider/button block area (around line 250-256) as a third option alongside password submit and Google SSO, not as a `useEffect`-gated conditional render.

**Modal-swap-on-state pattern (MFA step-up UI)** (lines 83-91):
```typescript
if (mfaSessionToken) {
    return (
        <MFAVerifyModal
            mfaSessionToken={mfaSessionToken}
            onSuccess={handleMfaSuccess}
            onCancel={() => { setMfaSessionToken(null); setIsLoading(false); }}
        />
    );
}
```
Not directly needed for passkey login (single round-trip, no intermediate modal state required for AUTH-01 unless UX wants a "waiting for authenticator" overlay), but shows the established idiom if a `PasskeyLoginPrompt` overlay component is wanted during the `navigator.credentials.get()` browser prompt wait.

**`api.login()` client function this file calls** (`services/apiService.ts` lines 366-391, see below) — the token-storage side effect (`sessionStorage.setItem('token', data.access_token)`) must be replicated by the new `loginPasskeyVerify()` client function.

---

### `components/UserProfilePage.tsx` + `components/MFASetupWizard.tsx` (component, MODIFIED + new `PasskeySetupModal.tsx`)

**Analog:** `components/MFASetupWizard.tsx` (read lines 1-60) for the new `PasskeySetupModal.tsx`; `components/UserProfilePage.tsx` Security card (read lines 150-235) for the new "Passkeys" row.

**MFASetupWizard step-based modal pattern** (lines 1-49):
```typescript
import React, { useState } from 'react';
import { authFetch } from '../services/apiService';

export default function MFASetupWizard({ onClose, onEnabled }: MFASetupWizardProps) {
    const [step, setStep] = useState<1 | 2 | 3>(1);
    ...
    const startSetup = async () => {
        setLoading(true); setError('');
        try {
            const r = await authFetch('/api/mfa/setup');
            const d = await r.json();
            if (!r.ok) throw new Error(d.detail || 'Setup failed');
            setSecret(d.secret);
            setQrBase64(d.qr_base64);
            setQrUri(d.qr_uri);
            setStep(2);
        } catch (e: any) { setError(e.message); }
        finally { setLoading(false); }
    };

    const verifySetup = async () => {
        ...
        try {
            const r = await authFetch('/api/mfa/verify-setup', {
                method: 'POST',
                body: JSON.stringify({ totp_code: code }),
            });
            const d = await r.json();
            if (!r.ok) throw new Error(d.detail || 'Verification failed');
            setBackupCodes(d.backup_codes || []);
            setStep(3);
        } catch (e: any) { setError(e.message); }
        finally { setLoading(false); }
    };
```
`PasskeySetupModal.tsx` follows the same shape but is simpler (no multi-step QR/backup-code flow) — step 1: call `api.registerPasskeyOptions()`, then call `startRegistration(optionsJSON)` from `@simplewebauthn/browser`, then step 2: prompt for a device name, then call `api.registerPasskeyVerify(credential, sessionId, deviceName)`.

**Security card row pattern in UserProfilePage.tsx** (lines 166-192, the MFA row — exact structure to clone for a "Passkeys" row):
```tsx
<div className="flex items-center justify-between py-4 border-b border-gray-200 dark:border-gray-700">
    <div className="flex items-center gap-3">
        {mfaEnabled
            ? <ShieldCheckIcon size={24} className="text-green-500" />
            : <ShieldAlertIcon size={24} className="text-amber-500" />
        }
        <div>
            <p className="text-sm font-medium text-gray-900 dark:text-white">Two-Factor Authentication (TOTP)</p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
                {mfaEnabled ? `Enabled — ${mfaBackupRemaining} backup code${mfaBackupRemaining !== 1 ? 's' : ''} remaining` : 'Not enabled — your account is less secure without 2FA'}
            </p>
        </div>
    </div>
    {mfaEnabled ? (
        <button onClick={...} className="px-4 py-2 text-sm font-medium text-red-600 border border-red-300 dark:border-red-700 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20">
            {showDisableMfa ? 'Cancel' : 'Disable 2FA'}
        </button>
    ) : (
        <button onClick={() => setShowMfaSetup(true)} className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">
            Enable 2FA
        </button>
    )}
</div>
```
And the overlay-render pattern (lines 226-234):
```tsx
{showMfaSetup && (
    <MFASetupWizard
        onClose={() => setShowMfaSetup(false)}
        onEnabled={() => { setMfaEnabled(true); setMfaBackupRemaining(8); }}
    />
)}
```
New "Passkeys" row goes directly below the MFA row inside the same Security card, listing registered passkeys (device_name, created_at) with per-credential delete buttons, plus an "Add a passkey" button that opens `PasskeySetupModal`. State needed: `passkeys: PasskeyListItem[]`, `showPasskeySetup: boolean` — fetched via `authFetch('/api/passkey/list')` in the same `useEffect` block that currently fetches `/api/mfa/status` (line 47).

---

### `services/apiService.ts` (utility, MODIFIED)

**Analog: sibling MFA client functions** (lines 291-322, full block):
```typescript
// --- MFA / SSO Services ---
export const fetchMfaStatus = async () => {
    const res = await authFetch(`${API_BASE}/mfa/status`);
    if (!res.ok) throw new Error("Failed to fetch MFA status");
    return res.json();
};

export const setupMfa = async () => {
    const res = await authFetch(`${API_BASE}/mfa/setup`, { method: 'POST' });
    if (!res.ok) throw new Error("Failed to initiate MFA setup");
    return res.json();
};

export const verifyMfaSetup = async (code: string) => {
    const res = await authFetch(`${API_BASE}/mfa/verify-setup`, {
        method: 'POST',
        body: JSON.stringify({ totp_code: code }),
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "MFA verification failed");
    }
    return res.json();
};

export const disableMfa = async (code: string) => {
    const res = await authFetch(`${API_BASE}/mfa/disable`, {
        method: 'POST',
        body: JSON.stringify({ totp_code: code }),
    });
    if (!res.ok) throw new Error("Failed to disable MFA");
    return res.json();
};
```
New `// --- Passkey Services ---` block adds `registerPasskeyOptions`, `registerPasskeyVerify`, `listPasskeys`, `deletePasskey`, `renamePasskey` following this exact `authFetch(...)` + `if (!res.ok) throw new Error(...)` + `return res.json()` idiom, all using `authFetch` (authenticated) since registration/management always happens post-login.

**Analog: unauthenticated `login()` (login/register options+verify are unauthenticated too)** (lines 366-391, full function):
```typescript
export const login = async (username: string, password: string): Promise<any> => {
    // We don't use authFetch here because we don't not need a token to login
    const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: username, password }),
    });
    if (res.status === 429) {
        throw new Error('Too many login attempts. Please wait a moment and try again.');
    }
    if (!res.ok) {
        throw new Error('Invalid credentials');
    }
    const data = await res.json();
    if (data.access_token) {
        _sessionEnding = false;
        _lastRefreshFailTime = 0;
        sessionStorage.setItem('token', data.access_token);
    }
    return data;
};
```
`loginPasskeyOptions(email)` and `loginPasskeyVerify(credential, sessionId)` must use plain `fetch` (not `authFetch`) exactly like `login()` — there is no JWT yet at this point in the flow — and `loginPasskeyVerify` must replicate the same `sessionStorage.setItem('token', data.access_token)` + `_sessionEnding`/`_lastRefreshFailTime` reset side effect on success, since it is a genuine login entry point parallel to `login()`.

---

### `backend/tests/test_passkey_auth.py` (test, NEW)

**Analog:** `backend/tests/test_auth_mfa.py` (targeted reads: header/helpers lines 1-60, `TestMFAVerifyLogin` class lines 250-330+)

**File header + DB-mock helper pattern** (lines 1-42):
```python
"""
Unit tests for authentication and MFA endpoints.

These tests mount only the relevant routers on a minimal FastAPI app and
patch get_database() / external services so no real MongoDB is required.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

def _make_db_mock(user=None, role_obj=None, login_record=None):
    """Return a minimal async DB mock that supports the auth query surface."""
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.update_one = AsyncMock()
    col.delete_one = AsyncMock()
    raw_db = MagicMock()
    raw_db.users = MagicMock()
    raw_db.users.find_one = AsyncMock(return_value=user)
    ...
    db = MagicMock()
    db._db = raw_db
    db.users = MagicMock()
    db.users.find_one = AsyncMock(return_value=user)
    db.users.update_one = AsyncMock()
    ...
    return db
```

**Authenticated-app test-double pattern (skip real JWT validation)** (lines 256-271, `TestMFAVerifyLogin._make_authenticated_mfa_app`):
```python
def _make_authenticated_mfa_app(self, db_mock):
    """Build MFA app with mocked get_current_user (skips JWT validation)."""
    from auth_types import TokenData
    from authentication_service import get_current_user
    mock_token_data = TokenData(
        username="user@example.com", role="Viewer", tenant_id="t1", mfa_verified=True,
    )
    app = _make_mfa_app()
    app.dependency_overrides[get_current_user] = lambda: mock_token_data
    return app
```

**Service-layer patch + TestClient round-trip pattern** (lines 273-291, `test_verify_mfa_login_success`):
```python
def test_verify_mfa_login_success(self):
    user = _make_hashed_user()
    db = _make_db_mock(user=user)
    app = _make_mfa_app()
    with patch("mfa_endpoints.get_database", return_value=db), \
         patch("mfa_service.verify_mfa_token", new_callable=AsyncMock,
               return_value={"success": True, "email": "user@example.com"}):
        with TestClient(app) as client:
            resp = client.post("/api/mfa/verify", json={...})
    assert resp.status_code == 200
```
`test_passkey_auth.py` clones this exact `patch("passkey_endpoints.get_database", ...)` + `patch("passkey_service.<ceremony_fn>", new_callable=AsyncMock, return_value=...)` + `TestClient(app).post(...)` shape for `/api/passkey/register/verify` and `/api/passkey/login/verify`, but per RESEARCH.md's Standard Stack, ceremony-level tests (full `generate_registration_options`/`verify_registration_response` round trips) should instead use `soft_webauthn.SoftWebauthnDevice` to drive the real `webauthn` library functions rather than mocking `passkey_service` internals — reserve the `patch(...)`-based approach (shown above) for endpoint-layer tests (rate limiting, error-code mapping, response shape) and use `SoftWebauthnDevice` for service-layer ceremony-correctness tests.

---

## Shared Patterns

### Auth dependency injection
**Source:** `backend/authentication_service.py` — `get_current_user` (lines 169-171), `require_admin` (lines 194-203)
**Apply to:** All new authenticated passkey endpoints (`/register/options`, `/register/verify`, `/list`, `/rename`, `/delete`)
```python
async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Dependency to get the current user; performs async revocation check."""
    return await verify_token_async(token)
```
Use `current_user=Depends(get_current_user)` exactly as `mfa_endpoints.py` does; do NOT use `require_mfa` (passkey enrollment doesn't require prior MFA step-up) or invent a new dependency.

### JWT minting (read-only reuse — do not modify)
**Source:** `backend/authentication_service.py` lines 50-66
```python
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "jti": uuid.uuid4().hex})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh", "jti": uuid.uuid4().hex})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
```
**Apply to:** `passkey_endpoints.py` `/login/verify` only — call these two functions unmodified with `data={"sub": email, "role": role, "tenant_id": tenant_id}` for access token and `data={"sub": email}` for refresh token (identical shape to every other login path). Zero lines of `authentication_service.py` change.

### Rate limiting with `response: Response`
**Source:** `backend/mfa_endpoints.py` line 76-77 (see Pattern Assignments above)
**Apply to:** `passkey_endpoints.py` `/login/options` and `/login/verify` (login-attempt-enumeration protection; registration routes are behind auth already so lower priority per RESEARCH.md Pitfall 2)

### Error handling / HTTPException mapping
**Source:** `backend/mfa_endpoints.py` throughout — `{"success": False, "error": ...}` from service layer becomes `raise HTTPException(status_code=400 or 401, detail=result["error"])` in endpoint layer
**Apply to:** All new passkey_endpoints.py routes

### Sensitive-field filtering on user-object responses
**Source:** `backend/mfa_endpoints.py` line 109: `user_data = {k: v for k, v in user.items() if k not in ("password", "_id", "mfa")}`
**Apply to:** `passkey_endpoints.py` `/login/verify` — extend the exclusion tuple to `("password", "_id", "mfa", "webauthn_credentials")` per RESEARCH.md Pitfall 4

## No Analog Found

None — every file in this phase's scope has a strong, directly-analogous existing file to clone from (`mfa_service.py`/`mfa_endpoints.py` pair is a near-exact structural precedent per RESEARCH.md's own conclusion).

## Metadata

**Analog search scope:** `backend/` (mfa_service.py, mfa_endpoints.py, authentication_service.py, router_registry.py, tests/test_auth_mfa.py), `components/` (LoginPage.tsx, UserProfilePage.tsx, MFASetupWizard.tsx), `services/apiService.ts`
**Files scanned:** 8 (all read in full or via targeted non-overlapping offset/limit reads; no re-reads of already-loaded ranges)
**Pattern extraction date:** 2026-07-08
