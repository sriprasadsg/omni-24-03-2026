---
phase: 76-catalogue-manifest-backend-route-enforcement
plan: 13
subsystem: api
tags: [rbac, catalogue-guard, agent-tolerant, platform-read, wr-01, d-02, gap-closure]

requires:
  - phase: 76-catalogue-manifest-backend-route-enforcement
    provides: catalogue_guard factory and named guards (76-01, 76-05, 76-06, 76-11), route walker and slice pins
provides:
  - catalogue_guard(allow_agent=, platform_read=) with construction-time checks, agent_tolerant(guard), check_catalogue_access(platform_read=)
  - agent-tolerant guards on GET /api/software/download/{filename}, GET /api/response/tasks/{agent_id}, GET /api/agent-chat/sessions
  - probe_real_app case value auth="agent_capable"
  - D-02 slice pins (devices, secops, agents) that refuse any non-tolerant tag on an agent-capable route
  - backend/tests/test_catalogue_guard_variants.py (32 tests)
affects: [76-14, 76-15]

actuals:
  tokens: 8000
  tasks: 2
  commits: 4
plan_head_before: c25d6696c7e41791a21d448f27c4e190126a299d
plan_head_after: 320276da6a168a63aae9a136b2074b8883fee703

tech-stack:
  added: []
  patterns:
    - "Agent-tolerant guard: same catalogue check built on get_current_user_or_agent; token role exactly 'agent' returns before any permission lookup, every other identity gets the full check"
    - "platform_read: safe-method fallback through has_platform_permission, restricted at construction to PLATFORM_ONLY_PERMISSIONS; scope check then needs the platform permission used"
    - "New tag keys (allow_agent, platform_read) are added only when set, so every existing guard tag is byte-identical"

key-files:
  created:
    - backend/tests/test_catalogue_guard_variants.py
  modified:
    - backend/catalogue_guards.py
    - backend/software_endpoints.py
    - backend/response_endpoints.py
    - backend/agent_chat_endpoints.py
    - backend/tests/_route_walk.py
    - backend/tests/test_catalogue_slice_devices.py
    - backend/tests/test_catalogue_slice_secops.py
    - backend/tests/test_catalogue_slice_agents.py

key-decisions:
  - "Agent identity is the auth layer's own test (TokenData.role == 'agent' from get_current_user_or_agent); a role spelled 'Agent' is a person and is fully checked (PROH-76-05)"
  - "allow_agent is validated by auth.__qualname__ == 'get_current_user_or_agent' so a reload of authentication_service cannot break construction"
  - "POST result/feedback, POST /agent-chat/sessions and PATCH close get no guard here; 76-14 lists them in the reviewed ledger"
  - "shared/catalogue-gaps.json, _catalogue_parity.py and test_catalogue_route_parity.py are untouched (76-14 owns them)"

requirements-completed: [ACC-04, ACC-05]

coverage:
  - id: D1
    description: "GET /api/software/download/{filename} refuses viewer, itam_viewer and nobody; agent, tenant_admin and platform_support reach the handler (404 for a missing file)"
    requirement: ACC-04
    verification:
      - kind: integration
        ref: "backend/tests/test_catalogue_guard_variants.py#test_download_on_the_real_app"
        status: pass
      - kind: integration
        ref: "backend/tests/test_catalogue_guard_variants.py#test_download_serves_agent_and_permitted_roles"
        status: pass
    human_judgment: false
  - id: D2
    description: "GET /api/response/tasks/{agent_id} refuses people without view:security and still answers the agent and view:security holders"
    requirement: ACC-04
    verification:
      - kind: integration
        ref: "backend/tests/test_catalogue_guard_variants.py#test_task_poll_and_chat_list_on_the_real_app"
        status: pass
    human_judgment: false
  - id: D3
    description: "GET /api/agent-chat/sessions carries the chat agent-tolerant guard without changing any built-in role's outcome"
    requirement: ACC-04
    verification:
      - kind: integration
        ref: "backend/tests/test_catalogue_guard_variants.py#test_task_poll_and_chat_list_on_the_real_app"
        status: pass
    human_judgment: false
  - id: D4
    description: "Guard factory: allow_agent / platform_read construction checks, tag shape, platform read rule, agent identity never permission-checked"
    requirement: ACC-05
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_guard_variants.py (guard-variant unit tests)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Live agent installer download and live viewer refusal after the user's deploy"
    verification: []
    human_judgment: true
    rationale: "Needs the deployed backend and an enrolled Rust agent; deploy and restart are user-owned"

duration: 16min
completed: 2026-10-16
status: complete
---

# Phase 76 Plan 13: Agent-tolerant catalogue guards (WR-01 route half) Summary

**Agent-tolerant and platform-read variants of the catalogue guard, applied to the installer download, the response-task poll and the agent-chat session list so viewers are refused while the enrolled agent keeps working.**

## Performance

