---
phase: 07-evidence-lifecycle-staleness-chain-of-custody
plan: "01"
subsystem: backend-evidence-lifecycle
tags: [staleness, chain-of-custody, mongodb-indexes, unit-tests]
dependency_graph:
  requires: []
  provides:
    - backend/evidence_staleness.py::compute_stale
    - backend/evidence_staleness.py::get_staleness_threshold
    - backend/evidence_coc.py::_append_coc_entry
    - backend/database.py::evidence_audit_log indexes
  affects:
    - backend/tests/test_evidence_lifecycle.py
tech_stack:
  added: []
  patterns:
    - tenant-first/global-fallback settings lookup (mirroring _get_raw_llm_settings)
    - raw Motor db._db access to bypass TenantIsolatedCollection
    - fire-and-forget CoC insert with logging fallback
    - asyncio.run() for async unit tests (consistent with decision 02-01)
key_files:
  created:
    - backend/evidence_staleness.py
    - backend/evidence_coc.py
    - backend/tests/test_evidence_lifecycle.py
  modified:
    - backend/database.py
decisions:
  - "Raw Motor db._db.evidence_audit_log used in _append_coc_entry to prevent TenantIsolatedCollection double-injecting tenantId from request context"
  - "evidence_audit_log has no TTL index — compliance audit trails must be retained long-term per research Open Question 2"
  - "compute_stale does not gate on systemGenerated/source — caller in 07-02 is responsible for filtering manual evidence before invoking it"
  - "asyncio.run() used for async tests — consistent with decision 02-01 (pytest-asyncio not installed)"
metrics:
  duration: "~3m"
  completed: "2026-06-22"
  tasks: 3
  files: 4
status: complete
---

# Phase 07 Plan 01: Evidence Lifecycle Foundation Summary

**One-liner:** Staleness helper (compute_stale + get_staleness_threshold) and immutable CoC append (_append_coc_entry) with evidence_audit_log compound indexes and 7-test Wave-0 scaffold.

## What Was Built

### Task 1 — evidence_staleness.py (57 lines)

Two functions implementing STALE-01:

- `compute_stale(uploaded_at: str, threshold_days: int) -> dict` — parses ISO 8601 upload timestamp, computes age in days, returns `{"stale": bool, "stale_days": int}`. Returns safe default `{"stale": False, "stale_days": 0}` on any parse error (ValueError/AttributeError/TypeError). Does NOT decide whether evidence is automated — the 07-02 caller gates on `systemGenerated`/`source`.
- `async get_staleness_threshold(db, tenant_id) -> int` — queries `system_settings` with tenant-first/global-fallback pattern (mirrors `_get_raw_llm_settings` in settings_endpoints.py). Uses `raw = db._db if hasattr(db, "_db") else db` to bypass TenantIsolatedCollection. Returns default `7` when no doc exists.

### Task 2 — evidence_coc.py (45 lines)

One coroutine implementing COC-01:

- `async _append_coc_entry(db, evidence_id, tenant_id, actor, action_type, snapshot_before, snapshot_after) -> None` — inserts one document into `evidence_audit_log` with all 7 fields. Uses `db._db.evidence_audit_log.insert_one(...)` (raw Motor) so TenantIsolatedCollection does not auto-inject tenantId. Fire-and-forget: swallows all exceptions via `logging.error`, never re-raises, returns None — a failed CoC write must not break the parent evidence operation.

### Task 3 — database.py indexes + test scaffold

**database.py:** Two compound indexes added immediately after the existing `compliance_evidence` compound index (line 264), inside the existing `connect_to_mongo()` try block:
- `evidence_audit_log (evidenceId, tenantId)` — supports CoC lookup per evidence item with tenant isolation
- `evidence_audit_log (tenantId, timestamp DESC)` — supports CoC list endpoint per tenant, time-ordered
- No TTL index — compliance audit trails must not be auto-purged.

**tests/test_evidence_lifecycle.py (155 lines, 7 tests):**
- `test_staleness_computation` — old date → stale=True, stale_days > threshold
- `test_staleness_inside_window` — future date → stale=False
- `test_staleness_bad_input` — unparsable → safe default without raise
- `test_staleness_manual_excluded` — caller-contract: manual evidence gate returns False
- `test_staleness_threshold_default` — no settings doc → returns 7
- `test_coc_create_entry` — insert_one awaited once, all 7 fields present
- `test_coc_never_raises` — insert_one raises Exception → returns None, no propagation

## Verification Results

```
$ python3 -c "import evidence_staleness, evidence_coc; print('imports OK')"
imports OK

$ python3 -m pytest tests/test_evidence_lifecycle.py -x -q
7 passed, 1 warning in 0.14s

$ grep -c 'evidence_audit_log.create_index' database.py
2

$ wc -l evidence_staleness.py evidence_coc.py tests/test_evidence_lifecycle.py
 57 evidence_staleness.py
 45 evidence_coc.py
155 tests/test_evidence_lifecycle.py
```

## Deviations from Plan

### Auto-added Tests

Two extra test functions added beyond the 5 specified (`test_staleness_inside_window`, `test_staleness_bad_input`) to cover edge cases required by the acceptance criteria (verify `compute_stale` returns safe default on bad input, and behaves correctly for dates within the window). These do not modify any interface or add external dependencies.

No other deviations — plan executed as written.

## Commits

| Hash | Task | Description |
|------|------|-------------|
| 6de432d | Task 1 | feat(07-01): add evidence_staleness.py helper module |
| 0bd73c9 | Task 2 | feat(07-01): add evidence_coc.py immutable CoC append helper |
| 7a3e139 | Task 3 | feat(07-01): add evidence_audit_log indexes and Wave-0 test scaffold |

## Known Stubs

None — all functions are fully implemented with real logic.

## Threat Surface Scan

No new network endpoints introduced in this plan. All new code is internal helper modules:
- `evidence_staleness.py` — pure compute function + DB read (no mutations)
- `evidence_coc.py` — DB insert only, no read/update/delete
- `database.py` — index creation only

T-07-01 through T-07-04 mitigations from the threat register are implemented:
- T-07-01: Only `insert_one` exposed, no update/delete helper created
- T-07-02: Fire-and-forget pattern implemented — swallows exceptions, never propagates
- T-07-03: Compound indexes on (evidenceId, tenantId) and (tenantId, timestamp) in place
- T-07-04: Raw Motor `db._db.evidence_audit_log` used, not TenantIsolatedCollection

## Self-Check: PASSED

- [x] backend/evidence_staleness.py exists (57 lines)
- [x] backend/evidence_coc.py exists (45 lines)
- [x] backend/tests/test_evidence_lifecycle.py exists (155 lines)
- [x] database.py has 2 evidence_audit_log.create_index calls, 0 TTL entries
- [x] All 3 commits exist: 6de432d, 0bd73c9, 7a3e139
- [x] 7 tests pass with 0 failures
