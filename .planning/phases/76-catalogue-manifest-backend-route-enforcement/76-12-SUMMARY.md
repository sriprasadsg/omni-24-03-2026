---
phase: 76-catalogue-manifest-backend-route-enforcement
plan: 12
subsystem: api
tags: [rbac, catalogue-manifest, agents, data-plane, d-02]

requires:
  - phase: 76-catalogue-manifest-backend-route-enforcement
    provides: catalogue_guard / parity helpers (76-01), manifest (76-02), named AGENTS_GUARD (76-05)
provides:
  - route-level AGENTS_GUARD on the console reads and writes of five mixed agent data-plane routers
  - backend/tests/test_catalogue_slice_agents_dataplane.py (parity, explicit 15-route ingest list, real-app 403, agent-auth baseline)
affects: [76-11, 77]

actuals:
  tokens: 40000
  tasks: 2
  commits: 2
plan_head_before: 3b93b633eb88a7278bc04377095ba108d95f7a9f
plan_head_after: 574c8d023f3e599d121c9983b7bd2de030ce8049

tech-stack:
  added: []
  patterns:
    - "Mixed agent router: reuse the named AGENTS_GUARD from catalogue_mounts_agents per console route; agent routes keep verify_agent_key / get_current_user_or_agent and carry no tag"
    - "Ingest exclusion is asserted from an explicit (method, path) list so a renamed ingest route fails loudly"

key-files:
  created:
    - backend/tests/test_catalogue_slice_agents_dataplane.py
  modified:
    - backend/agent_tasks_endpoints.py
    - backend/agent_security_endpoints.py
    - backend/agent_telemetry_endpoints.py
    - backend/agentic_tasks_endpoints.py
    - backend/agent_uninstall_endpoints.py

key-decisions:
  - "All 17 console routes in these five modules are owned by the agents catalogue in the manifest, so the 76-05 AGENTS_GUARD is reused instead of defining new guards"
  - "No MOUNTS entry added and catalogue_mounts_agents.py not edited; every router here is mixed so guards are route-level"

requirements-completed: [ACC-04]

coverage:
  - id: D1
    description: "parity_offenders over the five data-plane modules is empty"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_slice_agents_dataplane.py#test_dataplane_parity"
        status: pass
    human_judgment: false
  - id: D2
    description: "All 15 agent ingest routes (verify_agent_key and get_current_user_or_agent) stay in the walk with agent / agent_capable auth, no tag and no exemption; agent-auth dependency counts unchanged"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_slice_agents_dataplane.py#test_dataplane_agent_routes_untouched"
        status: pass
      - kind: unit
        ref: "backend/tests/test_catalogue_slice_agents_dataplane.py#test_dataplane_agent_auth_unchanged"
        status: pass
    human_judgment: false
  - id: D3
    description: "Real app: viewer (no view:agents) gets 403 and analyst (view:agents) does not on instruction history, task status, telemetry, vulnerability scans and agentic-task decisions"
    requirement: ACC-04
    verification:
      - kind: integration
        ref: "backend/tests/test_catalogue_slice_agents_dataplane.py#test_dataplane_real_app_enforced"
        status: pass
    human_judgment: false
  - id: D4
    description: "Live check that an enrolled Rust agent still polls instructions, posts results, telemetry, scans and uninstall reports after deploy"
    verification: []
    human_judgment: true
    rationale: "Structural proof only (D2); nothing was deployed or restarted. The live agent check stays a 76-11 human-check item."

duration: 45min
completed: 2026-10-15
status: complete
---

# Phase 76 Plan 12: Agents Data-Plane Slice Summary

**The agent console reads and writes that live in the five mixed data-plane routers (tasks, security scans, telemetry, agentic tasks, uninstall) now carry the agents-catalogue guard; all 15 agent ingest routes keep exactly their verify_agent_key / get_current_user_or_agent auth and carry no tag.**

