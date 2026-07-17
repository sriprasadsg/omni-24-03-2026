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

## Discovered during 39-04 (2026-07-18) full-suite regression check

Items 1-5 above still reproduce identically. One new observation, unrelated to this plan's three
new files (`backend/ai_orchestration/models.py`/`memory.py`/`tracing.py`) or its `app_startup.py`
edit (confirmed: none of the files below import `app_startup` or `ai_orchestration`):

6. **`backend/tests/eval_langchain/test_router_passthrough.py::test_router_tool_and_response_format_passthrough`**
   — in this session's sandbox, `AI_ROUTER_URL` now resolves to a real value (via `.env`, not
   readable/writable by this session) by the time this module is collected in a full-suite run, so
   the test's `skipif(not AI_ROUTER_URL, ...)` guard no longer skips it — it attempts a live
   `ainvoke()` against the router and fails with an OpenAI-client-wrapped connection/HTTP error.
   Run in isolation (`pytest tests/eval_langchain/test_router_passthrough.py`) it still cleanly
   skips. This is an environmental difference in this sandbox session, not a regression introduced
   by 39-04 — `models.py`'s router-provider builder never sets/mutates `AI_ROUTER_URL`, and this
   test file is untouched by this plan. Per 39-02-SUMMARY.md, the 9router
   `response_format`/tool-calling passthrough decision therefore remains genuinely unresolved and
   should be re-run deliberately (`pytest tests/eval_langchain/test_router_passthrough.py -m "eval and llm" -q`)
   in an environment where `AI_ROUTER_URL` reachability is intentional and controlled, not
   incidental to full-suite collection order.

**Net result for 39-04:** `backend/venv/bin/python -m pytest backend/tests/test_ai_orchestration_infra.py -q`
is 25/25 green (all three per-task `-k models`/`-k memory`/`-k tracing` verify commands pass), `cd
backend && venv/bin/python -c "import app_startup"` exits 0, and the full suite's 13 failures (items
1-6) are confirmed pre-existing/environmental and unrelated to this plan's changes.
