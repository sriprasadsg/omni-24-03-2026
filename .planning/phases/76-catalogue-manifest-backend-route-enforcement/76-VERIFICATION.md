---
phase: 76-catalogue-manifest-backend-route-enforcement
verified: 2026-10-15T21:30:00Z
status: gaps_found
score: 4/5 must-haves verified
covered_files:
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-01-PLAN.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-01-SUMMARY.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-02-PLAN.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-02-SUMMARY.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-03-PLAN.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-03-SUMMARY.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-04-PLAN.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-04-SUMMARY.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-05-PLAN.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-05-SUMMARY.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-06-PLAN.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-06-SUMMARY.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-07-PLAN.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-07-SUMMARY.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-08-PLAN.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-08-SUMMARY.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-09-PLAN.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-09-SUMMARY.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-10-PLAN.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-10-SUMMARY.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-11-PLAN.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-11-SUMMARY.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-12-PLAN.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-12-SUMMARY.md"
  - "App.tsx"
  - "backend/asset_finance_fields.py"
  - "backend/catalogue_guards.py"
  - "backend/catalogue_mounts.py"
  - "backend/router_registry.py"
  - "backend/tests/_catalogue_parity.py"
  - "backend/tests/test_catalogue_route_parity.py"
  - "components/Sidebar.tsx"
  - "shared/catalogue-access.json"
  - "shared/catalogue-gaps.json"
  - "src/__tests__/catalogueAccess.test.ts"
  - "utils/catalogueAccess.ts"
covered_digest: "v3:sha256:60b3f6a94bdc32e08059de8b9b6b568ff93885fc4c2911da5dc73319d78396d0"
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "A user lacking the matching view: permission receives 403, not data, from the Assets, ITAM, Settings, financial, identity, and security-operations route groups (roadmap SC2)"
    status: partial
    reason: "814 route methods are guarded and tested, but two agent_capable routes in enforced catalogues carry no guard at all (WR-01), and five tenant GET routes are marked catalogue_exempt although they return role-restricted admin data to any signed-in tenant role (WR-05). Neither set is visible to the parity gate, so the gate stays green while data reaches a role whose sidebar item is hidden."
    artifacts:
      - path: "backend/software_endpoints.py"
        issue: "GET /api/software/download/{filename} (softwareUpdates) uses get_current_user_or_agent with no permission check; any signed-in tenant user, including a viewer without view:software_updates, can download any installer from the shared uploads/repo directory. The guarded sibling GET /api/software/repository hides the same listing from that role."
      - path: "backend/response_endpoints.py"
        issue: "GET /api/response/tasks/{agent_id} (edr) uses get_current_user_or_agent; checks only that the agent is in the caller's tenant, so any signed-in user can read an agent's queued response-task payloads (isolate, kill, quarantine)."
      - path: "backend/tenant_enrollment_endpoints.py"
        issue: "GET /api/tenants/{id}/allowlist and /enrollment-keys carry catalogue_exempt(TENANT_OWN_SCOPE); _assert_tenant_read pins the tenant, not the role, so a viewer / itam_viewer reads the enrolled-hardware allowlist (serials, SMBIOS UUIDs, MACs) and the install-key list."
      - path: "backend/tenant_endpoints.py"
        issue: "GET /api/tenants/{id}/email/config, /email/preferences (and /license) are exempt on the same basis; SMTP host/user config and license seat data are readable by any tenant role."
    missing:
      - "An agent-tolerant guard variant (skip only the agent identity, apply the catalogue check to everyone else) mounted on the two agent_capable GET routes, with the walker counting it so the parity gate covers agent_capable routes (WR-01 fix)"
      - "A role-gated tag (for example read=manage:settings or view:agents) for the tenant allowlist, enrollment-keys and email-config GETs; keep catalogue_exempt only for branding and the app-shell license summary (WR-05 fix)"
      - "Tighten the exemption ratchet so an exemption reason that claims 'self-service' for a route returning role-restricted admin data is reviewed (the maxExemptRoutes: 34 ratchet only length-checks reasons)"
