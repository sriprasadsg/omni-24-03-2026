---
phase: 26-vendor-and-risk-data-completeness
reviewed: 2026-07-27T00:00:00Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - backend/dpa_endpoints.py
  - backend/vendor_service.py
  - backend/vendor_endpoints.py
  - backend/risk_service.py
  - backend/risk_endpoints.py
  - components/VendorDetailModal.tsx
  - components/RiskFormModal.tsx
  - components/RiskRegister.tsx
findings:
  critical: 1
  warning: 4
  info: 4
  total: 9
status: issues_found
---

# Phase 26: Code Review Report

**Reviewed:** 2026-07-27T00:00:00Z
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

Phase 26 adds DPA lifecycle, vendor subprocessors, and inherent/residual risk scoring. Most tenant-scoping and RBAC gates are correct and consistently applied. One Critical authorization gap: `PATCH /api/dpa/{id}` has no admin gate and blindly `$set`s the client payload, letting any tenant member bypass the create/sign/terminate workflow and reassign `tenantId`. Additional Warnings cover a tenant-isolation hole in `VendorService._scope`, missing numeric-bounds validation on risk inputs at the API boundary, and mass-assignment on DPA update.

## Critical Issues

### CR-01: Ungated PATCH /api/dpa/{id} allows workflow + authz bypass and mass-assignment

**File:** `backend/dpa_endpoints.py:125-138`
**Issue:** `create_dpa`, `sign_dpa`, and `terminate_dpa` all enforce `_DPA_ADMIN_ROLES`, but `update_dpa` (PATCH) enforces no role gate and applies the raw client `payload` via `$set` after popping only `id`/`_id`. Any authenticated tenant member (including read-only roles) can therefore: (a) set `status: "active"`, `signed_by_us: true`, `signed_by_vendor: true` — bypassing the admin-gated sign workflow and its dual-party activation logic; (b) set `tenantId` to another value, orphaning or reassigning the agreement (the filter is tenant-scoped, but `tenantId` is not popped from the `$set` body); (c) overwrite `created_by`, `vendor_id`, or any other field.
**Fix:**
```python
@router.patch("/{dpa_id}")
async def update_dpa(dpa_id: str, payload: dict, db=Depends(_db), current_user=Depends(get_current_user)):
    if _role(current_user) not in _DPA_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    _ALLOWED = {"business_associate", "contact_email", "services", "phi_types",
                "effective_date", "expiration_date", "breach_notification_days", "audit_rights"}
    updates = {k: v for k, v in payload.items() if k in _ALLOWED}
    updates["updated_by"] = _sub(current_user)
    updates["updated_at"] = time.time()
    # ...scoped filter + $set updates...
```
Never let status/signature/tenant fields be client-writable via the generic PATCH.

## Warnings

### WR-01: VendorService._scope returns empty filter for tenantless non-admin — cross-tenant read

**File:** `backend/vendor_service.py:38-41`
**Issue:** `_scope` returns `{}` (no filter → all tenants) when `role` is non-super AND `tenant_id` is falsy. Only `get_vendors` guards against a missing tenant (`vendor_endpoints.py:47`); `get_vendor`, `add_subprocessor`, `remove_subprocessor`, `get_subprocessors`, `calculate_risk_score`, and `get_portfolio_summary` call the service directly, so an authenticated user with no `tenant_id` can read/mutate any tenant's vendor by id. Compare `risk_service._db`/`dpa_endpoints` which scope to `{"tenantId": tenant_id}` even when `tenant_id` is None (yielding no matches rather than all matches).
**Fix:** Make the tenantless branch fail closed: `return {"tenantId": tenant_id}` (matches nothing when None) or raise, instead of `return {}`.

### WR-02: Missing numeric-bounds validation on risk likelihood/impact at API boundary

**File:** `backend/risk_endpoints.py:9-39`, `backend/risk_service.py:50-57`
**Issue:** `RiskCreate`/`RiskUpdate` declare `likelihood`/`impact`/`residual_*`/`inherent_*` as bare `int` with no `ge=1, le=5` constraint. The frontend enforces 1–5 (`min`/`max`), but the backend accepts any integer, so `risk_score`/`residual_risk_score` can be arbitrarily large or negative — violating the CLAUDE.md "validate input at system boundaries" rule and corrupting portfolio aggregates.
**Fix:** Use `pydantic.Field(ge=1, le=5)` on all four score-input fields.

### WR-03: DPA expiration_date type inconsistency breaks stats query

**File:** `backend/dpa_endpoints.py:69-73, 107`
**Issue:** `dpa_stats` compares `expiration_date` numerically (`{"$lte": thirty_days_ts, "$gt": now_ts}` where both are epoch floats), but `create_dpa` stores `expiration_date` from an arbitrary client payload (`payload.get("expiration_date") or payload.get("expiry_date")`) with no coercion — typically an ISO string from the frontend. String vs. numeric comparison in Mongo silently never matches, so `expiring_soon` is always 0.
**Fix:** Coerce `expiration_date`/`effective_date` to epoch seconds on write (parse ISO → timestamp), or store both consistently and compare same-typed values.

### WR-04: remove_subprocessor reports success when nothing was removed

**File:** `backend/vendor_service.py:151-155`
**Issue:** Returns `result.matched_count > 0`, which is true whenever the *vendor* matches — even if the `$pull` removed no subprocessor (wrong `subprocessor_id`). The endpoint then returns 200 "removed successfully" for a no-op, and the caller believes a deletion happened.
**Fix:** Return `result.modified_count > 0` so a nonexistent subprocessor id yields the 404 the endpoint already maps.

## Info

### IN-01: Optional fields typed as bare `str = None` / `int = None`

**File:** `backend/risk_endpoints.py:17-39`
**Issue:** `mitigation_plan: str = None`, `residual_likelihood: int = None`, etc. rely on Pydantic v1 implicit-optional coercion. Under stricter typing this is a type mismatch (a `str` field defaulting to `None`).
**Fix:** Use `Optional[str] = None` / `Optional[int] = None` explicitly.

### IN-02: Empty numeric input yields NaN → 422

**File:** `components/RiskFormModal.tsx:81, 85, 91, 95`
**Issue:** `parseInt(e.target.value)` returns `NaN` when the field is cleared; `JSON.stringify(NaN)` serializes to `null`, which fails the required-`int` validation server-side with an opaque 422.
**Fix:** Guard: `parseInt(e.target.value) || 1` or coerce empty to a default in `onChange`.

### IN-03: fetchDPAs() fetches all DPAs to find one vendor's status

**File:** `components/VendorDetailModal.tsx:48-54`
**Issue:** Loads the entire DPA list on every modal open just to `.find` one by `vendor_id`. Functional but wasteful; a `?vendor_id=` filter or dedicated lookup would scale better. (Not flagged as perf per v1 scope — noted for maintainability.)
**Fix:** Add a vendor-scoped DPA lookup endpoint or query param.

### IN-04: Dead commented-out code

**File:** `components/VendorDetailModal.tsx:36`
**Issue:** `// const { showToast } = useToast(); // Remove this line` left in place.
**Fix:** Delete the commented line.

---

_Reviewed: 2026-07-27T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
