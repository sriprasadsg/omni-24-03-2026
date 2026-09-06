---
phase: 69-user-management
reviewed: 2026-08-13T08:04:48Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - backend/mfa_service.py
  - backend/mfa_endpoints.py
  - backend/authentication_endpoints.py
  - components/UserProfilePage.tsx
  - backend/tests/test_mfa.py
  - backend/tests/test_auth_mfa.py
findings:
  critical: 2
  warning: 7
  info: 2
  total: 11
status: fixed
fixed_at: 2026-08-13T08:20:00Z
fix_status:
  fixed:
    - id: CR-01
      commit: 41db5aa2
      note: fixed separately, prior to this review-fix pass
    - id: CR-02
      commit: d9305c75
    - id: WR-01
      commit: 4c16aafb
    - id: WR-02
      commit: 5b560a17
    - id: WR-03
      commit: dfdc1fda
    - id: WR-04
      commit: 9256308d
    - id: WR-05
      commit: 3c925ef2
    - id: WR-06
      commit: f68f120f
    - id: WR-07
      commit: ec968860
    - id: IN-02
      commit: e83ce2f0
  not_applicable:
    - id: IN-01
      note: product decision, not a code defect — intentionally left as-is per the finding's own "N/A" fix guidance
---

# Phase 69 Plan 06: Code Review Report — 2FA/TOTP

**Reviewed:** 2026-08-13T08:04:48Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** fixed

## Fix Status (2026-08-13T08:20:00Z)

All actionable findings are fixed. `IN-01` is an explicit product decision
(not a code defect) per its own "N/A" fix guidance and was intentionally
left as-is.

| Finding | Status | Commit |
|---|---|---|
| CR-01 | Fixed (prior pass) | `41db5aa2` |
| CR-02 | Fixed | `d9305c75` |
| WR-01 | Fixed | `4c16aafb` |
| WR-02 | Fixed | `5b560a17` |
| WR-03 | Fixed | `dfdc1fda` |
| WR-04 | Fixed | `9256308d` |
| WR-05 | Fixed | `3c925ef2` |
| WR-06 | Fixed | `f68f120f` |
| WR-07 | Fixed | `ec968860` |
| IN-01 | N/A — product decision, not a defect | — |
| IN-02 | Fixed | `e83ce2f0` |

`backend/tests/test_mfa.py` and `backend/tests/test_auth_mfa.py` were
extended to cover the new/changed observable behavior (re-enrollment
password gate, atomic backup-code consumption, rate limiting, TOTP
anti-replay, login-lockout folding, session cap, request-model length
bounds, MFA-session DB-failure handling, QR-failure logging). Full suite:
81 passed, 0 failed (`pytest tests/test_mfa.py tests/test_auth_mfa.py`).

## Summary

Reviewed the 2FA/TOTP implementation (enroll, verify, backup codes, disable, MongoDB TTL session persistence, AES-256-at-rest encryption) delivered by plan 64-06, commits `57a27292`, `4d0c728e`, `928bbf0b`.

The two headline fixes claimed by the SUMMARY hold up under inspection: MFA sessions are genuinely persisted in a MongoDB TTL collection (not an in-memory dict), and `_encrypt_secret`/`_decrypt_secret` genuinely fail closed with no base64 fallback (`encryption_service` imported at module level, no `try/except ImportError` swallow). The `mfa_verified=True` JWT claim fix is real and correctly wired through `TokenData`/`require_mfa`. Backup codes are bcrypt-hashed via the same `auth_utils` convention as passwords, a legitimate improvement over unsalted SHA-256.

The specific tradeoff flagged for scrutiny — `verify_mfa_token` consuming the MFA session via `find_one_and_delete` on the very first attempt, correct or not — is confirmed to work exactly as SUMMARY describes, and its blast radius is confirmed **not** to extend to password auth: `/api/auth/login`'s own lockout/attempt-tracking (`_check_login_lockout`/`_record_login_failure`) only fires on failed *password* verification, and a wrong TOTP code doesn't touch that counter at all. However, that same fact creates an adjacent, unflagged risk (WR-04 below): an attacker who already knows the account password can grind the TOTP keyspace across unlimited fresh login+verify round trips, because "wrong TOTP" never counts as a login failure.

