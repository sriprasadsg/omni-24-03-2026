---
phase: 41-cspm-provider-expansion-oci-alibaba-cloudflare
plan: 05
subsystem: api
tags: [python, fastapi, motor, cspm, oci, alibaba, cloudflare, pytest]

# Dependency graph
requires:
  - phase: 41-01
    provides: "RUNNABLE_PROVIDERS accepts oci/alibaba/cloudflare so run_checks() doesn't error on dispatch"
  - phase: 41-03
    provides: "poll_oci_cspm_findings / poll_alibaba_cspm_findings / poll_cloudflare_cspm_findings ingest functions"
provides:
  - "scan_account() ingests real oci/alibaba/cloudflare findings before run_checks() evaluates them (CSPM-01/02/03 end-to-end)"
  - "Dispatch + end-to-end regression tests proving simulated=False when real findings exist"
affects: [42-comment-threads-on-compliance-controls]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Provider-dispatch elif ladder in scan_account(): decrypt credentials_ref -> json.loads (fail-soft to {}) -> await poll_<provider>_cspm_findings(config, account_id, tenant_id), function-local imports"

key-files:
  created: []
  modified:
    - backend/cloud_accounts_service.py
    - backend/tests/test_cloud_findings_ingest.py

key-decisions:
  - "Dispatch tests added to test_cloud_findings_ingest.py rather than test_cloud_accounts.py — the plan's own acceptable-alternative clause applies: the 3 poll functions were already imported there and the mock_db/mock_get_db fixtures already patch get_database for oci_ingest/alibaba_ingest/cloudflare_ingest; test_cloud_accounts.py's existing scan tests are TestClient/HTTP-layer tests, a different pattern than the direct scan_account()-call dispatch tests this task needed."

patterns-established: []

requirements-completed: [CSPM-01, CSPM-02, CSPM-03]

# Metrics
duration: 25min
completed: 2026-07-20
status: complete
---

# Phase 41 Plan 05: CSPM Scan Dispatch Wiring Summary

**Three new `elif` branches wire `poll_oci_cspm_findings`/`poll_alibaba_cspm_findings`/`poll_cloudflare_cspm_findings` into `scan_account()`'s existing decrypt-and-ingest ladder, closing the last gap between the Phase 41 check catalogs (41-01) and ingest functions (41-03) — a real scan now imports findings before `run_checks()` evaluates them.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-20T20:07:25Z (approx, per STATE.md session start)
- **Completed:** 2026-07-20T20:13:48Z
- **Tasks:** 3 (2 code/test tasks + 1 regression-gate task with no file changes)
- **Files modified:** 2

## Accomplishments
- `scan_account()` now dispatches `oci`/`alibaba`/`cloudflare` providers through the same decrypt → `json.loads` → `poll_<p>_cspm_findings(config, account_id, tenant_id)` shape as the existing `microsoft365`/`mongodb_atlas` branches, with function-local imports preserved
- Three new dispatch tests (`test_scan_account_oci_dispatch`, `test_scan_account_alibaba_dispatch`, `test_scan_account_cloudflare_dispatch`) plus one end-to-end test (`test_scan_account_oci_simulated_false_end_to_end`) proving `cloud_check_results` carries `simulated=False` when real findings are present
- Full backend suite re-run as the phase regression gate: no new failure attributable to any phase 41 file

## Task Commits

Each task was committed atomically:

1. **Task 1: Add oci/alibaba/cloudflare branches to scan_account()** - `c4d55cb` (feat)
2. **Task 2: End-to-end scan dispatch tests** - `0fd2c7c` (test)
3. **Task 3: Full backend suite regression gate** - no file changes; verification only (see below)

**Plan metadata:** (this commit, immediately following)

## Files Created/Modified
- `backend/cloud_accounts_service.py` - `scan_account()` gained `elif provider == "oci"/"alibaba"/"cloudflare"` branches, each cloning the exact decrypt/`json.loads`/call shape of the existing `microsoft365`/`mongodb_atlas` branches
- `backend/tests/test_cloud_findings_ingest.py` - added 3 dispatch tests + 1 end-to-end `simulated=False` test for the new providers, following the existing `test_scan_account_m365_dispatch`/`test_scan_account_atlas_dispatch`/`test_scan_account_m365_simulated_false_end_to_end` pattern verbatim

