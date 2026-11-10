---
phase: "88"
slug: "plan-based-licensing-network-enrollment-rules"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-11-10"
---

# Phase 88 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 + pytest-asyncio 1.4.0 (`asyncio_mode = auto`); frontend vitest |
| **Config file** | `pytest.ini` (`testpaths = . backend`); frontend `npx vitest run src/__tests__` |
| **Quick run command** | `cd backend && venv/bin/python -m pytest tests/test_enrollment_controls.py tests/test_pending_agents.py tests/test_licensing.py tests/test_machine_identity.py tests/test_asset_identity.py -q -p no:cacheprovider` |
| **Full suite command** | `cd backend && venv/bin/python -m pytest tests -q -p no:cacheprovider` then `npx vitest run src/__tests__` from the repo root |
| **Estimated runtime** | ~12 seconds (quick, 57 tests at research time); full backend suite several minutes |

Real-Mongo tests use `backend/tests/_mongo_test_db.py::mongo_db` (throwaway `omni_test_<hex>` database, unique `agents` indexes, dropped afterwards; skips without mongod). The register harness is `_register` in `backend/tests/test_enrollment_controls.py` (Request with client `203.0.113.7`).

---

## Sampling Rate

- **After every task commit:** Run the quick run command plus the task's own new test file
- **After every plan wave:** Run the full suite command (backend + vitest)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds for the per-task run

---

## Per-Task Verification Map

Seeded from 88-RESEARCH.md "Phase Requirements -> Test Map" (requirement IDs LIC-01..07 proposed there, mapped to CONTEXT D-IDs). The planner replaces the Task ID / Plan / Wave columns with real task IDs.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | LIC-01 seats | — | partner allotment and override never overwritten by a plan write; seat writes only in licensing.py | real-Mongo unit + AST scan | `pytest tests/test_plan_seats.py tests/test_license_seat_toctou.py tests/test_partner_license_writers.py -q` | ❌ W0 (toctou/writers exist) | ⬜ pending |
| TBD | TBD | TBD | LIC-02 plan changes | — | one change_plan path; partner limited to its plan ceiling; payment route validates plan; audit + tenant notice | real-Mongo + route + AST scan | `pytest tests/test_plan_change.py tests/test_plan_writers_scan.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | LIC-03 trial | — | one trial per tenant; trial_ended holds new machines only; reminders 7/1 once each | real-Mongo | `pytest tests/test_trial.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | LIC-04 screen ceiling | — | server refuses screens outside plan (and partner) ceiling at every write path; kept screens survive downgrade | real-Mongo/unit | `pytest tests/test_plan_ceiling.py tests/test_partner_ceiling.py tests/test_tenant_feature_switches.py -q` | ❌ W0 (partner/switch tests exist) | ⬜ pending |
| TBD | TBD | TBD | LIC-05 network rule | — | decision uses server-observed request.client.host; spoofed X-Forwarded-For ignored; tenant admin cannot approve; enrolled agents never held | unit + real-Mongo | `pytest tests/test_network_rule.py tests/test_proxy_headers.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | LIC-06 cross-tenant duplicate | — | no organization name crosses tenants (lists, feeds, ledger); retired agent's tokens revoked and its heartbeat refused; MAC-only never counts | real-Mongo | `pytest tests/test_cross_tenant_duplicate.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | LIC-07 Plans API | — | only the Super Admin edits plans; route guard parity with the catalogue manifest | route + manifest | `pytest tests/test_plan_endpoints.py tests/test_catalogue_route_parity.py tests/test_catalogue_manifest.py -q` | ❌ W0 (catalogue tests exist) | ⬜ pending |
| TBD | TBD | TBD | Migration 034 | — | idempotent; old seat numbers recorded before overwrite | real-Mongo | `pytest tests/test_migration_034_plans.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | UI | — | licence panel, Pending reasons + widen input, Plans screen, partner plan picker, Add Tenant default Free | vitest | `npx vitest run src/__tests__/PendingAgentsPanel.test.tsx src/__tests__/PartnerPortal.test.tsx src/__tests__/PlansScreen.test.tsx` | partly | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_plan_seats.py`, `test_plan_change.py`, `test_plan_writers_scan.py`, `test_trial.py`, `test_plan_ceiling.py`, `test_network_rule.py`, `test_proxy_headers.py`, `test_cross_tenant_duplicate.py`, `test_plan_endpoints.py`, `test_migration_034_plans.py`
- [ ] A shared two-tenant fixture (tenants A and B with agents and install keys on `mongo_db`) built on the `_register` harness, moved to a shared helper module instead of importing one test module from another
- [ ] Existing pinned-shape tests updated where the phase changes the shape: `tests/test_partner_license_writers.py` (`PRE_CHANGE_KEYS` for `trial`), `partner_store.CUSTOMER_FIELDS` pin (`plan`, `trialEndsAt`)

*Framework install: none needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Pending reason text and the widen-to-range input on the published UI | LIC-05, LIC-06 | Needs the published frontend and a real second network | Enroll a test machine from a new public IP; check the tenant admin sees the reason and cannot approve; Super Admin approves with a range |
| Plans screen edit applies at once on the live VM | LIC-07 | Live tenants and published UI | Change a plan's seats as Super Admin; confirm a direct tenant without override shows the new limit |
| Live proxy chain (nginx -> uvicorn) still passes the real client address after the unit change | LIC-05 | Depends on the running systemd unit and nginx | After restart, compare nginx access log client IP with the agent's stored sourceIp for a fresh registration |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
