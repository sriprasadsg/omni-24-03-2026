---
status: diagnosed
phase: 86-activity-reporting-hardening-live-validation
source: [86-VERIFICATION.md]
started: 2026-11-14T10:45:00Z
updated: 2026-11-14T11:20:00Z
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
  root_cause: "Two conditions together: (1) both components pick the wide table by the viewport (WIDE_QUERY '(min-width: 1024px)', GoLiveOrganizations.tsx:15, StatsRuleTable.tsx:16) while the table width depends on the card's content column, which is vw - 358 - scrollbar with the sidebar open (656 px at 1024) and the tables need 884 px (Organizations, column minimums :141-145) and ~946 px (per-rule, 240 + 7x72 + 144, min-w-[72px] includes padding, :55-57), so they only fit from ~1252 / ~1314 px; (2) nothing makes the overflow scrollable: the wrapper is a plain min-w-0 div (GoLiveOrganizations.tsx:231-233, StatsRuleTable.tsx:150-152), .card has no overflow rule, and main's overflow-x-hidden (App.tsx:2023) clips the spill so the columns cannot be reached. Designed in, not a regression: the UI-SPEC 900 px table budget was never compared with the real column and its 888 px per-rule figure is wrong. Every other matchMedia useWideLayout table (RingDetail.tsx:64, PartnersDashboard.tsx:188/:327, PartnerPortal.tsx:240, PartnerTeamPanel.tsx:281) wraps the table in overflow-x-auto. 320 px: no page scroll in light or dark (cards render), but the Organizations card's 'Shadow mode on' chip overlaps the Days observed cell below ~366 px (25 px at 320) and 'Use as test organization' overhangs its list item by 16 px (cosmetic)."
  artifacts:
    - path: "components/autonomousOpsGoLive/GoLiveOrganizations.tsx"
      issue: "Table wrapper (:231-233) has no overflow-x-auto; viewport switch at 1024 (:15, :24-35) while the 884 px table needs ~1252 px with the sidebar open; card chip cell overlaps at <=366 px (:169-176, grid-cols-2)"
    - path: "components/autonomousOpsStats/StatsRuleTable.tsx"
      issue: "Table wrapper (:150-152) has no overflow-x-auto; viewport switch at 1024 (:16, :19-30) while the ~946 px table needs ~1314 px with the sidebar open"
    - path: "App.tsx"
      issue: "main overflow-x-hidden (:2023) clips the spill; amplifier only, not to be changed"
    - path: ".planning/phases/86-activity-reporting-hardening-live-validation/86-UI-SPEC.md"
      issue: "900 px table budget and 888 px per-rule figure (:72, :258, :341, :387) are wrong; real per-rule minimum ~946 px and real column is vw - 358 - scrollbar"
  missing:
    - "Wrap the Organizations and per-rule tables in an overflow-x-auto scroll region (the RingDetail.tsx:64 / PartnersDashboard.tsx:188 pattern), keyboard-reachable (tabIndex 0 + label), so every column is reachable at every width"
    - "Vitest regression: each table has an overflow-x-auto ancestor inside its card section (jsdom has no layout, so assert structure, not pixels)"
    - "Optional: fix the <=366 px Organizations card chip overlap (chip cell col-span-2 or single-column dl below sm) and let 'Use as test organization' wrap"
    - "Correct the UI-SPEC table budget lines to the measured widths"
  debug_session: ".planning/debug/golive-tables-clipped.md"
