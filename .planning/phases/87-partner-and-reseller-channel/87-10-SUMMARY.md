---
phase: 87-partner-and-reseller-channel
plan: 10
subsystem: api
tags: [fastapi, mongodb, partner-channel, seat-pool, licensing, drift-test]

requires:
  - phase: 87-01
    provides: tenant_docs.build_tenant_doc / ensure_tenant_extras, partner organization shape
  - phase: 87-03
    provides: partner_pool.change_allotment, release, PartnerError, pool_expired
provides:
  - create_tenant built on tenant_docs.build_tenant_doc (same stored fields, no partnerId)
  - pool-aware PATCH /api/tenants/{id}/license for partner customers (409 pool_full with free)
  - customer deletion releases its seats; partner with customers refused with 409
  - pending_agents.approve raise draws from the partner pool (409 no_free_seat when it lacks room)
  - license_rules.hold_reason treats the partner's pool expiry as the customer's licence expiry (D-08)
  - MSSP tenant list, overview and alert-feed name map exclude partner organizations
  - drift test: only allowlisted modules write license.maxAgents
affects: [87-11, 87-12, 87-13, 87-14]

actuals:
  tokens: 6400
  tasks: 3
  commits: 6
plan_head_before: d3b92c1b06c39bbe6674c05b9a2155a1951b8614
plan_head_after: 9be8871d34783058decbf89cb7aed4d8590de493

tech-stack:
  added: []
  patterns:
    - "Every writer of a partner customer's seats goes through partner_pool.change_allotment; Platform staff pass enforce_used_floor=False, require_active=False (the pool total binds, suspension and expiry do not)"
    - "A source-scan drift test (AST dict keys) with a tmp_path negative control guards the seat-writer allowlist"
    - "hold_reason does one extra find_one of the customer's partner only when partnerId is set"

key-files:
  created:
    - backend/tests/test_partner_license_writers.py
    - backend/tests/test_partner_expiry.py
  modified:
    - backend/tenant_endpoints.py
    - backend/partner_pool.py
    - backend/pending_agents.py
    - backend/license_rules.py
    - backend/mssp_endpoints.py

key-decisions:
  - "Platform Owner / Platform Billing raising a partner customer's seats must find room in the pool but ignore the partner's suspension and pool expiry (A-87-PLATFORM-RAISE)"
  - "The drift scan reads dict keys through the AST rather than regexing text, and ignores a literal 0 (the partner organization carries no seats of its own, partner_platform_service.py)"
  - "The drift scan reads only the top level of backend/ (modules are flat; the folder holds virtualenvs that must not be walked) and checks found-minus-allowlist is empty plus that the four known writers are still seen, instead of strict equality, because the sign-up path writes a top-level maxAgents, not license.maxAgents"
  - "MSSP alert feed filters only the tenant-name map, as the plan says; an alert whose tenantId is a partner id falls back to the id and never shows the partner's name"

patterns-established:
  - "_NOT_PARTNER = {'type': {'$ne': 'partner'}} in mssp_endpoints for every unfiltered tenants listing"

requirements-completed: [PART-03, PART-04, PART-07, PART-02]

