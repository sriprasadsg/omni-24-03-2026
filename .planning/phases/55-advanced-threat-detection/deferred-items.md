# Phase 55 — Deferred Items

Out-of-scope discoveries logged during execution, per the executor's scope-boundary rule
(only auto-fix issues directly caused by the current task's changes; pre-existing issues
in unrelated files are logged here, not fixed).

## 55-01

### 1. `backend/virustotal_client.py` — pre-existing broken import (`NameError: name 'BaseCapability' is not defined`)

- **Found during:** Task 2 (companion `/api/threat-intel/correlate-native` route) — sanity-checked
  `import threat_intel_endpoints` and hit this transitively via `from virustotal_client import
  get_virustotal_client`.
- **Root cause:** `virustotal_client.py` line 7 defines `class VirusTotalScanCapability(BaseCapability):`
  but nothing in the file (or its imports) defines/imports `BaseCapability` — no `BaseCapability`
  class exists anywhere in the codebase (`grep -rln "class BaseCapability"` returns nothing).
- **Confirmed pre-existing:** `git diff --stat virustotal_client.py` shows zero changes from this
  session; last touched by an unrelated prior commit (`8df0bdf`, "wip: pause — 54-01-PLAN.md...").
  Not caused by, and not in the file list of, plan 55-01.
- **Why not fixed:** Out of this plan's file scope (`backend/siem_engine.py`,
  `backend/threat_intel_endpoints.py`, `backend/tests/test_siem_engine.py` only). The existing
  test suite already works around it (`tests/test_fim_events_rich.py` stubs `sys.modules
  ["virustotal_client"]` before importing the endpoint module it needs), and `router_registry.py`
  loads `threat_intel_endpoints` as a non-required router, so this does not currently break app
  startup or the full test suite (`threat_intel_endpoints` was never directly imported by any
  passing test before this session either).
- **Impact:** Directly importing `threat_intel_endpoints` in a bare Python REPL/script (not via
  pytest, which never imports it at module scope in the passing suite) raises `NameError` at
  import time. The new `/api/threat-intel/correlate-native` route is syntactically correct and
  covered indirectly via `SiemEngine.correlate_native_findings()`'s own direct tests
  (`test_siem_engine.py`), but has no live `TestClient` HTTP-level test in this plan because the
  module cannot be imported standalone until `virustotal_client.py` is fixed.
- **Recommendation:** A future phase/cleanup pass should either define a minimal `BaseCapability`
  base class `VirusTotalScanCapability` can extend, or drop the unused capability-class wrapper
  and keep only the module-level `get_virustotal_client()`/scan functions the rest of the codebase
  actually calls.
- **UPDATE (55-04 phase-verification pass, 2026-08-03):** Confirmed via `gsd-verifier` +
  independent orchestrator investigation that this is deeper than the `BaseCapability` NameError
  alone. `virustotal_client.py` is 121 lines total and defines ONLY `VirusTotalScanCapability` —
  the `get_virustotal_client()` factory that `threat_intel_endpoints.py`, `threat_endpoints.py`,
  and `soar_engine.py` all actually import and call **does not exist anywhere in the file**
  (confirmed by stubbing a fake `BaseCapability` and executing the module: it runs clean, but
  `get_virustotal_client` is absent from its namespace). `VirusTotalScanCapability.collect()` is
  separately broken too — it references `requests`/`psutil`/`hashlib`/`socket`/`subprocess`/`re`/
  `logger`, none imported in this file. Fixing the NameError alone would only change the failure
  to `ImportError: cannot import name 'get_virustotal_client'`. This is missing-feature
  implementation work (a real client factory + whatever scan interface the three callers expect),
  not a one-line fix — flagged as its own gap in `55-VERIFICATION.md`, left open for a user
  decision rather than fixed as part of phase 55.

### 2. Full backend suite baseline (re-run at end of 55-01)

`cd backend && venv/bin/python -m pytest -q --ignore=tests/test_graphql.py --ignore=test_ai_service_config.py --ignore=test_network_endpoint.py --ignore=test_sbom_api.py` →
**1525 passed / 34 skipped / 5 failed**, all failures pre-existing and unrelated to this plan's files:
- `test_webhook_logic.py::TestWebhookLogic::test_jira_intent_parsing` / `test_zoho_intent_parsing` —
  fail in isolation too (`RuntimeError: Database not connected`), an order-dependent test that
  needs a live Mongo connection normally provided earlier in full-suite fixture order.