Two Critical findings were found: an information-disclosure bug where `/api/mfa/verify`'s response can leak a user's bcrypt password hash for accounts created via the admin `user_endpoints.py` path (which stores the hash under `hashed_password`, not `password`), and a control-bypass where the password-confirmation gate this plan added to `/mfa/disable` and `/mfa/backup-codes/regenerate` (T-64-26) can be sidestepped entirely by re-running `/mfa/setup` + `/mfa/verify-setup` against an already-enrolled account, silently replacing the active TOTP secret and backup codes with attacker-controlled ones — with only a valid JWT, no password required at all.

## Critical Issues

### CR-01: `/api/mfa/verify` can leak a user's password hash in the JSON response body

**Status:** Fixed (prior pass) — commit `41db5aa2`

**File:** `backend/mfa_endpoints.py:116`
**Issue:** The post-MFA-verification response builds `user_data` by excluding only three keys:
```python
user_data = {k: v for k, v in user.items() if k not in ("password", "_id", "mfa")}
```
This is a narrower, ad-hoc exclusion list than `authentication_endpoints.py`'s own `_SENSITIVE_USER_FIELDS` set (`password`, `hashed_password`, `password_hash`, `_id`, `mfa`, `reset_token`, `invite_token`, `api_key`, `secret` — see `authentication_endpoints.py:5-9`).

Crucially, `hashed_password` is a real, live field name in this codebase: users created via `backend/user_endpoints.py` (the admin user-management flow) store their bcrypt hash under `hashed_password` (`user_endpoints.py:226`, `:294`), not `password`. `mfa_service.disable_mfa`/`regenerate_backup_codes` even account for this dual naming (`user.get("password") or user.get("hashed_password")`), but `mfa_endpoints.py`'s response-shaping code does not.

Concretely: any admin-created user who enables 2FA will have their bcrypt password hash included verbatim in the `user` object of every successful `/api/mfa/verify` response — handed directly to the browser (and to any logging/APM middleware that captures response bodies), enabling offline brute-forcing of the account password.

**Fix:** Reuse the same exclusion set used elsewhere in the codebase instead of a local literal tuple:
```python
from authentication_endpoints import _SENSITIVE_USER_FIELDS
...
user_data = {k: v for k, v in user.items() if k not in _SENSITIVE_USER_FIELDS}
```
(or hoist `_SENSITIVE_USER_FIELDS` into a shared module both files import from, to prevent this drift recurring.)

### CR-02: MFA re-enrollment bypasses the password-confirmation gate this plan added for disable/regenerate

**Status:** Fixed — commit `d9305c75`

**File:** `backend/mfa_endpoints.py:35-75` (`/api/mfa/setup`, `/api/mfa/verify-setup`), `backend/mfa_service.py:147-179` (`enroll_mfa`)
**Issue:** This plan hardened `disable_mfa` and `regenerate_backup_codes` to require the account password (T-64-26/T-64-25), explicitly because "a lost/stolen authenticator app should not be sufficient to turn MFA off." But `setup_mfa`/`enroll_mfa` have no equivalent gate at all:

- `POST /api/mfa/setup` (`mfa_endpoints.py:36`) only requires `Depends(get_current_user)` — a valid JWT, nothing else — and unconditionally overwrites `mfa.pending_secret`, with no check for whether MFA is already `enabled` on the account.
- `POST /api/mfa/verify-setup` → `enroll_mfa()` (`mfa_service.py:147`) then unconditionally sets `mfa.secret_encrypted = pending` and replaces `mfa.backup_codes_hashed` with a fresh attacker-chosen set — again with no check for a pre-existing `mfa.enabled == True` state, and no password re-confirmation.

