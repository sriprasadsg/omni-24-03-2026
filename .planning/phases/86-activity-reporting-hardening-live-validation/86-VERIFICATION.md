---
phase: 86-activity-reporting-hardening-live-validation
verified: 2026-11-14T10:40:00Z
status: human_needed
score: 3/5 must-haves verified
covered_files:
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-01-PLAN.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-01-SUMMARY.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-02-PLAN.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-02-SUMMARY.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-03-PLAN.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-03-SUMMARY.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-04-PLAN.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-04-SUMMARY.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-05-PLAN.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-05-SUMMARY.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-06-PLAN.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-06-SUMMARY.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-07-PLAN.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-07-SUMMARY.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-08-PLAN.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-08-SUMMARY.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-09-PLAN.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-09-SUMMARY.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-10-PLAN.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-10-SUMMARY.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-11-PLAN.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-11-SUMMARY.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-12-PLAN.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-12-SUMMARY.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-13-PLAN.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-13-SUMMARY.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-14-PLAN.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-14-SUMMARY.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-15-PLAN.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-15-SUMMARY.md
  - backend/autonomous_ops/reporting/digest.py
  - backend/autonomous_ops/reporting/digest_job.py
  - backend/autonomous_ops/reporting/export.py
  - backend/autonomous_ops/reporting/golive.py
  - backend/autonomous_ops/reporting/stats.py
  - backend/autonomous_ops_golive_endpoints.py
  - backend/autonomous_ops_platform_endpoints.py
  - backend/autonomous_ops_reporting_endpoints.py
  - backend/dlp_service.py
  - backend/migrations/035_activity_reporting.py
  - components/autonomousOpsGoLive/GoLiveCard.tsx
  - components/autonomousOpsStats/StatsCard.tsx
covered_digest: "v3:sha256:d244b42bc2e103c6540a296ca167f355d941379e4e719b823f2548f713a00f4b"
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Walk the five go-live checks per docs/autonomous-ops-go-live.md (firewall round-trip, reboot gate, watchdog stop/start, alert delivery, live stop drill) and record each on the Going live card as a Super Admin"
    expected: "Each check shows as recorded with note, who and when; the lift gate then reports 5 of 5 (days observed and shadow records still apply to every organization except the marked test organization)"
    why_human: "Live-only by definition (roadmap SC5): needs AUTONOMOUS_REMEDIATION_DRY_RUN off, a real agent, a real firewall, SMTP/on-call delivery. The user's call. Not done: this verification never touched live data."
  - test: "Live stop drill on the real server: press the platform stop, then a tenant stop, and watch queued instructions, pending approvals, a running patch rollout, the security sweep and an AI ticket reply"
    expected: "New security decisions halt, queued automatic instructions are held back at the next agent poll, approvals answer 'stopped', rollouts freeze, AI replies pause; clearing the stop resumes work as new attempts"
    why_human: "Roadmap SC4 says 'live'. The automated drill (test_autonomous_ops_stop_drill.py, 17 tests, passed) proves the code paths on a private mongod; it does not prove the live process, agent poll and watchdog."
  - test: "First real daily digest: after 07:00 UTC on 2026-11-15 check that each ticked tenant with activity got one in-app notice (tenant admins only) and one email per admin, and no second digest on later passes"
    expected: "Exactly one autonomy_digests claim per (tenant, day), state 'sent' or 'quiet'; no on-call page; log line 'autonomous_ops digest: {...}'"
    why_human: "Loop is live (started 05:18:14Z) but has never reached 07:00 UTC. Mail delivery needs FRONTEND_URL and an SMTP configuration on this VM (memory: SMTP keys unset), so the email half may legitimately degrade."
  - test: "As a tenant admin: open Statistics card, change period, expand time-saved table, export CSV and PDF from the Activity header and from Reporting > Autonomous Ops Activity; open both files"
    expected: "Per-rule table matches the Activity list, 'Estimate' chip beside the time-saved figure, simulation shown apart, file holds the nine columns / summary page, one autonomous_ops.export audit entry per download; Export absent or disabled for a user without export:reports"
    why_human: "Rendering, download behaviour and the audit entry through the published UI (index-BwnVKpDW.js) cannot be seen from code."
  - test: "Visual checks at 320 px, light and dark, and at 1024-1280 px with the sidebar open for the Going live organizations table and per-rule table"
    expected: "No clipped Action column (see warning W2) and no horizontal page scroll at 320 px"
    why_human: "Layout; UI review was code-only plus a static probe."
---

# Phase 86: Activity Reporting, Hardening & Live Validation Verification Report

