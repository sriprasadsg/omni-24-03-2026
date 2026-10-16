---
phase: 76-catalogue-manifest-backend-route-enforcement
plan: 14
subsystem: testing
tags: [rbac, parity-gate, gap-ledger, agent-capable, exemption-review, wr-01, d-05, gap-closure]

requires:
  - phase: 76-catalogue-manifest-backend-route-enforcement
    provides: agent_tolerant guards and the agent_capable probe mode (76-13), parity helper and gap ledger (76-11)
provides:
  - _parity_scope in backend/tests/_catalogue_parity.py (agent-capable routes in the deny-by-default parity gate)
  - agentCapableRoutes (12 reviewed entries) in shared/catalogue-gaps.json
  - exemptRoutes (34 reviewed entries) in shared/catalogue-gaps.json
  - synthetic negative controls for both reviewed lists
affects: [76-15]

actuals:
  tokens: 14000
  tasks: 2
  commits: 4
plan_head_before: 07b008909c3e043c8f2466bccc3d8da9d63a2ed9
plan_head_after: 4f729da94628464fe9f1b41620758d25b513ad06

tech-stack:
  added: []
  patterns:
    - "Reviewed-list ledger keys are optional in ledger_offenders, so ledgers without them keep their old meaning"
    - "Ledger entries are generated once by a throwaway scratchpad script over run_real_app_walk(), reviewed by hand, never written from a test (PROH-76-03)"

key-files:
  created: []
  modified:
    - backend/tests/_catalogue_parity.py
    - backend/tests/test_catalogue_route_parity.py
    - shared/catalogue-gaps.json

key-decisions:
  - "slice_modules keeps _in_scope; only parity_offenders uses the wider _parity_scope, so the wave-3 slice partition is unchanged"
  - "Untagged agent-capable writes stay out of parity scope and are covered by the reviewed agentCapableRoutes list; safe-method agent-capable routes of enforce:true catalogues must carry agent_tolerant(catalogue_guard(...)) and can never be ledgered"
  - "agentAuthExcludedRoutes now counts only untagged agent-capable pairs (15 -> 12); maxExemptRoutes stays 34"
  - "The refusing-tag rule (a tag without allow_agent True on an agent-capable route) fires regardless of scope, group enforcement or exemption"

requirements-completed: [ACC-04, ACC-05]

coverage:
  - id: D1
    description: "Parity gate names an agent-capable read under an enforced catalogue lacking agent_tolerant(catalogue_guard(...)) and any tag that would refuse the agent"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_route_parity.py#test_untagged_agent_capable_read_in_enforced_catalogue_is_a_parity_offender"
        status: pass
      - kind: unit
        ref: "backend/tests/test_catalogue_route_parity.py#test_plain_guard_on_agent_capable_route_would_refuse_the_agent"
        status: pass
      - kind: integration
        ref: "backend/tests/test_catalogue_route_parity.py#test_all_enforced_routes_guarded"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every untagged agent-capable route is an individually reviewed agentCapableRoutes line; unlisted, stale, duplicate, placeholder and listed-read entries fail"
    requirement: ACC-05
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_route_parity.py#test_ledger_offender_for_unlisted_agent_capable_route_is_paste_ready"
        status: pass
      - kind: integration
        ref: "backend/tests/test_catalogue_route_parity.py#test_ledger_ratchets"
        status: pass
    human_judgment: false
  - id: D3
    description: "Every catalogue_exempt route is a reviewed exemptRoutes line; unlisted, stale, duplicate and re-worded exemptions fail"
    requirement: ACC-05
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_route_parity.py#test_reworded_exempt_reason_is_an_offender_showing_both_reasons"
        status: pass
      - kind: integration
        ref: "backend/tests/test_catalogue_route_parity.py#test_committed_exempt_list_matches_the_production_registry"
        status: pass
    human_judgment: false

duration: 45min
completed: 2026-10-16
status: complete
---

# Phase 76 Plan 14: Parity gate over agent-capable routes and reviewed exemption lists Summary

**The deny-by-default parity gate now sees agent-capable routes (reads must carry agent_tolerant guards, no tag may refuse an agent), and every untagged agent-capable route (12) and every catalogue_exempt route (34) is an individually reviewed line in shared/catalogue-gaps.json.**

## Accomplishments

- `_parity_scope` (used only by `parity_offenders`): agent-capable routes of an enforce:true catalogue enter parity scope when they have a safe method or already carry a tag. Expected text reads `agent_tolerant(catalogue_guard("view", read=[...], write=[...]))`. Any tag on an agent-capable route without `allow_agent` True is an offender ("would refuse the agent identity"), independent of scope. The real app is clean under the wider scope (76-13 had already tagged the three reads).
- `ledger_offenders`: `agentAuthExcludedRoutes` counts untagged agent-capable pairs only; optional `agentCapableRoutes` list requires every untagged agent-capable pair listed with a reason of at least 10 characters and no `<` placeholder, fails stale and duplicate entries, and refuses a listed safe-method route under an enforced catalogue. Optional `exemptRoutes` list must equal the app's exempt set with reasons equal character for character; unlisted/stale/duplicate/re-worded entries fail with paste-ready entries. The helper never writes the ledger.
- Ledger: `agentAuthExcludedRoutes` 15 -> 12, `maxExemptRoutes` 34 (unchanged, for 76-15), `agentCapableRoutes` (12) and `exemptRoutes` (34) inserted before `routers`, both sorted by route string. Both lists were generated with throwaway scripts in the session scratchpad and reviewed by hand against the handlers.

