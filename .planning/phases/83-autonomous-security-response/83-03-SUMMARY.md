---
phase: 83-autonomous-security-response
plan: 03
subsystem: autonomous-ops
tags: [autonomous-ops, copy, activity-rows, undo, banned-terms, pytest]

requires:
  - phase: 83-autonomous-security-response
    provides: "83-01 tracer: security_response rows with blockedFrom/blockedUntil, instructionIds, reason.inputs.origins"
provides:
  - backend/autonomous_ops/response_messages.py, the one module holding every Phase 83 server sentence
  - backend/autonomous_ops/response_views.py (row_extras), the wider Activity row payload
  - canUndo, undoHint, incidentId, blockedUntil, suggestion on every Activity row of the existing routes
  - FENCE texts for the swarm, SOAR, worker and swarm-mission paths (used by 83-06)
affects: [83-04, 83-05, 83-06, 83-07, 83-11, 83-16, 83-18, 83-19]

actuals:
  tokens: 14000
  tasks: 2
  commits: 4
plan_head_before: e083bd748ca97d1c1735c1e7bb248c56db85da85
plan_head_after: 251f23b417ac739f905c1cce7d72038f77c39bb8

tech-stack:
  added: []
  patterns:
    - "Server copy is rendered from reason.inputs at read time, so a refreshed row never shows stale words; a row with no inputs keeps its stored text"
    - "fill(template, **tokens) replaces only the tokens it is given, so {until} and {at} stay literal for the browser"
    - "canUndo is display only; approvals.undo and the route permission check remain the guard"

key-files:
  created:
    - backend/autonomous_ops/response_messages.py
    - backend/autonomous_ops/response_views.py
    - backend/tests/test_autonomous_ops_response_rows.py
  modified:
    - backend/autonomous_ops/messages.py
    - backend/autonomous_ops/views.py
    - backend/autonomous_ops_endpoints.py
    - shared/autonomous-ops-banned-terms.json
    - backend/tests/test_autonomous_ops_copy.py
    - src/__tests__/autonomousOpsCopy.test.ts

key-decisions:
  - "Row outcome wording (block active or expired, quarantine, isolation, restart) is overridden only for dispatcher security_response rows; Phase 81 rows keep their stored text and results"
  - "The agent's healthy_after and still_running are read from row.result (the bounded verify result), so the plan that stores them must write them there"
  - "Block active reads Verified only on a verified row; an executed row whose verify has not arrived claims nothing"
  - "A block row keeps state, chip and ledger row unchanged after blockedUntil: only canUndo and the result text change at read time"

patterns-established:
  - "Stable payload keys: canUndo false, undoHint/incidentId/blockedUntil/suggestion null for rows with nothing to say"
  - "Origin names raise KeyError for an unknown id; row_extras catches it and falls back to the stored wording so a raw id is never shown"

requirements-completed: [ACTV-02, RESP-02, RESP-03, RESP-08]

coverage:
  - id: D1
    description: "Every Phase 83 server sentence lives in response_messages.py, on the copy gate (JSON list and both test lists), and passes the banned-terms rules with no markup"
    requirement: "RESP-08"
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_copy.py#test_every_string_in_the_module_passes_the_rules_and_holds_no_html"
        status: pass
      - kind: unit
        ref: "src/__tests__/autonomousOpsCopy.test.ts"
        status: pass
    human_judgment: false
  - id: D2
    description: "why_two_sources refuses fewer than two different origin ids, sorts the shown names, and an unknown origin id raises KeyError and is never shown"
    requirement: "RESP-08"
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_copy.py#test_two_sources_sentence_needs_two_different_origins_and_sorts_the_names"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_response_rows.py#test_two_entries_from_one_origin_never_read_as_two_sources_and_an_unknown_origin_is_never_shown"
        status: pass
    human_judgment: false
  - id: D3
    description: "An active block row reads Blocked for {length}, until {until} with the literal token; after blockedUntil it reads Block removed automatically at {at} with state, bucket and ledger row unchanged and Undo gone"
    requirement: "RESP-02"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_response_rows.py#test_a_block_past_its_time_reads_as_removed_on_the_route_without_changing_state"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_response_rows.py#test_a_block_whose_time_ran_out_loses_undo_and_keeps_its_state"
        status: pass
    human_judgment: false
  - id: D4
    description: "A verified quarantine reads Moved {path} to quarantine. It was not deleted. Verified: the file is in quarantine."
    requirement: "RESP-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_response_rows.py#test_quarantine_and_isolation_rows_offer_their_own_undo_hint"
        status: pass
    human_judgment: false
  - id: D5
    description: "canUndo is true only for a registered undo, state executed or verified, one step, not simulated, a target, not past blockedUntil, and a viewer holding control:autonomous_ops in an interactive session; Platform Support, an API key and a view-only role always get false"
    requirement: "ACTV-02"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_response_rows.py#test_the_activity_route_offers_undo_only_to_a_person_who_may_use_it"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_response_rows.py#test_rows_that_cannot_be_undone_get_false_and_no_hint"
        status: pass
    human_judgment: false
  - id: D6
    description: "Suggestion rows are labelled from reason.inputs.suggestion, class line Suggestion only, grouped with at most 10 items and an openView (patchManagement, fimMonitoring); an old row presents as before with the new keys empty"
    requirement: "RESP-08"
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_response_rows.py#test_a_vulnerability_suggestion_is_grouped_capped_and_links_to_patching"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_response_rows.py#test_an_old_row_presents_as_before_with_the_new_keys_empty"
        status: pass
    human_judgment: false
  - id: D7
    description: "The sentences read well and match the screen in a real browser"
    requirement: "ACTV-02"
    verification: []
    human_judgment: true
    rationale: "Wording was copied from 83-UI-SPEC and checked by string equality in tests; how it reads in the Activity list belongs to the UI plans (83-18, 83-19) and UAT."

