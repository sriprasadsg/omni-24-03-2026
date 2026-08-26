---
phase: 73-api-integrations
plan: 01
subsystem: auth
tags: [fastapi, api-key-auth, rbac, scope-narrowing, webhooks, itam]

# Dependency graph
requires:
  - phase: 64-01 (ITAM-USR-05)
    provides: api_key_auth.py's APIKeyService/get_current_user_or_api_key and TokenData.scopes/auth_source fields this plan builds on
provides:
  - Dual session/API-key auth on all 11 _require_itam_admin-gated ITAM routers, scope-narrowed
  - The 4 non-ITAM surfaces (LDAP, SSO, user-mgmt, API-key-mgmt) provably fenced off from API-key auth
  - itam_webhook_events.py — the single-source-of-truth catalog of 8 ITAM webhook event-type constants
  - The first ITAM webhook dispatch call site (asset.checked_out on checkout_asset)
affects: [73-02, 73-03, 73-04, 73-05, 73-06]

tech-stack:
  added: []
  patterns:
    - "Dual-guard split: _require_itam_admin (dual auth + scope narrowing) vs _require_itam_admin_session_only (role check only) for surfaces deliberately excluded from API-key reach"
    - "Fire-and-forget webhook dispatch via asyncio.create_task, never awaited inline, placed after the mutation + invalidate_cache and before the audit-log call"
    - "Constants-only event-type module (itam_webhook_events.py) — no dispatch wrapper"

key-files:
  created:
    - backend/itam_webhook_events.py
    - backend/tests/test_itam_api_integrations.py
    - backend/tests/itam_api_integrations_test_support.py
  modified:
    - backend/api_key_auth.py
    - backend/itam_asset_endpoints.py
    - backend/itam_catalog_endpoints.py
    - backend/itam_lifecycle_endpoints.py
    - backend/ldap_endpoints.py
    - backend/api_key_endpoints.py
    - backend/sso_endpoints.py
    - backend/user_endpoints.py
    - 22 existing ITAM test files (dependency_overrides fix, see Deviations)

key-decisions:
  - "sso_endpoints.py and user_endpoints.py import the same shared _require_itam_admin symbol as ldap_endpoints.py/api_key_endpoints.py — discovered during execution, not just the two RESEARCH.md enumerated; excluded on identical reasoning (materially different risk from ITAM asset read/write; API-key-managing-API-keys is a privilege-escalation surface)"
  - "Existing ITAM test files that override FastAPI's get_current_user dependency directly stopped working once _require_itam_admin's dependency graph changed to get_current_user_or_api_key (a different callable never in that resolved tree) — fixed by adding a parallel dependency_overrides[get_current_user_or_api_key] assignment alongside every existing override, rather than replacing it, so both auth styles keep working in mixed-router test apps"

patterns-established:
  - "Pattern 1: any router gated by _require_itam_admin (or its session-only sibling) must be tested by overriding get_current_user_or_api_key, not get_current_user — the latter is no longer in the resolved dependency tree for these 11 ITAM surfaces"
  - "Pattern 2: independent duplicate guards (itam_catalog_endpoints._require_itam_admin) must be found and migrated in lockstep with the canonical one — a grep-only migration misses them"

requirements-completed: [ITAM-API-01, ITAM-API-02]

