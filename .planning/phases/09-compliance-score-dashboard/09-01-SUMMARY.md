---
phase: 09-compliance-score-dashboard
plan: "01"
subsystem: backend-compliance-scoring
status: complete
tags: [compliance, scoring, caching, fastapi, redis, tdd]
dependency_graph:
  requires:
    - 08-01 (compliance_bulk_evidence_endpoints — extended with cache invalidation)
    - 07-01 (evidence_coc — chain-of-custody used by bulk upload)
    - 06-01 (compliance_status_endpoints — extended with cache invalidation)
  provides:
    - GET /api/compliance/score — severity-weighted score endpoint
    - compliance:score:{tenant_id} cache key pattern
  affects:
    - backend/router_registry.py (compliance_score_endpoints added to _REQUIRED_ROUTERS)
    - backend/compliance_status_endpoints.py (cache invalidation on status patch)
    - backend/compliance_bulk_evidence_endpoints.py (cache invalidation on bulk upload)
tech_stack:
  added: []
  patterns:
    - TDD RED/GREEN with asyncio.run() + TestClient (decision 02-01)
    - Category-based severity mapping (_CATEGORY_SEVERITY dict, Option A from RESEARCH.md)
    - Per-tenant Redis caching via CacheService (TTL 300s); super admin uses __super__ key
    - _score_status() copied inline (precedent: _require_admin in 07-02; avoids circular import)
    - invalidate_cache() called synchronously (CacheService.invalidate_cache is not async)
key_files:
  created:
    - backend/compliance_score_endpoints.py (161 lines)
    - backend/tests/test_compliance_score.py (307 lines)
  modified:
    - backend/router_registry.py (compliance_score_endpoints in _REQUIRED_ROUTERS + _load)
    - backend/compliance_status_endpoints.py (+2 lines: import + invalidate_cache call)
    - backend/compliance_bulk_evidence_endpoints.py (+2 lines: import + invalidate_cache call)
decisions:
  - "09-01: invalidate_cache() called synchronously — CacheService.invalidate_cache is not async (contrary to key_facts note); verified via agent_registry_endpoints.py usage pattern"
  - "09-01: compliance_frameworks queried via db._db.compliance_frameworks (raw Motor) per plan; also exempt from TenantIsolatedCollection in database.py lines 123-135 — both forms equivalent"
  - "09-01: _score_status() copied inline (7 lines) to avoid circular import risk per RESEARCH.md Pitfall 5 and STATE.md 07-02 decision precedent"
  - "09-01: Category-based severity (Option A) — no per-control severity DB field; Access Control/Cryptography/Incident Response→Critical, Audit/Configuration/Vulnerability→High, Operations/Risk Management→Medium, default→Low"
  - "09-01: compliance_evidence_endpoints.py intentionally not modified (495 lines; adding import+calls would reach 500 — CLAUDE.md limit); those paths rely on 300s TTL for natural expiry"
metrics:
  duration: "~7m"
  completed: "2026-06-22"
  tasks: 3
  files: 5
---

# Phase 09 Plan 01: Compliance Score Backend Summary

One-liner: Severity-weighted compliance score endpoint (GET /api/compliance/score) with per-tenant Redis caching, cache invalidation on bulk upload and status-patch, and an 8-test TDD suite.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create test_compliance_score.py (RED) | e038bd2 | backend/tests/test_compliance_score.py |
| 2 | Implement compliance_score_endpoints.py + register router (GREEN) | 4192a14 | backend/compliance_score_endpoints.py, backend/router_registry.py |
| 3 | Add cache invalidation to evidence write paths | bb7e0b9 | backend/compliance_status_endpoints.py, backend/compliance_bulk_evidence_endpoints.py |

## What Was Built

### GET /api/compliance/score

New endpoint returning:
```json
{
  "overall_score": 73.2,
  "frameworks": [
    {
      "framework_id": "soc2", "framework_name": "SOC 2 Type II", "short_name": "SOC 2",
      "score": 80.0, "passing": 3, "failing": 1, "partial": 0, "total_controls": 4
    }
  ],
  "computed_at": "2026-06-22T08:15:17+00:00",
  "tenant_id": "tenant-abc"
}
```

### Severity Weighting

SEVERITY_WEIGHTS: Critical=4, High=3, Medium=2, Low=1. Severity derived from
control category via `_CATEGORY_SEVERITY` static dict (Option A — no DB schema change).
Warning controls score at 50% of their weight (partial credit, consistent with
compliance_frameworks_endpoints.py _score() pattern).

### Caching

Cache key `compliance:score:{tenant_id}` (TTL 300s). Super admin uses
`compliance:score:__super__`. Invalidated on:
- PATCH /api/assets/{asset_id}/compliance/status (status patch)
- POST /api/compliance/evidence/bulk (bulk upload)
- Single-file paths in compliance_evidence_endpoints.py rely on 300s TTL (file at 495 lines — cannot add import+calls without breaching CLAUDE.md 500-line limit)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] invalidate_cache() is synchronous — plan said to use `await`**
- **Found during:** Task 3 implementation
- **Issue:** key_facts stated "cache_service.py is at backend/cache_service.py with invalidate_cache() as an async function" but the actual function (line 202) is `def invalidate_cache(pattern: str):` — not async
- **Fix:** Called without `await`, consistent with all existing callers (agent_registry_endpoints.py lines 214-215, 256-257, 325; asset_endpoints.py lines 101, 298-299, 362-363)
- **Files modified:** compliance_status_endpoints.py, compliance_bulk_evidence_endpoints.py
- **Commits:** bb7e0b9

## Test Results

```
tests/test_compliance_score.py ........ (8 passed)
tests/ — 415 passed, 1 skipped (full suite green, no regression)
```

## File Size Verification

| File | Lines | Limit | Status |
|------|-------|-------|--------|
| compliance_score_endpoints.py | 161 | 200 | PASS |
| compliance_evidence_endpoints.py | 495 | 500 | PASS (unchanged) |
| compliance_status_endpoints.py | 91 | 500 | PASS |
| compliance_bulk_evidence_endpoints.py | 231 | 500 | PASS |
| tests/test_compliance_score.py | 307 | 500 | PASS |

## Known Stubs

None — all score computation is live DB-backed; no placeholder data flows to response.

## Threat Surface Scan

All threat mitigations from the plan's threat register were applied:

| Threat ID | Mitigation | Implemented |
|-----------|-----------|-------------|
| T-09-01 | Cache key includes tenant_id from JWT; super admin uses __super__ | compliance_score_endpoints.py line 69 |
| T-09-02 | tenant_id from JWT (get_current_user dependency), not user input | compliance_score_endpoints.py lines 64-65 |
| T-09-04 | get_current_user dependency raises 401 on missing/invalid JWT | FastAPI Depends() on the endpoint |
| T-09-05 | db.asset_compliance (TenantIsolatedCollection) used, not db._db.asset_compliance | compliance_score_endpoints.py line 92 |

No new threat surface beyond the plan's threat register.

## Self-Check: PASSED

- [x] backend/compliance_score_endpoints.py exists (161 lines)
- [x] backend/tests/test_compliance_score.py exists (307 lines)
- [x] compliance_score_endpoints in _REQUIRED_ROUTERS (grep count=2)
- [x] invalidate_cache in compliance_status_endpoints.py (count=2: import + call)
- [x] invalidate_cache in compliance_bulk_evidence_endpoints.py (count=2: import + call)
- [x] All 8 tests pass
- [x] Full suite 415 passed, 1 skipped
- [x] Commits e038bd2, 4192a14, bb7e0b9 exist