duration: 25min
completed: 2026-11-01
status: complete
---

# Phase 83 Plan 03: Every new row sentence in one module, and which rows can be undone

**All Phase 83 server wording now lives in `response_messages.py` (on the banned-terms gate), and `response_views.row_extras` gives each Activity row `canUndo`, `undoHint`, `incidentId`, `blockedUntil` and `suggestion` plus wording rendered from `reason.inputs`, so the browser infers nothing.**

## Performance

- **Duration:** 25 min
- **Tasks:** 2 (both TDD)
- **Commits:** 4 (2 test, 2 feat), measured from `e083bd748` to `251f23b41`
- **Line counts:** `views.py` 406 (below 450), `autonomous_ops_endpoints.py` 449 (below 455), `response_messages.py` 248, `response_views.py` 241

## Task Commits

| Task | Commit | Type |
|------|--------|------|
| 1 RED: copy module tests, gate list | `991bf4891` | test |
| 1 Every server sentence in one module | `1a42f5bd8` | feat |
| 2 RED: row copy, canUndo, suggestions | `881e99b94` | test |
| 2 Rows say what happened and which can be undone | `251f23b41` | feat |

## Keys in `response_messages.py` (for later plans to cite)

Constants (dict keys):

- `ORIGIN_NAMES`: native, feed:urlhaus, feed:malwarebazaar, feed:otx, virustotal, onhost
- `CLAIM_LABELS`: unblock_ip, unquarantine_file, restore_host
- `WHAT_HAPPENS`: kill_process, isolate_host, reboot_host, restart_over_budget ({service}), kill_then_quarantine, protected_file
- `NOTICES` (plain strings): kill_then_quarantine, kill_only
- `UNDO_HINTS`: unblock_ip ({ip}), unquarantine_file ({path}), restore_host; `UNDO_HINTS_PLAIN`: unblock_ip, unquarantine_file (used when the row names no address or path)
- `RESULT_TEMPLATES`: block_active ({length}, literal {until}), block_expired (literal {at}), block_check_failed, quarantine_done ({path}), quarantine_still_running, restart_done ({service}, {seconds}, {attempt}), isolation_done ({host}), isolation_reverted, suggestion_vulnerability, suggestion_file_change, suggestion_one_source, suggestion_correlation, not_repeated, nothing_done
- `WHY_TEMPLATES`: two_sources ({first}, {second}), rule_off ({origin}), one_source ({origin}), restart_watched ({service}), restart_over_budget ({service}), protected_file ({reason}), undone_earlier ({date}), agent_cannot, os_cannot ({os}), correlation ({rule}), vulnerability ({n}, {noun}, {host}, {severity}), file_change ({n}, {noun}, {host})
- `SUGGESTION_LABELS`: block_ip, quarantine_file, isolate_host, vulnerability, file_change; `SUGGESTION_CLASS_LINE` = Suggestion only; `SUGGESTION_VIEWS`: vulnerability -> patchManagement, file_change -> fimMonitoring
- `FENCE`: swarm (exact UI-SPEC text), soar, worker, swarm_mission
- `REASON_TEXT` additions: agent_unsupported, capability_off, agent_offline, range_block, superseded, hash_mismatch, locked, protected_path, blocked_by_local_security, suggestion_only, auto_reverted, undo_failed
- `CONTROL_LABELS` additions: two_signal_on, two_signal_off, block_length_changed, watched_services_changed
- `API_DETAIL` additions: suggestion_only, already_confirmed, not_isolated, revert_passed, invalid_service, invalid_block_length

Functions: `fill(template, **tokens)`, `origin_name(id)` (KeyError on unknown), `why_two_sources(ids)` (ValueError under two different ids, sorted shown names), `why_one_source(id)`, `why_rule_off(id)`, `why_vulnerabilities(n, host, severity)`, `why_file_changes(n, host)`, `vulnerabilities(n)`, `files(n)`, `short_date(value)` (Mon D, UTC), `length_text(seconds)` (whole days from 2 days, else hours), `undo_hint(undo_command, ip=, path=)`, `what_happens(key, **tokens)`.

