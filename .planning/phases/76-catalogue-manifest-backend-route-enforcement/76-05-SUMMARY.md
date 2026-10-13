---
phase: 76-catalogue-manifest-backend-route-enforcement
plan: 05
subsystem: api
tags: [rbac, catalogue-manifest, agents, support-chat, jobs, d-02]

requires:
  - phase: 76-catalogue-manifest-backend-route-enforcement
    provides: catalogue_guard / catalogue_exempt / MOUNTS convention / parity helpers (76-01), full manifest (76-02)
provides:
  - backend/catalogue_mounts_agents.py (4 MOUNTS entries + named guards and two support exemption markers)
  - route-level guards in 13 agent-slice modules; agent-key, agent-capable and public routes untouched
  - backend/tests/test_catalogue_slice_agents.py (DATA_PLANE_MODULES, LEFTOVER_MODULES, parity, exclusion, real-app probes)
affects: [76-07, 76-11, 76-12, 77]

actuals:
  tokens: 70000
  tasks: 2
  commits: 3
plan_head_before: a0b3b6b0c
plan_head_after: f72217470

tech-stack:
  added: []
  patterns:
    - "Straddling module: each route takes the guard of its own manifest owner, all defined in the slice that owns the module"
    - "Self-service routes carry a named catalogue_exempt marker from the slice mount file"

key-files:
  created:
    - backend/catalogue_mounts_agents.py
    - backend/tests/test_catalogue_slice_agents.py
  modified:
    - backend/agent_approval_endpoints.py
    - backend/agent_core_endpoints.py
    - backend/agent_download_endpoints.py
    - backend/agent_registry_endpoints.py
    - backend/agent_metrics_endpoints.py
    - backend/agent_chat_endpoints.py
    - backend/capability_endpoints.py
    - backend/remote_endpoints.py
    - backend/compliance_scans_endpoints.py
    - backend/update_endpoints.py
    - backend/platform_endpoints.py
    - backend/security_ops_endpoints.py
    - backend/support_endpoints.py
    - backend/tests/test_core_endpoints.py

key-decisions:
  - "Support conversations are self-service: every signed-in user reaches them (sidebar unread badge, global auto-opening chat window, supportChat view on view:dashboard) and every route filters by _access_filter, so 8 routes are catalogue_exempt; only the admin tenant-users picker takes the chat guard"
  - "Modules the partition put in this slice but the plan did not list (agent_chat, compliance_scans, update_endpoints) are guarded here, because the must-have is empty parity over the slice minus the data-plane modules"
  - "route_aliases is left to 76-11 (LEFTOVER_MODULES): it straddles six catalogues across four slices and 76-11 Task 2 owns the alias sweep"
  - "router_registry's /api/tasks/{task_id} alias is not guarded: the manifest gives /api/tasks to the automation group, which is not enforced"

requirements-completed: []

coverage:
  - id: D1
    description: "parity_offenders over slice_modules('agents') minus DATA_PLANE_MODULES minus route_aliases is empty"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_slice_agents.py#test_agents_slice_parity"
        status: pass
    human_judgment: false
  - id: D2
    description: "No agent, agent_capable, public or REVIEWED_UNAUTHENTICATED route owned by an agents-slice catalogue carries a guard (76-12 modules and agent_heartbeat included) (D-02)"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_slice_agents.py#test_agent_routes_untouched"
        status: pass
    human_judgment: false
  - id: D3
    description: "Real app: viewer 403 on GET /api/agents and /api/remote/sessions; analyst not refused; tenant_admin 403 and super_admin not refused on /api/jobs; viewer not refused on support conversations and unread count; /api/agents/version not refused"
    requirement: ACC-04
    verification:
      - kind: integration
        ref: "backend/tests/test_catalogue_slice_agents.py#test_agents_real_app_enforced"
        status: pass
    human_judgment: false
  - id: D4
    description: "Live check that an enrolled agent still registers, heartbeats and polls instructions after deploy"
    verification: []
    human_judgment: true
    rationale: "Structural proof only (D2); the live agent check is a 76-11 human-check item. Nothing was deployed."

