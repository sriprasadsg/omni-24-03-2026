---
phase: 86-activity-reporting-hardening-live-validation
verified: 2026-11-14T11:50:00Z
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
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-16-PLAN.md
  - .planning/phases/86-activity-reporting-hardening-live-validation/86-16-SUMMARY.md
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
  - components/autonomousOpsGoLive/GoLiveOrganizations.tsx
  - components/autonomousOpsStats/StatsCard.tsx
  - components/autonomousOpsStats/StatsRuleTable.tsx
  - src/__tests__/autonomousOpsTableScroll.test.tsx
covered_digest: "v3:sha256:6d03864494f59f6816667e2a2af37522f6b2e01fddd32042a0286403b9a800f3"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 3/5
  gaps_closed:
    - "G-86-5 (UAT test 5): Going live Organizations table and Statistics per-rule table clipped at 1024-1280 px with the sidebar open. Closed in code by 86-16 (scroll regions + structural test); real-width visual confirmation still needs a browser on the published build (human item 5)."
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Walk the five go-live checks per docs/autonomous-ops-go-live.md (firewall round-trip, reboot gate, watchdog stop/start, alert delivery, live stop drill) and record each on the Going live card as a Super Admin"
    expected: "Each check shows as recorded with note, who and when; the lift gate then reports 5 of 5 (days observed and shadow records still apply to every organization except the marked test organization)"
    why_human: "Live-only by definition (roadmap SC5): needs AUTONOMOUS_REMEDIATION_DRY_RUN off, a real agent, a real firewall, SMTP/on-call delivery. UAT tests 1, 2 and 4 were also recorded as blocked because nothing reached the server. This verification never touched live data."
  - test: "Live stop drill on the real server: press the platform stop, then a tenant stop, and watch queued instructions, pending approvals, a running patch rollout, the security sweep and an AI ticket reply"
    expected: "New security decisions halt, queued automatic instructions are held back at the next agent poll, approvals answer 'stopped', rollouts freeze, AI replies pause; clearing the stop resumes work as new attempts"
    why_human: "Roadmap SC4 says 'live'. The automated drill (test_autonomous_ops_stop_drill.py, 17 tests) proves the code paths on a private mongod; it does not prove the live process, agent poll and watchdog."
  - test: "First real daily digest: after 07:00 UTC on the first day after the backend carries the digest loop, check that each ticked tenant with activity got one in-app notice (tenant admins only) and one email per admin, and no second digest on later passes"
    expected: "Exactly one autonomy_digests claim per (tenant, day), state 'sent' or 'quiet'; no on-call page; log line 'autonomous_ops digest: {...}'"
    why_human: "The loop had not yet reached 07:00 UTC when last observed. Mail delivery needs FRONTEND_URL and SMTP on this VM (SMTP keys unset per memory), so the email half may legitimately degrade."
  - test: "As a tenant admin: open the Statistics card, change period, expand the time-saved table, export CSV and PDF from the Activity header and from Reporting > Autonomous Ops Activity; open both files"
    expected: "Per-rule table matches the Activity list, 'Estimate' chip beside the time-saved figure, simulation shown apart, file holds the nine columns / summary page, one autonomous_ops.export audit entry per download; Export absent or disabled for a user without export:reports"
    why_human: "Rendering, download behaviour and the audit entry through the published UI cannot be seen from code. UAT tests 1, 2 and 4 recorded as blocked."
  - test: "G-86-5 re-check on the published build of HEAD (dist-new index-BeV-nK0J.js, not yet published): at 1024, 1100, 1280 and 1440 px, sidebar open and collapsed, light and dark, open Going live > Organizations and Statistics > per-rule table; also at 320 px"
    expected: "Each wide table scrolls sideways inside its card; Tab reaches the labelled region and shows a visible focus ring; Action column (Lift shadow mode, Use as test organization) and Refused / Would have done (simulation) columns are reachable by scrolling; no horizontal page scroll at 320 px; the Organizations card chip no longer overlaps Days observed at 320-366 px"
    why_human: "jsdom has no layout. The structural test proves an overflow-x-auto ancestor exists, not that the content actually overflows into it at real widths. The live site still serves index-BwnVKpDW.js, which lacks the fix."
