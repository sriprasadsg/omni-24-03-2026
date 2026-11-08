---
phase: 85-first-line-service-desk
plan: 07
subsystem: service-desk
tags: [service-desk, ollama, loopback, availability-guard, timeouts, structural-fence]
status: complete

requires: [85-01]
provides:
  - "service_desk.model: ModelBusy, ModelTimeout, OllamaClient.loaded, memory_ok, clear_probe_cache, a 15 s availability cache per base URL and tag, num_thread and keep_alive on every request"
  - "service_desk.runtime: Measurement, load_measurement, recent_gen_ms, call_timeout, estimate_seconds, save_measurement (the one system_settings document of type service_desk_runtime)"
  - "backend/tests/test_service_desk_structural.py: the AST fence around the desk (D-15)"
affects: [85-13, 85-17, 85-22]

actuals:
  tokens: 13800
  tasks: 3
  commits: 3
plan_head_before: 5bc4373eacc7256ee05f55351a648b9dfdab3130
plan_head_after: af859009329d72e875dc706a911ed74f04db87e8

tech-stack:
  added: []
  patterns:
    - "Probe once per 15 s per URL and tag, and cache the failure too, so a burst of jobs sends one /api/tags request whether the model is up or down"
    - "Busy is a distinct signal: 503 or too little free memory for a cold load raises ModelBusy before any ticket text is sent"
    - "Timeouts come from injected measurements (document plus recent desk rows); the real numbers are the operator's step"
    - "Structural scanner functions take (path, source) so each rule has a synthetic negative control"

key-files:
  created:
    - backend/service_desk/runtime.py
    - backend/tests/test_service_desk_model.py
    - backend/tests/test_service_desk_structural.py
  modified:
    - backend/service_desk/model.py

key-decisions:
  - "The availability cache entry also holds the transport the probe used, and is reused only by a client with the same transport. In production every client has transport None, so it is shared per URL and tag; a test with its own stand-in transport never reads another test's answer, so the 85-01 tracer tests needed no change"
  - "The cache stores the model size from /api/tags, so the cold-load memory check costs no extra request after the first probe"
  - "call_timeout and estimate_seconds round to two places (the plan's 88.75 needs two; 280.0 is unchanged); estimate_seconds includes the load allowance and omits only the 1.5 factor"
  - "recent_gen_ms reads across tenants (one model serves every tenant) and keeps only positive numeric genMs, filtered in the query so the limit counts usable rows"
  - "asyncio.wait_for outlasts the read timeout by a 1 s grace constant (it was 5 s), which a test can shorten; a read timeout and the outer wait both raise ModelTimeout"

requirements-completed: [DESK-03, DESK-04, DESK-05]