duration: 45min
completed: 2026-10-13
status: complete
---

# Phase 76 Plan 05: Agents Slice Summary

**Agent console, capabilities, remote access, agent chat, jobs, service catalog and the platform/compliance/update routes that land in this slice now carry the manifest guard; every agent-key, agent-capable and public agent route is untouched, and support chat stays open to every user as self-service.**

## Accomplishments
- `catalogue_mounts_agents.py`: MOUNTS for `agent_analyze_endpoints`, `agent_quarantine_endpoints`, `agent_uptime_endpoints` (agents) and `jobs_endpoints` (jobs). Named guards for agents, agentCapabilities, remoteAccess, chat, jobs, serviceCatalog, plus alertManagement, settings, cloudSecurity and securityAudit for the straddling routes, and exemption markers `SUPPORT_OWN_CONVERSATION`, `SUPPORT_PRESENCE`.
- 57 route decorators guarded and 8 exempted across 13 modules (route-level, because each router also serves agent, agent-capable or public routes, or spans catalogues).
- Probe without the new guards: viewer on `GET /api/agents` and tenant_admin on `GET /api/jobs` reached the handler (500 in the throwaway env), so the 403s in the test come from this plan's guards. `/api/remote/sessions` already had `require_permission("view:remote_access")`.

## slice_modules("agents") vs expected
Actual (22): agent_analyze, agent_approval, agent_chat, agent_core, agent_download, agent_metrics, agent_quarantine, agent_registry, agent_security*, agent_tasks*, agent_telemetry*, agent_uninstall*, agent_uptime, agentic_tasks*, capability, compliance_scans, jobs, platform, remote, route_aliases, support, update_endpoints (* = DATA_PLANE_MODULES, 76-12).

| Difference | Handling |
|---|---|
| `agent_chat_endpoints` (4 admin routes under /api/agent-chat) not in the plan's lists | guarded here with the chat guard |
| `compliance_scans_endpoints` (POST /api/agents/{id}/compliance/scan and /fix) | guarded here (agents); its /api/compliance routes are governance, untouched |
| `update_endpoints` (build-info, build, build/{task_id}) | guarded here (agents); latest/download/checksum are reviewed public, untouched |
| `route_aliases` | **left for the 76-11 alias sweep** (GET /api/agent/download-token/{tenant_id} and GET /api/agents/stats are its agents-owned aliases) |
| `security_ops_endpoints` | partitioned to **secops**, not agents; guarded verify-integrity (agents) and audit-log (securityAudit) as the plan asked; **76-07 still owns POST /api/security/encrypt** |
| `agent_heartbeat_endpoints` | not in the slice (no user routes); covered by the exclusion test, no guard |

## Support self-service decision (evidence)
- `components/Sidebar.tsx` polls `fetchSupportUnreadCount` for every signed-in user; `App.tsx` listens for `support_message` socket events and auto-opens the support chat window from any view; the `supportChat` view needs only `view:dashboard`.
- Every conversation route filters with `_access_filter`: regular users see conversations they started or were targeted in, tenant admins their tenant, super admins all.
- Exempt (8): GET/POST `/api/support/conversations`, GET `/conversations/{convo_id}`, POST `/messages`, PATCH `/status`, POST `/read`, GET `/unread-count` -> "self-service: caller's own support conversation"; GET `/presence` -> "self-service: online status of the caller's support-chat partners".
- Guarded: GET `/api/support/tenant-users` (chat, manage:agents). The handler already refused non-admins; tenant_admin holds manage:agents.

## Task Commits
1. `afada38ea` (feat): mount map, slice tests, straddling and extra-module guards, support exemptions
2. `bc2c78759` (feat): approval, core, download, registry console routes
3. `f72217470` (test): agent core test principals moved to tenant_admin

## Numbers
- `test_catalogue_slice_agents.py` 3 + `test_route_auth_baseline.py` 20 = 23 passed.
- Full backend suite: 3335 passed, 47 skipped (after 76-04: 3332 / 47; +3 new tests, no regressions) in 3m07s.

