---
status: partial
phase: 86-activity-reporting-hardening-live-validation
source: [86-VERIFICATION.md]
started: 2026-11-14T11:48:57Z
updated: 2026-11-16T09:12:00.000Z
---

## Current Test

[testing complete]

## Tests

### 1. Walk the five go-live checks per docs/autonomous-ops-go-live.md (firewall round-trip, reboot gate, watchdog stop/start, alert delivery, live stop drill) and record each on the Going live card as a Super Admin
expected: Each check shows as recorded with note, who and when; the lift gate then reports 5 of 5 (days observed and shadow records still apply to every organization except the marked test organization)
result: blocked
blocked_by: server
reason: "Round 2: user typed 'pass', but at 12:24 UTC 2026-11-14 the Omniai-copy server still had 0 autonomy_golive_checks records, no nginx request to any go-live or autonomous-ops endpoint since 12:00, no omni-watchdog.timer installed (checks 3 and 4 cannot run here), and the live UI still served index-BwnVKpDW.js. User chose to record it as blocked."
note: "Round 1 (2026-11-14): blocked, because nothing reached the server (0 autonomy_golive_checks) and no omni-watchdog.timer is installed on Omniai-copy. Install the watchdog first."

### 2. Live stop drill on the real server: press the platform stop, then a tenant stop, and watch queued instructions, pending approvals, a running patch rollout, the security sweep and an AI ticket reply
expected: New security decisions halt, queued automatic instructions are held back at the next agent poll, approvals answer 'stopped', rollouts freeze, AI replies pause; clearing the stop resumes work as new attempts
result: blocked
blocked_by: server
reason: "Round 2: user typed 'pass' about two minutes after the test was shown, but at 12:26 UTC 2026-11-14 no autonomy_settings document (platform or tenant) had a stop set, the newest audit_logs entry was 11:04 UTC (finops_recalculation, no stop/clear events), and nginx showed no request to any autonomous-ops or stop endpoint that day (only scanner traffic). Recorded as blocked, same as the user's choice for test 1."
note: "Round 1 (2026-11-14): blocked, because no platform stop was ever pressed on the server."

### 3. First real daily digest: after 07:00 UTC, check that each ticked tenant with activity got one in-app notice (tenant admins only) and one email per admin, and no second digest on later passes
expected: Exactly one autonomy_digests claim per (tenant, day), state 'sent' or 'quiet'; no on-call page; log line 'autonomous_ops digest: {...}' (the email half may degrade while SMTP is unset on this VM)
result: pass
evidence: "Round 2: re-checked 12:28 UTC 2026-11-14. Still exactly one autonomy_digests claim (tenant_f988871f8e54, day 2026-11-14, state quiet, claimedAt 07:01:47 UTC, counts all 0) and no duplicate after the 11:50:33 backend restart. Send path (notice + email) still unexercised; next digest 07:00 UTC 2026-11-15."
note: "Round 1 (2026-11-14): pass on server evidence. The first digest pass ran 07:01:47 UTC 2026-11-14. ABC had exactly one autonomy_digests claim, state quiet, and no duplicate over about 40 later passes. The notice/email send path was not exercised, because ABC had no activity in the prior 24 h. 86-16 changed no digest code."

