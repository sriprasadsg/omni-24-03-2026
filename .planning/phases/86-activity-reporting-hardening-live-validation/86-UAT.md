---
status: testing
phase: 86-activity-reporting-hardening-live-validation
source: [86-VERIFICATION.md]
started: 2026-11-14T11:48:57Z
updated: 2026-11-14T11:48:57Z
---

## Current Test

number: 1
name: Walk the five go-live checks per docs/autonomous-ops-go-live.md (firewall round-trip, reboot gate, watchdog stop/start, alert delivery, live stop drill) and record each on the Going live card as a Super Admin
expected: |
  Each check shows as recorded with note, who and when; the lift gate then reports 5 of 5 (days observed and shadow records still apply to every organization except the marked test organization)
awaiting: user response

## Tests

### 1. Walk the five go-live checks per docs/autonomous-ops-go-live.md (firewall round-trip, reboot gate, watchdog stop/start, alert delivery, live stop drill) and record each on the Going live card as a Super Admin
expected: Each check shows as recorded with note, who and when; the lift gate then reports 5 of 5 (days observed and shadow records still apply to every organization except the marked test organization)
result: [pending]
note: "Round 1 (2026-11-14): blocked, because nothing reached the server (0 autonomy_golive_checks) and no omni-watchdog.timer is installed on Omniai-copy. Install the watchdog first."

### 2. Live stop drill on the real server: press the platform stop, then a tenant stop, and watch queued instructions, pending approvals, a running patch rollout, the security sweep and an AI ticket reply
expected: New security decisions halt, queued automatic instructions are held back at the next agent poll, approvals answer 'stopped', rollouts freeze, AI replies pause; clearing the stop resumes work as new attempts
result: [pending]
note: "Round 1 (2026-11-14): blocked, because no platform stop was ever pressed on the server."

### 3. First real daily digest: after 07:00 UTC, check that each ticked tenant with activity got one in-app notice (tenant admins only) and one email per admin, and no second digest on later passes
expected: Exactly one autonomy_digests claim per (tenant, day), state 'sent' or 'quiet'; no on-call page; log line 'autonomous_ops digest: {...}' (the email half may degrade while SMTP is unset on this VM)
result: [pending]
note: "Round 1 (2026-11-14): pass on server evidence. The first digest pass ran 07:01:47 UTC 2026-11-14. ABC had exactly one autonomy_digests claim, state quiet, and no duplicate over about 40 later passes. The notice/email send path was not exercised, because ABC had no activity in the prior 24 h. 86-16 changed no digest code."

### 4. As a tenant admin: open the Statistics card, change period, expand the time-saved table, export CSV and PDF from the Activity header and from Reporting > Autonomous Ops Activity; open both files
expected: Per-rule table matches the Activity list, 'Estimate' chip beside the time-saved figure, simulation shown apart, file holds the nine columns / summary page, one autonomous_ops.export audit entry per download; Export absent or disabled for a user without export:reports
result: [pending]
note: "Round 1 (2026-11-14): blocked. The server had 0 autonomous_ops.export audit entries and 0 nginx requests to any autonomous-ops endpoint that day."

### 5. G-86-5 re-check on the published build: at 1024, 1100, 1280 and 1440 px, sidebar open and collapsed, light and dark, open Going live > Organizations and Statistics > per-rule table; also at 320 px
expected: Each wide table scrolls sideways inside its card; Tab reaches the labelled region and shows a visible focus ring; Action column (Lift shadow mode, Turn shadow mode back on, Use as test organization) and Refused / Would have done (simulation) columns are reachable by scrolling; no horizontal page scroll at 320 px; the Organizations card chip no longer overlaps Days observed at 320-366 px
result: [pending]
note: "Round 1 (2026-11-14): issue G-86-5 (major), diagnosed in .planning/debug/golive-tables-clipped.md. Gap plan 86-16 fixed it in code (2a4e2ea4e, ad556c174). Publish dist-new (index-BeV-nK0J.js) first; the live site still serves index-BwnVKpDW.js, which lacks the fix. Review WR-07: nothing on screen shows that the tables scroll."

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps
