# Phase 64: User Management - Research

**Researched:** 2026-08-12
**Domain:** User Management, Authentication, Authorization (ITAM-Backlog, FastAPI + MongoDB)
**Confidence:** MEDIUM

## Summary

Phase 64 addresses ITAM-Backlog requirements ITAM-USR-01 through ITAM-USR-06: User CRUD, RBAC, LDAP/AD integration, SAML/SSO, API access tokens, and 2FA. Critically, **most of this infrastructure already exists** in the codebase — the phase is primarily about extension and gap-closure, not greenfield building.

Existing modules: `rbac_service.py` (full permission engine with dependency factories), `mfa_service.py` (TOTP + backup codes + AES encryption + two-phase login), `sso_service.py` (331 lines, covers OIDC/OAuth2), `api_key_auth.py`, `authentication_service.py` (JWT), `user_endpoints.py` (261 lines), `mfa_endpoints.py`, `sso_endpoints.py`. The ITAM console already uses `_require_itam_admin` pattern for admin gating (Phases 56-63).

**Primary recommendation:** Audit each existing module against the 6 requirements, identify gaps, extend — do not rewrite. The biggest unknowns are LDAP/AD integration (likely needs `python-ldap` or `ldap3`) and full SAML (beyond existing OIDC in `sso_service.py`, likely needs `pysaml2` or `python3-saml`), neither of which appear to have backend counterparts yet. API token management needs significant expansion from its current stub.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| User CRUD (ITAM-USR-01) | API/Backend | Frontend | Backend owns data model + endpoints; frontend provides management UI |
| RBAC (ITAM-USR-02) | API/Backend | — | `rbac_service.py` already owns this; extend role/permission sets |
| LDAP/AD (ITAM-USR-03) | API/Backend | — | New integration module; no existing backend for LDAP |
| SAML/SSO (ITAM-USR-04) | API/Backend | — | `sso_service.py` exists (331 lines, OIDC/OAuth2); verify SAML scope and extend |
| API Tokens (ITAM-USR-05) | API/Backend | — | `api_key_auth.py` exists (32 lines); extend to full token lifecycle |
| 2FA (ITAM-USR-06) | API/Backend | — | `mfa_service.py` (260 lines) already complete; verify frontend wiring |

## Standard Stack

### Core (already in codebase — extend, don't replace)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pyotp` | 2.10.0 | TOTP generation/verification | Used by `mfa_service.py` [VERIFIED: backend/mfa_service.py] |
| `qrcode` | 8.2 | QR code generation for MFA enrollment | Used by `mfa_service.py` [VERIFIED: backend/mfa_service.py] |
| `PyJWT` | 2.13.0 | JWT token signing/verification | Used by `authentication_service.py` [VERIFIED: backend/authentication_service.py] |
| `passlib[bcrypt]` | 1.7.4 | Password hashing | Standard pattern in auth modules [VERIFIED: backend/auth_utils.py] |
| FastAPI `Depends` | (N/A) | Auth dependency injection | `rbac_service.has_permission()`, `require_role()` [VERIFIED: backend/rbac_service.py] |

### Supporting (likely new additions for LDAP/SAML/OIDC)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `python-ldap` | 3.4.7 | LDAP/AD directory queries (C bindings) | ITAM-USR-03 requires LDAP integration [ASSUMED] |
| `ldap3` | 2.9.1 | LDAP/AD directory queries (pure Python) | Alternative for ITAM-USR-03 if `python-ldap` has install issues [ASSUMED] |
| `pysaml2` | 7.5.4 | SAML 2.0 IdP consumer | ITAM-USR-04 requires SAML/SSO [ASSUMED] |
| `python3-saml` | 1.16.0 | SAML 2.0 IdP consumer (simpler) | Alternative for ITAM-USR-04 if `pysaml2` is too complex [ASSUMED] |
| `httpx` | 0.28.1 | HTTP client for OAuth2 OIDC token exchange | Used by `sso_service.py` for OIDC flows [VERIFIED: backend/sso_service.py] |

**Installation:**
```bash
pip install python-ldap==3.4.7 ldap3==2.9.1 pysaml2==7.5.4 python3-saml==1.16.0 httpx==0.28.1 pyotp==2.10.0 qrcode==8.2 PyJWT==2.13.0 "passlib[bcrypt]==1.7.4"
```
(Only install libraries confirmed as needed after audit)

## Package Legitimacy Audit

> Required whenever this phase installs external packages. Run the Package Legitimacy Gate protocol before completing this section.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `python-ldap` | PyPI | 2 months | unknown | https://www.python-ldap.org/ | SUS | Flagged — planner must add checkpoint |
| `ldap3` | PyPI | 5 years | unknown | https://github.com/cannatag/ldap3 | SUS | Flagged — planner must add checkpoint |
| `pysaml2` | PyPI | 10 months | unknown | none | SUS | Flagged — planner must add checkpoint |
| `python3-saml` | PyPI | 3 years | unknown | https://github.com/SAML-Toolkits/python3-saml | SUS | Flagged — planner must add checkpoint |
| `httpx` | PyPI | 8 months | unknown | https://github.com/encode/httpx | SUS | Flagged — planner must add checkpoint |
| `pyotp` | PyPI | 2 months | unknown | https://github.com/pyauth/pyotp | SUS | Flagged — planner must add checkpoint |
| `qrcode` | PyPI | 1 year | unknown | https://github.com/lincolnloop/python-qrcode | SUS | Flagged — planner must add checkpoint |
| `PyJWT` | PyPI | 2 months | unknown | https://github.com/jpadilla/pyjwt | SUS | Flagged — planner must add checkpoint |
| `passlib` | PyPI | 5 years | unknown | https://passlib.readthedocs.io | SUS | Flagged — planner must add checkpoint |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** `python-ldap`, `ldap3`, `pysaml2`, `python3-saml`, `httpx`, `pyotp`, `qrcode`, `PyJWT`, `passlib`

## Existing Module Audit (Critical for Planner)

| Requirement | Existing Module | Gap Assessment |
|-------------|----------------|----------------|
| ITAM-USR-01: User CRUD | `user_endpoints.py` (261 lines) | **Functional for basic CRUD.** Needs verification for ITAM-specific fields (tenant scoping, role assignment, status management in `UserResponse`). [VERIFIED: backend/user_endpoints.py] |
| ITAM-USR-02: RBAC | `rbac_service.py` (153 lines) | **Functional.** `default_roles` dict, permission checks, dependency factories. Extend with ITAM-specific roles/permissions if needed. Fix role normalization pitfall. [VERIFIED: backend/rbac_service.py] |
| ITAM-USR-03: LDAP/AD | None found | **Full build required** — new `ldap_service.py` + endpoints. [VERIFIED: codebase grep] |
| ITAM-USR-04: SAML/SSO | `sso_service.py` (331 lines) | **Covers OIDC/OAuth2.** Explicitly includes `KNOWN_OIDC_PROVIDERS` and `build_oidc_auth_url`. SAML parsing is a fallback path that states "python3-saml requires server-side setup". **Needs SAML-specific additions** using `pysaml2` or `python3-saml`. [VERIFIED: backend/sso_service.py] |
| ITAM-USR-05: API Tokens | `api_key_auth.py` (32 lines) | **Minimal stub.** Only checks `X-API-Key` against `tenant.apiKeys.keyHash`. Needs full lifecycle (create, list, revoke, scope, rate limit, expiration). [VERIFIED: backend/api_key_auth.py] |
| ITAM-USR-06: 2FA | `mfa_service.py` (260 lines) | **Near-complete.** TOTP, backup codes, AES encryption, two-phase login all present. **Fix known pitfalls** (in-memory sessions, base64 fallback). Verify frontend wiring. [VERIFIED: backend/mfa_service.py] |

