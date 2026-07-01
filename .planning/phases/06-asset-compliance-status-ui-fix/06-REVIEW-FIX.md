---
phase: 06-asset-compliance-status-ui-fix
fixed_at: 2026-06-21T00:00:00Z
review_path: .planning/phases/06-asset-compliance-status-ui-fix/06-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 5
skipped: 1
status: partial
---

# Phase 06: Code Review Fix Report

**Fixed at:** 2026-06-21T00:00:00Z
**Source review:** .planning/phases/06-asset-compliance-status-ui-fix/06-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (CR-01, CR-02, WR-01, WR-02, WR-03, WR-04)
- Fixed: 5
- Skipped: 1

## Fixed Issues

### CR-01: Super-admin bypass silently skips tenantId guard

**Files modified:** `backend/compliance_status_endpoints.py`, `backend/tests/test_compliance_status.py`
**Commit:** 8c0070a
**Applied fix:** Replaced the conditional tenant-isolation check (which was skipped for super-admins) with an unconditional asset lookup by `asset_id` only. The asset's `tenantId` is extracted as `resolved_tenant_id` and used for all subsequent DB operations (`find_one`, `update_one` filter and upsert). Non-super-admins are then compared against `resolved_tenant_id`. This prevents the empty-string pollution bug and the cross-tenant write path for privileged callers. The companion test (test 2) was updated to supply an asset document belonging to tenant-a while the caller is in tenant-b, correctly exercising the 403 path under the new logic.

---

### CR-02: Evidence key collision causes incorrect item deletion

**Files modified:** `components/AssetComplianceList.tsx`
**Commit:** 552d4e0
**Applied fix:** Changed `evId` computation from `ev.id || ev.evidence_id || String(idx)` to `ev.id || ev.evidence_id` (no index fallback). The React key was updated to `evId ?? \`idx-${idx}\`` so rendering still works for legacy evidence without stable IDs. The delete button now has an additional `evId &&` guard so it is never rendered — and `handleDeleteEvidence` is never called — when no stable ID is present, preventing invalid API calls with bare index strings.

---

### WR-01: onUpdateStatus prop type is synchronous but caller is async

**Files modified:** `components/AssetComplianceList.tsx`
**Commit:** 562bc96
**Applied fix:** Changed the `onUpdateStatus` prop type in `AssetComplianceListProps` from `() => void` to `() => Promise<void>`. Added `updatingMap` state and a `handleUpdateStatus` async wrapper that sets/clears the per-asset loading flag around `await onUpdateStatus(...)`. Both status-change buttons now call `handleUpdateStatus` (not `onUpdateStatus` directly), are disabled while `updatingMap[asset.id]` is true, and carry `disabled:opacity-40` to communicate the in-flight state visually.

---

### WR-02: router_registry.py silently swallows load failures

**Files modified:** `backend/router_registry.py`
**Commit:** 4b84221
**Applied fix:** Added a `_REQUIRED_ROUTERS` frozenset containing `"compliance_status_endpoints"`. The `_load` function now re-raises after logging when `module_name in _REQUIRED_ROUTERS`, causing startup to fail fast rather than silently serve a 404 for the compliance status PATCH endpoint.

---

### WR-03: Test 3 uses bare pytest.raises(Exception)

**Files modified:** `backend/tests/test_compliance_status.py`
**Commit:** 5eeb445
**Applied fix:** Added `from pydantic import ValidationError` import at the top of the test file. Changed `pytest.raises(Exception)` to `pytest.raises(ValidationError)` in `test_patch_compliance_status_invalid_status_422`. The test now verifies that Pydantic's specific validation error is raised for out-of-range status values, not any arbitrary exception.

---

## Skipped Issues

### WR-04: FrameworkDetail.tsx exceeds 500-line CLAUDE.md limit

**File:** `components/FrameworkDetail.tsx:1-854`
**Reason:** Pre-existing scope violation — the file was 854 lines before this phase and the line count was not increased by this phase's changes. Splitting the three modal components (`ControlEvidenceUploadModal`, `AddControlModal`, `ReportsModal`) into separate files would require significant cross-file refactoring with import updates across the codebase, which is beyond the scope of an atomic fix pass. This finding is documented for the developer to address in a dedicated refactoring task.
**Original issue:** File is 854 lines, nearly double the 500-line ceiling set in CLAUDE.md. Three modal components share the file with FrameworkDetail itself.

---

_Fixed: 2026-06-21T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