**Phase Goal:** Operators get the daily digest, per-rule statistics, export and an honest time-saved estimate, and the whole of Autonomous Ops is proven safe end to end (stop drills, two-tenant isolation and a live-only checklist) before any tenant is lifted out of shadow mode.
**Verified:** 2026-11-14T10:40:00Z
**Status:** human_needed
**Re-verification:** No, initial verification

## Goal Achievement

All code, wiring and automated proof exist and pass. Two roadmap truths (SC4, SC5) are explicitly about live validation and cannot be confirmed from the codebase, and SC1's first real delivery has not happened yet. Several review findings stay open (below); none falsifies a success criterion, but one is rated critical and the user should decide on it before relying on it.

### Observable Truths

| #  | Truth (ROADMAP success criterion) | Status | Evidence |
| -- | --------------------------------- | ------ | -------- |
| 1  | Each tenant receives one daily digest of what ran, what was undone, what is waiting | VERIFIED (code and tests); first live delivery pending, see human item 3 | `reporting/digest.py` (unique `(tenantId, day)` claim `digest_once_per_day`, claims before sending, ran/undone/waiting/simulation groups, tenant-admin-audience notice, admin emails with 30 s timeout, raw handle + explicit tenantId); `digest_job.py` (due from 07:00 UTC, 300 s wake, distributed lock, platform org skipped, stop does not suppress); started in `app_startup.py:544-546`; migration 035 creates the claim index. `test_autonomous_ops_digest.py` 38 and `test_autonomous_ops_digest_job.py` 11 passed. Live log confirms loop start at 05:18:14Z (orchestrator fact, not re-read). Caveat W3: window keys on `finishedAt`, which `executed -> verified` rewrites. |
| 2  | Operator sees per-rule statistics (fired, approved, denied, undone) and can export the activity log as CSV or PDF | VERIFIED | `reporting/stats.py` aggregates `autonomy_actions` per tenant with the D-07 column map; `GET /api/autonomous-ops/statistics` (window 7/30/90, 409 for platform org, tenant via `_tenant_for`). `reporting/export.py` + `export_pdf.py` build CSV (formula-sanitised cells, nine fixed columns, 5,000-row cap with Note row) and PDF; `GET /api/autonomous-ops/export` needs `export:reports` and `view:autonomous_ops`, DLP-scans, audits `autonomous_ops.export`, answers 204 on no rows. Mounted via `catalogue_mounts_autonomous_ops.py:34` and `router_registry.py:357`; registry entry for Reporting screen. UI: `StatsCard`, `StatsRuleTable`, `ExportDialog` wired in `AutonomousOpsActivity.tsx:158,186`; `ReportExportCard` in `ReportingDashboard.tsx:562`. Tests: stats 27, export 39, export_registry 7 passed; vitest stats/export 5 files 140 passed. |
| 3  | Screen shows an estimate of operator time saved, labelled as an estimate | VERIFIED | `stats.time_saved` returns `estimate: True` and a fixed `MINUTES_PER_KIND` table over executed/verified rows only (simulation and undone add 0). `TimeSavedBlock.tsx` renders an "Estimate" chip, the method sentence ("an estimate, not a measurement"), a shadow-mode sentence and a read-only per-kind table; card headline reads "... saved (estimate)". Copy gate tests (`test_autonomous_ops_copy.py` 33, `autonomousOpsCopy.test.ts`) passed. |
| 4  | A live stop drill across every actor shows platform and tenant stop halt new decisions, hold back queued instructions, freeze approvals and rollouts, pause AI ticket replies | UNCERTAIN: automated drill VERIFIED, live drill not performed | `test_autonomous_ops_stop_drill.py` (17 tests, passed) drives sweep, delivery, approvals, rollout controller, service desk, watchdog database source, retention (documented exception) under a platform stop and a tenant stop, with clean resume and an unreadable-stop-is-stopped case. The roadmap word is "live"; that is human item 2. |
| 5  | Two-tenant contract per automatic loop (security response, patch rollouts, service desk, retention) and the live-only checklist walked and recorded before any tenant leaves shadow mode | UNCERTAIN: contract tests and recording/gate VERIFIED, checklist not yet walked | `test_autonomous_ops_two_tenant.py` (7 tests, passed): one real entry point per loop over two same-shaped tenants, plus statistics, export and digest. `reporting/golive.py` records five checks append-only and `lift_decision` blocks a lift until 5 checks and 7 observed days (fail closed on unreadable); `put_shadow` (`autonomous_ops_platform_endpoints.py:221-265`) is the only caller of `settings.set_shadow` in production code, gate runs before the write, re-check after a test-organization lift (T-86-14-03). Walking the checklist is human item 1; the lift gate means no organization can leave shadow mode until it is done (the D-23 marked test organization is the only exemption). |

