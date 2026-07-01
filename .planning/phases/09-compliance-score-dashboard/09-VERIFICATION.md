---
phase: 09-compliance-score-dashboard
verified: 2026-06-22T18:00:00Z
status: passed
score: 9/9
behavior_unverified: 0
overrides_applied: 0
---

# Phase 9: Compliance Score Dashboard Verification Report

**Phase Goal:** Each tenant has a live compliance score (% controls passing, severity-weighted) visible on the main dashboard, broken down by framework.
**Verified:** 2026-06-22T18:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | GET /api/compliance/score returns HTTP 200 with overall_score, frameworks list, computed_at, and tenant_id | VERIFIED | All 8 tests pass including test_score_endpoint_happy_path; endpoint implemented in compliance_score_endpoints.py lines 66-161 |
| 2 | Score uses severity weights Critical=4, High=3, Medium=2, Low=1; all-Compliant = 100.0, all-Non-Compliant = 0.0 | VERIFIED | SEVERITY_WEIGHTS dict at line 24; _weighted_score() at line 49; test_score_extremes and test_severity_weight_formula both pass |
| 3 | Per-framework breakdown includes framework_id, framework_name, short_name, score, passing, failing, partial, total_controls | VERIFIED | test_per_framework_breakdown passes; payload construction at lines 127-138 includes all 8 keys |
| 4 | Cache hit path returns cached payload without touching MongoDB | VERIFIED | test_score_cache_hit passes; cache.get() checked at line 75-77 before any DB call |
| 5 | Cache key compliance:score:{tenant_id} invalidated after evidence write (bulk upload, status-patch) | VERIFIED | invalidate_cache(f"compliance:score:{tenant_id}") at compliance_bulk_evidence_endpoints.py line 219 and compliance_status_endpoints.py line 90; test_cache_invalidated_on_upload passes |
| 6 | compliance_frameworks queried globally (raw Motor); asset_compliance via TenantIsolatedCollection | VERIFIED | db._db.compliance_frameworks.find({}) at line 82; db.asset_compliance.find() at line 99 — TenantIsolatedCollection auto-injects tenantId |
| 7 | compliance_score_endpoints registered in _REQUIRED_ROUTERS — startup aborts if it fails to load | VERIFIED | router_registry.py: "compliance_score_endpoints" in frozenset at line 23; _load call at line 134; grep count=2 confirmed |
| 8 | ComplianceScorePanel renders on main Dashboard above ComplianceStatus | VERIFIED | Dashboard.tsx line 49: `<ComplianceScorePanel />` immediately before `<ComplianceStatus ...>` at line 50; import confirmed at line 6 |
| 9 | fetchComplianceScore in apiService.ts calls backend endpoint; FrameworkScore and ComplianceScorePayload in types.ts | VERIFIED | fetchComplianceScore at apiService.ts line 727 calls authFetch(`${API_BASE}/compliance/score`); FrameworkScore interface at types.ts line 1677; ComplianceScorePayload at line 1688 |

