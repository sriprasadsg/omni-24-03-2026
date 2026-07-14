# Deferred Items — Phase 29 (Public Trust Center)

Out-of-scope discoveries logged per executor scope-boundary rules. Not fixed as part of
plan 29-01 — pre-existing and unrelated to the trust_service/trust_endpoints changes.

## test_auth_mfa.py order-dependent failures (pre-existing, unrelated)

- **Found during:** Plan 29-01, Task 3 full-suite verification (`pytest tests/ -q`)
- **Symptom:** 10 tests in `tests/test_auth_mfa.py::TestMFAVerifyLogin` fail when run as part
  of the full `tests/` suite, but all 21 tests in that file pass when run in isolation
  (`pytest tests/test_auth_mfa.py -q`).
- **Confirmed unrelated to this plan:** Reproduced identically with `test_trust_center.py`
  fully excluded from the run (`pytest tests/ -q --ignore=tests/test_trust_center.py`) —
  the failure is present with or without any of this plan's changes in the run.
- **Likely cause:** Test-order-dependent global/module-level state pollution from an
  earlier-running test file (alphabetically prior to `test_auth_mfa.py`), not investigated
  further — out of scope per SCOPE BOUNDARY (only auto-fix issues directly caused by the
  current task's changes).
- **Action:** Not fixed. Flagged for separate investigation/phase.