## Tests changed to fix 403s
- `test_core_endpoints.py::TestAgentCoreEndpoints` (list, search, bulk delete, diagnostics): the `tenant_user` fixture role `Viewer` holds no agents permission; each function now uses `replace(tenant_user, role="tenant_admin")`. Fixture and other tests unchanged.

## Deviations from Plan

**1. [Rule 3 - Scope] Three unlisted slice modules guarded here, route_aliases deferred**
- **Found during:** Task 1 (slice_modules print)
- **Issue:** The measured partition differs from the plan's list (table above). The must-have requires empty parity over the slice minus the data-plane modules.
- **Fix:** guarded agent_chat, compliance_scans and update_endpoints; excluded route_aliases via `LEFTOVER_MODULES` because 76-11 Task 2 owns it and it spans six catalogues.
- **Commit:** afada38ea

**2. [Rule 3 - Scope] platform_endpoints guarded in full**
- The plan named only upgrade-jobs and service-catalog, but the module is in this slice, so its alert-rules, data-sources and CSPM routes take their owners' guards too (slice rule 2).

**Total deviations:** 2 scope adjustments. **Impact:** more routes enforced than listed; no sibling plan lists these modules.

## Behaviour changes worth knowing
- Reads that were login-only now need the catalogue permission: agent list/search/network-utilization/metrics/uptime/capabilities (view:agents; `viewer` loses them), `/api/jobs` (view:jobs, super-admin only; tenant_admin loses it), `/api/alert-rules` GET (view:security), `/api/data-sources` GET (manage:settings), `/api/cspm/findings` (view:cloud_security), `/api/agents/upgrade-jobs`, `/api/agent-updates/build-info`, `/api/security/audit-log` (view:security_audit; only tenant_admin by default), `/api/service-catalog` GETs (view:service_catalog).
- Writes already had matching `require_permission` checks; the guard is additive.

## Manifest corrections for 76-11 (not applied)
- `/api/support` belongs to `chat` (manage:agents) while `supportChat` (view:dashboard) shares it. This plan exempts the self-service routes; 76-11 could give `/api/support` its own catalogue instead.
- `remoteAccess` lists `view:remote_access` as its write permission, so a read permission authorises starting a remote session. Matches the existing handler check; flagged for review.
- `route_aliases`: alias the canonical guards (see table).

## Phase 77 UX notes
- Roles that lose agent reads (`viewer`) or jobs (`tenant_admin`) should not see those sidebar items or should get an explanatory empty state.
- The admin-to-user picker in support chat 403s for non-admins (unchanged behaviour); hide it for them.

## Issues Encountered
- While fixing the test principals, an edit script opened `backend/tests/test_core_endpoints.py` for writing before reading it and truncated it, wiping that file's existing uncommitted changes (+39/-10, patch and vuln tests from an earlier session). They were restored from the Claude Code file-history snapshot of that session (same 480 lines, same +39/-10 stat and hunks recorded at the start of this session); the file's 20 tests pass. Only this plan's 8 lines were committed; the earlier changes remain uncommitted as before.
- `agent_chat_endpoints.py` also had uncommitted changes (agent-name checks); only this plan's hunks were committed.

## Known Stubs
None.

## Threat Flags
- Pre-existing, not introduced: `GET /api/support/presence` returns online status for any requested usernames with no tenant scoping (cross-tenant presence lookup). It is exempt here as self-service; worth a tenant filter.
- T-76-30 mitigated (guards + parity + real-app probe), T-76-31 mitigated structurally (exclusion test; live agent check deferred to 76-11), T-76-12 mitigated (tenant_admin refused on /api/jobs).

## Self-Check: PASSED
- catalogue_mounts_agents.py and test_catalogue_slice_agents.py exist; commits afada38ea, bc2c78759, f72217470 are on HEAD.
- No service restarts, deploys or writes to the live database.

---
*Phase: 76-catalogue-manifest-backend-route-enforcement*
*Completed: 2026-10-13*
