---
phase: "04"
status: findings
depth: standard
reviewed_at: 2026-06-18
files_reviewed: 7
files_reviewed_list:
  - backend/compliance_remediation_service.py
  - backend/compliance_remediation_endpoints.py
  - backend/ai_service.py
  - backend/agent_tasks_endpoints.py
  - backend/websocket_manager.py
  - components/RemediationDashboard.tsx
  - components/RemediationTaskModal.tsx
findings:
  critical: 4
  warning: 4
  info: 2
  total: 10
---

# Phase 04: Code Review Report

**Reviewed:** 2026-06-18
**Depth:** standard
**Files Reviewed:** 7
**Status:** findings

## Summary

The Phase 04 compliance remediation workflow implements task CRUD, AI-assisted suggestions,
rescan dispatch, and WebSocket broadcasting. The tenant isolation model is largely sound, but
four critical defects were found: (1) the AI suggestion persist write lacks a tenant filter,
creating a cross-tenant write vector; (2) `agent_id` sourced from user-submitted task data
flows into `agent_instructions` without any verification against the database, enabling
arbitrary agent targeting; (3) the `agent_instructions` insert in `dispatch_rescan` omits
`tenantId`, breaking the tenant-scoped poll query in `get_agent_instructions`; and (4) the
React component calls hooks after a conditional early return, violating the Rules of Hooks and
causing runtime crashes.

---

## Critical Issues

### CR-01: AI suggestion persist bypasses tenant scope — cross-tenant write

**File:** `backend/compliance_remediation_endpoints.py:159-162`

**Issue:** The `update_one` that writes `ai_suggestion` back to the task uses only `{"id": task_id}` as the filter. The task was already fetched with `tenant_filter` (line 132), so the tenant is known. However the persist call does not include it. A user who discovers a valid `task_id` from another tenant (e.g., via timing or enumeration), but whose task lookup returns 404 before this write executes, is not the issue — the real problem is that if `task_id` is ever reused or if a race allows a different tenant's document to match, the write lands on the wrong tenant. More concretely, a Super Admin calling this endpoint with an empty `tf = {}` will correctly reach the doc, but a non-admin with an injected or guessed `task_id` whose document happens to share the ID could overwrite the wrong record if the tenant filter is absent.

**Fix:**
```python
await db.compliance_remediation_tasks.update_one(
    {"id": task_id, **tf},          # tf is already in scope at line 129
    {"$set": {"ai_suggestion": text}},
)
```

---

### CR-02: `agent_id` in `dispatch_rescan` is not validated — arbitrary agent targeting

**File:** `backend/compliance_remediation_service.py:121-165`

**Issue:** `dispatch_rescan` takes `agent_id` from `task.get("agent_id")`. The task was originally created from user-supplied `data.get("agent_id", "")` in `create_task` (line 33), which was never verified to exist in the `agents` collection or to belong to the caller's tenant. An attacker can create a task with `agent_id` set to the ID of any agent in any other tenant, then resolve the task to dispatch `Run Compliance Scan` instructions to that foreign agent.

**Fix:** Before inserting into `agent_instructions`, verify the agent belongs to the task's tenant:
```python
if agent_id:
    agent_doc = await db.agents.find_one(
        {"id": agent_id, "tenantId": task.get("tenantId", "")}
    )
    if not agent_doc:
        return {"dispatched": False, "reason": "Agent not found in tenant"}
```

---

### CR-03: `dispatch_rescan` inserts `agent_instructions` without `tenantId`

**File:** `backend/compliance_remediation_service.py:138-148`

**Issue:** The instruction document inserted at line 148 does not include a `tenantId` field. The polling query in `agent_tasks_endpoints.py:33-38` filters `agent_instructions` by `{"tenantId": tenant_id, ...}`. Any compliance-rescan instruction inserted by `dispatch_rescan` will never be returned to the polling agent because the `tenantId` field is missing. The rescan is silently lost.

**Fix:** Add `tenantId` to the instruction document:
```python
instruction = {
    "agent_id": agent_id,
    "tenantId": task.get("tenantId", ""),   # ← add this
    "instruction": "Run Compliance Scan",
    "status": "pending",
    "created_at": _now(),
    "created_by": created_by,
    "priority": "high",
    "control_id": task.get("control_id", ""),
    "remediation_task_id": task.get("id", ""),
}
```

---

### CR-04: Hooks called after conditional early return — violates React Rules of Hooks

**File:** `components/RemediationTaskModal.tsx:25-53`

**Issue:** The component unconditionally returns `null` on line 25 when `isOpen` is `false`, and then declares eight `useState` calls and one `useEffect` on lines 27–53. React requires that hooks are called in the same order on every render. Placing hooks after an early-return guard means they are skipped whenever `isOpen` is `false`, and React will throw an invariant error (`Rendered fewer hooks than expected`) at runtime when the modal transitions from open to closed (or vice versa), crashing the component tree.

**Fix:** Move all hook declarations above the early-return guard, or gate rendering at the call site (preferred):
```tsx
// Option A — move early return AFTER all hooks
const [title, setTitle] = useState('');
// ... all other hooks ...
useEffect(() => { ... }, [task, isOpen]);

if (!isOpen) return null;   // ← AFTER hooks

// Option B (preferred) — gate in RemediationDashboard.tsx
{(isCreating || !!editingTask) && (
    <RemediationTaskModal ... />
)}
// and remove the guard from inside the component
```

---

## Warnings

