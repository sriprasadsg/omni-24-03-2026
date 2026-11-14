---
phase: "86"
slug: "activity-reporting-hardening-live-validation"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-11-11"
validated: "2026-11-14"
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
| **Test DB prefix (required)** | `MONGO_TEST_URL=mongodb://127.0.0.1:27998 MONGODB_URL=mongodb://127.0.0.1:27998 MONGO_URI=mongodb://127.0.0.1:27998` (all three; otherwise conftest finalizes against the live 27017). Never run anything against 127.0.0.1:27017. Desk and drill files also need `TICKET_ATTACHMENT_DIR=$(mktemp -d)`. |
| **Quick run command** | `{prefix} backend/venv/bin/python -m pytest backend/tests/test_autonomous_ops_stats.py backend/tests/test_autonomous_ops_digest.py backend/tests/test_autonomous_ops_copy.py -q -p no:cacheprovider` |
| **Full suite command** | `{prefix} TICKET_ATTACHMENT_DIR=$(mktemp -d) backend/venv/bin/python -m pytest backend/tests/test_autonomous_ops_*.py backend/tests/test_migration_035_activity_reporting.py backend/tests/test_catalogue_slice_autonomous_ops.py backend/tests/test_route_auth_baseline.py backend/tests/test_patch_rollout_*.py backend/tests/test_service_desk_*.py backend/tests/test_retention_job.py backend/tests/test_audit_export.py backend/tests/test_notification_*.py -q -p no:cacheprovider -rs` (from the repo root; the earlier `test_catalogue_route_parity.py::test_ledger_ratchets` failure passes since 86-13); UI: `npx vitest run src/__tests__` and `npm run build` |
| **Estimated runtime** | quick ~60 s; Phase 86 map set ~75 s; full ~17-21 min |

---

## Sampling Rate