**Score:** 3/5 truths verified, 2 needing live human confirmation (0 behavior-unverified; behavior-dependent truths have named passing tests).

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `backend/autonomous_ops/reporting/{stats,digest,digest_job,export,export_pdf,golive,golive_test_org,rule_names}.py` | Reporting engine | VERIFIED | Substantive (1,562 lines across the package and routes), no TBD/FIXME/XXX markers in any phase file |
| `backend/autonomous_ops_reporting_endpoints.py`, `autonomous_ops_golive_endpoints.py` | Routes | VERIFIED | Mounted in `router_registry.py:353,357`; catalogue guard for reporting at `catalogue_mounts_autonomous_ops.py:34` |
| `backend/migrations/035_activity_reporting.py` | Indexes only | VERIFIED | Calls `digest.ensure_indexes` and `golive.ensure_indexes`; 5 migration tests passed; applied live 05:16:13Z (orchestrator fact) |
| `components/autonomousOpsStats/*`, `components/autonomousOpsGoLive/*`, services | UI | VERIFIED (wired) | Mounted from `AutonomousOpsActivity.tsx` (Going live only in platform scope with `control:platform_autonomous_ops`) and `ReportingDashboard.tsx` |
| `docs/autonomous-ops-go-live.md` | Live-only checklist | VERIFIED (exists) | Triggers confirmed by the user per 86-10 |
| Stop drill, two-tenant, golive, test-org, race tests | Proof | VERIFIED | 236 backend tests passed in this run (list below) |

### Key Link Verification

| From | To | Via | Status |
| ---- | -- | --- | ------ |
| `app_startup.py` | `digest_job.digest_loop` | `asyncio.create_task(_safe_bg_task(...))` line 544-546 | WIRED |
| `digest_job.run_once` | `digest.send_for_tenant` | per ticked tenant, claim first | WIRED |
| `export.deliver` | `dlp_service.scan_export`, `audit_ledger.event` | called before the file is returned | WIRED (see CR-01 for scan limits) |
| `AutonomousOpsActivity.tsx` | statistics / export / go-live services | `fetchAutonomousOpsStatistics`, export dialog, `GoLiveCard` | WIRED |
| `put_shadow` | `golive.lift_decision` | 409 with reasons before `set_shadow` | WIRED; only production writer of the flag |
| `export_controls.EXPORT_PATHS` | `/api/autonomous-ops/export` | allowance, bulk-export check, `data.export` audit | PARTIAL: applies to JWT callers only (W1) |

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | Real data | Status |
| -------- | ---- | ------ | --------- | ------ |
| StatsCard / TimeSavedBlock | rules, totals, timeSaved | `statistics_payload` -> `$group` aggregation over `raw(db).autonomy_actions` filtered by tenantId | Yes | FLOWING |
| Export file | rows | `count_documents` + `find` on the same filter as the Activity list | Yes | FLOWING |
| Digest | ran/undone/waiting/simulation | `count_documents` + `find` per group | Yes | FLOWING |
| GoLiveCard | checks, organizations | `golive.overview` (evidence collection + ticked tenants) | Yes | FLOWING |

### Behavioral Spot-Checks (run in this verification, private mongod 127.0.0.1:27998 only)

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Backend Phase 86 suites | `pytest tests/test_autonomous_ops_{stop_drill,two_tenant,stats,digest,digest_job,export,export_registry,golive,golive_test_org,golive_test_org_race,copy}.py tests/test_migration_035_activity_reporting.py` | 236 passed in 44 s | PASS |
| UI Phase 86 suites | `npx vitest run` stats, export, goLive, goLiveTestOrg, copy | 5 files, 140 tests passed | PASS |
| Code at the tested HEAD | working tree equals HEAD for all phase files (git status clean for them) | yes | PASS |

### Probe Execution

Step 7c: SKIPPED. No probe-based verification is declared by any Phase 86 plan.

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
| ----------- | -------------- | ----------- | ------ | -------- |
| ACTV-04 | 86-05, 86-09, 86-13 | Daily digest per tenant | SATISFIED in code; first live delivery pending | Truth 1 |
| ACTV-05 | 86-01, 86-04, 86-09, 86-13 | Per-rule statistics | SATISFIED | Truth 2 |
| ACTV-06 | 86-06, 86-08, 86-09, 86-11, 86-13 | CSV/PDF export | SATISFIED (W1, CR-01 caveats) | Truth 2 |
| ACTV-07 | 86-01, 86-04, 86-13 | Time-saved estimate labelled as estimate | SATISFIED | Truth 3 |

