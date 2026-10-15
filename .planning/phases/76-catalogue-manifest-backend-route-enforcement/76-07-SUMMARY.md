---
phase: 76-catalogue-manifest-backend-route-enforcement
plan: 07
subsystem: api
tags: [rbac, catalogue-manifest, secops, siem, edr, alerts, d-02]

requires:
  - phase: 76-catalogue-manifest-backend-route-enforcement
    provides: catalogue_guard / MOUNTS convention / parity helpers (76-01), full manifest (76-02)
provides:
  - backend/catalogue_mounts_secops.py (26 MOUNTS entries plus 10 named guards for per-route use)
  - route-level catalogue guards in 10 mixed or straddling modules (alert, EDR, response, deception, security cases, XDR hunts, security keys/ops, AI, threat)
  - backend/tests/test_catalogue_slice_secops.py (parity, manifest drift, public/agent exclusion, real-app 403/200, write strings)
affects: [76-11, 76-12, 77]

requirements-completed: [ACC-04]

actuals:
  tokens: 14000
  tasks: 3
  commits: 2
plan_head_before: 0b05b5cc60fa40c78f529d374afd9a3b6cc9c969
plan_head_after: b2ca8516e2f19ba8465a0173ba68a22cdb87a65f

tech-stack:
  added: []
  patterns:
    - "Named guards exported from the slice mount file and imported by route files for per-route guarding (same as 76-05/76-06)"
    - "Guard drift test: every MOUNTS entry and named guard is compared to the manifest's resolved read/write"

key-files:
  created:
    - backend/catalogue_mounts_secops.py
    - backend/tests/test_catalogue_slice_secops.py
  modified:
    - backend/alert_endpoints.py
    - backend/response_endpoints.py
    - backend/edr_telemetry_endpoints.py
    - backend/deception_endpoints.py
    - backend/security_cases_endpoints.py
    - backend/future_ops_endpoints.py
    - backend/security_keys_endpoints.py
    - backend/security_ops_endpoints.py
    - backend/ai_endpoints.py
    - backend/threat_endpoints.py

key-decisions:
  - "security_endpoints is an aggregator (cases, keys, ops, scans), so those sub-routers are guarded per route, never by a mount on the aggregator"
  - "ai_endpoints and threat_endpoints straddle catalogues (threatHunting, threatIntelligence, settings); guarded per route with the owning catalogue's guard"
  - "Existing guards stay; the catalogue guard is additive (PROH-76-01). Writes keep the manifest strings, no route demands manage:security"

coverage:
  - id: D1
    description: "parity_offenders over slice_modules('secops') is empty (36 modules)"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_slice_secops.py#test_secops_slice_parity"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every slice guard equals the manifest's resolved read/write; mount keys are the ones router_registry loads"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_slice_secops.py#test_secops_guards_match_manifest"
        status: pass
    human_judgment: false
  - id: D3
    description: "POST /api/edr/events, the deception webhook, POST /api/alerts and the response task routes carry no guard"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_slice_secops.py#test_secops_public_routes_untouched"
        status: pass
    human_judgment: false
  - id: D4
    description: "Real app: a role without view:security gets 403 on /api/alerts and /api/siem and nine more reads; security_analyst and tenant_admin are not refused; writes with existing strings pass"
    requirement: ACC-04
    verification:
      - kind: integration
        ref: "backend/tests/test_catalogue_slice_secops.py#test_secops_real_app_enforced"
        status: pass
      - kind: integration
        ref: "backend/tests/test_catalogue_slice_secops.py#test_secops_writes_use_existing_strings"
        status: pass
    human_judgment: false
  - id: D5
    description: "Live check that agents still post EDR events, alerts and response task results after deploy"
    verification: []
    human_judgment: true
    rationale: "Structural proof only (D3); nothing was deployed or restarted."

duration: 40min
completed: 2026-10-15
status: complete
---

# Phase 76 Plan 07: SecOps Slice Summary

**Detection and response catalogues (alerts, SIEM, MITRE, threat intel, correlations, rules, hunting, connectors, copilot, YARA, MDR, EDR, XDR, war room, NDR, UEBA, email security, FIM, drift, persistence, simulation, agent groups, deception, security cases) now refuse callers without the manifest permission; EDR ingest, the deception webhook, agent alert ingest and response task routes stay unguarded.**

## Accomplishments
- `catalogue_mounts_secops.py`: 26 MOUNTS entries for user-only routers and 10 named guards (security, EDR, deception, XDR, incident response, incident impact, threat hunting, threat intel, plus re-exports of alert management, settings, security audit and vulnerability guards).
- Per-route guards in 10 modules; agent, agent-capable and public routes skipped.
- `test_catalogue_slice_secops.py`: 5 tests.

## slice_modules("secops") vs expected
Actual (36). Expected plan list was fully covered; differences:

