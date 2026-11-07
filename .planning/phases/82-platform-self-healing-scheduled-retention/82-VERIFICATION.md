---
phase: 82-platform-self-healing-scheduled-retention
verified: 2026-11-07T14:30:00Z
status: passed
score: 5/5 must-haves verified
covered_files:
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-01-PLAN.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-01-SUMMARY.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-02-PLAN.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-02-SUMMARY.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-03-PLAN.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-03-SUMMARY.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-04-PLAN.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-04-SUMMARY.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-05-PLAN.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-05-SUMMARY.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-06-PLAN.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-06-SUMMARY.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-07-PLAN.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-07-SUMMARY.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-08-PLAN.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-08-SUMMARY.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-09-PLAN.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-09-SUMMARY.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-10-PLAN.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-10-SUMMARY.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-11-PLAN.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-11-SUMMARY.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-12-PLAN.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-12-SUMMARY.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-13-PLAN.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-13-SUMMARY.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-14-PLAN.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-14-SUMMARY.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-15-PLAN.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-15-SUMMARY.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-16-PLAN.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-16-SUMMARY.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-17-PLAN.md
  - .planning/phases/82-platform-self-healing-scheduled-retention/82-17-SUMMARY.md
  - backend/autonomous_ops/health_messages.py
  - backend/autonomous_ops/selfheal.py
  - backend/autonomous_ops_retention_endpoints.py
  - backend/retention_endpoints.py
  - backend/retention_gate.py
  - backend/retention_job.py
  - backend/retention_service.py
  - backend/watchdog_ingest_endpoints.py
  - components/AutonomousOpsRetentionConfirmDialog.tsx
  - components/AutonomousOpsRetentionReview.tsx
  - components/RetentionPolicyDashboard.tsx
  - deploy/omni-watchdog/omni_watchdog/restart.py
  - deploy/omni-watchdog/omni_watchdog/warnings.py
covered_digest: "v3:sha256:e7b7dd81b91435372acd45e9295e99b7d9c8fb480b7291dba7e236cd10eac285"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 5/5
  gaps_closed: []
  gaps_remaining: []
  regressions: []
  notes:
    - "Previous report (2026-10-31, human_needed 5/5) went stale because shared files changed after it (Phases 83, 84, 87 and the 2026-11-04/05 audit rounds). Re-checked against HEAD b4e450eda."
    - "WR-06 (advisory in the previous report) is fixed in 79191ef5e and re-verified here; WR-04 (legacy RetentionService delete paths) is fixed in 1ff293e66 and re-verified here."
    - "The five human items of the previous report were persisted as 82-UAT.md and are complete, 5/5 passed (2026-11-07). They are not re-raised."
human_verification_accepted:
  - item: "UAT 1-4 (watchdog install and polkit, real stop/restart of mongod and backend, real on-call channel and heartbeat, first live retention count and confirmation)"
    state: "Accepted by the user on 2026-11-07 (82-UAT.md, 5/5 pass). Each carries the note that this VM (Omniai-copy) has no omni-watchdog timer and no /etc/omni-watchdog, so the checks were not run on this server. This report records that as the user's acceptance, not as verifier evidence."
  - item: "UAT 5 (browser pass, light and dark, 640/1024/1280 px)"
    state: "Passed 2026-11-05 in headless Chrome on the release bundle against a private copy; only the not-installed and never-counted states could show."
---

# Phase 82: Platform Self-Healing and Scheduled Retention Verification Report

**Phase Goal:** The platform watches its own health from outside the backend, restarts what fails within a budget, warns well before certificates expire or disks fill, pages the on-call person, and runs data retention on a schedule without ever touching audit evidence.
**Verified:** 2026-11-07
**Status:** passed
**Re-verification:** Yes. The 2026-10-31 report went stale after later phases edited shared files. Judged against committed HEAD `b4e450eda`.

## Goal Achievement

I started from the hypothesis that the goal had regressed under the later phases (83, 84, 87) and the audit rounds. I looked for regressions in four places: the Phase 82 files themselves, the shared files the phase wires into, the retention safety rule (the one defect the earlier rounds found), and the tests.

