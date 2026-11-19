---
phase: 88-plan-based-licensing-network-enrollment-rules
plan: 16
subsystem: go-live
tags: [plans, licensing, go-live, read-only-check]
status: complete

requires:
  - phase: 88-11
    provides: backend/scripts/check_plan_golive.py, migration 034
provides:
  - "Recorded go-live state of Phase 88 on the live database and the running omni-backend unit"
affects: [88-verification]

actuals:
  tokens: 15000
  tasks: 2
  commits: 1

key-files:
  created:
    - .planning/phases/88-plan-based-licensing-network-enrollment-rules/88-16-SUMMARY.md
  modified: []
---

# 88-16 Summary: go-live hand-off and read-only check

Phase 88 is live: migration 034 was applied at the backend restart of 2026-11-11 08:05:15 UTC, and the running unit
trusts forwarded addresses only from 127.0.0.1. The go-live check's one FAIL is a roaming test laptop, recorded as
such at the user's decision on 2026-11-19 ("Record it as a roaming laptop"); no live data was changed for it.

## Task 1: the user's go-live

- Restart that applied migration 034: 2026-11-11 08:05:15 UTC (backend log: "migrations: applying 034 — Plan
  licensing", noted 2026-11-14). The trials started then: ABC and shieldforgetech end 2026-11-25.
- Proxy trust: the unit's ExecStart carries `--proxy-headers --forwarded-allow-ips 127.0.0.1` (seen 2026-11-15 and
  2026-11-19).
- UI and pushes: the Phase 88 screens have been in every UI published since (latest index-BWDFsUv3.js), and the
  Phase 88 commits are on origin/npx.

## Task 2: read-only checks (2026-11-19 14:3x UTC)

`backend/scripts/check_plan_golive.py --db omni_platform` (URL from /etc/omni/mongo-read.env, read-only), exit 1:

```
Platform | plan Enterprise | maxAgents 5 | override - | trial ends - | networks -
Exafluence Global Analytics Private Limited | plan Pro | maxAgents 50 | override - | trial ends 2026-11-11T08:05:15.510727+00:00 | networks -
shieldforgetech | plan Free | maxAgents 5 | override - | trial ends 2026-11-25T08:05:15.510727+00:00 | networks -
ABC | plan Free | maxAgents 5 | override - | trial ends 2026-11-25T08:05:15.510727+00:00 | networks 115.245.47.74/32
FAIL tenant_f988871f8e54: agent EILT0197 public address 203.193.174.92 is not inside its allowed networks
```

`systemctl cat omni-backend | grep -c -- "--forwarded-allow-ips 127.0.0.1"` printed 1.

### The FAIL: a roaming test laptop

ABC's allowed network is the address learned at go-live (115.245.47.74/32; the plan expected 103.174.161.233). Its
only agent, the test laptop EILT0197, has since reported from 103.174.161.211 (2026-11-15) and 203.193.174.92
(2026-11-19). The check is right that the address is outside ABC's networks; the cause is the laptop moving, not a
migration or enforcement fault. The user chose to record it rather than add each new address or lift ABC's limit.

## Human checks (open, for /gsd-verify-work 88)

Not done in this plan and not claimed here:

1. Super Admin, Tenant Management: the Plans button and four plans; changing a plan's seats reports the tenants
   updated and a direct tenant without override shows the new limit (revert afterwards).
2. ABC's tenant admin, Agents screen: "Your plan" card shows Free, days left, 5 seats and ABC's network, with no edit
   control.
3. A test machine for ABC enrolling from a different public address: ABC's admin sees "New network <ip>, waiting for
   platform approval" with no approve button; the Super Admin approves with a range; the nginx client address of
   that register call equals the stored sourceIp. EILT0197's moves would serve for this the next time it re-enrolls.

The plan's note for the user, given in the 2026-11-19 reply: Exafluence's licence expiry (2026-10-30) has passed, so
its new machines stay held license_expired until a new expiry date is set in Manage Tenant, whatever its 50 seats.
