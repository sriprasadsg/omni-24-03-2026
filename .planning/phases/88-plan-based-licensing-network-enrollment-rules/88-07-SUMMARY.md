---
phase: 88-plan-based-licensing-network-enrollment-rules
plan: 07
subsystem: licensing
tags: [cross-tenant, enrollment, hardware-identity, pending, mongodb]

requires:
  - phase: 88-05
    provides: hold_reasons, license_rules.hold_reason rule order, the observed client address passed into register
  - phase: 88-01
    provides: the shared _enrollment_harness
provides:
  - cross_tenant (live_owner, silent_copies, hold_detail, alert_platform_hold, retire_copy, retire_silent_copies, ensure_indexes, LIVE_WINDOW, MOVED_REASONS)
  - seat_identity.hardware_match_other_tenants_filter and seat_identity.seen_within
  - cross_tenant_duplicate hold (third rule in license_rules.hold_reason, license_rules.returning_hold_reason)
  - Pending field crossTenant (platform-only detail), agent fields replacedReason and movedAt
  - audit events agent.moved_out (old tenant) and agent.moved (platform)
affects: [88-09, 88-11, 88-14, 88-16]

actuals:
  tokens: 9500
  tasks: 2
  commits: 4
plan_head_before: af4bb90a8815cd86e0001a6df7ccaa45e1e41579
plan_head_after: f5b447159dd94c1824a79cc5b6518c1f307ad8b8

tech-stack:
  added: []
  patterns:
    - "every cross-tenant read goes through getattr(db, '_db', db) with an explicit filter built by a pure seat_identity helper; the request wrapper never sees it"
    - "retirement is one conditional update (status not in NON_SEAT_STATUSES) so only the call that flips it releases the seat, revokes tokens and writes ledger entries"
    - "tenant-facing text is one fixed unnamed sentence; the other organization lives only in the platform feed, the platform ledger and the Pending record's crossTenant field"

key-files:
  created:
    - backend/cross_tenant.py
    - backend/tests/test_cross_tenant_duplicate.py
  modified:
    - backend/seat_identity.py
    - backend/hold_reasons.py
    - backend/license_rules.py
    - backend/agent_registry_endpoints.py

key-decisions:
  - "hardware_match_other_tenants_filter takes the seat-holding statuses as a parameter (seat_identity stays pure); with none given it omits the status clause"
  - "live_owner reads up to 50 matches and picks the most recently seen one inside the 24-hour window in Python, so lastSeen stays an ISO string"
  - "A failure to release a seat or revoke tokens while retiring a copy propagates to retire_silent_copies, which logs it and carries on; only the ledger and notice writes are swallowed in place"
  - "The platform notice for a hold and for a move are separate feed items with no audience tag, so no tenant feed or socket carries them"

requirements-completed: [LIC-06]

coverage:
  - id: D1
    description: "A machine whose serial or SMBIOS UUID belongs to a seat-holding agent in another tenant seen in the last 24 hours is held Pending cross_tenant_duplicate (new machine and returning agent needing a seat, platform organization included); old builds get a 403 starting cross_tenant_duplicate:"
    requirement: LIC-06
    verification:
      - kind: integration
        ref: "backend/tests/test_cross_tenant_duplicate.py (test_a_machine_live_in_another_organization_is_held_and_neither_name_leaks, test_an_old_agent_build_is_refused_without_a_name, test_a_returning_agent_that_needs_a_seat_is_held_while_the_machine_is_live_elsewhere, test_the_platform_organization_is_held_too)"
        status: pass
    human_judgment: false
  - id: D2
    description: "A silent copy (30 h), a seat-less copy, a same-tenant copy, a MAC alone, nothing, and OEM placeholder serials never cause the hold; serial and UUID are compared after normalization"
    requirement: LIC-06
    verification:
      - kind: integration
        ref: "backend/tests/test_cross_tenant_duplicate.py (test_no_live_owner_for_a_silent_seatless_or_same_tenant_copy x7, test_hardware_without_a_serial_or_uuid_never_matches, test_an_oem_placeholder_serial_never_matches_across_tenants, test_a_live_seat_holder_elsewhere_is_found_after_normalizing_the_serial, test_the_uuid_finds_a_copy_whose_serial_differs, test_a_mac_alone_is_never_a_cross_tenant_duplicate, test_a_copy_that_holds_no_seat_does_not_hold_the_new_enrollment)"
        status: pass
    human_judgment: false
  - id: D3
    description: "While held, tenant A gets no notice and no change; B's feed and refusal text carry the fixed unnamed sentence with neither A's name, id, agent id nor hostname; the platform feed alert and the crossTenant field name both"
    requirement: LIC-06
    verification:
      - kind: integration
        ref: "backend/tests/test_cross_tenant_duplicate.py (test_a_machine_live_in_another_organization_is_held_and_neither_name_leaks, test_an_old_agent_build_is_refused_without_a_name)"
        status: pass
    human_judgment: false
  - id: D4
    description: "A silent copy elsewhere is retired by the new enrollment: Replaced, replacedReason moved_silent, no replacedBy, seat released, tokens revoked, platform notice and platform-ledger entry naming both, and an old-tenant ledger entry naming neither; a second retirement changes nothing"
    requirement: LIC-06
    verification:
      - kind: integration
        ref: "backend/tests/test_cross_tenant_duplicate.py (test_retiring_a_copy_frees_its_seat_ends_its_tokens_and_keeps_the_names_apart, test_a_copy_that_lost_its_seat_meanwhile_is_not_retired_twice, test_retire_silent_copies_retires_each_silent_copy_and_no_live_one, test_a_silent_copy_elsewhere_is_retired_by_the_new_enrollment)"
        status: pass
    human_judgment: false
  - id: D5
    description: "The hold runs before the allowlist and network rules, so a duplicate on a new network teaches no network; two sparse indexes serve the lookup (explain shows IXSCAN, no COLLSCAN)"
    requirement: LIC-06
    verification:
      - kind: integration
        ref: "backend/tests/test_cross_tenant_duplicate.py (test_the_duplicate_rule_runs_before_the_network_rule_and_teaches_nothing, test_the_two_sparse_indexes_serve_the_lookup)"
        status: pass
    human_judgment: false

