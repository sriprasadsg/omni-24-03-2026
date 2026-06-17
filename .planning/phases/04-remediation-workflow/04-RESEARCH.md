# Phase 4: Remediation Workflow — Research

**Researched:** 2026-06-18
**Domain:** Compliance remediation task lifecycle — backend CRUD, agent re-scan dispatch, frontend dashboard, real-time status push
**Confidence:** HIGH

---

## Summary

The codebase contains substantial remediation infrastructure that is fragmented across several services. The existing `remediation_endpoints.py` + `remediation_service.py` handle AI-generated fix scripts for *vulnerabilities*, not compliance controls. The `continuous_compliance_service.py` has a `create_remediation_task` method that writes to a `remediation_tasks` MongoDB collection, but there are no HTTP GET/PATCH/delete endpoints for that collection and no frontend that reads it. This means Phase 4 must build a new, focused `remediation_task_endpoints.py` + `remediation_task_service.py` pair that stores compliance-scoped remediation tasks and wires them into the existing agent instruction dispatch and WebSocket broadcast infrastructure.

The agent re-scan mechanism is fully built and proven. The compliance scan instruction `"Run Compliance Scan"` is handled by the Python agent (`agent/agent.py` line 623) and `"run_compliance_check"` / `"Run Compliance Check"` by the Rust agent (`agent-rust/src/poll.rs` line 260). The backend dispatches instructions by inserting into `db.agent_instructions` (polled by agents every 5 s), with a parallel Socket.IO `send_to_agent` path for agents that hold an active WebSocket connection. Both paths exist and work today.

The WebSocket broadcast infrastructure (`websocket_manager.py`) already has `broadcast_compliance_alert` (line 287) as the template for a new `broadcast_remediation_update` function. The frontend `socketService.ts` has the subscription wiring. The compliance data model in `asset_compliance` stores `assetId`, `controlId`, `status` (`"Compliant"` / `"Non-Compliant"` / `"Warning"` / `"Pending_Review"`), and `tenantId`. "Failed" controls are those with `status in {"Non-Compliant", "Warning"}`. The link back to an agent goes through `assets` → `agentId` field: given an `assetId`, look up `assets.find_one({"id": assetId})["agentId"]`.

**Primary recommendation:** Build two new backend files (`remediation_task_endpoints.py` + `remediation_task_service.py`), one new frontend component (`RemediationDashboard.tsx`) with a modal (`RemediationTaskModal.tsx`), extend `websocket_manager.py` with one new broadcast function, extend `services/apiService.ts` with CRUD helpers, extend `types.ts` with `RemediationTask` and `'remediationWorkflow'` AppView entry, and extend `components/Sidebar.tsx` with a nav item. No new database collections are required beyond `compliance_remediation_tasks` (distinct from the existing `remediation_tasks` used by `continuous_compliance_service.py`).

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Remediation task CRUD | API / Backend | — | Data mutation and tenant scoping must happen server-side |
| Re-scan dispatch to agent | API / Backend | Agent (execution) | Server decides when to dispatch; agent executes and posts result |
| Compliance status update post-scan | Agent → Backend | — | Agent posts heartbeat/instruction-result; backend processor updates `asset_compliance` |
| Real-time task status push | Backend (Socket.IO) | Frontend (subscriber) | Backend emits `remediation_update` event; frontend patches local state |
| Remediation task list and create | Frontend / Client | — | Browser renders filtered list, opens create modal |
| Sidebar navigation | Frontend / Client | — | AppView enum + sidebar nav item |

---

## Research Findings by Question

### Q1 — Existing task/ticket infrastructure

**Finding:** Multiple overlapping remediation systems exist. None directly serves Phase 4.

| File | Purpose | Gap |
|------|---------|------|
| `backend/remediation_endpoints.py` | AI fix scripts for **vulnerabilities** (`RemediationRequest` model). Routes: `POST /api/remediation/generate`, `POST /api/remediation/{id}/execute`, `GET /api/remediation/`. | No `title`, `assignee`, `due_date`, `description`, no control linkage — wrong domain. |
| `backend/remediation_service.py` | Generates and dispatches Celery-based fix scripts. Writes to `db.remediation_requests`. | Not for compliance control tasks. |
| `backend/continuous_compliance_service.py` `create_remediation_task()` (line 268) | Writes `{type: "compliance_remediation", violation, status: "open", priority, assigned_to: None, due_date: None}` to `db.remediation_tasks`. | No GET/PATCH endpoint, no frontend, no agent dispatch, no WebSocket. Exists only as a service method — the HTTP API is `POST /api/compliance-automation/create-remediation-task` (line 312 of `compliance_automation_api.py`) with no corresponding GET. |
| `backend/tasks_endpoints.py` (optional router) | Agent task tracking in `db.agent_tasks`. Not compliance-aware. | Wrong collection, no control linkage. |
| `backend/compliance_scans_endpoints.py` | `POST /api/compliance/{framework}/scan` and `POST /api/agents/{id}/compliance/scan` write `"Run Compliance Scan"` to `db.agent_instructions`. | This is *exactly* what REM-03 re-scan dispatch should call or replicate per-agent. |

