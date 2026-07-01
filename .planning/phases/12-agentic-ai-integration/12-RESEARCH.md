# Phase 12: Agentic AI Integration — Research

**Researched:** 2026-06-23
**Domain:** Anthropic SDK tool-calling, FastAPI async endpoints, MongoDB audit logging
**Confidence:** HIGH

---

## Summary

Phase 12 wires Claude (claude-sonnet-4-6) tool-calling into the existing agentic_poller path so the backend LLM can reason about live Windows endpoint security findings and select one of five capability tools per polling tick. The work requires: (1) a new `agentic_service.py` that owns the two-turn Anthropic SDK decision loop, (2) a new `agentic_tasks_endpoints.py` FastAPI router providing `GET /api/agents/{id}/agentic-tasks` (polled by the Rust agent) and `POST /api/agents/{id}/agentic-tasks/{id}/result`, and (3) a new `agent_ai_decisions` MongoDB collection with compound indexes for audit trail queries.

The Anthropic SDK is already installed at version 0.111.0 — well above the 0.28.0 minimum. The existing `AnthropicProvider` in `ai_providers.py` uses raw httpx and does not need to be changed; `agentic_service.py` uses `AsyncAnthropic` directly from the SDK. The circuit-breaker (`circuit_breaker.py:ai_breaker`) and `MockProvider` fallback pattern from `ai_service.py` provide the graceful-degradation model. Router registration is a one-line `_load()` call in `router_registry.py`.

**Primary recommendation:** Create `backend/agentic_service.py` with `AgenticService` (wrapping `AsyncAnthropic` + `TOOL_REGISTRY`) and `backend/agentic_tasks_endpoints.py` (new FastAPI router). Add indexes for `agent_ai_decisions` in `database.py`. Register the router via `router_registry.py`. Do not modify `ai_providers.py` or `ai_service.py`.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| LLM tool-calling decision loop | API / Backend (`agentic_service.py`) | — | Runs inside the backend agentic poller on each tick; no user-facing UI |
| Security capability dispatch | API / Backend (`agentic_tasks_endpoints.py`) | Rust agent (executor) | Backend queues the task; agent executes it on the endpoint |
| Audit logging (`agent_ai_decisions`) | Database / Storage | API / Backend | MongoDB write happens synchronously in `AgenticService._log_decision()` |
| Fallback / circuit-breaker | API / Backend (`circuit_breaker.py`) | — | Existing `ai_breaker` pattern reused in `AgenticService.run()` |
| Context assembly & truncation | API / Backend (`agentic_service.py`) | — | `truncate_security_context()` runs before every API call |
| Task result ingestion | API / Backend (`agentic_tasks_endpoints.py`) | — | Agent POSTs result to `/api/agents/{id}/agentic-tasks/{id}/result` |

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AI-01 | Backend agentic task endpoint uses Claude (claude-sonnet-4-6) with structured tool-calling to reason about the agent's security context and select which capability to invoke — replacing the current stub that ignores the LLM response | F-01 (AnthropicProvider unchanged; new AsyncAnthropic client in agentic_service.py); F-02 (AgenticService.run() two-turn loop) |
| AI-02 | Claude has access to ≥ 5 security capability tools defined as JSON tool schemas; the LLM-selected tool is dispatched to the agent via the existing instruction channel | F-02 (TOOLS list + TOOL_REGISTRY); F-03 (endpoint queues agent_instructions) |
| AI-03 | Each agentic LLM invocation is logged with reasoning chain, selected tool, input parameters, agent response, and outcome in `agent_ai_decisions` per-tenant | F-04 (document schema + indexes); F-02 (_log_decision() in AgenticService) |
| AI-04 | Agentic task path degrades gracefully when Claude API is unreachable — falls back to existing rule-based decisions | F-02 (circuit-breaker pattern from circuit_breaker.py ai_breaker + MockProvider rule-based fallback); ai_service.py circuit-breaker already proven |
</phase_requirements>

---

## Q1: What does the existing AnthropicProvider.generate() look like? What needs to change?

**File:** `backend/ai_providers.py` lines 159–177

The current implementation is a raw `httpx.AsyncClient` call to `/v1/messages`. It does NOT use the Anthropic Python SDK (`AsyncAnthropic`); it constructs headers manually and sends a plain `messages` payload with no `tools`, `tool_choice`, or `system` parameters.

```python
# ai_providers.py lines 159–177 (verbatim)
async def generate(self, prompt: str) -> str:
    if not self.api_key:
        raise RuntimeError("Anthropic API key not configured")
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model_name,
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]
```

**Decision from AI-SPEC Section 3:** `AnthropicProvider.generate()` is NOT modified in Phase 12. The AI-SPEC explicitly states: "Use the SDK client directly — not the httpx-based AnthropicProvider. The SDK handles retry, timeout, and header management automatically." The new `agentic_service.py` instantiates `AsyncAnthropic` independently and owns the tool-calling loop. `ai_providers.py` remains unchanged.

[VERIFIED: reading ai_providers.py directly]

---

## Q2: Is there an agentic_tasks_endpoints.py? Pattern for creating it?

**Finding:** `agentic_tasks_endpoints.py` does NOT exist. There is no file by that name anywhere in `backend/`. [VERIFIED: `ls /home/user/enterprise-omni-agent-ai-platform/backend/ | grep agentic` returned empty]

**Closest analogs to follow:**

1. **`backend/agent_tasks_endpoints.py`** — the primary pattern template. Uses:
   - `APIRouter(prefix="/api/agents", tags=["Agents"])` (line 13)
   - `verify_agent_key` (`from agent_auth import verify_agent_key`) for agent-authenticated POSTs
   - `get_current_user` from `authentication_service` for operator-authenticated GETs
   - `Body(...)` for JSON request bodies
   - `db = get_database()` at top of each handler (not Depends)

2. **`backend/agent_approval_endpoints.py`** — directly adjacent module with the `agentic-decisions` collection endpoints. Shows how `agentic_decisions` collection is read/written from a router in the `/api/agents` prefix family.

**The Rust agent polls:** `GET /api/agents/{id}/agentic-tasks` (agentic.rs line 84).
**The Rust agent reports results to:** `POST /api/agents/{id}/agentic-tasks/{task_id}/result` (agentic.rs line 129).
Neither endpoint exists today — both must be created in `agentic_tasks_endpoints.py`.

[VERIFIED: reading agent_tasks_endpoints.py, agent_approval_endpoints.py, agent-rust/src/agentic.rs]

---

## Q3: What MongoDB collections exist? What index pattern for agent_ai_decisions?

**Existing collections created in `database.py` `connect_to_mongo()` (lines 223–302):**
- `agents`, `assets`, `vulnerabilities`, `patches`, `security_events`, `security_cases`, `audit_logs`
- `users`, `tenants`, `roles`, `notifications`, `cloud_accounts`, `system_features`
- `compliance_evidence`, `asset_metrics`, `agent_metrics_history`, `fim_events`, `edr_telemetry`
- `threat_alerts`, `correlation_rules`, `pentest_jobs`, `tickets`, `software_inventory`
- `login_attempts`, `password_reset_tokens`, `revoked_tokens`, `report_delivery_logs`

**Existing `agentic_decisions` collection (agent_approval_endpoints.py line 256):** This is an EXISTING collection used for the human-approval workflow (agent self-reports an action needing sign-off). It is NOT the same as `agent_ai_decisions`. They are separate concerns.

**New collection `agent_ai_decisions`:** Does not exist yet. Must be created at startup.

**Index recommendation from AI-SPEC Section 4 (State Management):**
```python
# Add to database.py connect_to_mongo() after line 302
await mongodb.db.agent_ai_decisions.create_index(
    [("agent_id", 1), ("started_at", -1)]
)
await mongodb.db.agent_ai_decisions.create_index([("tool_name", 1)])
await mongodb.db.agent_ai_decisions.create_index([("tenantId", 1), ("started_at", -1)])
```

The third index (compound tenantId + started_at) is required because the `TenantIsolatedCollection` wrapper in `database.py` injects `tenantId` into all queries, so per-tenant history queries will always include it. The AI-SPEC specifies the first two; the third is the pattern applied to all high-traffic audit collections (e.g., `security_events` at line 253, `audit_logs` at line 254).

**No TTL index on `agent_ai_decisions`:** Per AI-SPEC Section 1b, "SOC 2 Type II requires that automated systems acting on behalf of tenants are logged with sufficient granularity to reconstruct events" — audit trails must not be auto-purged. Compare: `evidence_audit_log` (database.py lines 265–268) has no TTL for the same reason.

[VERIFIED: reading database.py lines 223–302 and agent_approval_endpoints.py]

---

## Q4: How does the Rust agent submit agentic task results back?

**File:** `agent-rust/src/agentic.rs` lines 128–133

The Rust agent (`execute_agentic_task` function) already constructs and sends:

```rust
// agentic.rs lines 128–133
let result_url = format!("{}/api/agents/{}/agentic-tasks/{}/result", base, id, task_id);
let _ = client.post(&result_url).bearer_auth(token)
    .json(&json!({
        "task_id": task_id,
        "status": "completed",
        "result": result,
        "completed_at": Utc::now().to_rfc3339()
    }))
    .send().await;
```

**What the agent sends as task context (Q4 — F-06 answer):**

When the Rust agent fetches pending tasks (`fetch_agentic_tasks`, line 84), it receives an array of task documents. For each task it calls `execute_agentic_task` which extracts:
- `task.id` — the task UUID (string)
- `task.type` — the task type string (e.g., `"analyse_security"`, `"compliance_check"`)
- `task.context` — arbitrary JSON object (currently anything the backend puts in the task document)

The agent then builds an `llm_ctx` JSON object (lines 101–106):
```json
{
  "task_type": "<string>",
  "context": "<task.context object>",
  "agent_version": "2.0.0-rust",
  "timestamp": "<ISO8601 RFC3339>"
}
```

This is currently POSTed to `/api/knowledge/query` (unused for agentic purposes — line 109). In Phase 12, the backend endpoint that serves `agentic-tasks` will embed the pre-assembled `security_context` (findings, alerts, processes) directly in the task's `context` field so the Rust agent never needs to construct it — the backend's `agentic_service.py` reads it and calls Claude.

**Result payload the backend endpoint receives:**
```json
{
  "task_id": "<UUID>",
  "status": "completed",
  "result": { /* capability-specific output */ },
  "completed_at": "<ISO8601 RFC3339>"
}
```

[VERIFIED: reading agent-rust/src/agentic.rs lines 83–133]

---

## Q5: What is the existing router registration pattern in app_startup.py?

**Correction:** Router registration is NOT in `app_startup.py`. That file handles: config validation, database seeding, background task launch. Startup calls `run_startup_services()` and `seed_database()`.

**Router registration is in `backend/router_registry.py`**, called once from `backend/app.py` line 157:
```python
from router_registry import register_all_routers
register_all_routers(app)
```

**The `_load()` helper (router_registry.py lines 26–42)** is the standard pattern:
```python
def _load(app: FastAPI, module_name: str, attr: str = "router", **kwargs) -> None:
    try:
        mod = importlib.import_module(module_name)
        app.include_router(getattr(mod, attr), **kwargs)
        logger.debug("[Router] Loaded %s", module_name)
    except Exception as exc:
        logger.error("[Router] Failed to load %s: %s", module_name, exc)
        if module_name in _REQUIRED_ROUTERS:
            raise
```

**To register the new `agentic_tasks_endpoints` router**, add one line in the "AI & Data Science" section of `router_registry.py` (around line 137):
```python
_load(app, "agentic_tasks_endpoints", "router")
```

