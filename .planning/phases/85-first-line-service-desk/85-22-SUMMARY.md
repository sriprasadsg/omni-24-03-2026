---
phase: 85-first-line-service-desk
plan: 22
subsystem: service-desk
tags: [service-desk, operator-script, ollama, measurement, injection-set, calibration, loopback]
status: complete

requires: [85-07, 85-13]
provides:
  - "backend/scripts/service_desk_eval.py: the operator's script with --measure, --sets, --calibrate, --tenant, --samples, --mongo, --db-name, --dry-run; async main(argv, *, transport=None) returns the exit code"
  - "--measure: 5 to 40 real-shape prompts one at a time, median and p95 of total, load, prefill and generation speed, stores the medians as the one service_desk_runtime document through runtime.save_measurement"
  - "--sets: escalation, injection and retrieval sets through the desk's own stages and the model, read only, exit 1 on a foreign fragment that passed the output checks"
  - "--calibrate --tenant: read-only score, shared words and accept decision per recent person-raised ticket under the pinned CUT and MIN_TERMS"
  - "service_desk.model.ModelReply.prefill_ms (prompt_eval_duration in milliseconds), so the prefill speed is exact"
affects: [85-23]

actuals:
  tokens: 11100
  tasks: 2
  commits: 4
plan_head_before: 1dfaa7a69160cb77125308a27133969ed591f0d5
plan_head_after: 465018965ae6bd7d0ae179a16dcf1197cc8b269e

tech-stack:
  added: []
  patterns:
    - "The operator script reaches the model only through service_desk.model.OllamaClient and imports no httpx and no AI provider (an AST test pins it); a non-loopback SERVICE_DESK_OLLAMA_URL exits 2 before anything is sent"
    - "main(argv, *, transport=None) returns the exit code, so every mode is tested offline with an httpx.MockTransport stand-in and the private mongod"
    - "The script holds its own second reading of the D-19 rule (foreign_kinds), so a broken service_desk.checks cannot make the live run look clean"
    - "Stages are called through their modules (rules.evaluate, checks.check) so a test can swap in a broken one and see the run fail"

key-files:
  created:
    - backend/scripts/service_desk_eval.py
    - backend/tests/test_service_desk_eval_script.py
  modified:
    - backend/service_desk/model.py

key-decisions:
  - "ModelReply gained prefill_ms (default 0). The model client kept only the total, load and generation times, so the prefill speed (prompt_eval_count / prompt_eval_duration) could not be computed exactly; deriving it as total - load - generation would have counted tokenising and sampling overhead as prefill"
  - "--db-name (default MONGODB_DB_NAME, else omni_platform) was added next to --mongo, so the script targets the database the environment names and tests can aim it at a throwaway database on the private mongod"
  - "--measure takes 5 to 40 samples: below 5 the plan's own minimum, above 40 the retrieval set has no more distinct matching questions"
  - "loadSeconds stores the median load, as planned. With keep_alive 30m only the first sample normally loads the model, so the median is near 0; the output also prints the first and the longest load so the operator sees the cold figure"
  - "A model that answers without timings stores nothing (exit 3): a measurement without durations is not a measurement"
  - "The retrieval set in --sets is reported (margin, cases not as expected) but never fails the run: it is pure code pinned by test_service_desk_retrieval.py, and the plan's failure conditions are the foreign fragment and an escalation case reaching the model"
  - "--calibrate never changes the cut-off; it prints the lowest accepted and highest refused gate score and says that moving CUT is a reviewed change to retrieval.py"

requirements-completed: [DESK-02, DESK-03, DESK-05]

