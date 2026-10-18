---
phase: 76-catalogue-manifest-backend-route-enforcement
verified: 2026-10-18T18:10:00Z
status: human_needed
score: 5/5 must-haves verified
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
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-13-PLAN.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-13-SUMMARY.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-14-PLAN.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-14-SUMMARY.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-15-PLAN.md"
  - ".planning/phases/76-catalogue-manifest-backend-route-enforcement/76-15-SUMMARY.md"
  - "App.tsx"
  - "backend/agent_chat_endpoints.py"
  - "backend/asset_finance_fields.py"
  - "backend/catalogue_guards.py"
  - "backend/catalogue_mounts.py"
  - "backend/catalogue_mounts_billing_identity.py"
  - "backend/response_endpoints.py"
  - "backend/route_aliases.py"
  - "backend/router_registry.py"
  - "backend/software_endpoints.py"
  - "backend/tenant_endpoints.py"
  - "backend/tenant_enrollment_endpoints.py"
  - "backend/tests/_catalogue_parity.py"
  - "backend/tests/_route_walk.py"
  - "backend/tests/test_catalogue_guard_variants.py"
  - "backend/tests/test_catalogue_route_parity.py"
  - "backend/tests/test_catalogue_slice_billing_identity.py"
  - "components/Sidebar.tsx"
  - "shared/catalogue-access.json"
  - "shared/catalogue-gaps.json"
  - "src/__tests__/catalogueAccess.test.ts"
  - "utils/catalogueAccess.ts"
covered_digest: "v3:sha256:36ace10acb4d2c926a9db25b499448ef3fc8697ab65de6003cfdbcaf75dcec8d"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 4/5
  gaps_closed:
    - "SC2 / WR-01: agent-capable routes in enforced catalogues had no human-path guard (installer download, response-task poll, agent-chat session list)"
    - "SC2 / WR-05: five tenant GETs marked catalogue_exempt returned role-restricted admin data to any signed-in tenant role"
    - "Review CR-01: GET /api/tenants/me returned the whole tenant document (registration key, SMTP settings, API keys, seat data) to every signed-in role"
  gaps_remaining: []
  regressions: []
gaps: []
deferred: []
advisory:
  - finding: "Self-service exemption rule (PROH-76-08) is lexical: it matches reasons starting 'self-service' on four literal placeholders only (review WR-01)"
    category: security
    reason: "It could not have caught CR-01 (no placeholder in the path). The CR-01 instance is fixed and has its own test; the class is still guarded only by human review of the exemptRoutes ledger. A behavioural sentinel-secret probe over every exempt GET would close it."
    evidence_status: "reproduced by reading backend/tests/_catalogue_parity.py; not exploitable today"
  - finding: "agent_tolerant() rebuilds the guard without platform_read (review WR-02)"
    category: other
    reason: "Latent: no guard combines allow_agent with platform_read today, so nothing is refused wrongly. A future combination would silently drop platform staff."
    evidence_status: "code read, catalogue_guards.py agent_tolerant()"
  - finding: "Untagged agent-capable writes rely on prose reasons in agentCapableRoutes (review IN-03), e.g. POST /api/agents/{agent_id}/raise-ticket lets any tenant role raise a ticket for an agent in its tenant"
    category: other
    reason: "A write that creates a support ticket, not a read of restricted data; the roadmap criterion is about reads returning 403. The reason text is reviewed, not verified."
    evidence_status: "handler agent_tasks_endpoints.raise_ticket_via_agent read: tenant-pinned, no permission check"
  - finding: "Open older review findings WR-03, WR-04, WR-06, IN-01, IN-02, IN-04 (and WR-02 above)"
    category: other
    reason: "Over-refusal, test-strength and code-quality items recorded in 76-REVIEW-DISPOSITION.md as open; none lets data reach a role whose sidebar item is hidden."
    evidence_status: "dispositions read; no new evidence of exposure"