---

# Phase 86: Activity Reporting, Hardening & Live Validation Verification Report

**Phase Goal:** Operators get the daily digest, per-rule statistics, export and an honest time-saved estimate, and the whole of Autonomous Ops is proven safe end to end (stop drills, two-tenant isolation and a live-only checklist) before any tenant is lifted out of shadow mode.
**Verified:** 2026-11-14T11:50:00Z
**Status:** human_needed
**Re-verification:** Yes, after gap-closure plan 86-16 (the previous report carried no `gaps:` section, so all truths were re-checked, with full depth on the 86-16 items)

## Goal Achievement

The code, wiring and automated proof for all five roadmap success criteria exist and pass at HEAD. SC4 and SC5 are explicitly about live validation, and SC1's first real delivery has not happened. Those cannot be confirmed from the codebase and stay as human items; none is marked passed. Plan 86-16 closes UAT gap G-86-5 in code; the visual effect awaits a browser on a published build. CR-01 and the other review findings remain open and unchanged.

### Observable Truths

| #  | Truth (ROADMAP success criterion) | Status | Evidence |
| -- | --------------------------------- | ------ | -------- |
| 1  | Each tenant receives one daily digest of what ran, what was undone, what is waiting | VERIFIED (code and tests); first live delivery pending (human item 3) | `digest_loop` created at `backend/app_startup.py:545-546`; `reporting/digest.py` and `digest_job.py` unchanged since the prior verification (git status clean). Digest and digest_job suites pass in this run. Caveat W3 (`finishedAt` rewritten by `executed -> verified`) unchanged. |
| 2  | Per-rule statistics and CSV/PDF export of the activity log | VERIFIED | `GET /api/autonomous-ops/export` in `autonomous_ops_reporting_endpoints.py:68` requires `export:reports` and `view:autonomous_ops`; stats, export and export_registry suites pass in this run. `StatsRuleTable` is imported by `StatsCard.tsx`; the per-rule table now also scrolls (Truth 6). |
| 3  | Screen shows an estimate of operator time saved, labelled as an estimate | VERIFIED | Unchanged since prior verification; stats and copy-gate suites (33 copy tests) pass. |
| 4  | Live stop drill across every actor | UNCERTAIN: automated drill VERIFIED, live drill not performed | `test_autonomous_ops_stop_drill.py` passes in this run (part of 262). Roadmap word is "live": human item 2. |
| 5  | Two-tenant contract per automatic loop; live-only checklist walked and recorded before any tenant leaves shadow mode | UNCERTAIN: contract tests and gate VERIFIED, checklist not walked | `test_autonomous_ops_two_tenant.py` passes. `put_shadow` (`autonomous_ops_platform_endpoints.py:244-255`) calls `golive.lift_decision` before `settings.set_shadow` and re-checks after a test-organization lift; those two lines are the only production callers of `set_shadow` in the backend (grep). Walking the checklist is human item 1. |
| 6  | (86-16, G-86-5) Going live Organizations table sits in its own labelled, focusable `overflow-x-auto` region, every Action control reachable | VERIFIED structurally; visual effect at real widths needs a browser (human item 5) | `GoLiveOrganizations.tsx:137`: `<div role="region" aria-label={ORG_CAPTION} tabIndex={0} className="min-w-0 overflow-x-auto">` wraps the table including the Action column. Test "sits in its own labelled, focusable overflow-x-auto region" and "keeps the Action header and every action button inside the scroll region" pass. |
| 7  | (86-16) Statistics per-rule table sits in its own scroll region; Refused and simulation columns reachable; Show all and glossary outside | VERIFIED structurally; visual per human item 5 | `StatsRuleTable.tsx:51`: same wrapper with `aria-label={rulesCaption(days)}`. The `StatsRuleTable` export keeps "Show all" and `Glossary` outside the wrapper (lines 147-165). Tests pass (region contains Refused, simulation headers and All rules footer; buttons not contained). |
| 8  | (86-16) Layout switch and App.tsx unchanged; cards below 1024 px unchanged | VERIFIED | `WIDE_QUERY = '(min-width: 1024px)'` and `useWideLayout` intact in both files (lines 15/24 and 16/19). `git diff 16bbdda58 HEAD -- App.tsx` is empty; the `main` `overflow-x-hidden` is unchanged (`App.tsx:2023`). App.tsx's uncommitted working-tree changes are the user's WIP and do not touch overflow. Card-layout tests (no region, no table) pass. |
| 9  | (86-16) Organizations card `dl` one column below `sm`, two from `sm`, simulation cell spans the row | VERIFIED structurally | `GoLiveOrganizations.tsx:171` `grid grid-cols-1 gap-2 sm:grid-cols-2`; line 180 `col-span-full`. Test asserts these classes and the absence of bare `grid-cols-2`. Overlap itself is rendering: human item 5. |
| 10 | (86-16) Structural vitest regression fails if either table loses its scroll ancestor | VERIFIED | `src/__tests__/autonomousOpsTableScroll.test.tsx` (163 lines, 8 tests) passes (run in this verification). It asserts `table.closest('.overflow-x-auto')` equals the labelled region and sits inside the component's own section. Limit: it cannot prove content overflows into the region. |
| 11 | (86-16) 86-UI-SPEC.md records measured widths and the scroll-region rule; wrong claims removed | VERIFIED | `86-UI-SPEC.md` lines 18, 74, 260, 343, 389 carry 884 px, 946 px, "viewport minus 358px minus the scrollbar (656px at 1024)" and the region rule; no "888" or "inside the 900px budget" claim remains for these two tables (the inherited 900 px budget is explicitly excepted at line 15). |