### agentCapableRoutes as committed

| Route | Reason |
|-------|--------|
| GET /api/swarm/peers | Automation & Intelligence group is not enforced: route guards deferred to ACC-F2 (D-01) |
| PATCH /api/agent-chat/sessions/{session_id}/close | admin-only: close_session refuses every role outside the tenant admin roles, agents included (403) |
| POST /api/agent-chat/sessions | admin-only: start_session refuses every role outside the tenant admin roles, agents included (403) |
| POST /api/agents/{agent_id}/metrics | agent ingest: an agent reports only its own metrics; people need manage:agents, checked in record_agent_metrics |
| POST /api/agents/{agent_id}/raise-ticket | agent ingest: the agent raises a ticket for its own machine; people are pinned to their tenant in raise_ticket_via_agent but hold no permission check (write path, not a read) |
| POST /api/agents/{agent_id}/uninstall-report | agent-only: report_uninstall refuses every caller except the named agent (403) |
| POST /api/alerts | agent ingest: agents raise alerts; people need investigate:security, checked in create_alert |
| POST /api/remote/session/{session_id}/consent | agent-only: report_consent refuses every non-agent caller (401) and any agent that does not own the session (403) |
| POST /api/response/tasks/{task_id}/feedback | agent ingest: an agent reports on its own task (_require_own_task); people need remediate:agents, checked in submit_task_feedback |
| POST /api/response/tasks/{task_id}/result | agent ingest: an agent reports on its own task (_require_own_task); people need remediate:agents, checked in submit_task_result |
| POST /api/stream/publish/{topic} | Observability group is not enforced: route guards deferred to ACC-F2 (D-01) |
| POST /api/swarm/report | Automation & Intelligence group is not enforced: route guards deferred to ACC-F2 (D-01) |

exemptRoutes: 34 entries (equal to maxExemptRoutes), exact app reasons.

## TDD Gate Compliance

- Task 1 RED `edf0a9042` (10 failing: parity offender missing for untagged agent-capable read and plain-guard route, ledger list checks absent, shape test missing the `agentCapableRoutes` key; failures were on the planned assertions, a first GREEN run exposed a manifest-twin typo in my own synthetic tags, fixed in the same test commit before GREEN). GREEN `60a8540ce`.
- Task 2 RED `1a8a21e7e` (6 failing: unlisted/re-worded/stale/duplicate offenders absent, shape test and registry-equality test hit missing `exemptRoutes` key). GREEN `4f729da94`.
- Semantic assessment: each RED test failed on an assertion for the planned behavior with the target helper present; `gsd_run check tdd-red-evidence` was not run (pytest output is not a supported report format).

## Verification

- Targeted set (route parity, manifest, route_auth_baseline, agents_dataplane, devices, secops, agents slices, guard_variants): 122 passed.
- Full backend suite: 3774 passed, 47 skipped, 0 failed (baseline after 76-13: 3753 passed, 47 skipped; +21 new tests).
- `npx vitest run src/__tests__`: 266 passed (baseline 266). `npm run build`: exit 0.
- Acceptance: both python3 ledger assertions print ok; `def _parity_scope` count 1; no `open(..."w")` in `_catalogue_parity.py`.

## Deviations from Plan

None - plan executed exactly as written. The two test files carried a pre-existing chmod-only change (644 -> 755); all commits staged by explicit path with `core.fileMode=false`, so no mode change entered any commit.

## Observations (not fixed, out of scope)

- `POST /api/agents/{agent_id}/raise-ticket` has no permission check for people beyond tenant pinning (any authenticated tenant user can raise a ticket for an agent in their tenant). Recorded honestly in the ledger reason; a guard decision belongs to a later plan or ACC-F2.

## Known Stubs

None.

## Threat Flags

None. T-76-42, T-76-48 and T-76-49 are mitigated by the new gate checks and covered by synthetic controls.

## Human verification (post-deploy, user-owned)

None required; this plan changes test helpers and a committed ledger only (no runtime or UI change).

## Next

76-15 builds on the exemptRoutes list (WR-05) and leaves the ratchet numbers as set here.

## Self-Check: PASSED

- FOUND: backend/tests/_catalogue_parity.py, backend/tests/test_catalogue_route_parity.py, shared/catalogue-gaps.json; commits edf0a9042, 60a8540ce, 1a8a21e7e, 4f729da94 are on the branch.
