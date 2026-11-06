---
phase: 84-staged-patch-rollouts
plan: 11
subsystem: agent
status: complete
tags: [rust-agent, service-state, health-gate, heartbeat, agent-contract]

requires:
  - phase: 84-staged-patch-rollouts
    provides: 84-07 agent tokens and the contract (12 tokens); 84-08 backend reads meta.service_state (block newer than the change + 120 s, every watched service running)
provides:
  - service_watch::state_from_health, state_report_with (pure), state_report (60 s cache, Windows and Linux)
  - heartbeat key meta.service_state {v 1, at, services [{name, state}]} on every heartbeat
  - token service_state in SUPPORTED_TOKENS and the contract (13 tokens)
affects: [84-12, 84-13, 84-21]

requirements-completed: [PTCH-02]

actuals:
  tokens: 6500
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "a pure report function takes the status lookup as an argument, so the heartbeat block is tested without a service manager"

key-files:
  created: []
  modified:
    - agent-install/omni-agent-rs/src/capabilities/service_watch.rs
    - agent-install/omni-agent-rs/src/capabilities/service_watch_tests.rs
    - agent-install/omni-agent-rs/src/heartbeat.rs
    - agent-install/omni-agent-rs/src/capabilities/response_actions.rs
    - agent-install/omni-agent-rs/src/capabilities/response_contract_tests.rs
    - shared/agent-response-contract.json
    - backend/tests/test_patch_rollout_contract.py

key-decisions:
  - "Starting and stopping (Pending) and unreadable (Unknown) both report as unknown, because the contract lists only four states and the gate must never read a half-started service as running"
  - "The state report is not behind the remediation_executor capability: the agent only holds a watched list when the tenant has that capability, and an empty list gives services []"
  - "A critical service name on the watched list is still reported (read-only status); only a malformed name or one over 128 characters is left out, so the backend never finds a watched service missing from the block"
  - "Answers are cached for 60 s for the same list (same rule as service_failures); the block keeps the time it was read, which is always inside the backend's 120 s settle margin"
  - "Duplicates are matched case-insensitively, as the failure report does"

patterns-established:
  - "heartbeat.rs gets one line per new meta block; the logic lives in the capability module"

coverage:
  - id: D1
    description: "Every Windows and Linux heartbeat carries meta.service_state listing each watched service as running, stopped, failed or unknown in watched order; a clean stop is reported; an empty list gives services []"
    requirement: PTCH-02
    verification:
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/service_watch_tests.rs#state_report_lists_every_watched_service_in_order_including_a_clean_stop"
        status: pass
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/service_watch_tests.rs#state_report_of_an_empty_list_has_no_services"
        status: pass
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/service_watch_tests.rs#state_from_health_maps_every_variant"
        status: pass
    human_judgment: true
    rationale: "The mapping and the block are tested with a fake status lookup; the live systemctl and sc answers on a real host are the existing status_of paths and need a real Windows host to prove"
  - id: D2
    description: "Duplicate names appear once, names over 128 characters and malformed names are never asked about or listed"
    requirement: PTCH-02
    verification:
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/service_watch_tests.rs#state_report_lists_a_duplicate_name_once_and_drops_a_name_over_128_characters"
        status: pass
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/service_watch_tests.rs#state_report_asks_each_service_once_and_never_for_a_malformed_name"
        status: pass
    human_judgment: false
  - id: D3
    description: "The agent advertises service_state on Windows and Linux and nothing on another platform; the contract tokens list equals SUPPORTED_TOKENS (13) and a state report has the shape of the contract serviceState example"
    requirement: PTCH-02
    verification:
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/response_contract_tests.rs#a_state_report_has_the_shape_of_the_contract_service_state_example"
        status: pass
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/response_contract_tests.rs#the_reported_tokens_equal_the_contract_exactly"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_contract.py#test_service_state_is_the_last_of_thirteen_tokens"
        status: pass
    human_judgment: false

