# Phase 64: User Management & Auth - Research

**Researched:** 2026-08-12
**Domain:** Authentication, Authorization, User Management (FastAPI + MongoDB)
**Confidence:** HIGH

## Summary

Phase 64 addresses ITAM-Backlog requirements ITAM-USR-01 through ITAM-USR-06: User CRUD, RBAC, LDAP/AD integration, SAML/SSO, API access tokens, and 2FA. Critically, **most of this infrastructure already exists** in the codebase — the phase is primarily about extension and gap-closure, not greenfield building.

Existing modules: `rbac_service.py` (full permission engine with dependency factories), `mfa_service.py` (TOTP + backup codes + AES encryption + two-phase login), `sso_service.py` (331 lines), `api_key_auth.py`, `authentication_service.py` (JWT), `user_endpoints.py` (261 lines), `mfa_endpoints.py`, `sso_endpoints.py`. The ITAM console already uses `_require_itam_admin` pattern for admin gating (Phases 56-63).

**Primary recommendation:** Audit each existing module against the 6 requirements, identify gaps, extend — do not rewrite. The biggest unknowns are LDAP/AD integration (likely needs `python-ldap` or `ldap3`) and SAML (likely needs `pysaml2` or similar), neither of which appear to have backend counterparts yet.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| User CRUD (ITAM-USR-01) | API/Backend | Frontend | Backend owns data model + endpoints; frontend provides management UI |
| RBAC (ITAM-USR-02) | API/Backend | — | `rbac_service.py` already owns this; extend role/permission sets |
| LDAP/AD (ITAM-USR-03) | API/Backend | — | New integration module; no existing backend for LDAP |
| SAML/SSO (ITAM-USR-04) | API/Backend | — | `sso_service.py` exists (331 lines); verify SAML vs OAuth scope |
| API Tokens (ITAM-USR-05) | API/Backend | — | `api_key_auth.py` exists (32 lines); extend to full token lifecycle |
| 2FA (ITAM-USR-06) | API/Backend | — | `mfa_service.py` (260 lines) already complete; verify frontend wiring |

## Standard Stack

### Core (already in codebase — extend, don't replace)
| Library | Status | Purpose | Notes |
|---------|--------|---------|-------|
| `pyotp` | Installed | TOTP generation/verification | Used by `mfa_service.py` |
| `qrcode` | Installed | QR code generation for MFA enrollment | Used by `mfa_service.py` |
| `pyjwt` | Installed (assumed) | JWT token signing/verification | Used by `authentication_service.py` |
| `passlib[bcrypt]` | Installed (assumed) | Password hashing | Standard pattern in auth modules |
| FastAPI `Depends` | In use | Auth dependency injection | `rbac_service.has_permission()`, `require_role()` |

### Likely New Additions (for LDAP/SAML)
| Library | Purpose | When to Use |
|---------|---------|-------------|
| `python-ldap` or `ldap3` | LDAP/AD directory queries | ITAM-USR-03 requires LDAP integration |
| `pysaml2` or `python3-saml` | SAML 2.0 IdP consumer | ITAM-USR-04 requires SAML/SSO |
| `httpx` | OAuth2 OIDC token exchange | If SSO is OAuth2-based (check `sso_service.py` scope) |

**Version verification:** Not run — context exhausted. Planner must verify `pip index versions` for new additions before install.

## Existing Module Audit (Critical for Planner)

| Requirement | Existing Module | Gap Assessment |
|-------------|----------------|----------------|
| ITAM-USR-01: User CRUD | `user_endpoints.py` (261 lines) | Likely functional — verify ITAM-specific fields (tenant scoping, role assignment) |
| ITAM-USR-02: RBAC | `rbac_service.py` (153 lines) | Functional — `default_roles` dict, permission checks, dependency factories. Extend with ITAM-specific roles if needed |
| ITAM-USR-03: LDAP/AD | None found | **Full build required** — new `ldap_service.py` + endpoints |
| ITAM-USR-04: SAML/SSO | `sso_service.py` (331 lines) | **Scope check needed** — verify whether SAML or OAuth2 only. May need SAML-specific additions |
| ITAM-USR-05: API Tokens | `api_key_auth.py` (32 lines) | **Thin stub** — needs full lifecycle (create, list, revoke, scope, rate limit) |
| ITAM-USR-06: 2FA | `mfa_service.py` (260 lines) | **Near-complete** — TOTP, backup codes, AES encryption, two-phase login all present. Verify frontend wiring |

