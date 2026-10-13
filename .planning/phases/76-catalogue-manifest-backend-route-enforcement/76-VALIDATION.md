---
phase: "76"
slug: "catalogue-manifest-backend-route-enforcement"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-13"
---

# Phase 76 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `76-RESEARCH.md` § Validation Architecture. Task IDs are assigned by the planner.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Backend: pytest + pytest-asyncio (`asyncio_mode = auto`). Frontend: vitest 5.0.0 + jsdom + @testing-library/react |
| **Config file** | root `pytest.ini`; `backend/tests/conftest.py` (`make_test_app`, `make_token_data`); `vite.config.ts` `test` block (include glob `src/**/*.{test,spec}.?(c|m)[jt]s?(x)`); `src/__tests__/setup.ts` |
| **Quick run command** | `backend/venv/bin/python -m pytest backend/tests/test_catalogue_manifest.py backend/tests/test_catalogue_route_parity.py backend/tests/test_catalogue_guards.py backend/tests/test_asset_finance_fields.py backend/tests/test_route_auth_baseline.py -q -p no:cacheprovider` and `npx vitest run src/__tests__/catalogueAccess.test.ts` |
| **Full suite command** | `backend/venv/bin/python -m pytest backend/tests -q -p no:cacheprovider` and `npx vitest run src/__tests__` and `npm run build` (writes `dist-new/`) |
| **Estimated runtime** | quick ~25 s (the route walk subprocess is ~10 s); full backend ~150 s; vitest ~60 s |

**Baselines:** full backend 3276 passed / 47 skipped (orchestrator brief); frontend 209 tests (orchestrator brief). Measured 2026-10-13: `test_route_auth_baseline.py` + `test_rbac_defaults.py` 58 passed in 10 s; `permissions.test.ts` + `SidebarAuditFixes.test.tsx` 31 passed.

**Constraints:** hermetic only; never write to the live `omni_platform` database; any DB-backed check must use a uniquely named throwaway database that the test drops.

---

## Sampling Rate

- **After every task commit:** Run the quick run command
- **After every plan wave:** Run the full suite command (guard waves can turn full-app tests red when new 403s land)
- **Before `/gsd-verify-work`:** Full suite must be green, including `npm run build`
- **Max feedback latency:** 30 seconds (quick), 150 seconds (full)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | ACC-03 | — | Manifest is the single source: every nav entry has exactly one permission, all permission strings are grantable, the 9 mismatched views resolve to the Sidebar string, `viewPermissionMap` literal is gone | unit (py) | `backend/venv/bin/python -m pytest backend/tests/test_catalogue_manifest.py -q -p no:cacheprovider` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ACC-03 | — | Sidebar and App.tsx read the manifest; every `AppView` has a manifest entry; every manifest permission is in the `Permission` union | unit (ts) | `npx vitest run src/__tests__/catalogueAccess.test.ts` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ACC-04 | T-76-01 Elevation of Privilege | Caller lacking `view:X` (and `manage:X`) gets 403 from guarded in-scope routes; holder gets non-403; write needs the write permission; super-admin bypass; role checked before API-key scope | unit/integration | `backend/venv/bin/python -m pytest backend/tests/test_catalogue_guards.py -q -p no:cacheprovider` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ACC-04 | T-76-02 Denial of Service | Agent enrollment/heartbeat on `/api/agents/*` and credential-in-handler routes unchanged; existing ITAM API-key callers still work | unit/integration | `backend/venv/bin/python -m pytest backend/tests/test_catalogue_guards.py backend/tests/test_route_auth_baseline.py -q -p no:cacheprovider` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ACC-04 | T-76-03 Information Disclosure | `/api/assets`, `/api/assets/search`, `/api/assets/{id}` strip purchase/finance fields without `view:itam`, keep them with it, and never mutate the cached object | unit | `backend/venv/bin/python -m pytest backend/tests/test_asset_finance_fields.py -q -p no:cacheprovider` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ACC-04 | — | Committed gap ledger lists every still-unguarded out-of-scope router with a reason and a ratchet count; stale entries fail | unit | `backend/venv/bin/python -m pytest backend/tests/test_catalogue_route_parity.py -q -p no:cacheprovider` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ACC-05 | T-76-01 Elevation of Privilege | Parity test fails on an unguarded in-scope route and on an unledgered unguarded router (negative controls using a synthetic app), message names router/route and expected permission | unit | `backend/venv/bin/python -m pytest backend/tests/test_catalogue_route_parity.py -q -p no:cacheprovider` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ACC-05 | — | Frontend drift test fails when a nav item has no manifest entry or a manifest nav entry has no nav item | unit (ts) | `npx vitest run src/__tests__/catalogueAccess.test.ts` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ACC-03/04/05 | — | Existing suites stay green after guards land | regression | `backend/venv/bin/python -m pytest backend/tests -q -p no:cacheprovider && npx vitest run src/__tests__ && npm run build` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `shared/catalogue-access.json` and `shared/catalogue-gaps.json` — seeded manifest (all 202 `AppView`s) and ledger skeleton
- [ ] `backend/tests/_route_walk.py` — walker and reviewed-unauthenticated list extracted from `test_route_auth_baseline.py` (baseline must stay green)
- [ ] `backend/tests/test_catalogue_manifest.py` — manifest sanity (ACC-03)
- [ ] `backend/tests/test_catalogue_route_parity.py` — deny-by-default parity plus negative controls (ACC-04/05)
- [ ] `backend/tests/test_catalogue_guards.py` — 403/200 matrix, scope narrowing, agent and API-key regression (ACC-04)
- [ ] `backend/tests/test_asset_finance_fields.py` — D-04 strip, including cache behaviour
- [ ] `src/__tests__/catalogueAccess.test.ts` — frontend drift test (ACC-03/05)
- [ ] Framework install: none — pytest, vitest and testing-library already present

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live agent enrollment and heartbeat still succeed after guards land | ACC-04 | Needs a real agent and a service restart, which the researcher/executor must not perform; the user owns restarts and deploys | After the user deploys and restarts: enroll or restart the agent on EILT0197 and confirm heartbeat in the Agents view; confirm no 401/403 in the agent log |
| A non-ITAM user sees no purchase cost in the Assets detail UI; an ITAM user does | ACC-04 | Visual check against live data | Log in as a viewer-role user and as an `itam_viewer`, open an asset with a recorded cost, compare |
| Sidebar still renders all groups for a super-admin after the manifest swap | ACC-03 | Visual regression of ordering, icons and tier locks | Load the app as super-admin, expand each group, compare to `sidebar-working.png` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s (quick) / 150s (full)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