**Score:** 3/5 roadmap truths verified (SC1, SC2, SC3); SC4 and SC5 need live human confirmation. All 6 plan-level 86-16 truths (6-11) are verified at the code level. 0 behavior-unverified (state-transition truths have named passing tests).

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `components/autonomousOpsGoLive/GoLiveOrganizations.tsx` | Scroll region around table, dl one column below sm | VERIFIED | Exists, substantive, mounted by `GoLiveCard.tsx`; commits 2a4e2ea4e, ad556c174 |
| `components/autonomousOpsStats/StatsRuleTable.tsx` | Scroll region around table | VERIFIED | Mounted by `StatsCard.tsx` |
| `src/__tests__/autonomousOpsTableScroll.test.tsx` | G-86-5 structural regression | VERIFIED | 8 passed |
| `86-UI-SPEC.md` | Corrected widths | VERIFIED | grep of 946/884/358 present |
| Phase 86 backend reporting package, endpoints, migration 035, UI cards | Earlier plans' artifacts | VERIFIED (regression) | Phase files have no uncommitted changes; no changes since prior verification besides 86-16 |
| `docs/autonomous-ops-go-live.md` | Live-only checklist | VERIFIED (exists) | Unchanged |

### Key Link Verification

| From | To | Via | Status |
| ---- | -- | --- | ------ |
| `app_startup.py` | `digest_job.digest_loop` | `asyncio.create_task(_safe_bg_task(...))` | WIRED |
| `put_shadow` | `golive.lift_decision` then `settings.set_shadow` | 409 with reasons before the write | WIRED |
| `GoLiveCard.tsx` / `StatsCard.tsx` | the two table components | imports and render | WIRED |
| `OrganizationTable` / `RuleTable` | scroll region | root `div role="region" ... overflow-x-auto` | WIRED |
| `export_controls.EXPORT_PATHS` | `/api/autonomous-ops/export` | JWT callers only | PARTIAL (W1, unchanged) |

### Data-Flow Trace (Level 4)

Unchanged for earlier plans (stats aggregation, export rows, digest groups, go-live overview all read real collections: FLOWING). 86-16 adds no data path; it only wraps existing renders.