The module is NOT listed in `_REQUIRED_ROUTERS`, so a load failure will log an error but not abort startup (appropriate for an optional AI feature that degrades gracefully). [VERIFIED: reading router_registry.py lines 1–303 and app.py lines 156–157]

---

## Q6: Does ai_service.py already have circuit-breaker + fallback that can be reused?

Yes. The circuit-breaker pattern is fully implemented and reusable.

**`circuit_breaker.py` provides:**
- `CircuitBreaker` class (lines 34–84): async context manager, CLOSED → OPEN → HALF_OPEN state machine
- `CircuitBreakerOpen` exception (lines 27–30)
- Pre-built `ai_breaker = CircuitBreaker("ai_provider", failure_threshold=5, recovery_timeout=30)` (line 99)

**`ai_service.py` uses it (lines 228–234):**
```python
async with ai_breaker:
    response = await provider.generate(prompt)
break
except CircuitBreakerOpen as cb_err:
    last_err = cb_err
    logger.warning("[AI] Circuit breaker open: %s", cb_err)
    break  # Do not retry when the circuit is open
```

**For `agentic_service.py`, the pattern is:**
1. Instantiate a SEPARATE `agentic_breaker = CircuitBreaker("agentic_ai", failure_threshold=3, recovery_timeout=60)` — distinct from `ai_breaker` so agentic failures don't affect the chat/incident-analysis path.
2. Wrap the `AsyncAnthropic` call inside `async with agentic_breaker:`
3. On `CircuitBreakerOpen`, catch and activate rule-based fallback (log `source: "rule_based_fallback"`).
4. The rule-based fallback is identical to what the Rust agent currently does in `execute_agentic_task` (agentic.rs lines 117–126): match on `task_type` and dispatch a fixed capability.

**What is NOT reusable from ai_service.py:** The `IncidentAnalyzer`, `MockProvider`, `OmniLocalProvider` chain. `agentic_service.py` only uses `AsyncAnthropic` directly (not the provider abstraction) because tool-calling requires the SDK client, not the httpx-based provider.

[VERIFIED: reading circuit_breaker.py and ai_service.py lines 228–234]

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `anthropic` (AsyncAnthropic) | 0.111.0 (installed) | Tool-calling LLM client | Only client with native ToolUseBlock parsing; already in requirements.txt |
| `pydantic` | Already installed (FastAPI dep) | `AgenticDecision` validation | Catches hallucinated tool names before dispatch |
| `motor` (via `database.py`) | Already installed | Async MongoDB for `agent_ai_decisions` | All collections use Motor through the existing `TenantIsolatedDatabase` wrapper |
| `fastapi` | Already installed | `agentic_tasks_endpoints.py` router | Matches entire backend; no new dependency |

### No New Dependencies Required
The Anthropic SDK at 0.111.0 provides `AsyncAnthropic`, `ToolUseBlock`, `ToolParam`, `MessageParam` — all imports needed. `requirements.txt` already specifies `anthropic>=0.28.0,<2.0.0`. No pip install needed.

[VERIFIED: pip show anthropic returned 0.111.0]

---

## Package Legitimacy Audit

No new packages are introduced in Phase 12. The `anthropic` package is already installed (0.111.0) and is from the official Anthropic SDK. No additional `pip install` commands are required.

| Package | Registry | Age | Verdict | Disposition |
|---------|----------|-----|---------|-------------|
| `anthropic` | PyPI | 3+ yrs | OK (official Anthropic SDK) | Already installed — no action |

**Packages removed due to SLOP verdict:** none
**Packages flagged as suspicious:** none

---

## Architecture Patterns

### System Architecture Diagram

```
Rust Agent (60s tick)
       |
       | GET /api/agents/{id}/agentic-tasks  (verify_agent_key)
       v
agentic_tasks_endpoints.py
       |
       | Assembles security_context from DB (agent findings, alerts, processes)
       | (or reads pre-built context stored in agent_ai_tasks collection)
       |
       v
agentic_service.AgenticService.run(agent_id, security_context)
       |
       |-- Turn 1: AsyncAnthropic.messages.create(tools=TOOLS, tool_choice="any")
       |           |
       |           |-- circuit breaker OPEN? --> rule_based_fallback()
       |                                         log source="rule_based_fallback"
       |           |
       |           v
       |   ToolUseBlock (tool_name, tool_input)
       |           |
       |   Pydantic AgenticDecision.model_validate()
       |           |
       |   TOOL_REGISTRY[tool_name](**tool_input) --> dispatches agent_instructions
       |           |
       |-- Turn 2: AsyncAnthropic.messages.create(tool_result) --> rationale text
       |
       |-- _log_decision() --> agent_ai_decisions (MongoDB)
       |
       v
agentic_tasks_endpoints.py returns [{id, type, context}] to Rust agent

Rust Agent executes capability (run_compliance_check etc.)
       |
       | POST /api/agents/{id}/agentic-tasks/{task_id}/result
       v
agentic_tasks_endpoints.py
       |
       | Updates agent_ai_decisions.result / agent_tasks.status
       v
Done
```

### Recommended Project Structure
```
backend/
├── agentic_service.py          # NEW: AsyncAnthropic client, AgenticService, TOOL_REGISTRY, TOOLS
├── agentic_tasks_endpoints.py  # NEW: FastAPI router for GET/POST agentic-tasks
├── agent_tasks_endpoints.py    # EXISTING: unchanged (pattern template)
├── agent_approval_endpoints.py # EXISTING: unchanged (agentic_decisions collection nearby)
├── ai_providers.py             # EXISTING: unchanged (AnthropicProvider stays httpx-only)
├── ai_service.py               # EXISTING: unchanged (chat/incident path unchanged)
├── circuit_breaker.py          # EXISTING: add agentic_breaker instance here OR in agentic_service.py
├── database.py                 # EXISTING: add agent_ai_decisions indexes in connect_to_mongo()
├── router_registry.py          # EXISTING: add one _load() line for agentic_tasks_endpoints
└── tests/
    └── test_agentic_service.py # NEW: pytest unit tests
```