human_verification:
  - test: "Enrolled agent still works after deploy (agent route group)"
    expected: "After the backend is restarted on this checkout, an enrolled Rust agent registers, heartbeats, polls /api/agentic-tasks and /api/response/tasks/{agent_id}, downloads an installer from /api/software/download/{filename}, and posts telemetry/scan results with no 401/403; the UI agent list is unchanged."
    why_human: "Needs a live agent, its TLS pin and the real database. The route classification and the agent_tolerant bypass are proven in-process (agent identity gets 404/handler status, never 403), but the real token path is not."
  - test: "Tenant admin and platform staff reads of the five gated tenant GETs"
    expected: "Signed in as a tenant admin, then as Platform Support and Platform Billing, GET /api/tenants/{id}/allowlist, /enrollment-keys, /license (and, for tenant admin only, /email/config and /email/preferences) return 200 with data and the Tenant Management and Settings screens render them."
    why_human: "Probes on the throwaway app have an unreachable database, so the allowed side is proven only as 'not 401/403' (a 500 at the handler). Live data is needed to see a real 200."
  - test: "Viewer, itam_viewer and analyst refusals on live data"
    expected: "These roles receive 403 from the same five tenant GETs, the installer download, GET /api/response/tasks/{agent_id} and GET /api/agent-chat/sessions, and no screen they can still reach shows a blank page or crash because of it."
    why_human: "Refusals are proven in-process; whether the UI handles them gracefully is visual. Phase 77 (fail-closed sidebar) is planned to precede deploy."
  - test: "Tenant shell still renders after the GET /api/tenants/me projection (CR-01)"
    expected: "Logged in as viewer and tenant admin, the app shell shows tenant name, tier and branding; no screen is missing a field. The endpoint now returns only id, name, subscriptionTier and branding."
    why_human: "No frontend caller of the literal path /api/tenants/me was found by grep (the shell reads branding through /api/tenants/{id}/branding), but a dynamic caller cannot be excluded statically."
  - test: "Registration key exposure decision (CR-01)"
    expected: "Decide whether tenant registrationKey values were exposed to non-admin roles while the old GET /api/tenants/me was live (the backend running now still serves the old response until restart) and rotate them if so."
    why_human: "An operational and security decision for the owner, and a live-environment fact; the fix only takes effect on restart."
---

# Phase 76: Catalogue Manifest & Backend Route Enforcement Verification Report

**Phase Goal:** Each in-scope left-nav catalogue is defined once in a shared manifest, and the backend refuses what the sidebar would hide, with a deny-by-default test that fails whenever the two drift.
**Verified:** 2026-10-18T18:10:00Z
**Status:** human_needed
**Re-verification:** Yes, after gap closure (plans 76-13, 76-14, 76-15 and the CR-01 fix)

## Verdict

The goal is achieved in the committed code. The two reasons the previous report was `gaps_found` are closed, and the one new critical defect found by the 2026-10-18 code review (CR-01) is fixed and tested. I re-derived the evidence rather than reading the summaries: a fresh walk of the real 1616-route app, an independent probe of the eight formerly failing routes, and re-runs of the catalogue test files (191 passed, 34 frontend tests passed). What is left is live-environment confirmation that this machine cannot do (a real agent, a real database, a deploy), plus open review findings that do not let data reach a role whose sidebar item is hidden. Status is therefore `human_needed`, not `passed`.

HEAD content was judged: for every file listed in `covered_files` that is not a planning document, `git diff HEAD --ignore-cr-at-eol` against the working tree is empty (the working tree differs from HEAD only by mode bits and line endings).

## Goal Achievement

### Observable Truths