duration: ~20min
completed: 2026-11-06
plan_head_before: cf6fcbc147e7c8ee6221be47e93caf565bc7b815
commits: 2
plan_head_after: cab3e647c23724e57791e44958f335d7be0a24a1
---

# Phase 84 Plan 11: Service State Report Summary

**Every 2.1.17 heartbeat on Windows and Linux now lists the state (running, stopped, failed, unknown) of each watched service in meta.service_state, advertised by the service_state token, so the rollout health gate can see a cleanly stopped service that service_failures never reports.**

## Accomplishments

- `service_watch.rs`: `state_from_health`, the pure `state_report_with(watched, now, status)` and `state_report(os, watched, now)` (asks the service manager through `status_of`, caches the answer 60 s for the same list; other platforms give `services: []`).
- `heartbeat.rs`: exactly one added line after `service_failures`; `service_failures` is untouched.
- Token `service_state` appended to `SUPPORTED_TOKENS` and the contract `tokens` (13 entries); pinned lists updated; a Rust test builds a report from the contract's example names and compares it with `serviceState.example`; the backend contract test pins 13 tokens with `service_state` last.

## Task Commits

1. Task 1: service_state report from the watched list - `ed01f0aa3` (feat)
2. Task 2: the service_state token - `cab3e647c` (feat)

TDD note: as in 84-07, tests and code were written together per task in the same commit (Rust inline tests; a compile error is not a valid RED). No separate RED commit exists.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] The user's uncommitted heartbeat.rs work sits in the same file**
- **Found during:** Task 1
- **Issue:** heartbeat.rs carries the user's gzip and `collect_due` hunks (+51/-11), so staging the whole file would commit their code.
- **Fix:** built a patch of the one added line against `git show HEAD:` and staged it with `git apply --cached`. The user's hunks are still present unstaged (`git diff --ignore-cr-at-eol --stat HEAD` still shows +51/-11). The "at most 3 added lines" criterion is therefore measured on the staged diff: 1 added line.
- **Files modified:** `agent-install/omni-agent-rs/src/heartbeat.rs`
- **Commit:** `ed01f0aa3`

**2. [Rule 2 - Missing critical] Cache for the state report**
- **Found during:** Task 1 (T-84-37)
- **Issue:** with up to 50 watched services, a status command per service on every heartbeat would be heavier than the failure report, which is cached for 60 s.
- **Fix:** `state_report` shares the 60 s rule; tested pure function unchanged.
- **Commit:** `ed01f0aa3`

**Total deviations:** 2 (1 blocking, 1 missing-critical). **Impact:** none on the plan's truths.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register. T-84-36: names over 128 characters and malformed names are not listed; the backend matches against the tenant's own list only. T-84-37: one entry per watched service, duplicates dropped, at most 50 names by the existing watched-list cap.

## Issues Encountered

None. Not done here (belongs to 84-21): the Windows target build check and the agent version bump; nothing was built as a release binary, deployed, restarted or published.

## Verification

- `cargo test --lib service_watch`: 37 passed; `--lib response_`: 92 passed; whole `--lib`: 476 passed, 0 failed, 1 ignored (private target dir `target/nodebug`).
- Backend on a private mongod (port 27998, stopped afterwards): `test_patch_rollout_contract`, `test_autonomous_ops_block_contract`, `test_patch_rollout_health` 118 passed, no skips.
- Acceptance: `grep -c service_state heartbeat.rs` is 1; staged heartbeat diff `1 0`; contract `tokens[-1]` prints `service_state`.

## Next Phase Readiness

With 2.1.17 published, a tenant that has `remediation_executor` and a watched list gets a real Services signal; until then those hosts read Not checked. Live-only: real `systemctl` and `sc` answers on a host with a stopped service.

## Self-Check: PASSED

- Commits `ed01f0aa3` and `cab3e647c` are ancestors of HEAD; the files above exist; the user's heartbeat.rs hunks are still unstaged in the working tree.
