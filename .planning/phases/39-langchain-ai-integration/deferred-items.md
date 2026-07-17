# Deferred Items — Phase 39 (LangChain AI Integration)

Pre-existing issues discovered while verifying no regression from 39-01's dependency install.
Out of scope per execute-plan.md's SCOPE BOUNDARY (not caused by this plan's changes) — logged,
not fixed.

## Discovered during 39-01 (2026-07-18) full-suite regression check

All items below reproduce identically on the pre-39-01 tree (confirmed by isolating each file/test
and observing failures are either environmental — no live network/MongoDB in this sandbox — or
order-dependent, not related to `backend/requirements.txt`'s new LangChain pins).

1. **`backend/test_ai_service_config.py`, `backend/test_network_endpoint.py`, `backend/test_sbom_api.py`**
   — collection-time `ConnectError`/`URLError` (these files make live network calls at import time).
   Requires network access unavailable in this sandbox. Pre-existing, unrelated to LangChain install.

2. **`backend/test_log_heartbeat.py::test_heartbeat_logs`, `backend/test_virustotal.py::test_vt`**
   — `ConnectError`/`ConnectionError` to live external services. Same root cause as (1).

3. **`backend/test_webhook_logic.py::test_jira_intent_parsing`, `::test_zoho_intent_parsing`**
   — `RuntimeError: Database not connected` — these tests need a live MongoDB connection not
   running in this sandbox.

4. **`backend/tests/test_agentic_ai.py` (6 tests)** — pass individually (`8 passed` in isolation)
   but fail with `RuntimeError: There is no current event loop in thread 'MainThread'` when run as
   part of the full suite. Order-dependent flake, same class as the previously-documented
   `test_auth_mfa.py` flake (see STATE.md session 2026-07-14). Not related to LangChain.

5. **`backend/tests/test_e2e_integration.py::test_golden_path_evidence_to_remediation`,
   `backend/tests/test_rust_heartbeat_parity.py::test_rust02_and_rust03_db_calls`** — reproduce in
   isolation too: pushed evidence dict is missing `agent_type` key even though the calling code
   sets it. Pre-existing product/test bug unrelated to this plan's file (`backend/requirements.txt`
   only) — not investigated further per scope boundary.

**Net result for 39-01:** isolating every failing file individually shows identical failures with
or without the new LangChain pins — none of the 12 full-suite failures are caused by the packages
installed in this plan. Confirmed via `import app_startup` (clean import, only expected dev-mode
JWT_SECRET_KEY warning) and the plan's own documented import-verification command (`OK 1.3.14`).