---

## F-01: How to Extend AnthropicProvider for Tool-Calling

**Answer:** Do NOT extend `AnthropicProvider`. Per AI-SPEC Section 3 and Section 4:

> "Use the SDK client directly — not the httpx-based AnthropicProvider. The SDK handles retry, timeout, and header management automatically."

`AnthropicProvider.generate()` (ai_providers.py lines 159–177) is a general-purpose text generator used by the chat assistant and incident analyzer. Adding tool-calling there would couple agentic security logic to the general AI path and break the single-responsibility principle.

The correct approach: instantiate `AsyncAnthropic` independently in `agentic_service.py`:

```python
# backend/agentic_service.py (new file)
from anthropic import AsyncAnthropic
from anthropic.types import ToolUseBlock

_agentic_client: AsyncAnthropic | None = None

def get_agentic_client(api_key: str) -> AsyncAnthropic:
    """Return or create the module-level AsyncAnthropic client."""
    global _agentic_client
    if _agentic_client is None:
        _agentic_client = AsyncAnthropic(api_key=api_key, max_retries=2, timeout=30.0)
    return _agentic_client
```

**What lines would change if someone chose to extend AnthropicProvider instead (informational only):**
- Add `tools: list | None = None` parameter to `generate()` at line 159
- Add `"tools": tools` to the json payload at line 173
- Change return at line 177 to detect `tool_use` content blocks
This approach is explicitly ruled out by the AI-SPEC.

---

## F-02: Schema for agentic_service.py

```python
# backend/agentic_service.py
"""
Agentic AI decision service — two-turn Claude tool-calling loop for security capability selection.
Consumed by: agentic_tasks_endpoints.py
"""
import copy
import datetime
import json
import logging
import os
import uuid
from typing import Callable, Awaitable

from anthropic import AsyncAnthropic
from anthropic.types import ToolUseBlock
from pydantic import BaseModel, field_validator
from typing import Literal

from circuit_breaker import CircuitBreaker, CircuitBreakerOpen
from database import get_database

logger = logging.getLogger(__name__)

# ── Circuit breaker (separate from ai_breaker so agentic failures don't affect chat) ──
agentic_breaker = CircuitBreaker("agentic_ai", failure_threshold=3, recovery_timeout=60)

# ── Tool definitions (JSON Schema, passed to every messages.create() call) ──
TOOLS: list[dict] = [...]  # Five tools as in AI-SPEC Section 3 (exact definitions copied verbatim)

# ── Tool registry (maps name → async dispatcher that queues agent_instructions) ──
TOOL_REGISTRY: dict[str, Callable[..., Awaitable[dict]]] = {
    "run_compliance_check":   _dispatch_compliance_check,
    "run_vulnerability_scan": _dispatch_vulnerability_scan,
    "run_threat_hunt":        _dispatch_threat_hunt,
    "run_persistence_scan":   _dispatch_persistence_scan,
    "collect_processes":      _dispatch_collect_processes,
}

# ── System prompt (static — never embed dynamic data here) ──
SYSTEM_PROMPT = """..."""  # Verbatim from AI-SPEC Section 3

# ── Pydantic validation model ──
class AgenticDecision(BaseModel):
    tool_name: Literal[
        "run_compliance_check", "run_vulnerability_scan", "run_threat_hunt",
        "run_persistence_scan", "collect_processes"
    ]
    agent_id: str
    framework: Literal["CIS", "NIST", "ISO27001"] | None = None
    severity_threshold: Literal["low", "medium", "high", "critical"] | None = None
    hunt_profile: Literal["lateral_movement", "credential_access", "persistence", "exfiltration"] | None = None
    include_network: bool = False

    @field_validator("agent_id")
    @classmethod
    def agent_id_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("agent_id must be a non-empty string")
        return v.strip()

# ── Context truncation (pre-call, bounds input tokens) ──
def truncate_security_context(ctx: dict, max_findings: int = 20) -> dict: ...

# ── Core decision function ──
async def decide_and_execute(agent_id: str, security_context: dict, client: AsyncAnthropic) -> dict: ...

# ── Service class (wraps decision + MongoDB logging) ──
class AgenticService:
    def __init__(self, api_key: str):
        self._client = AsyncAnthropic(api_key=api_key, max_retries=2, timeout=30.0)

    async def run(self, agent_id: str, security_context: dict) -> dict:
        """Execute one agentic decision cycle. Logs result to agent_ai_decisions."""
        decision_id = str(uuid.uuid4())
        started_at = datetime.datetime.utcnow()
        try:
            async with agentic_breaker:
                result = await decide_and_execute(agent_id, security_context, self._client)
        except CircuitBreakerOpen:
            logger.warning("[AgenticService] Circuit breaker open — activating rule-based fallback")
            result = await _rule_based_fallback(agent_id, security_context)
            result["source"] = "rule_based_fallback"
        except Exception as exc:
            logger.error("[AgenticService] Decision failed for %s: %s", agent_id, exc)
            result = await _rule_based_fallback(agent_id, security_context)
            result["source"] = "rule_based_fallback"
        await self._log_decision(decision_id, agent_id, result, started_at)
        return result

    async def _log_decision(self, decision_id, agent_id, result, started_at):
        db = get_database()
        if not db:
            logger.warning("[AgenticService] DB unavailable; decision %s not logged.", decision_id)
            return
        doc = {
            "_id": decision_id,
            "agent_id": agent_id,
            "tool_name": result.get("tool_name"),
            "tool_input": result.get("tool_input"),
            "rationale": result.get("rationale", ""),
            "model": "claude-sonnet-4-6",
            "started_at": started_at.isoformat(),
            "completed_at": datetime.datetime.utcnow().isoformat(),
            "source": result.get("source", "agentic_ai"),
        }
        try:
            await db.agent_ai_decisions.insert_one(doc)
        except Exception as e:
            # NEVER suppress silently — Critical Failure Mode #3 from AI-SPEC
            logger.error("[AgenticService] AUDIT WRITE FAILURE for decision %s: %s", decision_id, e)

# Module-level singleton — created on first use
_service: AgenticService | None = None

def get_agentic_service() -> AgenticService:
    global _service
    if _service is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        _service = AgenticService(api_key)
    return _service
```

---

## F-03: Schema for agentic_tasks_endpoints.py

```python
# backend/agentic_tasks_endpoints.py
"""
Agentic task endpoints — Rust agent polling and result submission.

GET  /api/agents/{agent_id}/agentic-tasks           → agent polls for pending tasks (verify_agent_key)
POST /api/agents/{agent_id}/agentic-tasks/{task_id}/result → agent reports capability result (verify_agent_key)
POST /api/agents/{agent_id}/agentic-tasks/trigger   → operator triggers agentic cycle (get_current_user)
GET  /api/agents/{agent_id}/agentic-tasks/decisions → operator reads AI decision history (get_current_user)
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from typing import Dict, Any, List, Optional
from database import get_database
from authentication_service import get_current_user
from agent_auth import verify_agent_key
from datetime import datetime, timezone
import uuid, logging, os

from agentic_service import get_agentic_service

router = APIRouter(prefix="/api/agents", tags=["Agentic AI"])
logger = logging.getLogger("agentic_tasks_endpoints")


@router.get("/{agent_id}/agentic-tasks")
async def get_agentic_tasks(
    agent_id: str,
    _tenant: Dict[str, Any] = Depends(verify_agent_key),
):
    """Rust agent polls this every 60 seconds. Returns pending agentic task(s) with pre-assembled security_context."""
    db = get_database()
    # Pull pending tasks from agent_tasks or agent_ai_tasks collection
    # Include the security_context assembled from findings/alerts/processes
    ...
    # After assembling context, invoke AI decision (or queue for async)
    # Return task list: [{"id": task_id, "type": task_type, "context": security_context}]


@router.post("/{agent_id}/agentic-tasks/{task_id}/result")
async def submit_agentic_task_result(
    agent_id: str,
    task_id: str,
    result: Dict[str, Any] = Body(...),
    _tenant: Dict[str, Any] = Depends(verify_agent_key),
):
    """Rust agent submits capability execution result. Updates agent_ai_decisions record."""
    db = get_database()
    # Update agent_ai_decisions._id=task_id with result + completed status
    ...
    return {"status": "ok"}


@router.post("/{agent_id}/agentic-tasks/trigger")
async def trigger_agentic_task(
    agent_id: str,
    payload: Optional[Dict[str, Any]] = Body(default=None),
    current_user: Any = Depends(get_current_user),
):
    """Operator manually triggers one agentic AI decision cycle for a given agent."""
    ...


@router.get("/{agent_id}/agentic-tasks/decisions")
async def list_agentic_decisions(
    agent_id: str,
    limit: int = 50,
    current_user: Any = Depends(get_current_user),
    db=Depends(get_database),
):
    """Operator views AI decision history for a given agent from agent_ai_decisions."""
    cursor = db.agent_ai_decisions.find(
        {"agent_id": agent_id}, {"_id": 0}
    ).sort("started_at", -1).limit(limit)
    return {"decisions": await cursor.to_list(limit)}
```

**Key differences from `agent_tasks_endpoints.py` pattern:**
- Uses `verify_agent_key` (not `get_current_user`) on the Rust-agent-facing GET and POST result endpoints
- The `/agentic-tasks` GET endpoint needs careful ordering relative to `/{agent_id}/agentic-tasks/{task_id}/result` — FastAPI matches routes in registration order, so the static suffix `/decisions` must be registered before `/{task_id}/result` to avoid path collision. Alternatively use different path structure.

---

## F-04: MongoDB agent_ai_decisions Document Schema and Indexes

### Document Schema

```python
{
    "_id":          str,        # UUID — the decision_id, set explicitly (not ObjectId)
    "tenantId":     str,        # Injected by TenantIsolatedCollection.insert_one()
    "agent_id":     str,        # UUID of the managed Windows endpoint
    "tool_name":    str | None, # One of the five capability names; None on fallback failure
    "tool_input":   dict | None,# Raw validated AgenticDecision.model_dump() output
    "rationale":    str,        # Turn 2 text from Claude; "rule_based_fallback" on fallback
    "model":        str,        # "claude-sonnet-4-6" | "rule_based_fallback"
    "started_at":   str,        # datetime.utcnow().isoformat() at decision cycle start
    "completed_at": str,        # datetime.utcnow().isoformat() after tool execution + log
    "source":       str,        # "agentic_ai" | "rule_based_fallback"
    # Optional — populated when agent submits result:
    "result":       dict | None,# Capability output from Rust agent (submitted via result endpoint)
    "result_at":    str | None, # datetime.utcnow().isoformat() when result received
}
```

### Indexes (add to `database.py` `connect_to_mongo()`)

```python
# agent_ai_decisions — agentic AI audit trail (Phase 12)
# Primary query: "show me all decisions for agent X sorted by time"
await mongodb.db.agent_ai_decisions.create_index(
    [("agent_id", 1), ("started_at", -1)],
    name="agent_ai_decisions_agent_time_idx",
)
# Secondary query: "what % of decisions used each tool" (tool distribution monitoring)
await mongodb.db.agent_ai_decisions.create_index(
    [("tool_name", 1)],
    name="agent_ai_decisions_tool_idx",
)
# Tenant isolation: TenantIsolatedCollection always injects tenantId
await mongodb.db.agent_ai_decisions.create_index(
    [("tenantId", 1), ("started_at", -1)],
    name="agent_ai_decisions_tenant_time_idx",
)
# Fallback rate monitoring: count "source" = "rule_based_fallback" per day
await mongodb.db.agent_ai_decisions.create_index(
    [("source", 1), ("started_at", -1)],
    name="agent_ai_decisions_source_idx",
)
```