- `tests/test_agentic_ai.py::TestRunCallsAnthropicWithToolChoiceAny` — pre-existing
  `tool_choice` shape drift (`disable_parallel_tool_use` key added upstream).
- `tests/test_e2e_integration.py::test_golden_path_evidence_to_remediation` — pre-existing,
  documented in project memory.
- `tests/test_rust_heartbeat_parity.py::test_rust02_and_rust03_db_calls` — pre-existing,
  documented in project memory (`agent_type` missing from a `$push.evidence` array).

4 test-collection modules were excluded entirely (pre-existing environment drift, not
this-session regressions): `tests/test_graphql.py` (strawberry/pydantic version mismatch),
`test_ai_service_config.py`, `test_network_endpoint.py` (live network calls), `test_sbom_api.py`
(live network calls).

## 55-02

### 3. `REQUIREMENTS.md` does not contain AUT-03 (or any 55-advanced-threat-detection requirement)

- **Found during:** post-execution state update (`requirements.mark-complete AUT-03`).
- **Root cause:** `.planning/REQUIREMENTS.md` currently holds a completely different, later
  requirements set (header `# Requirements: v4.0`, defined 2026-07-31, requirements SCALE-*/SEC-*/
  UX-*/SIEM-*) that was written over whatever v3.4 requirements set originally defined AUT-03/
  INT-04/COMM-01 for phase 55. `STATE.md`'s own frontmatter is likewise stale (`current_phase: 48`,
  `milestone: v3.4`) despite phase 55 plans 01/02 already being executed and committed — this is a
  pre-existing, project-wide STATE/REQUIREMENTS drift, not something introduced by 55-01 or 55-02.
- **Why not fixed:** Out of this plan's scope (file list: `backend/remediation_playbook_service.py`,
  `backend/tests/test_remediation_playbook.py` only). Reconciling REQUIREMENTS.md/STATE.md against
  the actual v3.4 phase 55 plan set is a project-level documentation repair, not a code deviation.
- **Impact:** `requirements.mark-complete AUT-03` returned `not_found` — no checkbox/traceability
  row exists to check off. Requirement completion is still traceable via this plan's `SUMMARY.md`
  frontmatter (`requirements-completed: [AUT-03]`) and the coverage block's test refs.
- **Recommendation:** A future housekeeping pass should reconcile `REQUIREMENTS.md` and `STATE.md`
  frontmatter against the real phase history (phases 46-55+ per `55-advanced-threat-detection/`'s
  own RESEARCH/CONTEXT docs) before starting the v4.0 cycle those files currently describe.

## 55-05 (gap closure)

### 4. `backend/test_virustotal.py` — stale manual smoke-script for a non-existent API surface

- **Found during:** 55-05 gap-closure planning (rewriting `virustotal_client.py`).
- **Root cause:** `backend/test_virustotal.py` (backend root, NOT `tests/`) is a manual dev
  smoke-test hitting `http://localhost:5000/api/threat-intelligence/config` and
  `/api/threat-intelligence/scan` — **neither endpoint exists anywhere in the codebase**
  (`grep -rn "threat-intelligence" backend/*.py` returns nothing). It references a DIFFERENT,
  never-built-or-already-removed API surface: note `threat-intelligence` vs the real
  `threat-intel` prefix in `threat_intel_endpoints.py`, and its `{"artifact","type"}` scan
  payload differs from the real `ScanRequest {"artifact","artifact_type"}`.
- **Why not fixed by 55-05:** Out of the gap's scope (the gap is `virustotal_client.py`'s missing
  `get_virustotal_client()` factory + the unmounted `/correlate-native` route). This script does
  not import `virustotal_client` and is not run by pytest (it is a `__main__` httpx script against
  a live server). Reconciling or deleting it is unrelated pre-existing drift.
- **Recommendation:** Leave as-is (pre-existing unrelated drift); a future cleanup pass may delete
  it or repoint it at the real `/api/threat-intel/*` routes.