**Phase 82's own files are unchanged since the last verification apart from two fix commits.** `git log bb5889529..HEAD` over the covered backend, UI and `deploy/omni-watchdog` files shows only:

- `79191ef5e` (2026-10-31, WR-06): a tenant's manual retention run no longer rewrites a usable stored count, so it cannot move the Super Admin's review token. Re-read at HEAD: `_record_count(..., keep_usable=True)` in `retention_job.py` returns the fresh answer but leaves a usable stored row alone.
- `1ff293e66` (2026-11-04, WR-04): the legacy `RetentionService` now raises on construction, so its un-gated, tenant-unfiltered delete methods cannot be reached. Re-read at HEAD.

Nothing under `deploy/omni-watchdog/` changed. The later-phase commits that touched shared files (`app_startup.py`, `router_registry.py`, `autonomous_ops/ledger.py`, `delivery.py`) were checked by wiring and by the tests below, not by diff reading alone. The retention loop (`app_startup.py:536-537`), the self-heal and dead-man loop (`:530-532`) and the two routers (`router_registry.py:348`, `:351`) are still registered.

### Observable Truths (ROADMAP success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Watchdog notices a stopped MongoDB, backend or (where expected) Ollama within about a minute, restarts from a fixed allowlist, MongoDB before backend; after the budget it backs off, stops restarting and pages once | VERIFIED (code and fakes) | `restart.py`: `WAITS = (60, 120, 240)`, `BUDGET = 3`. `test_watchdog_restart`, `test_watchdog_restart_order`, `test_watchdog_checks` pass on HEAD. Real systemd restarts were not exercised by me. The user accepted this in UAT 2 |
| 2 | Warned at 30/14/7/1 days (certificate), 80/90/95 percent (disk), and days ahead by growth forecast; never renews or deletes | VERIFIED | `warnings.py`: `CERT_LADDER` 1/7/14/30, `DISK_LADDER` 80/90/95, `FORECAST_LADDER` 1/7/14. The audit-facing rule id derives from the unrounded `daysLeft` (WR-02 fix still in place). `test_watchdog_warnings`, `test_platform_health_status` pass |
| 3 | Test alert arrives once; banner when no working channel; alert when the watchdog stops reporting | VERIFIED in code; live delivery accepted by the user | `test_watchdog_oncall`, `test_platform_health_oncall`, `test_platform_health_deadman` pass. UAT 3 passed by the user; no channel exists on this VM |
| 4 | Retention runs on a schedule per tenant in bounded batches, never touches audit logs, the audit ledger or decision records; the first run is a dry-run count the operator confirms before anything is deleted | VERIFIED | See "Retention safety re-check" below |
| 5 | Watchdog events appear in platform-scope Activity; the repo ships units, drop-ins and checklist; the app installs nothing | VERIFIED | `deploy/omni-watchdog/` still holds `INSTALL.md`, `systemd/` (service, timer, and mongod, nginx and omni-backend drop-in dirs), `polkit/49-omni-watchdog.rules`, `etc/*.example`. `test_platform_health_activity`, `test_watchdog_artifacts` pass |

**Score:** 5/5 truths verified (0 present, behavior-unverified). No override applied.

### Retention safety re-check (HEAD)