coverage:
  - id: D1
    description: "--measure sends 5 real-shape prompts one at a time, prints median and p95 of total, load, prefill and generation speed, and stores prefillTps, genTps, loadSeconds, samples, model and measuredAt as the one service_desk_runtime document; --dry-run prints the same and writes nothing"
    requirement: "DESK-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_eval_script.py (test_measure_prints_the_medians_and_stores_exactly_them, test_measure_sends_five_real_shape_prompts_one_at_a_time, test_dry_run_prints_the_same_and_writes_nothing, test_measure_writes_one_document_even_when_run_twice, test_a_model_that_reports_no_timings_stores_nothing)"
        status: pass
    human_judgment: false
  - id: D2
    description: "The script refuses a non-loopback model URL in every mode (exit 2, nothing sent), reports an absent model or tag as 'Offline: the local model isn't running' (exit 3), and imports neither httpx nor an AI provider"
    requirement: "DESK-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_eval_script.py (test_a_lan_model_url_exits_2_naming_loopback_and_sends_nothing, test_an_unavailable_model_exits_3_with_the_offline_message, test_the_script_reaches_the_model_only_through_the_desk_client); backend/tests/test_service_desk_structural.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "--sets runs the escalation, injection and retrieval sets through the desk's own stages, exits 1 naming the case when a reply passes the output checks while carrying a foreign link, address, phone, number or command, when a prompt holds a link, or when an escalation case reaches the model, and writes nothing"
    requirement: "DESK-02, DESK-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_eval_script.py (test_sets_with_a_benign_model_exit_0_with_a_summary_line_per_set, test_a_compliant_model_answering_with_a_foreign_link_is_rejected_by_the_output_checks, test_a_broken_output_check_is_caught_and_the_case_is_named, test_an_escalation_case_that_reaches_the_model_fails_the_run, test_a_prompt_that_carries_a_link_fails_the_run, test_the_scripts_own_detector_finds_a_foreign_fragment_without_using_the_desk_checks)"
        status: pass
    human_judgment: false
  - id: D4
    description: "--calibrate --tenant prints one line per recent person-raised ticket of that tenant with score, shared words and accepted yes or no under the pinned CUT and MIN_TERMS, at most 80 characters of ticket text, and leaves every collection unchanged and the model uncalled"
    requirement: "DESK-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_eval_script.py (test_calibrate_prints_one_line_per_person_raised_ticket_and_writes_nothing, test_calibrate_on_a_tenant_without_articles_says_so, test_calibrate_names_a_database_that_is_not_reachable)"
        status: pass
    human_judgment: false
  - id: D5
    description: "The real speed of llama3.2:3b on this CPU, what the real model answers to the injection set, and how the cut-off treats a real tenant's articles"
    requirement: "DESK-02, DESK-03, DESK-05"
    verification: []
    human_judgment: true
    rationale: "Needs Ollama and the model, which are not installed on this VM and are the operator's step; the live run is on the user's list in 85-23"
---

# Phase 85 Plan 22: The operator's measurement, live-set and calibration script Summary

**One safe script, `backend/scripts/service_desk_eval.py`, measures llama3.2:3b on this CPU and stores the medians for the desk's timeouts (`--measure`), re-runs the escalation, injection and retrieval sets against the real model with its own foreign-fragment detector (`--sets`), and shows how the pinned cut-off treats a real tenant's Help desk articles and tickets (`--calibrate`); every mode is tested offline and none was run against a real model or the live database.**

Duration: 14 min (2026-11-09 06:03 to 06:17 UTC). Tasks 2, files 3 (script, test file, model.py), commits 4.

## What the operator runs, in order

This VM has 4 vCPU and 15 GB of RAM and no GPU (the research assumed 2 vCPU and 7 GB). The default model tag is `llama3.2:3b`. Until a measurement is stored the desk uses its default timeouts: 280 s for a 4,000-character prompt (85-07). All commands run from the repository root. Nothing below was run by this plan.

1. Install Ollama bound to this server only (`OLLAMA_HOST=127.0.0.1:11434`; optional drop-in `OLLAMA_NUM_PARALLEL=1` and `OLLAMA_MAX_LOADED_MODELS=1`), then `ollama pull llama3.2:3b`, then check `curl http://127.0.0.1:11434/api/tags` lists `llama3.2:3b`. If the model is missing or Ollama is down the script says "Offline: the local model isn't running" with the address and the tag and exits 3.
2. Rehearse, no write (sends 5 prompts, prints the numbers):
   `backend/venv/bin/python backend/scripts/service_desk_eval.py --measure --dry-run`
3. Measure and store, at a quiet time, with API latency watched while it runs (one core stays free for the API, but check it):
   `backend/venv/bin/python backend/scripts/service_desk_eval.py --measure --mongo "$MONGODB_URL"`
   It prints median and p95 of total time, load time, prefill tokens per second and generation tokens per second (plus the slowest speed, the first and longest load, and the timeout a 4,000-character prompt would now get), then stores one `service_desk_runtime` document in the database named by `--db-name` / `MONGODB_DB_NAME` (default `omni_platform`). Record those numbers for the phase notes.
4. Run the sets against the real model (read only, no database needed, about 25 model calls so expect tens of minutes on a CPU):
   `backend/venv/bin/python backend/scripts/service_desk_eval.py --sets`
   Exit 0 means every check held; exit 1 lists `FAIL escalation <id>` or `FAIL injection <id>` lines. The retrieval line prints the margin (0.2268 with the pinned set).
5. Calibrate on a real tenant (read only, no model call):
   `backend/venv/bin/python backend/scripts/service_desk_eval.py --calibrate --tenant <tenant id> --mongo "$MONGODB_URL"`
   Record the cut-off the output supports. The script never changes `CUT`; moving it is a reviewed change to `retrieval.py` re-pinned with the retrieval set.

Exit codes: 0 done, 1 a check failed, 2 wrong usage or a refused (non-loopback) URL, 3 the model or the database is not available.

## Task commits

