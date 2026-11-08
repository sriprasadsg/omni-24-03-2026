---
phase: 85-first-line-service-desk
plan: 11
subsystem: service-desk-settings
tags: [service-desk, settings, ledger, audit, breaker-restore, status-line, ollama, routes]
status: complete

requires: [85-01, 85-02, 85-03]
provides:
  - "service_desk.settings: SettingsError, PlatformTenantError, validate_word, validate_changes, save, restore, posting_blockers, status_view, CLIENT_FACTORY"
  - "control events service_desk_mode_changed, service_desk_words_changed, service_desk_restored (labels in autonomous_ops CONTROL_LABELS, reason lines in service_desk/messages CONTROL_REASONS)"
  - "GET and PUT /api/autonomous-ops/service-desk and POST /api/autonomous-ops/service-desk/restore (backend/autonomous_ops_service_desk_endpoints.py), mounted under the Autonomous Ops catalogue guard and listed in _REQUIRED_ROUTERS"
  - "copy gate: backend/service_desk_endpoints.py and backend/autonomous_ops_service_desk_endpoints.py on the files list and both EXPECTED_FILES lists"
affects: [85-12, 85-14, 85-17, 85-18, 85-19]

actuals:
  tokens: 15400
  tasks: 3
  commits: 3
plan_head_before: 886cf6d1c290c0e876c15bbf11546b1a68ee3b0a
plan_head_after: 49f6495b69c63c1fbe8c1491f8a44cc00183143c

tech-stack:
  added: []
  patterns:
    - "One control row and one audit event per value that really changed, naming the person; an unchanged save writes nothing (the Phase 83 response_settings pattern)"
    - "Post answers is checked twice: before the write, and again as a filter on the write itself (serviceDesk.breaker is absent), so a breaker trip that lands in between wins"
    - "Restore is one find_one_and_update on the stored breaker, so two people pressing it record one row; a control row that cannot be recorded puts the old values back"
    - "The status view reads the model through an injectable client (argument or module attribute CLIENT_FACTORY); tests only ever use httpx.MockTransport"

key-files:
  created:
    - backend/autonomous_ops_service_desk_endpoints.py
    - backend/tests/test_service_desk_settings.py
  modified:
    - backend/service_desk/settings.py
    - backend/service_desk/messages.py
    - backend/autonomous_ops/messages.py
    - backend/catalogue_mounts_autonomous_ops.py
    - backend/router_registry.py
    - backend/tests/test_catalogue_slice_autonomous_ops.py
    - shared/autonomous-ops-banned-terms.json
    - backend/tests/test_autonomous_ops_copy.py
    - src/__tests__/autonomousOpsCopy.test.ts

key-decisions:
  - "posting is True only when the saved mode is post, the Tickets and Knowledge Base screens are on and no blocker is unmet (the plan said 'only when saved mode is post and none is unmet'; adding the screens keeps the card from claiming Posting while effectiveMode is off)"
  - "timing.measured reads runtime.load_measurement (a valid service_desk_runtime document), so a malformed document reads not measured, the same as the timeouts treat it"
  - "A PUT with neither key (or only nulls) is accepted and records nothing instead of a 422; the three modes and the words are the only fields and the body refuses unknown ones"
  - "The router accepts the same optional tenantId as the Phase 83 settings routes, so a Super Admin can name an organization; the platform organization is 409 either way"

requirements-completed: [DESK-02, DESK-04, DESK-05]

