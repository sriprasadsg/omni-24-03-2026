---
phase: 82-platform-self-healing-scheduled-retention
verified: 2026-10-31T13:00:00Z
status: human_needed
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
  - components/AutonomousOpsRetentionConfirmDialog.tsx
  - components/AutonomousOpsRetentionReview.tsx
  - components/RetentionPolicyDashboard.tsx
  - deploy/omni-watchdog/omni_watchdog/restart.py
  - deploy/omni-watchdog/omni_watchdog/warnings.py
covered_digest: "v3:sha256:97f12ccf4c67dc5d806d6310423c7565508af6c2c0b15305b567dc463a3097c1"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 4/5
  gaps_closed:
    - "CR-01: a tenant the first pass never reached is deleted with no count and no confirmation (SC4 / HEAL-06)"
    - "WR-01: Confirm deletion enabled while review pages remain unloaded (T-82-42)"
    - "WR-02: certificate ruleId off by one rung (HEAL-03 audit-facing id)"
    - "WR-03: a malformed watchdog event wedges the sync (T-82-04), including the non-string kind hole found by the security audit (cbdb97708, T-82-50)"
  gaps_remaining: []
  regressions: []
advisory:
  - finding: "WR-06: Run Cleanup Now by any tenant admin re-stamps countedAt, which moves the review token and can keep the Super Admin's Confirm deletion answering 409 while a script loops on POST /api/retention/run"
    category: other
    reason: "Confirmed in code (retention_job.py:81-84, retention_endpoints.py:99-115). Availability of one confirmation step only; it can never cause a deletion. Fix is small (skip the count write when days, count and error are unchanged)."
    evidence_status: "code read; not reproduced against a mongod"
    resolution: "Fixed after this report in 79191ef5e, with tests that failed first; the rate limit covers the lock path. Not re-verified by a verifier run."
human_verification:
  - test: "Install the watchdog on the server by hand following deploy/omni-watchdog/INSTALL.md (never run-on-ubuntu.sh), then run pkcheck as the omni-watchdog user for nginx.service restart"
    expected: "Timer active; polkit allows exactly the listed units and verbs; the existing mongod GLIBC_TUNABLES drop-in still applies; deployed ownership and modes match T-82-06/20/21/22"
    why_human: "Operator step; nothing is installed on this host. HEAL-08 asks the repo to ship the files, which it does"
  - test: "Stop mongod, then the backend, on the installed server"
    expected: "Noticed within about 2 minutes, mongod restarted first, backend second; after 3 failed restarts one page only; panel and Activity show each step"
    why_human: "Needs real units, real restarts and polkit; unit tests use fakes"
  - test: "Fill /etc/omni-watchdog/oncall.env, press Send test alert, set the external heartbeat URL"
    expected: "One alert arrives and resolves; the no-working-channel banner clears; stopping the watchdog raises the in-app alarm and the external heartbeat service alerts"
    why_human: "Needs a real PagerDuty key or webhook and outbound HTTPS. The in-app dead-man alarm is by design not queued for on-call (a silent watchdog cannot send it); the out-of-band alert depends on the external heartbeat URL"
  - test: "After deploy, review the first 02:00 UTC retention count on the Platform health panel and Confirm deletion"
    expected: "Counts for every organization are listed, nothing is deleted before the confirmation, and the next run deletes only confirmed rows. Confirm only on a build that includes 82-15 to 82-17"
    why_human: "Live data; deletion is irreversible; nothing is deployed"
  - test: "Open Autonomous Ops platform health and the retention review in a published UI, light and dark, at 640, 1024 and 1280 px"
    expected: "Layout matches 82-UI-SPEC sections 1-7"
    why_human: "UI not published; layout and dark theme are visual"
---

# Phase 82: Platform Self-Healing and Scheduled Retention Verification Report

**Phase Goal:** The platform watches its own health from outside the backend, restarts what fails within a budget, warns well before certificates expire or disks fill, pages the on-call person, and runs data retention on a schedule without ever touching audit evidence.
**Verified:** 2026-10-31
**Status:** human_needed
**Re-verification:** Yes, after gap closure (plans 82-15, 82-16, 82-17 and the follow-up commit cbdb97708)

## Goal Achievement

