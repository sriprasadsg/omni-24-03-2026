---
phase: 07-evidence-lifecycle-staleness-chain-of-custody
plan: "02"
subsystem: backend-evidence-lifecycle
tags: [staleness, chain-of-custody, endpoints, tenant-isolation, integration-tests]
dependency_graph:
  requires:
    - backend/evidence_staleness.py::get_staleness_threshold
    - backend/evidence_staleness.py::compute_stale
    - backend/evidence_coc.py::_append_coc_entry
  provides:
    - backend/compliance_evidence_lifecycle_endpoints.py::router
    - GET /api/settings/evidence-staleness
    - PATCH /api/settings/evidence-staleness
    - GET /api/compliance/evidence/{evidence_id}/audit-log
    - GET /api/compliance/controls/{control_id}/audit-log
    - backend/compliance_evidence_endpoints.py::get_control_evidence (stale/stale_days fields)
    - backend/compliance_evidence_endpoints.py (4 CoC call sites)
  affects:
    - backend/router_registry.py
    - backend/tests/test_evidence_lifecycle.py
tech_stack:
  added: []
  patterns:
    - admin-only PATCH with _require_admin (mirrors settings_endpoints.py)
    - StalenessThresholdUpdate Pydantic model with Field(ge=1, le=365) → auto-422
    - tenant-first/global-fallback settings read via raw Motor db._db
    - CoC call sites placed after successful write await (fire-and-forget, Pitfall 2)
    - staleness threshold fetched once per GET request (no N+1)
    - TestClient dependency_overrides pattern for endpoint integration tests
key_files:
  created:
    - backend/compliance_evidence_lifecycle_endpoints.py
  modified:
    - backend/router_registry.py
    - backend/compliance_evidence_endpoints.py
    - backend/tests/test_evidence_lifecycle.py
decisions:
  - "compliance_evidence_lifecycle_endpoints.py declares router = APIRouter() with NO prefix — serves two URL spaces (/api/settings and /api/compliance)"
  - "_require_admin copied inline (not imported from settings_endpoints) to keep the file self-contained"
  - "get_control_audit_log collects evidence IDs from both control_evidence and asset_compliance collections before querying evidence_audit_log"
  - "delete_control_direct_evidence CoC call compacted to 4 lines to keep compliance_evidence_endpoints.py at 495 lines (under 500)"
  - "compliance_evidence_lifecycle_endpoints added to _REQUIRED_ROUTERS so a load failure fails startup fast (T-07-09)"
metrics:
  duration: "~5m"
  completed: "2026-06-22"
  tasks: 3
  files: 4
status: complete
---

# Phase 07 Plan 02: Evidence Lifecycle Endpoints & Interceptors Summary

**One-liner:** Staleness settings GET/PATCH with admin gate + 1-365 Pydantic validation, CoC read endpoints with tenant isolation, 4 CoC call sites in evidence mutations, and staleness injection in get_control_evidence — all wired on top of the 07-01 helpers.

## What Was Built

### Task 1 — compliance_evidence_lifecycle_endpoints.py (197 lines) + router_registry.py

Four endpoints in a new router registered as a required router:

- `GET /api/settings/evidence-staleness` — returns `{"thresholdDays": N}` for the caller's tenant; no admin gate (non-sensitive config); calls `get_staleness_threshold(db, tenant_id)` from the 07-01 helper.
- `PATCH /api/settings/evidence-staleness` — admin-only (`_require_admin`); validates `thresholdDays: int = Field(ge=1, le=365)` via `StalenessThresholdUpdate`; upserts to `system_settings` using `raw = db._db if hasattr(db, "_db") else db` idiom.
- `GET /api/compliance/evidence/{evidence_id}/audit-log` — returns CoC entries for a single evidence item; non-super users must have a tenant_id (else 403) and get `query["tenantId"] = tenant_id`.
- `GET /api/compliance/controls/{control_id}/audit-log` — aggregates evidence IDs from `control_evidence` and `asset_compliance`, then queries `evidence_audit_log`; same tenant isolation; returns `{"control_id": ..., "entries": []}` when no evidence IDs found.

`router_registry.py` changes:
- `_load(app, "compliance_evidence_lifecycle_endpoints", "router")` added after `compliance_remediation_endpoints`.
- `"compliance_evidence_lifecycle_endpoints"` added to `_REQUIRED_ROUTERS` frozenset.

### Task 2 — compliance_evidence_endpoints.py (495 lines)

Two imports added (`_append_coc_entry`, `get_staleness_threshold`, `compute_stale`).

Four CoC call sites (COC-01), each placed after the successful DB write `await`:
1. `upload_compliance_evidence` — after `asset_compliance.update_one(..., upsert=True)`: `action_type="create"`, `snapshot_after=evidence_record`.
2. `delete_compliance_evidence` — after `$pull` `update_one`: `action_type="delete"`, `snapshot_before=ev`.
3. `upload_control_direct_evidence` — after `control_evidence.insert_one(record)`: `action_type="create"`, `snapshot_after=record`.
4. `delete_control_direct_evidence` — after `control_evidence.delete_one(...)`: `action_type="delete"`, `snapshot_before=record`.