## Decisions Made
- Placed the new dispatch/end-to-end tests in `test_cloud_findings_ingest.py` instead of `test_cloud_accounts.py`. The plan's Task 2 action explicitly allows this ("if the existing dispatch pattern lives more naturally beside the M365/Atlas dispatch tests, adding them to `test_cloud_findings_ingest.py` is acceptable"). `test_cloud_findings_ingest.py` already imports all three new poll functions and its `mock_db`/`mock_get_db` fixtures already patch `get_database` for `oci_ingest`/`alibaba_ingest`/`cloudflare_ingest`; `test_cloud_accounts.py`'s scan tests use a `TestClient`/HTTP-request pattern, not the direct `scan_account(mock_db, ...)` call pattern this task's tests needed.
- No architectural changes needed — the ingest function signatures from 41-03 (`poll_<p>_cspm_findings(config, account_id, tenant_id)`) matched the plan's assumed shape exactly, so the branches are pure clones of the existing microsoft365/mongodb_atlas branches.

## Deviations from Plan

None - plan executed exactly as written (test-file placement used the plan's own pre-authorized alternative, not a deviation).

## Issues Encountered

During Task 3 verification, a stray `git stash --include-untracked` was run to test something and immediately reverted with `git stash pop stash@{0}` — no data was lost (verified `git status` file count and my own commits/files were unaffected before continuing) and the two other worktrees' pre-existing stash entries (`stash@{1}`, `stash@{2}` at the time) were left untouched. Flagging for transparency even though no lasting effect occurred.

Task 3's full-suite run (`cd backend && venv/bin/python -m pytest -q`) hit 2 collection errors from files unrelated to phase 41, at the backend root (not `backend/tests/`): `test_ai_service_config.py` (imports `_init_db` from `database`, which does not exist — file untouched since Phase 16 per `git log`) and `test_network_endpoint.py` (a live network smoke script that gets HTTP 401 from an external endpoint). Both files are unmodified relative to `HEAD~2` (confirmed via `git diff HEAD~2 -- <file>` returning empty), so they predate this plan's commits and are unrelated to it. Re-ran with `--ignore=test_ai_service_config.py --ignore=test_network_endpoint.py` to get an actual pass/fail count: **1311 passed / 34 skipped / 5 failed**. All 5 failures confirmed pre-existing and unrelated to phase 41 files (`cloud_checks_*`, `*_ingest.py`, `cloud_accounts_service.py`):
- `test_webhook_logic.py::TestWebhookLogic::test_jira_intent_parsing` / `test_zoho_intent_parsing` — `RuntimeError: Database not connected` (reproduces in isolation; environmental, needs a live MongoDB connection this sandbox session doesn't have)
- `tests/test_agentic_ai.py::TestRunCallsAnthropicWithToolChoiceAny::test_run_calls_anthropic_with_tool_choice_any` — asserts the Anthropic SDK call's `tool_choice` has no extra keys, but the installed SDK now adds `disable_parallel_tool_use: True` by default (SDK version drift, unrelated to phase 41)
- `tests/test_e2e_integration.py::test_golden_path_evidence_to_remediation` — known pre-existing failure per the Phase 40 baseline noted in this plan's Task 3 instructions
- `tests/test_rust_heartbeat_parity.py::test_rust02_and_rust03_db_calls` — known pre-existing failure per the Phase 40 baseline (same `agent_type` push-array gap noted in Phase 39's session log)

All 5 reproduce identically when run in isolation (ruling out order-dependency introduced by the new tests) and touch files with zero diff since before this plan's commits.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- CSPM-01/02/03 are now fully wired end-to-end: catalogs (41-01) + ingest functions (41-03) + scan dispatch (this plan) all connect. Phase 41 (CSPM Provider Expansion — OCI, Alibaba, Cloudflare) is now complete across all 5 plans.
- No blockers for Phase 42 (Comment Threads on Compliance Controls), which is structurally isolated per the v3.2 roadmap.

---
*Phase: 41-cspm-provider-expansion-oci-alibaba-cloudflare*
*Completed: 2026-07-20*

## Self-Check: PASSED

- FOUND: backend/cloud_accounts_service.py
- FOUND: backend/tests/test_cloud_findings_ingest.py
- FOUND: c4d55cb (Task 1 commit)
- FOUND: 0fd2c7c (Task 2 commit)
