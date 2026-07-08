# Phase 34: Passkey and WebAuthn Authentication - Research

**Researched:** 2026-07-08
**Domain:** WebAuthn/FIDO2 passkey registration and login, composed alongside an existing mature multi-method auth stack (password + bcrypt, TOTP MFA, SAML/OIDC SSO) in a Python/FastAPI/Motor backend with a React/TypeScript SPA frontend
**Confidence:** HIGH (backend integration points, tenant-isolation mechanics, existing auth patterns — all confirmed by direct in-session reads of this codebase) / MEDIUM (WebAuthn library API surface and current package versions — confirmed via WebSearch + direct registry verification, not Context7)

<user_constraints>
## User Constraints (from CONTEXT.md)

No CONTEXT.md exists for this phase. This project runs in yolo/auto mode this milestone — no `/gsd-discuss-phase` was run for Phase 34 (or any other v3.0 phase, per `.planning/STATE.md`). This research and the resulting plan must proceed from `.planning/REQUIREMENTS.md` + `.planning/ROADMAP.md` + direct codebase inspection only. There are no locked decisions, discretion notes, or deferred ideas to copy verbatim — everything below is this agent's own research-derived recommendation, and items needing a human product decision are called out explicitly in **Open Questions**.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AUTH-01 | Users can register and log in with a WebAuthn/FIDO2 passkey as an alternative to password/SSO/TOTP, with no regression to existing SAML/OIDC/TOTP flows | See Architecture Patterns → Patterns 1-4 (new `passkey_service.py`/`passkey_endpoints.py` pair cloned from `mfa_service.py`/`mfa_endpoints.py`'s file shape; `webauthn_credentials` array on the user document following `mfa: {...}`'s nested-field precedent; login-flow branch added to `authentication_endpoints.login_for_access_token` alongside the existing MFA branch, not replacing it) and Common Pitfalls (regression protection for the existing password/MFA/SSO paths) |
</phase_requirements>

## Summary

This phase adds a fourth authentication method to a codebase that already cleanly supports three (password+bcrypt in `auth_utils.py`, TOTP MFA in `mfa_service.py`/`mfa_endpoints.py`, SAML/OIDC SSO in `sso_service.py`/`sso_endpoints.py`). The architectural shape of the work is well-precedented by the existing MFA and SSO modules: a new `passkey_service.py` (ceremony logic + credential storage helpers) paired with a new `passkey_endpoints.py` (FastAPI routes), registered in `router_registry.py` exactly like `mfa_endpoints`/`sso_endpoints` are today. This is composition against an established pattern, not invention — the same conclusion prior v3.0 phases (28, 29) reached about their own domains.

**The standard library split is backend `webauthn` (PyPI package name `webauthn`, published by duo-labs/Cisco Duo, current version 3.0.0, requires Python >=3.10 — this codebase runs 3.12) for the server-side registration/authentication ceremony, and frontend `@simplewebauthn/browser` (current version 13.3.0, ~2.5M weekly downloads) for the browser-side `navigator.credentials` plumbing.** Neither is currently installed (`pip show webauthn` and a `package.json` grep both returned nothing this session). Both packages are recommended over hand-rolling: the backend library owns CBOR/COSE attestation-object parsing and signature verification (genuine cryptographic complexity, not just boilerplate — hand-rolling this is a real security risk), while the frontend library owns base64url/ArrayBuffer conversion (finicky but not cryptographic — still worth the ~5KB dependency to avoid a class of encoding bugs that silently corrupt credential IDs). Both packages passed a **Package Legitimacy Gate run this session with mixed results — see Package Legitimacy Audit; the backend `webauthn` package was flagged `[SUS]`** by the automated check due to a "too-new" signal (its most recent release, 3.0.0, was published 2026-06-29 — a signal artifact of recent-release-cadence, not package age; the underlying project has shipped on GitHub since 2019 under the well-known duo-labs/Cisco Duo organization) and must therefore go behind a `checkpoint:human-verify` task before install, per the standing protocol, despite this research's assessment that it is very likely a legitimate, actively-maintained package.

**Credential storage follows the existing `mfa: {...}` nested-field precedent on the user document** (not a new top-level collection) — a `webauthn_credentials: [{credential_id, public_key, sign_count, transports, device_name, created_at, last_used_at}, ...]` array, mirroring how `mfa.secret_encrypted`/`mfa.backup_codes_hashed` already live inside the same `users` document rather than a separate `mfa_credentials` collection. This keeps passkey data inside the same tenant-isolated `users` collection with no new collection, no new tenant-isolation surface to reason about, and no new index to add beyond what already exists on `users.email`.

**The short-lived WebAuthn challenge (server-side state between the options call and the verify call) should use the same in-memory-dict-with-TTL-pruning pattern already used twice in this codebase** — `mfa_service._mfa_sessions` (5-minute TTL) and `sso_service._oidc_states` (10-minute TTL), both plain Python dicts pruned on write/read, with no Redis dependency required. This would be the third instance of an already-established, already-reviewed pattern, not a new architectural decision. A WebAuthn challenge should use a short TTL (60-120 seconds is standard — ceremonies are fast, human-timed interactions) and must be single-use (deleted/popped on successful verification, exactly like `sso_service._oidc_states.pop(state, None)` already does).

**RP ID is a single static value for this platform.** WebAuthn's Relying Party ID must be the exact hostname or a registrable parent domain — this codebase already resolves its own public origin via the `PLATFORM_URL` environment variable in three other places (`agent_download_endpoints.py`, `remote_endpoints.py`, `agent_chat_endpoints.py`), and Phase 29's research confirmed custom domains (added in that phase) are scoped only to the public, unauthenticated Trust Center page — the authenticated app (where login, and therefore passkey registration/authentication, happens) stays on the platform's own origin. This means RP ID can be derived once from `PLATFORM_URL` (stripped of scheme/port) at module load, with no per-tenant or per-request RP ID logic needed — the multi-tenant-subdomain RP ID pattern documented for products like `tenant.app.example.com` does not apply here, because this platform does not put tenants on distinct subdomains for the authenticated app.

**The most important regression-protection finding: `authentication_endpoints.py` is already 479 lines**, five lines under CLAUDE.md's 500-line file-size rule. Adding a full passkey login branch inline to `login_for_access_token` would push this file over the limit. The plan should add passkey *login* as a **separate endpoint** (e.g., `POST /api/passkey/login/verify`, living in the new `passkey_endpoints.py`) that independently authenticates a user and mints a JWT via the same `create_access_token`/`create_refresh_token` helpers `authentication_endpoints.py` already imports from `authentication_service.py` — rather than editing the existing `/api/auth/login` password-only endpoint. This is both a file-size constraint and the architecturally cleaner choice: it makes "no regression to existing SAML/OIDC/TOTP flows" trivially true by construction, since none of `authentication_endpoints.py`, `mfa_service.py`, `mfa_endpoints.py`, `sso_service.py`, or `sso_endpoints.py` need to change at all for AUTH-01's login path. The one shared touchpoint is `authentication_service.py`'s `create_access_token`/`create_refresh_token`, which passkey login reuses read-only (calls them, doesn't modify them) — the JWT shape passkey login mints is therefore identical to every other login path's JWT by construction, not by parallel reimplementation.

**Primary recommendation:** Add `webauthn` (PyPI) + `@simplewebauthn/browser` (npm) as new dependencies (each gated behind `checkpoint:human-verify` per the Package Legitimacy Audit below); build `passkey_service.py` + `passkey_endpoints.py` as a new sibling pair cloned from the `mfa_service.py`/`mfa_endpoints.py` shape, registered in `router_registry.py`; store credentials in a new `webauthn_credentials` array on the existing `users` document (no new collection); store the transient challenge in a third instance of the existing in-memory-TTL-dict pattern; derive a single static RP ID from `PLATFORM_URL` at module load; add passkey login as an independent new endpoint that mints JWTs via the existing `create_access_token`/`create_refresh_token` helpers, touching zero lines of `authentication_endpoints.py`, `mfa_service.py`/`mfa_endpoints.py`, or `sso_service.py`/`sso_endpoints.py`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| WebAuthn ceremony cryptography (attestation/assertion verification, COSE public key parsing, signature checks) | API / Backend | — | Genuine cryptographic complexity; owned entirely by the `webauthn` (py_webauthn) library server-side, never the browser or a hand-rolled implementation |
| `navigator.credentials.create()`/`.get()` invocation + base64url/ArrayBuffer marshalling | Browser / Client | — | Must run in the browser (WebAuthn is a browser API); `@simplewebauthn/browser` owns the encoding plumbing so application code only handles JSON |
| Passkey credential storage (credential ID, public key, sign count, transports) | Database / Storage | API / Backend | New `webauthn_credentials` array on the existing tenant-isolated `users` document, written only via backend endpoints — same shape as `mfa.secret_encrypted` today |
| Registration/authentication challenge (short-lived, single-use, server-side) | API / Backend (in-process state) | — | Must not be trusted to the client; follows the existing `_mfa_sessions`/`_oidc_states` in-memory-dict-with-TTL pattern already proven twice in this codebase |
| JWT minting after successful passkey login | API / Backend | — | Reuses `authentication_service.create_access_token`/`create_refresh_token` unmodified — passkey login is a new credential-verification path feeding the same token-issuance code every other login method already shares |
| RP ID / origin resolution | API / Backend | — | Single static value derived from `PLATFORM_URL` at module load; the authenticated app has one origin (custom domains from Phase 29 only apply to the public Trust Center page) |
| Passkey enrollment/management UI (register, list, rename, revoke a passkey) | Browser / Client (existing gated SPA) | API / Backend | New tab/section inside `UserProfilePage.tsx`'s existing "Security" card, alongside the existing TOTP enable/disable UI — same pattern as `MFASetupWizard.tsx`, no new page/route needed |
| Passkey login UI (the "Sign in with a passkey" button on the login screen) | Browser / Client (existing `LoginPage.tsx`) | API / Backend | New button alongside the existing password form and conditional SSO button in `LoginPage.tsx` — no new page needed, this component already conditionally renders alternative login methods (SSO) |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `webauthn` (PyPI; import name `webauthn`; GitHub `duo-labs/py_webauthn`) | `3.0.0` [ASSUMED — package name and API surface discovered via WebSearch/GitHub README, not Context7; version 3.0.0 itself is `VERIFIED: PyPI registry` via `pip index versions webauthn` + PyPI JSON API this session, but per the package-name-provenance rule this is tagged ASSUMED overall until the Package Legitimacy Gate's SUS flag is human-cleared — see Package Legitimacy Audit] | Server-side WebAuthn ceremony: generates registration/authentication options, verifies attestation/assertion responses, parses COSE public keys | The de facto standard Python WebAuthn/FIDO2 library (Cisco Duo's official implementation); handles CBOR/COSE parsing and cryptographic signature verification that would be a serious security risk to hand-roll |
| `@simplewebauthn/browser` (npm) | `13.3.0` [CITED: npmjs.com/package/@simplewebauthn/browser, simplewebauthn.dev/docs/packages/browser — official docs; legitimacy check returned OK this session, so this is the one package in this phase meeting the bar for VERIFIED status] | Browser-side `startRegistration()`/`startAuthentication()` wrapping `navigator.credentials.create()`/`.get()`, plus `browserSupportsWebAuthn()` feature detection | The companion library to `@simplewebauthn/server` (not needed here — backend is Python) and the standard client-side WebAuthn wrapper; ~2.5M weekly downloads, actively maintained by MasterKale/SimpleWebAuthn |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `soft-webauthn` (PyPI; GitHub `bodik/soft-webauthn`) | `0.1.4` [ASSUMED — discovered via WebSearch; legitimacy check flagged SUS this session, see Package Legitimacy Audit] | Test-only software authenticator emulator (`SoftWebauthnDevice.create()`/`.get()`) for driving `webauthn`'s own ceremony functions in pytest without a real browser/hardware key | Wave 0 test infrastructure only (`requirements-dev.txt` / test extras, never a production dependency) — see Validation Architecture |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `webauthn` (py_webauthn) for server-side ceremony (recommended) | Hand-rolled CBOR/COSE parsing + signature verification | This is the one part of WebAuthn that is genuinely cryptographic, not just plumbing — hand-rolling attestation/assertion verification is exactly the kind of security-critical code this codebase's own conventions (bcrypt for passwords, established libraries for JWT/TOTP/SAML) argue against reimplementing |
| `@simplewebauthn/browser` for client-side calls (recommended) | Hand-rolled `navigator.credentials.create()`/`.get()` + manual base64url/ArrayBuffer conversion | Technically feasible (this is finicky encoding, not cryptography) and would avoid one new npm dependency, but the library is small (~5KB), extremely standard, and removes an entire class of silent credential-ID-corruption bugs from manual base64url handling — given the "don't hand-roll security-critical plumbing" principle also applies to auth-adjacent encoding bugs that are hard to test exhaustively, the dependency is worth it |
| `webauthn_credentials` array embedded on the `users` document (recommended) | A new top-level `webauthn_credentials` Mongo collection, tenant-scoped like every other domain collection | The MFA precedent (`mfa.*` nested fields on `users`) is the more direct analog — a passkey credential is 1:1 owned by a single user, has no independent lifecycle, and doesn't need its own collection/indexes; a new collection would be justified only if credentials needed cross-user querying, which nothing in AUTH-01 requires |
| In-memory dict with TTL pruning for the WebAuthn challenge (recommended, third instance of an existing pattern) | Redis-backed challenge storage | `redis>=5.0.0` is already a dependency and used optionally by `rate_limiter.py`, but both existing short-lived-state precedents in this codebase (`_mfa_sessions`, `_oidc_states`) use plain in-memory dicts with no Redis dependency — introducing Redis as a *hard* requirement for this phase would be new infrastructure coupling neither precedent has, and a WebAuthn challenge's TTL (60-120s) is even shorter-lived than the MFA session (5 min) it would be modeled after |

**Installation:**
```bash
# Backend (add to backend/requirements.txt under a new "WebAuthn / Passkeys" section)
pip install "webauthn>=3.0.0,<4.0.0"

# Backend, test-only (add to whatever dev/test extras mechanism this repo uses, or a requirements-dev.txt if one exists — none was found this session; confirm during planning)
pip install "soft-webauthn>=0.1.4,<0.2.0"

# Frontend
npm install @simplewebauthn/browser@^13.3.0
```

**Version verification:** `webauthn` 3.0.0 confirmed via `pip index versions webauthn` and `https://pypi.org/pypi/webauthn/json` this session (`requires_python: >=3.10`) — this codebase's `backend/requirements.txt` already pins `setuptools`/Python for 3.12.x-3.13.x, so no compatibility concern. `@simplewebauthn/browser` 13.3.0 confirmed via `npm view @simplewebauthn/browser version` this session (last published 2026-03-10 per `npm view ... time.modified`). `soft-webauthn` 0.1.4 confirmed via PyPI JSON API this session. Neither `webauthn` nor `@simplewebauthn/browser` currently appears in `backend/requirements.txt` or `package.json` — confirmed via grep this session; both are genuinely new dependencies for this phase.

## Package Legitimacy Audit

