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

Commands below are the plans' own verify commands (run from the repo root; real-Mongo ones with `MONGO_TEST_URL=mongodb://127.0.0.1:27998 MONGODB_URL=mongodb://127.0.0.1:27998 MONGO_URI=mongodb://127.0.0.1:27998` prefixed and `-q -p no:cacheprovider -rs` appended; a SKIPPED real-Mongo test is a failure).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 88-01-T2 (tracer) | 88-01 | 1 | LIC-01, LIC-03, LIC-07 | T-88-01..03 | seats and trial from the stored plan; trial_ended holds new machines only; platform exempt | real-Mongo end-to-end | `backend/venv/bin/python -m pytest backend/tests/test_plan_tracer.py backend/tests/test_partner_license_writers.py backend/tests/test_enrollment_controls.py backend/tests/test_pending_agents.py backend/tests/test_licensing.py backend/tests/test_tenant_license_api.py backend/tests/test_machine_identity.py` | ❌ W0 (tracer creates it) | ⬜ pending |
| 88-02-T1, 88-02-T2 | 88-02 | 2 | LIC-01 seats | T-88-04..06 | partner allotment and override never overwritten by a plan write; seat writes only in licensing.py; platform unlimited | real-Mongo unit + AST scan | `backend/venv/bin/python -m pytest backend/tests/test_plan_seats.py backend/tests/test_license_seat_toctou.py backend/tests/test_partner_license_writers.py backend/tests/test_partner_move.py` | ❌ W0 (toctou/writers exist) | ⬜ pending |
| 88-03-T1, 88-03-T2 | 88-03 | 2 | LIC-04 screen ceiling | T-88-07..08 | seed 19/88/208 pinned; partner path refuses screens outside plan or partner ceiling; kept screens stay | unit + real-Mongo | `backend/venv/bin/python -m pytest backend/tests/test_plan_ceiling.py backend/tests/test_partner_ceiling.py backend/tests/test_partner_customers.py` | ❌ W0 (partner tests exist) | ⬜ pending |
| 88-04-T1, 88-04-T2 | 88-04 | 3 | LIC-02 plan changes, LIC-04 Super Admin path | T-88-09..11 | one change_plan path; payment route never changes the plan (D-39); Super Admin limited by plan only (D-40); AST scan of plan writers | real-Mongo + route + AST scan | `backend/venv/bin/python -m pytest backend/tests/test_plan_change.py backend/tests/test_plan_writers_scan.py backend/tests/test_tenant_feature_switches.py` | ❌ W0 | ⬜ pending |
| 88-05-T1..T3 | 88-05 | 3 | LIC-05 network rule | T-88-12..15 | decision uses server-observed request.client.host; spoofed forwarded header ignored; widen bounded /24 or /48; tenant admin cannot approve; enrolled agents never held | unit + real-Mongo | `backend/venv/bin/python -m pytest backend/tests/test_network_rule.py backend/tests/test_proxy_headers.py backend/tests/test_enrollment_controls.py backend/tests/test_pending_agents.py` | ❌ W0 | ⬜ pending |
| 88-06-T1, 88-06-T2 | 88-06 | 4 | LIC-03 trial, LIC-01 override clear | T-88-16..18 | one trial per tenant; extensions audited; reminders 7/1 once each, partner told; sign-up trial at approval | real-Mongo | `backend/venv/bin/python -m pytest backend/tests/test_trial.py backend/tests/test_tenant_license_api.py backend/tests/test_tenant_signup_approval.py` | ❌ W0 | ⬜ pending |
| 88-07-T1, 88-07-T2 | 88-07 | 4 | LIC-06 hold and silent retire | T-88-19..22 | no organization name crosses tenants; MAC-only never counts; retired copy's seat freed and tokens revoked; sparse indexes used | real-Mongo | `backend/venv/bin/python -m pytest backend/tests/test_cross_tenant_duplicate.py backend/tests/test_network_rule.py backend/tests/test_enrollment_controls.py` | ❌ W0 | ⬜ pending |
| 88-08-T1, 88-08-T2 | 88-08 | 4 | LIC-07 Plans API | T-88-23..24 | only the Super Admin edits plans; seat edits apply at once to direct tenants without override; route guard parity | real-Mongo + route + manifest | `backend/venv/bin/python -m pytest backend/tests/test_plan_endpoints.py backend/tests/test_catalogue_route_parity.py backend/tests/test_catalogue_manifest.py backend/tests/test_catalogue_slice_billing_identity.py` | ❌ W0 (catalogue tests exist) | ⬜ pending |
| 88-09-T1..T3 | 88-09 | 5 | LIC-06 decisions | T-88-25..28 | approval moves the machine; other approvals cannot admit a duplicate; crossTenant hidden from tenant readers; moved heartbeat refused; restore; hourly live-pair report | real-Mongo | `backend/venv/bin/python -m pytest backend/tests/test_cross_tenant_decisions.py backend/tests/test_catalogue_route_parity.py` | ❌ W0 | ⬜ pending |
| 88-10-T1..T3 | 88-10 | 5 | LIC-02, LIC-03, LIC-04 partner | T-88-29..31 | partner changes plans only for its customers within planCeiling; trial extension audited on both ledgers; rows from CUSTOMER_FIELDS | real-Mongo | `backend/venv/bin/python -m pytest backend/tests/test_partner_plans.py backend/tests/test_partner_customers.py backend/tests/test_partner_isolation.py` | ❌ W0 | ⬜ pending |
| 88-11-T1, 88-11-T2 | 88-11 | 6 | Migration 034 | T-88-32..33 | idempotent; old seat numbers recorded before overwrite; partner customers and platform untouched; screens untouched; read-only go-live check | real-Mongo | `backend/venv/bin/python -m pytest backend/tests/test_migration_034_plans.py` | ❌ W0 | ⬜ pending |
| 88-12-T1, 88-12-T2 | 88-12 | 5 | UI Plans screen, Manage/Add Tenant | T-88-34 | plan is a ceiling in the UI; Add Tenant defaults to Free | vitest | `npx vitest run src/__tests__/PlansPanel.test.tsx src/__tests__/ManageTenantModal.test.tsx src/__tests__/AddNewTenantModal.test.tsx` | partly | ⬜ pending |
| 88-13-T1, 88-13-T2 | 88-13 | 5 | UI licence card and panel | T-88-35 | tenant card read-only; Super Admin override clear and trial extension | vitest | `npx vitest run src/__tests__/TenantPlanCard.test.tsx src/__tests__/TenantLicensePanel.test.tsx` | ❌ W0 | ⬜ pending |
| 88-14-T1, 88-14-T2 | 88-14 | 6 | UI Pending reasons, widen, move, restore | T-88-36 | tenant text unnamed; widen input; move confirmation; restore | vitest | `npx vitest run src/__tests__/PendingAgentsPanel.test.tsx src/__tests__/PendingMovedAgents.test.tsx` | partly | ⬜ pending |
| 88-15-T1..T3 | 88-15 | 6 | UI partner plans | T-88-37 | plan ceiling form; plan and trial modal; picker shows plan limit | vitest | `npx vitest run src/__tests__/PartnerAdminModals.test.tsx src/__tests__/PartnerPortal.test.tsx src/__tests__/PartnerPlanModal.test.tsx src/__tests__/PartnerScreenPicker.test.tsx` | partly | ⬜ pending |
| 88-16-T2 | 88-16 | 7 | go-live (D-08, D-18, D-34) | T-88-38 | live state matches; proxy trust pinned in the running unit | read-only live check | `backend/venv/bin/python backend/scripts/check_plan_golive.py --url mongodb://127.0.0.1:27017 --db omni_platform` | ❌ (88-11 creates it) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_plan_seats.py`, `test_plan_change.py`, `test_plan_writers_scan.py`, `test_trial.py`, `test_plan_ceiling.py`, `test_network_rule.py`, `test_proxy_headers.py`, `test_cross_tenant_duplicate.py`, `test_plan_endpoints.py`, `test_migration_034_plans.py`
- [ ] A shared two-tenant fixture (tenants A and B with agents and install keys on `mongo_db`) built on the `_register` harness, moved to a shared helper module instead of importing one test module from another: `backend/tests/_enrollment_harness.py` (88-01-T2, with a settable client address); each new test file is created by the task that first verifies with it (see the map above; `test_cross_tenant_decisions.py` is 88-09's)
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