- **After every task commit:** the task's new test file plus `test_autonomous_ops_structural.py` and `test_autonomous_ops_copy.py` (with the 27998 prefix)
- **After every plan wave:** the full suite command plus the touched vitest files
- **Before `/gsd-verify-work`:** full suite green, `npx vitest run src/__tests__`, `npm run build`, and the backend suite again on a `git archive` snapshot of HEAD with `pytest.ini` (D-18: the export work must not depend on uncommitted files)
- **Max feedback latency:** 120 seconds per task command

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 86-05-T1, 86-05-T2, 86-05-T3 | 86-05 | 2 | ACTV-04 | T-86-07, T-86-08, T-86-09, T-86-10 | Digest reaches tenant admins only (audience `tenant_admins`, nothing in the on-call outbox); once per tenant per UTC day (claim + unique index, second/parallel pass and restart send nothing); quiet day sends nothing; shadow-only day sends with `0 ran, 0 undone, 0 waiting` + simulation section; 07:00 UTC loop under the distributed lock, registered at startup | unit + real-Mongo | `{prefix} backend/venv/bin/python -m pytest backend/tests/test_autonomous_ops_digest.py backend/tests/test_autonomous_ops_digest_job.py -q -p no:cacheprovider` | ✅ | ✅ green |
| 86-01-T1, 86-01-T2, 86-04-T1, 86-04-T2 | 86-01, 86-04 | 1, 2 | ACTV-05 | T-86-01, T-86-02 | Per-rule counts tenant-scoped; shadow separate; control/platform-health rows excluded; 7/30/90 window, edge to the microsecond; another tenant's rows never change the numbers; tenant admin naming another tenant refused | real-Mongo + vitest | `{prefix} ... pytest backend/tests/test_autonomous_ops_stats.py -q`; `npx vitest run src/__tests__/autonomousOpsStats.test.tsx` | ✅ | ✅ green |
| 86-01-T1, 86-01-T2, 86-04-T1 | 86-01, 86-04 | 1, 2 | ACTV-07 | T-86-01 | Minutes table (D-19) covers every registry command + `ticket_handoff`; counts executed/verified only; total = sum of subtotals; labelled estimate | unit + real-Mongo + vitest | same files | ✅ | ✅ green |
| 86-06-T2, 86-06-T3, 86-08-T1, 86-08-T2, 86-11-T1, 86-11-T2 | 86-06, 86-08, 86-11 | 2, 3, 4 | ACTV-06 | T-86-11, T-86-12, T-86-13, T-86-19, T-86-20, T-86-21, T-86-22, T-86-23 | Needs `export:reports` AND `view:autonomous_ops`; registry type refuses platform staff before cross-tenant elevation; audit event with who/filter/rows/format; 5,000 cap headers; zero rows → 204 (not audited); CSV formula and PDF markup injection neutralised; blocking DLP finding refuses; CORS exposes the headers | HTTP + real-Mongo + vitest | `{prefix} ... pytest backend/tests/test_autonomous_ops_export.py backend/tests/test_autonomous_ops_export_registry.py -q`; `npx vitest run src/__tests__/autonomousOpsExport.test.tsx` | ✅ | ✅ green |
| 86-07-T1, 86-07-T2 | 86-07 | 2 | D-14..D-16, D-20, D-21 (GATE-09) | T-86-15, T-86-16, T-86-17, T-86-18 | Lift refused (409) until 5 distinct checks recorded and 7 days since the first shadow record (to the second); unreadable input fails closed; shadow-on never gated; Super Admin only; audit event per lift/restore and per check; audit failure never undoes a lift; checks append-only (structural, with controls) | HTTP + structural | `{prefix} ... pytest backend/tests/test_autonomous_ops_golive.py -q` | ✅ | ✅ green |
| 86-14-T1, 86-14-T2 | 86-14 | 6 | D-23 (GATE-09) | T-86-14 | One test organization, marked by exact typed name (wrong name 422, platform org 409, unticked/unknown 404, second mark 409, race leaves one); only it lifts without the checks and the 7 days; unreadable mark exempts nobody; clear only while its shadow flag is on; Super Admin in a session only; module never names the evidence collection; runbook carries the real steps | HTTP + real-Mongo + structural | `cd backend && {prefix} ENVIRONMENT=development JWT_SECRET_KEY=test venv/bin/python -m pytest -q tests/test_autonomous_ops_golive_test_org.py tests/test_autonomous_ops_golive.py` | ✅ | ✅ green |
| 86-02-T1, 86-02-T2 | 86-02 | 1 | Success criterion 4 (D-13, GATE-06) | T-86-04 | Platform and tenant stop halt new decisions, hold back queued instructions, freeze approvals and rollouts, pause AI ticket replies; undo exempt; retention keeps running (documented); watchdog pauses restarts via the database source; other tenant unaffected; clean resume; unreadable stop counts as stopped | real-Mongo integration | `{prefix} TICKET_ATTACHMENT_DIR=$(mktemp -d) ... pytest backend/tests/test_autonomous_ops_stop_drill.py -q` | ✅ | ✅ green |
| 86-03-T1, 86-03-T2, 86-09-T2 | 86-03, 86-09 | 1, 3 | Success criterion 5 (D-17, GATE-11) | T-86-05, T-86-25 | Per-loop two-tenant contract (security sweep, rollout controller, desk worker, retention) + stats/export/digest isolation | real-Mongo | `{prefix} TICKET_ATTACHMENT_DIR=$(mktemp -d) ... pytest backend/tests/test_autonomous_ops_two_tenant.py -q` | ✅ | ✅ green |
| 86-09-T1 | 86-09 | 3 | Migration 035 | T-86-24 | Four indexes only, digest claim unique per tenant and day; second run changes nothing; runner discovers 035 after 034 and records it | real-Mongo | `{prefix} ... pytest backend/tests/test_migration_035_activity_reporting.py -q` | ✅ | ✅ green |
| 86-01-T3, 86-07-T2, 86-10-T2, 86-12-T1, 86-14-T2, 86-15-T2 | 86-01, 86-07, 86-10, 86-12, 86-14, 86-15 | 1, 2, 3, 5, 6, 7 | ACTV-08 | — | No banned term in new code, docs and UI; new files registered | static | `{prefix} ... pytest backend/tests/test_autonomous_ops_copy.py -q`; `npx vitest run src/__tests__/autonomousOpsCopy.test.ts` | ✅ | ✅ green |
| 86-10-T2 | 86-10 | 3 | GATE-09 (runbook) | — | `docs/autonomous-ops-go-live.md` has one section per check id with Summary lines, names `omni-watchdog.timer`, uses the address placeholder and carries no IPv4/IPv6 literal | static | the 86-10 Task 2 grep command (third `<automated>`) | ✅ | ✅ green |
| 86-04-T1, 86-04-T2, 86-11-T1, 86-11-T2, 86-12-T1, 86-12-T2 | 86-04, 86-11, 86-12 | 2, 4, 5 | UI (UI-SPEC) | T-86-06, T-86-27, T-86-29 | Statistics card, per-rule table, Export activity dialog, Reporting card disabled reasons, Going live card (record form, gate reasons, typed-name confirm, turn-back-on dialog) | vitest | `npx vitest run src/__tests__/autonomousOpsStats.test.tsx src/__tests__/autonomousOpsExport.test.tsx src/__tests__/autonomousOpsGoLive.test.tsx src/__tests__/AutonomousOpsActivity.test.tsx` | ✅ | ✅ green |
| 86-15-T1, 86-15-T2 | 86-15 | 7 | D-23 (GATE-09, UI) | T-86-15 | Mark / Clear dialogs with typed name; only the marked row shows the Test organization label and Clear test mark; server `canLift` still drives Lift; Lift dialog states the exemption | vitest | `npx vitest run src/__tests__/autonomousOpsGoLiveTestOrg.test.tsx src/__tests__/autonomousOpsGoLive.test.tsx` | ✅ | ✅ green |
| 86-06-T1 | 86-06 | 2 | D-18 (ACTV-06 prerequisite) | T-86-14 | The seven export-controls files are one standalone commit (db8b8cd4c), unchanged and secret-free; a git archive snapshot imports them and passes test_audit_export | git + snapshot | file-list diff of the D-18 commit, then `test_audit_export.py` from a `git archive` snapshot with the {prefix} | ✅ (existing test) | ✅ green |
| 86-13-T1 | 86-13 | 8 | Phase gate (all) | T-86-31 | Full backend suite on the working tree and on a `git archive` snapshot of HEAD, `npx vitest run src/__tests__`, `npm run build` | static + real-Mongo | see 86-13 Task 1 | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `backend/tests/test_autonomous_ops_digest.py`, `test_autonomous_ops_stats.py`, `test_autonomous_ops_export.py`, `test_autonomous_ops_golive.py`, `test_autonomous_ops_stop_drill.py`, `test_autonomous_ops_two_tenant.py`, `test_migration_035_activity_reporting.py` (plus `test_autonomous_ops_digest_job.py`, `test_autonomous_ops_export_registry.py`, `test_autonomous_ops_golive_test_org.py` added during execution)
- [x] `src/__tests__/autonomousOpsStats.test.tsx`, `src/__tests__/autonomousOpsGoLive.test.tsx` (plus `autonomousOpsExport.test.tsx`, `autonomousOpsGoLiveTestOrg.test.tsx`)
- [x] Edits to existing tests: `test_autonomous_ops_copy.py` and `src/__tests__/autonomousOpsCopy.test.ts` (EXPECTED lists, `FRONTEND_DIRECTORIES`), `test_autonomous_ops_ledger.py:327` (protected set), `test_catalogue_slice_autonomous_ops.py` (mount dict, platform module tuple)
- [x] No framework install needed

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Digest delivery to a real admin (in-app, and email once SMTP is configured) | ACTV-04 | Needs the live backend restarted after the phase and a real day boundary at 07:00 UTC; SMTP is not configured on this VM | After the user's restart, wait for 07:00 UTC; an admin of a ticked organization with activity (or simulation items) sees `Autonomous Ops daily digest` in the notification center; no notice on a quiet day |
| CSV and PDF download from the published UI | ACTV-06 | Browser download on the published build | Export activity → Download CSV / Download PDF; Reporting → Autonomous Ops Activity card; check the cap note and the audit-log entry |
| PDF page layout and readability | ACTV-06 | Tests assert the text, page break and header repeat only; layout is judged by eye (86-06 D-coverage) | Open a downloaded PDF with a full page of rows; check the summary page, the per-rule table and the repeated rows header |
| Visual fit at 320px and lg, light and dark (Statistics card and per-rule table, Export dialog and Reporting card, Going live card, test-organization row and dialogs) | UI-SPEC, D-23 | jsdom has no layout engine; overflow and wrapping need a real browser (86-04, 86-11, 86-12, 86-15) | On the published UI, view each card at 320px and at lg in both themes; long organization names (100 characters) and long file names wrap without overflow |
| Live stop drill on the server | Success criterion 4 | Real agent poll, real approvals, rollout and Ollama ticket reply | Walk check 5 of `docs/autonomous-ops-go-live.md`; record it on the Going live card |
| Firewall round-trip, reboot gate, watchdog stop/start, alert delivery | Success criterion 5 | Real agents (2.1.16+/2.1.17+), installed watchdog, real on-call channel | Walk checks 1-4 of `docs/autonomous-ops-go-live.md`; record each on the Going live card |
| Runbook reads correctly to an operator; test-organization flow on the live server (mark, lift, turn shadow back on, clear) | GATE-09, D-23 | Operator judgment and a live walk; no real tenant was marked or lifted during execution (86-10, 86-14, 86-15) | Follow the runbook from the text alone with a dedicated test organization; confirm each audit event |
| Observe-first soak and per-tenant lift out of shadow mode | D-15, D-16 | Live data over 7 days; the deployment-wide `AUTONOMOUS_REMEDIATION_DRY_RUN` switch is the user's env change + restart | After 7 days and all 5 checks recorded, a Super Admin lifts one organization (typed name); confirm the audit event |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (86-10-T1 and 86-13-T2 are human checkpoints; 86-13-T3 has read-only live checks)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 120s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-11-14 by /gsd-validate-phase 86. Re-run on the final code (HEAD 63241711c): Phase 86 backend map set 248 passed, 0 skipped (private mongod :27998); vitest Phase 86 files 6 files, 177 passed; HEAD `git archive` snapshot of `test_audit_export.py`, both export files and `test_notification_audience_structure.py` 58 passed; 86-10 runbook check passed. Phase gate (86-13): full backend suite 2819 passed, vitest `src/__tests__` 2180 passed, build green. Live behaviours stay in Manual-Only above.

## Validation Audit 2026-11-14

| Metric | Count |
|---|---|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |
