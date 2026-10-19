---
phase: 77-fail-closed-sidebar-view-gate-role-visibility
plan: 04
subsystem: auth
tags: [mfa, rbac, custom-roles, admin-tier, fail-closed]
requires:
  - phase: 77-01
    provides: rbac_service.effective_permissions over role documents
  - phase: 77-03
    provides: custom role documents that can carry admin-tier permissions
provides:
  - rbac_defaults.ADMIN_TIER_PERMISSIONS and requires_mfa(perms)
  - authentication_service.resolve_mfa_required(role, tenant_id) with a 60 s per-(tenant, role) cache
  - permission-based MFA enforcement on the HTTP and WebSocket paths
  - mfa_action on /api/auth/login and /api/auth/me for custom admin-tier role users
affects: [77-09, 77-11, 77-12, role editor UI, custom role assignment]
status: complete
plan_head_before: 61e1f9cea452a7052a3be277123933691b8944ef
plan_head_after: 7d53533296915fbf46facc1a0788a9e4da57f91e
actuals:
  tokens: 5650
  tasks: 2
  commits: 2
tech-stack:
  added: []
  patterns:
    - "admin-tier permission set defined once in rbac_defaults; MFA answer derived from effective permissions"
    - "per-worker monotonic-time TTL cache; sync path reads the cache, async path fills it"
key-files:
  created:
    - backend/tests/test_custom_role_mfa.py
  modified:
    - backend/rbac_defaults.py
    - backend/authentication_service.py
    - backend/authentication_endpoints.py
    - backend/tests/test_role_literal_guard.py
key-decisions:
  - "D-14: MFA is permission-based; the six-name role-key set is deleted"
  - "Store error: custom names require MFA, built-in names use the table answer; error answers are never cached"
  - "Sessions that already passed MFA, MFA-pending routes and agent tokens trigger no role lookup"
requirements-completed: []
---

# Phase 77 Plan 04: Permission-based MFA Summary

A custom role that carries manage:users, manage:rbac, manage:settings, manage:api_keys, control:remote_access or a platform-only permission is now held to MFA on every request path, while every built-in role keeps exactly today's MFA behaviour.

## What changed

- `rbac_defaults.ADMIN_TIER_PERMISSIONS` (the five permissions plus `PLATFORM_ONLY_PERMISSIONS`) and `requires_mfa(perms)` ("*" or any admin-tier string). The one definition (D-14).
- `authentication_service`: the name-keyed role set is gone. `MFA_ROLE_CACHE_SECONDS = 60`, `_mfa_role_cache` keyed (tenant, normalized role) -> (expiry, bool), `_clear_mfa_role_cache()`.
  - `mfa_required_for(role, tenant_id=None)` (sync, WebSocket path): built-in admin-tier -> True; fresh cache entry -> its value; otherwise False for a built-in name and True for a custom name (cold cache fails closed).
  - `resolve_mfa_required(role, tenant_id)` (async): table True -> no lookup; fresh cache -> value; else lazily imports `database.get_database` and `rbac_service.effective_permissions` (rbac_service imports this module), caches `requires_mfa(...)`. On any exception it logs a warning and returns the table answer for a built-in name, True for a custom one, uncached.
  - `_enforce_admin_mfa(payload, role, allow_mfa_pending, required)`; `verify_token` passes the sync answer; `verify_token_async` resolves only when no early exit (MFA-pending route, mfa_verified, agent token) applies.
  - `mfa_action_for(..., *, required=None)`.
- `authentication_endpoints`: `/login` and `/me` pass `required=await resolve_mfa_required(...)`. Signup is unchanged.
- `test_role_literal_guard.py`: allowlist entry and the assertion that exercised it removed, since the set no longer exists.

## Built-in role MFA table (before == after)

| Role key | MFA before | MFA after |
|----------|-----------|-----------|
| super_admin, tenant_admin, admin, itam_admin, platform_support, platform_billing | required | required |
| user, analyst, security_analyst, incident_responder, viewer, itam_user, itam_viewer | not required | not required |

Verified by `test_admin_tier_selects_exactly_the_builtin_admin_roles` and by the plan's one-line acceptance command; `test_admin_mfa_required.py` and `test_platform_roles.py` pass unchanged.

## Custom-role cases (test_custom_role_mfa.py, 31 tests)

- "Deskadmin" [manage:rbac, view:agents] in tenant-a: 403 + `X-MFA-Required: 1`; with `mfa_verified` passes; MFA-pending routes accept it; no lookup for verified sessions.
- "Helpdesk" [view:agents]: passes.
- Legacy tenant-a document named "viewer" adding manage:users: viewer needs MFA in tenant-a only.
- Store error: Deskadmin and Helpdesk -> 403; Viewer passes; Tenant Admin still 403; error answer not cached.
- Sync verify_token: cold cache refuses custom names, accepts built-in "Viewer", refuses "Tenant Admin"; after an async check cached Helpdesk as not required it passes.
- Cache: per tenant; entries expire; a role edit adding manage:users is enforced once the entry is gone.
- Login: Deskadmin user -> `mfa_action` "enroll", Helpdesk -> None. `/me`: unverified Deskadmin -> "enroll" (MFA off) or "verify" (MFA on); verified -> None; Helpdesk -> None.

## Verification

- Task 1 set (test_custom_role_mfa, test_admin_mfa_required, test_platform_roles, test_role_literal_guard, test_rbac_defaults): 197 passed. Tracer verify re-run end to end before Task 2.
- Task 2 set (test_custom_role_mfa, test_admin_mfa_required, test_login_me_permissions, test_session_revocation): 134 passed.
- Full backend suite (`TICKET_ATTACHMENT_DIR`/`FILE_SHARE_DIR` temp dirs): 3908 passed, 47 skipped, 0 failed (685 s).
- Acceptance greps: ADMIN_TIER_PERMISSIONS 2, `def requires_mfa` 1, `async def resolve_mfa_required` 1, `resolve_mfa_required(` in authentication_endpoints.py 2.

## Deviations from Plan

**1. [Rule 3 - Blocking] Removed a role-literal-guard test assertion** - Found during Task 1. `test_scanner_allows_pure_sets_and_the_reviewed_sites` asserted the allowlist entry for the deleted set; with the entry removed (as the plan requires) the assertion could only fail. Removed that single line. Files: backend/tests/test_role_literal_guard.py. Commit d0178d5c4.

**Total deviations:** 1 auto-fixed (blocking). **Impact:** none on behaviour.

## Requirements

ACC-09 is not marked complete: `requirements.ready-ids` returned 0/1 ready because other Phase 77 plans still declare it. REQUIREMENTS.md untouched.

## Costly-to-reverse note (D-14) and assumptions

- Users who hold an admin-tier custom role and never enrolled MFA are prompted to enroll on their next sign-in (accepted in D-14).
- D14-WS-CACHE-MISS: a custom-role user whose WebSocket reconnects more than 60 s after the last HTTP request is refused until the next HTTP request refreshes the cache.
- Each worker caches independently, so an edit takes up to 60 s per worker to apply.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register. T-77-13 is covered by tests on both the async and sync paths with fail-closed behaviour.

## Self-Check: PASSED

- Files exist: backend/tests/test_custom_role_mfa.py, this SUMMARY.
- Commits d0178d5c4 and 7d5353329 are ancestors of HEAD.
- Pre-existing chmod-only mode changes and unrelated working-tree changes were not staged (`core.fileMode=false`, explicit paths).
