---
phase: 82-platform-self-healing-scheduled-retention
verified: 2026-10-31T12:00:00Z
status: gaps_found
score: 4/5 must-haves verified
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
  - backend/autonomous_ops/health_messages.py
  - backend/autonomous_ops/selfheal.py
  - backend/retention_endpoints.py
  - backend/retention_gate.py
  - backend/retention_job.py
  - components/AutonomousOpsRetentionReview.tsx
  - deploy/omni-watchdog/omni_watchdog/restart.py
  - deploy/omni-watchdog/omni_watchdog/warnings.py
covered_digest: "v3:sha256:e1ff4ef9372c3edc74ef2d93dbb25876bee1bd17a72998d896c18562cdadb5aa"
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "Data retention runs on a schedule per tenant in bounded batches and never touches audit logs, the audit ledger or decision records; its first run is a dry-run count the operator confirms before anything is deleted (SC4 / HEAL-06)"
    status: failed
    reason: "CR-01. gate_state returns 'adopt' (a deleting state) for any (tenant, type) whose confirmedDays is None and whose firstSeenAt is later than the one global confirmedAt. firstSeenAt is stamped only when run_tenant reaches the tenant (mark_seen), and confirm() seeds no gate rows. A tenant that existed before the confirmation but was not reached by the first count pass (time cap, lost lock, an unguarded error in another tenant, or a tenant added to the registry-type set later) is therefore deleted in the next nightly run, or by POST /api/retention/run, with no count and no operator confirmation. Reproduced by this verifier against a private mongod: two tenants with 3 old + 2 new agent_metrics each, first pass reached only t-a, Super Admin confirmed the one row shown, next nightly run took t-z from 5 documents to 2 and wrote no retention_counts row for t-z."
    artifacts:
      - path: "backend/retention_gate.py"
        issue: "gate_state lines 99-102 treat 'first seen after confirmedAt' as adopt; confirm() (lines 222-237) creates no gate rows for unreached tenants or types"
      - path: "backend/retention_job.py"
        issue: "run_tenant line 131-133 deletes on state adopt; run_all has no per-tenant error guard, so one tenant's Mongo error aborts the pass and leaves later tenants unreached"
      - path: "backend/retention_endpoints.py"
        issue: "POST /run reaches the same hole through run_manual -> run_tenant (line 108)"
    missing:
      - "Seed gate rows (confirmedDays null, firstSeenAt before confirmedAt) for every existing tenant and type at confirm time, or adopt only when the tenant's createdAt is after confirmedAt"
      - "Refuse confirm when the last scheduled run stopped early or any tenant lacks gate rows"
      - "Guard each tenant in run_all so one tenant's failure does not leave others unreached"
      - "A test for the unreached-tenant case (test_retention_gate.py and test_retention_job.py assert adopt only as designed)"
  - truth: "Operator confirmation attests to the rows it confirms (HEAL-06 operator-confirms clause; T-82-42 / WR-01)"
    status: failed
    reason: "components/AutonomousOpsRetentionReview.tsx:315 enables Confirm deletion while pages remain unloaded (nextOffset !== null). The server confirms every eligible row across all pages (retention_gate.py:228), so with more than 25 waiting rows one checkbox attests to rows the operator never saw."
    artifacts:
      - path: "components/AutonomousOpsRetentionReview.tsx"
        issue: "Confirm button disabled only on running or countable <= 0"
    missing:
      - "Disable Confirm until nextOffset === null, with a test for the paged case"
  - truth: "The operator is warned 30, 14, 7 and 1 days before a certificate expires, and each Activity row names the rule that fired (SC2 / HEAL-03, audit-facing ruleId)"
    status: partial
    reason: "WR-02, confirmed in code. The watchdog sends rung 1 for both the 14-day and 30-day steps, 2 for 7 days, 3 for 1 day. health_messages._rule_id indexes _CERT_RULES (30d, 14d, 7d, 1d) by rung-1, so a 14-day warning is labelled cert-expiry-30d, 7-day is cert-expiry-14d, 1-day is cert-expiry-7d, and cert-expiry-1d is never emitted. The warnings themselves fire at the correct thresholds; only the stored reason.ruleId is wrong."
    artifacts:
      - path: "backend/autonomous_ops/health_messages.py"
        issue: "_rule_id lines 134-137 maps rung to the wrong cert rule; rung does not distinguish 30d from 14d"
    missing:
      - "Derive the cert rule id from the key suffix or daysLeft, not from rung; test each of the four rungs"
  - truth: "A malformed event cannot wedge the watchdog sync (T-82-04 / WR-03, medium)"
    status: partial
    reason: "ingest_events catches only LedgerUnavailable. An event with forecastDays 1e999 passes validation and raises OverflowError in health_messages._num, post_sync answers 503 and the watchdog resends the same event every minute. Needs a token holder or a corrupted spool. Below the high-severity threshold; not a phase blocker on its own."
    artifacts:
      - path: "backend/autonomous_ops/selfheal.py"
        issue: "no per-event failure isolation; non-finite numbers not rejected"
    missing:
      - "Catch per-event failures and reject non-finite numbers"