### Behavioral Spot-Checks (private mongod 127.0.0.1:27998 only; live 27017 never touched)

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Phase 86 backend suites (stop drill, two-tenant, stats, digest, digest_job, export, export_registry, golive, golive_test_org, race, copy, structural, migration 035) | `venv/bin/python -m pytest -q ...` with the three 27998 env vars | 262 passed in 55 s | PASS |
| 86-16 structural test | `npx vitest run src/__tests__/autonomousOpsTableScroll.test.tsx` | 8 passed | PASS |
| Gates reported by the caller at HEAD (not re-run here) | vitest `src/__tests__` 131 files / 2188 passed twice; build passed | caller-supplied | accepted as stated |

### Probe Execution

Step 7c: SKIPPED. No probe-based verification is declared by any Phase 86 plan.

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
| ----------- | -------------- | ----------- | ------ | -------- |
| ACTV-04 | 86-05, 86-09, 86-13 | Daily digest per tenant | SATISFIED in code; first live delivery pending | Truth 1 |
| ACTV-05 | 86-01, 86-04, 86-09, 86-13, 86-16 | Per-rule statistics | SATISFIED (per-rule table now scrolls at all widths in code) | Truths 2, 7 |
| ACTV-06 | 86-06, 86-08, 86-09, 86-11, 86-13 | CSV/PDF export | SATISFIED (W1 and CR-01 caveats) | Truth 2 |
| ACTV-07 | 86-01, 86-04, 86-13 | Time-saved estimate labelled | SATISFIED | Truth 3 |

All four IDs are claimed by PLAN frontmatter and marked Complete in `REQUIREMENTS.md` (lines 80-83 and 256-259). No orphaned Phase 86 requirements. 86-16 additionally lists GATE-09 (Phase 81 requirement, re-verified, not newly claimed).

### Anti-Patterns Found

No TBD/FIXME/XXX in the 86-16 files or the new test. No stubs: both table components render real data from props fed by the existing services. Nothing blocking.

### Open Review Findings (unchanged, decision still requested)

All findings remain `open` in `86-REVIEW-DISPOSITION.md` (CR-01, WR-01..07, IN-01..07). None falsifies a roadmap success criterion, so none is recorded as a gap; the user should fix or explicitly accept each.

| ID | Severity | Re-verified | Why it matters |
| -- | -------- | ----------- | -------------- |
| CR-01 | critical (review) | Re-confirmed in `dlp_service.py:206-214` | `scan_export` truncates scanned text at 2,000,000 chars, uses default-ASCII `json.dumps` (non-ASCII keyword policies never match) and reads at most 100 policies, so a block policy can be skipped. The Autonomous Ops export is capped at 5,000 rows, but the generic export is exposed. |
| W1 / WR-01 | warning | Unchanged | API-key callers skip the export allowance / bulk-export incident / `data.export` audit; the route's own `autonomous_ops.export` audit and DLP scan still run. |
| W3 / WR-06 | warning | Unchanged | Digest day boundary can be off by one because `executed -> verified` rewrites `finishedAt`. |
| WR-02..05, WR-07, IN-01..07 | warning/info | Not re-checked | See `86-REVIEW.md`. |
| G-86-5 | was UAT major | Closed in code | See truths 6-11. The old W2 warning (tables clipped, no `overflow-x-auto`) is superseded: both files now carry the region. |

The T-86-14-03 security fixes and the 86-16 UI change are not yet live: the live site serves `index-BwnVKpDW.js`, and `dist-new` (`index-BeV-nK0J.js`) is unpublished. Restart, publish and push are the user's steps.

### Human Verification Required

See the five items in the frontmatter. None was performed or marked passed here.

### Gaps Summary

No must-have truth failed. Plan 86-16 delivers what it promised in code and its structural test passes, and no regression was found in the earlier plans (262 backend tests pass on the private mongod). The phase is not fully achieved until the live-only parts happen (SC4 live drill, SC5 checklist walk, first real digest) and the G-86-5 width check is made on a published build. Before relying on export in production, the user should decide on CR-01 and WR-01.

---

_Verified: 2026-11-14T11:50:00Z_
_Verifier: Claude (gsd-verifier)_