**No TTL index** — SOC 2 CC6.1 / ISO 27001 A.12.4 require audit logs are retained and not auto-purged. [CITED: AI-SPEC Section 1b Regulatory Context]

**Tenant isolation:** `agent_ai_decisions` is NOT in the global-exemption list in `database.py` (lines 123–134), so all reads and writes go through `TenantIsolatedCollection`. `_log_decision()` calls `db.agent_ai_decisions.insert_one(doc)` — `TenantIsolatedCollection.insert_one()` automatically injects `tenantId` from `get_tenant_id()`. No manual `tenantId` assignment needed in `_log_decision()`.

---

## F-05: How to Wire the New Router into app_startup.py (Correction: router_registry.py)

Router registration is in `backend/router_registry.py`, not `app_startup.py`.

**Exact change:** In `router_registry.py`, in the `# ── AI & Data Science ─────────────────────────────────────────────────────────` section (around line 136–152), add:

```python
# Line to add after existing AI router loads (e.g., after _load(app, "ai_endpoints", "router")):
_load(app, "agentic_tasks_endpoints", "router")
```

This is sufficient. The `_load()` helper at lines 26–42 handles: import, `include_router`, error logging. Since agentic AI is a graceful-degradation feature (AI-04), it is appropriate NOT to add it to `_REQUIRED_ROUTERS` — a broken import logs an ERROR but does not abort startup.

**Additionally:** `app_startup.py`'s `run_startup_services()` can optionally call `init_agentic_tracing()` (from AI-SPEC Section 7) to wire Arize Phoenix OpenTelemetry. This is a monitoring concern, not routing. Add it to `run_startup_services()` after existing startup tasks, wrapped in a try/except like all other optional service starts.

---

## F-06: What the Rust Agent Sends as Task Context

**Source:** `agent-rust/src/agentic.rs` lines 83–133

### Task Fetch Response (backend → agent)
The agent receives a JSON array from `GET /api/agents/{id}/agentic-tasks`. Each task element must have:
```json
{
  "id": "<UUID>",
  "type": "<task_type_string>",
  "context": {
    "agent_id": "<UUID>",
    "findings": [ /* up to 20, sorted severity desc */ ],
    "alerts": [ /* up to 5 most recent */ ],
    "processes": [ /* up to 30 anomalous */ ],
    "last_compliance_run": "<ISO8601 or null>",
    "last_vuln_scan": "<ISO8601 or null>",
    "capabilities": ["run_compliance_check", "run_vulnerability_scan", ...]
  }
}
```
The `context` field is the `security_context` assembled by the backend and passed to `AgenticService.run()`. The Rust agent does not modify it — it just echoes `task.context` to the backend LLM call. In Phase 12, the LLM call happens entirely on the backend before the task is even served; the task served to the agent already contains the AI's decision embedded as the `type` field (the selected tool) with tool inputs in `context`.

### Task Result (agent → backend)
The Rust agent posts to `POST /api/agents/{id}/agentic-tasks/{task_id}/result`:
```json
{
  "task_id": "<UUID>",
  "status": "completed",
  "result": { /* capability output — e.g. compliance_checks array, vulnerability list */ },
  "completed_at": "<RFC3339>"
}
```
Bearer token is the agent's auth token (same as used for heartbeat endpoints — `verify_agent_key` Depends).

---

## Common Pitfalls

### Pitfall 1: Path Collision in FastAPI Router
**What goes wrong:** Registering `GET /{agent_id}/agentic-tasks/decisions` after `GET /{agent_id}/agentic-tasks/{task_id}/result` causes FastAPI to match `/decisions` as the `task_id` variable instead of routing to the decisions endpoint.
**Why it happens:** FastAPI matches routes in declaration order; `/{task_id}` is a catch-all.
**How to avoid:** Register static-suffix routes (`/decisions`, `/trigger`) BEFORE parameterized routes (`/{task_id}/result`), OR use a distinct prefix like `/api/agentic` instead of nesting under `/api/agents`.
**Warning signs:** `GET /api/agents/{id}/agentic-tasks/decisions` returns a 404 or unexpected handler.

### Pitfall 2: TenantIsolatedCollection Double-Injecting tenantId
**What goes wrong:** `_log_decision()` manually sets `doc["tenantId"] = agent_tenant_id` AND `TenantIsolatedCollection.insert_one()` also sets it — the second write overwrites the first with the request context's tenant, which may differ if called from a background task without tenant context set.
**Why it happens:** The `TenantIsolatedCollection` wrapper (database.py line 47–54) unconditionally sets `tenantId` based on `get_tenant_id()`. Background tasks not setting tenant context will get `"ORPHANED_DATA_NO_TENANT_CONTEXT"`.
**How to avoid:** When calling `_log_decision()` from a background task (agentic poller), call `set_tenant_id(agent_tenant_id)` from `tenant_context` before writing. Do not pass `tenantId` manually in the doc — let the wrapper handle it. Or: use `db._db.agent_ai_decisions.insert_one()` (bypassing isolation wrapper) in contexts where tenant is set via a different mechanism.
**Warning signs:** `agent_ai_decisions` records have `tenantId = "ORPHANED_DATA_NO_TENANT_CONTEXT"` in MongoDB.

