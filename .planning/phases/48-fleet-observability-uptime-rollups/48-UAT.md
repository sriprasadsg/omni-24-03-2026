---
status: testing
phase: 48-fleet-observability-uptime-rollups
source: [48-VERIFICATION.md]
started: 2026-07-30T05:30:00Z
updated: 2026-07-30T05:30:00Z
audit_acknowledged:
  milestone: v4.1
  at: 2026-08-26
  gap_snapshot: "testing::scenarios=2"
---

## Current Test

number: 1
name: Agent detail Metrics tab renders charts + uptime timeline
expected: |
  Open an agent's detail view, click the Metrics tab. CPU/memory/disk history render as
  recharts AreaCharts and a uptime timeline + uptime % appear. Changing the range selector
  (1h / 6h / 24h / 48h) refetches and updates both. No 7d/30d option.
awaiting: user response

## Tests

### 1. Agent detail Metrics tab renders charts + uptime timeline

expected: Metrics tab shows CPU/mem/disk AreaCharts + uptime timeline/%; range selector 1h/6h/24h/48h refetches and updates; no 7d/30d. (FOBS-01/02)
result: [pending]

### 2. Fleet Observability page — reachability + permission gate

expected: A user with manage:agents sees the Fleet Observability sidebar entry and the page lists offline agents + version-drift (agents older than 2.1.4). A user WITHOUT manage:agents cannot see/reach it. (FOBS-03)
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
