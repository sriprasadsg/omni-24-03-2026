---
status: diagnosed
gap_id: G-88-5
phase: 88-plan-based-licensing-network-enrollment-rules
goal: find_root_cause_only
created: 2026-11-19
---

# DEBUG: a refused network range names the API field widenTo

## Symptoms (from 88-UAT.md test 5)

- Expected: a refused range tells the decider in plain words why (at most a /24 for IPv4, /48 for IPv6; must contain
  the observed address).
- Actual (live, 2026-11-19 14:57, Super Admin approving UAT88-NET-TEST with range 10.0.0.0/8 for 135.237.98.107):
  `Couldn't allow this network: widenTo may be at most a /24 (IPv4). Try again.`
- Reproduction: Agents > Agents waiting for approval > a new_network hold > Range (optional) = a /8 > Allow network.

## Root cause

`backend/network_rules.py` `validate_widen()` words every refusal for the API caller, starting with the request
field name: `widenTo is not a network: ...` (line 91), `widenTo must be the same IP version ...` (93),
`widenTo may be at most a /{widest} (IPv{n})` (96), `widenTo must contain the observed address {ip}` (98),
`widenTo is not a public range, but the observed address is` (100). `pending_agents._network_to_allow()` (384-386)
turns the EntryError into DecisionError(422, str(err)), and the UI shows the server message verbatim, as
88-UI-SPEC.md line 360 specifies (`Couldn't allow this network: {server message}. Try again.`). So the UI is to
spec; the server text is not written for a person.

Secondary: the width check runs before the containment check, so a /8 that also misses the address only reports
the width. One refusal at a time is acceptable; the wording is the defect.

## Evidence

- nginx: `POST /api/agents/pending/agent-922bb9c64aec4dcd9c12fc346e5905b5/approve 422` then `200` (the /29 retry).
- Screenshot: ~/omni-archives/uat88/shots/t6-super-bad-range.png.
- backend/tests/test_network_rule.py asserts only that EntryError is raised (lines 79-90, 281+), never the text, so
  rewording breaks no test; nothing else parses these strings (only caller: pending_agents.py:384).

## Fix direction (for the gap plan)

Reword the five messages for the decider, without API names, e.g. "the range must be at most a /24 for an IPv4
address", "the range must contain 135.237.98.107", "that is not a network range: '...'", "the range must be IPv4
like the address", "the range must be public like the address"; add a test asserting a refusal never contains
"widenTo" and names the limit or the address.