**Gaps to fill:**
- New collection `compliance_remediation_tasks` to store Phase 4 tasks (avoids colliding with `remediation_tasks` already used by `continuous_compliance_service`).
- New `backend/remediation_task_endpoints.py` with GET, POST, PATCH, and dispatch sub-resource.
- New `backend/remediation_task_service.py` for pure DB logic.
- Register in `router_registry.py` (required section, not optional).

---

### Q2 — Agent re-scan mechanism

**Finding:** Two parallel dispatch paths; both are operational.

**Path A — agent_instructions polling (primary):**
- Backend: `db.agent_instructions.insert_one({"agent_id": ..., "instruction": "Run Compliance Scan", "status": "pending", ...})` — see `compliance_scans_endpoints.py` lines 26–34, 68–76.
- Agent (Python): polls `GET /api/agents/{hostname}/instructions` (via heartbeat loop); `"Run Compliance Scan"` matched at `agent/agent.py` line 623, runs `compliance_enforcement.collect()`, then `POST /api/agents/{agent_id}/instructions/result`.
- Agent (Rust): polls `GET /api/agents/{agent_id}/instructions` every 5 s (`poll.rs` `instruction_poller`); matches `"run_compliance_check"` | `"Run Compliance Check"` at line 260, calls `caps::run_compliance_check()`.
- **Discrepancy to resolve:** Python agent matches `"Run Compliance Scan"`, Rust agent matches `"Run Compliance Check"`. The instruction string stored by `compliance_scans_endpoints.py` is `"Run Compliance Scan"`. Rust poll.rs does **not** match that string — it matches `"Run Compliance Check"`. The dispatch endpoint for Phase 4 should use **`"Run Compliance Scan"`** to ensure Python agent compat, and document that the Rust agent won't respond unless the dispatch or Rust source is updated.

**Path B — Socket.IO direct push (secondary, agent must be connected):**
- `websocket_manager.py` `send_to_agent(agent_id, payload)` (lines 353–365) emits a `command` event directly to the agent's Socket.IO session.
- Agent must have called the `connect` flow with `auth.type == "agent"` to register in `agent_sessions`.
- Returns `False` if agent is offline; caller must handle gracefully.
- The Rust agent has a `ws.rs` module but the heartbeat-based instruction polling (`poll.rs`) is the primary path used in production.

**Recommended approach for REM-03:**
1. Resolve `agentId` from `assets.find_one({"id": task["asset_id"]})["agentId"]`.
2. Insert `"Run Compliance Scan"` instruction into `db.agent_instructions`.
3. Optionally attempt `send_to_agent` for immediate push; log but do not fail if offline.
4. Return `{"dispatched": True, "agent_id": agent_id}` to caller.

---

### Q3 — Frontend task/remediation components

**Finding:** No `RemediationDashboard.tsx` for compliance remediation exists. Existing components handle unrelated domains.

| Component | Purpose | Relation to Phase 4 |
|-----------|---------|---------------------|
| `components/AIRemediationDashboard.tsx` | Agentic decision approval for AI risk remediation. Fetches `/api/agents/agentic-decisions/all`. | Different domain entirely. |
| `components/AutonomousRiskRemediation.tsx` | Autonomous risk remediation steps. | Different domain. |
| `components/CSPMRemediationModal.tsx` | Cloud security posture remediation modal. | Different domain. |
| `components/TaskList.tsx` | Generic to-do task list for the `Task` type (id: number, text, priority, completed). | Generic; not compliance-aware. |
| `components/TaskForm.tsx` | Form for `Task`. | Generic. |

**Sidebar navigation:**
- `components/Sidebar.tsx` currently has `{ view: 'aiRemediation', label: 'AI Remediation', ... }` (line 372) under the AI section.
- There is no `'remediationWorkflow'` AppView or sidebar item.
- Phase 4 must add `'remediationWorkflow'` to the `AppView` union in `types.ts` and a nav item in `Sidebar.tsx` under Compliance.

---

### Q4 — Compliance control data model