`messages.py` now merges `REASON_TEXT`, `CONTROL_LABELS` and `API_DETAIL` from the module, and `ACTION_LABELS` reads Kill process, Isolate host, Reboot host.

## Row contract for later plans (`response_views.row_extras`)

`reason.inputs` keys read: `origins`, `twoSignal`, `suggestion` ({kind: single_signal | vulnerability | file_change | correlation, count, severity, rule, items}), `suggestionOnly`, `incidentId`, `service`, `attempt`, `overBudget`, `protectedPath`, `detail`, `undoneAt`. Row fields read: `blockedFrom`, `blockedUntil`, `result.healthy_after`, `result.still_running`. Vulnerability items are `{cve, package}`, file-change items `{path}`; other keys are dropped and each value is capped at 300 characters. Wording and outcome overrides apply to `dispatcher == security_response` rows only; suggestion wording applies to any row that carries a valid `reason.inputs.suggestion`.

## Deviations from Plan

### Auto-fixed Issues

None needed fixing. One item the plan did not spell out, recorded as a choice:

**1. [Rule 2 - Missing critical] Text for reason codes the UI-SPEC does not word**
- **Found during:** Task 1
- **Issue:** the plan asks for `REASON_TEXT` entries for capability_off, agent_offline, range_block, superseded, hash_mismatch, locked, protected_path, blocked_by_local_security, suggestion_only, undo_failed, and `API_DETAIL` entries for suggestion_only, already_confirmed, not_isolated, revert_passed. The UI-SPEC words none of them, but a code with no text would show nothing.
- **Fix:** short plain sentences written for each (the UI-SPEC wording is reused for agent_unsupported, auto_reverted and invalid_service / invalid_block_length). The rule_off sentence is the one the plan authorises. These ten wordings are mine and should be read by the user.
- **Files modified:** `backend/autonomous_ops/response_messages.py`
- **Commit:** `1a42f5bd8`

### Plan departures that are choices, not fixes

- Platform-health rows are left exactly as they were (they do not gain the five new keys); the UI treats a missing key as empty.
- The vulnerability and file-change why templates take `{n}` and `{noun}` so one and many read correctly; two small helpers (`why_vulnerabilities`, `why_file_changes`) fill them.
- RED evidence: both RED runs failed by `ImportError` on the new module plus the file-list assertion, which the strict RED classifier would call `fixture_or_load_failure` (every module under test is new). No `gsd_run check tdd-red-evidence` record was produced.

**Total deviations:** 1 (missing-critical wording), 3 choices. **Impact:** none on the plan's truths.

## Verification Results

- Task 1: `test_autonomous_ops_copy.py` 27 passed; `npx vitest run src/__tests__/autonomousOpsCopy.test.ts` 18 passed. Neighbours (endpoints, gate, approvals, structural) 94 passed.
- Task 2 command (rows, endpoints, endpoint writes, copy) on the private mongod 27998: 77 passed, 0 skipped.
- Regression: platform health activity, catalogue slice, structural, permissions, block contract: 128 passed.
- Acceptance greps: `response_messages.py` appears once in the JSON and in each test list; the swarm sentence once; `Two sources agree` once; `row_extras` twice in `views.py`; `can_act` twice in `autonomous_ops_endpoints.py`.
- Phase 81 and 82 Activity row tests pass with no assertion edited.
- Not read in full: `83-CONTEXT.md` (read the decision lines D-03, D-06, D-07, D-08, D-11, D-14, D-18, D-24, D-25, D-27, D-28 only), `83-RESEARCH.md`, `83-VALIDATION.md`, `.planning/PROJECT.md`, and `STATE.md` outside the frontmatter and tail.

## Known Limitations (carried forward, not stubs)

- `response_views` reads `result.healthy_after` and `result.still_running` from the row. `verify.settle` stores neither today (it keeps `verify` and `outcome` only), so restart and still-running wording appears once the plan that records them (83-04 restart, 83-09 kill-then-quarantine) writes them into `row.result`.
- `reason.inputs.suggestion` and `incidentId` are produced by 83-05 and 83-11; until then no live row carries them.
- `undoHint` and Undo are offered for any registered undo; `enable_service` and `rotate_key_rollback` have no hint (Undo shows without one).

## Known Stubs

None.

## Threat Flags

None. No new network surface; the row payload gains fields on existing routes. T-83-09 (plain strings, caps), T-83-10 (canUndo display only, Platform Support / API key false) and T-83-11 (`why_two_sources` refuses one origin) are covered by tests.

## Self-Check: PASSED

Created files exist on disk (`response_messages.py`, `response_views.py`, `test_autonomous_ops_response_rows.py`, this summary) and commits `991bf4891`, `1a42f5bd8`, `881e99b94`, `251f23b41` are ancestors of HEAD (verified below the write).