| Task | Commit | What |
| ---- | ------ | ---- |
| 1 RED | 63e63c53b | `test(85-22)`: failing tests for --measure, --dry-run, the loopback refusal, the offline message, the AST import check |
| 1 GREEN | 418d60e1d | `feat(85-22)`: the script with --measure, plus `ModelReply.prefill_ms` |
| 2 RED | 15acc820e | `test(85-22)`: failing tests for --sets, the script's own detector and --calibrate |
| 2 GREEN | 465018965 | `feat(85-22)`: --sets and --calibrate |

## TDD Gate Compliance

RED and GREEN commits exist for both tasks, in order. This is a `type: execute` plan with `tdd="true"` tasks, so the machine classifier `gsd_run check tdd-red-evidence` (which does not read pytest reports) was not used; the semantic assessment is recorded instead.

- Task 1 RED: 10 of 10 target tests failed with `FileNotFoundError` on `backend/scripts/service_desk_eval.py`, which did not exist. Assessment: the planned behavior was absent, not a collection or import fault of the test file; accepted.
- Task 2 RED: 19 target tests failed and the 10 Task 1 tests stayed green. The failures were the stub's "--calibrate is not available yet" exit 2 and the missing `foreign_fragments`, so each failed on the planned assertion (exit code or output) and not on setup.
- No REFACTOR commit was needed.

## Verification

- Task 1 command (`test_service_desk_eval_script.py` + `test_service_desk_structural.py`): 44 passed, 0 skipped.
- Task 2 command (`test_service_desk_eval_script.py`): 29 passed, 0 skipped.
- Also green: `test_service_desk_model.py`, `test_service_desk_retrieval.py`, `test_service_desk_rules.py` (164 passed together with the two above). ruff is clean on both new files.
- Acceptance criteria: `grep -c save_measurement` prints 1, `grep -c -- --dry-run` prints 4, `grep -c -- "--sets\|--calibrate"` prints 10, the script is 465 lines (limit 500); the measure test asserts `max_in_flight == 1`; the calibrate test compares a full snapshot of every collection before and after.
- A manual look at the output with stand-in models showed the escalation set at 150 cases / 0 failed, the injection set at 33 cases (25 reach the model, 8 are handed off by the rules, 0 failed) and the retrieval margin at 0.2268, equal to the figure 85-06 pinned.
- The private mongod (27998) was the only database used; no omni_test database was left behind. The live server, a real model and the network were never touched.

## Deviations from Plan

**1. [Rule 3 - Blocking] `ModelReply.prefill_ms` added to `service_desk/model.py`**
- **Found during:** Task 1
- **Issue:** the plan computes prefill speed as `prompt_eval_count / prompt_eval_duration`, but `ModelReply` kept only the generation, load and total durations, so the prefill duration was out of reach of a script that must use `OllamaClient` and nothing else.
- **Fix:** one defaulted field, set from `prompt_eval_duration`. Backward compatible; the model tests still pass unchanged.
- **Files modified:** `backend/service_desk/model.py`
- **Commit:** 418d60e1d

**2. [Rule 2 - Missing critical] `--db-name` flag and sample bounds**
- **Found during:** Task 1
- **Issue:** `--mongo` alone cannot name which database to read or write, and the plan requires the script to target the database the environment names while tests must aim it at a throwaway database.
- **Fix:** `--db-name` (default `MONGODB_DB_NAME`, else `omni_platform`, the same default the backend uses); `--samples` limited to 5..40.
- **Files modified:** `backend/scripts/service_desk_eval.py`
- **Commit:** 418d60e1d

**Total deviations:** 2 auto-fixed (1 blocking, 1 missing-critical). **Impact:** none on scope; both are small and tested.

Two behaviors worth knowing, both as the plan wrote them: `loadSeconds` is the median load, so after the model is already in memory it is near 0 (the cold load shows in the printed first and longest load and is covered by the 45 s timeout floor), and the language set is not part of `--sets` (the plan names escalation, injection and retrieval; the English check runs inside each escalation and injection case).

## Authentication Gates

None.

## Known Stubs

None. The two "not available yet" placeholders that stood in the Task 1 commit were replaced in Task 2.

## Threat Flags

None. T-85-80 (ticket text in --calibrate: 80 characters of the cleaned text, scores and words), T-85-81 (only `--measure` without `--dry-run` writes, one document; tests snapshot the collections) and T-85-82 (sequential calls only, quiet time and latency watching in the docstring) are handled as planned.

## Next

Ready for 85-23 (the phase's closing plan; the live run of this script is on the user's list there). The user's uncommitted files were not touched and stay unstaged.

## Self-Check: PASSED

- Files exist: `backend/scripts/service_desk_eval.py`, `backend/tests/test_service_desk_eval_script.py`, `backend/service_desk/model.py` (all found).
- Commits are ancestors of HEAD: 63e63c53b, 418d60e1d, 15acc820e, 465018965 (4 commits, measured from the ledger base 1dfaa7a69).
- Both plan verification commands re-run after the last commit: 44 passed and 29 passed, 0 skipped.