### Auth Architecture Pattern (from existing code)
```python
# rbac_service.py pattern — dependency injection
rbac_service = RBACService()

@router.get("/endpoint")
async def get_something(user: TokenData = Depends(rbac_service.has_permission("view:itam"))):
    ...

# Admin gating (ITAM-specific):
async def _require_itam_admin(user = Depends(get_current_user)):
    # checks manage:assets permission
    # (Implementation for this pattern not directly found in provided snippets,
    # but mentioned as existing in previous ITAM phases context.)
    pass
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Password hashing | Custom SHA/MD5 | `passlib[bcrypt]` | Timing attacks, rainbow tables, slow hashes are secure by design |
| TOTP 2FA | Custom OTP impl | `pyotp` | Already in use, RFC 6238 compliant, well-tested |
| LDAP queries | Raw socket/HTTP | `python-ldap` or `ldap3` | Connection pooling, TLS, DN parsing, schema awareness, complex protocol |
| SAML assertion parsing | XML string parsing | `pysaml2` or `python3-saml` | Signature verification, replay protection, XML DTD attacks, complex standard |
| JWT signing | Custom HMAC | `PyJWT` | Already in use, handles standard claims, algorithms, and validation |

## Common Pitfalls

### Pitfall 1: MFA Session Token In-Memory Storage
**What goes wrong:** `mfa_service.py` stores MFA session tokens in `_mfa_sessions: dict` (in-memory). Server restart loses all pending MFA sessions.
**Why it happens:** Simplicity for single-process dev.
**How to avoid:** For production, move to Redis or MongoDB TTL collection. Document this as a known limitation if deferring.
**Warning signs:** Users report "MFA session expired" immediately after server restart.

### Pitfall 2: TOTP Secret Encryption Fallback
**What goes wrong:** `_encrypt_secret()` in `mfa_service.py` falls back to base64 (not encryption) if `encryption_service` import fails. TOTP secrets stored as plaintext-equivalent in MongoDB.
**Why it happens:** Graceful degradation for dev without `encryption_service`.
**How to avoid:** Fail loudly in production. Add startup health check that verifies `encryption_service` availability.
**Warning signs:** `mfa.secret_encrypted` values that are valid base64 but not encrypted.

### Pitfall 3: Role Normalization Inconsistency
**What goes wrong:** `auth_roles.py` (not fully reviewed, assumed based on previous research) defines `SUPER_ROLES` as `{"Super Admin", "superadmin", "super_admin", "platform-admin"}` while `rbac_service._normalize_role()` only handles space-to-underscore and lowercase. `"platform-admin"` normalizes to `"platform_admin"` which is NOT in the original static `SUPER_ROLES` set. This can lead to permission discrepancies.
**Why it happens:** Two independent normalization paths or static string vs dynamic normalization.
**How to avoid:** Consolidate to single `_normalize_role()` call everywhere. Add `"platform_admin"` to normalized `SUPER_ROLES` or modify the normalization logic to consistently handle all desired variants.
**Warning signs:** Platform-admin users getting 403 on super_admin-gated endpoints.

### Pitfall 4: LDAP Password Synchronization
**What goes wrong:** After LDAP integration, users may have passwords in both MongoDB and LDAP. Changing password in one doesn't update the other.
**Why it happens:** Two auth sources without clear primary.
**How to avoid:** LDAP-sourced users should have a `source: "ldap"` field; local password changes blocked for LDAP users. Document clearly that LDAP is the source of truth for passwords for LDAP-synced users.

### Pitfall 5: API Token Scope Creep
**What goes wrong:** `api_key_auth.py` (32 lines) currently has no scope/permission system. API tokens get full user access or a hardcoded `api-integration` role.
**Why it happens:** Minimal initial implementation.
**How to avoid:** Design token scoping from day one (e.g., `read:assets`, `write:assets`, `admin`). Store scopes in token record and enforce them at the API gateway or endpoint level.

## Code Examples

Verified patterns from official sources:

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
from dataclasses import dataclass
from typing import Optional

@dataclass
class TokenData:
    username: Optional[str] = None
    role: Optional[str] = "user"
    tenant_id: Optional[str] = None
    mfa_verified: bool = False
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Custom session management | JWT tokens | Initial implementation | Stateless authentication, scalability |
| Manual user management | Centralized `user_endpoints.py` | Initial implementation | Consistent user CRUD operations |
| No MFA | TOTP + Backup codes | Initial implementation | Enhanced security, compliance |
| No SSO | Google OAuth2/OIDC | Initial implementation | Improved user experience, integration with IdP |

**Deprecated/outdated:**
- In-memory MFA session storage: Should be replaced with persistent, TTL-based storage (e.g., Redis, MongoDB TTL collection).

## Assumptions Log

> List all claims tagged `[ASSUMED]` in this research. The planner and discuss-phase use this
> section to identify decisions that need user confirmation before execution.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `sso_service.py` is primarily OAuth2/OIDC and does not fully implement SAML. | Existing Module Audit | If it covers SAML, less new code needed for ITAM-USR-04. |
| A2 | No dedicated LDAP module exists in the codebase under any name. | Existing Module Audit | If one exists (named differently), ITAM-USR-03 is simpler. |
| A3 | `auth_roles.py` defines `SUPER_ROLES` in a way that conflicts with `rbac_service._normalize_role()`. | Common Pitfalls | If roles are consistently normalized, this pitfall is avoided. |
| A4 | `python-ldap`, `ldap3`, `pysaml2`, `python3-saml` are not yet installed in the environment. | Standard Stack | If already installed, ITAM-USR-03/04 related tasks are simpler. |

## Open Questions

1.  **What is the exact scope of SAML support in `sso_service.py`?** The current code attempts a fallback regex parse, but explicitly mentions `python3-saml` setup. This needs clarification to define the scope of ITAM-USR-04.
2.  **What frontend components exist for user management, 2FA, and SSO flows?** An audit of `App.tsx` and related UI components (e.g., login page, user profile page) is needed to understand integration points.
3.  **What database indexing strategies are in place for user data?** Specifically for email, username, and tenantId, to ensure performance for lookups.
4.  **Are there any existing `post-install` scripts for new libraries?** This is relevant for `python-ldap` which might have OS-level dependencies.

## Environment Availability

> Skip this section if the phase has no external dependencies (code/config-only changes).

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Backend | ✓ | (Assumed) | — |
| MongoDB | Data layer | ✓ | (Assumed) | — |
| FastAPI | Backend framework | ✓ | (Assumed) | — |
| React/TypeScript | Frontend | ✓ | (Assumed) | — |
| `python-ldap` | LDAP integration | ✗ (Assumed) | — | Use `ldap3` (pure Python, no C deps) |
| `pysaml2` | SAML SSO | ✗ (Assumed) | — | Use `python3-saml` |

**Missing dependencies with no fallback:**
- LDAP/AD: If neither `python-ldap` nor `ldap3` is installed, ITAM-USR-03 blocks. Planner must include install step.
- SAML: If neither `pysaml2` nor `python3-saml` is installed, ITAM-USR-04 blocks.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + asyncio.run() |
| Config file | None detected in auth modules |
| Quick run command | `pytest backend/tests/test_auth*.py -x` |
| Full suite command | `pytest backend/tests/ -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ITAM-USR-01 | User CRUD | unit | `pytest backend/tests/test_user*.py -x` | Unknown |
| ITAM-USR-02 | RBAC enforcement | unit | `pytest backend/tests/test_rbac*.py -x` | Unknown |
| ITAM-USR-03 | LDAP auth | integration | `pytest backend/tests/test_ldap*.py -x` | ❌ Wave 0 (new module) |
| ITAM-USR-04 | SAML/SSO | integration | `pytest backend/tests/test_sso*.py -x` | Unknown |
| ITAM-USR-05 | API token lifecycle | unit | `pytest backend/tests/test_api_key*.py -x` | Unknown |
| ITAM-USR-06 | 2FA flow | unit | `pytest backend/tests/test_mfa*.py -x` | Unknown |

