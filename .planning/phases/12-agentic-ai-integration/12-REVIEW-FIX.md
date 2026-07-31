---
phase: 12-agentic-ai-integration
fixed_at: 2026-07-03T00:00:00Z
review_path: .planning/phases/12-agentic-ai-integration/12-REVIEW.md
iteration: 1
findings_in_scope: 11
fixed: 10
skipped: 1
status: partial
---

# Phase 12: Code Review Fix Report

**Fixed at:** 2026-07-03T00:00:00Z
**Source review:** .planning/phases/12-agentic-ai-integration/12-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 11 (4 Critical, 7 Warning — `fix_scope: critical_warning`, the 2 Info findings were explicitly excluded per instructions)
- Fixed: 10
- Skipped: 1

## Fixed Issues

### CR-01: `truncate_security_context()` crashes on real MongoDB documents, and the crash bypasses the fallback/audit path entirely

**Files modified:** `backend/agentic_service.py`
**Commit:** `cbf66e8`
**Applied fix:** `estimate_tokens()` now calls `json.dumps(obj, default=str)` so any residual non-JSON-safe value (BSON datetime, etc.) is coerced to a string instead of raising. `truncate_security_context()` now strips the `_id` (ObjectId) key from every `findings`/`alerts`/`processes` item before any further processing. The call to `truncate_security_context()` in `AgenticService.run()` was moved from before the `try` block to inside it, so any exception from context truncation now flows through the same rule-based-fallback + audit-logging path as every other failure mode, matching the module docstring's contract.

### CR-02: LLM-supplied `agent_id` is trusted and dispatched without validation against the caller's actual target agent

**Files modified:** `backend/agentic_service.py`
**Commit:** `e45f7d2`
**Applied fix:** `decide_and_execute()` now compares `decision.agent_id` (model-echoed, untrusted) against the `agent_id` parameter (caller-supplied, trusted) after Pydantic validation. A mismatch raises `ValueError` (routed through the existing rule-based fallback in `run()`) and is logged as a warning. The tool executor is now always invoked with the trusted `agent_id` explicitly (`executor(agent_id=agent_id, **dispatch_kwargs)`), with `agent_id` excluded from the model-derived kwargs, so the model-echoed value can never reach the dispatcher even if the equality check were bypassed.

### CR-03: Agent execution results are never linked back to the AI decision — `report_agentic_task_result` silently no-ops

**Files modified:** `backend/agentic_service.py`, `backend/agentic_tasks_endpoints.py`
**Commit:** `ff93b09`
**Applied fix:** `AgenticService.run()` now adds `decision_id` to the dict it returns. `get_agentic_tasks()` in the endpoints file reads `result.get("decision_id")`, stores it on the newly created `agent_tasks` document, and — if present — immediately runs `db.agent_ai_decisions.update_one({"_id": decision_id}, {"$set": {"task_id": task_id}})` to write the correlating `task_id` onto the audit record. `report_agentic_task_result`'s existing filter `{"agent_id": agent_id, "task_id": task_id}` now matches, since `agent_ai_decisions.task_id` is populated at task-creation time.

**Note:** This is a functional-correctness / data-integrity fix (linking two collections). Verified via syntax check, full re-read, and the existing test suite (`test_agentic_ai.py`, 8/8 passing), but the correlation write path (`db.agent_ai_decisions.update_one` on task creation) is not exercised by any existing test — **recommend a human/manual pass exercising `GET .../agentic-tasks` followed by `POST .../result` end-to-end (or adding a regression test) to confirm the `agent_ai_decisions` document actually gets `task_id` set and `report_agentic_task_result` matches it**, since Tier 1/2 verification (syntax/re-read) cannot confirm the runtime Mongo behavior.

### CR-04: `_log_decision()` calls `get_database()` outside its own `try/except`, so a DB-unavailable condition raises instead of being logged

**Files modified:** `backend/agentic_service.py`
**Commit:** `16f4441`
**Applied fix:** `db = get_database()` in `_log_decision()` is now wrapped in its own `try/except Exception`, logging `"AUDIT WRITE FAILURE ... (db unavailable)"` and returning early instead of letting `RuntimeError` propagate. The dead `if not db:` check (which could never trigger, since `get_database()` never returns falsy) was removed.

### WR-01: `tenant_id` in `get_agentic_tasks()` is computed from the wrong dict keys and always evaluates to `""`

**Files modified:** `backend/agentic_tasks_endpoints.py`
**Commit:** `f105b95`
**Applied fix:** `tenant_id = _tenant.get("tenant_id") or _tenant.get("tenantId") or ""` changed to `_tenant.get("id") or _tenant.get("tenant_id") or _tenant.get("tenantId") or ""`, matching `verify_agent_key()`'s actual return shape (the tenant document keys its identifier under `"id"`).

