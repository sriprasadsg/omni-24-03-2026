# Phase 4: Remediation Workflow — Pattern Map

**Mapped:** 2026-06-18
**Files analyzed:** 7 new/modified files
**Analogs found:** 7 / 7

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `backend/remediation_task_endpoints.py` | controller | CRUD + request-response | `backend/mdr_endpoints.py` | exact |
| `backend/remediation_task_service.py` | service | CRUD | (no direct analog — infer from mdr_endpoints calling svc.*) | role-match |
| `backend/websocket_manager.py` (extend) | middleware/broadcaster | event-driven | `backend/websocket_manager.py` (existing) | exact |
| `services/apiService.ts` (extend) | utility | request-response | lines 3820–3852 (tasks CRUD block) | exact |
| `components/RemediationDashboard.tsx` | component | CRUD + event-driven | `components/SiemRulesDashboard.tsx` | exact |
| `components/RemediationTaskModal.tsx` | component | request-response | `components/SiemRulesDashboard.tsx` inline form panel | role-match |
| `types.ts` (extend) | config | — | `types.ts` existing interfaces | exact |

---

## Pattern Assignments

### `backend/remediation_task_endpoints.py` (controller, CRUD)

**Analog:** `backend/mdr_endpoints.py` (lines 1–176)

**Imports pattern** (mdr_endpoints.py lines 17–28):
```python
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from authentication_service import get_current_user
import remediation_task_service as svc

logger = logging.getLogger(__name__)
```

**Router + prefix pattern** (mdr_endpoints.py line 30):
```python
router = APIRouter(prefix="/api/remediation", tags=["Remediation"])
```

**Tenant-scoping helper** (mdr_endpoints.py lines 32–39):
```python
_SUPER_ADMIN_ROLES = {"Super Admin", "superadmin", "super_admin", "platform-admin"}

def _tenant_filter(user: dict) -> dict:
    if user.get("role") in _SUPER_ADMIN_ROLES:
        return {}
    tenant = user.get("tenantId") or user.get("tenant_id") or ""
    return {"tenantId": tenant} if tenant else {}
```
Copy this verbatim — all list/patch endpoints need tenant scoping applied the same way.

**Pydantic request body pattern** (mdr_endpoints.py lines 46–72):
```python
class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    control_id: str
    framework_id: str
    assignee: str = ""
    due_date: Optional[str] = None
    description: str = ""
    priority: str = "medium"

class TaskUpdate(BaseModel):
    status: Optional[str] = None
    assignee: Optional[str] = None
    due_date: Optional[str] = None
    resolution_notes: Optional[str] = None
```
Use `BaseModel` + `Field` for creates; all update fields are `Optional`. Never use raw `dict` or `Form` — every existing CRUD endpoint in this codebase uses Pydantic.

**GET list with optional status filter** (mdr_endpoints.py lines 102–108):
```python
@router.get("/tasks")
async def list_tasks(
    status: Optional[str] = Query(None),
    control_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    tf = _tenant_filter(current_user)
    return await svc.list_tasks(tf, status=status, control_id=control_id)
```

**POST create (status_code=201)** (mdr_endpoints.py lines 111–121):
```python
@router.post("/tasks", status_code=201)
async def create_task(
    body: TaskCreate,
    current_user: dict = Depends(get_current_user),
):
    tf = _tenant_filter(current_user)
    return await svc.create_task(
        body.model_dump(),
        tenant_filter=tf,
        created_by=current_user.get("email") or current_user.get("username") or "unknown",
    )
```

**PATCH update with 404 guard** (mdr_endpoints.py lines 124–134):
```python
@router.patch("/tasks/{task_id}")
async def update_task(
    task_id: str,
    body: TaskUpdate,
    current_user: dict = Depends(get_current_user),
):
    tf = _tenant_filter(current_user)
    result = await svc.update_task(task_id, body.model_dump(exclude_none=True), tf)
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return result
```
Always call `body.model_dump(exclude_none=True)` on update bodies — this lets callers send partial updates without overwriting fields with `None`.

**Agent re-dispatch action endpoint** — no existing exact analog. Closest is the heartbeat endpoint's `task_feedback` block (agent_heartbeat_endpoints.py lines 412–425). Use a POST sub-resource:
```python
@router.post("/tasks/{task_id}/dispatch", status_code=202)
async def dispatch_rescan(
    task_id: str,
    current_user: dict = Depends(get_current_user),
):
    tf = _tenant_filter(current_user)
    task = await svc.get_task(task_id, tf)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    sent = await send_to_agent(task["agent_id"], {
        "action": "compliance_scan",
        "control_id": task["control_id"],
        "task_id": task_id,
    })
    return {"dispatched": sent, "agent_id": task["agent_id"]}
```

**Router registration** — add one line to `backend/router_registry.py` following line 144:
```python
_load(app, "remediation_task_endpoints", "router")
```

**Gotchas:**
- `body.model_dump()` not `body.dict()` — the codebase uses Pydantic v2 throughout (see mdr_endpoints.py line 119).
- Do NOT raise inside `_tenant_filter` — return `{}` for super-admins and let the service handle it.
- The heartbeat endpoint returns `{"success": True}` (line 427), not a structured object. The dispatch endpoint should return `{"dispatched": bool, "agent_id": str}` so the frontend can surface failures.

