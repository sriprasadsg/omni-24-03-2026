---
phase: 06-asset-compliance-status-ui-fix
reviewed: 2026-06-21T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - backend/compliance_status_endpoints.py
  - backend/router_registry.py
  - backend/tests/test_compliance_status.py
  - components/AssetComplianceList.tsx
  - components/FrameworkDetail.tsx
  - services/apiService.ts
findings:
  critical: 2
  warning: 4
  info: 2
  total: 8
status: issues_found
---

# Phase 06: Code Review Report

**Reviewed:** 2026-06-21T00:00:00Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

This phase adds a PATCH endpoint for asset compliance status overrides, wires the frontend `onUpdateStatus` callback to that real API call, and registers the new router. The core logic is sound and the tenant-isolation guard on the happy path is correctly structured. However, two security-class defects were found: a privilege-escalation path that allows super-admin callers to write compliance records into any tenant's namespace without restriction, and an evidence-key collision in the React component that can cause the wrong evidence item to be deleted. Four quality/robustness warnings round out the report.

---

## Critical Issues

### CR-01: Super-admin bypass silently skips `tenantId` guard, allowing cross-tenant writes

**File:** `backend/compliance_status_endpoints.py:46-60`

**Issue:** The tenant-isolation check is skipped entirely for super-admin callers (`user_role not in _SUPER_ROLES`). The subsequent `find_one` and `update_one` operations then use `tenant_id`, which is derived from `getattr(current_user, "tenant_id", None) or ""`. For a super-admin whose JWT carries no `tenant_id` (a common pattern for platform admins), `tenant_id` collapses to the empty string `""`. The `upsert=True` `update_one` will then create a new compliance record with `tenantId: ""`, silently mixing it out of every tenant's namespace. More critically, a super-admin who supplies a `tenant_id` in their token for tenant A can update compliance records for any asset ID regardless of which tenant actually owns that asset — there is no ownership check at all for privileged callers.

```python
# Current — super-admin path uses caller's tenant_id with no ownership check
if user_role not in _SUPER_ROLES:
    asset = await db.assets.find_one({"id": asset_id, "tenantId": tenant_id})
    if not asset:
        raise HTTPException(status_code=403, detail="Asset not found in your tenant")

# Also: if super-admin has no tenant_id, tenant_id == "" and upsert pollutes the "" bucket
```

**Fix:** Always resolve the asset's real `tenantId` from the database before writing. For super-admins, look up the asset without a tenant filter, then extract its `tenantId` to scope all writes:

```python
# Resolve asset regardless of caller role; use its tenantId for all writes
asset = await db.assets.find_one({"id": asset_id})
if not asset:
    raise HTTPException(status_code=404, detail="Asset not found")

# Enforce tenant isolation for non-super-admins
resolved_tenant_id = asset.get("tenantId", "")
if user_role not in _SUPER_ROLES and resolved_tenant_id != tenant_id:
    raise HTTPException(status_code=403, detail="Asset not found in your tenant")

# Use resolved_tenant_id (not caller's tenant_id) for all subsequent DB operations
doc = await db.asset_compliance.find_one(
    {"assetId": asset_id, "controlId": body.control_id, "tenantId": resolved_tenant_id}
)
```

---

### CR-02: Evidence key collision causes incorrect item deletion

**File:** `components/AssetComplianceList.tsx:114`

**Issue:** The evidence item key and delete target are both computed as `ev.id || ev.evidence_id || String(idx)`. When evidence objects lack an `id` and `evidence_id` field, the fallback is the array index. If two different evidence items both fall back to `String(idx)`, React's reconciliation keying and `deletingMap[evId]` will both point to the wrong item. More concretely: the outer `div` key is `${evId}-${idx}` (line 116) which uses the same potentially-colliding `evId`, and the `handleDeleteEvidence` call passes `evId` to the API. If the first evidence item happens to get `evId = "0"` (from `String(0)`) and the user deletes the second item which also computes `evId = "1"`, the correct item is deleted — but if the backend also stores evidence without stable IDs, a re-fetch after deletion could change indices and make `deletingMap` apply the loading spinner to the wrong row next time.

The real bug: `handleDeleteEvidence(asset.id, evId)` at line 148 passes `evId` to `api.deleteComplianceEvidence`. If `evId` is an index string like `"0"`, the API call sends `DELETE /api/assets/{assetId}/compliance/evidence/0`, which is not a valid evidence document ID. The delete will silently fail or hit a wrong record on the backend.

**Fix:** Require a stable ID and refuse to render the delete button if none is present:

```tsx
const evId = ev.id || ev.evidence_id;
if (!evId) {
    // Automated evidence without a stable ID — skip delete button (already handled by isAutomated guard)
}
// Use evId as the React key; idx is only a last-resort display aid
return (
  <div key={evId ?? `idx-${idx}`} className="flex items-start gap-2">
    ...
    {!isAutomated && evId && (
      <button onClick={() => handleDeleteEvidence(asset.id, evId)} ...>
```

On the backend, validate that `evidenceId` is a non-empty, non-numeric string before executing the delete.

---

## Warnings

### WR-01: `onUpdateStatus` prop type is synchronous but caller is `async` — errors are silently swallowed by the component