coverage:
  - id: D1
    description: "create_tenant stores exactly the pre-change field set (no partnerId) through tenant_docs.build_tenant_doc"
    requirement: PART-02
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_license_writers.py#test_create_tenant_uses_the_shared_builder_and_stores_the_same_fields"
        status: pass
    human_judgment: false
  - id: D2
    description: "PATCH maxAgents on a partner customer claims or returns pool seats; past the pool answers 409 pool_full with free and changes nothing; below the seats used succeeds for the Super Admin; a raise ignores suspension and expiry but not the pool total; reclaim-window-only PATCH never touches the pool; direct customers unchanged"
    requirement: PART-03
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_license_writers.py#test_patch_seats_on_a_partner_customer_claims_the_pool"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_license_writers.py#test_patch_past_the_pool_answers_pool_full_and_changes_nothing"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_license_writers.py#test_patch_below_the_seats_used_succeeds_and_returns_the_seats"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_license_writers.py#test_a_raise_ignores_the_partners_suspension_and_expiry_but_not_the_pool_total"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_license_writers.py#test_patching_only_the_reclaim_window_never_touches_the_pool"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_license_writers.py#test_a_direct_customer_is_patched_as_before"
        status: pass
    human_judgment: false
  - id: D3
    description: "Deleting a partner customer returns its seats; deleting a partner with customers answers 409 and deletes nothing; a partner without customers can be deleted"
    requirement: PART-07
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_license_writers.py#test_deleting_a_partner_customer_returns_its_seats_to_the_pool"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_license_writers.py#test_deleting_a_partner_with_customers_is_refused_and_deletes_nothing"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_license_writers.py#test_deleting_a_partner_without_customers_works"
        status: pass
    human_judgment: false
  - id: D4
    description: "Approve-and-raise on a partner customer draws from the pool (409 no_free_seat with the licence when it lacks room, nothing changed); direct customers keep the $inc path"
    requirement: PART-03
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_license_writers.py#test_approve_with_a_raise_claims_the_extra_seats_from_the_pool"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_license_writers.py#test_approve_with_a_raise_the_pool_cannot_fit_is_refused_and_changes_nothing"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_license_writers.py#test_approve_with_a_raise_ignores_the_partners_suspension"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_license_writers.py#test_approve_with_a_raise_on_a_direct_customer_is_unchanged"
        status: pass
    human_judgment: false
  - id: D5
    description: "hold_reason returns license_expired for a partner customer once the partner pool has expired (even when the customer's own licence has no expiry), None before, None for direct customers; already enrolled agents keep status and seats"
    requirement: PART-04
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_expiry.py"
        status: pass
    human_judgment: false
  - id: D6
    description: "MSSP tenant list, overview and aggregated alerts never show a partner organization"
    requirement: PART-02
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_license_writers.py#test_mssp_listings_never_show_a_partner_organization"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_license_writers.py#test_mssp_alert_feed_does_not_resolve_a_partner_name"
        status: pass
    human_judgment: false
  - id: D7
    description: "A new module writing license.maxAgents outside the allowlist fails a test; the scanner is proved on scratch files and cannot go blind"
    requirement: PART-03
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_license_writers.py#test_only_the_allowlisted_modules_write_license_max_agents"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_license_writers.py#test_the_drift_scanner_catches_a_new_writer_and_ignores_a_zero_literal"
        status: pass
    human_judgment: false
  - id: D8
    description: "The HTTP layer of these routes (route functions are called directly) and live-database behavior"
    human_judgment: true
    rationale: "Tests call route functions with a TokenData and a private MongoDB; no request goes through the running app or the live database"

duration: about 1 h across two sessions (a usage limit cut the first session off after Task 2; the first start time was not recorded)
completed: 2026-11-03
status: complete
---

# Phase 87 Plan 10: Every Other Seat Writer Respects the Partner Pool Summary

**Licence PATCH, approve-and-raise and customer deletion now move seats through the partner pool, a partner's pool expiry holds its customers' new machines like an expired licence, MSSP lists skip partner organizations, and an AST drift test fails if any other module starts writing `license.maxAgents`.**

## Performance

- **Duration:** about 1 h (two sessions; see frontmatter)
- **Tasks:** 3 (6 commits, RED then GREEN per task)
- **Files:** 7 (2 created, 5 modified)

## Accomplishments

- **Task 1** (`create_tenant`, licence PATCH, deletion). `create_tenant` builds its document with `tenant_docs.build_tenant_doc` and `ensure_tenant_extras`; stored keys equal the old set and carry no `partnerId`. `update_tenant_license` reads the tenant's `partnerId`; when it is set and `maxAgents` was sent, `partner_pool.change_allotment(enforce_used_floor=False, require_active=False)` runs first and `update_license` receives `max_agents=None`; a `PartnerError` returns `partner_store.error_response`. `delete_tenant` refuses a partner that still has `{"partnerId": id}` customers with 409 "Move this partner's customers first." and releases a deleted customer's seats to its partner.
- **Task 2** (approve-and-raise, pool expiry). `pending_agents.approve` with `raise_limit_by` on a partner customer calls `change_allotment` for current + raise; `pool_full` becomes `DecisionError(409, "no_free_seat: ...")` carrying the licence summary; direct customers keep the `$inc`. `license_rules.hold_reason` finds the customer's partner (only when `partnerId` is set) and returns `license_expired` once `partner.expiresAt` has passed, even when the customer's own licence has no expiry. Nothing re-checks enrolled agents, so they keep status and seats. Module docstring gains the D-08 sentence.
- **Task 3** (MSSP lists, drift guard). `_NOT_PARTNER = {"type": {"$ne": "partner"}}` applies to the three formerly unfiltered `tenants.find` calls in `mssp_endpoints.py` (list, overview, alert-feed name map). The drift test scans `backend/*.py` by AST for a `"license.maxAgents"` key or a `"license": {"maxAgents": ...}` literal and asserts every hit is in `licensing`, `partner_pool`, `tenant_docs`, `pending_agents` or `authentication_endpoints`; a `tmp_path` negative control proves the scanner catches new writers.