Net effect: anyone holding a valid JWT for the account (e.g. via XSS, a leaked/stolen bearer token, or a fixated session — the exact "MFA bypass via session" threat class T-64-23 is meant to guard against) can silently re-enroll their own TOTP secret and backup codes on top of the victim's, without ever knowing the account password. This produces the same practical outcome the disable/regenerate password gate was built to prevent (attacker controls the second factor going forward) and does so through a path this plan's own threat register (T-64-26) claims is closed.

Note: `/setup` and `/verify-setup` were not touched by this plan's diff (frozen per the plan's `<frontend_scope>`), so this is pre-existing behavior — but it directly undermines the security property the plan's SUMMARY claims to have delivered ("closing the gap where a stolen/lost authenticator alone could turn 2FA off"), so it's flagged here as the gap is still open via a different route.

**Fix:** Require password confirmation (or at minimum an explicit re-auth / existing-TOTP-code check) before `/api/mfa/setup` is allowed to run against an account where `mfa.enabled` is already `True`:
```python
user = await db.users.find_one({"email": current_user.username})
if user.get("mfa", {}).get("enabled"):
    raise HTTPException(status_code=403, detail="MFA already enabled — disable it first or use the re-enrollment flow with password confirmation")
```
or thread a `password` field through `/setup`/`verify-setup` the same way `/disable` and `/backup-codes/regenerate` now do.

## Warnings

### WR-01: TOCTOU race lets a single backup code be consumed twice

**Status:** Fixed — commit `4c16aafb`

**File:** `backend/mfa_service.py:120-142` (`use_backup_code`)
**Issue:** The read-check-write is not atomic: `find_one` reads `backup_codes_hashed`, the matching hash is located in Python, then a single `update_one` `$set`s a locally-computed `new_hashes` list back. Two concurrent requests submitting the same still-valid backup code will both read the same list, both find the match, and both return `True` before either write lands — the single-use guarantee for that code is lost under a race.
**Fix:** Make consumption atomic with a single `find_one_and_update` that both matches and removes the hash in one operation (e.g. `$pull` the specific hash and check `modified_count`/the returned document to determine success), instead of read-then-replace-the-whole-array:
```python
result = await db.users.find_one_and_update(
    {"email": email, "mfa.backup_codes_hashed": code_hash},
    {"$pull": {"mfa.backup_codes_hashed": code_hash}, "$set": {"mfa.last_used_at": ...}},
)
return result is not None
```
(bcrypt hashes aren't directly matchable by Mongo query since they're salted per-call — this requires either pre-computing which hash matched via a first read, then using that exact hash string as the `$pull`/match filter as shown, which closes the double-spend window even though the initial verification-scan is still non-atomic.)

### WR-02: `/api/mfa/disable` and `/api/mfa/backup-codes/regenerate` have no rate limiting or lockout

**Status:** Fixed — commit `5b560a17`

**File:** `backend/mfa_endpoints.py:128-143`
**Issue:** Every other credential-adjacent endpoint in this flow is throttled — `/api/mfa/verify` carries `@limiter.limit("5/minute")` (`mfa_endpoints.py:79`), and `/api/auth/login` has both a `10/minute` limit and a 5-attempt/30-minute lockout (`authentication_endpoints.py:128`, `_check_login_lockout`). `/api/mfa/disable` and `/api/mfa/backup-codes/regenerate` — the two endpoints this plan specifically added password-confirmation to — have neither. An attacker holding a valid but not-fully-trusted JWT (e.g. from a short XSS window, or a token scoped for something else) can grind the account password against these endpoints with no throttling at all.
**Fix:** Add the same `@limiter.limit(...)` decorator used on `/verify`, and/or route password verification for these two endpoints through the same `_record_login_failure`/lockout bookkeeping used by `/api/auth/login`.

### WR-03: No TOTP anti-replay — the same valid code can be reused across separate sessions

**Status:** Fixed — commit `dfdc1fda`