**Finding:** `asset_compliance` is the canonical collection. Schema (from `compliance_evidence_processor.py` lines 248–266 and `compliance_evidence_endpoints.py` lines 101–112):

```
asset_compliance document:
  assetId:           string   (e.g. "asset-HOSTNAME")
  controlId:         string   (e.g. "A.8.22", "PCI-1.1", "CC6.6")
  status:            string   "Compliant" | "Non-Compliant" | "Warning" | "Pending_Review"
  tenantId:          string
  checkName:         string   (human-readable check name, e.g. "Windows Firewall Profiles")
  lastUpdated:       ISO-8601 string
  lastAutomatedCheck: ISO-8601 string
  evidence:          array of evidence subdocuments
  agent_type:        string (optional)
```

**"Failed" controls are those with `status` equal to `"Non-Compliant"` or `"Warning"`.** The evidence processor sets `"Compliant"`, `"Warning"`, or `"Non-Compliant"` depending on agent check result (lines 187–191). Manual uploads set `"Pending_Review"`.

**Agent linkage:** `asset_compliance.assetId` → `assets.id` → `assets.agentId`. This two-hop lookup is required to find the agent to re-scan.

The `GET /api/compliance/evidence` endpoint (line 123 of `compliance_evidence_endpoints.py`) returns all `asset_compliance` records for the tenant. Phase 4's create-task UI can use this to populate a "pick a failed control" selector.

---

### Q5 — WebSocket / real-time for REM-04

**Finding:** Socket.IO is fully operational. The frontend subscribes to events via `socketService.on(event, handler)`. Compliance-related events already exist.

**Existing events in `socketService.ts`:**
- `compliance_alert` (line 98) — broadcast when compliance alert fires.
- `notification` (line 83) — generic.
- `agent_status_change` (line 88) — agent online/offline.

**What is missing for REM-04:**
- No `remediation_update` event is registered in `socketService.ts` or broadcast from any backend endpoint.
- The `compliance_evidence_processor.py` does **not** call `broadcast_compliance_alert` or any WebSocket function after updating `asset_compliance.status`. Status updates are fully silent on the WebSocket bus today.

**Recommended approach for REM-04:**
1. Add `broadcast_remediation_update(tenant_id, payload)` to `websocket_manager.py` (emit event `"remediation_update"`).
2. Call it from `remediation_task_service.update_task(...)` whenever `status` changes to `"resolved"`.
3. Also call it from `agent_tasks_endpoints.py` `report_instruction_result` (line 82) when `compliance_checks` data is processed — this is the hook that fires when the agent posts re-scan results. [ASSUMED] Adding the broadcast call here requires verifying `tenant_id` is available in that handler.
4. Frontend: `socketService.on('remediation_update', handler)` in `RemediationDashboard.tsx` to refresh task list or patch a single task's status in-place.

**Polling fallback:** The frontend can also call `fetchTasks()` on a 30 s interval as fallback for environments without WebSocket (e.g., HTTP-only proxies). Pattern: `useInterval(fetchTasks, 30000)`.

---

### Q6 — Agent command structure

**Finding:** Two instruction channels; both confirmed operational.

**`db.agent_instructions` document shape (insert side, from `compliance_scans_endpoints.py` lines 26–34):**
```json
{
  "agent_id":    "<agent-id>",
  "instruction": "Run Compliance Scan",
  "status":      "pending",
  "created_at":  "<ISO-8601>",
  "created_by":  "<user-email>",
  "priority":    "high"
}
```
When the agent polls `GET /api/agents/{hostname}/instructions`, the response is shaped by `agent_tasks_endpoints.py` lines 48–50:
```json
[{"task_id": "<id>", "instruction": "Run Compliance Scan", "payload": null}]
```

**`send_to_agent` (Socket.IO, `websocket_manager.py` lines 353–365):**
```python
await sio.emit('command', payload, room=sid)
```
Payload shape is freeform; the agent must interpret the `action` key. For compliance re-scan, the recommended payload:
```json
{"action": "compliance_scan", "control_id": "<controlId>", "task_id": "<remediationTaskId>"}
```
The Rust agent dispatches on `instr_type` read from `item["instruction"]` or `item["type"]` or `item["action"]` (poll.rs line 52). This means the Socket.IO `command` event payload needs an `instruction` key set to `"Run Compliance Scan"` for the Rust agent to route it correctly, or the Rust agent's `dispatch_instruction` function needs a new match arm for `"compliance_scan"`.

**Heartbeat response:** The heartbeat endpoint returns only `{"success": True}` (agent_heartbeat_endpoints.py line 427). There is **no** command piggyback in the heartbeat response. Commands go exclusively through the `agent_instructions` collection poll or Socket.IO push.