human_verification:
  - test: "Install the watchdog on the server by hand following deploy/omni-watchdog/INSTALL.md (never run-on-ubuntu.sh), then run pkcheck as the omni-watchdog user for nginx.service restart"
    expected: "Timer active; polkit allows exactly the listed units and verbs; existing mongod GLIBC_TUNABLES drop-in still applies; deployed ownership and modes match T-82-06/20/21/22"
    why_human: "Operator step; nothing is installed on this host. HEAL-08 asks the repo to ship the files, which it does; the install is deliberately not done by the app"
  - test: "Stop mongod, then the backend, on the installed server"
    expected: "Noticed within about 2 minutes, mongod restarted first, backend second; after 3 failed restarts one page only; panel and Activity show each step"
    why_human: "Needs real units, real restarts and polkit; unit tests use fakes"
  - test: "Fill /etc/omni-watchdog/oncall.env, press Send test alert, set the external heartbeat URL"
    expected: "One alert arrives and resolves; the no-working-channel banner clears; stopping the watchdog raises the in-app alarm and the external heartbeat service alerts"
    why_human: "Needs a real PagerDuty key or webhook and outbound HTTPS. Note the in-app alarm is by design not queued for on-call (a silent watchdog could not send it); the out-of-band alert depends on the external heartbeat URL being configured"
  - test: "Open Autonomous Ops platform health and the retention review in a published UI, light and dark, at 640, 1024 and 1280 px"
    expected: "Layout matches 82-UI-SPEC sections 1-7"
    why_human: "UI not published; layout and dark theme are visual"
---

# Phase 82: Platform Self-Healing and Scheduled Retention Verification Report

**Phase Goal:** The platform watches its own health from outside the backend, restarts what fails within a budget, warns well before certificates expire or disks fill, pages the on-call person, and runs data retention on a schedule without ever touching audit evidence.
**Verified:** 2026-10-31
**Status:** gaps_found
**Re-verification:** No, initial verification

## Goal Achievement

The self-healing half of the goal is real code and works under test. The retention half does not meet its own stated guarantee: the "first run is a dry-run count the operator confirms" rule has a reproducible hole that deletes data with no count and no confirmation. 82-SECURITY.md carries three open high-severity threats, and I independently confirmed the root cause behind them.

### Observable Truths (ROADMAP success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Watchdog notices a stopped MongoDB, backend or (where expected) Ollama within about a minute, restarts from a fixed allowlist, MongoDB before backend; after the budget it backs off, stops restarting and pages once | VERIFIED | `deploy/omni-watchdog/omni_watchdog/restart.py`: units only from `UNITS`, Ollama only when `ollama_expected`, `WAITS=(60,120,240)`, `BUDGET=3`, `WINDOW=1800`, sticky `gaveUp` until 1 h healthy, backend `blocked` while mongod down, stop pauses restarts with counters untouched. `test_watchdog_checks/restart/restart_order/contract` all pass (rerun by me). Real restarts unverified until install (human item 2) |
| 2 | Warned at 30/14/7/1 days (cert), 80/90/95 percent (disk), and days ahead by growth forecast; never renews or deletes | VERIFIED with defect (see gap 3) | `warnings.py`: `CERT_LADDER`, `DISK_LADDER` with 2-point hysteresis, `FORECAST_LADDER` over 7 days of hourly samples; read-only (only `openssl x509 -noout -enddate`, `statvfs`); structural test pins no delete/renew. Thresholds fire correctly; the stored `ruleId` is off by one rung for 14d, 7d, 1d (WR-02) |
| 3 | Test alert to webhook/PagerDuty arrives once; banner when no working channel; alert when watchdog stops reporting | VERIFIED in code, live delivery unverified | `paging.py` (stable dedup_key, grouped trigger, at most 10 sends per run), `POST /api/.../health/test-alert` gated by `control:platform_autonomous_ops`, banners in UI, `selfheal` dead-man arms after first heartbeat with 180 s grace and compare-and-set `alarmedAt`. `test_watchdog_oncall`, `test_platform_health_oncall/deadman/status` pass. Dead-man is an in-app alarm only by design; out-of-band alert needs the external heartbeat URL (human item 3) |
| 4 | Retention runs on a schedule per tenant in bounded batches, never touches audit logs/ledger/decision records; first run is a dry-run count the operator confirms before anything is deleted | FAILED (BLOCKER) | Scheduling, 500-id batches, pauses, 60-minute cap, 02:00 UTC catch-up under lock, NEVER_DELETED disjointness: verified. "Confirms before anything is deleted": violated by CR-01, reproduced (see below). WR-01 additionally lets one checkbox attest to unseen rows |
| 5 | Watchdog events appear in platform-scope Activity; repo ships unit files, drop-ins and install checklist; the app installs nothing | VERIFIED | `views.list_page` defaults `include_platform_health=False` and ANDs `kind != platform_health` for every tenant id; only the platform route passes True (`autonomous_ops_platform_endpoints.py:98`). `deploy/omni-watchdog/` has INSTALL.md, `systemd/` units and three drop-in dirs, `polkit/49-omni-watchdog.rules`, `etc/*.example`. No backend module calls systemctl or writes /etc (structural test). `test_platform_health_activity`, `test_watchdog_artifacts` pass |

