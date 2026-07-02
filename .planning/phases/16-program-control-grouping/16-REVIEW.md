---
phase: 16-program-control-grouping
reviewed: 2026-07-02T08:31:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - backend/program_service.py
  - backend/program_endpoints.py
  - backend/tests/test_program_service.py
  - backend/router_registry.py
  - components/ProgramsDashboard.tsx
findings:
  critical: 7
  warning: 6
  info: 3
  total: 16
status: issues_found
---

# Phase 16: Code Review Report

**Reviewed:** 2026-07-02T08:31:00Z
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Reviewed against `.planning/phases/16-program-control-grouping/16-01-PLAN.md`'s must-haves. `router_registry.py` correctly registers `program_endpoints`, and `DELETE /api/programs/{id}` correctly touches only the `programs` collection (control_evidence/compliance data is untouched, as required). However, the phase has severe, provable defects that were verified by actually executing the code, not just reading it:

- The unit test suite (`backend/tests/test_program_service.py`) **cannot even be collected** by pytest due to a wrong import, and after fixing that import, **all 7 tests still fail** because the RBAC dependency-override pattern used is fundamentally broken. I confirmed both failures by running pytest directly (see CR-01/CR-02/CR-03). The plan's must-have "All 7 unit tests in test_program_service.py pass green" is not met — 0 of 7 pass as committed.
- `POST /api/programs` and `PUT /api/programs/{id}/controls` both return raw Mongo documents that still carry a non-JSON-serializable `ObjectId` `_id` field, which I reproduced with `mongomock`/`fastapi.encoders.jsonable_encoder` — both endpoints will 500 on any real (or mongomock) database, not just in theory.
- `ProgramsDashboard.tsx` reports "success" toasts for create/delete regardless of the actual HTTP response status, and the "Manage Controls" feature (an explicit plan deliverable) sets state that no UI ever consumes — there is no modal, and no PUT request to `/api/programs/{id}/controls` anywhere in the file.

These are all "must ship broken" issues, not style nitpicks — they were reproduced, not assumed.

## Critical Issues

### CR-01: Test module fails to import — `TestClient` is not exported by `fastapi`

**File:** `backend/tests/test_program_service.py:4`
**Issue:** `from fastapi import FastAPI, TestClient` fails with `ImportError: cannot import name 'TestClient' from 'fastapi'` on the installed fastapi version (0.138.0). I ran `python3 -m pytest backend/tests/test_program_service.py -v` and confirmed: pytest cannot even collect the module — 0 of the 7 required tests run. Every other test file in `backend/tests/` correctly imports `from fastapi.testclient import TestClient` (e.g. `test_compliance_score.py`, `test_rbac.py`, `test_privacy_service.py`) — this file diverges from the established, working convention.
**Fix:**
```python
from fastapi import FastAPI
from fastapi.testclient import TestClient
```

### CR-02: RBAC dependency override never applies — every test request gets 401/500, none exercise real logic

**File:** `backend/tests/test_program_service.py:19-27`
**Issue:** `rbac_service.has_permission(...)` (see `backend/rbac_service.py:115-129`) is a **factory** that returns a brand-new `dependency` closure on every call. `program_endpoints.py` calls it once at import time to build each route's `Depends(...)`. The test's `_build()` helper calls `rbac_service.has_permission("manage:settings")` **again**, producing a *different* function object, and registers the override against that new object:
```python
app.dependency_overrides[rbac_service.has_permission("manage:settings")] = lambda: t
```
FastAPI matches overrides by the exact callable used in the route's `Depends(...)`; since the override key is a different object than the one baked into the router, the override never takes effect and the real dependency chain runs. I verified this by fixing only CR-01 and re-running the suite: every request returns `401 Unauthorized` because `get_current_user` (the real one) executes with no auth header. Even swapping to the codebase's established, correct pattern — `app.dependency_overrides[get_current_user] = lambda: t` (used in `test_compliance_score.py`, `test_rbac.py`) — still fails: it hits `rbac_service.get_user_permissions()`, which calls the real, un-mocked `get_database()` for any role other than `super_admin`, raising `RuntimeError: Database not connected` → every request 500s. I reproduced both failure modes directly with pytest.
**Fix:** Override the stable `get_current_user` singleton (not a freshly-constructed `has_permission(...)` closure) and use `role="super_admin"` for the mock user so `rbac_service.get_user_permissions` short-circuits before touching the database, e.g.:
```python
from authentication_service import get_current_user
...
def _mkuser(t="tenant-a", r="super_admin"): ...
app.dependency_overrides[get_current_user] = lambda: t
```

### CR-03: Required status-rollup tests are missing; existing tests assert nothing about behavior