---

### Q7 — Types

**Finding:** No `RemediationTask` interface exists in `types.ts`. The `Task` interface (line 1393) is generic (`id: number, text, priority, completed`). `MitigationTask` (line 570) is for AI risk mitigation, not compliance.

**Relevant existing types to be aware of:**
- `MitigationTask` (line 570): `{id, description, owner, dueDate, status: "To Do"|"In Progress"|"Done", priority: "Low"|"Medium"|"High"}` — similar shape but wrong domain. Do not reuse or alias.
- `MitigationTaskStatus` (line 556): `"To Do" | "In Progress" | "Done"` — the compliance remediation task should use different casing: `"open" | "in_progress" | "resolved"` to match backend snake_case conventions used in the `compliance_automation_api.py` POST handler.

**Type to add (from PATTERNS.md):**
```typescript
export interface RemediationTask {
    id: string;
    title: string;
    control_id: string;
    asset_id: string;
    framework_id?: string;
    status: 'open' | 'in_progress' | 'resolved' | 'dismissed';
    priority: 'low' | 'medium' | 'high' | 'critical';
    assignee?: string;
    due_date?: string;
    description?: string;
    resolution_notes?: string;
    agent_id?: string;
    created_by: string;
    created_at: string;
    updated_at: string;
    tenantId: string;
}
```
[ASSUMED] `asset_id` field is not in the PATTERNS.md spec but is needed for agent lookup. Adding it to the type is safe — the backend service will use it for agent resolution during dispatch.

---

## Standard Stack

### Core (existing — no new installs)
| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| FastAPI | existing | Backend routing, Pydantic validation | Already installed |
| Motor (AsyncIOMotorDatabase) | existing | Async MongoDB CRUD | Already in all endpoints |
| python-socketio | existing | WebSocket broadcast via `websocket_manager.py` | Already installed |
| React + TypeScript | existing | Frontend component | Already installed |
| socket.io-client | existing | Frontend WebSocket subscription via `socketService.ts` | Already installed |

No new packages are required. This phase is pure application code on top of existing infrastructure.

---

## Package Legitimacy Audit

Not applicable — no new packages are installed in this phase.

---

## Architecture Patterns

### System Architecture Diagram

```
User Browser
    │
    │  CRUD (create task, filter, mark resolved)
    ▼
RemediationDashboard.tsx
RemediationTaskModal.tsx
    │
    │  authFetch  POST/GET/PATCH  /api/remediation/tasks[/{id}[/dispatch]]
    ▼
remediation_task_endpoints.py
    │
    │  calls
    ▼
remediation_task_service.py
    │                            │
    │  upsert                    │  agent_instructions.insert_one
    ▼                            ▼
MongoDB                      MongoDB
compliance_remediation_tasks  agent_instructions
                                    │
                                    │  polls every 5 s
                                    ▼
                              Agent (Rust or Python)
                                    │
                                    │  "Run Compliance Scan"
                                    │  POST /api/agents/{id}/instructions/result
                                    ▼
                              agent_tasks_endpoints.py
                              report_instruction_result()
                                    │
                                    │  process_automated_evidence()
                                    ▼
                              compliance_evidence_processor.py
                                    │  updates asset_compliance.status
                                    │
                                    ▼
                              (broadcast_remediation_update — NEW)
                              websocket_manager.py
                                    │
                                    │  Socket.IO  "remediation_update"
                                    ▼
                              socketService.ts
                                    │
                                    ▼
                              RemediationDashboard.tsx  (patches task status live)
```

### Recommended Project Structure — New Files Only

```
backend/
├── remediation_task_endpoints.py   # NEW: CRUD + /dispatch sub-resource
├── remediation_task_service.py     # NEW: DB logic for compliance_remediation_tasks

components/
├── RemediationDashboard.tsx        # NEW: task list + filter bar + "Create" button
├── RemediationTaskModal.tsx        # NEW: create/edit form modal

services/apiService.ts              # EXTEND: add createRemediationTask, updateRemediationTask, dispatchRemediationScan, getRemediationTasks

types.ts                            # EXTEND: add RemediationTask interface, add 'remediationWorkflow' to AppView

components/Sidebar.tsx              # EXTEND: add nav item under Compliance group

backend/websocket_manager.py        # EXTEND: add broadcast_remediation_update()

backend/router_registry.py         # EXTEND: _load(app, "remediation_task_endpoints", "router") in required section
```

### Pattern 1: Tenant-scoped endpoint (from PATTERNS.md)