Staleness injection in `get_control_evidence` (STALE-01):
- `threshold = await get_staleness_threshold(db, tenant_id)` fetched once before the iteration loops.
- `system_docs`: each record tagged by `is_auto = bool(ev.get("systemGenerated") or ev.get("source") == "auto")`; automated records get `compute_stale(...)` result; others get `stale=False, stale_days=0`.
- `manual_docs`: all records get `stale=False, stale_days=0` (manual evidence never stale).

### Task 3 — tests/test_evidence_lifecycle.py (366 lines, 14 tests)

Seven new tests added (original 7 Wave-0 tests untouched):

- `test_coc_delete_entry` — verifies `snapshot_before` set and `snapshot_after=None` for delete action type.
- `test_get_staleness_threshold_default` — GET returns 200 with `thresholdDays: 7` when DB has no doc.
- `test_patch_staleness_threshold` — PATCH as admin returns 200 + `thresholdDays: 14` + `update_one` called with `upsert=True`.
- `test_patch_staleness_requires_admin` — PATCH as non-admin role returns 403.
- `test_staleness_threshold_validation` — PATCH with `thresholdDays: 0` → 422; `thresholdDays: 400` → 422.
- `test_get_coc_log` — GET audit-log returns 200 with 2 seeded entries.
- `test_coc_tenant_isolation` — non-super user with no tenant gets 403; tenant user's find query includes their tenantId.

## Verification Results

```
$ python -c "import compliance_evidence_lifecycle_endpoints, compliance_evidence_endpoints, router_registry; print('OK')"
OK

$ python -m pytest tests/test_evidence_lifecycle.py -x -q
14 passed, 1 warning in 1.01s

$ grep -c '_append_coc_entry(' backend/compliance_evidence_endpoints.py
4

$ grep -c 'compliance_evidence_lifecycle_endpoints' backend/router_registry.py
2

$ wc -l backend/compliance_evidence_lifecycle_endpoints.py backend/compliance_evidence_endpoints.py
197 backend/compliance_evidence_lifecycle_endpoints.py
495 backend/compliance_evidence_endpoints.py
```

## Deviations from Plan

### Minor: Line compaction in delete_control_direct_evidence CoC call

The CoC call at `delete_control_direct_evidence` was compacted from 9 lines to 4 to keep `compliance_evidence_endpoints.py` at 495 lines (under the 500-line CLAUDE.md limit). The plan anticipated ~18 lines total additions, but the multi-line CoC call format caused the count to hit 500. Functionality is identical.

No other deviations — plan executed as written.

## Commits

| Hash | Task | Description |
|------|------|-------------|
| a4cc7bf | Task 1 | feat(07-02): add compliance_evidence_lifecycle_endpoints and register as required router |
| 39a4aee | Task 2 | feat(07-02): add CoC interceptors and staleness injection in compliance_evidence_endpoints |
| 1857500 | Task 3 | test(07-02): add endpoint + interceptor integration tests for evidence lifecycle |

## Known Stubs

None — all endpoints are fully implemented with real logic.

## Threat Surface Scan

New network endpoints introduced (all in `compliance_evidence_lifecycle_endpoints.py`):

| Flag | File | Description |
|------|------|-------------|
| threat_flag: new-settings-write | compliance_evidence_lifecycle_endpoints.py | PATCH /api/settings/evidence-staleness mutates system_settings |
| threat_flag: new-audit-read | compliance_evidence_lifecycle_endpoints.py | GET audit-log endpoints read evidence_audit_log |

All threat register items mitigated:
- T-07-05 (cross-tenant CoC disclosure): `query["tenantId"] = tenant_id` for non-super; 403 without tenant. Verified by `test_coc_tenant_isolation`.
- T-07-06 (unauthorized threshold modification): `_require_admin` on PATCH. Verified by `test_patch_staleness_requires_admin`.
- T-07-07 (threshold injection/out-of-range): `Field(ge=1, le=365)` → 422. Verified by `test_staleness_threshold_validation`.
- T-07-08 (CoC entry written for failed op): call sites placed after successful write `await` (Pitfall 2). Fire-and-forget so CoC failure cannot block op.
- T-07-09 (router silently fails): added to `_REQUIRED_ROUTERS`.

## Self-Check: PASSED

- [x] backend/compliance_evidence_lifecycle_endpoints.py exists (197 lines)
- [x] backend/compliance_evidence_endpoints.py modified (495 lines, under 500)
- [x] backend/router_registry.py has 2 references to compliance_evidence_lifecycle_endpoints
- [x] backend/tests/test_evidence_lifecycle.py exists (366 lines, 14 tests pass)
- [x] All 3 commits exist: a4cc7bf, 39a4aee, 1857500
- [x] 14 tests pass with 0 failures
- [x] 4 _append_coc_entry calls in compliance_evidence_endpoints.py
