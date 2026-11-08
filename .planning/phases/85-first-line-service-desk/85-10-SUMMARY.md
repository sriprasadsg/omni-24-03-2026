---
phase: 85-first-line-service-desk
plan: 10
subsystem: service-desk-tray
tags: [tray, powershell, winforms, my-tickets, polling, rust-embed, static-tests]
status: complete

requires:
  - "85-02: backend/service_desk/tray_contract.py (frozen routes, field names, limits, timings)"
provides:
  - "tray_icon.ps1: Raise a Ticket on POST /tray/tickets with template + client.features [my_tickets], 404 fallback to the legacy route, 'My tickets' menu item, Initialize-TicketWatch before Application.Run"
  - "tray_my_tickets.ps1: answer check (timer, balloon, tray-seen.json, menu count), Show-MyTickets window, Show-TrayArticle window"
  - "tray.rs: TRAY_MY_TICKETS_PS embedded and written beside tray_icon.ps1; test tray_scripts_embed_and_dot_source"
  - "backend/tests/test_service_desk_tray_static.py: 37 static checks of both scripts against the contract"
affects: [85-19, 85-23]

actuals:
  tokens: 36000
  tasks: 2
  commits: 3
plan_head_before: 0b5e54ce008be2fe237892dd4d8f50c0230847b2
plan_head_after: 123d4a04a642c8ee1d18e54849f3219a53c88608

tech-stack:
  added: []
  patterns:
    - "Shared tray state is one hashtable ($script:TicketWatch) captured by closures, so timer, balloon and window see the same object"
    - "Window handlers are closures over controls and a $ui hashtable; cross-calls go through $ui.Load / $ui.Show so definition order does not matter"
    - "Static PowerShell tests: a small tokenizer skips comments, strings and here-strings so brackets, hashtable keys and function bodies can be checked without PowerShell"

key-files:
  created:
    - agent-install/omni-agent-rs/scripts/tray_my_tickets.ps1
    - backend/tests/test_service_desk_tray_static.py
  modified:
    - agent-install/omni-agent-rs/scripts/tray_icon.ps1
    - agent-install/omni-agent-rs/src/tray.rs

key-decisions:
  - "tray-seen.json holds two id lists, popped (announced in a balloon) and read (opened by the user), so each answer pops up once yet the menu count 'My tickets (n new)' stays until the user opens it"
  - "The window uses ClientSize 800x560 (not outer Size) so every UI-SPEC coordinate fits; the outer size would clip the bottom 39 px at 100% scaling"
  - "Pop-up title and text are fixed in the script, because the frozen list response has no pop-up fields (DISPLAY_FIELDS is footnote, footer, empty)"
  - "The AI mark line 'AI-assisted answer from your IT knowledge base' is added by the script for answer entries unless the server text already starts with it"

requirements-completed: [DESK-01]

coverage:
  - id: D1
    description: "Raise a Ticket posts to the contract create route with template and the my_tickets claim, falls back to the legacy route only on a 404, shows the server's created text"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_tray_static.py#test_create_body_names_exactly_the_contract_fields"
        status: pass
    human_judgment: true
    rationale: "Static only: PowerShell is not on this VM, the real POST from a Windows tray is the user's step"
  - id: D2
    description: "Timer-driven answer check: 30 s for 180 s after raising, then 300 s only while an open ticket exists; one balloon per answer; click opens My tickets on that ticket"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_tray_static.py#test_poll_timings_equal_the_contract"
        status: pass
    human_judgment: true
    rationale: "Timer and balloon behaviour cannot be observed without Windows"
  - id: D3
    description: "My tickets window and article window laid out per UI-SPEC section 8 on a 4 px grid with the contract routes and fields"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_tray_static.py#test_my_tickets_layout_matches_ui_spec_section_8"
        status: pass
    human_judgment: true
    rationale: "No clipping at 100% and 150% scaling, and 60-char title / 900-char answer / five articles are backstop checks that need a real display"
  - id: D4
    description: "Agent embeds both scripts and the Windows target compiles"
    requirement: "DESK-01"
    verification:
      - kind: command
        ref: "cargo test --lib tray_ (nodebug) and cargo check --target x86_64-pc-windows-gnu"
        status: pass
    human_judgment: false
---

# Phase 85 Plan 10: Tray My tickets window and answer pop-up Summary

The tray raises tickets on the new route with the `my_tickets` claim, watches for answers on a timer and pops up one balloon per answer, and opens a My tickets window where the user reads the conversation, opens cited articles and answers with This fixed it or I still need help, all against the frozen tray contract.

Duration: about 55 min. Tasks: 2. Files: 4 (2 created, 2 modified). Completed 2026-11-08.

## Accomplishments

