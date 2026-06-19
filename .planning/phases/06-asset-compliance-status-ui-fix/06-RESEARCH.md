# Phase 6 Research: Asset Compliance Status + UI Fix

**Researched:** 2026-06-20
**Domain:** FastAPI PATCH endpoint + React state update + WCAG badge fix
**Confidence:** HIGH

---

## Current State

### onUpdateStatus Call Site

In `components/AssetComplianceList.tsx` (lines 187–188), the two action buttons fire:

```tsx
// Line 187 — Mark Compliant button
<button onClick={() => onUpdateStatus(asset.id, 'Compliant')} ...>

// Line 188 — Mark Non-Compliant button
<button onClick={() => onUpdateStatus(asset.id, 'Non-Compliant')} ...>
```

The prop signature (line 11):
```ts
onUpdateStatus: (assetId: string, status: AssetCompliance['status']) => void;
```

`AssetCompliance['status']` resolves to `'Compliant' | 'Non-Compliant' | 'Pending_Evidence'` (see `types.ts` line 466).

The callback is synchronous (`void` return, not `Promise<void>`). The component does not handle loading state, error toast, or optimistic rollback around this call — that logic must be added or handled by the parent.

### Parent Component Wiring

`components/FrameworkDetail.tsx` (line 766–770) is the only consumer:

```tsx
<AssetComplianceList
  control={control}
  assets={assets}
  complianceData={assetComplianceData}
  onUpdateStatus={(assetId, status) => console.log('Update status', assetId, status)}
  ...
/>
```

The callback is currently a `console.log` no-op. It is **not** wired to any API call or state update.

`FrameworkDetail` already manages local compliance state through a `useState` initialized from `initialAssetComplianceData` prop (line 383: `const [localAssetCompliance, setLocalAssetCompliance] = useState(initialAssetComplianceData)`). It has a `refreshAssetCompliance(assetId)` helper (lines 386–395) that calls `api.fetchAssetCompliance(assetId)` and patches `localAssetCompliance` — this same helper is called after evidence upload/delete. The status-update flow should use the same pattern.

---

## Backend Patterns

### Compliance Endpoint Patterns

All existing compliance evidence endpoints are defined in `backend/compliance_evidence_endpoints.py` and **do not use** a router prefix — routes are spelled out explicitly (e.g., `/api/assets/{asset_id}/compliance/evidence`). The router is loaded into the app via `backend/compliance_endpoints.py`, which is registered in `router_registry.py` at line 108 as:

```python
_load(app, "compliance_endpoints", "router")
```

The new PATCH endpoint should be added to `compliance_evidence_endpoints.py` to keep all asset-compliance mutations in one file.

Auth injection pattern used in that file:

```python
from authentication_service import get_current_user

@router.post("/api/assets/{asset_id}/compliance/evidence")
async def upload_compliance_evidence(
    ...
    current_user=Depends(get_current_user),
):
    user_role = getattr(current_user, "role", "")
    tenant_id = getattr(current_user, "tenant_id", None) or ""
```

`get_current_user` returns a `TokenData` instance with `.role`, `.tenant_id`, and `.username` attributes.

Tenant gate for non-admins (the asset-lookup guard pattern, lines 51–55):

```python
if user_role not in _SUPER_ROLES:
    db = get_database()
    asset = await db.assets.find_one({"id": asset_id, "tenantId": tenant_id})
    if not asset:
        raise HTTPException(status_code=403, detail="Asset not found in your tenant")
```

`_SUPER_ROLES` is a module-level frozenset defined at line 18:
```python
_SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}
```

### PATCH Pattern from Remediation

`backend/compliance_remediation_endpoints.py` shows the canonical PATCH pattern:

```python
class TaskUpdate(BaseModel):
    status: Optional[Literal["open", "in_progress", "resolved"]] = None
    ...

@router.patch("/tasks/{task_id}")
async def update_task(
    task_id: str,
    body: TaskUpdate,
    current_user: dict = Depends(get_current_user),
):
    tf = _tenant_filter(current_user)
    result = await svc.update_task(
        get_database(), task_id, body.model_dump(exclude_none=True), tf, created_by=...
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return result
```

The `_tenant_filter` helper in that file (lines 34–41) is the cleanest reference:

```python
def _tenant_filter(user) -> dict:
    role = getattr(user, "role", "") or ""
    if role in _SUPER_ADMIN_ROLES:
        return {}
    tenant = getattr(user, "tenant_id", "") or ""
    if not tenant:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return {"tenantId": tenant}
```

For the new endpoint in `compliance_evidence_endpoints.py`, the existing per-asset guard (asset lookup against `tenantId`) is the correct pattern rather than copying `_tenant_filter` — it gives a 403 on asset-not-found without leaking whether the asset exists in another tenant.

### MongoDB Schema — Compliance Data

