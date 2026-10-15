---
phase: 76-catalogue-manifest-backend-route-enforcement
plan: 11
subsystem: api
tags: [rbac, catalogue-manifest, deny-by-default, gap-ledger, route-parity, d-05]

requires:
  - phase: 76-catalogue-manifest-backend-route-enforcement
    provides: route walker and parity helpers (76-01), manifest (76-02), wave-3 slice guards (76-04..76-10, 76-12)
provides:
  - shared/catalogue-gaps.json, the committed gap ledger (90 unguarded routers, 292 routes, ratchets)
  - ledger_offenders / load_ledger in backend/tests/_catalogue_parity.py
  - strict whole-app tests (test_all_enforced_routes_guarded, test_unguarded_routers_are_ledgered, test_ledger_ratchets) and 14 negative controls
  - catalogue guards on the seven route_aliases routes that sit under enforced catalogues
affects: [77, ACC-F2]

actuals:
  tokens: 32000
  tasks: 3
  commits: 3
plan_head_before: 9f8855ec37cda09b590e6e53324456d61b0a52fb
plan_head_after: 1f4cd54e95783bce781b0fae38abfe6f79093205

tech-stack:
  added: []
  patterns:
    - "Deny-by-default gate: one cached walk of the production registry; unguarded = user route with no tag, no known guard dependency, no exemption (RESEARCH A6)"
    - "Ratchets both ways: a count above the ledger fails, and so does slack, so the ledger can only shrink through a reviewed change"
    - "Route walker child gets scratch ticket-attachment and file-share dirs so the walked table does not depend on the host"

key-files:
  created:
    - shared/catalogue-gaps.json
  modified:
    - backend/tests/_catalogue_parity.py
    - backend/tests/test_catalogue_route_parity.py
    - backend/tests/_route_walk.py
    - backend/route_aliases.py

key-decisions:
  - "No edit to shared/catalogue-access.json: every wave-3 correction is either a policy question, a UI-visible change (D-11) or would need 15+ mount constants rewritten; all are listed below"
  - "/api/tenants/me (owned by profile) is catalogue_exempt as self-service, like /api/users/me, so custom roles without view:profile are not locked out; the other six aliases carry their owner's named guard"
  - "Ledger ratchets are two-sided (count above fails, slack fails) so a guarded route must lower the ratchet in the same reviewed commit"

requirements-completed: [ACC-04, ACC-05]

coverage:
  - id: D1
    description: "Whole-app parity over the production route table is empty (every enforce:true user route carries its catalogue guard)"
    requirement: ACC-05
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_route_parity.py#test_all_enforced_routes_guarded"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every unguarded router is in shared/catalogue-gaps.json with group, reason and a ratchet; stale, over-ratchet, slack and enforced-ledgered entries fail"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_route_parity.py#test_unguarded_routers_are_ledgered"
        status: pass
      - kind: unit
        ref: "backend/tests/test_catalogue_route_parity.py#test_ledger_ratchets"
        status: pass
    human_judgment: false
  - id: D3
    description: "Each ledger failure mode fires on a synthetic app and a compliant app passes"
    requirement: ACC-05
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_route_parity.py#test_ledger_offender_for_unledgered_router"
        status: pass
    human_judgment: false
  - id: D4
    description: "Live agent heartbeat, ITAM API-key traffic and role-lockout checks after the user deploys"
    verification: []
    human_judgment: true
    rationale: "Deploy and restart are user-owned; listed under Manual checks"
---

# Phase 76 Plan 11: Deny-by-default gate and gap ledger Summary

**A committed, two-way-ratcheted gap ledger (90 unguarded routers, 292 routes) plus a whole-app parity test that turns any new unguarded route, unledgered router, new agent-capable route or new exemption into a red build; the seven route_aliases routes now carry their owning catalogue's guard.**

## What was built

- `ledger_offenders(records, manifest, ledger)` and `load_ledger()` in `backend/tests/_catalogue_parity.py` (read-only; `grep -v '^#' ... | grep -c 'open(.*"w"'` prints 0, PROH-76-03). Checks: router missing from the ledger (prints a paste-ready JSON entry with `maxUnguardedRoutes` equal to the count), count above the ratchet, slack in the ratchet, stale or unmounted entry, blank group or reason, placeholder reason, duplicate entry, enforced-catalogue route in the ledger (PROH-76-04), `agentAuthExcludedRoutes` and `maxExemptRoutes` ratchets (both directions), exempt reason shorter than 10 characters.
- `test_catalogue_route_parity.py`: 14 synthetic-app negative controls (RED first, commit 2874d7f8e), then `test_load_ledger_is_shaped_and_sorted`, `test_all_enforced_routes_guarded`, `test_unguarded_routers_are_ledgered`, `test_ledger_ratchets` over `run_real_app_walk()`. 25 tests in the file (7 from 76-01 plus 18).
- `shared/catalogue-gaps.json`, generated once from the real walk with a scratchpad script (not from a test), reviewed by hand; two multi-group reasons were reworded.
- `backend/route_aliases.py`: guards on the seven aliases that parity named.