### WR-03: Audit doc hardcodes `"model": "claude-sonnet-4-6"` even when no model call occurred

**Files modified:** `backend/agentic_service.py`
**Commit:** `3d0eb65`
**Applied fix:** `"model"` field in the `agent_ai_decisions` doc is now `"claude-sonnet-4-6" if result.get("source") == "agentic_ai" else None`, so fallback-sourced records no longer misrepresent the decision as LLM-made.

### WR-04: Inconsistent naive vs. timezone-aware timestamps across the audit trail

**Files modified:** `backend/agentic_service.py`
**Commit:** `f738075`
**Applied fix:** Both `started_at` (in `run()`) and `completed_at` (in `_log_decision()`) now use `datetime.datetime.now(datetime.timezone.utc)` instead of the deprecated naive `datetime.datetime.utcnow()`, matching the timezone-aware format already used in `agentic_tasks_endpoints.py`.

### WR-05: Default OTLP exporter endpoint uses the gRPC port with an HTTP exporter

**Files modified:** `backend/app_startup.py`
**Commit:** `40ec356`
**Applied fix:** Default `PHOENIX_OTLP_ENDPOINT` changed from `http://localhost:4317` (gRPC port) to `http://localhost:4318/v1/traces` (conventional HTTP OTLP endpoint), matching the `opentelemetry.exporter.otlp.proto.http` exporter actually imported.

### WR-06: `TOOLS` schema advertises a default that is never applied

**Files modified:** `backend/agentic_service.py`
**Commit:** `f5632d2`
**Applied fix:** `_dispatch_vulnerability_scan()` now applies `severity_threshold = severity_threshold or "medium"` explicitly before building the payload, so the queued instruction always carries a `severity_threshold`, matching what the JSON Schema `"default": "medium"` documents to callers.

### WR-07: Dead/misleading falsy checks on `get_database()`'s return value

**Files modified:** `backend/agentic_tasks_endpoints.py`
**Commit:** `69efc79`
**Applied fix:** Removed the three `if db else []` conditionals on the `compliance_findings`/`alerts`/`process_snapshots` queries in `get_agentic_tasks()` — `get_database()` never returns a falsy value (confirmed alongside CR-04), so these were dead code implying a handled failure mode that doesn't exist. The real failure mode (`RuntimeError` from a disconnected DB) is still correctly handled by the route's outer `try/except Exception`.

## Skipped Issues

### WR-02: `agent_id` path parameter is not scoped to the authenticated caller — cross-agent access on all agent-key routes

**File:** `backend/agentic_tasks_endpoints.py:35-105, 164-205`; `backend/agent_auth.py:11-52`
**Reason:** This is not a locally-fixable code defect — it is a gap in the shared `verify_agent_key()` authentication primitive (`backend/agent_auth.py`), which authenticates a **tenant** (via `X-Tenant-Key` or a JWT whose payload carries only `tenant_id` + `jti`), not a specific **agent**. Confirmed by inspection: the JWT payload has no agent-identity claim anywhere in the codebase, and `verify_agent_key()` is reused as-is (unmodified by this phase) across at least 8 other route files (`agent_chat_endpoints.py`, `agent_telemetry_endpoints.py`, `agent_security_endpoints.py`, `agent_heartbeat_endpoints.py`, `agent_tasks_endpoints.py`, `agent_core_endpoints.py`, `edr_telemetry_endpoints.py`), all of which have the identical tenant-only-scoping limitation. Properly fixing this (per the review's own two suggested options — embedding agent identity in the JWT at token-issuance time, or restricting the route to platform-internal callers) requires either a broader token-issuance change spanning files well outside this phase's reviewed set, or would break the Rust agent's actual polling use case if routes were restricted to platform-internal callers only. Applying a narrow, one-off fix to only `agentic_tasks_endpoints.py` would make this endpoint inconsistent with every sibling agent-key route without closing the underlying gap (a compromised/malicious agent credential could still reach the other 8 files unaffected). Recommend tracking as a standalone security-hardening task scoped to `agent_auth.py`'s token-issuance flow, touching all consumers of `verify_agent_key()` consistently, rather than a single-finding fix in this pass.
**Original issue:** `verify_agent_key()` authenticates a tenant, not a specific agent. Nothing in `get_agentic_tasks()` or `report_agentic_task_result()` checks that the calling credential actually belongs to the `agent_id` in the URL path — any agent (or holder of a tenant registration key) can trigger a decision cycle or POST a fabricated result for an arbitrary `agent_id` within the tenant.

---

**Out of scope (not attempted per `fix_scope: critical_warning`):**
- IN-01: Test suite does not exercise the code paths behind CR-01/CR-04
- IN-02: OpenTelemetry SDK/API packages are not pinned directly

_Fixed: 2026-07-03T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
