---
phase: 88-plan-based-licensing-network-enrollment-rules
plan: 09
subsystem: licensing
tags: [cross-tenant, enrollment, pending, heartbeat, restore, mongodb]

requires:
  - phase: 88-07
    provides: cross_tenant (hold_detail, retire_copy, retire_silent_copies, MOVED_REASONS), the cross_tenant_duplicate hold and the Pending crossTenant field
  - phase: 88-06
    provides: license_seat_tick with one guarded step per maintenance job
provides:
  - cross_tenant.before_approval, after_admission, restore, list_moved, report_live_pairs, REPORTS
  - approve(): reason_changed 409 for a hold whose machine is now live elsewhere; move on approving a cross_tenant_duplicate hold; moved_silent retirement on any approval
  - pending_agents.list_not_admitted keyword platform_view; answer_heartbeat keyword extra
  - routes GET /api/agents/pending/moved and POST /api/agents/pending/{agent_id}/restore
  - heartbeat refusal agent_replaced and the cross-tenant hold for a returning agent
  - audit event agent.restored (platform and agent tenant); agent fields restoredAt, restoredBy; collection cross_tenant_reports
affects: [88-11, 88-14, 88-16]

actuals:
  tokens: 21000
  tasks: 3
  commits: 6
plan_head_before: f2aa7883cc49833f4a5213bdb4e9284d5afdc5b1
plan_head_after: cc042e093e9e8a37cc594c4940a6c4213e9437e5

tech-stack:
  added: []
  patterns:
    - "decision logic lives in cross_tenant.py; pending_agents.py keeps one-line hooks (it stays under 500 lines)"
    - "a hold is converted by a conditional update on status Pending, so only one caller alerts the platform"
    - "the live-pair report claims each machine key with an upsert on a unique key and a reportedAt cutoff, so a day's report is posted once even across processes"

key-files:
  created:
    - backend/tests/test_cross_tenant_decisions.py
  modified:
    - backend/cross_tenant.py
    - backend/pending_agents.py
    - backend/pending_agent_endpoints.py
    - backend/agent_heartbeat_endpoints.py
    - backend/app_background_tasks.py
    - shared/catalogue-gaps.json

key-decisions:
  - "A Pending hold converted by before_approval also posts the platform alert naming both organizations; a Rejected record that is approved while live elsewhere is refused with reason_changed but not rewritten"
  - "A heartbeat hold for a returning agent also posts the platform alert (alert_platform_hold), matching the enrollment path; it fires once per episode because a Pending agent no longer reaches the needs_seat branch"
  - "report_live_pairs keeps the cheap string lastSeen pre-filter in Mongo and applies seat_identity.seen_within in Python as the exact test"
  - "A failure to store the platform notice releases the day's claim so the next hourly tick retries"

requirements-completed: [LIC-06]