coverage:
  - id: D1
    description: "available() is False, and no generate request is sent, for a connect error, a 5xx, only another tag (llama3.2:1b, llama3.2:3b-instruct), malformed or wrong-shaped JSON, and any host that is not 127.0.0.1, ::1 or localhost (including look-alike names and non-http schemes); True only for the exact tag"
    requirement: "DESK-04"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_model.py (test_available_is_*, test_a_lan_address_is_refused_without_any_request, test_loopback_hosts_are_accepted, test_look_alike_and_non_http_urls_are_refused)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Availability is cached 15 s per URL and tag: two checks inside the window send one /api/tags request, a check after 16 s sends a second; a failed probe is cached too"
    requirement: "DESK-04"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_model.py (test_two_checks_within_the_cache_window_*, test_a_check_after_the_cache_window_probes_again, test_the_cache_is_shared_*, test_a_failed_probe_is_cached_too)"
        status: pass
    human_judgment: false
  - id: D3
    description: "generate raises ModelBusy on 503 and on a cold model without size plus 1.5 GB free (before any generate request), ModelTimeout on a read timeout or an outer wait that runs out, ModelError on 400 or a vanished tag; every request carries num_thread = max(1, cores - 1) and keep_alive 30m"
    requirement: "DESK-04"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_model.py (test_generate_*, test_a_cold_model_*, test_a_loaded_model_skips_the_memory_check, test_memory_ok_*, test_an_unreadable_meminfo_counts_as_enough)"
        status: pass
    human_judgment: false
  - id: D4
    description: "call_timeout and estimate_seconds follow the written formula: 280.0 with the defaults (measured False), 88.75 from a stored measurement, 1.5 x p95 of 6 recent genMs once 5 or more exist, clamped to 45..300; save_measurement keeps one document and rejects non-positive rates"
    requirement: "DESK-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_model.py (test_with_no_runtime_document_*, test_a_stored_measurement_sizes_the_timeout, test_enough_recent_rows_*, test_the_timeout_is_clamped_*, test_the_estimate_is_the_unscaled_sum, test_recent_gen_ms_*, test_save_measurement_*)"
        status: pass
    human_judgment: false
  - id: D5
    description: "No desk module imports a banned LLM module, local_ip, an omni_scratch or with_own_model module; only service_desk/model.py imports httpx; no desk module touches agent_instructions, instructions or response_tasks; nothing under autonomous_ops imports the desk; each rule has a negative control"
    requirement: "DESK-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_structural.py (15 tests, including test_scanner_reports_a_banned_import)"
        status: pass
    human_judgment: false
  - id: D6
    description: "How the real Ollama behaves on this 4 vCPU CPU-only server (real prefill, generation and load speeds; whether it stops generating when the client disconnects)"
    requirement: "DESK-05"
    human_judgment: true
    rationale: "Ollama is not installed on this VM and installing it is the user's step; the measurement belongs to the operator script (85-22) and the live check. Here the logic runs on injected numbers"
---

# Phase 85 Plan 07: The model guard and CPU-sized timeouts Summary

The desk now reaches only the exact local model on a loopback Ollama and stops cleanly, before any ticket text is sent, when that model is missing, remote, busy, short of memory or slow; every call's timeout is sized from a measurement of this server (conservative defaults until one exists); and a structural test fails the build if the desk ever imports an LLM provider, the LAN helper or touches an agent queue.

Duration: about 15 minutes. Tasks: 3. Files: 4 (3 created, 1 modified). Completed 2026-11-08.

## Accomplishments

