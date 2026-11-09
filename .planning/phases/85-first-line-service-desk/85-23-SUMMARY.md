---
phase: 85-first-line-service-desk
plan: 23
subsystem: service-desk
tags: [service-desk, agent-version, validation, gates, live-list, phase-close]
status: complete

requires: [85-01, 85-02, 85-03, 85-04, 85-05, 85-06, 85-07, 85-08, 85-09, 85-10, 85-11, 85-12, 85-13, 85-14, 85-15, 85-16, 85-17, 85-18, 85-19, 85-20, 85-21, 85-22]
provides:
  - "Agent version 2.1.18 (Cargo.toml line 3 and the omni-agent entry of Cargo.lock), committed alone; the Windows library target compiles and the two tray_ tests pass"
  - "Every automated gate of Phase 85 green together on the final code: 1,955 backend tests, 1,840 vitest tests, npm run build (bundle index-DrSQiTVf.js)"
  - "85-VALIDATION.md filled: real plan, task, wave, threat and command on every row, Wave 0 ticked (A-85-STARTER-SRC), status validated, nyquist_compliant and wave_0_complete true"
  - "The user's ordered live list (steps 0 to 10) and the known limits of the phase"
affects: [85-verification, 85-UAT]

requirements-completed: [DESK-01, DESK-02, DESK-03, DESK-04, DESK-05, DESK-06, DESK-07]

actuals:
  tokens: 9500
  tasks: 3
  commits: 2
commits: 2
plan_head_before: b4975ec3b35ab79ae69c80ca7af07cb6efb248a3
plan_head_after: 0e54c6125ef199d534f663a1d20363e8bdb9f95d

tech-stack:
  added: []
  patterns:
    - "Version commit built from `git show HEAD:<file>` with only the version edit and staged with `git update-index --cacheinfo 100755,...`, so the user's uncommitted flate2 hunks stay unstaged in the working tree"

key-files:
  created: []
  modified:
    - agent-install/omni-agent-rs/Cargo.toml
    - agent-install/omni-agent-rs/Cargo.lock
    - .planning/phases/85-first-line-service-desk/85-VALIDATION.md

key-decisions:
  - "Requirement IDs DESK-01..07 are NOT marked Complete here. The plan leaves that to phase verification, even though requirements.ready-ids may report them ready now that every plan has a summary"
  - "_LATEST_AGENT_VERSION stays at 2.1.14. Bumping it and publishing the agent are the user's steps after 2.1.18 is published (live list step 7)"
  - "The backend gate list is the plan's own (1,955 tests); the orchestrator's wider list (test_catalogue_* in full plus test_database_migrations_lock.py, 2,040 tests) was green on the previous HEAD and this plan changed no backend file"

coverage:
  - id: D1
    description: "Agent 2.1.18 carries the tray window: version lines set, the Windows library target compiles, and the tray scripts embed and dot-source"
    requirement: "DESK-01"
    verification:
      - kind: command
        ref: "cargo check --offline --lib --target x86_64-pc-windows-gnu (exit 0, 0 error lines); cargo test --offline --lib tray_ (2 passed)"
        status: pass
    human_judgment: false
  - id: D2
    description: "All backend, UI and build gates of the phase pass together on the final code"
    requirement: "DESK-01, DESK-02, DESK-03, DESK-04, DESK-05, DESK-06, DESK-07"
    verification:
      - kind: command
        ref: "pytest (plan list) 1955 passed in 893.86s; npx vitest run src/__tests__ 1840 passed, 116 files; npm run build exit 0"
        status: pass
    human_judgment: false
  - id: D3
    description: "The validation map names real plans and tasks and is marked validated"
    requirement: "DESK-01, DESK-02, DESK-03, DESK-04, DESK-05, DESK-06, DESK-07"
    verification:
      - kind: command
        ref: "grep -c '| TBD |' 85-VALIDATION.md prints 0; grep -c 'wave_0_complete: true' prints 1; grep -c 'nyquist_compliant: true' prints 2 (frontmatter and sign-off line)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Everything that needs Ollama, a real CPU, the live server or a real Windows tray (the live list below)"
    requirement: "DESK-01, DESK-02, DESK-03, DESK-04, DESK-05"
    verification: []
    human_judgment: true
    rationale: "None of it can run on this VM or without the user's restart, publish and agent release; the live list below is the ordered set of those steps"