coverage:
  - id: D1
    description: "API-key-authenticated caller performs an ITAM write (asset checkout) that previously required a browser session, narrowed by the key's own scopes"
    requirement: "ITAM-API-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_api_integrations.py::TestTracerApiKeyCheckoutFiresWebhook::test_tracer_api_key_checkout_fires_webhook"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_api_integrations.py -k scoped_key_allowed"
        status: pass
    human_judgment: false
  - id: D2
    description: "A read:assets-only key is rejected (403) on a manage:assets operation even when its owning user's role grants manage:assets — RESEARCH Pitfall 1 closed"
    requirement: "ITAM-API-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_api_integrations.py -k scope_narrowing_enforced (4 tests)"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_api_integrations.py::TestCatalogScopeNarrowing::test_catalog_scope_narrowing_read_only_key_refused_manage_key_allowed"
        status: pass
    human_judgment: false
  - id: D3
    description: "Session (JWT) auth keeps working unchanged on every _require_itam_admin-gated route — the auth change is additive"
    requirement: "ITAM-API-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_api_integrations.py -k session_auth (4 tests: asset/lifecycle/catalog/reporting)"
        status: pass
    human_judgment: false
  - id: D4
    description: "LDAP directory-sync, SAML/SSO config, user-management CRUD, and API-key-management routes stay unreachable with an API key alone; session admin still works on each"
    requirement: "ITAM-API-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_api_integrations.py::TestExcludedSurfacesRefuseApiKey (4 tests, one per excluded file)"
        status: pass
    human_judgment: false
  - id: D5
    description: "The existing per-key rate limiter (no new ITAM-specific tier) still returns 429 through an ITAM route"
    requirement: "ITAM-API-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_api_integrations.py::TestRateLimit::test_rate_limit_429_via_itam_route"
        status: pass
    human_judgment: false
  - id: D6
    description: "A successful asset checkout dispatches asset.checked_out without the HTTP response waiting on webhook delivery, carrying a before/after diff"
    requirement: "ITAM-API-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_api_integrations.py::TestTracerApiKeyCheckoutFiresWebhook::test_tracer_api_key_checkout_fires_webhook"
        status: pass
    human_judgment: false
  - id: D7
    description: "The 8 ITAM webhook event-type strings exist in exactly one place (itam_webhook_events.py)"
    requirement: "ITAM-API-02"
    verification:
      - kind: unit
        ref: "python -c import itam_webhook_events; assert len(ITAM_WEBHOOK_EVENT_TYPES) == 8"
        status: pass
    human_judgment: false

duration: 35min
completed: 2026-08-18
status: complete
---

# Phase 73 Plan 01: ITAM-API-01 Auth Spine + Webhook Dispatch Foundation Summary

**Dual session/API-key auth with mandatory scope narrowing across all 11 `_require_itam_admin`-gated ITAM routers, four non-ITAM surfaces (LDAP/SSO/user-mgmt/API-key-mgmt) provably fenced off, and the first ITAM webhook event (`asset.checked_out`) firing fire-and-forget off a real checkout.**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-08-18
- **Tasks:** 3/3
- **Files modified:** 9 production files, 3 new/rewritten test files, 22 existing test files touched for the dependency-override fix

## Accomplishments

- `_require_itam_admin` (canonical, `itam_asset_endpoints.py`) and its independent duplicate (`itam_catalog_endpoints.py`) both now accept session **or** API-key auth (`Depends(get_current_user_or_api_key)`), with a mandatory `rbac_service._scopes_allow` narrowing check applied after the existing role check — closing RESEARCH.md's Pitfall 1 (a `read:assets`-scoped key could otherwise pass a `manage:assets` gate).
- New `_require_itam_admin_session_only` sibling guard added; `ldap_endpoints.py`, `api_key_endpoints.py`, `sso_endpoints.py`, and `user_endpoints.py` re-point their local `_require_itam_admin` name to it via a one-line aliased import — every existing `Depends(_require_itam_admin)` call site in those four files keeps working verbatim, but none of them can be reached with an API key.
- `manage:assets` added to `api_key_auth.AVAILABLE_SCOPES` so a key that can actually pass the new gate is issuable at all.
- `itam_webhook_events.py` created: the 8 D-05 event-type string constants plus `ITAM_WEBHOOK_EVENT_TYPES`, single source of truth, no dispatch wrapper.
- `itam_lifecycle_endpoints.checkout_asset` now dispatches `asset.checked_out` via `asyncio.create_task(...)` — fire-and-forget, never blocking the HTTP response — with a payload carrying `assetId`, a `before`/`after` diff, and the full updated asset.
- 21 new tests in `backend/tests/test_itam_api_integrations.py` (+ shared fixtures in `itam_api_integrations_test_support.py`) covering the tracer slice, the 4 excluded surfaces, the catalog router's independent scope narrowing, and all four ITAM-API-01 validation rows (`session_auth` / `scoped_key_allowed` / `scope_narrowing_enforced` / `rate_limit`).