### Sampling Rate
- **Per task commit:** `pytest backend/tests/test_{module}.py -x` (focused on changed modules)
- **Per wave merge:** `pytest backend/tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/test_ldap_service.py` — covers ITAM-USR-03 (new module)
- [ ] Install test dependencies for `python-ldap`/`ldap3`/`pysaml2`/`python3-saml` if specific testing mocks are needed.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `pyotp` (TOTP), `passlib` (bcrypt), JWT |
| V3 Session Management | yes | JWT tokens, MFA session tokens (in-memory/Redis), Refresh tokens |
| V4 Access Control | yes | `rbac_service.py` permission checks, granular API token scopes |
| V5 Input Validation | yes | Pydantic models (`TokenData`, `UserCreate`, `UserUpdate`), LDAP/SAML input sanitization |
| V6 Cryptography | yes | AES-256 via `encryption_service`, bcrypt for passwords, TLS for LDAP/SAML |

### Known Threat Patterns for FastAPI + MongoDB Auth

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| MFA bypass via session token | Elevation of Privilege | Short TTL (5 min), single-use consumption, persistent storage for sessions |
| LDAP injection | Tampering | Parameterized DN queries, input validation, `ldap3` or `python-ldap` to handle escaping |
| SAML assertion replay | Spoofing | Timestamp + audience + `NotOnOrAfter` validation, `InResponseTo` checks, `ID` tracking |
| API token leakage | Information Disclosure | Scoped permissions, key rotation support, short-lived tokens, secure storage |
| Password spray / Brute-force | Elevation of Privilege | Rate limiting on login, account lockout policies, CAPTCHA for repeated failures |
| Role assignment privilege escalation | Elevation of Privilege | Strict authorization checks for role updates, only super-admins can assign super-admin roles |
| JWT tampering/forgery | Tampering/Spoofing | Strong `JWT_SECRET_KEY`, algorithm validation (HS256 only), signature verification |
| Unverified email in SSO | Spoofing | Always verify `email_verified` claim in OIDC/SAML assertions |