deferred: []
re_verification:
  previous_status: none
---

# Phase 76: Catalogue Manifest & Backend Route Enforcement Verification Report

**Phase Goal:** Each in-scope left-nav catalogue is defined once in a shared manifest, and the backend refuses what the sidebar would hide, with a deny-by-default test that fails whenever the two drift.
**Verified:** 2026-10-15T21:30:00Z
**Status:** gaps_found
**Re-verification:** No, initial verification

## Verdict

The mechanism the phase promised exists and works. One manifest, a frontend that reads it, a mount-time guard registry covering 814 route methods, a committed gap ledger, and a deny-by-default gate that is green on the real 1616-route app. The goal clause "the backend refuses what the sidebar would hide" is not fully true: two data-bearing routes in enforced catalogues have no guard, and five tenant GETs are exempted although they return admin-only data. These are narrow, nameable holes, not a broken design, and a short gap-closure plan closes them. They are reported as a partial failure of roadmap SC2 and not waved through, because the parity gate cannot see them and so cannot catch their recurrence.

## Goal Achievement

### Observable Truths

| # | Truth (roadmap success criterion) | Status | Evidence |
|---|-----------------------------------|--------|----------|
| 1 | One shared manifest maps every catalogue to its permission and routes; `Sidebar.tsx` and `App.tsx` both read it; the two divergent tables are gone; the 9 mismatched views resolve to one permission | VERIFIED | `shared/catalogue-access.json`: 202 catalogues, 188 `nav:true`, 8 groups. `Sidebar.tsx:5,211` builds `menuGroups` from `NAV_GROUPS`; `App.tsx:239,444,499,1023,1173` call `viewPermission`/`viewForHash`/`NAV_GROUPS`. No `viewPermissionMap` in repo source (the only hit is a pinned negative assertion in `catalogueAccess.test.ts:171`; the `version 1/App.tsx` hit is a stale copy outside the app). All 9 views independently confirmed in the JSON as exactly the Sidebar string (agentCapabilities `view:agent_capabilities`, jobs `view:jobs`, llmops `view:llmops`, persistenceDetection `view:persistence`, sustainability `view:sustainability`, swarm `view:swarm`, unifiedOps `view:unified_ops`, vulnerabilityManagement `view:vulnerabilities`, zeroTrustQuantum `view:zero_trust`). subscriptionManagement/invoices/knowledgeBase = `manage:settings`, finops = `view:finops` (D-08). |
| 2 | Lacking `view:` gets 403 (not data) from Assets, ITAM, Settings, financial, identity, security-operations, while a holder still gets 200; asset reads hide purchase-cost fields without `view:itam` | FAILED (partial) | Guarded part holds: independent real-app probe returned 403 for role `nobody` on `/api/assets`, `/api/settings/llm`, `/api/finops/costs`, `/api/users`, `/api/alerts`, `/api/siem/events`, `/api/patches`, `/api/agents` and 403 for `viewer` on settings/users/alerts/siem/patches/agents; permitted roles passed the guard (500 only because the throwaway Mongo is unreachable). Finance strip verified: `asset_finance_fields.finance_filtered` wraps `get_assets`, `search_assets`, `get_asset_details`, sits outside `@cached`, builds new dicts; cache cross-caller and no-mutation tests pass. Not holding: WR-01 and WR-05 (see gaps). Every one of the 667 remaining unguarded user routes is in a non-enforced group or the ledger; every enforced-group user route is tagged (814) or exempt (34). The "holder gets 200" half is only proven as `!= 403` on the real app (WR-06); see Human Verification. |
| 3 | Agent enrollment/heartbeat on `/api/agents/*` and API-key callers on ITAM routers keep working unchanged | VERIFIED (static; live check listed) | Walker over the real app: `POST /api/agents/register` public, `/api/agents/heartbeat` and `/{id}/heartbeat` auth `agent`, all with 0 catalogue tags and no exemption; all 29 `agent` and 15 `agent_capable` records carry 0 tags. `test_itam_api_key_unchanged` passes (`view:itam` scope reads, `view:assets` scope refused). Guard auth callable matches each route's own (`ITAM_API_KEY_GUARD` uses `get_current_user_or_api_key`). Reviewer additionally confirmed no WebSocket, Stripe, Jira/Zoho or SSO/LDAP sign-in route gained a guard. Live agent poll/report after deploy not testable here. |
| 4 | A committed gap ledger lists every unguarded router; the parity test fails if an in-scope route is unguarded or an unguarded router is missing from the ledger | VERIFIED | `shared/catalogue-gaps.json` committed with per-router `maxUnguardedRoutes` ratchets, `agentAuthExcludedRoutes: 15`, `maxExemptRoutes: 34`. Re-ran `parity_offenders` and `ledger_offenders` on the live walk: 0 and `[]`. Negative controls exist and pass for untagged route, wrong tag, unledgered router, over-ratchet, ratchet slack, stale entry, unmounted module, enforced route in ledger, duplicate entry, agent-capable and exempt over-ratchet (`test_catalogue_route_parity.py`, 25 tests). |
| 5 | A frontend test fails when sidebar and manifest drift | VERIFIED | `catalogueAccess.test.ts` + `SidebarAuditFixes.test.tsx`: 34 passed on re-run. `findNavDrift` is tested in both directions, `manifest nav views and presentation keys have no drift` runs on the real data, and a source-text test pins that `Sidebar.tsx` has no item-level permission literal. Because `Sidebar.tsx` builds from `NAV_GROUPS`, a nav item cannot exist without a manifest entry. |