**File:** `backend/mfa_service.py:107-110` (`verify_totp_code`), `:354-388` (`verify_mfa_token`)
**Issue:** `verify_mfa_token`'s single-use protection is scoped to the *session token*, not the *code*. `mfa.last_used_at` is updated but never checked against the code's time-step — nothing prevents the exact same 6-digit code from being accepted again on a brand-new session (e.g. a freshly restarted login after the mandated CR/WR-04-style retry) within its ~90-second validity window (`valid_window=1`). Standard TOTP hardening tracks the last successfully-used time-step per account and rejects a repeat of that same step, specifically to close the window where a captured/observed code (shoulder-surfing, compromised MITM proxy, malicious browser extension reading the DOM) can be replayed.
**Fix:** Store the TOTP time-step (or a hash of the accepted code) alongside `mfa.last_used_at` and reject `verify_totp_code` successes that reuse the same step:
```python
step = int(datetime.now(timezone.utc).timestamp()) // 30
if step <= user["mfa"].get("last_used_step", -1):
    return {"success": False, "error": "Invalid TOTP code"}
```

### WR-04: Password-known attacker can grind the TOTP keyspace via unlimited fresh login round-trips

**Status:** Fixed — commit `9256308d`

**File:** `backend/authentication_endpoints.py:127-173`, `backend/mfa_service.py:354-388`
**Issue:** Per the review's required check, the single-use-on-first-attempt design (CR confirmed correct, scoped only to the MFA step) does **not** touch password-auth state — but that's exactly the gap: `_record_login_failure`/`_check_login_lockout` only fire on failed *password* checks. A correct-password-then-wrong-TOTP round trip is a 200 from `/api/auth/login` (session token issued) followed by a 401 from `/api/mfa/verify` — neither increments the login lockout counter. An attacker who already has the account password (phished, credential-stuffed, leaked) can therefore mint a fresh `mfa_session_token` and get exactly one TOTP guess per login, throttled only by `/api/auth/login`'s `10/minute` limit — and that limit is keyed by source IP (`rate_limiter.py`'s `get_remote_address`), so it's bypassable with multiple source IPs. Over enough distributed requests this becomes a real (if slow from any single IP) exhaustive search of the 1,000,000-value TOTP space.
**Fix:** Track "password-correct-but-MFA-failed" as its own lockout-worthy event (or fold it into the existing `_record_login_failure` counter) so repeated correct-password/wrong-TOTP round trips lock the account the same way repeated wrong passwords do.

### WR-05: Threat register claims a per-user MFA session cap that isn't implemented

**Status:** Fixed — commit `3c925ef2`

**File:** `backend/mfa_service.py:297-312` (`create_mfa_session`), plan `<threat_model>` T-64-27
**Issue:** T-64-27's disposition table states the DoS mitigation for "MFA session exhaustion" is "TTL auto-cleanup; per-user session limit." `create_mfa_session` implements the TTL half but has no cap on how many live `mfa_sessions` documents a single account can accumulate — every successful password login (however many happen in a window) inserts a new, independent session document. This is low-severity as scored (attacker still needs the correct password to create a session at all), but the SUMMARY/threat register asserts a mitigation that the code doesn't actually contain, which is worth correcting either in the code or in the register so a future auditor doesn't trust a stale claim.
**Fix:** Either implement a cap (e.g. delete older sessions for the same email before inserting a new one, or reject creation past N live sessions), or update the threat register's disposition to drop the "per-user session limit" claim.

### WR-06: MFA request models have no length bounds on user-controlled strings

**Status:** Fixed — commit `f68f120f`

**File:** `backend/mfa_endpoints.py:18-30` (`MFAVerifySetupRequest`, `MFAVerifyLoginRequest`, `MFADisableRequest`, `MFABackupCodesRegenerateRequest`)
**Issue:** None of these Pydantic models bound the length of `totp_code`, `session_token`, `code`, or `password`. This is inconsistent with `authentication_endpoints.py`'s own `LoginRequest`, which caps `password` at `max_length=1024` and `username`/`email` at `max_length=254` specifically as a boundary-input-validation measure. An oversized `password` on `/api/mfa/disable` or `/api/mfa/backup-codes/regenerate` is passed straight into `bcrypt.checkpw` with no upstream size guard. Per this project's own CLAUDE.md rule ("Validate input at system boundaries"), these public request bodies should match the existing convention.
**Fix:**
```python
class MFADisableRequest(BaseModel):
    password: str = Field(..., max_length=1024)

class MFAVerifyLoginRequest(BaseModel):
    session_token: str = Field(..., max_length=64)
    code: str = Field(..., max_length=16)
    use_backup_code: bool = False
```