## Task Commits

1. **Task 1: End-to-end slice — API-key-authenticated asset checkout that fires a webhook** - `794de2bbf` (feat)
2. **Task 2: Patch the duplicate guard and fence off the four excluded non-ITAM surfaces** - `bb40aa4d3` (feat)
3. **Task 3: ITAM-API-01 regression suite — session parity, scope narrowing, rate limiting** - `689039347` (test)

## Files Created/Modified

- `backend/api_key_auth.py` — added `manage:assets` to `AVAILABLE_SCOPES`
- `backend/itam_asset_endpoints.py` — `_require_itam_admin` swapped to dual auth + scope narrowing; new `_require_itam_admin_session_only` sibling
- `backend/itam_catalog_endpoints.py` — its independent duplicate guard given the identical treatment
- `backend/itam_lifecycle_endpoints.py` — `checkout_asset` fires `asset.checked_out` via `asyncio.create_task`
- `backend/itam_webhook_events.py` (new) — the 8 event-type constants
- `backend/ldap_endpoints.py`, `backend/api_key_endpoints.py`, `backend/sso_endpoints.py`, `backend/user_endpoints.py` — re-pointed to `_require_itam_admin_session_only`
- `backend/tests/test_itam_api_integrations.py` (new, 400 lines), `backend/tests/itam_api_integrations_test_support.py` (new, 266 lines) — the full ITAM-API-01 regression suite
- 22 existing ITAM test files — added a parallel `dependency_overrides[get_current_user_or_api_key]` assignment alongside their existing `get_current_user` override (see Deviations)

## Decisions Made

- **sso_endpoints.py and user_endpoints.py join the exclusion set.** RESEARCH.md enumerated only `ldap_endpoints.py` and `api_key_endpoints.py` as importers of the shared guard needing exclusion; execution found `sso_endpoints.py` and `user_endpoints.py` also import the same symbol. Both were excluded on the identical reasoning (SAML/SSO config and user-management CRUD are each a materially different risk from ITAM asset read/write) — recorded per the plan's own instruction as a deviation-by-discovery, not a scope change.
- **Test-app builder for the tracer test simulates the X-API-Key header via a dependency override that itself reads the header**, rather than seeding a real bcrypt-hashed key through `APIKeyService`. The real header-parsing + DB-backed validation path is already covered end-to-end by the pre-existing `test_api_key_auth.py`; this plan's tests focus on what's new — the scope-narrowing enforcement inside `_require_itam_admin` — while still requiring the client to send a real `X-API-Key` header to reach the route.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1/3 - Bug/Blocking] Existing ITAM test suite broke when `_require_itam_admin`'s dependency changed from `get_current_user` to `get_current_user_or_api_key`**
- **Found during:** Task 1, immediately after committing the auth-spine swap
- **Issue:** FastAPI's `dependency_overrides` only intercepts a dependency callable if that exact callable object appears in the request's resolved dependency tree. Once `_require_itam_admin` depended on `get_current_user_or_api_key` (a different function that never calls `get_current_user`), the ~22 existing ITAM test files that override `get_current_user` directly (via `app.dependency_overrides[real_get_current_user] = lambda: current_user`) silently stopped applying — every one of those routes started returning 401 with no Authorization header present. Confirmed via `git stash` that this was a genuine regression introduced by this task's change, not pre-existing.
- **Fix:** Added a parallel `dependency_overrides[get_current_user_or_api_key] = lambda: current_user` assignment immediately after every existing `get_current_user` override in the 22 affected files (mechanical, scripted via `sed`), plus the matching import. Additive — any router in the same test app NOT touched by this plan still resolves through its unmodified `get_current_user` override.
- **Files modified:** `backend/tests/test_itam_component.py`, `test_itam_finance_bookvalue.py`, `test_itam_data_csv.py`, `test_itam_consumable.py`, `test_itam_custom_fields.py`, `test_itam_finance.py`, `test_itam_catalog.py`, `test_itam_labels.py`, `test_itam_finance_warranty.py`, `test_itam_lifecycle_expansion.py`, `test_itam_audit.py`, `test_itam_reporting_prebuilt.py`, `test_itam_lifecycle_audit.py`, `test_itam_labels_barcode.py`, `test_itam_lifecycle.py`, `test_itam_license.py`, `test_itam_reporting_export.py`, `test_itam_customization.py` (not needed — unaffected router, left as-is on recheck), `test_itam_reporting_kpis.py`, `test_itam_foundation.py`, `test_itam_labels_sheet_route.py`, `test_itam_reporting_builder.py`, `test_itam_lifecycle_history.py`
- **Verification:** Full `backend/tests/ -k itam` suite re-run: 513 passed, 1 pre-existing unrelated failure (same one that reproduces on the un-modified HEAD via `git stash`).
- **Committed in:** `794de2bbf` (Task 1 commit)