---

### `backend/websocket_manager.py` — add `broadcast_remediation_update`

**Analog:** `broadcast_compliance_alert` (websocket_manager.py lines 287–295) and `broadcast_siem_rule_match` (lines 319–334).

**Pattern to copy** (lines 287–295):
```python
async def broadcast_remediation_update(tenant_id: str, payload: dict) -> None:
    """Push a remediation task status change to all connected clients of a tenant."""
    if tenant_id not in connected_clients:
        return
    payload["timestamp"] = payload.get("timestamp", datetime.now(timezone.utc).isoformat())
    for sid in list(connected_clients[tenant_id]):
        await sio.emit("remediation_update", payload, room=sid)
    logger.debug("Remediation update broadcast to tenant %s", tenant_id)
```

**Agent direct command** — `send_to_agent` already exists (lines 353–365):
```python
async def send_to_agent(agent_id: str, payload: dict) -> bool:
    sid = agent_sessions.get(agent_id)
    if not sid:
        return False
    await sio.emit('command', payload, room=sid)
    return True
```
Import and call `send_to_agent` from the endpoint. Do NOT duplicate this logic.

**Gotcha:** The agent listens on the `command` event (line 361). The payload must include an `action` key so the agent-side dispatcher can route it. The Rust agent already has a task dispatch loop driven by `task_feedback` keys in the heartbeat meta — confirm the agent handles `action: "compliance_scan"` before wiring the dispatch endpoint.

---

### `services/apiService.ts` — extend with remediation CRUD helpers

**Analog:** lines 3820–3852 (existing tasks CRUD block — exact pattern match).

**POST pattern** (lines 3831–3838):
```typescript
export const createRemediationTask = async (body: {
    title: string;
    control_id: string;
    framework_id: string;
    assignee?: string;
    due_date?: string;
    description?: string;
    priority?: string;
}) => {
    const res = await authFetch(`${API_BASE}/remediation/tasks`, {
        method: 'POST',
        body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error('Failed to create remediation task');
    return await res.json();
};
```

**PATCH pattern** (lines 3840–3847):
```typescript
export const updateRemediationTask = async (
    id: string,
    updates: { status?: string; assignee?: string; due_date?: string; resolution_notes?: string }
) => {
    const res = await authFetch(`${API_BASE}/remediation/tasks/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(updates),
    });
    if (!res.ok) throw new Error('Failed to update remediation task');
    return await res.json();
};
```

**Dispatch action pattern** (use POST, not PATCH — matches sub-resource convention seen in `/tickets/${id}/escalate` at line 3996):
```typescript
export const dispatchRemediationScan = async (taskId: string) => {
    const res = await authFetch(`${API_BASE}/remediation/tasks/${taskId}/dispatch`, {
        method: 'POST',
        body: JSON.stringify({}),
    });
    if (!res.ok) throw new Error('Failed to dispatch rescan');
    return await res.json();
};
```

**Gotcha:** `authFetch` automatically sets `Content-Type: application/json` when body is not `FormData` (apiService.ts line 208). Never set it manually. Always `throw` on `!res.ok` for mutation calls; use `try/catch` with fallback return for read calls.

---

### `components/RemediationDashboard.tsx` (component, CRUD + event-driven)

**Analog:** `components/SiemRulesDashboard.tsx` (lines 1–346) — identical role and data flow.

**State management pattern** (SiemRulesDashboard.tsx lines 14–26):
```typescript
const [tasks, setTasks] = useState<RemediationTask[]>([]);
const [loading, setLoading] = useState(false);
const [filterStatus, setFilterStatus] = useState<string>('all');
const [isCreating, setIsCreating] = useState(false);
const [editingTask, setEditingTask] = useState<RemediationTask | null>(null);
```

**Fetch + useCallback pattern** (SiemRulesDashboard.tsx lines 28–38):
```typescript
const fetchTasks = useCallback(async () => {
    setLoading(true);
    try {
        const res = await api.authFetch('/api/remediation/tasks');
        if (res.ok) setTasks(await res.json());
    } catch (e) {
        console.error(e);
    } finally {
        setLoading(false);
    }
}, []);

useEffect(() => { fetchTasks(); }, [fetchTasks]);
```

**WebSocket subscription pattern** (SiemRulesDashboard.tsx lines 44–55):
```typescript
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

**Status badge pattern** (SiemRulesDashboard.tsx lines 6–11 — SEV_COLORS map):
```typescript
const STATUS_COLORS: Record<string, string> = {
    open:        'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
    in_progress: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
    resolved:    'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
    dismissed:   'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400',
};
```
Use `<span className={STATUS_COLORS[task.status] ?? STATUS_COLORS.open}>` — always provide a fallback key via `??`.

**Gotcha:** Do not inline the create/edit form in the same file if it grows beyond 500 lines — split into `RemediationTaskModal.tsx`. The CLAUDE.md 500-line rule is hard.

---

### `components/RemediationTaskModal.tsx` (component, request-response)