**Score:** 4/5 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `shared/catalogue-access.json` | Complete manifest | VERIFIED | 202 entries, enforce:true only for infra, security, mgmt |
| `backend/catalogue_guards.py` | `catalogue_guard`, `check_catalogue_access`, `catalogue_exempt`, `manage_twin` | VERIFIED | Substantive; role check precedes API-key scope narrowing; additive |
| `backend/catalogue_mounts.py` + 7 slice files | Mount registry | VERIFIED | Wired through `router_registry._load` -> `mount_dependencies`; all keys resolve per review |
| `backend/asset_finance_fields.py` | Finance strip | VERIFIED | Wired in `asset_endpoints.py:64,109,163` |
| `backend/tests/_route_walk.py`, `_catalogue_parity.py` | Walker and parity helper | VERIFIED | Run against real app: 1616 routes |
| `shared/catalogue-gaps.json` | Gap ledger | VERIFIED | Enforced by `test_unguarded_routers_are_ledgered`, `test_ledger_ratchets` |
| `utils/catalogueAccess.ts`, `components/sidebarPresentation.tsx` | Frontend reader / presentation | VERIFIED | Imported by `Sidebar.tsx` and `App.tsx` |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `router_registry.py` | `catalogue_mounts.py` | `mount_dependencies` at include time | WIRED | 814 tagged route methods observed on the real app |
| `catalogue_mounts_*.py` | `catalogue_guards.py` | `catalogue_guard(...)` | WIRED | Tags attached as `__catalogue_guard__` metadata and matched by value to the manifest |
| `_catalogue_parity.py` | `shared/catalogue-access.json` | `json.load`, tag equality | WIRED | Tag read/write lists must equal manifest-resolved lists |
| `Sidebar.tsx`, `App.tsx` | `utils/catalogueAccess.ts` | `NAV_GROUPS`, `viewPermission`, `viewForHash` | WIRED | Confirmed by grep and by `catalogueAccess.test.ts` |
| `asset_endpoints.py` | `asset_finance_fields.py` | `@finance_filtered` | WIRED | |

### Data-Flow Trace (Level 4)

| Artifact | Data variable | Source | Real data | Status |
|----------|---------------|--------|-----------|--------|
| `Sidebar.tsx` `menuGroups` | `NAV_GROUPS` | JSON manifest, same file the backend tests read | Yes | FLOWING |
| `App.tsx` `handleSetCurrentView` | `viewPermission(view)` | manifest | Yes (cast hides `undefined`, IN-04; every AppView has an entry per test) | FLOWING |
| `finance_filtered` | caller permission via `verify_permission` | role doc / defaults | Yes | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Guard, manifest, parity, all 8 slice tests, finance, route-auth baseline | `pytest tests/test_catalogue_guards.py test_catalogue_manifest.py test_catalogue_route_parity.py test_catalogue_slice_*.py test_asset_finance_fields.py test_route_auth_baseline.py` | 132 passed in 502 s | PASS |
| Frontend drift and sidebar tests | `npx vitest run src/__tests__/catalogueAccess.test.ts src/__tests__/SidebarAuditFixes.test.tsx` | 34 passed | PASS |
| Whole-app parity and ledger on a fresh walk | `run_real_app_walk()` + `parity_offenders` + `ledger_offenders` | 1616 routes, offenders 0 / `[]` | PASS |
| 403 for roles lacking the permission, 9 route families | `probe_real_app` | `nobody` 403 on all nine; `viewer` 403 on settings, users, alerts, siem, patches, agents | PASS |
| No auth dependency removed in phase 76 commits | `git show` over `(76-` commits, grep removed `Depends(`/`require_permission`/`verify_permission`/`get_current_user` | no lines | PASS (PROH-76-01) |
| `rbac_service.py` / `rbac_defaults.py` untouched by phase 76 | `git log --grep "(76-"` on both | no commits | PASS (D-07) |
| Full backend suite (3721 passed) and `npm run build` | not re-run; orchestrator-supplied evidence, no source change since 76-11 | n/a | accepted as given |

### Probe Execution

Step 7b/7c: no `probe-*.sh` scripts declared or present for this phase. SKIPPED. The in-process `probe_real_app` harness above is the phase's own runtime probe.

### Requirements Coverage

| Requirement | Source plans | Description | Status | Evidence |
|-------------|--------------|-------------|--------|----------|
| ACC-03 | 76-01, 76-02, 76-03 | Single shared manifest; frontend reads it; 9 mismatched views reconciled | SATISFIED | Truth 1 |
| ACC-04 | 76-01, 76-02, 76-04 .. 76-12 | Route guards on priority router groups; gap ledger; agent routes excluded | SATISFIED with residual holes | Guards and ledger verified; exclusion of agent routes correct; WR-01 and WR-05 are leaks inside the guarded groups. REQUIREMENTS.md marks it Complete, which overstates by those routes. |
| ACC-05 | 76-01, 76-02 (hand-off), 76-03, 76-11 | Deny-by-default parity test plus frontend drift test | SATISFIED | Truths 4 and 5. Gate scope caveat: `agent_capable` and `catalogue_exempt` routes are only ratcheted by count, not examined. |

All three IDs appear in plan frontmatter and in REQUIREMENTS.md. No orphaned Phase 76 requirements (ACC-06..09 map to Phase 77).

### Code-Review Findings Against the Goal

76-REVIEW-DISPOSITION.md lists all 10 findings as `open`. Verified by reading the code:

| ID | Confirmed in code | Effect on goal |
|----|-------------------|----------------|
| WR-01 | Yes (`software_endpoints.py:113`, `response_endpoints.py:192`) | Breaks "backend refuses what the sidebar would hide"; gap above |
| WR-05 | Yes (`tenant_enrollment_endpoints.py:67,121`; `_assert_tenant_read` pins tenant only) | Same; gap above. Pre-existing from spec C2-C4, but this phase chose to exempt rather than gate |
| WR-02 | Yes (`catalogue_mounts_settings_ops.py:63-75` keys on `role == "api-integration"`; `api_key_auth.py:282` sets no distinguishing `auth_source`; role-name validation reserves only built-in keys) | Warning. A tenant admin who can already grant `manage:settings` gains little; still a role-name-based decision copied into new code |
| WR-03 | Yes (`ITAM_READ = ("view:itam",)` vs `_require_itam_viewer` accepting `manage:assets`) | Warning. A custom role holding `manage:assets` without `view:itam`/`manage:itam` loses ITAM read; built-ins unaffected. Over-refusal, not a leak |
| WR-04 | Per review (secrets read needs `manage:settings`, `view:secrets` holders refused; write list contains a `view:` string) | Warning. Over-refusal for `platform_support`-style roles; writes unguarded by catalogue for `view:secrets` holders |
| WR-06 | Yes (permitted-role assertions are `!= 403`) | Weakens confidence that permitted roles reach a 200 |
| IN-01..IN-04 | Per review | Info; quality and drift risk, no current exposure |