```python
# Source: backend/mdr_endpoints.py lines 32–39 (analogue verified in codebase)
_SUPER_ADMIN_ROLES = {"Super Admin", "superadmin", "super_admin", "platform-admin"}

def _tenant_filter(user: dict) -> dict:
    if user.get("role") in _SUPER_ADMIN_ROLES:
        return {}
    tenant = user.get("tenantId") or user.get("tenant_id") or ""
    return {"tenantId": tenant} if tenant else {}
```

### Pattern 2: Agent instruction dispatch for re-scan (REM-03)

```python
# Source: backend/compliance_scans_endpoints.py lines 68–76 (verified in codebase)
async def dispatch_rescan(task: dict, db, created_by: str) -> dict:
    agent_id = task.get("agent_id")
    if not agent_id:
        # Resolve via asset → agentId
        asset = await db.assets.find_one({"id": task.get("asset_id")})
        agent_id = asset.get("agentId") if asset else None
    if not agent_id:
        return {"dispatched": False, "reason": "Agent not found for asset"}
    await db.agent_instructions.insert_one({
        "agent_id": agent_id,
        "instruction": "Run Compliance Scan",
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": created_by,
        "priority": "high",
        "control_id": task.get("control_id"),
        "remediation_task_id": task["id"],
    })
    # Attempt Socket.IO push; non-fatal if offline
    from websocket_manager import send_to_agent
    await send_to_agent(agent_id, {
        "action": "compliance_scan",
        "instruction": "Run Compliance Scan",
        "control_id": task.get("control_id"),
        "task_id": task["id"],
    })
    return {"dispatched": True, "agent_id": agent_id}
```

### Pattern 3: WebSocket broadcast (extend websocket_manager.py)

```python
# Source: backend/websocket_manager.py lines 287–295 (exact copy of broadcast_compliance_alert)
async def broadcast_remediation_update(tenant_id: str, payload: dict) -> None:
    """Push a remediation task status change to all connected clients of a tenant."""
    if tenant_id not in connected_clients:
        return
    payload["timestamp"] = payload.get("timestamp", datetime.now(timezone.utc).isoformat())
    for sid in list(connected_clients[tenant_id]):
        await sio.emit("remediation_update", payload, room=sid)
    logger.debug("Remediation update broadcast to tenant %s", tenant_id)
```

### Pattern 4: Frontend WebSocket subscription (teardown required)

```typescript
// Source: components/SiemRulesDashboard.tsx lines 44–55 (analogue verified in codebase)
useEffect(() => {
    const onUpdate = (data: any) => {
        setTasks(prev => prev.map(t =>
            t.id === data.task_id ? { ...t, ...data } : t
        ));
    };
    socketService.on('remediation_update', onUpdate);
    return () => socketService.off('remediation_update', onUpdate);
}, []);
```

### Anti-Patterns to Avoid

- **Writing `body.dict()` instead of `body.model_dump()`**: Codebase is Pydantic v2. `dict()` is deprecated. Use `model_dump(exclude_none=True)` on update bodies.
- **Blocking the event loop in `route.py` with synchronous DB**: Always `await` Motor calls.
- **Colliding with `remediation_tasks` collection**: `continuous_compliance_service.py` uses a `remediation_tasks` collection. Use `compliance_remediation_tasks` for Phase 4 to avoid schema confusion.
- **Registering the router in the optional section**: New feature routers must go in the required `register_all_routers` body. The optional section is for experimental/unstable routers that must not block app startup if broken.
- **Sending `"Run Compliance Scan"` via Socket.IO only**: The instruction must also be inserted into `db.agent_instructions` as the primary delivery mechanism. Socket.IO push is supplemental — agents not connected via WebSocket must still receive the instruction.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Agent instruction delivery | Custom polling endpoint | `db.agent_instructions` insert + `send_to_agent()` | Both paths already operational; agents poll `/api/agents/{hostname}/instructions` every 5 s |
| WebSocket broadcast | Custom event emitter | `broadcast_remediation_update()` added to `websocket_manager.py` | All tenant session tracking is centralized there; reinventing it creates race conditions |
| Tenant access scoping | Per-endpoint JWT inspection | `_tenant_filter(current_user)` helper | Pattern used in 20+ endpoints; avoids inconsistency |
| Compliance result processing | Custom heartbeat handler | Existing `process_automated_evidence()` in `compliance_evidence_processor.py` | Already maps agent checks to control IDs and updates `asset_compliance.status` |
| Frontend auth headers | Manual `Authorization` header | `authFetch` from `services/apiService.ts` | `authFetch` handles token injection and JSON content-type automatically |

---

## Common Pitfalls

### Pitfall 1: Rust agent instruction string mismatch

