---
phase: 12
plan: 01
status: complete
completed_at: 2026-06-23
---

# Phase 12 — Plan 01 SUMMARY: Agentic AI Service — Backend TDD

## What Was Built

### Files Created
- **`backend/agentic_service.py`** (491 lines) — `AgenticService` class with two-turn Claude tool-calling, 5 security capability tools (TOOLS + TOOL_REGISTRY), `AgenticDecision` Pydantic model (Literal enum validation), `truncate_security_context()`, `_rule_based_fallback()` (collect_processes), circuit-breaker at key `"agentic_ai"`, `_log_decision()` with "AUDIT WRITE FAILURE" ERROR logging, `get_agentic_service()` singleton.
- **`backend/agentic_tasks_endpoints.py`** (175 lines) — FastAPI router at `/api/agents` prefix. Routes: GET `/{agent_id}/agentic-tasks` (runs AgenticService inline), GET `/{agent_id}/agentic-tasks/decisions`, POST `/{agent_id}/agentic-tasks/trigger`, POST `/{agent_id}/agentic-tasks/{task_id}/result`. Static routes registered before parameterized (path collision prevention).
- **`backend/tests/test_agentic_ai.py`** (414 lines) — 8 unit tests covering AI-01 through AI-04 using synchronous TestClient + AsyncMock, no pytest-asyncio.

### Files Modified
- **`backend/database.py`** — 4 new indexes on `agent_ai_decisions`: `agent_ai_decisions_agent_time_idx`, `agent_ai_decisions_tool_idx`, `agent_ai_decisions_tenant_time_idx`, `agent_ai_decisions_source_idx`. No TTL per SOC 2 CC6.1.
- **`backend/router_registry.py`** — `_load(app, "agentic_tasks_endpoints", "router")` in AI & Data Science section. NOT in `_REQUIRED_ROUTERS` (graceful degradation per AI-04).

## Test Results

All 8 tests pass GREEN:
- `test_tool_registry_complete` — 5 tools in TOOLS and TOOL_REGISTRY ✓
- `test_run_calls_anthropic_with_tool_choice_any` — two-turn loop with tool_choice={"type":"any"} ✓
- `test_stop_reason_guard_triggers_fallback` — end_turn → rule_based_fallback ✓
- `test_hallucinated_tool_rejected` — unregistered tool → fallback (not 500) ✓
- `test_pydantic_validation_rejects_bad_input` — Literal enum rejects invalid names ✓
- `test_log_decision_writes_required_fields` — all 9 required fields non-null ✓
- `test_audit_write_failure_is_logged_not_suppressed` — AUDIT WRITE FAILURE logged at ERROR ✓
- `test_circuit_breaker_open_activates_fallback` — CircuitBreakerOpen → rule_based_fallback ✓

## Implementation Decisions

- **Inline AI execution on GET**: AgenticService.run() is called synchronously on the GET request rather than pre-queuing tasks. The Rust agent polls every 60s so latency is acceptable, and this avoids stale task state management.
- **`_log_decision` awaited directly**: The audit write is in the same request cycle as the decision, not a BackgroundTask. Ensures the audit record is committed before the Rust agent receives the task.
- **Dispatcher via agent_instructions**: TOOL_REGISTRY dispatchers write `agent_instructions` documents, queuing the capability for the Rust agent's existing instruction poll channel.
- **Empty return on RuntimeError**: If `ANTHROPIC_API_KEY` is unset, GET endpoint returns `[]` instead of erroring — agent skips the cycle cleanly.

## Deviations from AI-SPEC / PLAN.md

None. All specified constraints met:
- Circuit-breaker key `"agentic_ai"` (not `"ai"`)
- `tool_choice={"type": "any"}` (not `"auto"`)
- TenantIsolatedCollection tenantId NOT set manually
- Static routes before parameterized in router
- `_log_decision` never re-raises

## Self-Check: PASSED

```
8/8 tests pass
agentic_service.py: 491 lines (< 500 limit)
agentic_tasks_endpoints.py: 175 lines (< 500 limit)
No Co-Authored-By in commits
agent_ai_decisions: 4 indexes in database.py
router registration in router_registry.py AI section
```