| # | Truth (roadmap success criterion) | Status | Evidence |
|---|-----------------------------------|--------|----------|
| 1 | One shared manifest maps every catalogue to its permission and routes; `Sidebar.tsx` and `App.tsx` both read it; the divergent tables are gone; the 9 mismatched views resolve to one permission | VERIFIED | `shared/catalogue-access.json`: 202 catalogues, 188 `nav:true`, 8 groups. `components/Sidebar.tsx:5,211` builds `menuGroups` from `NAV_GROUPS`; `App.tsx:239,444,499,1023,1173` use `viewPermission`, `viewForHash`, `NAV_GROUPS`. `viewPermissionMap` appears only as a negative assertion in `src/__tests__/catalogueAccess.test.ts:171`. No frontend file changed since 76-15 (`git diff 15ef99ad7 HEAD` outside planning touches only `backend/route_aliases.py` and one test). |
| 2 | A user lacking `view:` gets 403, not data, from Assets, ITAM, Settings, financial, identity, security-operations, while a holder still gets 200; asset reads hide purchase-cost fields without `view:itam` | VERIFIED (live 200 and UI handling listed for humans) | See the gap-closure evidence below. Fresh walk of the real app: 822 tagged route methods, 29 exempt, 0 `user` routes in an enforced group without a tag or exemption, `parity_offenders` 0, `ledger_offenders` `[]`. Finance strip unchanged and its 11 tests pass. |
| 3 | Agent enrollment and heartbeat on `/api/agents/*` and API-key callers on the ITAM routers keep working unchanged | VERIFIED (static and in-process; live check listed) | Walk: no `agent` or `public` route carries a catalogue tag. All 15 agent-capable routes are either untagged (12, each on the reviewed `agentCapableRoutes` list) or carry `allow_agent: True` (3). Probe with the agent identity: `GET /api/software/download/...` 404 (handler reached), `GET /api/response/tasks/a1` 500 (handler reached, unreachable DB), `GET /api/agent-chat/sessions` 403 from the handler's own admin check, which is the unchanged pre-existing behaviour (plan 76-13 truth 3). `test_itam_api_key_unchanged` and `test_route_auth_baseline` pass. PROH-76-01 re-checked: gap commits remove only decorator lines that are re-added with the same `Depends(...)` plus the new guard. |
| 4 | A committed gap ledger lists every unguarded router; the parity test fails if an in-scope route is unguarded or an unguarded router is missing from the ledger | VERIFIED | `shared/catalogue-gaps.json` holds per-router ratchets plus the new reviewed lists `agentCapableRoutes` (12) and `exemptRoutes` (29, `maxExemptRoutes: 29`, `agentAuthExcludedRoutes: 12`). `test_catalogue_route_parity.py` (negative controls for untagged route, wrong tag, unledgered router, ratchet slack, stale entry, agent-capable and exempt lists, agent-refusing tag, self-service rule) passes. Independent re-run of the gate on a fresh walk: 0 offenders. |
| 5 | A frontend test fails when sidebar and manifest drift | VERIFIED | `npx vitest run src/__tests__/catalogueAccess.test.ts src/__tests__/SidebarAuditFixes.test.tsx`: 34 passed. `findNavDrift` is tested in both directions on real data, and a source-text test pins that `Sidebar.tsx` has no item-level permission literal. |

**Score:** 5/5 truths verified (0 present, behavior-unverified)

### Gap-closure evidence (the previously failed truth 2)

| Previous gap | Now | Evidence |
|--------------|-----|----------|
| WR-01 `GET /api/software/download/{filename}` unguarded for humans | CLOSED | `software_endpoints.py:118` `dependencies=[Depends(SOFTWARE_UPDATES_AGENT_GUARD)]`, built as `agent_tolerant(SOFTWARE_UPDATES_GUARD)`. Probe on the real app: viewer, itam_viewer, analyst, nobody all 403; tenant_admin, platform_support and the agent identity reach the handler (404 for a missing file). |
| WR-01 `GET /api/response/tasks/{agent_id}` | CLOSED | `response_endpoints.py:197` `EDR_AGENT_GUARD`. viewer, itam_viewer, nobody 403; analyst, tenant_admin, platform_support, agent reach the handler (500 only because the probe database is unreachable). |
| WR-01 `GET /api/agent-chat/sessions` | CLOSED | `agent_chat_endpoints.py:179` `CHAT_AGENT_GUARD`. viewer, itam_viewer, analyst, nobody 403; tenant_admin passes the guard. |
| WR-05 five tenant GETs | CLOSED | `tenant_endpoints.py:492,625` `SETTINGS_GUARD` (email config, preferences); `:714` and `tenant_enrollment_endpoints.py:67,121` `TENANT_CONTROLS_READ_GUARD` (license, allowlist, enrollment-keys). Probe: viewer, itam_viewer, analyst, nobody 403 on all five; tenant_admin and Super Admin reach the handler; platform_support and platform_billing (in the platform tenant) reach the three controls routes and are refused on the two email routes, which matches the handler's own `_assert_tenant_access` and the plan truth. Writes keep `TENANT_PLATFORM_STAFF` / `TENANT_MANAGEMENT_GUARD` plus the handler checks. |
| Review CR-01 `GET /api/tenants/me` full tenant document | CLOSED | `route_aliases.py:207-221` projects to `TENANT_ME_FIELDS = (id, name, subscriptionTier, branding)` both in the query projection and in the returned dict (so a store ignoring the projection still cannot leak). `test_tenants_me_returns_display_fields_only` seeds `registrationKey`, `emailConfig`, `apiKeys`, `license` and asserts none appears for viewer, itam_viewer, user and tenant_admin. Commits b2712aef0 (red) then 665b41941 (fix). |
| Gate blind to agent-capable and exempt routes | CLOSED | `_catalogue_parity._parity_scope` puts agent-capable safe-method routes under enforced groups in scope, `_refusing_tags` rejects any non-`allow_agent` tag on them, and `exemptRoutes` / `agentCapableRoutes` are reviewed ledger lists. |

### Prohibitions