- **Audit evidence is excluded by construction.** `retention_gate.py` defines `NEVER_DELETED` (audit_logs, audit_chain_heads, audit_chain_checkpoints, autonomy_actions, autonomy_settings, autonomy_never_touch, compliance_evidence, plus `PROTECTED_COLLECTIONS`) and asserts at import that the eight registry collections are disjoint from it. `delete_type` in `retention_job.py` raises `RuntimeError` if given a protected collection. The eight registry types are metrics, notifications, agent_location_history, agent_uptime_rollups, agent_metrics, asset_metrics, persistence_results and logs. The `logs` type is agent-collected log events, not `audit_logs`.
- **The CR-01 fix still holds.** `gate_state` returns `adopt` only when the tenant's own readable creation time is strictly after the one global confirmation; every other unconfirmed case, including an unreadable time, is `first_run` (count only). `confirm()` refuses with `ReviewIncomplete` before any write when a tenant has no gate rows. The pinning tests (`test_retention_unreached` and the updated gate, job, endpoint and review tests) pass on HEAD.
- **Bounded batches.** `delete_type` deletes at most `BATCH_SIZE` tenant-scoped `_id` values per pass, pauses, and honours a lost lock and a deadline.
- **WR-06 (an advisory last time) is closed.** Verified in code above and by the tests that ship with `79191ef5e`.
- **WR-04 is closed.** The legacy service refuses to construct at HEAD, so no un-gated path survives.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `deploy/omni-watchdog/omni_watchdog/*.py`, `omni-watchdog.py` | stdlib watchdog | VERIFIED | 1,985 lines in the package, unchanged since the last report |
| `deploy/omni-watchdog/systemd`, `polkit`, `etc`, `INSTALL.md` | units, drop-ins, rule, checklist | VERIFIED (shipped, not installed) | HEAL-08 asks only that the repo ships them |
| `backend/watchdog_ingest_endpoints.py` | token sync and results | VERIFIED | registered `router_registry.py:351` |
| `backend/autonomous_ops/selfheal.py`, `health_messages.py` | state, dead-man, messages | VERIFIED | loop started `app_startup.py:530-532` |
| `backend/retention_gate.py`, `retention_job.py` | registry, gate, nightly job | VERIFIED | `retention_loop` started `app_startup.py:536-537` |
| `backend/autonomous_ops_retention_endpoints.py`, `retention_endpoints.py` | review, confirm, manual run | VERIFIED | registered `router_registry.py:348` |
| `components/AutonomousOpsRetentionReview.tsx`, `...ConfirmDialog.tsx`, `RetentionPolicyDashboard.tsx` | review UI | VERIFIED | covered by the UI tests below |

### Key Link Verification

| From | To | Status | Details |
|------|----|--------|---------|
| retention_loop | run_once, run_all, run_tenant, gate_state | WIRED | single runner by lock |
| confirm() | incomplete_review | WIRED | before any write |
| tenant manual run | review token | WIRED (WR-06 fix) | `keep_usable` leaves a usable count alone |
| watchdog | /api/internal/watchdog/sync, then ledger platform_health rows | WIRED | per-event isolation in `selfheal` |
| ledger | Activity, platform scope | WIRED | `test_platform_health_activity` passes after the Phase 84 ledger edits |

### Data-Flow Trace (Level 4)

Review rows render from `retention_counts`, written by `_record_count` from a real `count_documents` on the raw handle with the stored tenant field. Not static. Unchanged.

### Behavioral Spot-Checks

All on the private mongod 127.0.0.1:27998. Nothing ran against 27017.

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Retention gate, job, unreached-tenant, review, endpoints; health sync; watchdog restart, restart order, warnings, artifacts; dead-man | `pytest test_retention_unreached test_retention_gate test_retention_job test_platform_retention_review test_retention_endpoints_phase82 test_platform_health_sync test_watchdog_restart test_watchdog_restart_order test_watchdog_warnings test_watchdog_artifacts test_platform_health_deadman` | 388 passed in 66 s | PASS |
| Activity, status, on-call, migration; watchdog checks, contract, on-call, sync; route auth baseline | `pytest test_platform_health_activity test_platform_health_status test_platform_health_oncall test_platform_health_migration test_watchdog_checks test_watchdog_contract test_watchdog_oncall test_watchdog_sync test_route_auth_baseline` | 202 passed in 39 s | PASS |
| Orchestrator gates on HEAD | Phase 82 backend files, 590 passed, 0 failed; `npx vitest run src/__tests__`, 108 files, 1,606 passed; `test_autonomous_ops_*` + `test_patch_*` + `test_maintenance_windows`, 1,531 passed | as reported by the orchestrator | Reported, not re-run by me |

Not run by me: the UI tests (reported green by the orchestrator, 1,606 passed), the full backend suite, and `npm run build`. I did not re-run the CR-01 reproduction script (it is not on disk); the pinning tests cover the same sequence and pass.

### Probe Execution

No `probe-*.sh` declared by the plans. SKIPPED.

### Requirements Coverage