**File:** `backend/tests/test_program_service.py:29-56`
**Issue:** The plan's TDD spec (`16-01-PLAN.md`) requires exactly these 7 tests: `test_create_program`, `test_add_controls_to_program`, `test_remove_controls_from_program`, `test_status_rollup_compliant`, `test_status_rollup_at_risk`, `test_list_programs_includes_rollup`, `test_tenant_isolation`. The committed file instead has `test_create_program`, `test_list_programs`, `test_get_program`, `test_add_controls`, `test_remove_controls`, `test_delete_program`, `test_tenant_isolation` — **`test_status_rollup_compliant` and `test_status_rollup_at_risk` do not exist at all**, so the single most important piece of business logic in this phase (the compliant/at_risk/in_progress classification thresholds in `_compute_status_rollup`) is completely untested. Additionally, the assertions that do exist are tautological and pass regardless of correctness, e.g. `assert r.status_code in (200, 400)` and `assert r.status_code in (200, 404)` — these accept both success *and* failure as a passing test, and none of the tests inspect the response body (e.g. verifying `status_rollup.status == "compliant"` or that `control_ids` actually changed). Combined with CR-01/CR-02, this suite provides zero real signal about correctness.
**Fix:** Add real tests for the rollup thresholds with concrete mocked `asset_compliance` data (e.g. 5 controls, 4 `Compliant` + 0 failing → `status == "compliant"`; 1 `Non-Compliant` → `status == "at_risk"`), and replace the `in (200, 400)`/`in (200, 404)` patterns with a single expected status code plus body assertions.

### CR-04: `POST /api/programs` returns a document with a raw, non-serializable Mongo `ObjectId`

**File:** `backend/program_service.py:11-19`
**Issue:** `db._db.programs.insert_one(doc)` mutates `doc` **in place**, adding an `_id: ObjectId(...)` key — this is documented pymongo/motor behavior. `create_program` then returns this same mutated `doc`, and `program_endpoints.create_program` wraps it directly in `{"program": doc}` with no `response_model` and no `_id` stripping. I reproduced this with `mongomock`:
```
doc after insert_one: {'id': 'prog-1', 'name': 'Test', '_id': ObjectId('...')}
jsonable_encoder ERROR: ValueError: [TypeError("'ObjectId' object is not iterable"), ...]
```
FastAPI calls `jsonable_encoder` on the return value before serializing the response, so **every real `POST /api/programs` call raises and 500s** — this is masked in the test suite only because the mock `insert_one` is an `AsyncMock` that does not replicate pymongo's mutate-and-inject-`_id` behavior. Note `get_program`/`list_programs` correctly avoid this by projecting `{"_id": 0}` (lines 23, 32) — `create_program` does not.
**Fix:**
```python
async def create_program(db, tenant_id: str, data: dict) -> dict:
    doc = {...}
    await db._db.programs.insert_one(doc)
    doc.pop("_id", None)
    return doc
```

### CR-05: `PUT /api/programs/{id}/controls` returns a document with a raw, non-serializable Mongo `ObjectId`

**File:** `backend/program_service.py:39-53`
**Issue:** `update_controls`'s `find_one` call at line 40 has no projection (`{"_id": 0}`), unlike the equivalent calls in `get_program` (line 23) and `list_programs` (line 32). The returned `doc` therefore retains its raw `_id: ObjectId`, and this document is returned directly through `program_endpoints.update_program_controls` with no stripping — same `jsonable_encoder` crash as CR-04, confirmed the same way. Every real `PUT /api/programs/{id}/controls` call will 500.
**Fix:**
```python
doc = await db._db.programs.find_one({"id": program_id, "tenantId": tenant_id}, {"_id": 0})
```

### CR-06: Frontend reports false "success" for create/delete regardless of actual HTTP outcome