### Auth Architecture Pattern (from existing code)
```python
# rbac_service.py pattern — dependency injection
rbac_service = RBACService()

# Endpoint gating:
@router.get("/endpoint")
async def get_something(user: TokenData = Depends(rbac_service.has_permission("view:itam"))):
    ...

# Admin gating (ITAM-specific):
async def _require_itam_admin(user = Depends(get_current_user)):
    # checks manage:assets permission
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Password hashing | Custom SHA/MD5 | `passlib[bcrypt]` | Timing attacks, rainbow tables |
| TOTP 2FA | Custom OTP impl | `pyotp` | Already in use, RFC 6238 compliant |
| LDAP queries | Raw socket/HTTP | `python-ldap` or `ldap3` | Connection pooling, TLS, DN parsing |
| SAML assertion parsing | XML string parsing | `pysaml2` or `python3-saml` | Signature verification, replay protection |
| JWT signing | Custom HMAC | `pyjwt` | Already in use |

## Common Pitfalls

### Pitfall 1: MFA Session Token In-Memory Storage
**What goes wrong:** `mfa_service.py` stores MFA session tokens in `_mfa_sessions: dict` (in-memory). Server restart loses all pending MFA sessions.
**Why it happens:** Simplicity for single-process dev.
**How to avoid:** For production, move to Redis or MongoDB TTL collection. Document this as a known limitation if deferring.
**Warning signs:** Users report "MFA session expired" immediately after server restart.

### Pitfall 2: TOTP Secret Encryption Fallback
**What goes wrong:** `_encrypt_secret()` in `mfa_service.py` falls back to base64 (not encryption) if `encryption_service` import fails. TOTP secrets stored as plaintext-equivalent in MongoDB.
**Why it happens:** Graceful degradation for dev without encryption_service.
**How to avoid:** Fail loudly in production. Add startup health check that verifies encryption_service availability.
**Warning signs:** `mfa.secret_encrypted` values that are valid base64 but not encrypted.

### Pitfall 3: Role Normalization Inconsistency
**What goes wrong:** `auth_roles.py` defines `SUPER_ROLES` as `{"Super Admin", "superadmin", "super_admin", "platform-admin"}` while `rbac_service._normalize_role()` only handles space-to-underscore and lowercase. `"platform-admin"` normalizes to `"platform_admin"` which is NOT in the normalized set.
**Why it happens:** Two independent normalization paths.
**How to avoid:** Consolidate to single `_normalize_role()` call everywhere. Add `"platform_admin"` to normalized SUPER_ROLES.
**Warning signs:** Platform-admin users getting 403 on super_admin-gated endpoints.

### Pitfall 4: LDAP Password Synchronization
**What goes wrong:** After LDAP integration, users may have passwords in both MongoDB and LDAP. Changing password in one doesn't update the other.
**Why it happens:** Two auth sources without clear primary.
**How to avoid:** LDAP-sourced users should have a `source: "ldap"` field; local password changes blocked for LDAP users. Document clearly.

### Pitfall 5: API Token Scope Creep
**What goes wrong:** `api_key_auth.py` (32 lines) likely has no scope/permission system. API tokens get full user access.
**Why it happens:** Minimal initial implementation.
**How to avoid:** Design token scoping from day one (e.g., `read:assets`, `write:assets`, `admin`). Store scopes in token record.

## Code Examples

### Existing RBAC Dependency Pattern
```python
# Source: backend/rbac_service.py
rbac_service = RBACService()

@router.get("/assets")
async def list_assets(user: TokenData = Depends(rbac_service.has_permission("view:itam"))):
    ...
```

### Existing MFA Two-Phase Login Flow
```python
# Source: backend/mfa_service.py
# Phase 1: Password check → mfa_session_token
session_token = create_mfa_session(email)

# Phase 2: TOTP code + session_token → full JWT
result = await verify_mfa_token(session_token, totp_code)
# result: { "success": True, "email": "..." }
```

### Existing User Model (TokenData)
```python
# Source: backend/auth_types.py
@dataclass
class TokenData:
    username: Optional[str] = None
    role: Optional[str] = "user"
    tenant_id: Optional[str] = None
    mfa_verified: bool = False
