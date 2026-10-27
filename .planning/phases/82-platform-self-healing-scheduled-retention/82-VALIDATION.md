---
phase: "82"
slug: "platform-self-healing-scheduled-retention"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-27"
---

# Phase 82 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `82-RESEARCH.md` § Validation Architecture, against `82-CONTEXT.md` D-01..D-26 and `82-UI-SPEC.md`. Task IDs are assigned by the planner.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Backend and watchdog: pytest + pytest-asyncio (`asyncio_mode = auto`). Frontend: vitest 5 + @testing-library/react (jsdom). polkit rule: node stub harness (`backend/tests/polkit_rule_harness.js`). Unit files: `systemd-analyze verify` |
| **Config file** | `pytest.ini` (root), `backend/tests/conftest.py` (throwaway `omni_test_*` DB and audit spool); `vite.config.ts` `test:` block |
| **Quick run command** | `backend/venv/bin/python -m pytest backend/tests/test_watchdog_*.py backend/tests/test_retention_job*.py backend/tests/test_platform_health*.py -x -q -p no:cacheprovider` |
| **Full suite command** | `npx vitest run src/__tests__`, `npm run build`, and `TICKET_ATTACHMENT_DIR=$(mktemp -d) FILE_SHARE_DIR=$(mktemp -d) backend/venv/bin/python -m pytest backend/tests -q -p no:cacheprovider` |
| **Estimated runtime** | quick: under 30 s per file; full backend ~11 min (Phase 81 baseline) |

Fixtures to reuse: `backend/tests/_mongo_test_db.py` (`mongo_db`, real throwaway MongoDB, reachable on this VM), `backend/tests/_autonomous_ops_http.py` (`Api` helper mounting the Autonomous Ops routers with a per-request identity), `backend/tests/autonomy_support.py` (`seed_tenant`, `seed_platform_stop`). The watchdog script is loaded in tests with `importlib.util.spec_from_file_location` (hyphen in the file name) and driven with an injected `run` (fake `systemctl`), fake clock and local fake HTTP / socket servers.

---

## Sampling Rate