- **Task 1, the guard (795dcaf25).** `model.py` gained `ModelBusy` and `ModelTimeout` (both subclasses of `ModelError`, so the existing `except ModelError` in the pipeline still catches them), a 15 s availability cache, `loaded()` (GET /api/ps), `memory_ok()` (MemAvailable against size plus 1.5 GB; an unreadable meminfo counts as enough) and `num_thread = max(1, cpu_count - 1)` with `keep_alive 30m` on every request. A tag that disappears between the probe and the call raises `ModelError`; nothing retries and nothing tries another tag.
- **Task 2, the timeouts (ea00eb032).** `runtime.py` computes `call_timeout` and `estimate_seconds` from the `service_desk_runtime` document (or the defaults 10 / 3 / 20 s, reported as not measured) and from the 95th percentile (nearest rank) of recent desk `genMs` values once five or more exist. `save_measurement` upserts the single document and rejects non-positive rates.
- **Task 3, the fence (af8590093).** `test_service_desk_structural.py` scans the desk package and every `service_desk_*.py` and `autonomous_ops_service_desk_endpoints.py` on disk with a glob (so later plans' endpoint modules are covered), reuses `BANNED_LLM_MODULES` from the Phase 81 structural test, also resolves relative imports, and checks that nothing under `autonomous_ops/` imports the desk. By hand, a throwaway desk file importing httpx, `ai_service` and `db.agent_instructions` made three of the real-code tests fail; the file was removed.

## Task Commits

| Task | Commit | Type | Description |
| ---- | ------ | ---- | ----------- |
| 1 | 795dcaf25 | feat | A missing, wrong, remote or overloaded model is detected before any ticket text is sent |
| 2 | ea00eb032 | feat | Every model call has a timeout sized from what this server measured |
| 3 | af8590093 | test | The structural fence around the desk |

Tasks are marked `tdd="true"`; as in 85-01 to 85-06, tests and implementation were written together and committed together per task.

## Verification

- Task 1 and 2 command (`test_service_desk_model.py`): 52 passed, no skips, against the private mongod on 27998.
- Task 3 command (structural for the desk and for Autonomous Ops): 41 passed.
- Plan-level: `test_autonomous_ops_copy.py` (the ACTV-08 scan covers the new `runtime.py`) with the structural, model and tracer tests: 142 passed; every `test_service_desk_*.py` file: 347 passed, no skips.
- Acceptance greps: `class ModelBusy|class ModelTimeout` 2; `num_thread` in model.py 1 (plus the test); `def call_timeout|def estimate_seconds|def save_measurement` 3; `280.0` and `88.75` asserted literally; model test file 26 test functions (52 cases); `BANNED_LLM_MODULES` in the structural test 3; `def test_scanner_reports_a_banned_import` 1; all four files are under 500 lines (largest 378).
- No model test sent a real network request (httpx.MockTransport only); every DB test used the private mongod on 27998 and nothing touched 27017.

## Deviations from Plan

None - plan executed exactly as written.

Notes that are choices inside the plan's latitude, not deviations: the outer `asyncio.wait_for` grace is 1 s rather than a flat 5 s so a test can exercise it quickly; `call_timeout` rounds to two decimals because the plan's own worked number is 88.75; the probe cache keeps the transport so injected stand-ins stay isolated (see key-decisions).

## Existing tests whose expectation changed

None. The 85-01 tracer tests pass unchanged: their stand-in Ollama has no /api/ps route (404, so the model reads as cold) and no model size, so the cold-load check runs against the real `/proc/meminfo` of the VM and needs 1.5 GB free.

## User WIP preserved

None of the four files overlap the user's uncommitted work. Only explicit paths were staged; no `git add -A`, stash, restore or reset was run.

## Hand-over for later plans

- **85-13 (hand-offs):** `pipeline.answer` still catches `ModelError` and returns `model_error`; `ModelBusy` and `ModelTimeout` are subclasses, so 85-13 can catch them first and map them to the `service_desk_busy` hand-off. The pipeline still calls `generate` with the fixed `DEFAULT_CALL_TIMEOUT`; wiring `runtime.call_timeout` into the call is 85-13's pipeline edit (this plan was told to leave `pipeline.py` alone).
- **85-17 (worker feasibility):** `runtime.estimate_seconds(prompt_chars, num_predict, measurement, recent)` is the expected duration; `runtime.load_measurement(db)` and `runtime.recent_gen_ms(db)` give its inputs. `Measurement.measured` is the "not measured" flag for the status line.
- **85-22 (operator script):** write the measurement with `runtime.save_measurement(db, {"model", "prefillTps", "genTps", "loadSeconds", "measuredAt", "samples"})`; it validates and keeps one document.
- **Cache in tests:** `model.clear_probe_cache()` resets the availability cache.

## User steps

Not done, by design: installing Ollama, pulling `llama3.2:3b`, the real measurement of this CPU (prefill, generation and load speeds), checking that Ollama stops generating when the client disconnects (A-85-A9), restart, publish and git push. Until the measurement exists the desk uses the conservative defaults (280 s for a 4000-character prompt and 220 tokens).

## Known Stubs

None.

## Threat Flags

None. T-85-22 and T-85-23 are mitigated by the loopback allow-list, the exact-tag probe and the structural import ban; T-85-24 by `num_thread`, the memory check and the 503 mapping; T-85-25 by `num_predict`, the read timeout plus `asyncio.wait_for`, and the 300 s ceiling.

## Self-Check: PASSED

- Files: `backend/service_desk/model.py`, `backend/service_desk/runtime.py`, `backend/tests/test_service_desk_model.py` and `backend/tests/test_service_desk_structural.py` exist; commits 795dcaf25, ea00eb032 and af8590093 are ancestors of HEAD.
- All `<acceptance_criteria>` of the three tasks re-run and pass (see Verification).