## Ledger and counts

| Item | Value |
|---|---|
| Routes walked (HTTP + WS) | 1616 |
| User routes | 1515 |
| Ledger entries (routers) | 90 |
| Unguarded user routes in the ledger | 292 (sum of `maxUnguardedRoutes`) |
| `agentAuthExcludedRoutes` | 15 (agent_capable method+path pairs) |
| `maxExemptRoutes` | 34 (33 from earlier plans + `/api/tenants/me`) |
| Enforced-group user routes unguarded | 0 |

By group: governance, dashboards, devsecops, automation and observability routers are ledgered with "<group> is not enforced: route guards deferred to ACC-F2 (D-01)". Five entries are unowned-prefix routers (`authentication_endpoints`, `global_search_endpoints`, `mfa_endpoints`, `passkey_endpoints`, and the `/api/platform` part of `platform_endpoints`) with the manifest's `unownedPrefixes` reason. `route_aliases` (11 routes) and `router_registry` (the `/api/tasks/{task_id}` alias) stay ledgered because their paths belong to non-enforced groups.

## Leftover modules guarded

`route_aliases` only. Alias routes registered first now carry the guard of the catalogue that owns the path:

| Alias | Guard |
|---|---|
| GET /api/agent/download-token/{tenant_id}, GET /api/agents/stats | agents (`AGENTS_GUARD`) |
| GET /api/ai/test-connection | settings (`SETTINGS_GUARD`) |
| GET /api/pqc/keys | zeroTrustQuantum (`ZERO_TRUST_GUARD`) |
| GET /api/secrets/findings | secretsManagement (`SECRETS_GUARD`) |
| GET /api/ueba/shadow-ai | ueba (local guard, view:security / investigate:security) |
| GET /api/tenants/me | `catalogue_exempt("self-service: caller's own tenant record")` (profile catalogue) |

No other module needed an edit: parity over the whole app had exactly these seven offenders.

## Manifest corrections: accepted and rejected

None accepted; `shared/catalogue-access.json` is unchanged (so the manifest, Sidebar and tenant-feature-switch tests are untouched). Reasons:

| Correction (source) | Decision | Reason |
|---|---|---|
| View strings in write lists (softwareDeployment 76-06; threatHunting, threatIntelligence, correlations 76-07; cloudAccounts, iacContainer, zeroTrustQuantum, vulnerabilityManagement 76-08; finops 76-09) | Rejected, human decision | 15 enforced entries carry a view string in `write`; several are intentional (profile, notificationPrefs, notifications, remoteAccess match the handler). They mirror what the routes accepted before the phase, the route-level checks still run, and removing them narrows who can write and needs a matching edit in 15+ mount constants. Not a mechanically clear error. |
| `stagedDeployments` owns no prefix (76-06) | Rejected | The manifest states `noBackendReason: "shares routes with softwareDeployment"`; it is a design choice, and a new prefix would change which feature switch and guard own `/api/deployments/staged*`. |
| `deploymentApprovals.read` view:patching vs the routes' view:approvals (76-06) | Rejected | `permission` is the sidebar string and D-11 says the Sidebar wins; the route check is stricter, so effective access is unchanged. |
| ITAM sub-paths under `/api/assets/{id}/...` owned by itam (76-04) | Rejected | Prefixes cannot express `{id}` mid-path; handlers already demand view:itam, nothing leaks. |
| Give `/api/support` its own catalogue (76-05) | Rejected | New catalogue and sidebar surface; support stays self-service exempt. |
| Add 8 backend-only strings to `Permission` in types.ts (76-03) | Not applied | Type-only, no behaviour; outside this plan's files. |
| `tenantManagement` / `apiKeys` / `knowledgeBase` / `userManagement` notes (76-09) | Rejected, human decision | Policy (platform roles, D-08/D-12 intent). |

## Needs a human decision

These change who can read or write today; each is listed so a person can choose, nothing was widened or narrowed here.