### Pitfall 3: stop_reason != "tool_use" Despite tool_choice="any"
**What goes wrong:** The `decide_and_execute()` Turn 1 call returns `stop_reason="max_tokens"` because the tool definitions (800 tokens) + security context exceed the prompt budget. The guard `if response.stop_reason != "tool_use": raise RuntimeError(...)` fires, triggering fallback on every call for large contexts.
**Why it happens:** `max_tokens=1024` on the response side is fine; the issue is total input tokens exceeding budget when `truncate_security_context()` is not called.
**How to avoid:** Always call `truncate_security_context()` before `decide_and_execute()`. Assert `estimate_tokens(context) < 3000` before the API call; log a warning and truncate to findings-only if exceeded.
**Warning signs:** Unusually high fallback rate; Phoenix traces showing `stop_reason="max_tokens"` on Turn 1 spans.

### Pitfall 4: Audit Write Failure Silently Suppressed
**What goes wrong:** `_log_decision()` wraps the MongoDB write in try/except and logs the error, but the calling code catches all exceptions broadly and returns success — no alert fires and the compliance auditor sees a gap.
**Why it happens:** Pattern copied from other endpoint code that suppresses non-fatal errors.
**How to avoid:** Log audit write failures at ERROR level (not WARNING) AND emit a metric counter (per AI-SPEC Section 6 online guardrails: `agentic.audit_write_failure`). Never return HTTP 200 to the caller without knowing whether the audit write succeeded.
**Warning signs:** `agent_ai_decisions` count diverges from `agent_tasks` count for the same time window.

### Pitfall 5: asyncio.run() Inside FastAPI Async Context
**What goes wrong:** Calling `asyncio.run(decide_and_execute(...))` inside a FastAPI endpoint raises `RuntimeError: asyncio.run() cannot be called when another event loop is running`.
**Why it happens:** FastAPI is async; calling `asyncio.run()` attempts to start a new event loop in a thread that already has one.
**How to avoid:** All calls to `AgenticService.run()` must use `await`. The endpoint handler must be `async def`.
**Warning signs:** `RuntimeError: asyncio.run() cannot be called when another event loop is running` in logs.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Tool-calling response parsing | Custom JSON parser for `tool_use` blocks | `from anthropic.types import ToolUseBlock; b.type == "tool_use"` | SDK provides typed blocks; manual parsing misses `stop_reason` edge cases |
| Retry on API failure | Custom retry loop with sleep | `AsyncAnthropic(max_retries=2)` constructor param | SDK handles retries with exponential backoff and respects `Retry-After` headers |
| Circuit breaking | Custom failure counter | `circuit_breaker.CircuitBreaker("agentic_ai", ...)` | Already tested in ai_service.py; 27 lines covers CLOSED/OPEN/HALF_OPEN |
| Schema validation | `isinstance(tool_name, str) and tool_name in TOOL_REGISTRY` | `pydantic.BaseModel.model_validate()` (AgenticDecision) | Pydantic catches enum violations, empty strings, type coercion errors atomically |
| Tenant isolation on DB writes | `doc["tenantId"] = tenant_id` inline | `TenantIsolatedCollection.insert_one()` (already injected) | Manual assignment causes double-injection or orphaned records if tenant context not set |

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `httpx` direct to `/v1/messages` (as in `AnthropicProvider`) | `AsyncAnthropic` SDK client for tool-calling | SDK ≥ 0.28.0 | SDK handles `ToolUseBlock` parsing, `tool_choice`, retry, `Retry-After` headers |
| `tool_choice: {"type": "auto"}` | `tool_choice: {"type": "any"}` | Anthropic SDK ≥ 0.20.0 | Guarantees `stop_reason="tool_use"` and prevents plain-text fallback in mandatory-decision loop |
| LangChain/LangGraph agent loop | Direct SDK two-turn loop | 2024–2025 | Phase 12 is single-tool-per-turn — framework overhead not justified |