duration: 4min
completed: 2026-11-11
status: complete
---

# Phase 88 Plan 07: Cross-tenant duplicate hold Summary

**A computer that holds a seat in one organization is held Pending `cross_tenant_duplicate` when a second organization enrolls it, a copy silent for 24 hours is retired by the new enrollment (seat released, tokens revoked), and neither organization ever sees the other's name or id.**

## Accomplishments

- `seat_identity.py`: `hardware_match_other_tenants_filter` (serial/UUID terms, `tenantId $ne`, seat-holding status filter passed in; None for a MAC alone) and the pure `seen_within`.
- `cross_tenant.py` (160 lines, raw collections only): `live_owner`, `silent_copies`, `hold_detail`, `alert_platform_hold`, `retire_copy` (one conditional update, then seat release, token revocation, ledger entries and a platform notice), `retire_silent_copies`, `ensure_indexes` (two sparse indexes), `LIVE_WINDOW`, `MOVED_REASONS`.
- `license_rules.hold_reason` returns `cross_tenant_duplicate` right after `trial_ended` and before the allowlist and network rules; `returning_hold_reason` applies only that rule to a returning agent that needs a seat again.
- `register_agent`: a returning agent needing a seat is checked, the hold carries `extra={"crossTenant": detail}`, the platform feed is alerted, and silent copies elsewhere are retired after the seat-taking upsert (12 lines added, the file was already over 500).
- `hold_reasons.py`: `REASON_CROSS_TENANT` with the D-36 tenant sentence and the old-build refusal.

## Verification

- Task 1 command: 20 passed. Task 2 command (test_cross_tenant_duplicate, test_network_rule, test_enrollment_controls, test_pending_agents, test_machine_identity, test_asset_identity, test_plan_tracer): 129 passed, 0 skipped, on the private mongod at 127.0.0.1:27998.
- Other suites that register agents or call `hold_reason` (test_licensing, test_partner_expiry, test_agent_identity, test_agent_location_history_wiring, test_agent_registry_regression_1, test_itam_lifecycle*, test_audit_ledger, test_rust_heartbeat_parity, test_seat_identity, test_tenant_license_api, test_route_auth_baseline, test_catalogue_route_parity): 217 passed.
- Acceptance greps: `"replacedBy"` 0 and `set_tenant_id` 0 in cross_tenant.py, `sparse=True` 2, `REASON_CROSS_TENANT` 3 in license_rules.py, 3 matching lines in agent_registry_endpoints.py.
- Not run: the ~4 minute test_catalogue_slice_* route walks (no route was added or changed).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Leak assertion tripped on the held agent's own id**
- **Found during:** Task 2 (GREEN run)
- **Issue:** the test searched B's feed for the string `agent-a`, which is also the start of B's own generated id `agent-af1b...`.
- **Fix:** the leak test's seeded A agent is named `owner-copy-1`; the code was right.
- **Files modified:** backend/tests/test_cross_tenant_duplicate.py
- **Commit:** f5b447159

**Total deviations:** 1 auto-fixed (test data). **Impact:** none on behavior.

## Commit hygiene

`seat_identity.py`, `license_rules.py`, `hold_reasons.py` and `agent_registry_endpoints.py` had no uncommitted changes before this plan, so each was staged whole by name; no user hunk was committed. No Co-Authored-By trailer (checked).

## Known Stubs

None.

## Threat Flags

None. T-88-19 (fixed unnamed tenant text; crossTenant and the alert are platform-only; tests assert neither name nor id reaches B's feed or refusal, and A's feed stays empty), T-88-20 (only 24-hour-silent seat holders are retired, each with a platform notice and platform-ledger entry; a MAC alone never counts), T-88-21 (`revoke_agent_tokens` at retirement) are implemented and tested. T-88-22 stays accepted.

## Handed to later plans

- 88-09: hide `crossTenant` from tenant readers of the Pending list, approve/reject of this hold (reject does not denylist the duplicate's own key yet), the heartbeat refusal for a Replaced agent, restore of a moved copy, and the hourly live-pair report (A-88-RACE).
- 88-11: migration 034 must call `cross_tenant.ensure_indexes(db)`; until it runs, the lookup is a collection scan on `agents`.
- Nothing is deployed: the backend must be restarted by the user.

## Self-Check: PASSED

- backend/cross_tenant.py and backend/tests/test_cross_tenant_duplicate.py found on disk.
- Commits f77c5eea0, 8ccd5e06f, 1f1d20d93, f5b447159 are ancestors of HEAD.