## Task Commits

1. Task 1: RED `6ea29f362`, GREEN `9f9064ca8`
2. Task 2: RED `32c9eb1f1`, GREEN `63b5a73c8`
3. Task 3: RED `424e63c00`, GREEN `9be8871d3`

## TDD Gate Compliance

Each task has a `test(87-10)` commit before its `feat(87-10)` commit. Task 3's RED run had two failures (`test_mssp_listings_never_show_a_partner_organization` returned `['c1','c2','p1']`; `test_mssp_alert_feed_does_not_resolve_a_partner_name` resolved the partner's name); the three drift-scan tests passed at once, because the existing backend already complied and the scanner is a guard, not driven code. They lock behaviour rather than drive new code. RED evidence for Tasks 1 and 2 was produced by the first session and is in commits `6ea29f362` and `32c9eb1f1`; this session did not re-run it. The pytest format has no `check tdd-red-evidence` adapter, so the classifier was not run. No REFACTOR commits.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] A refused claim that did not require an active partner was reported as partner_suspended**
- **Found during:** Task 1 (first session)
- **Issue:** `partner_pool._claim_refusal` always checked the partner's status first, so a Platform raise (`require_active=False`) refused for lack of room on a suspended partner answered `partner_suspended` instead of `pool_full`.
- **Fix:** `_claim_refusal(db, partner_id, require_active)` checks suspension only when the claim demanded an active partner.
- **Files modified:** backend/partner_pool.py (not in the plan's `files_modified`)
- **Commit:** `9f9064ca8`

**2. [Rule 3 - Blocking] Drift scan could not walk backend/ or read every file**
- **Found during:** Task 3
- **Issue:** `os.walk` over `backend/` entered virtualenv-like folders (about 94,000 .py files, the test never finished) and one file was not UTF-8.
- **Fix:** scan only the top level of `backend/` (modules are flat), read with `errors="replace"`, skip `database_migrations.py`.
- **Files modified:** backend/tests/test_partner_license_writers.py
- **Commit:** `424e63c00`

### Other differences from the plan text

- The plan's allowlist check is "equals"; the test asserts found-minus-allowlist is empty and that the four known writers are still found. Sign-up (`authentication_endpoints.py`) writes a top-level `maxAgents`, not `license.maxAgents`, so the scanner does not see it and strict equality would fail.
- The scanner ignores a literal `0` for `license.maxAgents`: `partner_platform_service.py` creates the partner organization with `{"license": {"maxAgents": 0}}` (it carries no seats), which grants nothing.
- The plan's MSSP test says no entry for the partner; the alert feed only builds a name map, so the added second test pins that a partner id's name is never resolved.

**Total deviations:** 2 auto-fixed, 3 minor differences. **Impact:** none on scope.

## Issues Encountered

`backend/tenant_endpoints.py` still carries the user's 11-line uncommitted hunk (the file was dirty before this plan); only this plan's hunks were committed.

## Verification

- Task 1 command (`test_partner_license_writers.py` + `test_tenant_license_api.py`): 22 passed, no skips.
- Task 2 command (`test_partner_expiry.py`, `test_partner_license_writers.py`, `test_licensing.py`, `test_pending_agents.py`): 53 passed, no skips.
- Task 3 command (`test_partner_license_writers.py`): 18 passed, no skips.
- Acceptance greps: `tenants.find({})` in mssp_endpoints.py = 0; `tmp_path` in the writers test = 7.
- Plan-level catalogue run (`test_catalogue_slice_billing_identity.py`, `test_catalogue_slice_settings_ops.py`): 18 passed in 8m46s, no skips (the real-app route walk is slow).
- Private mongod 27998 only; the live database, backend service and UI were not touched; nothing pushed or deployed.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register. T-87-31 (licence PATCH and approve-raise via `change_allotment`; drift test forbids new writers), T-87-32 (409 on a partner with customers; customer deletion releases seats), T-87-33 (`hold_reason` returns `license_expired` from the partner's expiry), T-87-34 (`type: partner` excluded from the three MSSP listings) are each exercised by a test.

## Next Phase Readiness

Every known path that changes a partner customer's seats now respects the pool. Later plans that add a seat writer must route through `partner_pool.change_allotment` or the drift test fails.

## Self-Check: PASSED

- Created: backend/tests/test_partner_license_writers.py and backend/tests/test_partner_expiry.py exist.
- Commits 6ea29f362, 9f9064ca8, 32c9eb1f1, 63b5a73c8, 424e63c00, 9be8871d3 are on HEAD.

