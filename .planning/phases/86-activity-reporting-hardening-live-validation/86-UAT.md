---
status: partial
phase: 86-activity-reporting-hardening-live-validation
source: [86-VERIFICATION.md]
started: 2026-11-14T10:45:00Z
updated: 2026-11-14T10:43:47.252Z
---

## Current Test

[testing complete]

## Tests

### 1. Walk the five go-live checks per docs/autonomous-ops-go-live.md (firewall round-trip, reboot gate, watchdog stop/start, alert delivery, live stop drill) and record each on the Going live card as a Super Admin
expected: Each check shows as recorded with note, who and when; the lift gate then reports 5 of 5 (days observed and shadow records still apply to every organization except the marked test organization)
result: blocked
blocked_by: server
reason: "User typed 'pass', but at 10:37 UTC 2026-11-14 the Omniai-copy server had 0 autonomy_golive_checks records, no go-live audit events and no nginx request to /api/platform/autonomous-ops/golive (logs back to 2026-10-31); omni-watchdog.timer is not installed, so checks 3 (watchdog stop/start) and 4 (alert delivery) cannot run here. User chose to record it as blocked."

### 2. Live stop drill on the real server: press the platform stop, then a tenant stop, and watch queued instructions, pending approvals, a running patch rollout, the security sweep and an AI ticket reply
expected: New security decisions halt, queued automatic instructions are held back at the next agent poll, approvals answer 'stopped', rollouts freeze, AI replies pause; clearing the stop resumes work as new attempts
result: blocked
blocked_by: server
reason: "User typed 'pass', but at ~10:45 UTC 2026-11-14 the Omniai-copy server showed no platform stop ever pressed (no autonomous_ops system_settings stop doc), no stop/clear events in autonomy_actions, only one tenant stop_pressed audit entry (2026-11-10 13:44, tenant_f988871f8e54), and 0 nginx requests to any autonomous-ops endpoint on 2026-11-13 or 2026-11-14. User chose to record it as blocked."

### 3. First real daily digest: after 07:00 UTC on 2026-11-15 check that each ticked tenant with activity got one in-app notice (tenant admins only) and one email per admin, and no second digest on later passes
expected: Exactly one autonomy_digests claim per (tenant, day), state 'sent' or 'quiet'; no on-call page; log line 'autonomous_ops digest: {...}' (the email half may degrade while SMTP is unset on this VM)
result: pass
note: "Verified on the Omniai-copy server: the first digest pass ran 07:01:47 UTC 2026-11-14 (a day earlier than this test assumed, since the backend went live that morning). ABC, the only ticked organization, has exactly one autonomy_digests claim for 2026-11-14, state quiet (0 ran/undone/waiting/simulation); no duplicate claim over ~40 later 5-minute passes; no on-call page. The notice/email send path was NOT exercised because ABC had no activity in the prior 24 h. The 'autonomous_ops digest: {...}' line is absent by design: digest_job.py logs it only when a digest was sent or failed."

### 4. As a tenant admin: open the Statistics card, change period, expand the time-saved table, export CSV and PDF from the Activity header and from Reporting > Autonomous Ops Activity; open both files
expected: Per-rule table matches the Activity list, 'Estimate' chip beside the time-saved figure, simulation shown apart, file holds the nine columns / summary page, one autonomous_ops.export audit entry per download; Export absent or disabled for a user without export:reports
result: blocked
blocked_by: server
reason: "User typed 'pass', but at 10:41 UTC 2026-11-14 the Omniai-copy server had 0 autonomous_ops.export audit entries and 0 nginx requests to any autonomous-ops endpoint that day. User chose to record it as blocked."

### 5. Visual checks at 320 px, light and dark, and at 1024-1280 px with the sidebar open for the Going live organizations table and per-rule table
expected: No clipped Action column (UI review blocker / verification warning W2) and no horizontal page scroll at 320 px
result: issue
reported: "User typed 'pass', but the code and live UI contradict it: GoLiveOrganizations.tsx and StatsRuleTable.tsx have no overflow-x-auto wrapper and switch to the wide layout at 1024 px (WIDE_QUERY), unchanged since 86-15 (c28996228); live UI is still index-BwnVKpDW.js, the build the UI review measured; no nginx request to any autonomous-ops endpoint on 2026-11-14. User chose to record it as an issue: the Going live Action column (Lift shadow mode / Turn shadow mode back on / Use as test organization) is clipped at ~1024-1175 px with the sidebar open, and the per-rule table loses Refused and Would have done (simulation) up to ~1240 px."
severity: major

## Summary

total: 5
passed: 1
issues: 1
pending: 0
skipped: 0
blocked: 3

## Gaps

- gap_id: G-86-5
  truth: "No clipped Action column (UI review blocker / verification warning W2) and no horizontal page scroll at 320 px"
  status: failed
  reason: "User reported: pass (recorded as an issue on code evidence, with the user's agreement): no overflow-x-auto wrapper in GoLiveOrganizations.tsx or StatsRuleTable.tsx and the wide layout switches at 1024 px, so the Going live Action column is clipped at ~1024-1175 px with the sidebar open and the per-rule table loses Refused and Would have done (simulation) up to ~1240 px"
  severity: major
  test: 5
  artifacts: []  # Filled by diagnosis
  missing: []    # Filled by diagnosis