| ID | Statement | Status | Evidence |
|----|-----------|--------|----------|
| PROH-76-05 | Only the auth layer's agent identity skips the catalogue check | VERIFIED | `catalogue_guards._require_catalogue` compares `user.role == AGENT_ROLE` (`"agent"`, `authentication_service.py:197`) exactly; `test_role_spelled_Agent_is_a_person` and `test_viewer_is_refused_on_an_agent_tolerant_guard` pass. Residual: the plan's flagged assumption that a tenant admin could assign the role string `agent` is a pre-existing auth-layer property (review confirms user roles are limited to built-in keys). |
| PROH-76-06 | No agent route gains a guard that refuses the agent | VERIFIED | Walk: no tag on any `agent` or `public` route; the three tags on agent-capable routes all carry `allow_agent`. |
| PROH-76-07 | Platform allowance never admits a tenant role or a non-safe method | VERIFIED | `check_catalogue_access` consults `platform_read` only when `safe`, validated against `PLATFORM_ONLY_PERMISSIONS` at construction, via `has_platform_permission`; `test_platform_support_reads_but_never_writes`, `test_platform_support_in_a_tenant_is_refused` pass. |
| PROH-76-08 | No exemption claims self-service for a route naming another tenant or user | VERIFIED (narrowly) | Rule exists and passes on the 29 exemptions; its lexical weakness is the advisory above. The one real violation it missed (CR-01) is fixed. |

The plan truth marked `verification: backstop` (the new guard paths hold no per-request or cross-request state) is directly observable: `catalogue_guards.py` has no module-level mutable state and the decision is a function of `TokenData`, method and the declared tuples.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `shared/catalogue-access.json` | Complete manifest | VERIFIED | 202 entries, settings catalogue owns the four nested tenant-control prefixes |
| `backend/catalogue_guards.py` | `catalogue_guard(allow_agent, platform_read)`, `agent_tolerant`, `check_catalogue_access`, `catalogue_exempt` | VERIFIED | Substantive; construction-time validation; additive |
| `backend/catalogue_mounts_billing_identity.py` | `TENANT_CONTROLS_READ_GUARD`, branding exemption | VERIFIED | Wired to the allowlist, enrollment-keys and license routes |
| `backend/tests/test_catalogue_guard_variants.py` | Variant unit, router and real-app tests | VERIFIED | Present, 32 tests, passing |
| `shared/catalogue-gaps.json` | Ledger with reviewed lists | VERIFIED | 12 + 29 entries, sorted, counts match the walk |
| `backend/tests/_catalogue_parity.py`, `_route_walk.py`, `test_catalogue_route_parity.py` | Gate and walker | VERIFIED | Run against the real app |
| `backend/route_aliases.py` | Projected `/api/tenants/me` | VERIFIED | Lines 204-221 |
| `utils/catalogueAccess.ts`, `components/Sidebar.tsx`, `App.tsx` | Frontend reader | VERIFIED | Imported and used |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| `software_endpoints.py` | `catalogue_guards.py` | `agent_tolerant(SOFTWARE_UPDATES_GUARD)` on GET `/download/{filename}` | WIRED |
| `response_endpoints.py` | `catalogue_guards.py` | `agent_tolerant(EDR_GUARD)` on GET `/tasks/{agent_id}` | WIRED |
| `agent_chat_endpoints.py` | `catalogue_guards.py` | `agent_tolerant(CHAT_GUARD)` on GET `/sessions` | WIRED |
| `tenant_enrollment_endpoints.py`, `tenant_endpoints.py` | `catalogue_mounts_*` | `Depends(TENANT_CONTROLS_READ_GUARD)` / `Depends(SETTINGS_GUARD)` | WIRED |
| `_catalogue_parity.py` | `catalogue_guards.py` | reads the `allow_agent` tag key | WIRED |
| `test_catalogue_slice_billing_identity.py` | `_route_walk.py` | `probe_real_app` | WIRED |
| `Sidebar.tsx`, `App.tsx` | `utils/catalogueAccess.ts` | `NAV_GROUPS`, `viewPermission`, `viewForHash` | WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data variable | Source | Real data | Status |
|----------|---------------|--------|-----------|--------|
| `get_my_tenant` | `tenant` | `mongodb.db.tenants.find_one({"id": tenant_id}, projection)` then field filter | Yes, real query, narrowed to four fields | FLOWING |
| `Sidebar.tsx` `menuGroups` | `NAV_GROUPS` | JSON manifest, same file the backend tests read | Yes | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Catalogue guards, manifest, parity gate, guard variants, all slice tests, finance fields, route-auth baseline | `backend/venv/bin/python -m pytest tests/test_catalogue_guards.py tests/test_catalogue_manifest.py tests/test_catalogue_route_parity.py tests/test_catalogue_guard_variants.py tests/test_catalogue_slice_*.py tests/test_asset_finance_fields.py tests/test_route_auth_baseline.py -q -p no:cacheprovider` (temp ticket and share dirs) | 191 passed in 540 s | PASS |
| Frontend drift and sidebar | `npx vitest run src/__tests__/catalogueAccess.test.ts src/__tests__/SidebarAuditFixes.test.tsx` | 34 passed | PASS |
| Whole-app parity and ledger on a fresh walk | `run_real_app_walk()` + `parity_offenders` + `ledger_offenders` | 1616 routes (1515 user, 57 public, 29 agent, 15 agent-capable); 0 offenders; 822 tagged methods; 29 exempt; 0 untagged unexempt user routes in enforced groups | PASS |
| 403 for lacking roles on the eight formerly failing routes; permitted and agent identities reach the handler | `probe_real_app` over 8 routes x up to 7 roles | see gap-closure table | PASS |
| Full backend suite, `npm run build`, `npx vitest run src/__tests__` | not re-run; orchestrator-supplied (3780 passed / 47 skipped / 0 failed at HEAD; 266 vitest passed; build exit 0) | n/a | accepted as given. The only non-planning changes since the frontend run are `route_aliases.py` and one backend test |

### Probe Execution

No `probe-*.sh` scripts are declared or present for this phase. SKIPPED. The in-process `probe_real_app` harness above is the phase's own runtime probe.

### Requirements Coverage

| Requirement | Source plans | Description | Status | Evidence |
|-------------|--------------|-------------|--------|----------|
| ACC-03 | 76-01, 76-02, 76-03 | Single shared manifest; frontend reads it; 9 mismatched views reconciled | SATISFIED | Truth 1. REQUIREMENTS.md still shows the checkbox unchecked and "Gaps Found" (lines 13 and 63); it should read Complete. |
| ACC-04 | 76-01, 76-02, 76-04 .. 76-15 | Route guards on priority router groups; gap ledger; agent routes excluded by design | SATISFIED | Truths 2, 3, 4. The WR-01 and WR-05 leaks that made this "satisfied with residual holes" are closed. REQUIREMENTS.md already shows Complete, which is now accurate. |
| ACC-05 | 76-01, 76-02, 76-03, 76-11, 76-14, 76-15 | Deny-by-default parity test plus frontend drift test | SATISFIED | Truths 4, 5. Gate now covers agent-capable routes and reviews both exemption lists. REQUIREMENTS.md already shows Complete, now accurate. |

All three IDs appear in plan frontmatter and in REQUIREMENTS.md. No orphaned Phase 76 requirements (ACC-06..09 map to Phase 77).

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| phase files | `TBD` / `FIXME` / `XXX` markers | none found | clean |
| `backend/tests/_catalogue_parity.py:353` | `_listed(entries, key)` ignores `key` (IN-02) | Info | lint only |
| `backend/catalogue_guards.py` `agent_tolerant` | drops `platform_read` (WR-02) | Warning (latent) | see advisory |
| `App.tsx:1173` | `viewPermission(view) as Permission` (IN-04) | Info | fails closed for non-super-admin today; Phase 77 owns |

### Human Verification Required

See the `human_verification` list in the frontmatter. In short: (1) a live enrolled agent after deploy, (2) tenant admin and platform staff reads of the gated tenant GETs return real 200s, (3) viewer / itam_viewer / analyst refusals and UI handling, (4) the app shell after the `/api/tenants/me` projection, (5) the owner's decision on rotating tenant registration keys. All depend on a deploy that is the user's call; Phase 77 is planned to precede it.

### Gaps Summary

No gaps. The previous report's single gap (roadmap SC2 / ACC-04: unguarded agent-capable reads and exempt tenant admin GETs) is closed by plans 76-13, 76-14 and 76-15, and the defect the code review found in that closure (CR-01) is fixed and covered by a regression test. The deny-by-default gate now sees the route classes it was previously blind to.

Reconciliation of requirement statuses: ACC-03 should be marked Complete in REQUIREMENTS.md (checkbox and traceability row); ACC-04 and ACC-05 are correctly Complete. Phase 76 is not deployed, so the live backend still serves the pre-fix `/api/tenants/me` and the pre-guard routes until the user restarts it.

---

_Verified: 2026-10-18T18:10:00Z_
_Verifier: Claude (gsd-verifier)_