**File:** `components/AssetComplianceList.tsx:11` / `components/FrameworkDetail.tsx:770-778`

**Issue:** `AssetComplianceListProps` declares `onUpdateStatus` as `(assetId: string, status: AssetCompliance['status']) => void` (line 11, synchronous). The actual callback in `FrameworkDetail.tsx` is an `async` function that `await`s two API calls. TypeScript allows returning a `Promise<void>` where `void` is expected, so no compile error is raised — but the component's `onClick` handler at line 187-188 calls `onUpdateStatus(asset.id, 'Compliant')` without `await`, meaning any rejection from the async callback is a floating unhandled promise rejection. The error toast in `FrameworkDetail` line 776 does fire (inside the async body), but the component itself has no way to set a loading state or disable the button during the in-flight request.

**Fix:** Change the prop type to return `Promise<void>`:

```tsx
onUpdateStatus: (assetId: string, status: AssetCompliance['status']) => Promise<void>;
```

Then add loading state in `AssetComplianceList` and `await` the call:

```tsx
const [updatingMap, setUpdatingMap] = useState<Record<string, boolean>>({});

const handleUpdateStatus = async (assetId: string, status: AssetCompliance['status']) => {
    setUpdatingMap(prev => ({ ...prev, [assetId]: true }));
    try {
        await onUpdateStatus(assetId, status);
    } finally {
        setUpdatingMap(prev => ({ ...prev, [assetId]: false }));
    }
};
```

---

### WR-02: `router_registry.py` silently swallows load failures — broken router is invisible at startup

**File:** `backend/router_registry.py:23-28`

**Issue:** `_load()` catches all exceptions and logs at `ERROR` level, but continues. If `compliance_status_endpoints` fails to import (e.g., a syntax error, a missing `auth_types` import after refactor), the PATCH endpoint is simply absent at runtime. The application starts successfully, every request to the status endpoint returns 404, and the only signal is a log line that may go unnoticed. This is especially risky because `compliance_status_endpoints` is a new file that could be broken by future refactors.

**Fix:** At minimum, collect load failures and log a startup summary. Optionally, promote the compliance-critical routers to the "fail-fast" category that raises rather than swallows:

```python
_REQUIRED_ROUTERS = {
    "compliance_status_endpoints",
    # add others that must be present for the app to be usable
}

def _load(app, module_name, attr="router", **kwargs):
    try:
        mod = importlib.import_module(module_name)
        app.include_router(getattr(mod, attr), **kwargs)
    except Exception as exc:
        logger.error("[Router] Failed to load %s: %s", module_name, exc)
        if module_name in _REQUIRED_ROUTERS:
            raise  # fail startup rather than serve a broken app
```

---

### WR-03: Test 3 uses bare `pytest.raises(Exception)` — masks incorrect error type

**File:** `backend/tests/test_compliance_status.py:120`

**Issue:** `test_patch_compliance_status_invalid_status_422` asserts that constructing a `ComplianceStatusUpdate` with an invalid status raises "any exception". Pydantic v2 raises `pydantic.ValidationError` specifically. Using `pytest.raises(Exception)` means the test would also pass if the code raised `TypeError`, `AttributeError`, or any other unrelated error, falsely certifying that status validation works.

**Fix:**

```python
from pydantic import ValidationError

def test_patch_compliance_status_invalid_status_422():
    from compliance_status_endpoints import ComplianceStatusUpdate
    with pytest.raises(ValidationError):
        ComplianceStatusUpdate(control_id="c1", status="invalid")
```

---

### WR-04: `FrameworkDetail.tsx` exceeds the 500-line limit mandated by `CLAUDE.md`

**File:** `components/FrameworkDetail.tsx:1-854`

**Issue:** The file is 854 lines, nearly double the 500-line ceiling set in `CLAUDE.md`. The `ControlEvidenceUploadModal`, `AddControlModal`, `ReportsModal`, and `FrameworkDetail` itself are all defined in the same file. This is a project-rule violation and a practical maintainability concern.

**Fix:** Extract the three modal components (`ControlEvidenceUploadModal`, `AddControlModal`, `ReportsModal`) into separate files under `components/`. Each is self-contained and has no circular dependency on `FrameworkDetail`.

---

## Info

### IN-01: `console.log` debug artifact left in production path

**File:** `components/FrameworkDetail.tsx:793`

**Issue:** `console.log(`Ingesting evidence for asset ${assetId}: ${fileName}`)` is an unconditional debug log in the `onIngestEvidence` callback. CLAUDE.md style and general production hygiene call for its removal.

**Fix:** Remove the line or replace with a conditional `if (import.meta.env.DEV)` guard.

---

### IN-02: `@ts-ignore` suppresses a type error on `api.triggerFrameworkScan`

**File:** `components/FrameworkDetail.tsx:435`

**Issue:** `// @ts-ignore` above the `triggerFrameworkScan` call indicates the function is either not exported from `apiService.ts` or has an incompatible signature. Suppressing the error hides a real gap — if the function does not exist at runtime the call will throw a `TypeError` that no error boundary catches.

**Fix:** Either export `triggerFrameworkScan` from `apiService.ts` with the correct signature, or remove the call if the feature is not yet implemented. Do not leave `@ts-ignore` suppressing a missing-export error.

---

_Reviewed: 2026-06-21T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