**Collection:** `asset_compliance`

Document shape (inferred from `update_one` calls in both `compliance_evidence_processor.py` and `compliance_evidence_endpoints.py`):

| Field | Type | Source |
|-------|------|--------|
| `assetId` | `str` | Primary lookup key (e.g., `"asset-hostname"`) |
| `controlId` | `str` | Secondary lookup key (e.g., `"A.8.22"`) |
| `tenantId` | `str` | Tenant isolation field |
| `status` | `str` | `"Compliant"`, `"Non-Compliant"`, `"Warning"`, `"Pending_Review"` |
| `lastUpdated` | ISO8601 str | Set on every write |
| `lastAutomatedCheck` | ISO8601 str | Set only by automated evidence processor |
| `checkName` | `str` | Set only by automated evidence processor |
| `agent_type` | `str` | Set only by automated evidence processor |
| `reason` | `str` | Optional — set by some paths |
| `remediation` | `str` | Optional — set by some paths |
| `evidence` | `list[dict]` | Array of evidence sub-documents |
| `ai_evaluation` | `dict` | Optional AI evaluation block |

**Primary lookup pattern** (the `update_one` filter used by all existing mutations):
```python
{"assetId": asset_id, "controlId": control_id}
```
The `TenantIsolatedCollection` wrapper in `database.py` automatically prepends `tenantId` to all queries.

**No index** on `(assetId, controlId)` is created at startup — only compound indexes on `(tenantId, controlId)` exist for `compliance_evidence` (a different collection from `asset_compliance`). The PATCH endpoint will do a full-collection scan without an index on `asset_compliance(assetId, controlId)`. Considered low-risk for phase 6 scope (lookup is key-exact), but may be worth flagging.

### Tenant Isolation Pattern

Tenant isolation is **automatic and ambient** via `database.py`'s `TenantIsolatedCollection` and `TenantIsolatedDatabase` wrappers.

When `get_current_user` is called as a dependency, it invokes `verify_token_async`, which calls `_set_tenant_id(tenant_id)` as a side effect (authentication_service.py line 157). From that point forward, any `db.asset_compliance.update_one(...)` call automatically prepends `{"tenantId": effective_tenant_id}` to the filter.

Super-admin bypass: if `tenant_id == "platform-admin"`, `_inject_tenant_id` returns the filter unchanged.

The practical implication for the new endpoint: the `asset_id`-level guard (look up `db.assets.find_one({"id": asset_id, "tenantId": tenant_id})`) is the explicit human-readable check. The implicit `TenantIsolatedCollection` layer provides the actual database-level enforcement. Both should be present for defense-in-depth.

---

## Frontend Patterns

### API Service

Base URL: `export const API_BASE = '/api';` (relative — proxied by Vite to backend).

Auth: `authFetch(url, options)` automatically attaches `Authorization: Bearer <token>` from `sessionStorage.getItem('token')`. It also handles proactive token refresh and 401 → refresh → retry cycle.

PATCH call pattern (from `apiService.ts` `apiService.patch` helper, lines 1959–1966):
```ts
const res = await authFetch(endpoint, {
    method: 'PATCH',
    body: JSON.stringify(body)
});
if (!res.ok) throw new Error(`PATCH ${endpoint} failed: ${res.statusText}`);
return await res.json();
```

All compliance-related calls currently in `apiService.ts` use `authFetch` directly with explicit `method` and `body: JSON.stringify(...)`:

