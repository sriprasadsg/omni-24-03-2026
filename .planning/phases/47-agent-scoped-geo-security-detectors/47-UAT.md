---
status: testing
phase: 47-agent-scoped-geo-security-detectors
source: [47-VERIFICATION.md]
started: 2026-07-29T20:20:00Z
updated: 2026-07-29T20:20:00Z
---

## Current Test

number: 1
name: VPN/hosting heuristic badge renders on the agent card
expected: |
  Load an agent card (AgentList.tsx) for an agent whose public IP resolves to a known
  VPN/hosting AS-org (geo.vpn_heuristic === true). An amber pill with a WifiIcon reading
  "likely VPN/hosting" appears in the Location row. For an agent with vpn_heuristic
  false/absent, no badge appears. Wording never says "detected".
awaiting: user response

## Tests

### 1. VPN/hosting heuristic badge renders on the agent card
expected: Amber "likely VPN/hosting" WifiIcon pill in the Location row when geo.vpn_heuristic === true; no badge when false/absent; never "detected" (GSEC-01).
result: [pending]

### 2. Geo Security settings panel — admin flow + persistence + isolation
expected: As admin, open Sidebar → Management & Settings → Geo Security. Toggle Impossible-Travel off/on, toggle Geo-Fence on, add a country code (e.g. US) → chip appears, remove it. Each edit calls PATCH /api/settings/geo-security, shows a success toast, and persists across reload (GET read-back). As non-admin, the panel/mutation is inaccessible (403 + nav gated by manage:settings). (GSEC-03 config half)
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
