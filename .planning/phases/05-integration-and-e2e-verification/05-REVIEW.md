---
phase: 05-integration-and-e2e-verification
reviewed: 2026-07-27T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - backend/compliance_remediation_endpoints.py
  - backend/compliance_reports_endpoints.py
  - backend/compliance_evidence_processor.py
  - backend/agent_heartbeat_endpoints.py
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: issues_found
---

# Phase 05: Code Review Report

**Reviewed:** 2026-07-27T00:00:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Phase 05 fixes three tenant-isolation/runtime bugs (GAP-1 TokenData.get crash, GAP-2 os.listdir info-leak, GAP-3 orphaned evidence). Core fixes are correct: `getattr` on TokenData, DB-sourced report listing with tenant filter, path-traversal guard on download, and `fallback_tenant_id` priority in evidence processing. No Critical defects. Two Warnings concern residual cross-tenant data-mixing via hostname-derived asset IDs and the legacy no-fallback code path that still writes `tenantId: None`.

## Warnings

### WR-01: Hostname-derived asset_id enables cross-tenant evidence collision

**File:** `backend/compliance_evidence_processor.py:223, 397-416`
**Issue:** `asset_id = f"asset-{agent_hostname}"` is derived from attacker-influenced payload hostname. Two tenants with the same hostname map to the same `asset_compliance` document keyed on `{"assetId": asset_id, "controlId": control_id}`. The `$set: {tenantId: tenant_id}` at line 406 is last-writer-wins, so tenant B's heartbeat overwrites tenant A's `tenantId` and appends evidence to the shared doc. `fallback_tenant_id` fixes *which* tenant is stamped but not the shared document key. The CR-02 comment (lines 233-235) addresses injection-by-hostname but not the shared-document collision.
**Fix:** Scope the asset_compliance key by tenant, e.g. include tenant in the id or filter: `{"assetId": asset_id, "controlId": control_id, "tenantId": tenant_id}` on all three update_one calls, and build `asset_id` as `f"asset-{tenant_id}-{agent_hostname}"` or resolve the real asset `_id` instead of a hostname string.

### WR-02: Legacy 3-arg path writes evidence with tenantId=None

**File:** `backend/compliance_evidence_processor.py:237-242, 376, 406`
**Issue:** When `fallback_tenant_id` is None (legacy callers) and neither the asset nor agent lookup yields a tenant, `tenant_id` stays None and evidence records are written with `tenantId: None` (line 376) and the control doc `$set tenantId: None` (line 406) — the exact GAP-3 orphaning the phase set out to fix, still reachable from any caller not passing `fallback_tenant_id`.
**Fix:** If `tenant_id` is None after all lookups, skip the write and log a warning rather than persisting orphaned evidence: `if not tenant_id: logger.warning(...); return`.

## Info

### IN-01: Broad Exception suppression in suggest_remediation asset lookup

**File:** `backend/compliance_remediation_endpoints.py:156-157`
**Issue:** `except Exception` swallows all asset-lookup failures (including DB outage) and proceeds to generate an AI suggestion with empty context. User gets a degraded suggestion with no signal that context was missing.
**Fix:** Acceptable for a non-critical enrichment, but log at `error` level so outages are visible: `logger.error("suggest_remediation asset lookup failed", exc_info=True)`.

### IN-02: Tenant context can leak on exception between lookup and main try

**File:** `backend/compliance_evidence_processor.py:252-296`
**Issue:** `set_tenant_id(tenant_id)` at line 253 runs outside any try; the guarding `try/finally` that restores `old_tenant_id` only starts at line 297. An exception in the dedup loop (252-295) would leave the tenant context set to `tenant_id` instead of restoring `old_tenant_id`.
**Fix:** Move `set_tenant_id(tenant_id)` inside the existing outer `try` (before line 297), or widen the try to cover line 253.

### IN-03: memory_used_mb formula couples percent and total silently

**File:** `backend/agent_heartbeat_endpoints.py:280`
**Issue:** `meta.get("current_memory", 0) * (meta.get("total_memory_gb", 16) * 1024 / 100)` assumes `current_memory` is a percentage and hardcodes a 16 GB default when total is missing, producing misleading metric values for agents that omit `total_memory_gb`.
**Fix:** Guard the derivation on presence of `total_memory_gb` rather than defaulting to 16, or store the raw percent and compute MB downstream.

---

_Reviewed: 2026-07-27T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