**What goes wrong:** The dispatch endpoint writes `"Run Compliance Scan"` to `agent_instructions`. The Rust agent (`poll.rs` line 260) only matches `"run_compliance_check"` | `"Run Compliance Check"`. Rust-based agents will silently ignore the instruction.

**Why it happens:** The Python agent and Rust agent have diverged in instruction string handling. The Python agent (line 623) matches `"Run Compliance Scan"` exactly; the Rust agent does not.

**How to avoid:** Either (a) write both `"Run Compliance Scan"` and `"Run Compliance Check"` instructions (one per string), or (b) add `"Run Compliance Scan"` as a match arm in `poll.rs` `dispatch_instruction`. Option (b) keeps the DB clean. Flag in PLAN.md as a Wave 0 task.

**Warning signs:** Rust agent receives instruction (status changes to `"sent"`) but never posts a result; `db.agent_instructions.status` stays `"sent"` indefinitely.

---

### Pitfall 2: Agent lookup failure when `asset_id` has no `agentId`

**What goes wrong:** `compliance_remediation_tasks` stores `asset_id`. At dispatch time, `db.assets.find_one({"id": asset_id})` may not have an `agentId` field if the asset was created from seed data or has no enrolled agent.

**Why it happens:** `assets.agentId` is only set when an agent heartbeat includes a `hostname` that matches `f"asset-{hostname}"` (heartbeat_endpoints.py line 121). Seeded or cloud assets may have no enrolled agent.

**How to avoid:** Return `{"dispatched": False, "reason": "No agent enrolled for this asset"}` rather than raising 500. The task remains `"open"` for manual follow-up.

---

### Pitfall 3: Missing `tenantId` in broadcast when calling from `report_instruction_result`

**What goes wrong:** `broadcast_remediation_update` needs a `tenant_id`. The `report_instruction_result` handler (agent_tasks_endpoints.py line 54) authenticates via `verify_agent_key`, which returns the tenant dict. But if the instruction result triggers evidence processing, the compliance update is written without any WebSocket push (the processor has no broadcast call today).

**Why it happens:** `process_automated_evidence` was not designed with real-time push in mind.

**How to avoid:** After calling `process_automated_evidence`, query `db.compliance_remediation_tasks` for any open task whose `control_id` matches the updated control, then call `broadcast_remediation_update`. Guard with `try/except` so a broadcast failure never breaks the result-posting flow.

---

### Pitfall 4: File size limit violation (CLAUDE.md)

**What goes wrong:** `RemediationDashboard.tsx` risks exceeding the 500-line limit if task list, filter bar, and create modal are all in one file.

**How to avoid:** Split modal into `RemediationTaskModal.tsx` from the start. Keep `RemediationDashboard.tsx` to list + filter + button; delegate all form state to the modal component.

---

### Pitfall 5: Router registration in optional section

**What goes wrong:** If `remediation_task_endpoints.py` is registered in the `_OPTIONAL` list, a startup import error would silently omit all Phase 4 endpoints with no user-visible failure.

**How to avoid:** Add `_load(app, "remediation_task_endpoints", "router")` in the required `register_all_routers` body (after line 144, inside "Operations & Automation" or "Compliance & Governance" section).

---

## Code Examples

### Backend — service create_task

```python
# Source: pattern from backend/continuous_compliance_service.py lines 268–285 + mdr_endpoints.py
import uuid
from datetime import datetime, timezone

async def create_task(db, data: dict, tenant_filter: dict, created_by: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    task = {
        "id": str(uuid.uuid4()),
        "title": data["title"],
        "control_id": data["control_id"],
        "asset_id": data.get("asset_id", ""),
        "framework_id": data.get("framework_id", ""),
        "status": "open",
        "priority": data.get("priority", "medium"),
        "assignee": data.get("assignee", ""),
        "due_date": data.get("due_date"),
        "description": data.get("description", ""),
        "resolution_notes": None,
        "agent_id": data.get("agent_id"),
        "tenantId": tenant_filter.get("tenantId", ""),
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
    }
    await db.compliance_remediation_tasks.insert_one(task)
    task.pop("_id", None)
    return task
```

### Backend — endpoint registration snippet

```python
# Add to backend/router_registry.py after line 144 (Operations & Automation group)
_load(app, "remediation_task_endpoints", "router")
```

### Frontend — status filter bar