coverage:
  - id: D1
    description: "Mode and words are validated at the API boundary (mode off/drafts/post; at most 50 words, 2-40 characters, allowed characters only, casefolded, de-duplicated) with the UI-SPEC sentences, 422 on refusal"
    requirement: "DESK-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_settings.py#test_the_mode_must_be_one_of_the_three; #test_words_are_trimmed_casefolded_and_checked_with_the_screen_sentences; #test_a_bad_word_is_422_with_the_screen_sentence_and_nothing_is_stored"
        status: pass
    human_judgment: false
  - id: D2
    description: "Each changed value writes one control row and one audit event naming the person; saving the current values writes nothing; a change that cannot be recorded is put back"
    requirement: "DESK-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_settings.py#test_a_mode_change_writes_one_control_row_and_one_audit_event_naming_the_person; #test_saving_the_current_values_writes_nothing; #test_a_words_change_writes_one_control_row; #test_a_change_that_cannot_be_recorded_is_put_back"
        status: pass
    human_judgment: false
  - id: D3
    description: "Post answers is refused 409 'Restore Post answers first.' while the desk breaker is stored; restore clears it, sets post and records service_desk_restored once"
    requirement: "DESK-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_settings.py#test_post_answers_is_refused_while_the_breaker_is_stored; #test_restore_clears_the_breaker_sets_post_and_records_once; #test_post_is_409_while_the_breaker_is_stored_and_restore_is_the_way_back"
        status: pass
    human_judgment: false
  - id: D4
    description: "The status view lists exactly the unmet conditions (level with its value, shadow, stop, hourly_limit at 20 desk answers in the servicedesk pool, desk_breaker) for Post answers only, and says posting only when none is unmet"
    requirement: "DESK-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_settings.py (post_with_suggest_level, deployment_master, all_conditions_met, tenant_and_platform_stop, unreadable_platform_stop, twenty_desk_answers, stored_breaker, drafts_and_off)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Model state is online only when the loopback client finds the exact tag (offline for any failure); timing is the median of the tenant's last 20 desk rows with genMs, None with samples 0 when there are none, measured only with a runtime document; the view is off when Tickets or Knowledge Base is switched off"
    requirement: "DESK-04"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_settings.py#test_the_model_is_online_only_for_the_exact_tag; #test_the_typical_answer_time_is_the_median_of_the_last_twenty_rows; #test_only_the_newest_twenty_count; #test_a_runtime_document_makes_the_timing_measured; #test_a_tenant_without_the_knowledge_base_screen_is_off"
        status: pass
    human_judgment: false
  - id: D6
    description: "The three routes need manage:autonomous_ops in a signed-in session (view-only roles, API keys and Platform Support get 403), the Platform tenant gets 409, the router is under the autonomousOps guard and required at startup, and both desk endpoint files are on the copy gate"
    requirement: "DESK-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_settings.py#test_the_role_matrix_on_the_real_app; #test_a_view_only_role_an_api_key_and_platform_support_are_refused; #test_the_platform_tenant_is_409_on_all_three; backend/tests/test_catalogue_slice_autonomous_ops.py; backend/tests/test_autonomous_ops_copy.py; src/__tests__/autonomousOpsCopy.test.ts"
        status: pass
    human_judgment: false
---

# Phase 85 Plan 11: The service desk's own switch, words, restore and status line Summary

A tenant admin can now read and change the desk's Off / Drafts only / Post answers switch and their own hand-off words, restore Post answers after the breaker, and see an honest status line (why answers are or are not posted, whether the local model runs, the typical answer time), all through three guarded, required, audited routes.

Duration: about 25 minutes (20:27 to 20:52 UTC). Tasks: 3. Files: 11 (2 created, 9 modified). Completed 2026-11-08.

## Accomplishments

- **Task 1, settings (ec9b0b183).** `service_desk/settings.py` gained `SettingsError`, `PlatformTenantError`, `validate_word`, `validate_changes`, `save` and `restore`. Words are trimmed, inner spaces collapsed, casefolded and de-duplicated (letters and digits of any script, plus space, hyphen, apostrophe, ampersand, slash and dot, 2 to 40 characters, at most 50). `save` writes one control row and one audit event per changed value naming the person, nothing for an unchanged save, and puts the old values back if a row cannot be recorded. Post answers is refused while a breaker is stored, and the check is repeated as a filter on the write. `restore` is one atomic update, so two presses record one row.
- **Task 2, status view (339dcc2af).** `status_view` builds the `DeskSettingsView` shape of `services/serviceDesk/types.ts`: mode and effectiveMode (off while Tickets or Knowledge Base is switched off), readable, screensOn, words, maxWords, breaker {trippedAt, count}, posting {posting, blockers}, model {state, tag}, timing {medianSeconds, samples, measured}, canManage, canRestore. Blockers are listed in the order level (with the level value), shadow, stop, hourly_limit (20 in the last hour, the servicedesk pool), desk_breaker, and only for Post answers. An unreadable platform stop counts as stopped and an unreadable ledger counts as the limit reached (fail closed).
- **Task 3, routes (49f6495b6).** `autonomous_ops_service_desk_endpoints.py` has GET and PUT `/api/autonomous-ops/service-desk` and POST `.../restore`, each behind `_require_manage` and `_require_interactive_session`; 409 for the platform organization, the breaker and "nothing to restore", 422 for any other refused value. Mounted in `MOUNTS` under the Autonomous Ops guard, loaded next to the Phase 83 routers and listed in `_REQUIRED_ROUTERS`. The two desk endpoint files are on the copy gate's files list and both `EXPECTED_FILES` lists.

## Task Commits

| Task | Commit | Type | Description |
| ---- | ------ | ---- | ----------- |
| 1 | ec9b0b183 | feat | Validate, save and restore the desk settings, recorded in the ledger |
| 2 | 339dcc2af | feat | The desk status view: readiness blockers, model status and typical answer time |
| 3 | 49f6495b6 | feat | The settings routes, mounted, required and on the copy gate |

Plan type `execute` with tasks marked `tdd="true"`: as in 85-01 to 85-03, tests and implementation were written together and committed together for each task.

## Verification

- Task 1 and 2 command (`test_service_desk_settings.py`): 41 passed after task 3, no skips (14 after task 1, 33 after task 2).
- Task 3 command (settings, catalogue slice, route parity, route-auth baseline, copy): 150 passed, no skips. `npx vitest run src/__tests__/autonomousOpsCopy.test.ts`: 23 passed.
- Regression run: structural tests for desk and Autonomous Ops, router registry, router smoke, tenant screen routes, response endpoints, desk ledger, tracer and intake: 137 passed.
- Acceptance greps: `def validate_changes|def save|def restore` 3; `def status_view` 1; `hourly_limit|desk_breaker` in settings.py 4; `autonomous_ops_service_desk_endpoints` in router_registry.py 2 and in catalogue_mounts_autonomous_ops.py 1; `service_desk_endpoints.py` in the banned-terms JSON 2. settings.py is 375 lines, the endpoint file 128.
- Mutation check run by hand: removing the breaker refusal (both the early check and the write filter) made `test_post_answers_is_refused_while_the_breaker_is_stored` fail; the file was restored from a copy before committing.
- Every database test used the private mongod on 27998; the model was only ever an `httpx.MockTransport`, and a test asserts the status line sends one `GET /api/tags` and never a generate request and nothing to a non-loopback host.

## Existing tests whose expectation changed

- `test_catalogue_slice_autonomous_ops.py`: the MOUNTS equality, the walk's module list and a new required-router test now include the desk router (as the plan named).
- `test_autonomous_ops_copy.py` and `autonomousOpsCopy.test.ts`: `EXPECTED_FILES` gains the two desk endpoint files (as the plan named).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical] Control labels and messages for the three new events**
- **Found during:** Task 1
- **Issue:** The Activity list shows `Control event` for a control row whose event has no label, and `SettingsError` needed keys (`mode_invalid`, `not_tripped`) that `API_DETAIL` did not have.
- **Fix:** Added the three labels to `autonomous_ops/messages.CONTROL_LABELS` (declared once there; service_desk imports autonomous_ops, never the reverse), and `mode_invalid`, `not_tripped`, `MODE_LABELS` and `CONTROL_REASONS` to `service_desk/messages.py`.
- **Files modified:** backend/autonomous_ops/messages.py, backend/service_desk/messages.py (neither is on the plan's files list; neither carried user changes)
- **Commit:** ec9b0b183

**2. [Rule 2 - Test seam] `CLIENT_FACTORY` module attribute on the status view**
- **Found during:** Task 3
- **Issue:** The routes build the view without a factory, so a route test would have reached the real loopback Ollama.
- **Fix:** `settings.CLIENT_FACTORY` (None in production) is used when no factory argument is given; the route tests set it to a mock-transport client.
- **Commit:** 49f6495b6

**Total deviations:** 2 auto-fixed (both Rule 2). **Impact:** none on scope; no architectural change.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register. T-85-38 (manage plus interactive session, API key and Platform Support refused, real-app role probe), T-85-39 (count, length and character allow-list at the API), T-85-40 (one control row and audit event per change naming the person) and T-85-41 (probe bounded by the 2 s timeout and the 15 s availability cache) are covered by tests. T-85-SC accepted: no package installed.

## User WIP preserved

None of this plan's files carried user changes. `backend/tests/test_router_registry_required.py` (an import-style edit I did not make) and `shared/catalogue-gaps.json` show as modified in the working tree; both were left untouched and unstaged.

## Hand-over for later plans

- **85-14 (settings card):** consume `GET/PUT /api/autonomous-ops/service-desk` and `POST .../restore`; every field of `DeskSettingsView` is returned, `model.tag` is returned also when offline, and `breaker.trippedAt` is an ISO string. A PUT may carry either key or both and returns the same view as GET.
- **85-18 (desk breaker):** the breaker is the dict `{trippedAt, actionIds}` under `autonomy_settings.serviceDesk.breaker` with `serviceDesk.mode` set to `drafts` by the trip; `restore` clears it and sets `post`, and `save` refuses `post` while it is stored.
- **Activity list:** control rows carry `controlEvent` service_desk_mode_changed, service_desk_words_changed or service_desk_restored with labels and reason lines.
- Words are stored casefolded; `rules._tenant_hit` normalises both sides anyway.

## User steps

None for this plan. Not done, by design: restart of the backend (the new routes go live on the user's next restart; the router is required, so a broken import would stop startup), UI publish, git push, writing to the live database.

## Self-Check: PASSED

- Files: `backend/autonomous_ops_service_desk_endpoints.py`, `backend/tests/test_service_desk_settings.py` and all nine modified files exist and are committed.
- Commits ec9b0b183, 339dcc2af and 49f6495b6 are ancestors of HEAD; `git rev-list --count` from the recorded base gives 3.
- All `<acceptance_criteria>` of the three tasks and the plan-level verification were re-run and pass.