**Score:** 4/5 truths verified (truth 4 failed; truth 2 carries a non-blocking defect)

### CR-01 reproduction (this verifier, private mongod on 27998, not the live server)

Script: `/tmp/claude-1000/-home-azureuser-enterprise-omni-agent-ai-platform/a3b8aa48-54a2-4741-bb98-bfa3aaa198d5/scratchpad/repro_cr01.py`

```
review rows tenants: ['t-a']
t-z before: 5
t-z after next nightly: 2 counts row for t-z: None
manual run for tenant first seen after confirm: {'state': 'adopt', 'days': 30, 'deleted': 3, ...} remaining 0
```

Sequence: both tenants hold 3 records older than 30 days. A first pass that reached only t-a, the operator confirmed the single row shown, the next nightly run deleted t-z's 3 old records with no count. The 82-VALIDATION.md and 82-SECURITY.md accounts of the gap are accurate. The 418 Phase 82 backend tests I reran (watchdog, retention, platform-health) all pass, and none covers this case: tests assert `adopt` as designed.

Note on the manual-run line: a tenant created after the confirmation with old data is adopted by design (A-82-A12), so that line shows the design, not an independent defect; the defect is the unreached pre-existing tenant.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `deploy/omni-watchdog/omni_watchdog/*.py`, `omni-watchdog.py` | stdlib watchdog | VERIFIED | 2001 lines, substantive, tested through fakes |
| `deploy/omni-watchdog/systemd`, `polkit`, `etc`, `INSTALL.md` | units, drop-ins, rule, checklist | VERIFIED (shipped, not installed) | HEAL-08 asks only that the repo ships them |
| `backend/watchdog_ingest_endpoints.py` | token sync/results | VERIFIED | loopback + proxy-header refusal, constant-time bearer compare, 256 KB cap; registered in `router_registry.py:343` |
| `backend/autonomous_ops/selfheal.py`, `health_messages.py`, `oncall.py` | state, dead-man, messages | VERIFIED with WR-02/WR-03 defects | dead-man loop started in `app_startup.py:511` |
| `backend/retention_gate.py`, `retention_job.py` | registry, gate, nightly job | STUB-level correctness gap | wired (`app_startup.py:517-520`), but the gate has the CR-01 hole |
| `backend/autonomous_ops_retention_endpoints.py`, `retention_endpoints.py` | review, confirm, manual run | WIRED, same gate hole | `router_registry.py:342` |
| `components/AutonomousOpsRetentionReview.tsx` | review UI | WIRED, WR-01 | Confirm enabled with unloaded pages |

### Key Link Verification