| Module | Handling |
|---|---|
| `ai_endpoints` (not in plan) | tie-break put it in secops: `/api/ai/threat-hunt` (threatHunting) and `/api/ai/test-connection` (settings) guarded per route; its other routes are out of scope |
| `threat_endpoints` | straddles threatHunting (`/api/ai/threat-hunt`) and threatIntelligence (`/api/ai/reputation/*`); per route |
| `security_keys_endpoints`, `security_ops_endpoints` | reached through the `security_endpoints` aggregator; per route (`/api/security/generate-keypair`, `/api/security/encrypt`); ops already carried agents and audit-log guards from 76-05 |
| `itdr_endpoints`, `ot_ics_endpoints`, `insider_threat_endpoints` (not in plan) | pure user routers, mounted (ueba, ndr, insiderThreat owners) |
| `ip_ban_endpoints` | mounted with the security guard |
| `security_cases_endpoints` | `/api/vulnerability-scans` is owned by vulnerabilityManagement and `/api/security/incident-impact` by incidentImpact; each takes its own owner's guard |
| `response_endpoints`, `alert_endpoints` | mixed (agent-capable task routes / `POST /api/alerts`); per route |
| `ueba_service`, `binary_analysis`, `security_intel_status`, `agent_group`, `simulation` etc. | mounted as listed |

Mounted by module router_registry actually imports (lesson from 76-06); parity empty.

## Task Commits
1. Tasks 1-2: `89cd25f5e` (feat): secops mount map
2. Task 3: `b2ca8516e` (feat): route-level guards and the slice test

## Numbers
- Slice file 5 + `test_route_auth_baseline.py` 20 + `test_catalogue_route_parity.py` 7 = 32 passed.
- Full backend suite: 3677 passed, 47 skipped, 0 failed (baseline 3672; +5 new tests) in 4m28s.

## Tests changed to fix 403s
None. No existing test failed.

## Deviations from Plan

**1. [Rule 3 - Scope] Unlisted modules guarded**
- `ai_endpoints`, `itdr_endpoints`, `ot_ics_endpoints`, `insider_threat_endpoints`, `threat_endpoints`, `security_keys_endpoints`, `security_ops_endpoints` are in `slice_modules("secops")` though the plan did not list them; the must-have is empty parity over the slice.

**2. [Process] Commit split**
- The detection and response tasks share one mount file and the slice test needs the route-level guards to pass parity, so the mount map is one commit and the route-level guards plus the test are the second. `alert_endpoints.py` and `ai_endpoints.py` had other uncommitted edits (agent alert `reportedByAgent`, a `datetime` import); only the guard hunks were staged and the others were left in the working tree.

**3. [Process] First-draft test paths**
- Two probe paths in the first draft of the real-app test were wrong (404); corrected before commit.

**Total deviations:** 3 scope/process adjustments. **Impact:** none beyond extra routes enforced.

## Behaviour changes worth knowing
Reads that were login-only now need the catalogue read permission (or its `manage:` twin). Default roles holding each (from `rbac_defaults.ROLE_DEFAULTS`):
- `view:security` (alerts, SIEM, MITRE, correlations, EDR, deception, NDR, UEBA, email, insider threat, YARA, ...): tenant_admin, user, analyst, security_analyst, incident_responder, platform_support. `viewer` and the other roles are now refused.
- `/api/detection-rules*` needs `view:detection_rules` and `/api/fim*` needs `view:fim`: only tenant_admin and platform_support hold them, so `user`, `analyst`, `security_analyst` lose these reads.
- `/api/ai/reputation/*` previously needed `view:security`; the manifest owner threatIntelligence needs `view:threat_intel` (tenant_admin, analyst, security_analyst, platform_support); `user` and `incident_responder` lose it.
- `/api/security-cases`, `/api/security-events`, `/api/security/incident-impact` need `investigate:security` for reads (tenant_admin, analyst, security_analyst, incident_responder); `user` loses them.
- Writes already carried `require_permission` / `has_permission`; the guard is additive (PROH-76-01).

## Manifest corrections for 76-11 (not applied)
- `threatHunting.write` is `["view:threat_hunting"]` and `threatIntelligence.write` is `["view:threat_intel"]`: view strings listed as writes, so any holder passes the catalogue guard on POST (the route-level `require_permission` still decides). Likely intended `manage:` or `investigate:security`.
- `correlations.write` includes `view:security` (same pattern).
- `detectionRules.read` (`view:detection_rules`) and `fimMonitoring.read` (`view:fim`) are held only by tenant_admin and platform_support; the analyst roles used to read these pages. Either grant them in `rbac_defaults` or point the read at `view:security`.
- `incidentResponse.read` is `investigate:security` (not a `view:` string), so `user` role loses the cases list it could read before; confirm intent.
- `/api/ai/threat-hunt` is defined in both `ai_endpoints` and `threat_endpoints` (same path, two modules); the first mounted wins. Not changed.

## Phase 77 UX notes
- Sidebar and route gating should use the manifest read permission, so roles that now get 403 (viewer; user on detection rules/FIM/cases/reputation) do not see dead items.
- `future_ops_endpoints` other routes (unified ops, streaming) are owned by non-enforced groups and stay login-only.

## Known Stubs
None.

## Threat Flags
None. No new endpoints, auth paths or schema.

## Self-Check: PASSED
- Files exist: backend/catalogue_mounts_secops.py, backend/tests/test_catalogue_slice_secops.py.
- Commits 89cd25f5e and b2ca8516e are ancestors of HEAD.
- Acceptance: parity_offenders over slice_modules("secops") empty; public ingest and webhook routes untagged; full suite 3677 passed, 0 failed.
