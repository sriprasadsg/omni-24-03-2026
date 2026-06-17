---
phase: 01-rust-agent-evidence-parity
plan: "02"
subsystem: backend/tests
tags:
  - rust-agent
  - compliance-evidence
  - heartbeat
  - simulation-test
dependency_graph:
  requires:
    - 01-01 (process_automated_evidence with agent_type param, direct import fix)
  provides:
    - backend/tests/test_rust_heartbeat_parity.py — acceptance test for RUST-01/02/03
  affects:
    - backend/tests/test_rust_heartbeat_parity.py
tech_stack:
  added: []
  patterns:
    - pytest unit test with AsyncMock DB mocking
    - Dual-mode test (pytest unit + standalone live-backend __main__ script)
key_files:
  created:
    - backend/tests/test_rust_heartbeat_parity.py
  modified: []
decisions:
  - "Wrote pytest unit test (not standalone script) as primary test mode — live backend not available in CI environment"
  - "Combined RUST-02 and RUST-03 into one test function to stay within 200-line limit"
  - "Retained __main__ entrypoint for live end-to-end smoke testing against running backend"
metrics:
  duration: "~3 minutes"
  completed: "2026-06-17"
  tasks_completed: 1
  tasks_total: 2
  files_modified: 1
---

# Phase 01 Plan 02: Rust Agent Heartbeat Simulation Test Summary

**One-liner:** Pytest unit test directly calls process_automated_evidence with a 12-check Rust payload and mocked DB, asserting agent_type="rust" in every $set call and all 9 representative control IDs are written.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create Rust heartbeat simulation test script | 9549aef | backend/tests/test_rust_heartbeat_parity.py |

## Task 2 (Checkpoint)

Task 2 is a `checkpoint:human-verify` — paused for human verification. See Checkpoint Details below.

## What Was Built

### backend/tests/test_rust_heartbeat_parity.py (196 lines)

Three sections:

**Configuration (lines 1–15):** Module-level constants for BASE_URL, MONGO_URI, DB_NAME, TEST_AGENT_ID, TEST_HOSTNAME, TEST_ASSET_ID — all overridable via env vars.

**Payload (lines 16–67):** `RUST_HEARTBEAT_PAYLOAD` with all 12 Rust compliance check names (Windows Firewall Profiles, Windows Defender Antivirus, BitLocker Encryption, User Access Control, Remote Desktop Service, SMBv1 Protocol Disabled, Password Policy (Min Length), Audit Logging Policy, Windows Update Service, PowerShell Script Block Logging, WinRM Status, Secure Boot). `CHECK_TO_CONTROL` dict maps 9 check names to representative control IDs for RUST-03 verification.

**pytest unit tests (lines 68–130):**
- `test_rust01_processor_is_importable`: Imports `process_automated_evidence` from `compliance_evidence_processor` directly — verifies RUST-01 (direct import path works).
- `test_rust02_and_rust03_db_calls`: Runs the full function against a mocked AsyncMock DB. Asserts every `$set` block in `update_one` calls contains `agent_type="rust"` (RUST-02) and all 9 representative control IDs appear as filters (RUST-03).

**Live-backend mode (lines 131–196):** `main()` function for direct script execution — registers test agent, POSTs heartbeat, queries MongoDB for records, asserts agent_type and control mappings, cleans up.

## Verification Results

```
python3 -c "import ast; ast.parse(...); print('syntax ok')" → ok
Structure check: PASS (196 lines)
grep -c 'RUST-0' → 15
grep -c 'WinRM Status' → 1
pytest test_rust_heartbeat_parity.py -v
  test_rust01_processor_is_importable: PASSED
  test_rust02_and_rust03_db_calls: PASSED
  2 passed in 0.19s
```

## Deviations from Plan

### Adaptation — Unit test instead of pure standalone script

**Found during:** Task 1 execution

**Issue:** The plan specified a standalone script (`python3 backend/tests/test_rust_heartbeat_parity.py`) requiring a live server. The important_note in the execution context explicitly directed unit testing with mocked DB when live infrastructure is unavailable.

**Fix:** Wrote as a pytest module (`test_*.py`) compatible with the project's existing test suite (conftest.py, pytest.ini). The `process_automated_evidence` function is called directly with a mocked async MongoDB DB — no HTTP server required. The `__main__` entrypoint is retained for live backend verification.

**Files modified:** backend/tests/test_rust_heartbeat_parity.py

### Consolidation — RUST-02 and RUST-03 merged into one test function

**Found during:** Line-count check (207 lines exceeded 200 limit)

**Issue:** Two separate test functions for RUST-02 and RUST-03 pushed the file to 207 lines.

**Fix:** Combined into `test_rust02_and_rust03_db_calls` — the assertions share the same DB mock run, which is correct (both verify the same `update_one` call list). No assertion coverage lost.

## Checkpoint: human-verify (Task 2)

This plan includes a `checkpoint:human-verify` task for live backend validation. The automated checks (Task 1) are complete and committed. To verify end-to-end:

```bash
# Static checks (no server needed):
python3 -c "import ast; ast.parse(open('backend/tests/test_rust_heartbeat_parity.py').read()); print('ok')"
python3 -m pytest backend/tests/test_rust_heartbeat_parity.py -v

# Live backend (requires running backend + MongoDB):
python3 backend/tests/test_rust_heartbeat_parity.py
```

## Requirements Satisfied

| Requirement | Status |
|-------------|--------|
| RUST-01 | Verified — direct import from compliance_evidence_processor works (test_rust01) |
| RUST-02 | Verified — agent_type=rust in all $set calls (test_rust02_and_rust03) |
| RUST-03 | Verified — all 9 representative control IDs present in update_one call filters |

## Threat Flags

None — test utility only, reads from env vars, no hardcoded credentials, test data cleaned up in main().

## Self-Check: PASSED

- [x] backend/tests/test_rust_heartbeat_parity.py exists (196 lines)
- [x] Commit 9549aef exists
- [x] Both pytest tests pass (2 passed, 0 failed)
- [x] All 12 check names present in payload
- [x] agent_type assertion logic present
- [x] asset_compliance collection referenced
- [x] RUST-01, RUST-02, RUST-03 all referenced (15 occurrences)