**Analog:** The inline form panel in `components/SiemRulesDashboard.tsx` (lines 157–237).

**Controlled input pattern** (SiemRulesDashboard.tsx lines 163–169):
```tsx
const [title, setTitle] = useState('');
const [assignee, setAssignee] = useState('');
const [dueDate, setDueDate] = useState('');
const [description, setDescription] = useState('');
const [priority, setPriority] = useState('medium');

// Each field:
<input
    type="text"
    value={title}
    onChange={e => setTitle(e.target.value)}
    className="w-full p-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white"
    placeholder="Remediation task title"
/>
```

**Save handler pattern** (SiemRulesDashboard.tsx lines 64–80):
```typescript
const handleSave = async () => {
    try {
        if (editingTask) {
            await api.updateRemediationTask(editingTask.id, { ... });
        } else {
            await api.createRemediationTask({ title, assignee, due_date: dueDate, ... });
        }
        onClose();
        onRefresh();
    } catch (e) {
        console.error(e);
    }
};
```

**Cancel + save buttons** (SiemRulesDashboard.tsx lines 221–234):
```tsx
<div className="flex justify-end gap-3 mt-4">
    <button
        onClick={onClose}
        className="px-4 py-2 border rounded text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 text-sm"
    >
        Cancel
    </button>
    <button
        onClick={handleSave}
        className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded flex items-center gap-2 text-sm"
    >
        Save Task
    </button>
</div>
```

**Gotcha:** The modal receives `isOpen`, `onClose`, `task` (nullable), and `onRefresh` as props — mirror the `AgentDetailModalProps` pattern (AgentDetailModal.tsx lines 17–29). Always guard with `if (!isOpen) return null;` as the first line of the render.

---

### `types.ts` — extend with RemediationTask type

**Analog:** `types.ts` — `Control` interface (lines 443–452) and `AssetCompliance` interface (lines 461–476).

**Type alias vs interface rule:** This codebase mixes both but uses `interface` for object shapes with optional fields and `type` for unions/primitives. Use `interface` for `RemediationTask`.

**Optional field pattern** (types.ts line 447: `category?: string`):
```typescript
export interface RemediationTask {
    id: string;
    title: string;
    control_id: string;
    framework_id: string;
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
Add `'remediationWorkflow'` to the `AppView` union at types.ts line 5 if the dashboard gets a sidebar route.

**Gotcha:** `tenantId` (camelCase) is the consistent field name throughout the codebase — do not use `tenant_id` in the TypeScript type even though the Python service uses snake_case internally.

---

## Shared Patterns

### Authentication (apply to all backend endpoints)
**Source:** `backend/mdr_endpoints.py` lines 32–39 + `Depends(get_current_user)` on every handler.
```python
from authentication_service import get_current_user
# ...
current_user: dict = Depends(get_current_user)
tf = _tenant_filter(current_user)
```

### WebSocket broadcast (apply when task status changes)
**Source:** `backend/websocket_manager.py` lines 257–273 (`broadcast_agent_status_change` as template).
Import at point of use:
```python
from websocket_manager import broadcast_remediation_update
await broadcast_remediation_update(tenant_id, {"task_id": task_id, "status": new_status, ...})
```

### Agent direct command (apply to dispatch endpoint)
**Source:** `backend/websocket_manager.py` lines 353–365 (`send_to_agent`).
```python
from websocket_manager import send_to_agent
sent = await send_to_agent(agent_id, {"action": "compliance_scan", "control_id": ..., "task_id": ...})
```

### Frontend event subscription teardown (apply to all components with WS)
**Source:** `components/SiemRulesDashboard.tsx` lines 44–55.
```typescript
useEffect(() => {
    const handler = (data: any) => { /* ... */ };
    socketService.on('remediation_update', handler);
    return () => socketService.off('remediation_update', handler);  // always clean up
}, []);
```

### authFetch Content-Type (apply to all apiService functions)
**Source:** `services/apiService.ts` lines 205–208.
Never set `Content-Type` manually. `authFetch` sets it to `application/json` automatically unless the body is `FormData`.

---

## Agent Dispatch — Architecture Note

The heartbeat endpoint (`backend/agent_heartbeat_endpoints.py`) returns only `{"success": True}` (line 427). There is **no polling command queue** in the heartbeat response. The agent command path is push-only via `send_to_agent` → Socket.IO `command` event. This means:

1. The dispatch endpoint calls `send_to_agent(agent_id, {...})` immediately.
2. If the agent is offline (`send_to_agent` returns `False`), the endpoint should return `{"dispatched": false}` and leave the task in `open` state for retry.
3. Do NOT build a command queue in MongoDB for this phase — the existing Socket.IO push is sufficient and matches the existing codebase pattern.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `backend/remediation_task_service.py` | service | CRUD | No standalone service module found with a clear analog — infer the pattern from how `mdr_endpoints.py` calls `mdr_service.py` (pass `tenant_filter` dict + caller identity string to every write function) |

---

## Metadata

**Analog search scope:** `backend/`, `components/`, `services/`, `types.ts`
**Files scanned:** 8 source files read
**Pattern extraction date:** 2026-06-18
