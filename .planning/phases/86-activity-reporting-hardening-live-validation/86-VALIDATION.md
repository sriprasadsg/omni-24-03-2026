---
phase: "86"
slug: "activity-reporting-hardening-live-validation"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-11-11"
---

# Phase 86 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Built from 86-RESEARCH.md "Validation Architecture". The planner fills the task IDs in the Per-Task Verification Map.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 + pytest-asyncio 1.4.0 (`asyncio_mode = auto`); vitest ^5.0.0 for the UI |
| **Config file** | `pytest.ini` (repo root), `backend/tests/conftest.py`, `package.json` |
| **DB fixture** | `backend/tests/_mongo_test_db.py` (`mongo_db`, throwaway database on the private mongod); helpers `tests/autonomy_support.py`, `tests/rollout_support.py`, `tests/service_desk_support.py`, HTTP harness `tests/_autonomous_ops_http.py` |
| **Test DB prefix (required)** | `MONGO_TEST_URL=mongodb://127.0.0.1:27998 MONGODB_URL=mongodb://127.0.0.1:27998 MONGO_URI=mongodb://127.0.0.1:27998` (all three; otherwise conftest finalizes against the live 27017). Never run anything against 127.0.0.1:27017. |
| **Quick run command** | `{prefix} backend/venv/bin/python -m pytest backend/tests/test_autonomous_ops_stats.py backend/tests/test_autonomous_ops_digest.py backend/tests/test_autonomous_ops_copy.py -q -p no:cacheprovider` |
| **Full suite command** | `{prefix} backend/venv/bin/python -m pytest backend/tests/test_autonomous_ops_*.py backend/tests/test_catalogue_slice_autonomous_ops.py backend/tests/test_catalogue_route_parity.py backend/tests/test_route_auth_baseline.py backend/tests/test_patch_rollout_*.py backend/tests/test_service_desk_*.py backend/tests/test_retention_job.py backend/tests/test_audit_export.py backend/tests/test_notification_*.py -q -p no:cacheprovider` (from the repo root; known pre-existing failure `test_catalogue_route_parity.py::test_ledger_ratchets`, 9 named routes, predates this phase); UI: `npx vitest run src/__tests__` and `npm run build` |
| **Estimated runtime** | quick ~60 s; full ~10 min |

---

## Sampling Rate