- **Raise a Ticket (Task 1, 237dee66e).** `$Templates` entries carry the contract template ids (six, including `custom`). `Show-TicketDialog` posts `title, description, type, priority, template, endpoint_info, client {features ['my_tickets'], version}` to `$Base/api/agents/$AgentId/tray/tickets` with `-TimeoutSec 10` and a UTF-8 body. Only a 404 retries once on the legacy `/ticket` route with today's body. Success shows the server's `message` in ForestGreen (fallback: the UI-SPEC text) and calls `Start-TicketWatch`. A new `Get-ErrorStatusCode` helper reads the HTTP code.
- **Menu and polling (Task 1).** A `My tickets` item sits between Raise a Ticket and Chat with IT Support; it is added only when the second script loaded. `Initialize-TicketWatch` creates a `System.Windows.Forms.Timer` (30 s tick) before `Application.Run`. A tick calls `Invoke-TicketPoll` inside the 180 s fast window after a ticket is raised, or every 300 s while the last list held an open ticket (status not resolved or closed). The poll compares `answerIds` with `%LOCALAPPDATA%\OmniAgent\tray-seen.json`, raises one balloon `Your ticket has an answer` / `{number}: {title}. Click to read it.` (title cut under 255 characters), and sets the menu to `My tickets ({n} new)` only when n is at least 1. Failures are logged, never shown.
- **Agent embedding (Task 1).** `tray.rs` embeds `tray_my_tickets.ps1` under `#[cfg(windows)]`, adds `my_tickets_path()` and writes it beside `tray_icon.ps1`. `tray_scripts_embed_and_dot_source` embeds both scripts on any OS and checks the wiring.
- **My tickets window (Task 2, fc2c8a50d).** `Show-MyTickets` builds every control of UI-SPEC section 8 at its absolute position (list 292x400 with columns 64/140/80, bold title, status or reason line, read-only conversation, flow panel of article links, footer, note box limited to 500, four buttons, feedback label), tab order and accessible names as listed, Close as CancelButton. It runs `Sync-TrayConfig` and `Test-Enrolled` first, loads the list with `Get-TrayTicketList`, renders the server's entries (heading line with time, answer mark, text, `Based on:`), enables the two buttons from `canConfirm` / `canHelp`, and shows the server's reason line when they are off. Confirm and help post `{user}` / `{user, text}` to the contract routes (UTF-8, 10 s timeout) with `Saving...`, then the ForestGreen result and a refresh. A failed request shows `Couldn't load your tickets. {why}` or `Couldn't send that. {why}` and keeps the last list.
- **Article window (Task 2).** `Show-TrayArticle` (520x432, one read-only box, Close) fetches the cited article and shows `This article is no longer available.` when the server says so.
- **Static tests.** 37 tests: ASCII, under 500 lines, balanced brackets, no `Invoke-Expression`/`iex`/downloads/`Start-Process` of a URL, no PowerShell 7 syntax, `-TimeoutSec 10` on every request, routes and body keys equal to the contract, template ids and legacy prefixes cross-checked, dot-source order, menu order, timer before `Run`, poll constants, every Location/Size/column width a multiple of 4 (with a self-check that an off-grid value is caught), layout coordinates, tab order, accessible names, state texts, no privacy claim, response fields read are in the contract.

## Task Commits

| Task | Commit | Type | Description |
|------|--------|------|-------------|
| 1 | 237dee66e | feat | Raise a Ticket on the tray route, answer watch, agent ships the second script |
| 2 | fc2c8a50d | feat | My tickets window and read-only article window |
| - | 123d4a04a | refactor | Share one token skipper in the static test to stay under 500 lines |

Plan type is `execute` (tasks marked `tdd="true"`, `workflow.tdd_mode` false). RED was run before each implementation: Task 1's tests failed on the missing second script and missing menu, route and dot-source (12 failed, 8 errors); Task 2's 12 new tests failed on the stub window (12 failed, 25 passed). Test and implementation were committed together per task.

## Verification

- `pytest backend/tests/test_service_desk_tray_static.py test_service_desk_tray_contract.py test_autonomous_ops_copy.py` with `MONGO_*` on 27998: 78 passed (static 37, contract 8, copy gate 33).
- `cargo test --offline --lib tray_` (nodebug target dir): `tray::tests::tray_scripts_embed_and_dot_source ... ok`, 2 passed, 0 failed.
- `cargo check --offline --lib --target x86_64-pc-windows-gnu`: finished, 0 errors (11 pre-existing warnings, none in tray.rs).
- Acceptance: `tray_my_tickets.ps1` named 1 time in `tray_icon.ps1` and 4 times in `tray.rs`; `my_tickets` and `'My tickets'` present; `function Show-MyTickets` + `function Show-TrayArticle` count 2; the 800x560 form size present; `tray_icon.ps1` 364 lines, `tray_my_tickets.ps1` 494, the test 499.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] tray_icon.ps1 was not ASCII**
- **Found during:** Task 1 RED
- **Issue:** the plan requires ASCII-only scripts, but five comment lines held an em dash and box-drawing characters; the static test failed on the untouched file.
- **Fix:** replaced them with `-` and `-` runs (comments only).
- **Files modified:** agent-install/omni-agent-rs/scripts/tray_icon.ps1
- **Commit:** 237dee66e