duration: 17min
completed: 2026-11-09
---

# Phase 85 Plan 23: Agent 2.1.18, All Gates Together and the Live List Summary

**The tray window rides its own agent version (2.1.18, two version lines committed alone), every automated gate of the phase passes together (1,955 backend, 1,840 vitest, build), the validation map names real plans and tasks, and the ordered live list for the user is below.**

## Performance

- **Duration:** 17 min (2026-11-09 06:46 to 07:04 UTC); the backend list took 14m54s of that
- **Tasks:** 3
- **Files:** 3 modified (Cargo.toml, Cargo.lock, 85-VALIDATION.md)
- **Commits:** 2 task commits (Task 2 changes no file; it is the gate run)

## Task commits

| Task | Commit | What |
| ---- | ------ | ---- |
| 1 | 6c981365d | `chore(85-23)`: agent version 2.1.18 (Cargo.toml line 3, the omni-agent entry of Cargo.lock), D-05 |
| 2 | none | The three gates, run on HEAD 6c981365d; results copied below |
| 3 | 0e54c6125 | `docs(85-23)`: the validation map with real ids, status validated |

## Accomplishments

- **Version 2.1.18 (Task 1).** Both files were built from `git show HEAD:<file>` with only the version edit and staged with `git update-index --cacheinfo 100755,...`; `git diff --cached` showed exactly the two version lines; the commit stat is 1 line changed in each file. After the commit `git diff` still shows the user's `flate2 = "1"` line and comment in Cargo.toml and the `"flate2",` line in Cargo.lock, unstaged, and the working tree reads 2.1.18 too (so a build from the working tree carries the right version). The deletion check on the commit found nothing deleted.
- **Windows compile and tray tests (Task 1).** `cargo check --offline --lib --target x86_64-pc-windows-gnu`: exit 0, 0 lines starting with `error`, 11 warnings (pre-existing, none from this plan). `cargo test --offline --lib tray_` (nodebug target): `running 2 tests ... test result: ok. 2 passed; 0 failed` (`tray::tests::tray_scripts_embed_and_dot_source`, `registration::tests::admission_states_set_the_tray_notice_and_retry_pace`). No release build, installer or publish.
- **Every gate together (Task 2).** One after another, nothing else running, backend on the private mongod 27998 only (the live 27017 was never reached):
  - Backend (the plan's list): `======================= 1955 passed in 893.86s (0:14:53) =======================` (0 failed, 0 skipped, exit 0).
  - Vitest: ` Test Files  116 passed (116)` and `      Tests  1840 passed (1840)` (exit 0, read directly).
  - Build: `npm run build` exit 0, `built in 3.04s`, 0 lines containing "error"; the bundle is `dist-new/assets/index-DrSQiTVf.js` (576.98 kB, gzip 146.85 kB). Nothing was published.
  - No flake appeared in this run: `FinancePanel.test.tsx` passed, `test_autonomous_ops_approvals.py` passed, and the tracer's cold-load check had the memory it needs.
- **Validation map (Task 3).** 85-VALIDATION.md has 26 rows (the 16 of the draft plus 10 added for the tracer, ledger, pipeline, hand-off, portal routes, withdraw, eval script, starters, tray contract, tray server contract, and the Rust agent build), each with the real plan and task ids, wave, threat refs and command, File Exists and Status green; the Wave 0 list is ticked with A-85-STARTER-SRC (`service_desk/starters.py` replaced the planned `starter_articles.json` fixture); the Manual-Only table gained the restart, the portal round trip and the browser layout rows; status is `validated`, `nyquist_compliant: true`, `wave_0_complete: true`, sign-off ticked.

## Deviations from Plan

None - plan executed exactly as written.

One note on the plan's acceptance wording: `grep -c "nyquist_compliant: true"` prints 2, not 1, because the sign-off checkbox line quotes the same text; the plan's own verify only needs a non-zero count and the frontmatter holds the real flag. The requirements are left unmarked on purpose (see key-decisions).

## Live list (the user's steps, in this order; the executor performed none of them)

**Read this before step 1: what the restart does at once.** A backend restart runs migration 032 (indexes only, including the `one_starter_copy` unique index) and starts the desk worker (5-second passes, hourly return sweep). Every tenant defaults to Drafts only (D-03). With Ollama absent, every new person-raised ticket in an eligible tenant is handed off `service_desk_offline` within about 5 seconds: a staff-only note plus a requester-visible "A person from IT will look at this." and a ledger row. To avoid that before Ollama exists, set the desk to Off per tenant first, or delay the restart until step 3 is done.

0. **Decide on the uncommitted Rust work before building.** Cargo builds the working tree. It holds your gzip/flate2 heartbeat work (the `flate2` lines in Cargo.toml and Cargo.lock, left unstaged by this plan, plus edits in several `src/*.rs` files such as `config.rs`). Commit it, stash it by your own means or drop it first; otherwise 2.1.18 ships it. Note that your `write_tray_config` in `config.rs` writes no `agent_version`, so the tray's `client.version` is empty until you add it.
1. **Check mongod, then restart the backend** (runs migration 032 and starts the desk worker; see the warning above). If the backend is down after a reboot check mongod first (kernel 7.0 drop-in). Then open Settings, Autonomous Ops, Service desk and read the status line.
2. **Publish the UI.** The bundle is `dist-new` (`index-DrSQiTVf.js` or later). The Phase-84-only backup is `/tmp/claude-1000/-home-azureuser-enterprise-omni-agent-ai-platform/df9d77ab-4108-4efa-b80f-d2f9962e90c3/scratchpad/dist-new.pre-85` (`index-DAKhmZYo.js`). Layout has not been checked in a real browser: look at Settings, the ticket panels and the Knowledge Base tabs in light and dark and at 320px.
3. **Install Ollama** as a systemd service bound to 127.0.0.1 (`OLLAMA_HOST=127.0.0.1:11434`; optionally a drop-in with `OLLAMA_NUM_PARALLEL=1` and `OLLAMA_MAX_LOADED_MODELS=1`), then `ollama pull llama3.2:3b`, then `curl http://127.0.0.1:11434/api/tags` and check the tag is listed.
4. **Run the 85-22 operator commands, in order,** from the repository root:
   - `backend/venv/bin/python backend/scripts/service_desk_eval.py --measure --dry-run` (rehearsal, writes nothing),
   - `backend/venv/bin/python backend/scripts/service_desk_eval.py --measure --mongo "$MONGODB_URL"` (at a quiet time, watching API latency while it runs; stores one runtime document),
   - `backend/venv/bin/python backend/scripts/service_desk_eval.py --sets` (about 25 model calls, tens of minutes; exit 0 means no foreign fragment passed the output checks),
   - `backend/venv/bin/python backend/scripts/service_desk_eval.py --calibrate --tenant <id> --mongo "$MONGODB_URL"` (read only; the script never changes the cut-off, moving `CUT` is a reviewed change to `retrieval.py`).
   Record the median and p95 times, the tokens per second, the sets result and the cut-off the calibration supports.
5. **On a test tenant:** add the starter IT articles (Knowledge Base, Help desk), edit them, raise a portal ticket, see the staff draft and Send as is; as the requester use "This fixed it" and "I still need help".
6. **As Super Admin:** lift shadow for that tenant, set Undoable-auto and Post answers, see a post, Undo it from Activity, trip the desk breaker with three withdrawals, then Restore.
7. **Build and publish agent 2.1.18** (Windows), then bump `_LATEST_AGENT_VERSION` in `backend/agent_auto_update_service.py` (still "2.1.14"; this plan did not touch it). Then on a real Windows PC: raise a ticket from the tray, see the pop-up, open My tickets and a cited article, use "This fixed it" and "I still need help", and check the window at 150% display scaling (also a 60-character title, a 900-character answer and five cited articles; the 85-10 checklist). **Shared PC (D-34):** the list is scoped by the Windows user name the tray reports, which is a convenience, not privacy: a second Windows user on the same PC sees an empty My tickets, and a local user who can read `tray-config.json` can see the name. The tray scripts have never been executed (PowerShell is not on this VM). 2.1.17, if you publish it first, simply has no My tickets window and the server keeps such tickets as drafts.
8. **Check the three-working-day return** on a test ticket (a posted answer waiting on the customer moves back to Open after three working days in the tenant's zone; the hourly sweep does it).
9. **If the Phase 82 watchdog is installed,** confirm it probes Ollama (no watchdog is installed on Omniai-copy today).
10. **`git push`.** Phase 85 commits are unpushed.

## Known limits (open items for verification, a gap plan or the user)

- **T-85-77 (accepted in the 85-20 plan):** on the portal the reporter's ticket JSON still carries staff-only comments and drafts; the requester panel only hides them in the UI. Server-side redaction is not done (pre-existing: anyone with ticket access sees all comments). The tray routes are the enforced boundary. Flag for secure-phase.
- The Activity "Open ticket" and the Knowledge gaps "Open ticket" deep links are not wired: they need an intent in `App.tsx` and `InternalTicketsDashboard.tsx` (both carry your uncommitted work). Gap ticket numbers are plain text.
- A tenant with Knowledge Base ticked but not Settings (the `manage:settings` parent switch) gets no desk attempts.
- The Post answers dialog cannot show blockers before the first save: the status view sends `posting.blockers` only while the saved mode is already post.
- `service_desk/worker.py` calls `pipeline._stopped` and `pipeline._handoff` (underscore names): a review item.
- The @mention notices are stored with an empty tenantId (pre-existing) and are never shown in any feed.
- A job waiting behind a running generation can be handed off up to one call timeout past its 10 minutes (a late answer is never posted).
- Panel dates use the viewer's calendar day, so a return date can differ by a day from the tenant zone near midnight; kanban cards have no Draft waiting chip; "Median of the last 1 answers." has no singular form.
- The tracer's cold-load check reads the real `/proc/meminfo` and needs 1.5 GB free: a possible flake on a loaded VM. `FinancePanel.test.tsx` ("shows None for an asset with no purchase_order_id") and some `test_autonomous_ops_approvals.py` tests are known load flakes, not Phase 85; none failed in this run.
- 85-21 added `GET /api/knowledge/docs/{doc_id}` (manage:ai_risks, tenant-own only); it and the rest of the backend need the restart in step 1.

## Authentication Gates

None.

## Known Stubs

None found in the files this plan changed (version lines and a planning document).

## Threat Flags

None. T-85-85 (user WIP shipped with the version commit) is mitigated: only the two version lines were staged and live list step 0 puts the decision first; T-85-86 (unverified live behaviour) is mitigated by the ordered live list above; T-85-SC accepted, nothing added.

## Requirements

DESK-01..DESK-07 were deliberately left unmarked Complete: the plan assigns that to phase verification, which the orchestrator runs next, even though `requirements.ready-ids` may now report them ready.

## Next

Phase 85 has 23 of 23 plans summarised. Next is phase verification (`completed_phases` in STATE.md stays at 5 until it passes); the live list above is what turns its human_needed items into passes.

## Self-Check: PASSED

- Files: `agent-install/omni-agent-rs/Cargo.toml`, `agent-install/omni-agent-rs/Cargo.lock`, `.planning/phases/85-first-line-service-desk/85-VALIDATION.md` (all found).
- Commits are ancestors of HEAD: 6c981365d, 0e54c6125 (2 commits, measured from the ledger base b4975ec3b).
- Acceptance criteria re-run: `grep -m1 '^version' Cargo.toml` prints `version = "2.1.18"`; `git show --stat` shows 1 line changed in each Cargo file and `git diff` still shows the user's flate2 hunks; `grep -c "| TBD |"` prints 0; `grep -c "wave_0_complete: true"` prints 1; the live list has steps 0 to 10 in the plan's order.
- Plan verification: the Windows check (exit 0), `tray_` tests (2 passed), backend (1955 passed, 0 skipped), vitest (1840 passed), build (exit 0): all re-run on the final code, which no later commit changed.
- The user's uncommitted work was left unstaged and untouched: nothing was staged except by explicit path.