1. `retentionPolicy` (`/api/retention`, previously any signed-in user) now needs `manage:settings`; confirm for `itam_admin`.
2. PAM reads and writes both need `manage:settings` (`pam`), the only secposture catalogue with a manage: read.
3. `secretsManagement` read `manage:settings` locks out `platform_support`, which holds `view:secrets`; `integrations` read `manage:settings` vs `view:integrations`. The new `/api/secrets/findings` alias follows the first.
4. `fleetGeoMap` and `fleetObservability` read `manage:agents`; analyst, incident_responder, platform_support and user hold only `view:agents` and lose both pages.
5. `hadr`: routes check `view:backups`, `manage:backups`, `view:system`, which no built-in role holds apart from the Super Admin wildcard; grant to `tenant_admin` or change the route checks.
6. Write lists containing view strings (table above); `softwareDeployment` likely means `manage:software_deployment`.
7. `detectionRules.read` (`view:detection_rules`), `fimMonitoring.read` (`view:fim`) are held only by tenant_admin and platform_support; analyst roles used to read these. `incidentResponse.read` investigate:security removes the cases list from `user`.
8. `tenantManagement` / `bundleManagement` read `manage:tenants` (Super Admin only) versus platform roles that need `view:tenants`; `apiKeys` read removes `/api/admin/api-keys` from itam_admin; `knowledgeBase` read manage:settings removes queries from viewer/user.
9. Pre-existing, outside scope: `GET /api/support/presence` has no tenant scoping; tenant email config and enrollment-key GET need only tenant ownership; `/api/ai/threat-hunt` and `GET /api/system/health` are defined twice (first mounted wins).

## Deviations from Plan

**1. [Rule 3 - Blocking] Route walker depended on the host's storage directories**
- **Found during:** Task 2 (route count was 1594 before and 1616 after the alias edit)
- **Issue:** The child interpreter inherits the host environment; on this VM `TICKET_ATTACHMENT_DIR`/`FILE_SHARE_DIR` resolve to the unwritable `/var/lib/omni-platform`, so `tickets_endpoints` and `file_share_endpoints` silently failed to register and 22 routes vanished from the walk. Ledger counts would have flipped between environments.
- **Fix:** `throwaway_env()` in `backend/tests/_route_walk.py` now points both at per-process scratch directories.
- **Files modified:** backend/tests/_route_walk.py
- **Commit:** 1f4cd54e9

**2. [Design call] Ratchets fail on slack as well as on excess**
- The plan names "a count above the ratchet"; the ledger is meant to shrink only through review, so a ratchet above the real count (room to add unguarded routes unseen) also fails with "lower it to N". Applies to `maxUnguardedRoutes`, `agentAuthExcludedRoutes` and `maxExemptRoutes`.

**3. [Design call] `/api/tenants/me` exempt instead of guarded**
- The alias is owned by the `profile` catalogue (view:profile, held by every built-in role). It is exempted, matching `/api/users/me`, so a custom role without view:profile is not locked out of its own tenant record. Counts toward `maxExemptRoutes` (34).

**Total deviations:** 1 auto-fixed (Rule 3), 2 design calls. **Impact:** none on scope.

## Task 3: regression results

| Check | Result | Baseline |
|---|---|---|
| Full backend suite (`backend/venv/bin/python -m pytest tests -q -p no:cacheprovider`, scratch dirs exported) | 3721 passed, 47 skipped, 0 failed (10m56s) | 3703 passed, 47 skipped at 9f8855ec3 (+18 new) |
| `npx vitest run src/__tests__` | 34 files, 266 passed | 235 after 76-03 |
| `npm run build` | built, exit 0 (outDir dist-new untouched in git, nothing copied) | n/a |

No wave-3 red test remained, so no principal or test change was needed. Manifest, Sidebar and tenant-switch tests were not re-run separately because the manifest is unchanged; they are inside the 3721.

## Manual checks for the user (after deploy and restart, both user-owned)

1. Enroll or restart the agent on EILT0197; confirm heartbeat in the Agents view and no 401/403 in the agent log. Existing ITAM API-key integrations still return data.
2. Log in as a viewer-role user and as an `itam_viewer`; open an asset with a recorded purchase cost; only the itam_viewer sees cost, warranty and supplier fields.
3. Load the app as super-admin, expand every sidebar group and compare ordering, icons and tier locks with the pre-phase sidebar.
4. As analyst, viewer and platform_support, open Agents stats, Settings test-connection, PQC keys, Secrets findings, UEBA shadow AI: expect 403 only where the owning catalogue's read permission is missing, and `/api/tenants/me` still loads for every role.
5. Decide the items under "Needs a human decision".

## Known Stubs

None.

## Threat Flags

None. No new endpoints, auth paths or schema. T-76-25 (whole-app parity plus ledger completeness), T-76-26 (two-way ratchets, stale and enforced-ledgered failures, read-only helper) and T-76-27 (alias guards) are mitigated by tests.

## Self-Check: PASSED

- Files exist: shared/catalogue-gaps.json, backend/tests/_catalogue_parity.py, backend/tests/test_catalogue_route_parity.py, backend/tests/_route_walk.py, backend/route_aliases.py.
- Commits 2874d7f8e (test, RED), 6b183f39d (feat, GREEN), 1f4cd54e9 (feat) are ancestors of HEAD; RED run failed with ImportError on `ledger_offenders`.
- Acceptance: ledger JSON check prints 90 with every reason and group non-blank; `grep -c 'open(.*"w"'` on the helper prints 0; parity, manifest and auth-baseline tests: 60 passed.
- No service restarts, deploys or writes to the live database.