All eight HEAL ids are claimed by the Phase 82 plans and defined in REQUIREMENTS.md lines 56-63. No ids map to Phase 82 without a plan claiming them (no orphans).

| Requirement | Status | Evidence |
|-------------|--------|----------|
| HEAL-01 watchdog outside the backend, minute checks, allowlist restart, mongo first | SATISFIED | restart and check tests pass; repo ships the units |
| HEAL-02 budget, backoff, page once | SATISFIED | `WAITS`, `BUDGET`, sticky give-up; tests pass |
| HEAL-03 30/14/7/1 cert, 80/90/95 disk, never renews or deletes | SATISFIED | ladders in `warnings.py` |
| HEAL-04 growth forecast | SATISFIED | `FORECAST_LADDER`, tests pass |
| HEAL-05 webhook or PagerDuty, dedup, test alert, banner, dead-man | SATISFIED | on-call and dead-man tests pass; live delivery accepted in UAT 3 |
| HEAL-06 scheduled, bounded, never audit, first run dry-run confirmed | SATISFIED | retention safety re-check above |
| HEAL-07 events in platform Activity | SATISFIED | Activity test passes on HEAD |
| HEAL-08 repo ships units, drop-ins, checklist | SATISFIED | `deploy/omni-watchdog/` |

**REQUIREMENTS.md state, for the orchestrator (I did not edit it):** lines 56-63 are all still `[ ]` and the traceability rows for HEAL-01..08 read "Gaps Found" (lines 212-219 now). That is stale against this report; the orchestrator should update both.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| backend/retention_job.py | run-in-progress branch | "run without finishedAt" branch can never match (IN-08) | INFO | run-in-progress rests on the lock only |
| backend/retention_gate.py | `gate_state` parameter | `tenant_created_at` shadows the module function (IN-06) | INFO | latent |
| backend/seed_demo_data.py | 19-30 | rewrites `createdAt` for existing tenants (IN-07) | INFO | latent, manual script; adoption keys on `createdAt` |

No unreferenced `TBD`, `FIXME` or `XXX` found in the phase's modified files. Both Phase 82 REVIEW blockers and warnings are recorded as closed in `82-REVIEW-DISPOSITION.md`; I did not re-run a code review (skipped on purpose for this run, since the phase's own task commits have not changed since the last review).

### Working-tree note (judged on HEAD)

The tree holds the user's uncommitted work. Two Phase 82 files differ from HEAD:

- `backend/retention_endpoints.py`: four added `_POLICY_DEFAULTS` entries (agent_metrics, asset_metrics, persistence_results, logs). This only adds entries to the policy-listing defaults dict; the nightly job's registry in `retention_gate.py` already holds those four types, unchanged.
- `backend/retention_service.py`: adds `AGENT_TELEMETRY`, `cleanup_agent_telemetry` and `purge_agent_telemetry`, and keeps `RetentionService.__init__` raising. I found no caller of `purge_agent_telemetry`, and `RetentionService` cannot be constructed, so `run_cleanup` and the new telemetry path are unreachable from the app. The new code deletes by ObjectId creation time with no confirmation gate and no batching. If a caller is ever wired to `purge_agent_telemetry`, it would bypass the HEAL-06 first-run confirmation. As it stands it does not change the verdict, but I would not commit it wired in.

The tests above ran on the working tree (with these edits) and passed. The `covered_digest` is computed on the working-tree contents, so it will go stale when these two files are committed or reverted. That is expected.

### Human Verification

None new. The five items of the previous report were persisted as `82-UAT.md` and are complete, 5/5 passed (2026-11-07). Items 1-4 carry the user's note that this VM (Omniai-copy) has no omni-watchdog timer and no `/etc/omni-watchdog`, so those checks were not run on this server; they are recorded here as the user's acceptance. I found no must-have that needs a distinct human check beyond them.

### Gaps Summary

None. All five success criteria and all eight HEAL requirements hold on HEAD. The earlier blocker (CR-01) and the earlier warnings (WR-01 to WR-06, including the advisory one) are closed and re-verified. 82-SECURITY.md reports `threats_open: 0`, which I did not re-audit.

---

_Verified: 2026-11-07_
_Verifier: Claude (gsd-verifier)_
