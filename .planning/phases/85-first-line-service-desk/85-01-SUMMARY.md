---
phase: 85-first-line-service-desk
plan: 01
subsystem: service-desk
tags: [service-desk, tracer, gate, retrieval, ollama, tickets, requester-view]
status: complete

requires: [85-03]
provides:
  - "backend/service_desk package: constants (__init__), settings, store (collections and every desk index), intake, sanitize, retrieval, model (loopback-only Ollama client), checks, ticket_writes, projection, pipeline, worker"
  - "POST /api/tickets stamps raised_via (portal or automation) and requester_channel from the session and queues one service_desk_jobs document per person-raised ticket"
  - "GET /api/tickets/{ticket_id}/service-desk: the requester view (reporter only; others get no requester block; other tenants get 404)"
  - "ticket document fields raised_via, requester_channel, desk; comment fields visibility, kind, ai"
  - "tests/service_desk_support.py: seed_desk_tenant, seed_article, ollama_transport, portal_user, desk_app"
affects: [85-04, 85-05, 85-06, 85-07, 85-09, 85-13, 85-14, 85-17]

actuals:
  tokens: 17800
  tasks: 2
  commits: 2
plan_head_before: f116c3d677a74d45b0ce82ee347af4fd0a97d632
plan_head_after: 5af3c07a0ad31eb8a9805cf9376587cb94edde9b

tech-stack:
  added: []
  patterns:
    - "Decision after generation: probe the model, ask once, check the reply, then gate.decide, so a stop during the slow call is honoured at posting time"
    - "Every desk read and write goes through the raw handle with an explicit tenantId; each ticket write is one filtered update (comment idempotent on comment id, status compare-and-set)"
    - "A client built for a non-loopback host refuses every call without sending; the model tag must match exactly"

key-files:
  created:
    - backend/service_desk/__init__.py
    - backend/service_desk/settings.py
    - backend/service_desk/store.py
    - backend/service_desk/intake.py
    - backend/service_desk/sanitize.py
    - backend/service_desk/retrieval.py
    - backend/service_desk/model.py
    - backend/service_desk/checks.py
    - backend/service_desk/ticket_writes.py
    - backend/service_desk/projection.py
    - backend/service_desk/pipeline.py
    - backend/service_desk/worker.py
    - backend/service_desk_endpoints.py
    - backend/tests/service_desk_support.py
    - backend/tests/test_service_desk_tracer.py
  modified:
    - backend/tickets_service.py
    - backend/tickets_endpoints.py
    - backend/router_registry.py

key-decisions:
  - "The tickets_endpoints.py hooks use lazy imports inside create_ticket so the committed hunks stay apart from the user's attachment hunks; a failure in either hook falls back to automation / no job and never fails the ticket"
  - "raised_via is validated in create_ticket against service_desk.RAISED_VIA (stdlib-only constants) and falls back to automation for anything else"
  - "Reply checks in this plan are the citation rule plus length (parse by pydantic strict types); the markup, link, address, phone, command and number rules are 85-06"

requirements-completed: [DESK-01, DESK-04, DESK-05]

coverage:
  - id: D1
    description: "A portal ticket is stamped raised_via portal, queued once, answered from the tenant's own Help desk article through gate.decide (dispatcher service_desk, targets [], desk subdocument on the row), posted as a requester-visible ai_answer with the ticket held at pending_customer, and read back by the reporter only"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_tracer.py#test_a_portal_ticket_is_stamped_queued_answered_through_the_gate_and_read_back; #test_the_requester_reads_the_answer_back_and_nobody_else_does"
        status: pass
    human_judgment: false
  - id: D2
    description: "With no serviceDesk setting stored the same ticket ends with a suggested row (suggestionOnly True), a staff-only ai_draft comment, the status still open and nothing for the requester"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_tracer.py#test_with_nothing_stored_the_desk_drafts_for_staff_and_the_requester_sees_nothing"
        status: pass
    human_judgment: false
  - id: D3
    description: "API key, Off, unticked and Platform tickets never get a job; the body cannot set raised_via; one attempt per ticket"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_tracer.py (api_key, body field, mode off, unticked, platform, queued once)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Global, foreign and non-Help-desk articles are never candidates; an unreachable, wrong-tag or non-loopback model sends no generate request and writes no row; an uncited or mis-shaped reply writes no row"
    requirement: "DESK-04"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_tracer.py (only_the_tenants_own_help_desk_articles, cannot_be_reached, different_model_tag, non_loopback_host, look_alike_name, cites_an_article_it_was_not_given, not_the_agreed_shape)"
        status: pass
    human_judgment: false
  - id: D5
    description: "worker.run_once claims the single oldest pending job and ends it done with the outcome as its reason"
    requirement: "DESK-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_tracer.py (every case runs one worker pass and reads the job back)"
        status: pass
    human_judgment: false