**Deprecated:**
- `asyncio.run()` inside async contexts: always was wrong; raises in FastAPI/uvicorn
- OpenAI-style `response_format` for structured output: Anthropic uses `tool_use` blocks instead — there is no `response_format` parameter in the Anthropic messages API

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing in backend/tests/) |
| Config file | `backend/pytest.ini` or `backend/pyproject.toml` (check existing) |
| Quick run command | `pytest backend/tests/test_agentic_service.py -x -q` |
| Full suite command | `pytest backend/tests/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AI-01 | `AgenticService.run()` calls AsyncAnthropic with tool_choice="any" and returns tool_name | unit (mock AsyncAnthropic) | `pytest backend/tests/test_agentic_service.py::test_run_calls_anthropic -x` | No — Wave 0 |
| AI-01 | `decide_and_execute()` raises RuntimeError if stop_reason != "tool_use" | unit | `pytest backend/tests/test_agentic_service.py::test_stop_reason_guard -x` | No — Wave 0 |
| AI-02 | All 5 tools present in TOOLS list and TOOL_REGISTRY | unit | `pytest backend/tests/test_agentic_service.py::test_tool_registry_complete -x` | No — Wave 0 |
| AI-02 | Hallucinated tool name raises ValueError before dispatch | unit | `pytest backend/tests/test_agentic_service.py::test_hallucinated_tool_rejected -x` | No — Wave 0 |
| AI-03 | `_log_decision()` writes all required fields to agent_ai_decisions | unit (mongomock) | `pytest backend/tests/test_agentic_service.py::test_log_decision_fields -x` | No — Wave 0 |
| AI-03 | Audit write failure is logged at ERROR (not suppressed) | unit | `pytest backend/tests/test_agentic_service.py::test_audit_write_failure_logged -x` | No — Wave 0 |
| AI-04 | CircuitBreakerOpen activates rule-based fallback with source="rule_based_fallback" | unit | `pytest backend/tests/test_agentic_service.py::test_fallback_on_circuit_open -x` | No — Wave 0 |
| AI-04 | API exception activates rule-based fallback (not 500 to agent) | unit | `pytest backend/tests/test_agentic_service.py::test_fallback_on_api_error -x` | No — Wave 0 |

### Wave 0 Gaps
- [ ] `backend/tests/test_agentic_service.py` — all 8 tests above; use `unittest.mock.AsyncMock` to mock `AsyncAnthropic.messages.create`
- [ ] `backend/tests/test_agentic_tasks_endpoints.py` — endpoint smoke tests (GET agentic-tasks returns list, POST result updates DB)

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `verify_agent_key` (agent-facing endpoints); `get_current_user` (operator endpoints) |
| V3 Session Management | no | Agentic poller is server-to-server; no session |
| V4 Access Control | yes | Tenant isolation via `TenantIsolatedCollection`; operator endpoints require `get_current_user` |
| V5 Input Validation | yes | `AgenticDecision.model_validate()` (Pydantic); `truncate_security_context()` bounds context |
| V6 Cryptography | no | No new crypto operations |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection via agent-supplied findings | Tampering | Keep dynamic data in user message JSON (not system prompt); `truncate_security_context()` strips raw blobs |
| Tool name hallucination | Tampering | `AgenticDecision.model_validate()` + `tool_name in TOOL_REGISTRY` guard before dispatch |
| Audit write failure masking real actions | Repudiation | Log at ERROR; emit `agentic.audit_write_failure` metric; never suppress exception silently |
| Unauthenticated agentic task fetch | Elevation of Privilege | `verify_agent_key` Depends on all Rust-agent-facing endpoints |
| Orphaned `agent_ai_decisions` records (no tenantId) | Information Disclosure | Set tenant context before all DB writes in background tasks via `set_tenant_id()` |

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python `anthropic` SDK | `agentic_service.py` AsyncAnthropic | Yes | 0.111.0 | MockProvider / rule-based fallback |
| `ANTHROPIC_API_KEY` env var | `get_agentic_service()` | Unknown (runtime) | — | `ai_service.py` initializer pattern: warn at startup if unset |
| MongoDB `agent_ai_decisions` | `_log_decision()` | Needs index creation | n/a | Logs ERROR; does not block tool dispatch |
| `circuit_breaker.CircuitBreaker` | `agentic_breaker` | Yes | existing module | n/a |
| FastAPI `verify_agent_key` | Endpoint auth | Yes | existing module | n/a |

**Missing dependencies with no fallback:** `ANTHROPIC_API_KEY` must be set for the agentic AI path to function. If unset, `get_agentic_service()` should raise at construction time with a clear error. The `ai_service.py` initialization pattern (lines 131–137) shows how to detect and warn at startup.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The Rust agent's `GET /api/agents/{id}/agentic-tasks` response is expected to be a JSON array with `{id, type, context}` elements, and the agent places the decision back into the `execute_agentic_task` switch statement based on `task.type` | F-06, F-03 | If the agent expects a different response shape, the endpoint must match it — re-read agentic.rs lines 70–73 before finalizing response schema |
| A2 | The `security_context` for the AI call is assembled on the backend (from findings/alerts in MongoDB) rather than sent by the Rust agent | F-06, F-02 | If the intent is for the agent to supply the context (endpoint-push), the endpoint design changes significantly |
| A3 | `set_tenant_id()` is safe to call from the agentic poller background task | F-04, Pitfall 2 | If `set_tenant_id()` uses a request-scoped context var that doesn't work in background tasks, a different isolation mechanism is needed |

---

## Sources

### Primary (HIGH confidence — code directly read)
- `backend/ai_providers.py` — AnthropicProvider.generate() lines 159–177; confirmed httpx-only, no tool-calling
- `backend/ai_service.py` — IncidentAnalyzer, ai_breaker usage lines 228–234; circuit-breaker pattern
- `backend/circuit_breaker.py` — CircuitBreaker class lines 34–101; ai_breaker pre-built instance
- `backend/database.py` — TenantIsolatedCollection, connect_to_mongo() index creation lines 223–302
- `backend/agent_tasks_endpoints.py` — router pattern, verify_agent_key usage, Body() pattern
- `backend/agent_approval_endpoints.py` — agentic_decisions collection read/write pattern
- `backend/router_registry.py` — _load() helper, register_all_routers() full listing
- `backend/app.py` — register_all_routers() call at line 157; lifespan pattern
- `backend/app_startup.py` — run_startup_services() pattern for background task startup
- `backend/llm_proxy.py` — ai_audit_logs write pattern (reference for agent_ai_decisions)
- `agent-rust/src/agentic.rs` — fetch_agentic_tasks() line 84, execute_agentic_task() lines 93–133, result POST line 129
- `.planning/phases/12-agentic-ai-integration/12-AI-SPEC.md` — framework decision, code examples, tool schemas, evaluation strategy
- `pip show anthropic` — confirmed 0.111.0 installed (well above 0.28.0 minimum)

### Secondary (HIGH confidence — from AI-SPEC which cites official Anthropic docs)
- Anthropic Python SDK api.md (tool use reference) [CITED: github.com/anthropics/anthropic-sdk-python/blob/main/api.md]
- Tool definitions and parameters [CITED: deepwiki.com/anthropics/anthropic-sdk-python/7.1-tool-definitions-and-parameters]
- Known Sonnet 4.6 parallel tool regression [CITED: github.com/anthropics/anthropic-sdk-typescript/issues/956]

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — anthropic 0.111.0 verified installed; no new packages
- Architecture: HIGH — all files read directly; patterns extracted from existing working code
- Pitfalls: HIGH — based on direct code inspection of database.py (tenant isolation), agentic.rs (Rust expectations), circuit_breaker.py (state machine)
- Tool-calling patterns: HIGH — from AI-SPEC (authoritative design contract for this phase)

**Research date:** 2026-06-23
**Valid until:** 2026-07-23 (Anthropic SDK moves fast; re-verify imports if SDK is upgraded beyond 0.111.0)