## Accomplishments
- 17 route decorators guarded with `Depends(AGENTS_GUARD)` (route-level, additive): agent_tasks 5 (dispatch, tasks/{task_id}, update, instructions/history, discovery/scan), agent_security 5 (fim-events, shadow-ai-scans, vulnerability-scans, malware-scans, persistence-findings GETs), agent_telemetry 2 (telemetry, detections GETs), agentic_tasks 2 (decisions GET, trigger POST), agent_uninstall 2 (uninstall-code GET, rotate POST).
- Existing guards kept: `require_permission("manage:agents")` on dispatch and both uninstall-code routes, `remediate:agents` on the agentic-task trigger.
- `test_catalogue_slice_agents_dataplane.py`: `DATA_PLANE_MODULES`, `AGENT_INGEST_ROUTES` (15 pairs), `AGENT_AUTH_BASELINE`, four tests, all passing.
- Mid-plan state (after Task 1) matched the plan: parity offenders were exactly the four Task 2 modules.

## slice_modules("agents") membership
Measured: 23 modules; all five data-plane modules are present (agent_security, agent_tasks, agent_telemetry, agent_uninstall, agentic_tasks). The test asserts `DATA_PLANE_MODULES <= slice_modules("agents")`. New relative to the 76-05 listing: `pending_agent_endpoints` (spec C2-C4 pending agents: GET /api/agents/pending, approve, reject, bulk) is in the slice; parity over it is already empty, so it needs no change from this plan.

## Per-route auth vs the interfaces block
No differences: every route matched the plan's auth listing (walk output: 5 user + 3 agent + 1 agent_capable in agent_tasks, etc.). The telemetry router appears twice in the walk (mounted via two includes); the same router object, so guards cover both mounts. Baseline agent-auth counts unchanged (verify_agent_key 4/5/2/2, get_current_user_or_agent 1 in agent_tasks and 1 in agent_uninstall).

## Task Commits
1. `c80d9a809` (feat): agent_tasks route guards + data-plane slice test
2. `574c8d023` (feat): security, telemetry, agentic-task and uninstall route guards; full real-app probes

## Numbers
- Data-plane test file 4 passed; with `test_catalogue_slice_agents.py` and `test_route_auth_baseline.py`: 27 passed.
- Full backend suite: 3703 passed, 47 skipped, 0 failed (baseline 3699 + 4 new tests) in 10m46s.

## Tests changed
None. No existing test needed a role change.

## Deviations from Plan

None - plan executed exactly as written. (Housekeeping: `agent_uninstall_endpoints.py` carried a pre-existing mode-only working-tree change 644 to 755; it was staged with `core.fileMode=false` so the commit contains no mode change.)

## Behaviour changes worth knowing
- Console reads that were login-only now need `view:agents` (or `manage:agents`): agent instruction history, task status, telemetry, detections, FIM events, shadow-AI/vulnerability/malware scans, persistence findings, agentic-task decisions. `viewer` loses them; analyst and above keep them.
- Writes (dispatch, update, discovery scan, trigger, uninstall-code rotate) already needed role permissions; the catalogue guard is additive. `GET /uninstall-code` still requires `manage:agents` through its existing guard.

## Manifest corrections for 76-11
None found for these five modules: every console route resolves to the `agents` catalogue as intended. (route_aliases still has the unguarded offenders already listed in 76-05: /api/agent/download-token/{tenant_id}, /api/agents/stats, /api/ai/test-connection, /api/pqc/keys, /api/secrets/findings, /api/tenants/me, /api/ueba/shadow-ai.)

## Phase 77 UX notes
- Agent detail tabs for telemetry, detections, scans, instruction history and agentic decisions call the newly guarded reads; the UI should hide these tabs for roles without view:agents instead of showing 403s.

## Known Stubs
None.

## Threat Flags
None.

## Self-Check: PASSED
- backend/tests/test_catalogue_slice_agents_dataplane.py exists; commits c80d9a809 and 574c8d023 are ancestors of HEAD.
- Plan verification: data-plane + route_auth_baseline tests pass; full backend suite 3703 passed, 47 skipped, 0 failed.