coverage:
  - id: D1
    description: "Approving a cross_tenant_duplicate hold admits the machine in the new tenant first and then retires every seat-holding copy elsewhere (Replaced, moved, seat released, tokens revoked, no replacedBy); with no free seat the answer is 409 no_free_seat and the old copy is untouched"
    requirement: LIC-06
    verification:
      - kind: integration
        ref: "backend/tests/test_cross_tenant_decisions.py (test_approving_a_held_duplicate_admits_it_and_moves_the_machine_off_the_old_tenant, test_with_no_free_seat_in_the_new_tenant_the_old_copy_is_untouched, test_every_seat_holding_copy_elsewhere_is_retired_in_one_approval)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Approving a hold for any other reason re-checks the machine: live elsewhere turns it into cross_tenant_duplicate with its platform-only detail and answers 409 reason_changed, admitting nothing and raising no limit; otherwise silent copies elsewhere are retired as moved_silent"
    requirement: LIC-06
    verification:
      - kind: integration
        ref: "backend/tests/test_cross_tenant_decisions.py (test_a_seat_limit_hold_whose_machine_is_now_live_elsewhere_turns_into_a_duplicate_hold, test_any_approval_retires_a_silent_copy_in_another_organization, test_an_approval_with_no_copy_elsewhere_changes_nothing_else)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Rejecting a cross_tenant_duplicate hold denylists nothing; the tenant's Pending list never carries crossTenant, the other organization's name, id, agent id or hostname, and the platform list does"
    requirement: LIC-06
    verification:
      - kind: integration
        ref: "backend/tests/test_cross_tenant_decisions.py (test_rejecting_a_cross_tenant_hold_denylists_nothing, test_the_tenant_list_never_carries_the_other_organization_but_the_platform_list_does)"
        status: pass
    human_judgment: false
  - id: D4
    description: "A heartbeat from an agent retired because its computer moved answers 403 agent_replaced and claims no seat; a returning agent whose computer is live elsewhere is held cross_tenant_duplicate instead of taking a seat"
    requirement: LIC-06
    verification:
      - kind: integration
        ref: "backend/tests/test_cross_tenant_decisions.py (test_a_moved_agent_is_refused_at_its_heartbeat_and_claims_no_seat x2, test_an_in_tenant_replacement_keeps_its_old_behaviour, test_a_returning_agent_whose_machine_is_live_elsewhere_is_held_not_given_a_seat)"
        status: pass
    human_judgment: false
  - id: D5
    description: "The Super Admin lists moved agents and restores one to Inactive, recorded in the platform ledger and the agent's own tenant ledger without the other organization's name; non-moved, unknown and tenant-admin requests are refused (409, 404, 403); the two routes are recorded as exempt platform routes (ratchet 31)"
    requirement: LIC-06
    verification:
      - kind: integration
        ref: "backend/tests/test_cross_tenant_decisions.py (test_the_super_admin_restores_a_moved_agent_and_both_ledgers_record_it, test_a_restored_agent_that_returns_while_its_machine_is_live_in_the_new_tenant_is_held, test_restoring_an_agent_that_is_not_moved_or_unknown_or_by_a_tenant_admin_is_refused, test_moved_agents_are_listed_for_the_platform_only); backend/tests/test_catalogue_route_parity.py"
        status: pass
    human_judgment: false
  - id: D6
    description: "The hourly licence tick posts one platform notice per serial or SMBIOS UUID held by seat-holding agents seen in the last 24 hours in two or more tenants, once per key per day, and still runs when an earlier step raises"
    requirement: LIC-06
    verification:
      - kind: integration
        ref: "backend/tests/test_cross_tenant_decisions.py (test_a_machine_live_in_two_organizations_is_reported_once_a_day, test_the_uuid_pairs_are_reported_too_and_each_key_once, test_pairs_that_are_not_both_live_seat_holders_in_two_tenants_are_not_reported x4, test_the_licence_tick_reports_live_pairs_even_when_an_earlier_step_fails)"
        status: pass
    human_judgment: false

duration: 17min
completed: 2026-11-11
status: complete
---

# Phase 88 Plan 09: Cross-tenant decisions Summary

**Approving a held machine now moves it between organizations with one licence, no other approval can admit a duplicate, tenant users never see the other organization, a moved agent cannot heartbeat back in, the Super Admin can list and restore moved agents, and an hourly report names any machine live in two organizations.**

## Accomplishments

- `cross_tenant.before_approval` / `after_admission`: `approve` re-checks a non-cross-tenant hold (409 `reason_changed`, hold converted, platform alerted, nothing admitted, no limit raised); after the status flip a cross_tenant_duplicate approval retires every seat-holding copy elsewhere as `moved` (at most 20), any other approval retires silent copies as `moved_silent`, and the machine is remembered for the new tenant. With no free seat the claim fails first, so the old copy is untouched.
- `reject` of a cross_tenant_duplicate hold denylists nothing; `crossTenant` is unset on approval and projected out of `list_not_admitted` unless `platform_view` (the endpoint passes `platform`).
- Heartbeat: a Replaced agent with a moved reason gets 403 `agent_replaced` before any seat claim; a returning agent that needs a seat is held `cross_tenant_duplicate` with `crossTenant` when its computer is live elsewhere (`answer_heartbeat` gained `extra`).
- `cross_tenant.restore` / `list_moved` and the routes `GET /api/agents/pending/moved` (platform readers) and `POST /api/agents/pending/{agent_id}/restore` (`_require_decider`): a conditional update from a moved state to Inactive, an `agent.restored` entry in the platform ledger and in the agent's own tenant's ledger (no other organization named), 404 unknown, 409 not moved.
- `cross_tenant.report_live_pairs` as one more guarded step of `license_seat_tick`: one platform notice per serial or SMBIOS UUID per day for a machine whose seat-holding copies were seen within 24 hours in two or more tenants; a unique-key index on `cross_tenant_reports` (also created by `ensure_indexes`).
- `shared/catalogue-gaps.json`: the two new exempt routes and `maxExemptRoutes` 29 to 31.