**File:** `components/ProgramsDashboard.tsx:23-33`
**Issue:** `submit()` and `del()` never check `response.ok`/`response.status` before declaring success:
```javascript
const submit = async () => {
  try {
    await (await authFetch('/api/programs', { method: 'POST', ... })).json();
    showToast('Program created', 'success'); setShowForm(false); setForm({}); fetch();
  } catch { showToast('Failed', 'error'); }
};
const del = async (id: string) => {
  try { await authFetch(`/api/programs/${id}`, { method: 'DELETE' }); showToast('Deleted', 'success'); fetch(); }
  catch { showToast('Delete failed', 'error'); }
};
```
`authFetch` (`services/apiService.ts:198`) returns the raw `Response` for any status code — it does not throw on 4xx/5xx. Given CR-04, a real `POST /api/programs` call currently 500s with a JSON error body, so `.json()` resolves successfully (no exception), and the `catch` block never fires: the user sees "Program created" even though nothing was created and the form is silently dismissed. The same applies to `del()` for e.g. a 403/404 delete failure — the UI reports "Deleted" unconditionally.
**Fix:**
```javascript
const submit = async () => {
  try {
    const res = await authFetch('/api/programs', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(form) });
    if (!res.ok) throw new Error(await res.text());
    showToast('Program created', 'success'); setShowForm(false); setForm({}); fetch();
  } catch { showToast('Failed', 'error'); }
};
const del = async (id: string) => {
  try {
    const res = await authFetch(`/api/programs/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(await res.text());
    showToast('Deleted', 'success'); fetch();
  } catch { showToast('Delete failed', 'error'); }
};
```

### CR-07: "Manage Controls" feature is entirely non-functional — no modal, no PUT call

**File:** `components/ProgramsDashboard.tsx:12, 76`
**Issue:** The plan explicitly requires: `"Manage Controls" button → modal with control picker (search + select)`, and the must-have "ProgramsDashboard.tsx renders program list with ... create/edit/delete actions". The component declares `editing` state and a "Controls" button that calls `setEditing(p.id)` (line 76), but **no JSX anywhere in the file reads `editing`** to render a modal, and there is no `authFetch` call to `PUT /api/programs/{id}/controls` anywhere in the component. Clicking "Controls" silently does nothing visible — the entire control-membership-management UI required by the plan is missing, not just buggy.
**Fix:** Implement the control picker modal (rendered when `editing` is set) that calls `PUT /api/programs/${editing}/controls` with `{add, remove}`, e.g. add a conditional block:
```jsx
{editing && (
  <ControlPickerModal
    programId={editing}
    onClose={() => setEditing(null)}
    onSave={async (add, remove) => {
      const res = await authFetch(`/api/programs/${editing}/controls`, {
        method: 'PUT', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ add, remove }),
      });
      if (!res.ok) { showToast('Update failed', 'error'); return; }
      setEditing(null); fetch();
    }}
  />
)}
```

## Warnings

### WR-01: `_compute_status_rollup` silently ignores its own `tenant_id` parameter for the `asset_compliance` query

**File:** `backend/program_service.py:61-67`
**Issue:** `programs` access consistently bypasses tenant isolation and filters manually (`db._db.programs.find_one({..., "tenantId": tenant_id})`), which is correct given `db._db` returns the raw, unwrapped Motor collection (`TenantIsolatedDatabase._db` is set directly in `__init__`, bypassing `__getattr__`). But `_compute_status_rollup` queries `db.asset_compliance` (no `._db`), which goes through `TenantIsolatedDatabase.__getattr__` → `TenantIsolatedCollection`, whose `find()` **overwrites** whatever `"tenantId"` key is in the filter with `get_tenant_id()` from the `tenant_context` contextvar (`tenant_context.py`, `database.py:106-136`). The explicit `tenant_id` argument passed into `_compute_status_rollup` is therefore dead for this query — it happens to match today only because both values ultimately derive from the same per-request contextvar. If this function is ever called from a background job or any code path where the contextvar isn't set to the same tenant as the explicit parameter, the query will use the wrong (or fail-closed empty) tenant filter instead of the one the caller explicitly requested.
**Fix:** Use the same raw-access pattern as the rest of the file for consistency and to make the explicit `tenant_id` argument actually load-bearing:
```python
results = await db._db.asset_compliance.find(
    {"controlId": {"$in": control_ids}, "tenantId": tenant_id},
    {"_id": 0, "status": 1, "controlId": 1},
).to_list(length=1000)
```

### WR-02: Status rollup ignores "latest" semantics and silently drops results

**File:** `backend/program_service.py:64-81`
**Issue:** The plan requires "look up **latest** compliance check result" per control. The query has no `.sort()`, and `_compute_status_rollup` dedupes by keeping only the *first* document encountered per `controlId` in unspecified cursor order (`if cid in seen: continue`). If a control has been assessed against multiple assets (a very plausible schema given `assetId`+`controlId` compound records elsewhere, e.g. `compliance_auto_evidence_service.py`), all but one arbitrarily-chosen asset's result is silently discarded, and which one "wins" is non-deterministic (Mongo does not guarantee stable order without an index-backed sort). Two consecutive requests against unchanged data could theoretically report different rollup statuses.
**Fix:** Either aggregate per-control across all matching results deterministically (e.g. "failing" if any linked asset is failing) or sort by an update timestamp and keep the true latest result per control.

### WR-03: No schema/type validation on program-mutation request bodies

**File:** `backend/program_endpoints.py:16, 41`; `backend/program_service.py:44-47`
**Issue:** CLAUDE.md mandates "Validate input at system boundaries," but both `create_program` and `update_program_controls` accept a raw `dict = Body(...)` with no Pydantic schema. `create_program` only checks that `name` is truthy — `control_ids`, `framework_id`, etc. are unchecked. Worse, `update_program_controls` passes `payload.get("add", [])`/`payload.get("remove", [])` straight into `update_controls`, where `current.update(add)` (`program_service.py:44-47`) will silently iterate a string's characters as individual "control ids" if the caller sends `"add": "CC6.2"` instead of `"add": ["CC6.2"]` — corrupting `control_ids` without any error. A non-list `control_ids` also breaks `_compute_status_rollup`'s `{"controlId": {"$in": control_ids}}` query (Mongo's `$in` requires an array).
**Fix:** Use Pydantic request models, e.g. `class ProgramCreate(BaseModel): name: str; description: str = ""; framework_id: str = ""; owner: str = ""; control_ids: list[str] = []` and `class ControlsUpdate(BaseModel): add: list[str] = []; remove: list[str] = []`.

### WR-04: `Pending_Evidence` status is counted as "failing", inflating false "at_risk" signals

**File:** `backend/program_service.py:78`
**Issue:** `elif r.get("status") in ("Non-Compliant", "Pending_Evidence"): failing += 1` — a control whose evidence simply hasn't been reviewed yet (`Pending_Evidence`, per `compliance_status_endpoints.py:24`) is treated identically to an actual compliance failure. Since `at_risk` triggers whenever `failing > 0`, a program where every control is merely awaiting evidence review (not actually failing anything) will show a red "At Risk" badge, which is misleading to the end user relative to what "at risk" should mean.
**Fix:** Count `Pending_Evidence` toward `not_assessed` (or a new `pending` bucket) rather than `failing`, unless product intent genuinely wants pending evidence treated as a compliance risk — if so, document that decision explicitly.

### WR-05: Local `fetch` callback shadows the global `window.fetch`

**File:** `components/ProgramsDashboard.tsx:14`
**Issue:** `const fetch = useCallback(async () => {...`, [])` shadows the built-in global `fetch`. Nothing inside the component currently calls the real `fetch()`, so there's no active bug today, but this is a well-known footgun: any future edit inside this component that tries to call the global `fetch` (e.g. copy-pasted code from elsewhere) will silently call this local no-argument refresh function instead, with no type error to catch the mistake.
**Fix:** Rename to `loadPrograms` or `refresh`.

### WR-06: No confirmation before destructive delete

**File:** `components/ProgramsDashboard.tsx:30-33, 77`
**Issue:** Clicking "Delete" immediately calls `DELETE /api/programs/{id}` with no confirmation step — a single misclick permanently removes a program (the program document itself, not its evidence, but still an unrecoverable action from the UI's perspective).
**Fix:** Add a confirm step, e.g. `if (!window.confirm('Delete this program?')) return;` at the top of `del()`, or a proper confirmation modal consistent with other destructive actions in the codebase.

## Info

### IN-01: Plan documentation names the wrong collection

**File:** `.planning/phases/16-program-control-grouping/16-01-PLAN.md:57` (reference only)
**Issue:** The plan describes the rollup as reading from a `compliance_results` collection, but the implementation (correctly, matching the rest of the codebase's convention for control-level status) reads from `asset_compliance`. `compliance_results` is a different, unrelated collection used by `kpi_endpoints.py`/`analytics_service.py`. Not a code defect, but worth reconciling the plan text so future readers aren't misled.
**Fix:** Update the plan doc's status-rollup section to reference `asset_compliance`.

### IN-02: Loose `any` typing throughout the dashboard component

**File:** `components/ProgramsDashboard.tsx:8, 11`
**Issue:** `useState<any[]>([])` and `useState<any>({})` provide no compile-time safety for the `Program`/form shapes despite this being a TypeScript file with a well-defined backend document schema (see plan's "Program document schema").
**Fix:** Define `interface Program { id: string; name: string; ... ; status_rollup?: {...} }` and use it in place of `any`.

### IN-03: Unexplained magic number result caps

**File:** `backend/program_service.py:32, 67`
**Issue:** `to_list(length=100)` (list_programs) and `to_list(length=1000)` (status rollup lookup) are unexplained hardcoded caps with no named constant or comment on why those specific values were chosen; large tenants could silently have programs/controls dropped from the response with no indication to the caller.
**Fix:** Extract to named constants (e.g. `_MAX_PROGRAMS = 100`) or paginate properly.

---

_Reviewed: 2026-07-02T08:31:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