**2. [Rule 1 - Plan conflict] Pop-up text cannot come from the server**
- **Found during:** Task 1
- **Issue:** the plan says the pop-up title and text are read from the response, but the frozen contract's list response has no such fields (`DISPLAY_FIELDS` is footnote, footer, empty) and a frozen contract cannot gain fields without stranding older trays.
- **Fix:** the script composes the pop-up from the contract's `number` and `title` with the fixed UI-SPEC wording. `messages.py` already holds the same strings (`TRAY_POPUP_TITLE`, `TRAY_POPUP_TEXT`), so the two must be kept equal by hand.
- **Commit:** 237dee66e

**3. [Rule 2 - Missing critical] Show-MyTickets needed a first version in Task 1**
- **Found during:** Task 1
- **Issue:** the Rust test and the menu item need `Show-MyTickets` to exist, but the window is Task 2's work.
- **Fix:** Task 1's commit carried a one-line placeholder (a message box); Task 2 replaced it with the real window. No release was built between the two commits.
- **Commit:** 237dee66e, replaced in fc2c8a50d

**4. [Rule 2 - Missing critical] Robustness additions**
- Window uses `ClientSize` 800x560 and 520x432 (outer `Size` would clip the bottom of the window).
- Both new POST bodies are sent as UTF-8 bytes with `charset=utf-8`, so a note or title with accented characters is not mangled by Windows PowerShell 5.1.
- A tray that cannot load the second script still raises tickets and simply has no My tickets item (the dot-source is wrapped in try/catch and logged).
- The Agent Status balloon clears the pending answer ticket, so clicking it never opens My tickets.
- One My tickets window at a time (`WindowOpen` flag).
- The article window shows `Couldn't load this article. {why}` when there was no HTTP response (network failure), and the UI-SPEC text only when the server answered, so a network error is not reported as a missing article.
- The test file was refactored to share one tokenizer so it stays under the 500-line limit of CLAUDE.md.

**Total deviations:** 4 (1 bug, 1 plan conflict, 2 robustness groups). **Impact:** none on scope or contract.

## Authentication Gates

None.

## Known Stubs

None. The Task 1 placeholder was replaced in Task 2.

## Threat Flags

None. No new endpoint or auth path: the scripts call routes 85-19 builds, and `tray-seen.json` holds answer ids only (T-85-37 accepted). T-85-35 (no dynamic code) and T-85-36 (polling load, 10 s timeout) are enforced by the static tests.

## Notes for later plans

- **85-19 (tray routes).**
  - The create response must carry `message` and `ticket_number`; the tray reads both.
  - Answer entries: the script adds the line `AI-assisted answer from your IT knowledge base` before the answer text unless the entry text already starts with it. Either server choice works; do not send it twice with different wording.
  - `answerIds` must list only answers that should count as new (not withdrawn ones).
  - `status` of resolved or closed ends the slow polling.
  - The tray reads `$cfg.agent_version` for `client.version`; `write_tray_config` in `config.rs` (user's uncommitted work) does not write that field yet, so `version` is empty until 85-23 or the user adds it.
- **85-23.** The agent version carrying this window is 2.1.18; this plan did not bump it.

## User steps (live, Windows only)

No PowerShell exists on the VM, so none of the script behaviour has run. After the agent release:

1. Raise a Ticket from the tray: the green text reads `Ticket TKT-n created. Choose My tickets in the tray menu to see any reply.`
2. Within 30 s of an answer, one balloon `Your ticket has an answer` appears; clicking it opens My tickets on that ticket; the menu reads `My tickets (1 new)` until the window is opened.
3. In the window: This fixed it, I still need help (with and without a note), a cited article link, Refresh tickets, an empty list, a stopped service (error text keeps the list).
4. Check the window at 100% and 150% display scaling, with a 60-character title, a 900-character answer and five cited articles (the two backstop rows of UI-SPEC).
5. Confirm `tray_my_tickets.ps1` appears next to `tray_icon.ps1` in `C:\ProgramData\OmniAgent`.

Risk to watch in step 1-3: the handlers rely on script-scope functions from inside `.GetNewClosure()` scriptblocks, the same pattern the existing Raise a Ticket dialog already uses.

## Self-Check: PASSED

Files present: tray_icon.ps1, tray_my_tickets.ps1, tray.rs, test_service_desk_tray_static.py. Commits 237dee66e, fc2c8a50d and 123d4a04a are ancestors of HEAD. Acceptance criteria and plan-level verification re-run green. The user's uncommitted Rust work (Cargo.toml, Cargo.lock, buffer.rs, capabilities, config.rs, heartbeat.rs, lib.rs, main.rs and others) was not touched or staged.