The previous report found one blocking defect (CR-01, retention deleting data of a tenant the first count pass never reached) plus WR-01, WR-02 and WR-03. I re-checked each against the current code rather than the summaries. All four are closed. I re-ran the CR-01 sequence myself on a private mongod and it no longer deletes anything unconfirmed. No code gap remains that blocks a must-have. What is left is the operator-side work the phase deliberately does not do (install, real restarts, real on-call channel, browser pass), plus one open warning (WR-06) that I judged non-blocking.

### Observable Truths (ROADMAP success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Watchdog notices a stopped MongoDB, backend or (where expected) Ollama within about a minute, restarts from a fixed allowlist, MongoDB before backend; after the budget it backs off, stops restarting and pages once | VERIFIED (code and fakes) | Unchanged since the first verification; `test_watchdog_checks/restart/restart_order/contract` pass again (225 + 92 across the watchdog and health modules). Real restarts need an install (human item 2) |
| 2 | Warned at 30/14/7/1 days (cert), 80/90/95 percent (disk), days ahead by growth forecast; never renews or deletes | VERIFIED | `warnings.py` ladders unchanged. The WR-02 defect is fixed: `health_messages._cert_rule` (lines 147-155) derives the rule from the unrounded `daysLeft` with `<=` comparisons, mirroring `CERT_LADDER` (`warnings.py:27`); `cert-unreadable` is its own rule. The watchdog sends the unrounded `daysLeft` in the event params (`warnings.py:136`). Sync and status tests pass |
| 3 | Test alert arrives once; banner when no working channel; alert when watchdog stops reporting | VERIFIED in code, live delivery unverified | `test_watchdog_oncall`, `test_platform_health_oncall/deadman/status` pass. Needs a real channel (human item 3) |
| 4 | Retention runs on a schedule per tenant in bounded batches, never touches audit logs/ledger/decision records; first run is a dry-run count the operator confirms before anything is deleted | VERIFIED (CR-01 closed, reproduced) | See the CR-01 re-check below. `NEVER_DELETED` is asserted disjoint at import (`retention_gate.py:81`) and `delete_type` raises for a protected collection (`retention_job.py:97`). Scheduling at 02:00 UTC under the distributed lock, 500-id batches with 0.5 s pauses and the 60-minute cap are unchanged |
| 5 | Watchdog events appear in platform-scope Activity; the repo ships units, drop-ins and checklist; the app installs nothing | VERIFIED | `deploy/omni-watchdog/` has INSTALL.md, `systemd/` (service, timer, three drop-in dirs), `polkit/49-omni-watchdog.rules`, `etc/`; `test_platform_health_activity` and `test_watchdog_artifacts` pass |

**Score:** 5/5 truths verified (0 present, behavior-unverified). No override applied.

### CR-01 re-check (this verifier, private mongod on 27998, not the live server)

Script: `/tmp/claude-1000/-home-azureuser-enterprise-omni-agent-ai-platform/554b30f1-625e-4ceb-8777-9bc01f012660/scratchpad/repro_cr01_reverify.py`. It builds on the first report's repro and adds variants. Output:

```
[orig createdAt=False] review rows tenants: ['t-a']
  confirm: REFUSED ReviewIncomplete gap= {'reason': 'not_reached', 'tenants': 1}
  t-z before: 5 / after next nightly: 5   counts row: {'count': 3, 'days': 30}   t-a after: 2
[orig createdAt=True]  same: REFUSED, t-z 5 -> 5, counted 3
[manual] unreached pre-existing t-z: {'state': 'first_run', 'days': 30, 'count': 3} remaining 5
[poison] failedTenants ['t-b'] tenants reached 2 incomplete_review: {'reason': 'tenant_failed', 'tenants': 1} run row written: 1
[design] tenant created after confirm: t-new remaining 2 (by design A-82-A12); t-a remaining 2
[design] unreadable createdAt t-bad remaining 3
```

What this shows against the exact first-report scenario (two tenants, first pass reached only t-a):

1. **Layer one, the confirmation itself.** The Super Admin's confirm is now refused with `ReviewIncomplete` because t-z has no gate rows (`incomplete_review`, `retention_gate.py:262-298`, called inside `confirm()` before any write at `:322-324`). Before the fix the same call succeeded.
2. **Layer two, the deleting rule.** I then forced the t-a rows confirmed directly in the database, which is the old failure's precondition. The next nightly run counted t-z (3) and left all 5 of its records. `gate_state` (`:129-143`) returns `adopt` only when the tenant's own readable creation time is strictly after the global confirmation; everything else unconfirmed is `first_run`. Before the fix t-z went from 5 to 2.
3. **POST /api/retention/run path.** `run_manual` for an unreached, pre-existing tenant returns state `first_run` with a count and deletes nothing (previously `adopt` and deleted 3).
4. **One tenant failing.** `run_all` (`retention_job.py:175-182`) guards each tenant on `Exception`, records `failedTenants`, and always writes the run row (`:195`). Confirmation then refuses with `tenant_failed` until the next complete scheduled run.
5. **Fails closed.** An unreadable `createdAt` stays `first_run` (t-bad kept all 3 records). A tenant created after the confirmation is adopted, which is the documented design (A-82-A12), not a regression.