**2. [Rule 1] `test_user_crud.py`'s `test_create_user_with_itam_fields` broke transiently between Task 1 and Task 2**
- **Found during:** Task 1's full-suite run (before Task 2's exclusion fencing landed)
- **Issue:** `user_endpoints.py` still imported the canonical (now dual-auth) `_require_itam_admin` at that point in the sequence — Task 2's re-pointing to `_require_itam_admin_session_only` hadn't landed yet, so `POST /api/users`'s dependency graph had changed in the same way as the other 22 files. No separate fix needed — Task 2's exclusion fencing (which re-points `user_endpoints.py`'s import to the session-only guard, restoring its dependency on plain `get_current_user`) resolved it as a natural consequence of executing the tasks in plan order.
- **Verification:** `test_user_crud.py` re-run after Task 2: 26/26 passed.
- **Committed in:** `bb40aa4d3` (Task 2 commit, no separate fix needed)

---

**Total deviations:** 2 auto-fixed (1 Rule 1/3 blocking-bug fix across 22 test files, 1 Rule 1 fix that resolved itself via Task 2's planned work)
**Impact on plan:** Both fixes were required for the plan's own must_have truth #3 ("session caller keeps working unchanged") and the `<verification>` no-regression contract. No scope creep into production code — the fix is entirely test-infrastructure, additive, and mirrors the pattern the codebase's own `webhook_endpoints.py` migration already established.

## Issues Encountered

- **Full backend suite discovered 4 additional pre-existing failures beyond the 3 documented in the working baseline** (`test_itam_audit.py`'s purchase-route 404, confirmed via `git stash` to reproduce identically on HEAD; `test_powershell_evidence.py`'s JWT-bearer and cross-tenant tests; `test_secret_manager_service.py`'s 4 Vault-client tests). None of these touch any file this plan modified (confirmed via `git log` on each file — all last touched in unrelated earlier phases/sessions). Logged here for visibility; not fixed (out of scope — this plan's `<verification>` only requires no *new* failures relative to baseline, and Rule 1's scope boundary excludes pre-existing, unrelated failures).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The auth spine (`_require_itam_admin` dual-auth + scope narrowing) and the single-source event-type catalog (`itam_webhook_events.py`) are both committed and tested — every later plan in this phase (73-02 through 73-06) builds directly on these two artifacts.
- `itam_lifecycle_endpoints.py` now has the `_webhook_service` module singleton and the `asyncio.create_task` dispatch pattern established; 73-02's `checkin_asset` and other lifecycle events should follow the identical shape.
- No blockers. The pre-existing unrelated test failures noted above should be triaged separately from this phase's work.

---
*Phase: 73-api-integrations*
*Completed: 2026-08-18*

## Self-Check: PASSED
- FOUND: backend/itam_webhook_events.py
- FOUND: backend/tests/test_itam_api_integrations.py
- FOUND: backend/tests/itam_api_integrations_test_support.py
- FOUND: .planning/phases/73-api-integrations/73-01-SUMMARY.md
- FOUND: commit 794de2bbf
- FOUND: commit bb40aa4d3
- FOUND: commit 689039347