```ts
// Example — PATCH tenant (lines 1905–1933):
const res = await authFetch(`${API_BASE}/tenants/${tenantId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabledFeatures: features, subscriptionTier: tier })
});
```

Note: `authFetch` auto-sets `Content-Type: application/json` for non-FormData bodies (lines 207–212), so the explicit `headers` object is optional for JSON payloads.

### Existing Status-Update Calls

No existing frontend function calls a compliance **status** PATCH. The closest analog is `deleteComplianceEvidence` (lines 649–654):

```ts
export const deleteComplianceEvidence = async (
    assetId: string, controlId: string, evidenceId: string
): Promise<void> => {
    const res = await authFetch(
        `${API_BASE}/assets/${assetId}/compliance/evidence/${evidenceId}`,
        { method: 'DELETE' }
    );
    if (!res.ok) throw new Error("Evidence delete failed");
};
```

The new function should follow this exact pattern but with `PATCH` and a JSON body containing `{ status, control_id }`. Return type should be `Promise<void>` or `Promise<AssetCompliance>` depending on whether the frontend needs the updated record.

---

## Types

### AssetCompliance Type (`types.ts`, lines 462–477)

```ts
export interface AssetCompliance {
  id: string;
  assetId: string;
  controlId: string;
  status: 'Compliant' | 'Non-Compliant' | 'Pending_Evidence';
  evidence: AssetComplianceEvidence[];
  lastUpdated: string;
  reason?: string;
  remediation?: string;
  ai_evaluation?: {
    verified: boolean;
    reasoning: string;
    evaluatedAt: string;
    model_used: string;
  };
}
```

`AssetCompliance['status']` is the union `'Compliant' | 'Non-Compliant' | 'Pending_Evidence'`. The `onUpdateStatus` prop is already typed to accept this union. The backend uses `"Pending_Review"` (from the upload endpoint, line 104) — note the mismatch: `Pending_Evidence` (frontend type) vs `Pending_Review` (backend write path). This is a pre-existing inconsistency; the status-update endpoint only needs to handle `Compliant` and `Non-Compliant` so it is not relevant to this phase.

The `AssetComplianceEvidence` sub-type (`types.ts`, lines 455–460):
```ts
export interface AssetComplianceEvidence {
  id: string;
  name: string;
  url: string;
  date: string;
}
```

The actual MongoDB evidence sub-documents have significantly more fields (see processor: `uploadedAt`, `source`, `systemGenerated`, `agent_type`, `content`, etc.) — the TypeScript type is narrower than reality. The component uses `any` casts for `ev.systemGenerated`, `ev.source`, `ev.evidence_content` etc. (line 112–113). This is a pre-existing looseness; the status PATCH does not change evidence sub-documents.

---

## UI-01 Badge Fix

### Current Implementation

Two badge spans in `components/AssetComplianceList.tsx`, lines 142–145:

```tsx
// Line 142 — Automated badge
<span className="px-1.5 py-0.5 text-[10px] font-semibold rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900 dark:bg-blue-300">Automated</span>