Targeted tests that pin this: `backend/tests/test_retention_unreached.py` (407 lines), plus updates to `test_retention_gate.py`, `test_retention_job.py`, `test_platform_retention_review.py`, `test_retention_endpoints_phase82.py`. They are in the passing run below. 82-VALIDATION.md records that the CR-01 reproduction test failed on the pre-fix code (`assert 2 == 5`) and that three further tests were run against older exported code; I did not repeat that.

### Other gaps from the first report

| Gap | Status | Evidence |
|-----|--------|----------|
| WR-01 Confirm enabled with unloaded pages | CLOSED | `AutonomousOpsRetentionReview.tsx:262` `allLoaded = state?.nextOffset === null`; the button is disabled by `!allLoaded` and by `incomplete !== null` (line 346); an undefined state is also not `=== null`, so it fails closed. The dialog's Keep waiting is disabled and Esc closed while pending (`AutonomousOpsRetentionConfirmDialog.tsx:82,85`). The server side still confirms every eligible row (see limit in 82-SECURITY.md Audit Notes: "every row loaded" is a client-side guard) |
| WR-02 cert ruleId | CLOSED | `health_messages.py:147-155` as above |
| WR-03 poison event / number | CLOSED | `selfheal.py:174-208`: per-event guard on `Exception` (not `BaseException`), `LedgerUnavailable` keeps its keep-in-spool meaning, `clean_params` inside the `try`, `_storable` rejects non-finite floats and integers outside signed 64-bit (`:86-95`) |
| cbdb97708 non-string kind | CLOSED | `selfheal.py:191` `not isinstance(kind, str)` precedes the set lookup. This commit is outside any plan SUMMARY; it is documented in 82-SECURITY.md Audit Notes and covered by an added table test in `test_platform_health_sync.py` |
| WR-05 Run Cleanup Now showing success for refusals | CLOSED | `RetentionPolicyDashboard.tsx:49-60` checks `r.ok` and a string `ran_at` and has a `catch` |

### WR-06 judgment (open in 82-REVIEW.md): does not block a must-have or the phase goal

I confirmed the mechanism in code. `review_token` hashes `countedAt` per waiting row (`retention_gate.py:303`); `_record_count` writes `countedAt: now` on every count even when nothing changed (`retention_job.py:81-84`); `POST /api/retention/run` is open to any tenant admin for their own tenant (`retention_endpoints.py:99-115`) and recounts that tenant's waiting rows under the job lock. Default rate limit is 600/minute (`rate_limiter.py:18`). So a tenant admin looping on that route can keep the Super Admin's Confirm answering 409 (stale review or run in progress) until the loop stops, and an honest press during a review can cause the same 409 once.

Why it does not block:

- **No must-have needs the confirmation to be uncontestable.** SC4 requires that nothing is deleted before the operator confirms. WR-06 does the opposite of loosening that: it can only delay a confirmation. A refused or stale confirm deletes nothing and the next attempt (reload the review, confirm) succeeds as soon as the stalling stops.
- **No deletion or cross-tenant data exposure follows.** The manual run goes through the same gate, so a tenant still waiting for review is only counted.
- **Precondition is a signed-in tenant admin deliberately abusing a route**, and the effect clears when they stop. It is an availability concern for one admin action, not a safety one.

It is still worth fixing before deploy (the reviewer's fix is small: skip the count write when days, count and error are unchanged), and I would add a per-tenant rate limit on the route. I list it as advisory, not a gap.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `deploy/omni-watchdog/omni_watchdog/*.py`, `omni-watchdog.py` | stdlib watchdog | VERIFIED | 1,985 lines in the package; tested through fakes |
| `deploy/omni-watchdog/systemd`, `polkit`, `etc`, `INSTALL.md` | units, drop-ins, rule, checklist | VERIFIED (shipped, not installed) | HEAL-08 asks only that the repo ships them |
| `backend/watchdog_ingest_endpoints.py` | token sync/results | VERIFIED | registered `router_registry.py:343` |
| `backend/autonomous_ops/selfheal.py`, `health_messages.py` | state, dead-man, messages | VERIFIED | dead-man loop started `app_startup.py:513-515` |
| `backend/retention_gate.py`, `retention_job.py` | registry, gate, nightly job | VERIFIED | `retention_loop` started `app_startup.py:519-520` |
| `backend/autonomous_ops_retention_endpoints.py`, `retention_endpoints.py` | review, confirm, manual run | VERIFIED | `router_registry.py:342`; confirm path checks `run_in_progress`, `StaleReview`, `ReviewIncomplete` (lines 109-118) |
| `components/AutonomousOpsRetentionReview.tsx`, `...ConfirmDialog.tsx` | review UI | VERIFIED | WR-01 fixed |

### Key Link Verification

| From | To | Status | Details |
|------|----|--------|---------|
| retention_loop | run_once -> run_all -> run_tenant -> gate_state | WIRED | single runner by lock |
| confirm() | incomplete_review | WIRED | called before any write; 409 REVIEW_INCOMPLETE |
| confirm() | next run's gate_state | WIRED | unreached tenants stay `first_run`, so they are counted, not adopted |
| watchdog -> /api/internal/watchdog/sync | ledger platform_health rows | WIRED | per-event isolation now in `ingest_events` |
| ledger -> Activity | platform scope only | WIRED | server filter plus client second guard |
| `retention_service.py` legacy delete paths | any caller | NOT_WIRED | WR-04 remains open in the review as dead code; not re-checked this round |

### Data-Flow Trace (Level 4)

The review table renders `review_rows` from `retention_counts` written by `_record_count` (a real `count_documents` on the raw handle, `retention_job.py:69-85`), so counts are real queries, not static values. Confirmed in the reproduction above (counts row `count: 3`).

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| CR-01 sequence, manual path, failed tenant, adoption design, unreadable createdAt | `repro_cr01_reverify.py` on private mongod 27998 | t-z 5 -> 5, confirm refused, manual counts only | PASS |
| Retention and health backend modules | `pytest test_retention_unreached test_retention_gate test_retention_job test_platform_retention_review test_retention_endpoints_phase82 test_platform_health_sync test_platform_health_status` (MONGO_TEST_URL, MONGODB_URL, MONGO_URI on 27998) | 285 passed in 48 s, 0 skipped | PASS |
| Watchdog modules and platform health activity/on-call | `pytest test_watchdog_checks test_watchdog_restart test_watchdog_warnings test_watchdog_oncall test_watchdog_artifacts test_watchdog_contract test_platform_health_oncall test_platform_health_activity` | 225 passed in 49 s, 0 skipped | PASS |
| Remaining watchdog/health and drift modules | `pytest test_watchdog_restart_order test_watchdog_sync test_platform_health_deadman test_platform_health_migration test_route_auth_baseline test_autonomous_ops_copy` | 92 passed in 19 s, 0 skipped | PASS |
| Retention and health UI | `npx vitest run AutonomousOpsRetentionReview AutonomousOpsRetentionConfirmDialog RetentionPolicyDashboard AutonomousOpsPlatformHealth` | 4 files, 106 tests passed | PASS |

Not run, and why, so nothing here reads as stronger than it is:

- **The full backend suite was not run, and did not complete after the gap round.** Claude Code stopped it at about 25% because the VM ran critically low on memory (82-VALIDATION.md, Gap Round Results). The last complete full run is the 2026-10-30 one (4,983 passed, 5 failed, 47 skipped), which predates plans 82-15..82-17. I make no claim that the full suite passed after the gap round. The 645-pass figure in 82-VALIDATION.md is a targeted run of the Phase 82 modules plus drift tests, and it records one known failure, `test_catalogue_route_parity::test_ledger_ratchets`, which names no Phase 82 module. I did not run `test_catalogue_route_parity`, so I did not re-confirm that one.
- The full frontend suite (818 passed per 82-VALIDATION.md) and `npm run build` were not rerun by me; I ran only the four named UI files above.

### Probe Execution

No `probe-*.sh` declared by the plans. SKIPPED.

### Requirements Coverage

All eight HEAL ids appear in the plans' `requirements` fields and in REQUIREMENTS.md lines 56-63; no id maps to Phase 82 without a plan claiming it (no orphans).

| Requirement | Status | Evidence |
|-------------|--------|----------|
| HEAL-01 watchdog outside backend, minute checks, allowlist restart, mongo first | SATISFIED in code | restart/checks tests pass; live behavior is human item 2 |
| HEAL-02 budget, backoff, page once | SATISFIED in code | `WAITS=(60,120,240)`, `BUDGET=3`, sticky give-up; tests pass |
| HEAL-03 30/14/7/1 cert, 80/90/95 disk, never renews/deletes | SATISFIED | thresholds and audit rule ids now agree (WR-02 fixed) |
| HEAL-04 growth forecast | SATISFIED in code | `FORECAST_LADDER`, 7-day history |
| HEAL-05 webhook/PagerDuty, dedup, test alert, banner, dead-man | SATISFIED in code; live channel unverified | human item 3 |
| HEAL-06 scheduled, bounded, never audit, first run dry-run confirmed | SATISFIED | CR-01 closed and reproduced; WR-01 closed; WR-06 is an advisory availability item |
| HEAL-07 events in platform Activity | SATISFIED | leak guard and the retention_run row; `_record_run_activity` |
| HEAL-08 repo ships units, drop-ins, checklist | SATISFIED | install is the operator's step |

**REQUIREMENTS.md state, for the orchestrator (I did not edit it):** the checkboxes at lines 56-63 are all `[ ]`, and the traceability table at lines 201-208 reads "Gaps Found" for HEAL-01..08 (not "Pending"). On this evidence the code-level conditions for all eight are met; whether to tick them now or after the operator checks below is the orchestrator's decision. HEAL-01, HEAL-02, HEAL-05 and HEAL-08 each have an operator-only part that no test can prove.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| backend/retention_job.py | 81-84 | `countedAt` rewritten when nothing changed | WARNING (WR-06, advisory) | confirmation can be stalled, never forced |
| backend/retention_job.py | 247-249 | "run without finishedAt" branch can never match (IN-08) | INFO | run-in-progress rests on the lock only |
| backend/retention_gate.py | 129-130 | parameter `tenant_created_at` shadows the module function (IN-06) | INFO | latent |
| backend/seed_demo_data.py | 19-30 | rewrites `createdAt` for existing tenants (IN-07) | INFO | latent, manual script, adoption keys on `createdAt` |

No unreferenced `TBD`, `FIXME` or `XXX` in the phase's modified files I grepped. A working-tree edit to `backend/retention_endpoints.py` (four added `_POLICY_DEFAULTS` entries for agent_metrics, asset_metrics, persistence_results, logs) is uncommitted and not part of any plan; the tests above ran with it in place and passed. The orchestrator should decide whether it belongs in the phase commit.

### Human Verification Required

1. **Install the watchdog by hand per `deploy/omni-watchdog/INSTALL.md`**, then `pkcheck` as the `omni-watchdog` user for `nginx.service` restart. Expected: timer active, polkit allows exactly the listed units and verbs, the mongod GLIBC_TUNABLES drop-in still applies, ownership and modes match T-82-06/20/21/22. Why human: operator step, nothing is installed.
2. **Stop mongod, then the backend on the installed server.** Expected: noticed in about 2 minutes, mongod first, backend second, one page after 3 failed restarts. Why human: real units and polkit.
3. **Real on-call channel and external heartbeat.** Expected: one alert arrives and resolves, banner clears, silent watchdog alerts out of band. Why human: needs a real key and outbound HTTPS.
4. **First retention count after deploy.** Review counts, then Confirm deletion; only on a build that includes 82-15..82-17. Why human: live, irreversible data.
5. **Browser pass** of the health section and retention card, light and dark, 640/1024/1280 px, against 82-UI-SPEC sections 1-7. Why human: UI not published.

### Gaps Summary

None remain at the code level. The status is `human_needed` solely because the phase ships operator-installed pieces and an unpublished UI whose behavior only a real server and browser can show; all five items above are the operator checks listed under Manual-Only Verifications in 82-VALIDATION.md. Open but non-blocking: WR-06 (recommended fix before deploy), WR-04 (un-gated delete paths in `retention_service.py`, no non-test caller found by the first report, not re-checked), IN-01..IN-08. 82-SECURITY.md reports `threats_open: 0` (55 of 55 closed); I agree with its account of CR-01, WR-01, WR-02 and WR-03 from my own code reading and reproduction, and I did not re-audit the other threats.

---

_Verified: 2026-10-31_
_Verifier: Claude (gsd-verifier)_