- **After every task commit:** the targeted test file(s) for the module touched (each under 30 s), plus any exact-list test it touches (ACTV-08 copy lists, route auth baseline).
- **After every plan wave:** the quick run command plus `backend/venv/bin/python -m pytest backend/tests/test_route_auth_baseline.py backend/tests/test_catalogue_route_parity.py backend/tests/test_autonomous_ops_copy.py -q -p no:cacheprovider` and `npx vitest run src/__tests__`.
- **Before `/gsd-verify-work`:** full backend suite and `npm test` / `npm run build` green.
- **Max feedback latency:** ~60 seconds per task.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 82-02-T1, 82-03-T1, 82-03-T3 | 82-02, 82-03 | 1, 2 | HEAL-01 | T-82-08, T-82-11 | Checks via fakes: MongoDB OP_MSG ping against a local fake server; backend ready / 503 / demo mode; nginx TLS reply; Ollama expected-off never started; MongoDB restarted before the backend; backend still not ready after MongoDB recovery is restarted; nginx in the fixed list (D-10) | unit (injected run/now/http) | `pytest backend/tests/test_watchdog_checks.py backend/tests/test_watchdog_restart.py -x` | ❌ W0 | ⬜ pending |
| 82-03-T2, 82-03-T3, 82-05-T1 | 82-03, 82-05 | 2, 4 | HEAL-02 | T-82-10, T-82-12, T-82-18 | 2-failure debounce (D-06), 3 restarts / 30 min with 1/2/4 min waits and give-up paging exactly once (D-07), re-arm after 1 h healthy (D-08), platform stop = restarts skipped with counters untouched (D-11), STOP file / cached stop / database stop precedence | unit, table-driven over time | `pytest backend/tests/test_watchdog_restart.py -x` | ❌ W0 | ⬜ pending |
| 82-04-T1, 82-04-T3 | 82-04 | 3 | HEAL-03 | T-82-13, T-82-15 | Certificate rungs at 30/14/7/1 days and expired from a generated test certificate; extra certificate paths from config (D-13); disk rungs 80/90/95 with hysteresis via injected statvfs (D-14); never renews / never deletes (structural grep) | unit + structural | `pytest backend/tests/test_watchdog_warnings.py -x` | ❌ W0 | ⬜ pending |
| 82-04-T2 | 82-04 | 3 | HEAL-04 | T-82-14 | Forecast: fewer than 7 days of history = insufficient; flat = no forecast; growth = days to full; 14/7/1-day rungs, page at 1 day (D-14) | unit | `pytest backend/tests/test_watchdog_warnings.py -k forecast -x` | ❌ W0 | ⬜ pending |
| 82-01-T1, 82-01-T3, 82-07-T1..T3, 82-08-T1..T3, 82-05-T1..T3 | 82-01, 82-07, 82-08, 82-05 | 1-4 | HEAL-05 | T-82-01, T-82-16..T-82-19, T-82-24..T-82-29 | PagerDuty Events v2 / webhook payloads against a local fake HTTP server (stable dedup_key, resolve, severity map, retries only on 429/5xx, one grouped page per run, test alert = trigger + resolve) (D-02, D-03, D-21); backend outbox fed by `notify` and drained by the watchdog (D-04); watchdog token auth on the loopback sync route (constant-time compare, proxy headers rejected); dead-man: silent after 300 s only after the first heartbeat, grace after backend start (D-05, D-24); `health` summary values; no key/URL/token in any API response | unit + real-Mongo + HTTP | `pytest backend/tests/test_watchdog_oncall.py backend/tests/test_watchdog_contract.py backend/tests/test_platform_health_sync.py backend/tests/test_platform_health_oncall.py backend/tests/test_platform_health_status.py -x` | ❌ W0 | ⬜ pending |
| 82-09-T1..T3, 82-10-T1..T3 | 82-09, 82-10 | 1, 2 | HEAL-06 | T-82-30..T-82-37 | Gate function table; first run counts only (D-18); confirm deletes from the next run; shortened period back to count-only for that tenant + type only (D-19); lengthening adopts; manual run honours the gate (D-26); 409 on a changed review token; audit_logs and `autonomy_actions` untouched, including after a manual run (D-16); audit_logs policy writes refused / Edit removed (D-25); batches bounded (seed N, assert batch sizes and pauses); nightly 02:00 UTC catch-up under the distributed lock (D-17); telemetry loop folded in (D-15) | unit + real-Mongo | `pytest backend/tests/test_retention_job.py backend/tests/test_retention_gate.py backend/tests/test_retention_endpoints_phase82.py backend/tests/test_platform_retention_review.py -x` | ❌ W0 | ⬜ pending |
| 82-01-T1, 82-01-T2, 82-10-T1 | 82-01, 82-10 | 1, 2 | HEAL-07 | T-82-02, T-82-03 | Ingest creates `kind: "platform_health"` rows idempotently; Super Admin platform list shows them with `counts.platform_health`; tenant admins and Platform Support (including `tenantId=platform-admin`) see none (D-23); bucket mapping | real-Mongo + HTTP | `pytest backend/tests/test_platform_health_activity.py -x` | ❌ W0 | ⬜ pending |
| 82-06-T1..T3 | 82-06 | 1 | HEAL-08 | T-82-20..T-82-23 | Units pass `systemd-analyze verify`; no `RuntimeMaxSec` on a oneshot; polkit rule harness 8/8 + ES5 lint, unit + verb allowlist only (D-12); drop-ins use new file names only (existing mongod drop-ins untouched); `INSTALL.md` exists and names every file; no backend module calls `systemctl` or writes `/etc`; `start-all-services.sh` does not reference the watchdog | structural / unit | `pytest backend/tests/test_watchdog_artifacts.py -x` | ❌ W0 | ⬜ pending |
| 82-11-T1..T3, 82-12-T1..T3, 82-13-T1..T3, 82-14-T1..T3 | 82-11..82-14 | 4-6 | UI (D-20..D-26) | T-82-38..T-82-45 | Health banners (priority, arming after first heartbeat, Super Admin only), section states, test-alert state machine, retention review table / Confirm deletion dialog / 409, Activity `Platform health` pill and client-side drop outside platform scope, tenant Retention Policy notices, copy test file list | vitest | `npx vitest run src/__tests__/AutonomousOpsPlatformHealth.test.tsx src/__tests__/AutonomousOpsHealthCards.test.tsx src/__tests__/AutonomousOpsRetentionReview.test.tsx src/__tests__/AutonomousOpsHealthBanners.test.tsx src/__tests__/AutonomousOpsActivityPlatformHealth.test.tsx src/__tests__/RetentionPolicyDashboard.test.tsx src/__tests__/autonomousOpsCopy.test.ts` | ❌ W0 (copy test exists) | ⬜ pending |
| 82-01-T3, 82-10-T3, 82-11-T3, 82-12-T2, 82-12-T3, 82-13-T3 | 82-01, 82-10..82-13 | 1-6 | Drift | — | Route auth baseline (token routes reviewed), catalogue parity, ACTV-08 file lists | existing | `pytest backend/tests/test_route_auth_baseline.py backend/tests/test_catalogue_route_parity.py backend/tests/test_autonomous_ops_copy.py -x` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_watchdog_checks.py`, `test_watchdog_restart.py`, `test_watchdog_warnings.py`, `test_watchdog_oncall.py`, `test_watchdog_artifacts.py` — load `deploy/omni-watchdog/omni-watchdog.py` via `importlib.util.spec_from_file_location`; fake `systemctl` runner, fake clock, local `http.server` fakes for backend / PagerDuty / webhook, socket fake for the MongoDB ping
- [ ] `backend/tests/test_platform_health_sync.py`, `test_platform_health_status.py`, `test_platform_health_activity.py`, `test_retention_job.py`, `test_retention_gate.py`, `test_retention_endpoints_phase82.py` — using `mongo_db` and the `Api` helper
- [ ] `src/__tests__/AutonomousOpsPlatformHealth.test.tsx`, `AutonomousOpsRetentionReview.test.tsx`, `AutonomousOpsHealthBanners.test.tsx`
- [ ] `backend/tests/polkit_rule_harness.js` (the verified stub harness from research) and the ES5 lint
- [ ] Every new file added to `shared/autonomous-ops-banned-terms.json` `files`, to `EXPECTED_FILES` in `test_autonomous_ops_copy.py` and to the vitest copy test
- [ ] Watchdog token routes added to `REVIEWED_UNAUTHENTICATED` in `test_route_auth_baseline.py` with the "credential checked inside the handler" comment
- [ ] Migration test for any new migration (following `test_autonomous_ops_migration.py`)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Watchdog units, polkit rule and drop-ins installed; `omni-watchdog` user and directories created | HEAL-08 | Installing on the live server is the operator's step; the app installs nothing | Follow `deploy/omni-watchdog/INSTALL.md`; never `run-on-ubuntu.sh`; then `pkcheck --action-id org.freedesktop.systemd1.manage-units --details unit nginx.service --details verb restart` as the watchdog user |
| Real stop / start of MongoDB and the backend is noticed and restarted, MongoDB first | HEAL-01, HEAL-02 | Needs the installed units and real service restarts | Stop `mongod` (and the backend) on the server; watch the panel and Activity within about 2 minutes; confirm restart order and that the GLIBC_TUNABLES drop-in still applies after a watchdog-triggered restart |
| Test alert reaches the real on-call channel once; external heartbeat configured | HEAL-05 | Needs the real PagerDuty key / webhook URL in the root-only file and outbound HTTPS | Fill `/etc/omni-watchdog/oncall.env`; press Send test alert; confirm one alert arrives and resolves; confirm the "no working channel" banner clears |
| First retention count reviewed and confirmed before anything is deleted | HEAL-06 | Live data; deletion is irreversible | After the first 02:00 UTC run, review counts on the Platform health panel, then Confirm deletion |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