### 4. As a tenant admin: open the Statistics card, change period, expand the time-saved table, export CSV and PDF from the Activity header and from Reporting > Autonomous Ops Activity; open both files
expected: Per-rule table matches the Activity list, 'Estimate' chip beside the time-saved figure, simulation shown apart, file holds the nine columns / summary page, one autonomous_ops.export audit entry per download; Export absent or disabled for a user without export:reports
result: pass
source: automated-headless
evidence: "Round 3, 2026-11-16 09:01-09:08 UTC, on the build deployed that morning (npx 0b0e5492c, backend restarted 08:57:50 UTC, UI index-CCy72xqN.js). At the user's choice Claude ran it in headless Chromium (chrome-headless-shell 1254) against https://127.0.0.1 with two temporary MFA-enrolled ABC accounts (uat86r3-admin, Tenant Admin; uat86r3-analyst, Analyst: view:autonomous_ops without export:reports). Found first: no organization on this server could export. ABC had Autonomous Ops but neither Reporting nor export:reports, and the one organization with Reporting had no Autonomous Ops, so the admin's sign-in carried no export:reports. With the user's go, view:reporting, export:reports and screen:reporting were added to ABC's enabledFeatures for 33 s (09:06:58-09:07:31 UTC) and removed again; the list is identical to before. 25 of 25 checks passed, 0 page errors. Admin: the 7, 30 and 90 day pills each press and the server answers for that period (3 decisions, 3 done, 0 undone in each); the four readouts equal the server's totals; the 'Estimate' chip sits beside Time saved (0 min, shadow mode on); the simulation line is apart from the real counts; 'Show minutes per kind of action' expands; the per-rule table (service_desk:handoff: fired 3, done 3) equals the rows of the Activity list. The Export activity dialog opens on CSV and the Statistics period and names the audit log. CSV and PDF downloaded from the Activity header and from Reporting > Data Export Center > Autonomous Ops Activity: 4 files, each 3 of 3 rows, not truncated. Files opened: both CSVs hold the nine columns and 3 rows; both PDFs have 2 pages, a summary page (organization, generated time, filter line, counts, Time saved (estimate), per-rule table) and a rows page with the nine headers. Audit: exactly 4 autonomous_ops.export entries, one per download (csv and pdf with entry screen, csv and pdf with entry registry), each rows 3, total 3, truncated false. Analyst: the Statistics card shows, Export activity is absent (canExport false), both export routes answer 403, and with Reporting on the card's CSV and PDF buttons are disabled with 'Needs permission to export reports.'. Results, the 4 files, 7 screenshots and the archived account rows are in ~/omni-archives/uat86-r3-t4/ (no credentials); both accounts and their login, export-usage and DLP export rows were removed afterwards (users back to 5); 17 hash-chained audit_logs entries stay."
note: "Round 2 (2026-11-14): blocked. The user typed 'pass', but at 12:35 UTC the server had 0 autonomous_ops.export audit entries and no nginx request to any autonomous-ops, statistics or export endpoint that day. Round 1 (2026-11-14): blocked for the same reason. Open after round 3: on this server a real tenant admin still cannot export, because no organization has both Autonomous Ops and Reporting with export:reports."

### 5. G-86-5 re-check on the published build: at 1024, 1100, 1280 and 1440 px, sidebar open and collapsed, light and dark, open Going live > Organizations and Statistics > per-rule table; also at 320 px
expected: Each wide table scrolls sideways inside its card; Tab reaches the labelled region and shows a visible focus ring; Action column (Lift shadow mode, Turn shadow mode back on, Use as test organization) and Refused / Would have done (simulation) columns are reachable by scrolling; no horizontal page scroll at 320 px; the Organizations card chip no longer overlaps Days observed at 320-366 px
result: pass
source: automated-headless
evidence: "Round 2, 2026-11-14 12:45-13:10 UTC. User typed 'pass' but no browser had loaded index-BeV-nK0J.js (published 12:24:09, matches dist-new), so at the user's choice Claude ran it in headless Chromium (chrome-headless-shell 1248) against https://127.0.0.1 with two temporary MFA-enrolled accounts (uat86r2-super, Super Admin platform scope; uat86r2-admin, ABC Tenant Admin), measured in the DOM: widths 1024/1100/1180/1280/1440, sidebar open (256 px) and collapsed (76 px), light and dark (html.dark checked): 40/40 rows have the region inside its card, no page horizontal scroll, the table scrolls sideways where narrower than its content (Organizations 884 px, per-rule 920 px), and after scrolling to the end Action, Would have done (simulation), Lift shadow mode and Use as test organization (Organizations) and Refused, Would have done (simulation) (per-rule) are inside the region; Tab reaches the labelled region (6 Tabs / 5 Tabs from the card toggle) with :focus-visible and a visible outline. Turn shadow mode back on was absent (no organization has shadow lifted), so not checked. 320/340/366 px: no page horizontal scroll; Organizations shows stacked cards with the Shadow mode chip on its own row, no overlap with Days observed, chip inside the card; the per-rule table renders as cards below 1024 px. No page errors. Screenshots, results.json and archived account rows in ~/omni-archives/uat86-r2-t5/; both accounts removed afterwards (users 5, login_events 13, notifications 15 back to baseline; 17 hash-chained audit_logs entries left). Side note, outside G-86-5: the floating assistant greeting bubble (Chitti) overlays the right edge of both tables at 1024 px and runs off the left edge at 320 px."
note: "Round 1 (2026-11-14): issue G-86-5 (major), diagnosed in .planning/debug/golive-tables-clipped.md. Gap plan 86-16 fixed it in code (2a4e2ea4e, ad556c174). Publish dist-new (index-BeV-nK0J.js) first; the live site still serves index-BwnVKpDW.js, which lacks the fix. Review WR-07: nothing on screen shows that the tables scroll."

## Summary

total: 5
passed: 3
issues: 0
pending: 0
skipped: 0
blocked: 2

## Gaps
