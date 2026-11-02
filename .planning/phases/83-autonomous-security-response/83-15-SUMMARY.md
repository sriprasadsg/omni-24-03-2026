---
phase: 83-autonomous-security-response
plan: 15
subsystem: autonomous-ops
tags: [autonomous-ops, sweep, suggestions, vulnerabilities, file-integrity, mongodb, pytest]

requires:
  - phase: 83-autonomous-security-response
    provides: "83-05 sweep stages, signals.resolve and ledger.refresh_suggestion; 83-03 response_views suggestion payload and wording; 83-11 file signals and the quarantine path"
provides:
  - sweep_suggestions.py, the sweep's second stage: one suggested row per computer for vulnerabilities and one for changed files
  - in-place refresh of a grouped row (count, items, time) with no audit event, and no write at all on an unchanged tick
  - rows that end expired/superseded when the findings are gone
affects: [83-18, 83-19, 83-20]

actuals:
  tokens: 21000
  tasks: 2
  commits: 4
plan_head_before: 5e2b35fac06eaa1e5c651c2fd47e6615f013673a
plan_head_after: a4b7c2938317aea7628d144983882b44b3dc09ed

tech-stack:
  added: []
  patterns:
    - "A grouped suggestion is found by its dedupe key first; the gate is asked only when no open row exists"
    - "An unreadable findings list leaves that kind's rows exactly as they are; it never closes one"

key-files:
  created:
    - backend/autonomous_ops/sweep_suggestions.py
    - backend/tests/test_autonomous_ops_suggestions.py
  modified:
    - backend/autonomous_ops/sweep.py
    - backend/autonomous_ops/response_messages.py

key-decisions:
  - "The open row is looked up before the gate runs, so a steady tick costs two reads per computer and kind and writes nothing; a duplicate refusal from the gate still falls back to the refresh path (a racing runner)."
  - "A refused row (never-touch computer) is remembered on an autonomy_signals document keyed {tenant, agentId, kind: vulnerability|file_change, indicator: agentId} with empty origins. observe() only returns documents it touched, so these never become candidates, and the D-08 test shows a normal file-change tick writes no signal at all."
  - "A suggestion is not remembered when recorded (only refusals are): a row that is expired or superseded because the findings went away must be able to come back at once if they return."
  - "A path counts as flagged when either its hash_after or its sha256 is an autonomy_signals file signal for that same computer; the same hash flagged on another computer removes nothing."

requirements-completed: [RESP-01]

coverage:
  - id: D1
    description: "240 open agent vulnerabilities on one computer, CVE or not, are one suggested row (upgrade_software, suggestionOnly, count 240, highest severity, 10 items by severity then id, openView patchManagement); no instruction and no card exist"
    requirement: "RESP-01"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_suggestions.py#test_240_vulnerabilities_on_one_computer_are_one_suggested_row"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_suggestions.py#test_items_are_sorted_by_severity_and_then_by_id"
        status: pass
    human_judgment: false
  - id: D2
    description: "Ten unchanged ticks write nothing; the expiry is extended only under 12 hours; a new finding updates count and createdAt in place with no audit event and no new row; no findings left ends the row expired/superseded"
    requirement: "RESP-01"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_suggestions.py#test_ten_ticks_with_no_change_leave_one_row_and_no_write_after_the_first"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_suggestions.py#test_a_new_vulnerability_updates_the_row_in_place_with_no_new_row_and_no_audit_event"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_suggestions.py#test_when_no_vulnerabilities_are_left_the_row_ends_expired_superseded"
        status: pass
    human_judgment: false
  - id: D3
    description: "Two computers give two rows, two tenants stay apart, an ambiguous hostname is skipped, a never-touch computer records one refused row held 24 hours, shadow gives one simulation, and a row exists whatever the agent supports"
    requirement: "RESP-01"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_suggestions.py#test_a_never_touch_computer_records_one_refused_row_and_the_memory_holds_it_a_day"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_suggestions.py#test_a_tenant_in_shadow_gets_one_simulation_per_computer_and_kind_in_a_day"
        status: pass
    human_judgment: false
  - id: D4
    description: "Changed files in 24 hours are one file_change row (restore_file, openView fimMonitoring); duplicates count once; Added and Removed are not counted; a path whose hash is flagged for that computer leaves the row; old events are ignored and the row closes"
    requirement: "RESP-01"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_suggestions.py#test_three_changed_paths_in_a_day_are_one_row_with_the_paths"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_suggestions.py#test_a_path_whose_hash_is_flagged_leaves_the_row_and_without_others_there_is_no_row"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_suggestions.py#test_events_older_than_a_day_are_ignored_and_the_row_closes_when_none_remain"
        status: pass
    human_judgment: false
  - id: D5
    description: "D-08: a file-change tick writes nothing to autonomy_signals, so a change is never an origin"
    requirement: "RESP-01"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_suggestions.py#test_a_file_change_tick_writes_no_signal_and_no_origin"
        status: pass
    human_judgment: false
---

# Phase 83 Plan 15: Vulnerability and file-change suggestions Summary

One quiet suggestion per computer for open vulnerabilities and one for changed files, refreshed in place by a new second sweep stage, so a computer reporting hundreds of findings can never bury a decision.

