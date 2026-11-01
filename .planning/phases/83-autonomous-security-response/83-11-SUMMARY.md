---
phase: 83-autonomous-security-response
plan: 11
subsystem: autonomous-ops-sweep
tags: [autonomous-ops, incidents, quarantine, protected-paths, playbooks, isolation, mongo]

requires:
  - phase: 83-autonomous-security-response
    provides: "83-05 signals.observe new_evidence, Candidate.path, the sweep's memory and dedupe keys"
  - phase: 83-autonomous-security-response
    provides: "83-08 dormancy step (agent_support), host cap, breaker-ignored codes"
provides:
  - autonomous_ops/incidents.py (QUIET_GAP, attach, get_open, current, claim_isolate, release_isolate, ensure_indexes)
  - autonomous_ops/protected_paths.py (is_protected over the contract's protectedPaths)
  - automatic quarantine_file {path, sha256} decisions in the sweep, with a card for a protected file
  - select_playbook routes per D-05, D-07, D-08; vendored quarantine_file.yaml
  - one isolate_host approval line per incident (D-24)
affects: [83-12, 83-13, 83-18, 83-19, 83-20]

actuals:
  tokens: 23100
  tasks: 3
  commits: 6
plan_head_before: ee96b27654b23f7ec10d8feca2920195b45074da
plan_head_after: 03c90856d51ad5dd0c8cc9f2c24e01165abede5d

tech-stack:
  added: []
  patterns:
    - "Incident grouping is one compare-and-set find_one_and_update on the open document, a unique partial index for one open incident per host, and a retry through the read when the insert loses a race"
    - "lastAlertAt moves only forward ($max) and only on evidence time; alertCount counts the sweep's new_evidence, so a finding seen on ten ticks counts once"
    - "The sweep reads a playbook for its name and its gate_class raise key only; params, steps and rollback of the decision are built by the sweep"

key-files:
  created:
    - backend/autonomous_ops/incidents.py
    - backend/autonomous_ops/protected_paths.py
    - backend/playbooks/quarantine_file.yaml
    - backend/tests/test_autonomous_ops_incidents.py
    - backend/tests/test_autonomous_ops_quarantine_decisions.py
  modified:
    - backend/autonomous_ops/sweep_security.py
    - backend/autonomous_ops/decision_row.py
    - backend/autonomous_ops/response_messages.py
    - backend/migrations/028_security_response.py
    - backend/remediation_playbook_service.py
    - backend/tests/test_autonomous_ops_origins.py
    - backend/tests/test_autonomous_ops_two_signal.py
    - backend/tests/test_autonomous_ops_structural.py
    - backend/tests/test_autonomous_ops_remediation_truth.py
    - backend/tests/test_autonomous_remediation_loop.py
    - backend/tests/test_remediation_guards.py
    - backend/tests/test_remediation_playbook.py

key-decisions:
  - "A decision with no new evidence in its own tick (a retry, a later second origin) joins the host's open incident however old its lastAlertAt is; closing is lazy and happens only when new evidence arrives (incidents.current). A host with none open gets one with alertCount 0."
  - "A protected-file card puts the two-source sentence in reason.inputs.detail and sets inputs.protectedPath; response_views already words the protected-file reason from those two fields."
  - "The isolate line is skipped when the main decision was an undo-window refusal, and is attempted after a recorded acting decision in every state (dispatching, suggested, shadow, awaiting_approval)."
  - "Tests that used a malicious-file finding or a vulnerability as a vehicle for the approval card or the dispatch loop now use a tenant playbook that raises quarantine_file with gate_class approve, or route the vuln to patch_package by hand, because D-05 and D-07 changed the routes."

requirements-completed: []

coverage:
  - id: D1
    description: "Two evidence items 59 minutes apart share one incident (alertCount 2, lastAlertAt the later); exactly 60 minutes opens a new one and closes the old; out-of-order evidence does not move lastAlertAt back"
    requirement: "RESP-09"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_incidents.py#quiet gap"
        status: pass
    human_judgment: false
  - id: D2
    description: "One open incident per host: concurrent attaches end with one, the unique partial index refuses a second, a fresh client on the same database continues the same incident, hosts and tenants never mix"
    requirement: "RESP-09"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_incidents.py#one open incident, restart safety"
        status: pass
    human_judgment: false
  - id: D3
    description: "The same evidence on ten ticks counts once and lastAlertAt is the evidence time, not the tick time; acting rows carry reason.inputs.incidentId and a suggestion row carries none"
    requirement: "RESP-09"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_incidents.py#the sweep feeds and reads incidents"
        status: pass
    human_judgment: false
  - id: D4
    description: "A file two origins flag, with a known path, becomes one automatic quarantine_file {path, sha256}; with no known path it stays a suggestion and writes no instruction; in shadow it is a simulation"
    requirement: "RESP-03"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_quarantine_decisions.py#the automatic quarantine"
        status: pass
    human_judgment: false
  - id: D5
    description: "A file under a protected OS path (Linux and mixed-case forward-slash Windows) is a card with allow_protected true in its params; only approving that card sends allow_protected; an ordinary file never carries it"
    requirement: "RESP-03"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_quarantine_decisions.py#protected system files"
        status: pass
    human_judgment: false
  - id: D6
    description: "select_playbook: nscan file and hash -> quarantine_file, ip -> block_ip, vuln with or without a CVE -> None, fim -> None, rotate_key with fingerprint and the shadow-AI kill route kept; restore_file, disable_service, rotate_key stay vendored and approval-only"
    requirement: "RESP-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_remediation_playbook.py"
        status: pass
    human_judgment: false
  - id: D7
    description: "A tenant playbook with gate_class approve raises a block or a quarantine to a card; a class of auto changes nothing; nothing lowers an approval action"
    requirement: "RESP-01"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_quarantine_decisions.py#playbooks may raise a class, never lower it"
        status: pass
    human_judgment: false
  - id: D8
    description: "A corroborated finding adds one awaiting_approval isolate_host row with the same incidentId; a second finding in that incident adds none; a new incident may; a host without the token gets none and the claim is not spent; Suggest makes it a suggested row, shadow a simulation; no tick sends isolate_host to the dispatcher"
    requirement: "RESP-05"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_incidents.py#isolation is proposed once per incident"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-11-01
status: complete
---

# Phase 83 Plan 11: Incidents, the automatic quarantine and the one isolate line

**A burst of alerts on one host is one incident until it has been quiet for an hour; a file two sources agree on is moved to quarantine automatically unless it is a protected system file; and each incident asks a person once whether to isolate the host. Nothing here isolates, kills or reboots on its own.**

## Performance

- **Duration:** about 25 min
- **Tasks:** 3 (all TDD)
- **Commits:** 6 (3 test, 3 feat), measured from `ee96b2765` to `03c90856d`
- **Line counts:** `sweep_security.py` 369 (was 242, limit 500), `incidents.py` 120, `protected_paths.py` 81
- **Used the cargo recipe:** no, this plan touches no Rust.

## Task Commits

| Task | Commit | Type |
|------|--------|------|
| 1 RED: 14 incident tests | `27578bc16` | test |
| 1 incidents.py, sweep attach, migration 028 | `aebbf3d2e` | feat |
| 2 RED: quarantine decision, routing and updated route tests | `06134fb4a` | test |
| 2 protected_paths, quarantine decision, select_playbook, quarantine_file.yaml | `84c8fba0d` | feat |
| 3 RED: 11 isolation tests | `d6cc83be4` | test |
| 3 one isolate line per incident | `03c90856d` | feat |

## select_playbook route table

| Finding | Before | Now |
|---|---|---|
| nscan, type ip | block_ip | block_ip |
| nscan, type file or hash (any non-ip) | kill_process | **quarantine_file** (D-05) |
| vuln, playbook_ref rotate_key with a fingerprint | rotate_key | rotate_key |
| vuln with a CVE | patch_package | **None** (D-07) |
| vuln without a CVE (misconfig, or rotate_key without a fingerprint) | disable_service | **None** (D-07) |
| fim | restore_file | **None** (D-08) |
| anomaly shadow_ai_detected with an agent | kill_process | kill_process |
| anything else | None | None |

`restore_file`, `disable_service`, `patch_package` and `kill_process` stay vendored; `restore_file`, `disable_service`, `rotate_key` and `kill_process` stay approval-only in the registry (D-09). `ACTION_MAP` gains `quarantine_file` and `unquarantine_file`.

## Tests whose expectations changed

- `test_remediation_playbook.py`: the file, vuln-with-CVE, misconfig, rotate_key-without-fingerprint and fim route tests (new expectations above), plus new tests for a hash, for D-09 and for the quarantine_file playbook shape.
- `test_autonomous_remediation_loop.py`: the seven loop-mechanics tests used a vuln-with-CVE finding routed to patch_package; a fixture now routes a vuln to patch_package by hand for them. A new `TestSuggestionOnlyFindings` pins `no_playbook` for vuln and fim.
- `test_autonomous_ops_structural.py`: `_findings` now covers block_ip, quarantine_file, kill_process (shadow-AI anomaly) and rotate_key; the not-selected set `{patch_package, disable_service, restore_file}` is explicit and each must select None; the queue test runs four playbooks and treats block_ip and quarantine_file as the automatic ones.
- `test_autonomous_ops_two_signal.py`: `test_a_file_that_two_origins_name_is_left_for_the_quarantine_plan` (83-05) now expects the automatic quarantine.
- `test_autonomous_ops_origins.py`: the migration 028 test expects the new collections (autonomy_incidents, and autonomy_actions for its incident index).
- `test_remediation_guards.py` and `test_autonomous_ops_remediation_truth.py`: not in the plan's list. They used a malicious file as the vehicle for an approval card (kill_process). They now seed a tenant playbook that raises quarantine_file with `gate_class: approve`, so the card flow, the double-click, deny, stop and escalation tests are unchanged in what they prove; two assertions read `quarantine_file` where they read `kill_process`.

## What was built

- **incidents.py.** `attach` is a `find_one_and_update` on the open incident whose `lastAlertAt` is greater than `at - 1 h` (`$max lastAlertAt`, `$min startedAt`, `$inc alertCount`); otherwise it closes stale open incidents and inserts a new one, retrying through the read on `DuplicateKeyError`. `ensure_indexes` makes the unique partial index `(tenantId, agentId)` where `closed` is false, the `(tenantId, closed, lastAlertAt)` lookup, and `autonomy_actions (tenantId, reason.inputs.incidentId, state)`; migration 028 calls it.
- **Sweep.** Each `new_evidence` item is attached at its evidence time before candidates are decided. Acting decisions (address, range, file) carry `reason.inputs.incidentId`; a decision whose incident cannot be read is skipped. Playbooks load once per tenant per pass and only when a decision needs one; a tenant whose playbooks cannot be read gets a card.
- **Quarantine.** Params are exactly `{path, sha256}`. A protected path sets `playbook_raise`, adds `allow_protected: true` and `inputs.protectedPath` and `inputs.detail`. Dedupe key `{tenant}|sweep|quarantine_file|{agent}|{sha256}`. The dormant-host check, the undo window, the host cap and shadow all apply as they do to a block. A row for a file action shows the path as its target (`decision_row.display_target`).
- **Isolation.** After a recorded acting decision (and not an undo-window refusal): `agent_support.check` for `isolate_host`, then `incidents.claim_isolate`, then `gate.decide` with `actions=[isolate_host]`, no params, dedupe key `{tenant}|sweep|isolate_host|{agent}|{incidentId}`. A refusal that records nothing calls `release_isolate`.

## Deviations from Plan

**1. [Rule 3 - Blocking] Tests outside the plan's list had to change**
- `test_remediation_guards.py`, `test_autonomous_ops_remediation_truth.py`, `test_autonomous_ops_two_signal.py` and `test_autonomous_ops_origins.py` encoded the old routes or the old migration contents (see above). Committed with the Task 1 and Task 2 commits.

**2. [Rule 2 - Missing] One new user-visible sentence**
- `response_messages.WHY_TEMPLATES["file_no_path"]`: `{reason} Where this file is on the computer isn't known, so there is nothing to move.` It is on a corroborated hash with no known path (a suggestion), which the UI-SPEC does not word. **The user should read it.** The `{reason}` part is the existing two-sources or rule-off sentence. It passes the banned-terms gate (`test_autonomous_ops_copy.py`).

**3. [Honest note] A-83-ONE-PATH says "newest known path"; the signal keeps the lexicographically smallest.** `signals._Acc.origin` stores the smaller path string. This plan quarantines whatever `Candidate.path` holds. The behaviour for a second path of the same hash is as the assumption describes (decided after the 24-hour memory window), but "newest" is not how the path is chosen.

**4. [Order] The `select_playbook` change was made before its tests were committed**, to find which other tests it broke. RED for the routing tests was shown afterwards by putting HEAD's `remediation_playbook_service.py` back and removing the new YAML for one run: 14 failed, 53 passed, then both were restored.

## RED runs, stated honestly

- **Task 1:** all 14 tests failed with `ImportError: cannot import name 'incidents'`. That is an import error, not a behaviour assertion.
- **Task 2:** the quarantine-decision tests failed on assertions (no row written, `ValueError: not enough values to unpack`), 14 failed. The 40 `is_protected` cases passed at once because `protected_paths.py` was written before its tests were run.
- **Task 3:** 6 of 11 failed on assertions (no isolate row). The other 5 (rule on proposes nothing, no token, refusal gives the claim back, claim_isolate, never dispatched) passed vacuously before the change, so they guard the new code and did not drive it.

## Verification

All of `backend/tests/test_autonomous_ops_*.py` plus the remediation playbook, loop, guards, rotate-key, UEBA and catalogue-slice tests, on the private mongod (27998): **937 passed**, none skipped, 321 s. The plan's three verify commands were each run on the files they name and pass. `test_ledger_ratchets` was not in this run.

## Not read, or read in part

- `83-RESEARCH.md` (Q4 and the rest): not read.
- `83-UI-SPEC.md`: only the protected-file card and Isolation proposed paragraphs (found by grep), not section 2a in full.
- `83-CONTEXT.md`: the decisions section (D-01 to D-28 and the research defaults) in full; canonical references and code insights not read.
- `STATE.md`: frontmatter and the last section only. `83-05-SUMMARY.md` and `83-08-SUMMARY.md`: not read; I relied on the run notes and the code.

## Facts for later plans

- `incidents.current(db, tenant, agent, at)` is the lookup a decision uses; `incidents.get_open(..., now)` answers only inside the quiet gap. 83-12 and 83-13 (restart, kill-then-quarantine) should take `incidentId` from `current` so their rows join the same card.
- `sweep_security` counts now include `quarantined` and `isolation`.
- A protected-file row has `reason.inputs.protectedPath` true and `reason.inputs.detail` (the two-source sentence); `reasonCode` is `playbook_raised`, not `protected_path`.
- A card raised by a tenant playbook alone keeps the two-source sentence; only the protected-file, host-cap and undo cases have their own wording.
- The isolate row has no params, `targets` is the agent, and its `reasonText` equals the acting row's. The 83-18 card should group it by `reason.inputs.incidentId`.
- A done quarantine holds the finding for 24 hours (the default hold in `sweep_memory`); after that, if the hash is still seen on the host, the sweep decides again and the agent answers `refused` for a file that is gone (`agent_refused`, ignored by the breaker). Not fixed here.
- The old remediation loop (`remediate()`, started by a person or by UEBA) now sends a malicious file to `quarantine_file`, an automatic class, with `sha256` read from `details.sha256` (absent in today's scan findings). Only people start it for files, so the two-source rule is not bypassed by a timer, but the instruction carries no hash.
- Requirements RESP-01, RESP-03, RESP-05 and RESP-09 are not ticked: each spans plans still to come (kill chain, restart, the cards).

## Threat Flags

None. No new endpoint or file access; the quarantine boundary (T-83-46) and the playbook-raise boundary (T-83-48) are implemented as the threat model describes, and `protected_paths.is_protected` normalises before matching (T-83-49).

## Known Stubs

None.

## Self-Check: PASSED