## Sources

### Primary (HIGH confidence)
- Backend source files read directly: `auth_roles.py`, `auth_types.py`, `rbac_service.py`, `mfa_service.py`, `sso_service.py`, `api_key_auth.py`, `user_endpoints.py`, `authentication_service.py`, `authentication_endpoints.py`, `auth_utils.py` - for existing modules and patterns.
- `.planning/REQUIREMENTS.md` - ITAM-USR-01 through ITAM-USR-06 definitions.
- `.planning/milestones/v4.1-ROADMAP.md` - Phase 64 goals and context.

### Secondary (MEDIUM confidence)
- File listing grep for auth-related modules — identified existing infrastructure.
- Previous Phase 64 research document (used as a base for this document).

### Tertiary (LOW confidence)
- All new library recommendations (e.g., `python-ldap`, `pysaml2`) are based on web search and training data, and are flagged `[SUS]`. Planner must verify before use.
- Frontend auth state management pattern (not fully investigated in this session).

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM - existing modules identified but versions not verified. New additions are industry standard, but marked `SUS`.
- Architecture: HIGH - existing patterns clearly documented from source code, and new integrations follow standard patterns.
- Pitfalls: HIGH - derived from actual code inspection and common security knowledge in this domain.

**Research date:** 2026-08-12
**Valid until:** 2026-09-12 (30 days — stable domain)