## What was built

- `backend/autonomous_ops/sweep_suggestions.py` (284 lines): `run` is the second entry in `sweep._STAGES`. For each kind it reads the findings, groups them by resolved computer (`signals.resolve`; an ambiguous hostname is skipped), and keeps at most one open `suggested` row per computer and kind under `{tenant}|sweep-suggest|{kind}|{agent}`.
- Vulnerabilities: open agent findings, with or without a CVE, read with a 5000 limit; the row carries `suggestion {kind, count, severity, items[<=10]}` and `suggestionOnly`. Items are `{cve, package}` sorted by severity then id, text cut to a length and stripped of control characters.
- File changes: `fim_events` with `change_type: Changed` in the last 24 hours, distinct paths per computer, items `{path}`. A path whose `hash_after` or `sha256` is an `autonomy_signals` file signal for that computer is left out.
- Refresh: an unchanged tick writes nothing; a change calls `ledger.refresh_suggestion` (no audit event, `createdAt` moves to the latest sweep); expiry is extended to 24 hours only when under 12 hours remain.
- Findings gone: the open row ends `expired`, reasonCode `superseded`. An unreadable findings list closes nothing.
- A never-touch computer: the gate records one `refused` row and the refusal is remembered 24 hours on the computer's signal memory. Shadow tenants get one simulation per computer and kind in 24 hours (the gate's own dedupe).

## Task commits

| Task | Commit | What |
|------|--------|------|
| 1 RED | 3a5b69dcf | test for the vulnerability behaviours (assertion failures: no row was written; not an ImportError) |
| 1 GREEN | 2e6967aa3 | `sweep_suggestions.py`, `_STAGES`, one sentence in `response_messages.py` |
| 2 RED | 88a8bfed2 | file-change tests (8 assertion failures) |
| 2 GREEN | a4b7c2938 | `file_change` group |

## Verification

- `backend/tests/test_autonomous_ops_suggestions.py`: 23 passed on the private mongod 27998, none skipped.
- Together with `test_autonomous_ops_sweep.py`, `_sweep_dedupe`, `_two_signal`, `_origins`, `_response_rows`, `_quarantine_decisions`, `_range_block`, `_incidents`, `_isolation`, `_gate`, `_structural` and `_copy`: all passed (285 and 282 in two runs).
- Not run: the full backend suite (run notes forbid it), the known `test_catalogue_route_parity` ratchet (unrelated).

## Deviations from Plan

### Auto-added

**1. [Rule 2 - Missing critical functionality] A wording for a suggestion that ended because its findings are gone**
- **Found during:** Task 1
- **Issue:** the only `superseded` sentence ("A second source agreed, so this suggestion became an action.") is false for this case.
- **Fix:** added `REASON_TEXT["suggestion_gone"]` in `response_messages.py` ("Nothing is reported on this computer any more, so this suggestion ended.") and used it as the row's `reasonText`; the reasonCode stays `superseded` as the plan asks.
- **Files modified:** `backend/autonomous_ops/response_messages.py`
- **User-visible sentence the UI-SPEC does not word:** that one. For a suggestion row `row_extras` replaces the reason with the count sentence, so it will show only where the stored text is used.

Otherwise the plan ran as written. The plan's "on a duplicate refusal, find the open row" is kept, and the open row is also looked up before the gate runs (see key-decisions).

## Known limits

- Counts past 5000 open vulnerabilities (or 2000 changed-file events) are cut at the read limit and a warning is logged (T-83-56). A count of 5000 can therefore mean "at least 5000".
- Nothing dismisses a suggestion: a person cannot deny it, and while the findings last the row is kept alive. Not a bug here, but the Activity screen (83-18) should not offer Deny on these rows.
- Not tested against a real agent or a real FIM/vulnerability feed; the field names come from the ingest code (`agent_vuln_ingest_service.py`, `agent_security_endpoints.py`) and the plan's notes.

## Files I did not read in full

83-RESEARCH.md (only Pattern 3 and the suggestion lines), 83-UI-SPEC.md (sections 4, 5 and the R-list only), 83-CONTEXT.md (decisions section read in full), 83-PATTERNS.md and 83-VALIDATION.md (not read).

## Cross-plan facts for the orchestrator

- Suggestion rows from this stage: ruleIds `sweep:suggest_vulnerability` and `sweep:suggest_file_change`, commands `upgrade_software` and `restore_file`, `reason.inputs.suggestion` `{kind, count, severity?, items}`, `suggestionOnly: true`, no `incidentId`. `row_extras` already renders them and adds `openView`.
- `autonomy_signals` can now hold documents of kind `vulnerability` or `file_change` (indicator = agent id, empty `origins`, only a refusal `decision`) for computers on the never-touch list. They are never candidates.
- Stage counts added to the tick: `refreshed`, `closed` (plus `suggested`, `shadow`, `refused`, `skipped`).

## Self-Check: PASSED

- backend/autonomous_ops/sweep_suggestions.py: found
- backend/tests/test_autonomous_ops_suggestions.py: found
- commits 3a5b69dcf, 2e6967aa3, 88a8bfed2 and a4b7c2938 on HEAD