- **Duration:** 16 min
- **Tasks:** 2 (tracer + auto, both TDD)
- **Files:** 9 modified/created

## Accomplishments

- `catalogue_guard` gained `allow_agent` and `platform_read`; `agent_tolerant(guard)` rebuilds a tagged guard on `get_current_user_or_agent`. The agent identity (role exactly `agent`) returns before any permission lookup; everyone else, including a role spelled `Agent`, gets the full check. Construction refuses `allow_agent` without the agent-aware auth and any `platform_read` entry outside `PLATFORM_ONLY_PERMISSIONS`.
- BASE commit (HEAD before Task 1): `c25d6696c7e41791a21d448f27c4e190126a299d`.
- Tagged routes and guard constants:
  - `GET /api/software/download/{filename}` -> `SOFTWARE_UPDATES_AGENT_GUARD` (`agent_tolerant(SOFTWARE_UPDATES_GUARD)`, backend/software_endpoints.py)
  - `GET /api/response/tasks/{agent_id}` -> `EDR_AGENT_GUARD` (`agent_tolerant(EDR_GUARD)`, backend/response_endpoints.py)
  - `GET /api/agent-chat/sessions` -> `CHAT_AGENT_GUARD` (`agent_tolerant(CHAT_GUARD)`, backend/agent_chat_endpoints.py)
- `platform_read` is not applied to any route yet (76-15 uses it); it is unit-tested: Platform Support/Billing read in the platform tenant, never write, refused in a tenant, narrowed scopes refuse.
- Slice pins for devices, secops and agents now refuse any tag on an agent or public route and any tag without `allow_agent` True on an agent-capable route.
- Tracer gate: the installer-download slice was verified end to end on the real mounted app before expansion.

## TDD Gate Compliance

- Task 1 RED `ee2b3f12e` (21 of 24 new tests failing; the real-app download probe failed on its status assertion, viewer router test on 200 vs 403, others on the missing `agent_tolerant`/keyword arguments). GREEN `3de746d3a`.
- Task 2 RED `397466c35` (5 failing: poll refusals 200 vs 403, missing route guard tag, real-app 500 vs 403). GREEN `320276da6`.
- Semantic assessment: the factory-level RED tests fail on AttributeError/TypeError because the API did not exist (the test module imports it lazily so collection succeeds); the route-level RED tests fail on the planned status assertions. `gsd_run check tdd-red-evidence` was not run (pytest output is not one of its supported report formats).

## Verification

- `pytest backend/tests/test_catalogue_guard_variants.py backend/tests/test_catalogue_guards.py backend/tests/test_catalogue_slice_devices.py`: 46 passed.
- Task 2 targeted set (variants, secops, agents, devices slices, viewer_cannot_act_on_agents, route parity, agents_dataplane): 90 passed.
- Full backend suite: 3753 passed, 47 skipped, 0 failed (baseline 3721 passed, 47 skipped; +32 new tests).
- `npx vitest run src/__tests__`: 266 passed (baseline 266). `npm run build`: built, exit 0.
- Acceptance greps: `def agent_tolerant` 1, `agent_tolerant(SOFTWARE_UPDATES_GUARD)` 1, `agent_tolerant(EDR_GUARD)` 1, `agent_tolerant(CHAT_GUARD)` 1, one `Depends(EDR_AGENT_GUARD)` on the GET /tasks/{agent_id} decorator, one `Depends(CHAT_AGENT_GUARD)` on GET /sessions, `Depends(get_current_user_or_agent)` count in software_endpoints.py unchanged (1), `catalogue_guards.py` 194 lines.
- `git diff --name-only BASE..HEAD` lists none of shared/catalogue-gaps.json, backend/tests/_catalogue_parity.py, backend/tests/test_catalogue_route_parity.py.

## Deviations from Plan

None - plan executed exactly as written. (Housekeeping: the working tree carries many unrelated uncommitted changes and mode-only chmods; every commit staged explicit paths with `core.fileMode=false`, so none entered these commits.)

## Known Stubs

None.

## Threat Flags

None. The agent-identity check inherits the pre-existing auth-layer property noted as GAP-WR01-AGENT-ROLE-CLAIM (a tenant admin may assign the role string `agent`); closing it belongs with WR-02.

## Human verification (post-deploy, user-owned)

After the user deploys and restarts the backend: push a repository package to an enrolled Rust agent (Software Deployment) and confirm the agent downloads it with no 401/403 in its log; confirm a viewer session gets 403 from `GET /api/software/download/<file>`; confirm an enrolled agent still polls `GET /api/response/tasks/<agent_id>` without 403 and a viewer is refused.

## Next

Ready for 76-14 (parity gate and ledger over agent-capable routes), then 76-15.

## Self-Check: PASSED

- FOUND: backend/tests/test_catalogue_guard_variants.py and all modified files; commits ee2b3f12e, 3de746d3a, 397466c35, 320276da6 are on the branch.