---

# Phase 85 Plan 01: The service desk tracer Summary

A person who raises a ticket on the portal now gets one attempt: the ticket is stamped and queued, one worker pass finds the tenant's own Help desk article, asks a loopback-only model once, checks that the reply cites only the article it was given, asks the Autonomous Ops gate, and then either posts a cited answer the reporter reads back (mode post, level Undoable auto, shadow off) or keeps it as a staff-only draft (the default).

Duration: about 7 minutes (19:19 to 19:26 UTC). Tasks: 2. Files: 18 (15 created, 3 modified). Completed 2026-11-08.

## Accomplishments

- **Task 1, the tracer (b5fe83320).** Twelve `service_desk` modules, each carrying only its single-path behaviour: `__init__` declares every desk constant once; `store.ensure_indexes` creates every desk index (`one_attempt_per_ticket`, TTLs, `one_starter_copy`, `tray_list`, `desk_return_due`); `intake` enqueues once; `sanitize` cleans ticket text and builds the one prompt; `retrieval` scores only the tenant's own `helpdesk` articles with a per-call TF-IDF; `model` is the only httpx importer and refuses non-loopback hosts; `pipeline.answer` runs probe, generate, checks, `gate.decide`, then post or draft; `worker.run_once` claims the oldest pending job.
- **Ticket hooks.** `create_ticket` in `tickets_service.py` takes `raised_via` and `requester_channel` keywords (never read from the body). The endpoint stamps `portal` only for an interactive session with a tenant (`views.is_interactive`), calls `intake.on_ticket_created` inside try/except, and `router_registry.py` mounts `service_desk_endpoints` right after `tickets_endpoints`.
- **Requester view.** `GET /api/tickets/{id}/service-desk` reads the ticket inside the caller's tenant (another tenant, or no tenant, answers 404) and returns the requester block only to the reporter.
- **Task 2, fail-closed edges (5af3c07a0).** Thirteen further cases pin who raised it, Off, unticked, Platform, no article, the three model-unavailable shapes, the look-alike host names, the uncited and mis-shaped replies, and one attempt per ticket. They exposed no defect, so Task 2 is a test-only commit.
- Mutation check run by hand: removing the `helpdesk`/tenant filter from `retrieval.candidates` and the loopback refusal from `OllamaClient` made 5 of the 16 tests fail; both were restored before committing.

## Task Commits

| Task | Commit | Type | Description |
| ---- | ------ | ---- | ----------- |
| 1 | b5fe83320 | feat | A portal ticket gets one cited answer through the gate and the requester reads it back |
| 2 | 5af3c07a0 | test | Fail-closed edges on the one path |

Plan type `execute` with tasks marked `tdd="true"`: as in 85-02 and 85-03, tests and implementation were written together and committed together (Task 1's commit holds the first three tests; Task 2's holds the rest).

## Verification

- Task 1 command (tracer, structural, test_tickets): all pass, no skips. Task 2 command (tracer, structural): 42 passed, no skips.
- Plan-level: `test_autonomous_ops_copy.py` 33 passed (the ACTV-08 scan covers every new `backend/service_desk` file).
- Extra regression runs: ticket attachment download (4), route and catalogue guards (`test_route_auth_baseline`, `test_tenant_screen_routes`, `test_router_registry_required`, `test_catalogue_exempt_reads`, `test_000_router_smoke`: 29 passed; `test_catalogue_route_parity`, `_manifest`, `_guards`, `test_sidebar_screen_switches`, `test_itam_ticketing_bridge` plus the 85-02/03 desk tests: 200 passed).
- Acceptance greps: `one_attempt_per_ticket` in store.py 1; `on_ticket_created` in tickets_endpoints.py 1; `gate.decide` in pipeline.py 1; `import httpx` only in `service_desk/model.py`; no `ai_service`/`ai_providers` import under `backend/service_desk`; 16 tests in the tracer file (needs 12); every new file is under 500 lines (largest 117).
- Every DB test used the private mongod on 27998; nothing touched the live database and no real Ollama was called (stand-in `httpx.MockTransport` only).