### WR-07: Login's MFA branch only catches `ImportError`, not the DB errors its own `await` can now raise

**Status:** Fixed — commit `ec968860`

**File:** `backend/authentication_endpoints.py:155-173`
**Issue:**
```python
mfa = user.get("mfa", {})
if mfa.get("enabled"):
    try:
        import mfa_service
        session_token = await mfa_service.create_mfa_session(user["email"])
        return {...}
    except ImportError:
        raise HTTPException(status_code=503, detail="MFA is required for this account but the MFA service is unavailable...")
```
This plan's own Task-1 change made `create_mfa_session` an `async` function that performs a real MongoDB `insert_one` (and, on first call, `create_index`). That call can now fail with a connectivity/timeout error from the driver — a failure mode that didn't exist when the prior in-memory dict implementation was synchronous. The `except ImportError` clause does not, and was never intended to, catch that; a Mongo hiccup here will surface as an unhandled 500 (with whatever default FastAPI error body/stack trace exposure the app has configured) rather than the clean, intended 503 "MFA service is unavailable" response the comment/HTTPException imply this branch is meant to produce.
**Fix:** Broaden the except (or add a second clause) to cover the DB-call failure mode this plan introduced:
```python
except (ImportError, Exception) as e:  # or a narrower pymongo.errors.PyMongoError
    logger.error("MFA session creation failed: %s", e)
    raise HTTPException(status_code=503, detail="MFA is required for this account but the MFA service is unavailable. Contact your administrator.")
```

## Info

### IN-01: Single-use-on-first-attempt vs. backup-code peek-and-retry asymmetry is real and correctly scoped, but worth a product decision

**Status:** Not applicable — explicit product decision, not a code defect (see this finding's own "N/A" fix guidance below). Left as-is.

**File:** `backend/mfa_service.py:354-388` vs. `:315-330`
**Issue:** Confirmed as described in SUMMARY: `verify_mfa_token` (`find_one_and_delete`) burns the session on the very first TOTP attempt regardless of correctness, forcing a full `/api/auth/login` restart on a mistype, while the backup-code path (`validate_mfa_session`, a non-destructive peek) allows repeated guesses against the same session until it expires or the code is used. This asymmetry is intentional per SUMMARY and does not extend into the password-auth layer (verified — see Summary section above). No code change required; flagging only because the UX-cost tradeoff SUMMARY itself flags as "worth surfacing to product" hasn't apparently been surfaced yet.
**Fix:** N/A — product decision, not a code defect. Consider a small tolerance (e.g. allow the session to survive exactly one wrong TOTP attempt) if user complaints about mistyped codes become frequent.

### IN-02: `generate_qr_base64` swallows all exceptions silently, with no logging

**Status:** Fixed — commit `e83ce2f0`

**File:** `backend/mfa_service.py:93-104`
**Issue:**
```python
try:
    ...
    return base64.b64encode(buffer.getvalue()).decode()
except Exception:
    return ""  # Frontend falls back to showing the raw URI
```
A bare `except Exception: return ""` with no `logger.warning(...)` means a QR-rendering failure (e.g. a `qrcode`/`Pillow` dependency issue, corrupted font/image backend) is completely invisible server-side — support would only learn about it from a user reporting "the QR code didn't show up," with no log line to correlate.
**Fix:**
```python
except Exception as e:
    logger.warning("QR code generation failed, falling back to raw URI: %s", e)
    return ""
```

---

_Reviewed: 2026-08-13T08:04:48Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