None of WR-02..WR-06 independently fails a must-have; WR-01 and WR-05 do, for SC2.

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| phase files | `TBD`/`FIXME`/`XXX` markers | none found | clean |
| `backend/catalogue_guards.py:18`, `catalogue_mounts_assets.py:14` | unused imports (IN-02) | Info | lint only |
| `App.tsx:1173` | `viewPermission(view) as Permission` (IN-04) | Info | fails closed for non-super-admin today; Phase 77 owns |
| `shared/catalogue-access.json` write lists with `view:dashboard` (IN-01) | guard is a no-op for writes in ~12 catalogues | Warning | each non-GET route checked by reviewer carries its own permission check |

### Human Verification Required

These cannot be run here (no restarts, deploys or live DB) and do not change the status above, which is already `gaps_found`. They should be done after the gap-closure plan.

1. **Enrolled Rust agent after deploy.** Test: deploy, then watch an enrolled agent register, heartbeat, poll `/api/agentic-tasks`, `/api/agents/{id}/instructions`, and post telemetry/scan results. Expected: no 401/403 on any agent route; agent list in UI unchanged. Why human: needs a live agent, TLS pin and the real DB.
2. **Roles that lost reads see no broken pages.** Test: sign in as `viewer`, `itam_viewer`, `analyst`, and a custom role against the left nav. Expected: any page whose backend now returns 403 either is hidden or shows a handled state, not a blank or crash. Why human: visual; 76-UI-REVIEW.md scored 16/24 with frontend follow-ups routed to Phase 77.
3. **Permitted role gets real 200s.** Test: with live data, call one read per enforced catalogue as a permitted role. Expected: 200 with data. Why human: the real-app probes run on an unreachable DB and prove only "not 403" (WR-06).
4. **ITAM API-key caller live.** Test: call an ITAM read with an existing key scoped `view:itam`. Expected: 200. Why human: needs live key and DB.

### Gaps Summary

One gap, affecting roadmap SC2 and, through it, the "backend refuses what the sidebar would hide" clause of the goal and the completeness of ACC-04.

- Two `agent_capable` GET routes (`/api/software/download/{filename}`, `/api/response/tasks/{agent_id}`) in enforced catalogues have no human-path guard.
- Five tenant GETs (`allowlist`, `enrollment-keys`, `email/config`, `email/preferences`, plus `license`) are `catalogue_exempt` as "self-service" although they return admin-only data to any tenant role.
- The parity gate cannot see either class (`_in_scope` returns `None` for non-`user` auth; exempt routes are count-ratcheted with length-checked reasons), so the gate's green result is true but narrower than the goal sentence implies.

Nothing here is deferred: Phase 77 is frontend/role-visibility/regression tests, ACC-F2 covers only non-enforced groups, and Phase 78 builds on the ITAM guard. A single focused gap-closure plan (agent-tolerant guard variant plus role-gated tags for the tenant reads, then extend the walker to count `allow_agent` guards) is the right size. WR-02..WR-06 are worth folding into the same plan but are not blockers. 4 of 5 roadmap criteria are fully verified, ACC-03 and ACC-05 are met, and no regression of existing auth was found (no auth dependency removed, RBAC defaults untouched).

---

_Verified: 2026-10-15T21:30:00Z_
_Verifier: Claude (gsd-verifier)_