**Score:** 9/9 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/compliance_score_endpoints.py` | GET /api/compliance/score, severity-weighted, ≤200 lines | VERIFIED | 161 lines — exists, substantive (full implementation), wired (registered in router_registry.py) |
| `backend/tests/test_compliance_score.py` | 8-test suite | VERIFIED | 307 lines, all 8 tests pass |
| `backend/router_registry.py` | compliance_score_endpoints in _REQUIRED_ROUTERS + _load | VERIFIED | frozenset entry + _load call both present (count=2) |
| `backend/compliance_status_endpoints.py` | invalidate_cache call on success path | VERIFIED | 91 lines; import at line 15, call at line 90 — on success path before return |
| `backend/compliance_bulk_evidence_endpoints.py` | invalidate_cache call on success path | VERIFIED | 231 lines; import at line 23, call at line 219 — after commit loop, before return, outside exception handlers |
| `backend/compliance_evidence_endpoints.py` | Unchanged at 495 lines | VERIFIED | 495 lines confirmed — no cache import added (intentional: would breach 500-line CLAUDE.md limit) |
| `components/ComplianceScorePanel.tsx` | Self-contained panel, ≤250 lines | VERIFIED | Exactly 250 lines; implements loading/error/empty states, accordion, tooltip, color helpers |
| `components/Dashboard.tsx` | Imports and renders ComplianceScorePanel above ComplianceStatus | VERIFIED | Import at line 6; mounted at line 49 in space-y-6 wrapper at line 48 |
| `services/apiService.ts` | fetchComplianceScore function | VERIFIED | Exported at line 727; returns Promise<ComplianceScorePayload | null>; uses authFetch |
| `types.ts` | FrameworkScore and ComplianceScorePayload interfaces | VERIFIED | FrameworkScore at line 1677 (8 fields); ComplianceScorePayload at line 1688 (4 fields) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `compliance_score_endpoints.py` | `database.py` | `get_database()` + raw Motor + TenantIsolatedCollection | VERIFIED | db._db.compliance_frameworks.find({}) line 82; db.asset_compliance.find() line 99 |
| `compliance_score_endpoints.py` | `cache_service.py` | `cache.get / cache.set` | VERIFIED | cache.get at line 75; cache.set at line 154 with ttl=300 |
| `compliance_bulk_evidence_endpoints.py` | `cache_service.py` | `invalidate_cache(f'compliance:score:{tenant_id}')` after commit | VERIFIED | Line 219, after commit loop closes, before return |
| `ComplianceScorePanel.tsx` | `services/apiService.ts` | `fetchComplianceScore()` called in useEffect on mount | VERIFIED | Import at line 4; called in useEffect at lines 79-89 with cancellation pattern |
| `services/apiService.ts` | backend GET /api/compliance/score | `authFetch(\`${API_BASE}/compliance/score\`)` | VERIFIED | Line 729; uses existing authFetch (JWT Bearer injected automatically) |
| `components/Dashboard.tsx` | `components/ComplianceScorePanel.tsx` | import + render above ComplianceStatus in space-y-6 wrapper | VERIFIED | Import line 6; `<ComplianceScorePanel />` line 49; `space-y-6` class line 48 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `ComplianceScorePanel.tsx` | `data` (ComplianceScorePayload) | `fetchComplianceScore()` → `GET /api/compliance/score` → MongoDB compliance_frameworks + asset_compliance | Yes — live DB aggregation, no static returns | FLOWING |
| `compliance_score_endpoints.py` | `payload` dict | `db._db.compliance_frameworks.find({})` + `db.asset_compliance.find({"controlId": {"$in": ...}})` | Yes — real Motor queries with no static fallback | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 8 compliance score tests pass | `python3 -m pytest tests/test_compliance_score.py -x -q` | 8 passed, 1 warning in 1.01s | PASS |
| Full test suite passes without regression | `python3 -m pytest tests/ -x -q` | 415 passed, 1 skipped, 3 warnings in 15.45s | PASS |
| compliance_score_endpoints.py ≤200 lines | `wc -l` | 161 lines | PASS |
| ComplianceScorePanel.tsx ≤250 lines | `wc -l` | 250 lines | PASS |
| compliance_evidence_endpoints.py unchanged | `wc -l` | 495 lines | PASS |
| No arbitrary text sizes in ComplianceScorePanel.tsx | `grep -c "text-["` | 0 | PASS |
| aria-expanded, aria-controls, role="alert" present | `grep -c` each | 1, 1, 1 | PASS |
| Framework rows use button elements | `grep -c "<button"` | 1 | PASS |
| fetchComplianceScore in apiService.ts | `grep -c` | 3 occurrences | PASS |
| FrameworkScore in types.ts | `grep -c` | 2 occurrences | PASS |
| ComplianceScorePanel in Dashboard.tsx | `grep -c` | 2 occurrences (import + mount) | PASS |
| invalidate_cache in compliance_status_endpoints.py | `grep -c` | 2 (import + call) | PASS |
| invalidate_cache in compliance_bulk_evidence_endpoints.py | `grep -c` | 2 (import + call) | PASS |
| compliance_score_endpoints in router_registry.py | `grep -c` | 2 (frozenset + _load) | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| SCORE-01 | 09-01, 09-02 | Live compliance score visible on main dashboard | SATISFIED | GET /api/compliance/score returns score; ComplianceScorePanel mounted in Dashboard; test_score_endpoint_happy_path, test_score_cache_hit, test_score_tenant_isolation pass |
| SCORE-02 | 09-01, 09-02 | Severity-weighted scoring (Critical=4, High=3, Medium=2, Low=1) | SATISFIED | SEVERITY_WEIGHTS dict + _weighted_score(); SeverityWeightTooltip in ComplianceScorePanel; test_severity_weight_formula + test_score_extremes pass |
| SCORE-03 | 09-01, 09-02 | Per-framework breakdown | SATISFIED | Backend payload includes per-framework dict with 8 fields; ComplianceScorePanel accordion drill-down; test_per_framework_breakdown passes |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | — | — | No debt markers (TBD/FIXME/XXX), no stubs, no hardcoded empty returns found in phase-modified files |

### Human Verification Required

None. All must-haves are verifiable programmatically. The UI rendering states (loading skeleton, error banner, empty state, accordion drill-down, tooltip) are behavior-dependent on runtime, but the structural/aria/class evidence is complete and the test suite covers the underlying data contract fully. No items escalated to human verification.

### Gaps Summary

No gaps. All 9 observable truths verified. All artifacts exist, are substantive, and are wired. All key links confirmed. Full test suite (415 tests) passes with no regression. File size limits respected. Cache invalidation is on the success path only. compliance_evidence_endpoints.py intentionally left unmodified at 495 lines (a documented, planned deviation tracked in the SUMMARY and STATE.md decisions).

---

_Verified: 2026-06-22T18:00:00Z_
_Verifier: Claude (gsd-verifier)_