| Package | Registry | Age (latest release) | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|----------------------|-----------|--------------|---------|-------------|
| `webauthn` | PyPI | 3.0.0 published 2026-06-29 (~1 week before this research date — flagged "too-new" by the automated gate; the underlying `duo-labs/py_webauthn` project itself has existed on GitHub since 2019) | Unknown (gate could not resolve PyPI download stats) | `github.com/duo-labs/py_webauthn` (Cisco Duo's official organization) | **[SUS]** — reasons: `too-new`, `unknown-downloads` | Flagged — planner MUST add a `checkpoint:human-verify` task before this package is installed. This research's assessment: the SUS signal is very likely a false positive driven by measuring "latest release recency" rather than "package/maintainer age" — `duo-labs` is Cisco Duo's official GitHub organization and this library is the most commonly cited Python WebAuthn implementation across independent WebAuthn implementation guides — but the automated gate's verdict is followed per protocol regardless of this assessment. |
| `soft-webauthn` | PyPI | 0.1.4 published 2022-07-08 | Unknown (gate could not resolve PyPI download stats) | `github.com/bodik/soft-webauthn` | **[SUS]** — reason: `unknown-downloads` | Flagged — planner MUST add a `checkpoint:human-verify` task before this test-only dependency is installed. Lower risk than `webauthn` itself since it is never a production/runtime dependency (test-suite-only), but the protocol applies equally. |
| `@simplewebauthn/browser` | npm | 13.3.0 published 2026-03-10 | ~2,525,874/week | `github.com/MasterKale/SimpleWebAuthn` | **[OK]** | Approved — no checkpoint required. |
| `@simplewebauthn/server` | npm | 13.3.2 published 2026-06-24 | ~1,867,609/week | `github.com/MasterKale/SimpleWebAuthn` | **[SUS]** — reason: `too-new` | **Not recommended for this phase** — this codebase's backend is Python (`webauthn`/py_webauthn owns server-side ceremony logic); `@simplewebauthn/server` would only be relevant if a future phase introduced a Node.js backend service. Listed here only because it was checked alongside its sibling package; the planner should not install it. |

**Packages removed due to `[SLOP]` verdict:** none.
**Packages flagged as suspicious `[SUS]`:** `webauthn` (PyPI, production dependency) and `soft-webauthn` (PyPI, test-only dependency) — both require a `checkpoint:human-verify` task in the plan before `pip install` runs. `@simplewebauthn/server` is also SUS but is not being recommended for installation in this phase at all.

*`webauthn` and `soft-webauthn` were discovered via WebSearch/training knowledge, not Context7 or official-docs-with-OK-verdict, so both remain tagged `[ASSUMED]` for package-name provenance regardless of their registry existence being independently confirmed — per the standing provenance rule, registry existence alone does not confer VERIFIED status.*

## Architecture Patterns

### System Architecture Diagram

```
REGISTRATION (authenticated user, e.g. from UserProfilePage.tsx "Security" card)
  Browser                          Backend (passkey_endpoints.py)              Storage
    │                                       │                                     │
    │  POST /api/passkey/register/options   │                                     │
    │ ───────────────────────────────────►  │                                     │
    │                                       │  generate_registration_options()    │
    │                                       │  (webauthn lib; rp_id from          │
    │                                       │   PLATFORM_URL; exclude existing    │
    │                                       │   credential_ids for this user)     │
    │                                       │  store challenge in-memory,         │
    │                                       │  keyed by short-lived session id,   │
    │                                       │  TTL ~90s (3rd instance of the      │
    │                                       │  _mfa_sessions/_oidc_states pattern)│
    │  ◄─────────────── options JSON ────── │                                     │
    │                                       │                                     │
    │  startRegistration(options)           │                                     │
    │  (@simplewebauthn/browser wraps       │                                     │
    │   navigator.credentials.create())     │                                     │
    │  ── user completes platform/          │                                     │
    │     roaming authenticator prompt ──   │                                     │
    │                                       │                                     │
    │  POST /api/passkey/register/verify    │                                     │
    │ ───────────────────────────────────►  │                                     │
    │  { credential, session_id }           │  verify_registration_response()     │
    │                                       │  (checks challenge, origin, rp_id,  │
    │                                       │   signature) ─── pop challenge ───► │
    │                                       │  append to user.webauthn_credentials│
    │                                       │  { credential_id, public_key,       │
    │                                       │    sign_count: 0, device_name,      │
    │                                       │    transports, created_at }         │
    │                                       │                                     │  db.users.update_one(
    │  ◄─────────────── success ─────────── │                                     │   {email}, {$push: {...}})
    │                                       │                                     │

LOGIN (unauthenticated visitor, from LoginPage.tsx "Sign in with a passkey" button)
  Browser                          Backend (passkey_endpoints.py)              Storage
    │  POST /api/passkey/login/options      │                                     │
    │  { email }  (or empty for              │  db._db.users.find_one({email})    │
    │   discoverable/usernameless flow)      │  (bypasses tenant isolation —      │
    │ ───────────────────────────────────►  │   same reason authentication_      │
    │                                       │  endpoints.login already does this: │
    │                                       │  no JWT/tenant context exists yet)  │
    │                                       │  generate_authentication_options()  │
    │                                       │  (allow_credentials = user's stored │
    │                                       │   credential_ids)                   │
    │                                       │  store challenge in-memory, TTL~90s │
    │  ◄─────────────── options JSON ────── │                                     │
    │                                       │                                     │
    │  startAuthentication(options)         │                                     │
    │  ── user completes authenticator      │                                     │
    │     prompt (biometric/PIN/key) ──     │                                     │
    │                                       │                                     │
    │  POST /api/passkey/login/verify       │                                     │
    │ ───────────────────────────────────►  │                                     │
    │  { credential, session_id }           │  verify_authentication_response()   │
    │                                       │  (checks challenge, origin, rp_id,  │
    │                                       │   credential_public_key,            │
    │                                       │   credential_current_sign_count)    │
    │                                       │  new_sign_count > stored? update :  │
    │                                       │  flag possible clone (Pitfall 3)    │
    │                                       │  create_access_token(...)  ◄────────┤  (same helper every
    │                                       │  create_refresh_token(...)          │   other login path uses
    │  ◄──── access_token, refresh_token ── │                                     │   — authentication_service.py,
    │        (identical JWT shape to        │                                     │   untouched by this phase)
    │        password/SSO/MFA login)        │                                     │
```

### Recommended Project Structure
```
backend/
├── passkey_service.py           # NEW — ceremony logic (options/verify wrappers around `webauthn` lib), challenge TTL store, credential CRUD helpers on users.webauthn_credentials
├── passkey_endpoints.py         # NEW — /api/passkey/* FastAPI router (register/options, register/verify, login/options, login/verify, list, rename, delete)
├── router_registry.py           # MODIFIED — one new `_load(app, "passkey_endpoints", "router")` line, alongside mfa_endpoints/sso_endpoints
├── requirements.txt             # MODIFIED — add `webauthn>=3.0.0,<4.0.0` under a new "WebAuthn / Passkeys" section (mirrors existing "Authentication & Security" section style)
├── tests/
│   └── test_passkey_auth.py     # NEW — pytest suite using soft-webauthn's SoftWebauthnDevice to drive full ceremonies without a browser

components/
├── LoginPage.tsx                # MODIFIED — add a "Sign in with a passkey" button alongside the existing password form + conditional SSO button
├── UserProfilePage.tsx          # MODIFIED — add a "Passkeys" row to the existing "Security" card, alongside the TOTP enable/disable row
└── PasskeySetupModal.tsx        # NEW — small modal for naming + registering a new passkey, mirroring MFASetupWizard.tsx's shape

services/
└── apiService.ts                # MODIFIED — add passkey fetch helpers (registerPasskeyOptions, registerPasskeyVerify, loginPasskeyOptions, loginPasskeyVerify, listPasskeys, deletePasskey), following the existing fetchMfaStatus/setupMfa/verifyMfaSetup naming convention

package.json                     # MODIFIED — add @simplewebauthn/browser dependency
```

### Pattern 1: New service+endpoints sibling pair, cloned from `mfa_service.py`/`mfa_endpoints.py`
**What:** Build `passkey_service.py` (business logic, DB access, ceremony wrapping) and `passkey_endpoints.py` (thin FastAPI routes) as a new pair, following the exact file-role split every other auth-adjacent feature in this codebase already uses (`mfa_service.py`/`mfa_endpoints.py`, `sso_service.py`/`sso_endpoints.py`).
**When to use:** The entire AUTH-01 backend surface.
**Example:**
```python
# Source: pattern cloned from backend/mfa_endpoints.py (existing, read in full this session)
# backend/passkey_endpoints.py
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from authentication_service import get_current_user, create_access_token, create_refresh_token, ACCESS_TOKEN_EXPIRE_MINUTES
from rate_limiter import limiter
import passkey_service

router = APIRouter(prefix="/api/passkey", tags=["Passkeys"])

@router.post("/register/options")
async def passkey_register_options(current_user=Depends(get_current_user)):
    """Authenticated — generates registration options for the CURRENT user to add a new passkey."""
    return await passkey_service.build_registration_options(current_user.username)

@router.post("/register/verify")
async def passkey_register_verify(payload: dict, current_user=Depends(get_current_user)):
    result = await passkey_service.verify_and_store_registration(current_user.username, payload)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
```
Register in `router_registry.py` exactly like the two existing siblings:
```python
# Source: backend/router_registry.py line 91-92 (existing, read this session) — add directly below
_load(app, "mfa_endpoints",            "router")
_load(app, "sso_endpoints",            "router")
_load(app, "passkey_endpoints",        "router")   # NEW
```

### Pattern 2: Credential storage as a nested array on `users`, not a new collection
**What:** Store passkey credentials the same way `mfa.secret_encrypted`/`mfa.backup_codes_hashed` are stored today — nested inside the existing tenant-isolated `users` document, not a new top-level collection.
**When to use:** All persistence for registered passkeys.
**Example:**
```python
# Source: pattern cloned from backend/mfa_service.py's enroll_mfa() $set shape (existing, read this session)
async def store_credential(email: str, credential_id: str, public_key: bytes, sign_count: int, device_name: str, transports: list[str]) -> None:
    db = get_database()
    await db.users.update_one(
        {"email": email},
        {"$push": {"webauthn_credentials": {
            "credential_id": credential_id,       # base64url string — unique per credential
            "public_key": base64.b64encode(public_key).decode(),
            "sign_count": sign_count,
            "device_name": device_name,             # user-supplied label, e.g. "MacBook Touch ID"
            "transports": transports,                # e.g. ["internal"], ["usb", "nfc"]
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_used_at": None,
        }}}
    )
```
`credential_id` must be globally unique (WebAuthn credential IDs are effectively random) — add a sparse/partial unique index on `users.webauthn_credentials.credential_id` if the plan wants defense-in-depth against ID collision, though the library's own randomness makes a collision astronomically unlikely; this is optional hardening, not a hard requirement.

### Pattern 3: Third instance of the in-memory-TTL-dict challenge store
**What:** Store the transient WebAuthn challenge exactly like `mfa_service._mfa_sessions` and `sso_service._oidc_states` already do — a plain module-level dict, pruned of expired entries on read/write, popped (single-use) on successful verification.
**When to use:** Both registration and login ceremonies need a challenge stored between the `/options` call and the `/verify` call.
**Example:**
```python
# Source: pattern cloned from backend/sso_service.py lines 17-29 and mfa_service.py lines 198-218 (existing, read this session)
_webauthn_challenges: dict = {}   # { session_id: { "challenge": bytes, "user_email": str|None, "expires": datetime } }
_WEBAUTHN_CHALLENGE_TTL_SECONDS = 90  # short — this is a synchronous, human-timed browser prompt

def _prune_expired_challenges() -> None:
    now = datetime.now(timezone.utc)
    expired = [k for k, v in _webauthn_challenges.items() if v["expires"] < now]
    for k in expired:
        del _webauthn_challenges[k]

def store_challenge(challenge: bytes, user_email: str | None) -> str:
    _prune_expired_challenges()
    session_id = str(uuid.uuid4())
    _webauthn_challenges[session_id] = {
        "challenge": challenge,
        "user_email": user_email,
        "expires": datetime.now(timezone.utc) + timedelta(seconds=_WEBAUTHN_CHALLENGE_TTL_SECONDS),
    }
    return session_id

def consume_challenge(session_id: str) -> dict | None:
    """Single-use: pop, not peek. A replayed session_id after this call returns None."""
    entry = _webauthn_challenges.pop(session_id, None)
    if not entry or datetime.now(timezone.utc) > entry["expires"]:
        return None
    return entry
```

### Pattern 4: Passkey login as an independent new endpoint — do not edit `authentication_endpoints.py`
**What:** `authentication_endpoints.py` is 479 lines (CLAUDE.md's limit is 500). Passkey login must be its own endpoint in the new `passkey_endpoints.py`, minting JWTs via the same `create_access_token`/`create_refresh_token` helpers every other login path already imports from `authentication_service.py` — not a new branch inside `login_for_access_token`.
**When to use:** AUTH-01's login flow.
**Example:**
```python
# Source: JWT-minting shape cloned verbatim from backend/authentication_endpoints.py lines 176-182
# and backend/mfa_endpoints.py lines 103-108 (existing, both read this session) — same token_payload shape
@router.post("/login/verify")
@limiter.limit("10/minute")   # same rate as the password login route (Pitfall: don't forget `response: Response`)
async def passkey_login_verify(request: Request, response: Response, payload: dict):
    result = await passkey_service.verify_authentication(payload)  # checks challenge, sign_count, etc.
    if not result["success"]:
        raise HTTPException(status_code=401, detail=result["error"])
    user = result["user"]
    token_payload = {"sub": user["email"], "role": user.get("role", "user"), "tenant_id": user.get("tenantId")}
    access_token = create_access_token(data=token_payload, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    refresh_token = create_refresh_token(data={"sub": user["email"]})
    user_data = {k: v for k, v in user.items() if k not in ("password", "_id", "mfa", "webauthn_credentials")}
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer", "success": True, "user": user_data}
```
Note `"webauthn_credentials"` is added to the sensitive-fields exclusion set alongside the existing `"mfa"` — the response-sanitization list (`_SENSITIVE_USER_FIELDS` in `authentication_endpoints.py`, and the inline tuple in `mfa_endpoints.py`) must be checked for every new endpoint that returns a user object, since `passkey_endpoints.py` builds its own filtered dict rather than importing the shared constant (it's module-private in `authentication_endpoints.py`) — the plan should either export `_SENSITIVE_USER_FIELDS` for reuse or duplicate the frozenset locally, but must not skip the filtering step.

### Anti-Patterns to Avoid
- **Adding a passkey branch inside `authentication_endpoints.login_for_access_token`:** Would push `authentication_endpoints.py` (currently 479 lines) over CLAUDE.md's 500-line limit, and couples an orthogonal credential-verification method into a function that already branches on MFA. Build a separate endpoint (Pattern 4).
- **Creating a new `webauthn_credentials` top-level Mongo collection:** No precedent for 1:1 owned auth-credential data living outside the `users` document in this codebase (`mfa.*` is the direct analog); adds an unnecessary new tenant-isolation surface to reason about for no benefit AUTH-01 requires.
- **Trusting a client-supplied `sign_count` or skipping the sign-count check entirely:** `verify_authentication_response()`'s `new_sign_count` return value must be compared against the stored value and persisted back — silently accepting whatever the assertion claims defeats the one cloned-authenticator detection signal WebAuthn provides (see Security Domain).
- **Per-tenant or per-request RP ID computation:** This platform's authenticated app has one origin; RP ID should be resolved once from `PLATFORM_URL` at module load (mirroring how `agent_download_endpoints.py` already reads `PLATFORM_URL` once), not recomputed from `request.headers.get("host")` per request the way Phase 29's *public, unauthenticated* Trust Center route needed to for custom domains — that pattern does not apply here because passkey registration/login always happens inside the authenticated (or login) app on the platform's own origin.
- **Reusing `_mfa_sessions` or `_oidc_states` dicts directly for WebAuthn challenges:** Each existing short-lived-state dict is scoped to its own module and TTL semantics; the WebAuthn challenge needs its own dict (Pattern 3) with its own (shorter) TTL, not a shared/overloaded structure.
- **Forgetting `response: Response` on any new `@limiter.limit(...)`-decorated passkey route:** This is a documented, previously-shipped bug in this exact codebase (Phase 25/CHK-03, `container_scanner_endpoints.py`) — every new rate-limited route in `passkey_endpoints.py` must include it (see Common Pitfalls).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| WebAuthn attestation/assertion cryptographic verification (CBOR/COSE parsing, signature checks) | A custom parser/verifier for `attestationObject`/`authenticatorData` | `webauthn` (py_webauthn)'s `verify_registration_response()`/`verify_authentication_response()` | This is genuinely cryptographic code with a well-known history of subtle implementation bugs across the industry (why FIDO Alliance certification exists at all); exactly the class of code this codebase already refuses to hand-roll elsewhere (bcrypt for passwords, PyJWT for tokens, `defusedxml` for SAML XXE-safety) |
| Browser-side `navigator.credentials` base64url/ArrayBuffer marshalling | Manual `btoa`/`atob`/`Uint8Array` conversion helpers | `@simplewebauthn/browser`'s `startRegistration()`/`startAuthentication()` | Finicky, easy to get subtly wrong (silent credential-ID corruption), and the library is small/standard enough that the dependency cost is low relative to the bug-surface it removes |
| Short-lived, single-use server-side challenge storage | A new bespoke state-management abstraction, or trusting the client to echo the challenge back unmodified | The existing in-memory-dict-with-TTL pattern (Pattern 3), a third instance of what `_mfa_sessions`/`_oidc_states` already do | Already a proven, reviewed pattern in this exact codebase for exactly this shape of problem (short-lived server-side ceremony state) |
| Cloned-authenticator / replay detection | A custom device-fingerprinting or behavioral-analysis system | The sign-count monotonicity check already built into the WebAuthn spec and exposed by `verify_authentication_response()`'s `new_sign_count` return value | This is the standard, spec-defined mechanism; building anything more elaborate is out of scope for AUTH-01 and would duplicate what `ueba_service.py`'s existing post-login behavioral analysis (already fired for every login in `authentication_endpoints.py`) is designed to catch at a different layer |

**Key insight:** Every non-cryptographic piece of this phase (service/endpoint file structure, credential storage shape, challenge TTL storage, RP ID resolution, JWT minting) has a direct, already-shipped precedent in this codebase to clone. The one genuinely new piece — WebAuthn ceremony cryptography — is exactly the piece that should not be hand-rolled, and the standard library exists specifically because this is hard to get right.

## Runtime State Inventory

> This phase is purely additive (new fields, new collection-array, new endpoints) — not a rename/refactor/migration. Included per the standard protocol trigger check; all categories below confirm no migration is needed.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — `webauthn_credentials` is a brand-new field on the `users` document; no existing data references it. Existing users simply have an absent/empty array until they register a passkey. | None — additive schema change only, no migration of existing records. |
| Live service config | None found — no external service (n8n, Datadog, etc.) references authentication method configuration. | None. |
| OS-registered state | None found. | None. |
| Secrets/env vars | `PLATFORM_URL` is reused (read-only) for RP ID derivation — already an existing env var with existing behavior (agent download URLs, remote access URLs); this phase adds a new *consumer* of it, does not rename or repurpose it. No new secret/env var is strictly required, though see Open Questions for whether a distinct `WEBAUTHN_RP_NAME` display-name env var is wanted. | None required; PLATFORM_URL's existing semantics are unchanged. |
| Build artifacts | None found — no existing compiled/installed artifact references passkey/webauthn concepts. | None. |

**Nothing found requiring data migration** — this phase adds new optional fields and new endpoints; no existing user, credential, or session data changes shape or meaning.

## Common Pitfalls

### Pitfall 1: `authentication_endpoints.py` crosses the 500-line CLAUDE.md limit if passkey login is added inline
**What goes wrong:** A plan that adds passkey login as a new branch inside `login_for_access_token` (mirroring how the existing MFA branch was added) pushes the file from 479 to 500+ lines, violating CLAUDE.md's explicit file-size rule.
**Why it happens:** The MFA branch is the closest visible precedent for "alternative login flow," making it tempting to extend the same function rather than create a new one.
**How to avoid:** Add passkey login as an independent endpoint in the new `passkey_endpoints.py` (Pattern 4) — it needs no code from `login_for_access_token` beyond the already-importable `create_access_token`/`create_refresh_token` helpers.
**Warning signs:** `wc -l backend/authentication_endpoints.py` exceeds 500 after the change.

### Pitfall 2: `@limiter.limit(...)` without the `response: Response` parameter (documented, previously-shipped bug in this exact codebase)
**What goes wrong:** `slowapi`'s `@limiter.limit(...)` decorator requires a FastAPI-injected `response: Response` parameter on the decorated endpoint or the route 500s on every real request — unit tests that call the underlying function directly (bypassing the ASGI middleware stack) never catch this.
**Why it happens:** Easy to add `@limiter.limit(...)` to a route signature that only has `request: Request` and forget the sibling `response: Response` parameter.
**How to avoid:** Every new `@limiter.limit(...)`-decorated route in `passkey_endpoints.py` (both `/login/options` and `/login/verify` should be rate-limited — registration routes are behind auth already but a login-attempt-enumeration limit matters most) must include `response: Response`, exactly like `mfa_endpoints.verify_mfa_at_login` already does. Verify with an actual `TestClient` HTTP call, not just an import check — this exact bug (`container_scanner_endpoints.py`, Phase 25/CHK-03) was invisible to unit tests.
**Warning signs:** `grep -c "response: Response"` on `passkey_endpoints.py` returns fewer matches than `grep -c "@limiter.limit"`.

### Pitfall 3: Sign-count check silently skipped or silently made non-blocking
**What goes wrong:** `verify_authentication_response()` returns a `new_sign_count`; if the plan doesn't compare it against the credential's last stored `sign_count` and persist the new value, the one cloned-authenticator detection mechanism WebAuthn provides is a no-op.
**Why it happens:** The check is easy to skip because most authentications "just work" without it — the failure mode only shows up when a credential actually gets cloned or a multi-device sync desyncs, which won't appear in normal development/testing.
**How to avoid:** Always compare `new_sign_count` to the stored value; if `new_sign_count <= stored_sign_count` AND the stored value was previously non-zero (see caveat below), treat it as a signal (log + optionally require step-up re-auth), then always persist the new (or unchanged) count. **Caveat, confirmed via research:** many platform authenticators (Touch ID, Windows Hello, and especially multi-device/synced passkeys) always report a sign count of `0` — for these, the check is structurally a no-op and that is expected, not a bug. Do not reject `0 -> 0` transitions as suspicious.
**Warning signs:** `passkey_service.py` calls `verify_authentication_response()` but never reads or persists `new_sign_count`.

### Pitfall 4: Forgetting to sanitize `webauthn_credentials` out of user-object API responses
**What goes wrong:** `webauthn_credentials` will contain public keys (not secret, but still internal implementation detail) and device/usage metadata; if a new endpoint builds its user-response dict without excluding this field the way `mfa` is already excluded everywhere (`_SENSITIVE_USER_FIELDS` in `authentication_endpoints.py`, the inline tuple in `mfa_endpoints.py`), it leaks unnecessary internal detail to the frontend (not a critical vulnerability — public keys aren't secret — but inconsistent with this codebase's existing discipline and can leak device names/usage timestamps a user might not expect in a raw API response).
**Why it happens:** `_SENSITIVE_USER_FIELDS` is module-private to `authentication_endpoints.py`; new files copy the *pattern* but must remember to also copy (or extend) the *field list*.
**How to avoid:** Add `"webauthn_credentials"` to every user-field-filtering site touched or added by this phase — `_SENSITIVE_USER_FIELDS` in `authentication_endpoints.py` (if any of its endpoints could ever return it, they currently can't, but check), and any new filtering the passkey endpoints build for their own responses.
**Warning signs:** A `GET /api/passkey/list`-style endpoint (or any other) returns raw `public_key`/full credential objects instead of a filtered `{credential_id (partial), device_name, created_at, last_used_at}` shape.

### Pitfall 5: RP ID mismatch between registration and login due to inconsistent `PLATFORM_URL` parsing
**What goes wrong:** If RP ID is derived from `PLATFORM_URL` slightly differently in the registration path vs. the login path (e.g., one strips the port and one doesn't, or one includes `www.` and one doesn't), `verify_authentication_response()`'s `expected_rp_id` check fails for every login attempt even though registration succeeded — a subtle bug that only appears at login time, potentially after a passkey was already successfully registered and demoed.
**Why it happens:** `PLATFORM_URL` is a full URL (e.g., `https://app.example.com:8443`) but RP ID must be a bare hostname (`app.example.com`, no scheme, no port) — the string-processing step must be written once and shared, not duplicated.
**How to avoid:** Compute RP ID once, in `passkey_service.py`, at module load (or via a single shared helper function), and import it everywhere both registration and login options/verification need it — never re-derive it inline in more than one place.
**Warning signs:** Passkey registration succeeds but every subsequent login attempt fails `verify_authentication_response()` with an RP-ID-mismatch-shaped error.

## Code Examples

Verified/cited patterns:

### Registration options + verification (py_webauthn)
```python
# Source: github.com/duo-labs/py_webauthn examples/registration.py (official repo, fetched this session)
from webauthn import generate_registration_options, verify_registration_response, options_to_json
from webauthn.helpers.structs import AuthenticatorSelectionCriteria, AuthenticatorAttachment, ResidentKeyRequirement

options = generate_registration_options(
    rp_id="app.example.com",         # derived once from PLATFORM_URL — see Pitfall 5
    rp_name="Enterprise Omni-Agent",
    user_id=user_id_bytes,
    user_name=email,
    user_display_name=name,
    authenticator_selection=AuthenticatorSelectionCriteria(
        authenticator_attachment=AuthenticatorAttachment.PLATFORM,   # or omit to allow roaming keys too
        resident_key=ResidentKeyRequirement.PREFERRED,
    ),
    exclude_credentials=[...],       # existing credential_ids for this user, so they can't re-register the same key
)
options_json = options_to_json(options)   # send to frontend as-is

# ... after browser round-trip ...
verification = verify_registration_response(
    credential=credential_from_browser,          # JSON string or dict from startRegistration()
    expected_challenge=stored_challenge_bytes,     # from Pattern 3's challenge store
    expected_origin="https://app.example.com",
    expected_rp_id="app.example.com",
    require_user_verification=True,
)
# verification.credential_id, verification.credential_public_key, verification.sign_count now available to store
```

### Authentication options + verification (py_webauthn)
```python
# Source: github.com/duo-labs/py_webauthn examples/authentication.py (official repo, fetched this session)
from webauthn import generate_authentication_options, verify_authentication_response
from webauthn.helpers.structs import UserVerificationRequirement

options = generate_authentication_options(
    rp_id="app.example.com",
    allow_credentials=[...],   # this user's stored credential_ids, or omit entirely for usernameless/discoverable login
    user_verification=UserVerificationRequirement.REQUIRED,
)

# ... after browser round-trip ...
verification = verify_authentication_response(
    credential=credential_from_browser,
    expected_challenge=stored_challenge_bytes,
    expected_rp_id="app.example.com",
    expected_origin="https://app.example.com",
    credential_public_key=stored_public_key_bytes,
    credential_current_sign_count=stored_sign_count,
    require_user_verification=True,
)
# verification.new_sign_count — compare + persist per Pitfall 3
```

### Frontend registration/authentication calls (@simplewebauthn/browser)
```typescript
// Source: simplewebauthn.dev/docs/packages/browser (official docs, cited this session)
import { startRegistration, startAuthentication } from '@simplewebauthn/browser';

// Registration
const optionsJSON = await api.passkeyRegisterOptions();   // authFetch to /api/passkey/register/options
const credential = await startRegistration({ optionsJSON });
await api.passkeyRegisterVerify(credential, sessionId);

// Login
const optionsJSON = await api.passkeyLoginOptions(email); // unauthenticated fetch to /api/passkey/login/options
const credential = await startAuthentication({ optionsJSON });
const { access_token, refresh_token, user } = await api.passkeyLoginVerify(credential, sessionId);
```

### Test-only software authenticator (soft-webauthn)
```python
# Source: github.com/bodik/soft-webauthn README + soft_webauthn.py (fetched this session)
from soft_webauthn import SoftWebauthnDevice

device = SoftWebauthnDevice()
# Registration ceremony, no browser needed:
attestation = device.create(options_json_from_server, origin="https://app.example.com")
# → feed `attestation` into verify_registration_response() exactly as if it came from startRegistration()

# Authentication ceremony:
assertion = device.get(options_json_from_server, origin="https://app.example.com")
# → feed `assertion` into verify_authentication_response()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Auth methods: password (bcrypt) + TOTP MFA + SAML/OIDC SSO — no passkey/WebAuthn option | Adds WebAuthn/FIDO2 passkeys as a fourth, independent login method, following the same service+endpoints file-pair convention as MFA/SSO | This phase (34) | Closes the one auth-method gap this codebase had relative to OpenLane (per the v3.0 feature-parity audit that generated this milestone's roadmap); establishes credential storage on `users.webauthn_credentials` and a third in-memory-TTL-dict challenge-store instance as new precedents future auth work can clone |

**Deprecated/outdated:** Nothing in the existing auth stack is deprecated or replaced — AUTH-01 is explicitly additive ("as an alternative to password/SSO/TOTP," "no regression to existing... flows"). Password, TOTP MFA, and SAML/OIDC SSO all remain fully supported and untouched.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `webauthn` (PyPI, duo-labs/py_webauthn) is a legitimate, safe-to-install package despite the Package Legitimacy Gate's `[SUS]` verdict — the flag is a false positive driven by "latest release recency" rather than package/maintainer trustworthiness | Package Legitimacy Audit, Summary | Low likelihood of being wrong (well-known Cisco Duo org, long GitHub history, cited across many independent WebAuthn guides), but the protocol's `checkpoint:human-verify` gate exists precisely to catch cases where this kind of assessment is mistaken — the plan must not skip that checkpoint based on this research's opinion |
| A2 | RP ID can be a single static value derived from `PLATFORM_URL`, because the authenticated app (where passkey registration/login happens) has one origin, unlike Phase 29's public Trust Center page which added per-tenant custom domains | Summary, Anti-Patterns, Pitfall 5 | If a future or already-planned change puts tenants on distinct authenticated-app subdomains (not just the public Trust Center), a single static RP ID would break cross-subdomain passkey use — no evidence of this in the codebase today (confirmed via `tenant_endpoints.py` read this session, no subdomain-per-tenant concept for the authenticated app), but worth confirming explicitly with a human if there's a roadmap item this research didn't surface |
| A3 | Storing credentials as a `webauthn_credentials` array nested on the `users` document (not a new collection) is sufficient for AUTH-01's scope | Standard Stack → Alternatives Considered, Architecture Patterns → Pattern 2 | If a future requirement needs cross-user credential queries (e.g., "find all passkeys registered from IP X" for a security investigation), a nested array is harder to query/index than a dedicated collection — low risk for AUTH-01's literal scope (register + log in), flagged in case a follow-on security/audit phase needs it |
| A4 | A 60-120 second challenge TTL (this research recommends ~90s) is appropriate, modeled as shorter than the existing 5-minute MFA session TTL because a WebAuthn ceremony is a single synchronous browser-native prompt rather than a "go check your authenticator app" flow | Summary, Pattern 3 | If real-world users on slow platform-authenticator flows (e.g., some external-key browser prompts) routinely need more than ~90 seconds, a too-short TTL causes spurious ceremony failures — this is a tunable constant, low risk to get slightly wrong initially |

**If this table is empty:** N/A — see entries above.

## Open Questions (RESOLVED)

1. **Should passkey login support "discoverable"/usernameless flow (no email typed first, the authenticator itself surfaces which account) or only the "identify first, then authenticate" flow this research's diagrams show?** (RESOLVED)
   - What we know: `generate_authentication_options()` supports `allow_credentials=[]` (omitted) for a fully discoverable/usernameless flow, where the browser's autofill or a resident-key-capable authenticator lets the user pick an account without typing an email first; `LoginPage.tsx` currently always collects an email for password login, so an email-first passkey flow is the more consistent minimal addition.
   - What's unclear: Whether product wants the more modern "just tap your passkey, no email typed" UX (requires `resident_key=ResidentKeyRequirement.REQUIRED` at registration time, `@simplewebauthn/browser`'s `browserSupportsWebAuthnAutofill()` + `autocomplete="webauthn"` on the login input) from day one, or whether email-first is acceptable for v1.
   - Recommendation: Ship email-first for v1 (simpler, smaller diff, matches `LoginPage.tsx`'s existing input-first pattern) — this doesn't foreclose adding discoverable/usernameless login later, since it's purely an additive frontend UX change plus one registration-option flag, not a backend rearchitecture.
   - **RESOLVED: adopting the recommendation (email-first for v1).** Smallest diff consistent with the existing login UX; usernameless remains a purely additive follow-up.

2. **Does AUTH-01 require passkey enrollment to be gated behind an already-authenticated session only (registering a *second* factor for an existing account), or should new-user signup also support "sign up with a passkey" (no password at all)?** (RESOLVED)
   - What we know: The requirement text says "register and log in with a WebAuthn/FIDO2 passkey as an alternative to password/SSO/TOTP" — this reads as an alternative *login* method for existing accounts, and the diagrams/patterns above assume registration happens from within `UserProfilePage.tsx` (already logged in via password).
   - What's unclear: Whether "register" in AUTH-01's wording includes a passwordless-signup flow (new tenant/user creation with no password at all), which would touch `authentication_endpoints.signup` — currently untouched by this research's recommendations.
   - Recommendation: Scope this phase to "add a passkey to an existing, already-authenticated account, then use it to log in thereafter" (the OpenLane-parity gap this phase is closing) — passwordless *signup* is a larger, separate scope decision (every account still needs *some* recovery mechanism if the passkey is lost, which has real product/support implications) and should be a deferred idea unless a human confirms it's actually wanted for this phase.
   - **RESOLVED: adopting the recommendation.** AUTH-01's literal wording ("an alternative to password/SSO/TOTP") is satisfied by enrollment-while-authenticated + passkey login. Passwordless signup is explicitly a deferred idea, not built this phase.

3. **What happens when a user's only passkey is lost/unavailable — is there a recovery/account-lockout consideration for AUTH-01, or is this out of scope because password/TOTP/SSO remain available as fallbacks?** (RESOLVED)
   - What we know: AUTH-01 explicitly frames passkeys as "an alternative to password/SSO/TOTP" (not a replacement) — if passkey enrollment always requires an existing authenticated session (per Open Question 2's recommendation), the user's password (or SSO) always remains a valid fallback login method by construction, so there is no new account-lockout risk this phase introduces.
   - What's unclear: Nothing, given the Open Question 2 recommendation — flagging this only to make the reasoning explicit for the planner, since "what if the passkey is lost" is a natural first question and the answer ("the account still has its original login method") should be stated rather than left implicit.
   - Recommendation: No new recovery mechanism needed for v1, precisely because this phase (per Open Question 2's recommended scope) never makes a passkey the *only* credential on an account.
   - **RESOLVED: adopting the recommendation.** Follows directly from Q2's resolution — the original login method always remains valid, so no new lockout risk is introduced. The plan should state this explicitly in the passkey-management UI copy (a lost passkey can be removed and re-enrolled after logging in with the original method).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| MongoDB (via Motor) | Credential storage on `users.webauthn_credentials` | ✓ (assumed running — used by every other phase in this milestone) [ASSUMED — not independently re-probed this session; no prior phase in this milestone flagged it unavailable] | — | — |
| `webauthn` (PyPI) | Server-side ceremony logic | ✗ — confirmed not installed this session (`pip show webauthn` returned nothing) | Install `>=3.0.0,<4.0.0` — behind `checkpoint:human-verify` per Package Legitimacy Audit | None — this is the one library that must not be hand-rolled; no viable fallback |
| `@simplewebauthn/browser` (npm) | Client-side ceremony plumbing | ✗ — confirmed not in `package.json` this session | Install `^13.3.0` | Hand-rolled `navigator.credentials` calls are technically possible (evaluated in Alternatives Considered) but not recommended |
| `soft-webauthn` (PyPI, test-only) | Wave 0 test infrastructure — simulating a full ceremony without a browser | ✗ — confirmed not installed this session | Install `>=0.1.4,<0.2.0` — behind `checkpoint:human-verify` per Package Legitimacy Audit | Fallback: hand-build minimal test fixtures directly against `webauthn` library's own internal structs/test vectors if this dependency is rejected at the human-verify checkpoint — more work, still viable |
| `PLATFORM_URL` env var | RP ID / origin resolution | ✓ — already set/used by 3 other backend modules (confirmed via grep this session) | — | If unset in a given environment, `agent_download_endpoints.py`'s existing pattern already raises a clear error for its own use case; the passkey module should fail equally clearly (no silent RP-ID-is-empty-string bug) rather than introduce a new fallback-URL-guessing heuristic |
| Browser WebAuthn API support | End-user passkey registration/login | ✓ — WebAuthn/FIDO2 is supported by all evergreen browsers (Chrome, Safari, Firefox, Edge) as of any 2024+ release; no polyfill exists or is needed | — | `@simplewebauthn/browser`'s `browserSupportsWebAuthn()` should gate whether the "Sign in with a passkey" UI even renders, so unsupported browsers (effectively none in current use, but defensive) simply don't show the option rather than erroring |

**Missing dependencies with no fallback:** `webauthn` (PyPI) — server-side cryptographic ceremony verification has no safe hand-rolled fallback; must be installed (behind its human-verify checkpoint).
**Missing dependencies with fallback:** `@simplewebauthn/browser` (hand-rolled alternative evaluated, not recommended); `soft-webauthn` (test fixtures can be hand-built against `webauthn`'s own structs if rejected).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (project-standard; `pytest.ini` at repo root) [VERIFIED: `pytest.ini` read this session — `testpaths = . backend`, `asyncio_mode = auto`] |
| Config file | `pytest.ini` (repo root) |
| Quick run command | `cd backend && python -m pytest tests/test_passkey_auth.py -x` |
| Full suite command | `cd backend && python -m pytest tests/ -q` |
| Frontend framework | Vitest (`"test": "vitest run"` in `package.json`) [VERIFIED: `package.json` read this session] |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTH-01 | Full registration ceremony succeeds end-to-end using `soft-webauthn`'s `SoftWebauthnDevice` (no real browser) — options generated, verified, credential persisted to `users.webauthn_credentials` | integration | `pytest tests/test_passkey_auth.py -k registration -x` | ❌ Wave 0 |
| AUTH-01 | Full login ceremony succeeds end-to-end and mints a JWT with the identical shape (`sub`, `role`, `tenant_id`, `jti`, `exp`) to the existing password-login JWT | integration | `pytest tests/test_passkey_auth.py -k login_verify -x` | ❌ Wave 0 |
| AUTH-01 | Challenge is single-use — replaying a `session_id` after successful verification fails | unit | `pytest tests/test_passkey_auth.py -k challenge_replay -x` | ❌ Wave 0 |
| AUTH-01 | Expired challenge (past TTL) is rejected | unit | `pytest tests/test_passkey_auth.py -k challenge_expiry -x` | ❌ Wave 0 |
| AUTH-01 | Sign-count regression is detected and does not silently pass (per Pitfall 3, allow the `0→0` no-op case) | unit | `pytest tests/test_passkey_auth.py -k sign_count -x` | ❌ Wave 0 |
| AUTH-01 (regression) | Existing password login (`test_authentication.py`) still passes unmodified | regression | `pytest tests/test_authentication.py -x` | ✓ exists |
| AUTH-01 (regression) | Existing TOTP MFA login (`test_auth_mfa.py`) still passes unmodified | regression | `pytest tests/test_auth_mfa.py -x` | ✓ exists |
| AUTH-01 (regression) | Existing SSO/SAML/OIDC tests still pass unmodified — locate via `find backend/tests -iname "*sso*"` at plan time (none found by name this session; if SSO has no dedicated test file, add a minimal smoke test rather than leaving it uncovered) | regression | `pytest backend/tests/ -k sso -x` (verify file exists during planning) | ⚠ verify at plan time |
| AUTH-01 | `authentication_endpoints.py` line count stays ≤500 after this phase (Pitfall 1) | lint/manual | `wc -l backend/authentication_endpoints.py` | ❌ Wave 0 (add as an explicit plan verification step, not a pytest test) |

### Sampling Rate
- **Per task commit:** `cd backend && python -m pytest tests/test_passkey_auth.py -x`
- **Per wave merge:** `cd backend && python -m pytest tests/ -q` (must include `test_authentication.py` and `test_auth_mfa.py` passing unmodified — this is the literal verification of AUTH-01's "no regression" clause)
- **Phase gate:** Full suite green before `/gsd-verify-work`; additionally, an actual `TestClient` HTTP call through both new rate-limited routes (not just an import check), per Pitfall 2.

### Wave 0 Gaps
- [ ] `backend/tests/test_passkey_auth.py` — new file; clone the `_make_db_mock`/`TestClient` helper block from `backend/tests/test_auth_mfa.py` per this repo's per-file test-helper convention, extended with `SoftWebauthnDevice` for full-ceremony simulation
- [ ] Framework install: `pip install "webauthn>=3.0.0,<4.0.0" "soft-webauthn>=0.1.4,<0.2.0"` — both behind `checkpoint:human-verify` (Package Legitimacy Audit)
- [ ] `npm install @simplewebauthn/browser@^13.3.0` — for frontend Vitest coverage of `PasskeySetupModal.tsx`/`LoginPage.tsx` passkey button, if the plan includes frontend unit tests for those components (existing frontend test coverage conventions should be confirmed during planning — no existing `LoginPage.test.tsx` was found this session)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | yes — the core of this phase | WebAuthn/FIDO2 ceremony verification via `webauthn` (py_webauthn); challenge is server-generated, single-use, short-TTL (Pattern 3); `require_user_verification=True` on both registration and authentication options enforces authenticator-level user verification (biometric/PIN), not just presence |
| V3 Session Management | yes (indirect) | Successful passkey login mints the same JWT (via the same `create_access_token`/`create_refresh_token` helpers) as every other login method — no new session/token mechanism introduced, so this phase inherits the existing JWT expiry/revocation model (`authentication_service.py`'s JTI revocation cache) unchanged |
| V4 Access Control | yes | Passkey *registration* endpoints (`/api/passkey/register/*`) require `get_current_user` — only an already-authenticated user can add a passkey to their own account; a user can only register/list/delete their own credentials, never another user's (enforce this explicitly by scoping every DB operation to `current_user.username`, not a client-supplied user identifier) |
| V5 Input Validation | yes | Credential/assertion payloads from the browser are opaque structures verified entirely by the `webauthn` library's own parsing (do not hand-parse); `device_name` (user-supplied label) should be length-capped and sanitized before storage, matching this codebase's existing `Field(..., max_length=...)` convention seen in `authentication_endpoints.LoginRequest` |
| V6 Cryptography | yes (delegated) | All cryptographic operations (COSE public key parsing, signature verification) are owned by the `webauthn` library — this phase introduces zero hand-rolled cryptography, consistent with this codebase's existing practice (bcrypt, PyJWT, `cryptography` package) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Challenge replay — an attacker captures a valid registration/authentication response and resubmits it later | Spoofing / Tampering | Challenge is single-use (`consume_challenge` pops, not peeks — Pattern 3) and short-TTL (~90s); `verify_registration_response()`/`verify_authentication_response()` independently validate the challenge matches what was issued |
| Credential substitution — an attacker registers their own passkey against a victim's account by manipulating the registration flow | Spoofing / Elevation of Privilege | Registration endpoints require `get_current_user` and always scope credential storage to `current_user.username` server-side, never a client-supplied user identifier (V4 above); `exclude_credentials` on registration options additionally prevents re-registering an existing credential |
| Cloned/duplicated authenticator — a credential's private key material is extracted and used from two devices simultaneously | Spoofing | Sign-count monotonicity check (Pitfall 3) — flag when `new_sign_count <= stored_sign_count` for a credential whose stored count was previously non-zero; log for investigation (`ueba_service.py`'s existing post-login behavioral analysis, already invoked for every login, provides a second, independent detection layer at the account-behavior level) |
| RP ID / origin spoofing — a malicious page on a different origin tricks a user's browser into completing a WebAuthn ceremony that gets accepted by the server | Spoofing | `expected_origin`/`expected_rp_id` are checked server-side by `verify_registration_response()`/`verify_authentication_response()` against the value the browser itself reports in `clientDataJSON` (which the browser, not the page, controls) — this is WebAuthn's core anti-phishing property and is enforced by the library, not application code; RP ID must be derived consistently (Pitfall 5) or this check produces false rejections, not false acceptances (fails closed, not open) |
| Passkey-registration endpoint used to enumerate valid session/account state | Information Disclosure | `/api/passkey/register/*` already requires `get_current_user` (401 for unauthenticated callers, no account-existence signal leaked); `/api/passkey/login/options` (unauthenticated, needs an email to look up allowed credentials) should return a generically-shaped response for unknown emails (empty `allow_credentials`, not a distinct "no such user" error) to avoid the same user-enumeration risk `authentication_endpoints.login_for_access_token` already guards against with its single generic "Invalid credentials" message |
| Brute-force / abuse of the public login-options/login-verify endpoints | Denial of Service / Spoofing | Rate-limit both `/api/passkey/login/options` and `/api/passkey/login/verify` via the existing shared `slowapi` `limiter` (Pitfall 2), at a rate comparable to the existing `/api/auth/login`'s `10/minute` |

## Sources

### Primary (HIGH confidence)
- `backend/authentication_service.py` (full file read, this session) — JWT minting (`create_access_token`/`create_refresh_token`), `get_current_user`, JTI revocation — confirmed the exact reuse target for passkey login
- `backend/auth_utils.py` (full file read, this session) — bcrypt password verification, the analog for "a credential-verification module"
- `backend/mfa_service.py` (full file read, this session) — TOTP secret/backup-code storage on `users.mfa.*`, `_mfa_sessions` in-memory TTL dict pattern, two-phase login flow
- `backend/mfa_endpoints.py` (full file read, this session) — service+endpoints file-pair convention, `@limiter.limit(...)` + `response: Response` requirement in practice
- `backend/sso_service.py` (full file read, this session) — `_oidc_states` in-memory TTL dict pattern (second instance, confirming Pattern 3 is an established convention, not a one-off)
- `backend/authentication_endpoints.py` (full file read, this session) — confirmed 479 lines (Pitfall 1's load-bearing finding), existing `/api/auth/login` structure, `_SENSITIVE_USER_FIELDS` filtering pattern, existing MFA-branch precedent
- `components/LoginPage.tsx` (full file read, this session) — confirmed no client router, conditional SSO button pattern to clone for a passkey login button
- `components/UserProfilePage.tsx` (partial read, this session) — confirmed existing "Security" card / TOTP enable-disable UI shape to clone for passkey management
- `services/apiService.ts` (partial read, this session) — confirmed `authFetch`/plain-`fetch` split (login/options need no token; verify/list/delete need `authFetch`), existing MFA fetch-helper naming convention
- `backend/database.py` (`TenantIsolatedCollection`/`TenantIsolatedDatabase`, read this session) — confirmed `users` is NOT in the global-exemption allowlist (tenant-isolated), explaining why `authentication_endpoints.py` already uses `db._db.users.find_one(...)` (bypass) for the pre-JWT login lookup — passkey login must do the same
- `backend/router_registry.py` (read this session) — confirmed exact registration pattern (`_load(app, "mfa_endpoints", "router")`) to clone for `passkey_endpoints`
- `backend/rate_limiter.py` (read this session) — confirmed shared `limiter`, Redis-optional in-memory fallback
- `backend/tests/test_auth_mfa.py`, `backend/tests/test_authentication.py` (partial reads, this session) — confirmed existing regression-test files AUTH-01 must keep green, and the `TestClient`+mocked-DB test-helper convention to clone
- `pytest.ini`, `package.json` (read this session) — test framework/config confirmation
- `backend/requirements.txt` (full file read, this session) — confirmed no existing WebAuthn dependency; confirmed Python 3.12.x-3.13.x target compatible with `webauthn>=3.0.0`'s `requires_python>=3.10`
- CLAUDE.md (read this session) — 500-line file limit (direct cause of Pitfall 1's finding), "don't hand-roll," "validate input at boundaries"
- `.planning/phases/29-public-trust-center/29-RESEARCH.md` (read in full, this session) — confirmed custom-domain scope is limited to the public Trust Center page, not the authenticated app, supporting the single-static-RP-ID conclusion (Summary, Assumption A2)
- `.planning/STATE.md`, `.planning/ROADMAP.md`, `.planning/REQUIREMENTS.md` (read this session) — phase scope, requirement text, milestone/roadmap context, Phase 25/CHK-03 `response: Response` incident history

### Secondary (MEDIUM confidence)
- [github.com/duo-labs/py_webauthn](https://github.com/duo-labs/py_webauthn) + [examples/registration.py](https://github.com/duo-labs/py_webauthn/blob/master/examples/registration.py) + [examples/authentication.py](https://github.com/duo-labs/py_webauthn/blob/master/examples/authentication.py) (WebFetch of official repo/examples, this session) — exact API call shapes used in Code Examples
- [pypi.org/project/webauthn](https://pypi.org/pypi/webauthn/json) + `pip index versions webauthn` (registry query, this session) — version 3.0.0, `requires_python>=3.10`
- [npmjs.com/package/@simplewebauthn/browser](https://www.npmjs.com/package/@simplewebauthn/browser) + [simplewebauthn.dev/docs/packages/browser](https://simplewebauthn.dev/docs/packages/browser) (WebSearch + registry query, this session) — version 13.3.0, API surface
- [github.com/bodik/soft-webauthn](https://github.com/bodik/soft-webauthn) + [soft_webauthn.py](https://github.com/bodik/soft-webauthn/blob/master/soft_webauthn.py) (WebFetch of official repo, this session) — `SoftWebauthnDevice` API for Wave 0 test infrastructure
- [Deep Dive: Relying Party ID & origin (Passkeys) — Duende](https://duendesoftware.com/blog/20251014-deep-dive-into-relying-party-id-and-origin-with-passkeys), [RP ID deep dive — web.dev](https://web.dev/articles/webauthn-rp-id), [WebAuthn Relying Party ID (rpID) & Passkeys — Corbado](https://www.corbado.com/blog/webauthn-relying-party-id-rpid-passkeys) (WebSearch, this session) — RP ID / origin best practices, static-value reasoning
- [WebAuthn Client Registration — Yubico Developer Guide](https://developers.yubico.com/WebAuthn/WebAuthn_Developer_Guide/WebAuthn_Client_Registration.html), [Authenticator Counter — Webauthn Framework docs](https://webauthn-doc.spomky-labs.com/symfony-bundle/advanced-behaviors/authenticator-counter), [ImperialViolet: Signature counters](https://www.imperialviolet.org/2023/08/05/signature-counters.html) (WebSearch, this session) — sign-count/cloned-authenticator detection semantics and caveats (Pitfall 3)

### Tertiary (LOW confidence)
- None used as authoritative for any Standard Stack or Architecture recommendation without independent registry/repo verification — all package-version and API-surface claims were cross-checked against the actual PyPI/npm registries or the official GitHub repositories this session, even though the package *names themselves* remain tagged `[ASSUMED]` per the standing provenance rule (WebSearch/training-knowledge discovery, not Context7).

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM — package names/API surfaces sourced via WebSearch + official GitHub repos (not Context7), but versions independently cross-verified against live PyPI/npm registries this session; the backend `webauthn` package carries an unresolved `[SUS]` Package Legitimacy Gate flag requiring human sign-off before install
- Architecture: HIGH — every integration point (file-pair convention, credential storage shape, challenge-store pattern, RP ID resolution, JWT reuse, 500-line file-size constraint) is grounded in direct, full-file reads of this codebase's existing auth modules this session, not external research
- Pitfalls: HIGH for codebase-specific pitfalls (Pitfalls 1, 2, 4, 5 — all drawn directly from this session's file reads and this codebase's own documented incident history); MEDIUM for the WebAuthn-spec-level pitfall (Pitfall 3's sign-count semantics — cross-checked across three independent external sources, consistent caveats)

**Research date:** 2026-07-08
**Valid until:** 30 days for architectural/integration findings (stable, internal-codebase-grounded); 7 days for the exact package version pins (`webauthn` 3.0.0, `@simplewebauthn/browser` 13.3.0) given the backend package's very recent release cadence — re-verify versions at plan/execute time if this research is more than a week old. The `[SUS]` Package Legitimacy Gate flag on `webauthn` (PyPI) should be resolved via its `checkpoint:human-verify` task before this research's package recommendation is treated as final.