### WR-01: `_tenant_filter` returns empty dict `{}` for users missing `tenantId`

**File:** `backend/compliance_remediation_endpoints.py:33-37`

**Issue:** If a non-super-admin user has neither `tenantId` nor `tenant_id` populated (e.g., a broken JWT, a legacy account, or a seeding error), `_tenant_filter` returns `{}`. An empty filter applied to any query removes all tenant scoping, effectively granting that user access to all tenants' tasks. This is the same pattern that should have been hardened.

**Fix:** Fail closed instead of open when the tenant is absent:
```python
def _tenant_filter(user: dict) -> dict:
    if user.get("role") in _SUPER_ADMIN_ROLES:
        return {}
    tenant = user.get("tenantId") or user.get("tenant_id") or ""
    if not tenant:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return {"tenantId": tenant}
```

---

### WR-02: `status` and `priority` fields accept arbitrary strings — no enum validation

**File:** `backend/compliance_remediation_endpoints.py:52, 56`

**Issue:** `TaskCreate.priority` and `TaskUpdate.status` are plain `str` fields with no `Literal` or validator constraint. A client can set `status="hacked"` or `priority="∞"`, which will be persisted to the DB and potentially break downstream logic that pattern-matches on status strings (e.g., the `$in: ["open", "in_progress"]` query in `agent_tasks_endpoints.py:100`, and the frontend `STATUS_COLORS` lookup).

**Fix:**
```python
from typing import Literal

class TaskCreate(BaseModel):
    priority: Literal["low", "medium", "high", "critical"] = "medium"

class TaskUpdate(BaseModel):
    status: Optional[Literal["open", "in_progress", "resolved", "dismissed"]] = None
```

---

### WR-03: Asset lookup in `create_task` and `dispatch_rescan` is not tenant-scoped

**File:** `backend/compliance_remediation_service.py:38-41, 129-132`

**Issue:** Both `db.assets.find_one({"id": asset_id})` calls look up assets by `id` alone, without constraining by `tenantId`. An attacker who knows (or guesses) an `asset_id` belonging to a different tenant can cause the service to resolve and store that tenant's agent ID in a task they own, and subsequently dispatch instructions to that foreign agent when the task is resolved.

**Fix:**
```python
tenant_id = tenant_filter.get("tenantId", "")
asset_doc = await db.assets.find_one({"id": asset_id, "tenantId": tenant_id})
```
For `dispatch_rescan`, use `task.get("tenantId", "")` as the scoping value.

---

### WR-04: `handleMarkResolved` in `RemediationDashboard` has no error feedback to the user

**File:** `components/RemediationDashboard.tsx:55-62`

**Issue:** When `updateRemediationTask` throws, the error is only logged to the console. The UI silently appears unchanged (status badge stays non-resolved, no toast, no inline error). A user who clicks "Mark Resolved" on a network partition or 404 has no indication the action failed and may re-attempt, causing confusion or duplicate requests.

**Fix:** Add a toast or inline error state:
```tsx
const [error, setError] = useState<string | null>(null);

const handleMarkResolved = async (task: RemediationTask) => {
    try {
        await api.updateRemediationTask(task.id, { status: 'resolved' });
        fetchTasks();
    } catch (e) {
        console.error('Failed to resolve task:', e);
        setError('Failed to mark task as resolved. Please try again.');
    }
};
```

---

## Info

### IN-01: `suggest_remediation` in `ai_service.py` does not call `_check_policy` before building the prompt

**File:** `backend/ai_service.py:431-435`

**Issue:** `suggest_remediation` calls `generate_text` which calls `guardrail_service.scan_and_log` on the assembled prompt. However, the prompt is assembled from user-controlled database fields (`control_description` = task description, set by the creating user). While `generate_text` does scan the composed prompt via `guardrail_service`, the higher-level `_check_policy` that also applies the per-tenant `block_injection` policy is not called. This is inconsistent with `analyze_impact` (line 314) and `chat` (line 376) which both call `_check_policy` explicitly. The gap could allow prompt injection content to bypass the tenant-specific injection block policy if `guardrail_service` and `_check_policy` scan with different rule sets.

**Fix:** Add a policy check before assembling the prompt:
```python
async def suggest_remediation(self, control_id, control_description, failure_reason, asset_context):
    combined = f"{control_description}\n{failure_reason}"
    check = await self._check_policy(combined)
    if not check.passed:
        return f"BLOCKED: {', '.join(check.findings)}"
    prompt = (...)
    return await self.generate_text(prompt, source="remediation_suggestion")
```

---

### IN-02: `assignee_type` field collected in UI but never sent to the backend

**File:** `components/RemediationTaskModal.tsx:30, 77-90`

**Issue:** The component collects an `assigneeType` ('agent' | 'user') in state (line 30) and presents a dropdown to the user (line 180-188), but the `handleSave` call for both create and update paths never includes `assignee_type` in the payload (lines 77-100). The field is UI-only dead state. This means the backend has no way to distinguish agent assignees from user assignees, and any downstream logic that would rely on this distinction (e.g., routing notifications) cannot function.

**Fix:** Include `assignee_type` in the create and update payloads:
```tsx
await api.createRemediationTask({
    ...
    assignee_type: assigneeType,
    ...
});
// and in the update path:
await api.updateRemediationTask(task.id, {
    description,
    assignee,
    assignee_type: assigneeType,
    due_date: dueDate || undefined,
});
```

---

_Reviewed: 2026-06-18_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