```

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `sso_service.py` (331 lines) covers OAuth2/OIDC but not SAML | Existing Module Audit | If it covers SAML, less new code needed |
| A2 | `api_key_auth.py` (32 lines) is a minimal stub without full lifecycle | Existing Module Audit | If full lifecycle exists, USR-05 is simpler |
| A3 | No LDAP module exists in the codebase | Existing Module Audit | If one exists (named differently), less new code needed |
| A4 | `pyjwt` and `passlib[bcrypt]` are installed | Standard Stack | If not, adds install step |
| A5 | `python-ldap` or `ldap3` not yet installed | Standard Stack | If installed, LDAP phase is simpler |

## Open Questions

1. **What does `sso_service.py` actually implement?** (331 lines unread due to context limit). OAuth2? OIDC? SAML? This determines ITAM-USR-04 scope.
2. **What does `user_endpoints.py` expose?** (261 lines unread). Full CRUD? Tenant-scoped? This determines ITAM-USR-01 scope.
3. **Does LDAP/AD integration exist under a different name?** (e.g., `ldap_auth.py`, `active_directory.py`). Search missed it if so.
4. **What's the frontend auth state management pattern?** (e.g., React Context, Redux). Determines how 2FA/SSO flows wire to UI.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + asyncio.run() |
| Config file | None detected in auth modules |
| Quick run command | `pytest backend/tests/test_auth*.py -x` |
| Full suite command | `pytest backend/tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ITAM-USR-01 | User CRUD | unit | `pytest backend/tests/test_user*.py -x` | Unknown — context limit |
| ITAM-USR-02 | RBAC enforcement | unit | `pytest backend/tests/test_rbac*.py -x` | Unknown — context limit |
| ITAM-USR-03 | LDAP auth | integration | `pytest backend/tests/test_ldap*.py -x` | Likely no (new) |
| ITAM-USR-04 | SAML/SSO | integration | `pytest backend/tests/test_sso*.py -x` | Unknown |
| ITAM-USR-05 | API token lifecycle | unit | `pytest backend/tests/test_api_key*.py -x` | Unknown |
| ITAM-USR-06 | 2FA flow | unit | `pytest backend/tests/test_mfa*.py -x` | Unknown |

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `pyotp` (TOTP), `passlib` (bcrypt), JWT |
| V3 Session Management | yes | JWT tokens, MFA session tokens (in-memory) |
| V4 Access Control | yes | `rbac_service.py` permission checks |
| V5 Input Validation | yes | Pydantic models (`TokenData`, `Token`) |
| V6 Cryptography | yes | AES-256 via `encryption_service`, bcrypt for passwords |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| MFA bypass via session token | Elevation of Privilege | Short TTL (5 min), single-use consumption |
| LDAP injection | Tampering | Parameterized DN queries, input validation |
| SAML assertion replay | Spoofing | Timestamp + audience validation |
| API token leakage | Information Disclosure | Scoped permissions, rotation support |
| Password spray | Elevation of Privilege | Rate limiting, account lockout (verify exists) |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Backend | Yes | — | — |
| MongoDB | Data layer | Yes | — | — |
| FastAPI | Backend framework | Yes | — | — |
| React/TypeScript | Frontend | Yes | — | — |
| `python-ldap` | LDAP integration | Unknown | — | Use `ldap3` (pure Python, no C deps) |
| `pysaml2` | SAML SSO | Unknown | — | Use `python3-saml` |

**Missing dependencies with no fallback:**
- LDAP/AD: If neither `python-ldap` nor `ldap3` is installed, ITAM-USR-03 blocks. Planner must include install step.
- SAML: If neither `pysaml2` nor `python3-saml` is installed, ITAM-USR-04 blocks (if SAML is in scope per `sso_service.py` audit).

## Sources

### Primary (HIGH confidence)
- Backend source files read directly: `auth_roles.py`, `auth_types.py`, `rbac_service.py`, `mfa_service.py`
- `.planning/REQUIREMENTS.md` — ITAM-USR-01 through ITAM-USR-06 definitions
- `.planning/PROJECT.md` — Architecture decisions, existing auth patterns
- `.planning/codebase/ITAM-VS-SNIPE.md` — Gap analysis showing Users & Permissions as "Missing"

### Secondary (MEDIUM confidence)
- File listing grep for auth-related modules — identified existing infrastructure

### Tertiary (LOW confidence)
- Library version verification not completed (context limit)
- `sso_service.py`, `user_endpoints.py`, `api_key_auth.py` contents not read (context limit)

## Metadata

**Confidence breakdown:**
- Standard Stack: MEDIUM — existing modules identified but versions not verified via pip
- Architecture: HIGH — existing patterns clearly documented from source code
- Pitfalls: HIGH — derived from actual code inspection (MFA in-memory store, base64 fallback, role normalization gap)

**Research date:** 2026-08-12
**Valid until:** 2026-09-12 (30 days — stable domain)

## Key Finding: This Phase Is Mostly Extension, Not Greenfield

The planner should structure tasks as:
1. **Audit** existing modules (`sso_service.py`, `user_endpoints.py`, `api_key_auth.py`) against requirements
2. **Extend** what exists (RBAC roles, API token lifecycle, user CRUD fields)
3. **Build new** only for LDAP (`ldap_service.py`) and possibly SAML additions
4. **Wire frontend** for any missing UI flows (2FA enrollment, SSO login, API token management)
5. **Fix known pitfalls** (in-memory MFA sessions, base64 fallback, role normalization gap)
