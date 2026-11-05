---
status: testing
phase: 82-platform-self-healing-scheduled-retention
source: [82-VERIFICATION.md]
started: 2026-10-31T10:45:00Z
updated: 2026-11-05T11:50:54Z
---

## Current Test

number: 1
name: Install the watchdog by hand and check polkit
expected: |
  Timer active; polkit allows exactly the listed units and verbs; the existing mongod GLIBC_TUNABLES drop-in still applies; deployed ownership and modes match T-82-06/20/21/22
awaiting: user response

## Tests

### 1. Install the watchdog by hand and check polkit
how: Follow deploy/omni-watchdog/INSTALL.md (never run-on-ubuntu.sh), then run pkcheck as the omni-watchdog user for nginx.service restart
expected: Timer active; polkit allows exactly the listed units and verbs; the existing mongod GLIBC_TUNABLES drop-in still applies; deployed ownership and modes match T-82-06/20/21/22
result: [pending]

### 2. Real stop and restart of MongoDB and the backend
how: Stop mongod, then the backend, on the installed server
expected: Noticed within about 2 minutes, mongod restarted first, backend second; after 3 failed restarts one page only; panel and Activity show each step
result: [pending]

### 3. Real on-call channel and external heartbeat
how: Fill /etc/omni-watchdog/oncall.env, press Send test alert, set the external heartbeat URL
expected: One alert arrives and resolves; the no-working-channel banner clears; stopping the watchdog raises the in-app alarm and the external heartbeat service alerts
result: [pending]

### 4. First live retention count and confirmation
how: After deploy, review the first 02:00 UTC retention count on the Platform health panel, then Confirm deletion. Confirm only on a build that includes 82-15 to 82-17
expected: Counts for every organization are listed, nothing is deleted before the confirmation, and the next run deletes only confirmed rows
result: [pending]

### 5. Browser pass of the health section and retention card
how: Open Autonomous Ops platform health and the retention review in a published UI, light and dark, at 640, 1024 and 1280 px
expected: Layout matches 82-UI-SPEC sections 1-7
result: pass
note: "2026-11-05: passed in headless Chrome on the release bundle, private copy: Platform health, Scheduled data retention and the response settings section in light and dark at 1280, 1024 and 640 px, no sideways overflow, screenshots read right. Only the not-installed and never-counted states could show: the reporting and counted states follow items 1 and 4."

## Summary

total: 5
passed: 1
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