| From | To | Status | Details |
|------|----|--------|---------|
| retention_loop | run_once -> run_all -> run_tenant -> gate_state | WIRED | started at startup, single runner by lock |
| confirm() | next run's gate_state | PARTIAL | confirm covers only rows with gate rows; unreached tenants fall to `adopt` |
| watchdog -> /api/internal/watchdog/sync | ledger platform_health rows | WIRED | token-authenticated, idempotent ids |
| ledger -> Activity | platform scope only | WIRED | server filter plus client second guard |
| `retention_service.py` legacy delete paths | any caller | NOT_WIRED (good) | no non-test callers (WR-04 is dead code, not a live route) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase 82 backend modules | `pytest backend/tests/test_watchdog_*.py test_retention_job.py test_retention_gate.py test_retention_endpoints_phase82.py test_platform_retention_review.py test_platform_health_*.py` with MONGO_TEST_URL on a private mongod | 418 passed in 86 s | PASS |
| Interrupted first pass is not deleted | `repro_cr01.py` | t-z 5 -> 2, no count | FAIL |
| Full backend (5 failures) and frontend (792 passed) | not rerun, per instruction | 82-VALIDATION.md attributes the 5 failures to uncommitted user edits and calendar dependence, outside this phase | accepted as reported |

### Probe Execution

No `probe-*.sh` declared by the plans. SKIPPED.

### Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| HEAL-01 watchdog outside backend, minute checks, allowlist restart, mongo first | SATISFIED in code | restart.py, checks.py, unit + timer; live behavior is human item 2 |
| HEAL-02 budget, backoff, page once | SATISFIED in code | restart.py constants and sticky `gaveUp`; tests pass |
| HEAL-03 30/14/7/1 cert, 80/90/95 disk, never renews/deletes | SATISFIED with defect | thresholds right; WR-02 mislabels audit ruleId |
| HEAL-04 growth forecast | SATISFIED in code | `forecast()` 7-day least-squares |
| HEAL-05 webhook/PagerDuty, dedup, test alert, banner, dead-man | SATISFIED in code; live channel unverified | human item 3 |
| HEAL-06 scheduled, bounded, never audit, first run dry-run confirmed | **BLOCKED** | CR-01 deletes unconfirmed data; WR-01 unseen-row attestation |
| HEAL-07 events in platform Activity | SATISFIED | leak guard verified |
| HEAL-08 repo ships units, drop-ins, checklist | SATISFIED | install is the operator's step |

No orphaned requirements: REQUIREMENTS.md maps exactly HEAL-01..08 to Phase 82 and all eight are claimed by plans.

REQUIREMENTS.md currently ticks HEAL-06 `[x]` and "Complete" in the traceability table (lines 61, 206). Those ticks were set by executors on plan completion; on this evidence HEAL-06 should be reverted to Pending until CR-01 is fixed. I did not edit REQUIREMENTS.md (instructions: write 82-VERIFICATION.md only).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| backend/retention_gate.py | 99-102 | adopt keyed on first-seen time, not tenant creation time | BLOCKER | CR-01 |
| backend/retention_job.py | 157-177 | run_all has no per-tenant error guard | BLOCKER (contributes to CR-01) | leaves tenants unreached |
| components/AutonomousOpsRetentionReview.tsx | 315 | Confirm enabled with unloaded pages | BLOCKER (T-82-42) | unseen-row attestation |
| backend/autonomous_ops/health_messages.py | 134-137 | rung used as cert rule index | WARNING | wrong audit ruleId |
| backend/autonomous_ops/selfheal.py | ingest_events | catches only LedgerUnavailable | WARNING | repeated 503 on a bad event |
| components WR-05 | n/a | Run Cleanup Now shows "Cleanup completed" for 409/403/400 | WARNING | misleading result (from 82-REVIEW.md, not re-checked line by line) |

No unreferenced TBD/FIXME/XXX markers were sought beyond the files above; none appeared in the files read.

### Separation of unverifiable-before-deploy from code defects

Operator and deploy-only (human items above): watchdog install and deployed modes, real restarts, real on-call channel and external heartbeat, browser layout. Code defects that exist today: CR-01, WR-01, WR-02, WR-03. None of the four is a human-verification item.

### Gaps Summary

Close CR-01 and WR-01 together before any deploy, and do not let a Super Admin confirm a retention review on the live server until then. CR-01 is the only data-loss path: the tests that pass encode the flawed `adopt` rule as intended. Fixing it also closes T-82-33 and T-82-36 in 82-SECURITY.md; WR-01 closes T-82-42. WR-02 and WR-03 are small and can ride the same plan. Phase 82 is not ready to advance: `threats_open: 3` high in 82-SECURITY.md, `nyquist_compliant: false` in 82-VALIDATION.md, and HEAL-06 fails its own wording. Plan the gap round with `/gsd-plan-phase 82 --gaps`.

Repro artifacts and the private mongod live in the scratchpad; the mongod was killed afterwards. No source, /etc or live service was touched.

---

_Verified: 2026-10-31_
_Verifier: Claude (gsd-verifier)_
