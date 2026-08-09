---
phase: 34-passkey-and-webauthn-authentication
reviewed: 2026-07-27T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - backend/passkey_service.py
  - backend/passkey_endpoints.py
findings:
  critical: 1
  warning: 1
  info: 1
  total: 3
status: issues_found
---

# Phase 34: Code Review Report

**Reviewed:** 2026-07-27
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

WebAuthn ceremony hygiene is good: one-shot TTL challenge store (pop-then-expiry-check gives replay protection), sign-count updates, credential-id normalization (hex at rest / base64url on the wire), clean `ValueError → 401/400` mapping, and rate-limited login. The serious problem is that the endpoints key registration, challenge storage, and credential lookup on `current_user.tenant_id` instead of the authenticated user's id.

## Critical Issues

### CR-01: Passkey identity keyed on tenant_id, not user id

**File:** `backend/passkey_endpoints.py:44-48, 63-68, 149-151, 175-177`; `backend/passkey_service.py:73, 116-119`
**Issue:** Registration uses `user_id=current_user.tenant_id` as the WebAuthn user handle and challenge key; storage/lookup/delete use `{"id": current_user.tenant_id}`. In any tenant with more than one user this conflates tenant and user identity:
- The registration challenge is stored under `(tenant_id, "registration")`, so two users in the same tenant registering concurrently clobber each other's challenge.
- Credentials are pushed to / listed from / deleted from the user document whose `id` equals the tenant_id — potentially a different user than the caller, or none (then `list_passkeys` 404s for everyone whose `id != tenant_id`).
- This breaks per-user credential isolation and passkey management.
`username` is available on the token and is what should key these operations.
**Fix:** Use the authenticated user's own id (e.g. look up by `current_user.username`, or add a real user-id claim to `TokenData`) for the WebAuthn user handle, challenge key, and all `users` document filters — not `tenant_id`.

## Warnings

### WR-01: Concurrent registration challenge collision

**File:** `backend/passkey_service.py:23-26, 73`
**Issue:** Even once CR-01 is fixed, the in-memory `_webauthn_challenges` store keyed by `(user_key, "registration")` overwrites on a second concurrent registration for the same key, and is per-process (won't work across multiple workers). For multi-worker deployments, challenges must live in shared storage (the MFA challenge-store pattern this phase says it reused).
**Fix:** Back the challenge store with the shared store used by `mfa_service` rather than a module-level dict.

## Info

### IN-01: Dead parameters
**File:** `backend/passkey_service.py:89, 133` — `verify_and_store_registration` and `verify_authentication` accept `db` and `users_collection` args that are always passed `None` and never used (the functions import `mongodb` directly). Remove to avoid confusion.

---

_Reviewed: 2026-07-27_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