## Existing tests whose expectation changed

None. `test_tickets.py` passes unchanged (its mocked database absorbs the intake hook, which only logs).

## Defects in the 85-03 gate seam

None found. `gate.decide` with `desk=`, `targets=[]`, `params={"ticketId"}` and `dispatcher="service_desk"` produced `suggested` (Drafts) and `dispatching` (post) rows exactly as 85-03 documented, and `ledger.transition(... "dispatching" -> "executed", **{"desk.phase": ...})` worked as planned.

## Deviations from Plan

None - plan executed exactly as written.

Notes that are choices inside the plan's latitude, not deviations:
- `tickets_endpoints.py` is now 598 lines (it was 580, and 531-line `tickets_service.py` is 542). The plan named these two files as exceptions to the 500-line rule and allowed only the named hook lines; the additions are 18 and 11 lines.
- `retrieval.score` returns every candidate with its score (best first) and `select` applies the accept rule, so 85-06 can re-pin `CUT` and `MIN_TERMS` on the starter articles without touching the scoring.

## User WIP preserved

`backend/tickets_endpoints.py` had the user's uncommitted attachment directory and download route (+38/-11). Only this plan's hunks were committed: the file was rebuilt from `HEAD` with this plan's two edits applied and staged as that blob (`git update-index --cacheinfo`), so no user line was staged. After both commits `git diff -- backend/tickets_endpoints.py` still shows exactly +38/-11 and the working tree holds both sets of changes (the tracer tests ran against both). `router_registry.py` and `tickets_service.py` had no user changes.

## Hand-over for later plans

- **85-04 (outcome matrix and gate edges):** the pipeline treats every non-`allow_auto`, non-`refuse` decision as a staff draft and every `refuse` as `refused:<code>` (job reason). `desk.phase` values written so far: `queued` (ticket), `posted`, `drafted`. `reason.inputs` already carries `articles`, `cut`, `matchedTerms`, `model`, token and timing counts, `requesterCanSee`, `suggestionOnly`.
- **85-13 (moved ticket, stop after generation):** `pipeline.answer` posts the comment first, then calls `move_status(("open",), "pending_customer")` as the plan orders it; if that compare-and-set loses to a person who moved the ticket during generation, the answer is already posted and the status unchanged. That is the "ticket moved during generation" edge assigned to 85-13, not handled here.
- **85-06:** `checks.check` covers citation, emptiness and length only. `sanitize.clean_text` removes angle brackets so no ticket text can close the `<ticket>` tag; article text is passed with angle brackets and double quotes neutralised.
- **85-07:** `OllamaClient.available()` probes on every call (no cache) and `generate` uses the fixed `DEFAULT_CALL_TIMEOUT` of 120 seconds.
- **85-09:** `intake` checks only mode, Platform tenant, who raised it and the Autonomous Ops screen; level, stop and the ticket-screen checks are 85-09.
- The `tray_list` and `desk_return_due` indexes exist only after `store.ensure_indexes` runs; migration 032 (85-17) calls it. Nothing was run on the live database.

## User steps

None for this plan. Not done, by design: restart of the backend (the new route and the intake hook go live on the user's next restart; until then nothing queues a job), migration/index creation on the live database, installing Ollama or pulling `llama3.2:3b`, and git push.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register. The new `GET /api/tickets/{id}/service-desk` is behind `view:dashboard`, reads inside the caller's tenant and returns the requester block only when the reporter equals the caller's username or email.

## Self-Check: PASSED

- Files: all 15 created and 3 modified files exist and are committed (b5fe83320, 5af3c07a0 are ancestors of HEAD).
- All `<acceptance_criteria>` of both tasks re-run and pass (see Verification).
