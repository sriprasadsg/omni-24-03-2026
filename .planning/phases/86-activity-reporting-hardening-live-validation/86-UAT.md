---
status: testing
phase: 86-activity-reporting-hardening-live-validation
source: [86-VERIFICATION.md]
started: 2026-11-14T10:45:00Z
updated: 2026-11-14T10:45:00Z
---

## Current Test

number: 1
name: Walk the five go-live checks per docs/autonomous-ops-go-live.md and record each on the Going live card as a Super Admin
expected: |
  Each check shows as recorded with note, who and when; the lift gate then reports 5 of 5 (days observed and shadow records still apply to every organization except the marked test organization)
awaiting: user response

## Tests

### 1. Walk the five go-live checks per docs/autonomous-ops-go-live.md (firewall round-trip, reboot gate, watchdog stop/start, alert delivery, live stop drill) and record each on the Going live card as a Super Admin
expected: Each check shows as recorded with note, who and when; the lift gate then reports 5 of 5 (days observed and shadow records still apply to every organization except the marked test organization)
result: [pending]

### 2. Live stop drill on the real server: press the platform stop, then a tenant stop, and watch queued instructions, pending approvals, a running patch rollout, the security sweep and an AI ticket reply
expected: New security decisions halt, queued automatic instructions are held back at the next agent poll, approvals answer 'stopped', rollouts freeze, AI replies pause; clearing the stop resumes work as new attempts
result: [pending]

### 3. First real daily digest: after 07:00 UTC on 2026-11-15 check that each ticked tenant with activity got one in-app notice (tenant admins only) and one email per admin, and no second digest on later passes
expected: Exactly one autonomy_digests claim per (tenant, day), state 'sent' or 'quiet'; no on-call page; log line 'autonomous_ops digest: {...}' (the email half may degrade while SMTP is unset on this VM)
result: [pending]

### 4. As a tenant admin: open the Statistics card, change period, expand the time-saved table, export CSV and PDF from the Activity header and from Reporting > Autonomous Ops Activity; open both files
expected: Per-rule table matches the Activity list, 'Estimate' chip beside the time-saved figure, simulation shown apart, file holds the nine columns / summary page, one autonomous_ops.export audit entry per download; Export absent or disabled for a user without export:reports
result: [pending]

### 5. Visual checks at 320 px, light and dark, and at 1024-1280 px with the sidebar open for the Going live organizations table and per-rule table
expected: No clipped Action column (UI review blocker / verification warning W2) and no horizontal page scroll at 320 px
result: [pending]

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps
