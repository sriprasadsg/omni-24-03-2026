---
phase: 85-first-line-service-desk
plan: 09
subsystem: service-desk
tags: [service-desk, intake, raised-via, tray, eligibility, tickets]
status: complete

requires: [85-01, 85-02]
provides:
  - "intake.tray_claim(tags, endpoint_info) and intake.legacy_template(title): the legacy tray rule and the title-prefix template, both pure"
  - "POST /api/agents/{id}/raise-ticket stamps raised_via portal_agent (requester_channel.portal True) only for a signed-in person who is not an agent identity or an API key; everything else is automation"
  - "POST /api/agents/{id}/ticket stamps raised_via tray (requester_channel tray True, myTickets False, windowsUser, template) only when the request's own tags and endpoint_info satisfy the rule, decided before agent-raised is appended; everything else is automation"
  - "intake.on_ticket_created refuses (no job, no ledger row) when the effective level is Off, a tenant or platform stop is on (an unreadable platform stop counts as on), or the Tickets or Knowledge Base screen is switched off"
  - "tests/test_service_desk_intake.py: 32 cases covering every creation path and every refusal"
affects: [85-10, 85-17, 85-19]

actuals:
  tokens: 19000
  tasks: 2
  commits: 2
plan_head_before: b957e493e8ec2405def60abce7e683923045c0d7
plan_head_after: 62ee84d79515179dee9a3c0d630726918c24b856

tech-stack:
  added: []
  patterns:
    - "Who raised a ticket is decided from the authenticated identity and the route, never from a body field; the tray's tags are only a claim and a spoofed claim can only produce a draft (myTickets False)"
    - "Refusals in intake are silent and leave no trace: no job, no ledger row, a debug log line"

key-files:
  created:
    - backend/tests/test_service_desk_intake.py
  modified:
    - backend/agent_tasks_endpoints.py
    - backend/service_desk/intake.py
    - backend/tests/service_desk_support.py

key-decisions:
  - "The agent route file takes a top-level import of service_desk.intake (not a lazy one) so the two call sites stay at four lines each; the import works without a circle"
  - "A platform stop that cannot be read counts as on and the desk queues nothing; a tenant whose features cannot be read counts as screens off"
  - "A tray claim is matched case-insensitively on tags and the Windows user name is stripped and capped at 200 characters"

requirements-completed: []

coverage:
  - id: D1
    description: "raise-ticket: a signed-in person is portal_agent and queued; an agent identity, an API key and a body that claims otherwise are automation and not queued"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_intake.py#test_raise_ticket_by_a_signed_in_person_is_portal_agent_and_queued; #test_raise_ticket_by_an_agent_identity_is_automation_and_not_queued; #test_raise_ticket_by_an_api_key_is_automation_and_not_queued; #test_a_body_field_cannot_claim_a_person_raised_it"
        status: pass
    human_judgment: false
  - id: D2
    description: "Legacy /ticket: tray tags plus a Windows user name give tray with the channel and template and a job; a missing endpoint_info, an empty user, a lone user-raised tag, the Rust agent's tags and a claim that also says agent-raised are automation with no job"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_intake.py (legacy_tray_ticket_*, the_rust_agents_create_ticket_instruction, a_tray_claim_that_also_says_agent_raised, tray_claim_needs_lists_and_a_dict)"
        status: pass
    human_judgment: false
  - id: D3
    description: "An older tray's title prefix names its template, case-insensitively; an edited prefix is custom"
    requirement: "DESK-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_intake.py#test_legacy_template_from_the_title_prefix (8 titles); #test_a_stored_legacy_tray_ticket_carries_its_template"
        status: pass
    human_judgment: false
  - id: D4
    description: "Level Off, a tenant stop, a platform stop, an unreadable platform stop, either ticket screen switched off, and the desk set to Off each give no job and no ledger row; level Suggest and an inactive stop still queue; a ticket created without raised_via stays automation and is never queued"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_intake.py (level_off, tenant_stop, platform_stop, unreadable_platform_stop, switched_off_screen x2, desk_set_to_off, level_suggest_still_enqueues, stop_that_is_not_active, ticket_created_without_raised_via)"
        status: pass
    human_judgment: false
---

# Phase 85 Plan 09: Who raised it, and who gets an attempt Summary

Both agent-side ticket routes now decide on the server whether a person raised the ticket (the tray claim is the request's own tags plus a Windows user name, the signed-in route requires a session user who is not an agent), an older tray's title prefix names its template, and intake queues a ticket only in a tenant whose level is above Off, with no stop on, and with the Tickets and Knowledge Base screens switched on.

Duration: about 12 minutes (20:19 to 20:31 UTC). Tasks: 2. Files: 4 (1 created, 3 modified). Completed 2026-11-08.

## Accomplishments

- **Task 1 (5c114a712).** `intake.tray_claim` returns the Windows user name only when the tags (case-insensitive) hold `tray` and `user-raised`, do not hold `agent-raised`, and `endpoint_info.username` is a non-empty string. `intake.legacy_template` reads `tray_contract.LEGACY_TITLE_PREFIXES` with a casefolded prefix match, else `custom`. `raise_ticket_via_agent` stamps `portal_agent` with `{portal: True}` only when the caller's role is not `agent` and `views.is_interactive` holds; `create_ticket_from_agent` computes the claim from `body.tags` before the route appends `agent-raised` and stamps `tray` with `{tray True, myTickets False, windowsUser, template}`. Both call `on_ticket_created` inside try/except that only logs. The `agent_instructions` write in raise-ticket was not touched and no queue write was added.
- **Task 2 (62ee84d79).** `on_ticket_created` now also requires `effective_level != off`, no active tenant stop, no active platform stop (a read failure counts as active), and neither `screen:internalTickets` nor `screen:knowledgeBase` in `tenant_features.switched_off(enabledFeatures)`. Each refusal logs at debug and returns None; nothing is recorded.
- **Tests.** 32 cases in one file: 4 on raise-ticket, 6 on the legacy route, 8 title cases plus 2 on non-text titles and the stored template, and 12 on eligibility. Mutation check by hand (each restored before committing): a stop check that always says no, a screens check that always says yes, the level check removed, the `agent-raised` exclusion removed, and the agent-role exclusion removed each made at least one test fail.

## Task Commits

| Task | Commit | Type | Description |
| ---- | ------ | ---- | ----------- |
| 1 | 5c114a712 | feat | The server decides who raised a ticket on both agent routes |
| 2 | 62ee84d79 | feat | Intake refuses a stopped, Off or screen-less tenant |

Plan tasks are `tdd="true"`; as in earlier plans the tests and implementation of each task were written together and committed together. Task 1's commit holds only its own tests and Task 2's commit adds the eligibility tests.

## Verification

- Task 1 command (intake, catalogue slice agents): 24 passed, no skips (run against the Task 1 state of the files, before Task 2's code was restored).
- Task 2 command and the plan-level checks together (intake, tracer, `test_autonomous_ops_copy`, `test_service_desk_structural`, `test_catalogue_slice_agents`): 99 passed, no skips. Also `test_service_desk_comments`, `_gate`, `_ledger`: 84 passed.
- Acceptance greps: `on_ticket_created` in agent_tasks_endpoints.py 2; `def tray_claim|def legacy_template` in intake.py 2; `switched_off` 1; `platform_stop` 1. Each refusal case asserts both `service_desk_jobs` and `autonomy_actions` are empty (`_no_trace`).
- Every DB test used the private mongod on 27998; no live database, no real Ollama.
- `intake.py` is 120 lines and the new test 260; `agent_tasks_endpoints.py` was 522 lines and is 551 (it was already over 500; only the stamping and the two call sites were added).

## Deviations from Plan

**1. [Rule 3 - Blocking] The Knowledge Base screen needs its parent switch**
- **Found during:** Task 2
- **Issue:** `tenant_features.switched_off` treats `screen:knowledgeBase` as off unless its parent `manage:settings` is also in `enabledFeatures` (`screen:internalTickets` has no parent). `tests/service_desk_support.seed_desk_tenant` ticked only the two screens, so once intake applied the plan's screen rule the 85-01 tracer tests and the new positive cases found no job.
- **Fix:** `seed_desk_tenant` also ticks `manage:settings`. The production rule is the plan's (`switched_off`), unchanged.
- **Files modified:** `backend/tests/service_desk_support.py` (not in the plan's file list; a test-only helper)
- **Commit:** 62ee84d79

**Total deviations:** 1 auto-fixed (1 blocking). **Impact:** none on production code.

## Notes for later plans

- **85-19 (new tray route).** Not touched; it stamps `tray` by route identity and reads `myTickets` from `client.features`. The legacy route's `requester_channel` carries `myTickets False` and a `template`, so the pipeline can already treat an old tray's ticket as draft-only.
- **Real tenants.** A tenant that has the Knowledge Base screen ticked but not Settings (`manage:settings`) is treated as screen-off and its tickets get no attempt, by the same rule the sidebar uses. Worth knowing when a tenant reports "the desk never answers".
- **The desk setting is read once.** Intake reads the desk mode, then the Autonomous Ops settings, then the platform stop, then the tenant document: four reads per person-raised ticket, all uncached by design.

## User WIP preserved

None of this plan's files carried user changes (confirmed with `git diff --numstat` before editing). `backend/tickets_endpoints.py` still shows the user's uncommitted hunks and was not touched or staged.

## User steps

None. Not done, by design: restart of the backend (both agent routes go live on the user's next restart), publishing, push.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register (T-85-30 to T-85-33 are mitigated by the tests named under coverage D1 to D4).

## Self-Check: PASSED

- Files: `backend/tests/test_service_desk_intake.py` exists; the 3 modified files are committed; 5c114a712 and 62ee84d79 are ancestors of HEAD.
- All `<acceptance_criteria>` of both tasks re-run and pass (see Verification). The plan's `requirements` (DESK-01, DESK-02) are deliberately not marked Complete by this plan.