```typescript
// Source: pattern from components/SiemRulesDashboard.tsx (filter UI block)
const STATUSES = ['all', 'open', 'in_progress', 'resolved'];

const filtered = tasks.filter(t =>
    filterStatus === 'all' || t.status === filterStatus
);

// Render:
<div className="flex gap-2 mb-4">
    {STATUSES.map(s => (
        <button
            key={s}
            onClick={() => setFilterStatus(s)}
            className={`px-3 py-1 rounded-full text-xs font-medium capitalize transition
                ${filterStatus === s
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'}`}
        >
            {s.replace('_', ' ')}
        </button>
    ))}
</div>
```

---

## REM Requirement to Implementation Map

| Req | Behavior | Implementation |
|-----|----------|---------------|
| REM-01 | Create task with title, assignee, due date, description | `POST /api/remediation/tasks` → `remediation_task_service.create_task()` → `db.compliance_remediation_tasks`. Modal inputs: title (required), control_id (required), assignee, due_date, description, priority. |
| REM-02 | List tasks, filterable by Open / In Progress / Resolved | `GET /api/remediation/tasks?status={open\|in_progress\|resolved}` → return filtered cursor. Frontend: status chip filter in `RemediationDashboard.tsx`. |
| REM-03 | Mark Resolved → dispatch re-scan to assigned agent | `PATCH /api/remediation/tasks/{id}` sets `status: "resolved"` + triggers `dispatch_rescan()`. Service inserts `"Run Compliance Scan"` to `agent_instructions` and calls `send_to_agent`. |
| REM-04 | Compliance status auto-updates when new evidence arrives | Agent posts result → `report_instruction_result` → `process_automated_evidence` → `asset_compliance.status` updated. New: `broadcast_remediation_update` pushed to frontend. Frontend patches task status in-place on `remediation_update` event. |

---

## Runtime State Inventory

Not applicable — this is a greenfield feature addition. No rename or migration is involved.

---

## Environment Availability

| Dependency | Required By | Available | Notes |
|------------|------------|-----------|-------|
| MongoDB | Task CRUD | Confirmed (already in use) | `compliance_remediation_tasks` collection auto-created on first insert |
| Socket.IO (python-socketio) | REM-04 broadcast | Confirmed (websocket_manager.py operational) | No config change needed |
| FastAPI | New endpoints | Confirmed (already running) | |
| Agent (Python or Rust) | REM-03 re-scan | Present in repo | Rust agent needs `"Run Compliance Scan"` match arm if Rust agents are deployed |

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + httpx AsyncClient |
| Config file | `backend/tests/conftest.py` |
| Quick run command | `cd backend && python -m pytest tests/test_smoke_endpoints.py -x -q` |
| Full suite command | `cd backend && python -m pytest tests/ -q` |

### Phase Requirements Test Map

| Req ID | Behavior | Test Type | Automated Command |
|--------|----------|-----------|-------------------|
| REM-01 | POST /api/remediation/tasks creates task | unit/integration | `pytest tests/test_remediation_tasks.py::test_create_task -x` |
| REM-02 | GET /api/remediation/tasks?status=open filters | unit/integration | `pytest tests/test_remediation_tasks.py::test_list_tasks_filter -x` |
| REM-03 | PATCH status=resolved inserts agent instruction | unit/integration | `pytest tests/test_remediation_tasks.py::test_dispatch_rescan -x` |
| REM-04 | Compliance status updates after re-scan | integration | `pytest tests/test_remediation_tasks.py::test_compliance_status_update -x` |

### Wave 0 Gaps

- [ ] `backend/tests/test_remediation_tasks.py` — covers REM-01 through REM-04 (does not exist yet)
- [ ] `backend/remediation_task_endpoints.py` — does not exist yet (Wave 0 implementation)
- [ ] `backend/remediation_task_service.py` — does not exist yet

---

## Security Domain

`security_enforcement: true` per `.planning/config.json`. ASVS Level 1.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `get_current_user` Depends on all endpoints |
| V3 Session Management | no | Stateless JWT; no server session |
| V4 Access Control | yes | `_tenant_filter(current_user)` — tenant isolation on all reads/writes |
| V5 Input Validation | yes | Pydantic `Field(..., min_length=1, max_length=300)` on title; max_length on all string fields |
| V6 Cryptography | no | No new crypto in this phase |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cross-tenant task access | Information Disclosure | `_tenant_filter` applied on every query; tested in conftest |
| Injecting arbitrary `agent_id` in task creation | Tampering | Validate `agent_id` exists in `db.agents` with matching `tenantId` before storing |
| Unbounded list response | DoS | `to_list(length=500)` cap on GET list query |
| Dispatch to offline/wrong agent | Elevation of Privilege | Return `{"dispatched": False}` when `send_to_agent` returns `False`; do not fail silently |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Adding `broadcast_remediation_update` call inside `report_instruction_result` to trigger REM-04 is safe — `tenant_id` is available from the agent key. | Q5, REM-04 | If `tenant_id` is not resolvable in that handler, the broadcast must be moved to a post-update hook in the service layer instead |
| A2 | `asset_id` field should be added to `RemediationTask` interface beyond what PATTERNS.md specifies. | Q7 | Minor: backend service may use `control_id` + `assetId` lookup without storing asset_id explicitly. Verify in service design. |
| A3 | The new collection name should be `compliance_remediation_tasks` to avoid collision with `continuous_compliance_service`'s `remediation_tasks`. | Q1 | Low risk: different collection names simply coexist in MongoDB; wrong only if future code queries the wrong collection |

---

## Open Questions

1. **Rust agent instruction string (OPEN)**
   - What we know: Rust agent matches `"run_compliance_check"` / `"Run Compliance Check"` (poll.rs line 260). Python agent matches `"Run Compliance Scan"` (agent.py line 623).
   - What's unclear: Whether deployed environments primarily use Rust or Python agents.
   - Recommendation: Add `"Run Compliance Scan"` to the Rust agent match arm in Wave 0, or insert two instructions per dispatch. Plan task must cover this.

2. **Sidebar placement (OPEN)**
   - What we know: `aiRemediation` is under the AI section (line 372). Compliance evidence is under Compliance (line 344).
   - What's unclear: Whether `remediationWorkflow` should live under Compliance or Operations in the sidebar.
   - Recommendation: Place under Compliance group next to `complianceEvidence`. Requires only a sidebar line addition — safe to decide at plan time.

3. **Agent `agent_id` storage in task (RESOLVED)**
   - Tasks should store `agent_id` resolved at task-create time (look up `assets.agentId` from `assetId`), so dispatch does not need a second lookup. If not resolvable at create time, store `null` and resolve at dispatch time.

4. **Partial compliance update broadcast (OPEN)**
   - What we know: `process_automated_evidence` updates `asset_compliance.status` but does not call any broadcast.
   - What's unclear: Whether the planner should add a broadcast call inside `process_automated_evidence` (changing a shared file) or inside `report_instruction_result` (safer, more scoped).
   - Recommendation: Add in `report_instruction_result` to minimize changes to shared infrastructure.

---

## Sources

### Primary (HIGH confidence)
- `backend/agent_heartbeat_endpoints.py` — agent instruction dispatch patterns, task_feedback processing
- `backend/agent_tasks_endpoints.py` — instruction CRUD, `report_instruction_result`, `get_agent_instructions` poll endpoint
- `backend/compliance_scans_endpoints.py` — exact instruction dispatch pattern for compliance re-scan
- `backend/compliance_evidence_processor.py` — `asset_compliance` schema, status values, agent→asset linking
- `backend/compliance_evidence_endpoints.py` — `asset_compliance` CRUD, tenant scoping
- `backend/websocket_manager.py` — `broadcast_compliance_alert` template, `send_to_agent`, `agent_sessions`
- `services/socketService.ts` — existing event subscriptions, connection lifecycle
- `backend/router_registry.py` — all registered routers, required vs optional distinction
- `backend/remediation_endpoints.py` + `backend/remediation_service.py` — existing AI remediation (different domain)
- `backend/continuous_compliance_service.py` — existing `create_remediation_task` method, `remediation_tasks` collection
- `backend/compliance_automation_api.py` — existing POST endpoint for creating remediation tasks
- `agent/agent.py` lines 622–641 — Python agent `"Run Compliance Scan"` handler
- `agent-rust/src/poll.rs` lines 255–265 — Rust agent `"run_compliance_check"` handler
- `types.ts` — `MitigationTask`, `Task`, `AppView`, `Permission` types
- `.planning/phases/04-remediation-workflow/04-PATTERNS.md` — code patterns derived from codebase analogue search

### Secondary (MEDIUM confidence)
- `backend/rbac_utils.py` — `manage:compliance` permission confirmed for Tenant Admin and above

---

## Metadata

**Confidence breakdown:**
- Existing infrastructure: HIGH — all files read directly from codebase
- Agent dispatch mechanism: HIGH — Python agent and Rust agent both confirmed
- Data model: HIGH — read from actual processor and endpoint files
- WebSocket broadcast gap: HIGH — no `broadcast_remediation_update` call found anywhere
- Frontend component gaps: HIGH — no `RemediationDashboard.tsx` for compliance remediation found

**Research date:** 2026-06-18
**Valid until:** 2026-07-18 (stable backend; agent instruction format changes would invalidate Q6 findings)