## Verification

- Task 1 command: 109 passed (test_cross_tenant_decisions, test_cross_tenant_duplicate, test_pending_agents, test_network_rule, test_partner_license_writers), 0 skipped.
- Task 2 command: 106 passed on the non-report tests then, and the full file (23 tests) passes with test_catalogue_route_parity, test_route_auth_baseline, test_platform_role_routes and test_enrollment_controls.
- Task 3 command: test_cross_tenant_decisions (23), test_trial (26) and test_cross_tenant_duplicate (28): 77 passed, 0 skipped.
- Acceptance greps: `cross_tenant.before_approval|after_admission` 2 lines in pending_agents.py; `platform_view` in both files; `agent_replaced` 1 line in the heartbeat file; `"maxExemptRoutes": 31` 1; `async def restore|list_moved` 2; `report_live_pairs` 1 in app_background_tasks.py; pending_agents.py 499 lines and cross_tenant.py 311 lines (both under 500).
- Wider regression run on the private mongod: see Self-Check.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Platform alert on a heartbeat hold**
- **Found during:** Task 2
- **Issue:** The plan's heartbeat hold would have left the platform feed without the notice naming both organizations that the enrollment path posts (D-36, D-43); only the generic Pending notice would exist.
- **Fix:** One extra line in the heartbeat branch calls `cross_tenant.alert_platform_hold` before `answer_heartbeat`; it fires once per episode because a Pending agent no longer reaches the seat branch.
- **Files modified:** backend/agent_heartbeat_endpoints.py
- **Commit:** 2248201b1

**Total deviations:** 1 auto-fixed (1 missing critical). **Impact:** one added line in a file the plan asked to keep minimal; no behaviour change for the named paths.

## Notes for later plans

- A restored agent's old token stays revoked (tokens were revoked at retirement, 88-07); it comes back through its agent secret at re-enrollment, then takes a seat through the cross-tenant rule. The plan's "next check-in" wording assumes that path; a token re-issue on restore was not part of this plan.
- An older agent build (no `supportsPending`) heartbeating into a cross-tenant hold gets the existing generic 403 text ("Agent limit reached..."), as for every other hold reason raised from the heartbeat; `pending_agents.py` has no room left for a reason-specific text there.
- `agent_heartbeat_endpoints.py` still carries the user's uncommitted `collectionIntervals` hunk; only this plan's hunks were committed.

## Self-Check: PASSED

- Files found: backend/cross_tenant.py, backend/tests/test_cross_tenant_decisions.py.
- Commits found on the branch: 19acb8edd, 209ad15a8, 2e542eafd, 2248201b1, 791b1fcaf, cc042e093 (no Co-Authored-By trailer on any).
- Wider regression on the private mongod: test_agent_heartbeat_geo_security, test_agent_registry_regression_1, test_licensing, test_partner_expiry, test_rust_heartbeat_parity, test_seat_identity, test_tenant_license_api, test_license_seat_toctou: 58 passed; test_catalogue_slice_agents, _agents_dataplane, _partners: 11 passed. The other seven slice walks (assets, autonomous_ops, billing_identity, devices, secops, secposture, settings_ops) were not run: no route outside the agents catalogue changed.
- The two new routes sit under /api/agents/pending and are exempt; test_catalogue_route_parity and test_route_auth_baseline pass with ratchet 31.