// Line 144 — Manual badge
<span className="px-1.5 py-0.5 text-[10px] font-semibold rounded-full bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300">Manual</span>
```

`text-[10px]` is a Tailwind arbitrary-value class that sets `font-size: 10px`. WCAG 1.4.4 (Resize Text) and general WCAG text-size guidance flag 10px as below the minimum readable threshold for small text. Tailwind's `text-xs` maps to `font-size: 0.75rem` (12px at default root = 16px), which is the standard minimum for badge-style text.

### Required Change

Replace `text-[10px]` with `text-xs` on both badge spans. Two occurrences in the same file, same pattern. No layout impact expected — `px-1.5 py-0.5` padding remains unchanged; the badge width grows slightly to accommodate the larger text.

---

## Key Decisions to Make in Planning

### 1. New collection vs. field on existing `asset_compliance` records?

**Recommendation: update the existing `asset_compliance` document.**

The `asset_compliance` collection already has a `status` field that is read by the frontend (`complianceData.find(c => c.assetId === assetId && c.controlId === control.id).status`). Writing a manual override to a separate collection would require the GET endpoint (`/api/compliance/evidence`) to merge records — adding complexity with no benefit.

Use `$set` on the existing document's `status` and `lastUpdated` fields, plus add a new `manual_override` boolean flag and `overriddenBy`/`overriddenAt` fields for STATUS-02 auditability. Keep everything in the same document.

### 2. Optimistic vs. pessimistic UI update?

**Recommendation: pessimistic — wait for backend 200 before updating state.**

The existing pattern in `FrameworkDetail` is already pessimistic (upload evidence → await success → call `refreshAssetCompliance(assetId)`). Status changes are low-frequency user actions; the extra ~200ms latency is acceptable. Optimistic updates add rollback complexity that is out of scope for this phase.

The implementation:
1. `onUpdateStatus` becomes `async`
2. It calls the new `updateAssetComplianceStatus(assetId, controlId, status)` API function
3. On success, calls `refreshAssetCompliance(assetId)` (already exists in FrameworkDetail)
4. Shows a `showToast` success/error message

Since `onUpdateStatus` prop is currently typed as `() => void`, the prop type in `AssetComplianceListProps` must also change to `(assetId: string, status: AssetCompliance['status']) => Promise<void>`.

### 3. STATUS-02 — actor/timestamp/previous-status record?

**Recommendation: embed a `status_history` sub-array in the same `asset_compliance` document.**

Pattern mirrors how `evidence` is stored as a `$push` array within the document. A `$push` to `status_history` on every manual override keeps the audit trail co-located with the compliance record, avoids a separate collection, and is queryable if needed.

Each history entry:
```json
{
  "changedAt": "<ISO8601>",
  "changedBy": "<username>",
  "previousStatus": "<old status>",
  "newStatus": "<new status>"
}
```

### 4. PATCH endpoint URL structure?

**Recommendation: `/api/assets/{asset_id}/compliance/status`**

- Matches the existing URL family (`/api/assets/{asset_id}/compliance/evidence`)
- `control_id` goes in the request body (not the URL) — consistent with how `control_id` is a form field in the evidence upload POST
- Keeps the asset as the primary resource, control as a body parameter

Alternative `/api/compliance/status/{asset_id}/{control_id}` is a valid REST pattern but breaks the URL family convention already established in this codebase.

---

## Risks / Landmines

### 1. `onUpdateStatus` prop return type must change

`AssetComplianceListProps.onUpdateStatus` is typed `() => void`. Making the handler async in `FrameworkDetail` requires changing the prop type to `() => Promise<void>`. This is a breaking interface change — but `FrameworkDetail` is the **only** consumer (confirmed by grep). No other files need updating.

### 2. `control.id` is not passed to `onUpdateStatus`

The button calls `onUpdateStatus(asset.id, 'Compliant')` but does NOT pass `control.id`. The parent (`FrameworkDetail`) has `control` in scope when it defines the callback (inside a loop over controls at line 766). So `control.id` can be captured in the closure in the parent. The API function needs `control_id` for the backend, but it does not need to come from `AssetComplianceList` — it comes from the closure in `FrameworkDetail`.

**This is the key wiring point:** `onUpdateStatus` in FrameworkDetail should be defined as:
```tsx
onUpdateStatus={async (assetId, status) => {
    await updateAssetComplianceStatus(assetId, control.id, status);
    await refreshAssetCompliance(assetId);
}}
```

### 3. `TenantIsolatedCollection.update_one` auto-injects `tenantId` into the filter

The `database.py` wrapper automatically adds `tenantId` to all filters. However, the existing evidence upload endpoint (line 101) calls `db.asset_compliance.update_one({"assetId": asset_id, "controlId": control_id}, ..., upsert=True)`. With tenant injection, the filter becomes `{"assetId": ..., "controlId": ..., "tenantId": ...}`.

**Upsert + tenant injection = risk.** If a new document is created by upsert, the `tenantId` field in the `$set` clause will set it on the document correctly (line 104). But if the existing document was written without `tenantId` (e.g., by the automated processor when tenant lookup failed), the tenant-filtered `update_one` will fail silently (matched=0). This is a pre-existing risk, not new to this phase, but the new PATCH endpoint should include explicit `tenantId` in both `$match` and `$set` for safety.

### 4. `status` field value mismatch between automated and manual paths

Automated evidence processor writes `"Compliant"`, `"Warning"`, `"Non-Compliant"`. The evidence upload endpoint (POST) writes `"Pending_Review"`. The frontend `AssetCompliance` type declares `'Compliant' | 'Non-Compliant' | 'Pending_Evidence'`. The new PATCH endpoint should only write `"Compliant"` or `"Non-Compliant"` (matching the TypeScript union members that the buttons pass). Setting a manual override should set a `manual_override: true` flag so the next automated heartbeat knows the user has explicitly set this and may choose not to overwrite it (a decision for STATUS-02 scope, but the flag should be written now).

### 5. No compound index on `asset_compliance(assetId, controlId)`

The startup code in `database.py` does not create an index on `asset_compliance` keyed by `(assetId, controlId)`. The `update_one` filter on this pair will do a collection scan. For typical compliance deployments (hundreds of assets × tens of controls = thousands of records), this is acceptable but worth noting. Adding an index is out of scope for this phase.

### 6. `compliance_evidence_endpoints.py` is approaching 450 lines

The file is currently 448 lines. Adding a new PATCH endpoint will push it over the 500-line rule in CLAUDE.md. Options: (a) keep it at ~470 lines (within tolerance if the new endpoint is compact), or (b) extract the new status-update endpoint into a new `compliance_status_endpoints.py` and register it similarly to how the evidence file is included. The planner should decide which approach to take.

---

## Sources

All findings are based on direct reading of the codebase files in this session.

| File | What was extracted |
|------|--------------------|
| `components/AssetComplianceList.tsx` | onUpdateStatus call sites, badge text-[10px] locations |
| `components/FrameworkDetail.tsx` (lines 382–395, 766–810) | no-op wiring, refreshAssetCompliance pattern |
| `backend/compliance_evidence_endpoints.py` | auth pattern, tenant guard, MongoDB update_one pattern, collection name |
| `backend/compliance_evidence_processor.py` | MongoDB schema, field names, status values written by automation |
| `backend/compliance_remediation_endpoints.py` | PATCH pattern, _tenant_filter helper, Pydantic update model |
| `backend/database.py` | TenantIsolatedCollection auto-injection, TenantIsolatedDatabase, get_database() |
| `backend/authentication_service.py` | get_current_user dependency, TokenData fields |
| `backend/compliance_endpoints.py` | Router composition, how evidence_router is included |
| `backend/router_registry.py` | Router registration, confirmed compliance_endpoints at line 108 |
| `services/apiService.ts` | API_BASE, authFetch pattern, existing compliance API functions |
| `types.ts` (lines 455–477) | AssetCompliance and AssetComplianceEvidence interface definitions |