- **After every task commit:** the task's new test file plus `test_autonomous_ops_structural.py` and `test_autonomous_ops_copy.py` (with the 27998 prefix)
- **After every plan wave:** the full suite command plus the touched vitest files
- **Before `/gsd-verify-work`:** full suite green (except the known `test_ledger_ratchets` names), `npx vitest run src/__tests__`, `npm run build`, and the backend suite again on a `git archive` snapshot of HEAD with `pytest.ini` (D-18: the export work must not depend on uncommitted files)
- **Max feedback latency:** 120 seconds per task command

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (planner fills) | | | ACTV-04 | | Digest reaches tenant admins only (no platform feed, no on-call page); once per tenant per UTC day; quiet day sends nothing; shadow-only day sends with `0 ran, 0 undone, 0 waiting` + simulation section | unit + real-Mongo | `{prefix} backend/venv/bin/python -m pytest backend/tests/test_autonomous_ops_digest.py -q -p no:cacheprovider` | ❌ W0 | ⬜ pending |
| (planner fills) | | | ACTV-05 | | Per-rule counts tenant-scoped; shadow separate; control/platform-health rows excluded; 7/30/90 window | real-Mongo | `{prefix} ... pytest backend/tests/test_autonomous_ops_stats.py -q` | ❌ W0 | ⬜ pending |
| (planner fills) | | | ACTV-07 | | Minutes table (D-19) covers every registry command + `ticket_handoff`; counts executed/verified only; total = sum of subtotals; labelled estimate | unit + real-Mongo | same file | ❌ W0 | ⬜ pending |
| (planner fills) | | | ACTV-06 | | Needs `export:reports` AND `view:autonomous_ops`; registry type refuses platform staff with no organization; audit event with who/filter/rows/format; 5,000 cap headers; zero rows → 204; CSV formula and PDF markup injection neutralised | HTTP + real-Mongo | `{prefix} ... pytest backend/tests/test_autonomous_ops_export.py -q` | ❌ W0 | ⬜ pending |
| (planner fills) | | | D-14..D-16, D-20, D-21 | | Lift refused (409) until 5 checks recorded and 7 days since the first shadow record; shadow-on never gated; Super Admin only; audit event per lift/restore and per check; checks append-only | HTTP + structural | `{prefix} ... pytest backend/tests/test_autonomous_ops_golive.py -q` | ❌ W0 | ⬜ pending |
| (planner fills) | | | Success criterion 4 (D-13) | | Platform and tenant stop halt new decisions, hold back queued instructions, freeze approvals and rollouts, pause AI ticket replies; undo exempt; retention keeps running (documented); other tenant unaffected; clean resume | real-Mongo integration | `{prefix} ... pytest backend/tests/test_autonomous_ops_stop_drill.py -q` | ❌ W0 | ⬜ pending |
| (planner fills) | | | Success criterion 5 (D-17) | | Per-loop two-tenant contract (security sweep, rollout controller, desk worker, retention) + stats/export/digest isolation | real-Mongo | `{prefix} ... pytest backend/tests/test_autonomous_ops_two_tenant.py -q` | ❌ W0 | ⬜ pending |
| (planner fills) | | | Migration 035 | | Indexes only; second run changes nothing | real-Mongo | `{prefix} ... pytest backend/tests/test_migration_035_activity_reporting.py -q` | ❌ W0 | ⬜ pending |
| (planner fills) | | | ACTV-08 | | No banned term in new code, docs and UI; new files registered | static | `{prefix} ... pytest backend/tests/test_autonomous_ops_copy.py -q`; `npx vitest run src/__tests__/autonomousOpsCopy.test.ts` | ✅ (list edits) | ⬜ pending |
| (planner fills) | | | UI (UI-SPEC) | | Statistics card, per-rule table, Export activity dialog, Reporting card disabled reasons, Going live card (record form, gate reasons, typed-name confirm, turn-back-on dialog) | vitest | `npx vitest run src/__tests__/autonomousOpsStats.test.tsx src/__tests__/autonomousOpsGoLive.test.tsx` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_autonomous_ops_digest.py`, `test_autonomous_ops_stats.py`, `test_autonomous_ops_export.py`, `test_autonomous_ops_golive.py`, `test_autonomous_ops_stop_drill.py`, `test_autonomous_ops_two_tenant.py`, `test_migration_035_activity_reporting.py`
- [ ] `src/__tests__/autonomousOpsStats.test.tsx`, `src/__tests__/autonomousOpsGoLive.test.tsx`
- [ ] Edits to existing tests: `test_autonomous_ops_copy.py` and `src/__tests__/autonomousOpsCopy.test.ts` (EXPECTED lists, `FRONTEND_DIRECTORIES`), `test_autonomous_ops_ledger.py:327` (protected set), `test_catalogue_slice_autonomous_ops.py` (mount dict, platform module tuple)
- [ ] No framework install needed

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Digest delivery to a real admin (in-app, and email once SMTP is configured) | ACTV-04 | Needs the live backend restarted after the phase and a real day boundary at 07:00 UTC; SMTP is not configured on this VM | After the user's restart, wait for 07:00 UTC; an admin of a ticked organization with activity (or simulation items) sees `Autonomous Ops daily digest` in the notification center; no notice on a quiet day |
| CSV and PDF download from the published UI | ACTV-06 | Browser download on the published build | Export activity → Download CSV / Download PDF; Reporting → Autonomous Ops Activity card; check the cap note and the audit-log entry |
| Live stop drill on the server | Success criterion 4 | Real agent poll, real approvals, rollout and Ollama ticket reply | Walk check 5 of `docs/autonomous-ops-go-live.md`; record it on the Going live card |
| Firewall round-trip, reboot gate, watchdog stop/start, alert delivery | Success criterion 5 | Real agents (2.1.16+/2.1.17+), installed watchdog, real on-call channel | Walk checks 1-4 of `docs/autonomous-ops-go-live.md`; record each on the Going live card |
| Observe-first soak and per-tenant lift out of shadow mode | D-15, D-16 | Live data over 7 days; the deployment-wide `AUTONOMOUS_REMEDIATION_DRY_RUN` switch is the user's env change + restart | After 7 days and all 5 checks recorded, a Super Admin lifts one organization (typed name); confirm the audit event |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