All four IDs are claimed by PLAN frontmatter and marked Complete in REQUIREMENTS.md (lines 80-83, 256-259). No orphaned requirements: the Phase 86 row of the traceability table lists only ACTV-04..07. Plans also carry GATE-06 (86-02, re-verification), GATE-09 (86-07, 10, 12, 14, 15) and GATE-11 (86-03, 86-09); these belong to Phase 81 in REQUIREMENTS.md and are re-verified here, not claimed as new.

### Anti-Patterns Found

None blocking. No TBD/FIXME/XXX in any file the phase added. The open code-review items below were checked against the code and are real.

### Open Review Findings Verified Against the Code (decision requested)

None of these falsifies a roadmap success criterion, so none is recorded as a goal gap; each is a defect the user should either fix or accept. All 12 findings are still `open` in `86-REVIEW-DISPOSITION.md`.

| ID | Severity | Verified | Why it matters |
| -- | -------- | -------- | -------------- |
| CR-01 | critical (review) | Confirmed in `dlp_service.py:206-214` | `scan_export` truncates the scanned text at 2,000,000 chars, uses `json.dumps` with default `ensure_ascii` (non-ASCII text becomes `\uXXXX`, so non-Latin keyword policies never match) and reads at most 100 policies. A block policy can therefore be silently skipped. The file is the user's D-18 code committed unchanged (db8b8cd4c); the new Autonomous Ops export is capped at 5,000 rows so truncation is unlikely there, but the non-ASCII and policy-cap gaps apply, and the generic `/api/reports/export` is exposed to all three. |
| W1 / WR-01 | warning | Confirmed: `export_controls._caller` reads only the bearer JWT; the route authenticates via `get_current_user_or_api_key` (X-API-Key) | Plan 86-08's must-have "daily allowance, bulk-export incident and data.export audit apply to the dedicated route" holds for signed-in users but not API-key callers. The route's own `autonomous_ops.export` audit and DLP scan still run. |
| W2 / UI-REVIEW blocker | blocker-rated by the UI review, warning here | Confirmed: no `overflow-x-auto` in `GoLiveOrganizations.tsx` or `StatsRuleTable.tsx`; wide layout switches at 1024 px | At roughly 1024-1175 px with the sidebar open the Action column (Lift shadow mode) is clipped by `main`'s `overflow-x-hidden`. Workaround: collapse the sidebar or widen the window. Does not break the server-side gate. |
| W3 / WR-06 | warning | Confirmed: `ledger.transition` sets `finishedAt = now` on every move into a terminal state, including `executed -> verified` | A row executed just before 07:00 and verified after it is counted in the next day's digest rather than its own. Digest counts can be off by one day at the boundary; statistics are unaffected (they use `createdAt`). |
| WR-02 | warning | Not re-run | `PageSizeCapMiddleware` can raise on `limit=%C2%B2` (500, unauthenticated). |
| WR-03, WR-04, WR-05, IN-01..05 | warning/info | Not re-checked | WR-04: any ticked organization can be marked the test organization (documentation says customers are refused). WR-05: a marked organization that is later unticked cannot be cleared in the UI. |
| R1-R4 (86-SECURITY) | low | Taken from 86-SECURITY.md | Races needing three concurrent Super Admin requests; SECURED, threats_open 0. |

Also worth knowing: the T-86-14-03 security fixes (ae0b01058, 6b58bd655, 6cd12cb2d, 324340252) and later docs commits are not yet live or pushed, so the running backend does not yet contain them. A backend restart is the user's step.

### Human Verification Required

See the five items in the frontmatter (go-live checklist walk, live stop drill, first real digest, tenant-admin statistics/export through the published UI, visual checks).

### Gaps Summary

No must-have truth failed. Phase 86 delivered the digest, statistics, export, time-saved estimate, stop drill, two-tenant contract and go-live gate in code, with 236 backend and 140 UI tests passing on the current tree. The phase cannot be called fully achieved until the live-only parts are done (SC4 live drill, SC5 checklist walk) and the first digest is seen. Before treating the phase as closed, the user should decide on CR-01 (export DLP scan fails open), WR-01 (API-key exports skip the allowance) and the UI-review table clipping; fixing them would be a small follow-up, accepting them would be an explicit decision recorded in 86-REVIEW-DISPOSITION.md.

---

_Verified: 2026-11-14T10:40:00Z_
_Verifier: Claude (gsd-verifier)_
