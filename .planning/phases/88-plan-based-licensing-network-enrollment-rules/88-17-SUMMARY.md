---
phase: 88-plan-based-licensing-network-enrollment-rules
plan: 17
subsystem: network-rules
tags: [lic-05, network-enrollment, refusal-wording, gap-closure]
status: complete
gap_ids: [G-88-5]

requires:
  - phase: 88-05
    provides: validate_widen (D-42 bounded widening) and EntryError
provides:
  - "validate_widen refusals written for the decider: plain words, the /24 or /48 limit or the enrolled-from address, never the request field name"
affects: []

actuals:
  tokens: 30000
  tasks: 2
  commits: 2
plan_head_before: ca415e00f
plan_head_after: bd43d9802

key-files:
  created: []
  modified:
    - backend/network_rules.py
    - backend/tests/test_network_rule.py

coverage:
  - id: G-88-5
    description: "A refused network range reads as one plain sentence in the Pending agents panel, names its limit or the address, and never names the request field; the /8 case also says the range must contain the address"
    requirement: LIC-05
    verification:
      - kind: unit
        ref: "backend/tests/test_network_rule.py::test_each_range_refusal_reads_plainly_and_names_its_limit_or_the_address (11 cases)"
        status: pass
      - kind: integration
        ref: "backend/tests/test_network_rule.py::test_a_range_wider_than_a_24_is_refused_in_plain_words and the extended test_a_wide_or_foreign_range_answers_422_and_changes_nothing (4 cases)"
        status: pass
    human_judgment: false
---

# 88-17 Summary: plain-word network range refusals (G-88-5)

Only the refusal texts in `validate_widen` changed. The check order, the D-42 limits (/24, /48), the 422 path and "a refusal writes nothing" are unchanged and still tested.

## How the Pending agents panel shows each refusal

- Too wide: "Couldn't allow this network: the range can be at most a /24 for an IPv4 address, and must contain 198.51.100.9. Try again." (IPv6: "/48 for an IPv6 address")
- Not a range: "Couldn't allow this network: 'nonsense' is not a network range; write one that contains 198.51.100.9, like 198.51.100.0/24. Try again."
- Other IP version: "Couldn't allow this network: 198.51.100.9 is an IPv4 address, so the range must be IPv4 too. Try again."
- Misses the address: "Couldn't allow this network: the range must contain 198.51.100.9, the address this computer enrolled from. Try again."
- Private range for a public address: "Couldn't allow this network: 198.51.100.9 is a public address, so the range must be public too. Try again."

The wording is the planner's choice (assumption A-88-G1); ask for different wording if any of these reads wrong.

## Verification

- `tests/test_network_rule.py` + `tests/test_pending_agents.py`: 67 passed.
- `grep -v '^\s*#' backend/network_rules.py | grep -c widenTo` = 0.
- /verify: typecheck, lint, build PASS; tests TOO_BROAD (708 files against origin/main), the targeted suites above ran instead.

## Going live

A backend restart only (no UI publish). That is the user's call.

## Commits

- 8df9cc27a fix(88-17): a too-wide network range is refused in plain words, naming the limit and the address
- bd43d9802 fix(88-17): every network range refusal names its limit or the address, never the request field (G-88-5)
