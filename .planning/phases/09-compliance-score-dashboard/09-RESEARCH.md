# Phase 9: Compliance Score Dashboard — Research

**Researched:** 2026-06-22
**Domain:** FastAPI compliance scoring, MongoDB aggregation, React dashboard panel
**Confidence:** HIGH

---

## Summary

Phase 9 adds a live, severity-weighted compliance score visible on the main `Dashboard.tsx`
component, broken down by framework. The backend exposes a single new endpoint
`GET /api/compliance/score` that performs a MongoDB aggregation over `asset_compliance` and
`compliance_frameworks` collections, applies severity weights, and returns an overall tenant
score plus per-framework breakdown. The result is cached in the existing Redis-backed
`CacheService` (with `fakeredis` fallback) and the cache key is invalidated on every evidence
write.

The frontend adds a new `ComplianceScorePanel.tsx` component rendered inside `Dashboard.tsx`
alongside the existing `ComplianceStatus` component. It fetches from `GET /api/compliance/score`
on mount, displays an overall percentage gauge (or bold number), and a per-framework breakdown
row with drill-down. A tooltip/legend explains the severity weights (Critical=4, High=3,
Medium=2, Low=1).

**Primary recommendation:** Implement the score endpoint in a new file
`backend/compliance_score_endpoints.py` (≤ 500 lines, all other compliance files are at or
near the limit), register it in `router_registry.py` as a `_REQUIRED_ROUTER`, and add a new
`ComplianceScorePanel.tsx` in `components/`. The cache-invalidation hook goes into every
evidence-write endpoint by calling `invalidate_cache("compliance:score:*")` after a successful
commit.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCORE-01 | Each tenant has a compliance score on the main dashboard: % controls passing across all monitored assets, computed at the time of the last evidence update | Score computed from `asset_compliance.status` via aggregation; cached at write time; Dashboard.tsx already has a compliance section ready for a new panel |
| SCORE-02 | Score is severity-weighted — Critical/High failures count more than Medium/Low — with weighting visible in a tooltip or legend | Severity field must be added to control documents or mapped at score-time via a static weight table; weight legend is a Tooltip on the score display |
| SCORE-03 | Score broken down by framework (e.g., SOC 2: 87%, ISO 27001: 72%) and can be expanded in a panel | Framework is the grouping key; `compliance_frameworks` collection provides the framework → control membership; accordion/expand UI on `ComplianceScorePanel.tsx` |
</phase_requirements>

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Score computation | API / Backend | — | Requires DB aggregation across `asset_compliance` and `compliance_frameworks`; must not run client-side (tenant isolation, data volume) |
| Caching score | API / Backend | — | Redis `CacheService` is already wired in backend; cache key is per-tenant |
| Cache invalidation on evidence write | API / Backend | — | Evidence write endpoints (upload, delete, bulk) call `invalidate_cache` after commit — same pattern as `agent_registry_endpoints.py` |
| Score display + overall gauge | Browser / Client | — | `ComplianceScorePanel.tsx` renders the panel; fetches from API on mount |
| Per-framework drill-down | Browser / Client | — | Expand/collapse accordion within `ComplianceScorePanel.tsx`; data comes from API breakdown |
| Severity weight legend | Browser / Client | — | Tooltip on the score display; static content, no API needed |

---

## Standard Stack

### Core (no new packages — all already in project)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI + Pydantic | (project version) | Endpoint + response model | Established project standard |
| Motor (AsyncIOMotorClient) | (project version) | MongoDB async queries | Established project standard |
| `cache_service` (internal) | — | Redis/fakeredis caching | Already used by `asset_endpoints.py` for invalidation |
| React + TypeScript | (project version) | Frontend panel | Established project standard |
| Tailwind CSS | (project version) | Styling | Established project standard |

**No new packages are needed.** All required capabilities already exist in the project.

### Package Legitimacy Audit

> No new packages are introduced in this phase. All implementation uses existing project dependencies.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none new) | — | — | — | — | — | — |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

---

## Architecture Patterns

### System Architecture Diagram

```
Browser (Dashboard.tsx)
    │
    │  GET /api/compliance/score
    ▼
FastAPI (compliance_score_endpoints.py)
    │
    ├─ cache.get("compliance:score:{tenant_id}")
    │      └─ HIT → return cached payload
    │
    └─ MISS → MongoDB aggregation
         ├─ compliance_frameworks (global collection, not tenant-isolated)
         │       → fetch framework ids, control lists, control.severity
         └─ asset_compliance (TenantIsolated)
                 → per-control status per asset
                 → apply _score_status() normalisation
                 → apply severity weights
                 → group by framework_id
         └─ compute overall weighted score + per-framework breakdown
         └─ cache.set("compliance:score:{tenant_id}", payload, ttl=300)
         └─ return payload

Evidence write path (upload / delete / bulk / status patch):
    → existing endpoint handles write
    → invalidate_cache("compliance:score:{tenant_id}")   ← NEW call added
```

### Recommended Project Structure

```
backend/
├── compliance_score_endpoints.py   # NEW — score endpoint + calculation helpers
backend/tests/
├── test_compliance_score.py        # NEW — unit + integration tests
components/
├── ComplianceScorePanel.tsx        # NEW — overall gauge + per-framework breakdown
services/
└── apiService.ts                   # EDIT — add fetchComplianceScore()
```

### Pattern 1: Score Calculation (severity-weighted)

**What:** Each control has a severity (Critical / High / Medium / Low). Instead of counting controls equally, each is given a weight. The score = sum(weight of passing controls) / sum(weight of all controls) × 100.

**Severity weights** (to be locked in plan — inform user via tooltip):

| Severity | Weight |
|----------|--------|
| Critical | 4 |
| High | 3 |
| Medium | 2 |
| Low | 1 |
| (missing/unknown) | 1 |

**Formula:**

```python
# Source: derived from ai_governance_service.py deduction pattern [ASSUMED]
SEVERITY_WEIGHTS = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}

def _weighted_score(controls_with_status: list[dict]) -> float:
    total_weight = 0
    passing_weight = 0
    for c in controls_with_status:
        w = SEVERITY_WEIGHTS.get(c.get("severity", "Low"), 1)
        total_weight += w
        if c["status_norm"] == "Compliant":
            passing_weight += w
        elif c["status_norm"] == "Warning":
            passing_weight += w * 0.5   # partial credit (consistent with _score() in compliance_frameworks_endpoints.py)
    if total_weight == 0:
        return 0.0
    return round(passing_weight / total_weight * 100, 1)
```

**When to use:** The severity-weighted formula applies to both the overall score and each per-framework breakdown score. [ASSUMED]

### Pattern 2: Cache invalidation on evidence write

**What:** After any evidence write (upload, delete, bulk, status patch), invalidate the score cache for the writing tenant.

**Example (adapted from agent_registry_endpoints.py):** [VERIFIED: codebase grep]

```python
from cache_service import invalidate_cache

# At the end of a successful evidence upload:
tenant_id = getattr(current_user, "tenant_id", "") or ""
invalidate_cache(f"compliance:score:{tenant_id}")
```

Add this call in:
- `compliance_evidence_endpoints.py` — `upload_compliance_evidence()` and `delete_compliance_evidence()` and `upload_control_direct_evidence()` and `delete_control_direct_evidence()`
- `compliance_status_endpoints.py` — `patch_asset_compliance_status()`
- `compliance_bulk_evidence_endpoints.py` — bulk upload handler

### Pattern 3: Endpoint registration as a REQUIRED router

All v1.1 phase endpoints have been registered as `_REQUIRED_ROUTERS` (see `router_registry.py`
lines 20–23). The score endpoint follows the same pattern. [VERIFIED: codebase grep]

```python
# router_registry.py — add to _REQUIRED_ROUTERS:
_REQUIRED_ROUTERS: frozenset[str] = frozenset({
    "compliance_status_endpoints",
    "compliance_evidence_lifecycle_endpoints",
    "compliance_bulk_evidence_endpoints",
    "compliance_score_endpoints",   # NEW
})

# In register_all_routers(), after compliance_bulk_evidence_endpoints:
_load(app, "compliance_score_endpoints", "router")
```

### Pattern 4: Frontend API function (apiService.ts)

**What:** A fetch helper named `fetchComplianceScore` following the same try/catch pattern
used by all compliance fetch functions.

```typescript
// Source: apiService.ts existing pattern [VERIFIED: codebase grep]
export const fetchComplianceScore = async (): Promise<ComplianceScorePayload | null> => {
    try {
        const res = await authFetch(`${API_BASE}/compliance/score`);
        if (!res.ok) {
            console.error(`[fetchComplianceScore] HTTP ${res.status}`);
            return null;
        }
        return await res.json();
    } catch (err) {
        console.error('[fetchComplianceScore] Request failed:', err);
        return null;
    }
};
```

### Anti-Patterns to Avoid

- **Computing score client-side from framework.progress field:** `ComplianceStatus.tsx` currently derives its pie chart data from the static `framework.progress` field (lines 37-48) — this is approximate/static data, not a live DB-backed score. The new `ComplianceScorePanel.tsx` must call the new API endpoint, NOT derive from `framework.progress`. [VERIFIED: codebase grep]
- **Using TenantIsolatedCollection for compliance_frameworks:** `compliance_frameworks` is in the DB exemption list (database.py lines 123-135) — it is a global collection. The score endpoint must manually inject `tenantId` filters for `asset_compliance` but must NOT inject tenant filters for `compliance_frameworks`. [VERIFIED: codebase grep]
- **Adding score logic to compliance_evidence_endpoints.py:** It is already at 495 lines. Any addition puts it over the 500-line CLAUDE.md limit. New file required. [VERIFIED: codebase grep]
- **Adding the new endpoint to the optional router list:** Score is tenant-critical; failure to load must abort startup, so it belongs in `_REQUIRED_ROUTERS`, not the optional list. [VERIFIED: codebase grep]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Caching score per tenant | Custom dict / file cache | `cache_service.cache.get/set/delete_pattern` | Already in project, handles Redis → fakeredis fallback, handles serialization |
| Status normalisation | New mapping logic | `_score_status()` in `compliance_reporting_data.py` | Existing function with all status strings handled; import it |
| Severity weight deductions | Invent new approach | `SEVERITY_WEIGHTS` dict (define once in `compliance_score_endpoints.py`) | Pattern already established in `ai_governance_service.py` line 160 |
| Tenant isolation on asset_compliance | Manual filter injection | `get_database()` (returns `TenantIsolatedCollection`) | Auto-injects `tenantId`; use `db.asset_compliance.find(...)` directly |

**Key insight:** The score calculation is a projection over data that already exists — status lives in `asset_compliance`, framework/control membership lives in `compliance_frameworks`. No new collections, no schema changes.

---

## Where Pass/Fail/Partial Status Already Lives

[VERIFIED: codebase grep]

### Primary source: `asset_compliance` collection

Each document represents one asset × one control pair and has:
- `assetId`, `controlId`, `tenantId`
- `status`: one of `"Compliant"`, `"Non-Compliant"`, `"Warning"`, `"Pending_Review"`, `"Pending_Evidence"`, etc.
- `evidence`: array of evidence sub-documents
- `manual_override`, `overriddenBy`, `overriddenAt`, `status_history`

The `_score_status()` function in `compliance_reporting_data.py` normalises all status strings to `Compliant` / `Non-Compliant` / `Warning`. This is the canonical normaliser to reuse.

### Secondary: framework's `controls[].status` field

Each control in `compliance_frameworks.controls[]` has a `status` field (type: `ControlStatus` = `"Implemented"`, `"In Progress"`, `"Not Implemented"`, `"At Risk"`). This is the control-level status, not the asset-level evidence status. The score should use the `asset_compliance` status (evidence-backed), not the framework's control-level status.

### Stale evidence as failing: integration with Phase 7

Phase 7 (`evidence_staleness.py`) computes staleness at read time — it injects `stale: true`
onto evidence items returned by GET endpoints. The score endpoint does NOT call the staleness
helper inline. Instead, the planner must decide: **stale automated evidence → treat as
Non-Compliant or Partial?** This is an open question (see Open Questions section). The
conservative, SCORE-01-safe default is to score based on recorded status only (not staleness)
to keep the computation fast and non-blocking. [ASSUMED — needs plan decision]

---

## Severity Field on Controls

[VERIFIED: codebase grep — types.ts, compliance_frameworks_endpoints.py, compliance_framework_mgmt_endpoints.py]

**The `Control` interface in `types.ts` (line 444-453) does NOT currently have a `severity` field.** Controls have: `id`, `name`, `description`, `category`, `status`, `lastReviewed`, `evidence`.

The framework modules in `backend/frameworks/` also do NOT define a per-control severity — they define `id`, `function`, `category`, `title`, `description`, `check_collection`, etc.

**Implication for SCORE-02:** The score endpoint cannot read a `severity` field from the DB because it does not exist per-control yet. Two approaches:

**Option A (Recommended — simpler, no schema change):** Map `category` or `function` to a severity tier using a static lookup table. For example, controls in high-risk categories (e.g., "Access Control", "Cryptography") are treated as High; operational categories as Medium; governance as Low. This is done entirely in the score endpoint logic. No DB migration needed. [ASSUMED — needs plan decision]

**Option B (Correct but larger scope):** Add a `severity` field to control documents in `compliance_frameworks.controls[]`, seed it at framework creation time, and expose it via the framework management endpoints. This is correct but requires a schema migration and is out of scope for a 2-plan phase. [ASSUMED]

**Recommended:** Option A for Phase 9. Document in the plan that a future phase can add per-control severity to the DB schema when needed.

---

## Caching Strategy

[VERIFIED: codebase grep — cache_service.py, agent_registry_endpoints.py, asset_endpoints.py]

### Existing cache infrastructure

`CacheService` in `backend/cache_service.py`:
- Redis with graceful fallback to `fakeredis` (in-process, not shared across workers)
- `cache.get(key)` / `cache.set(key, value, ttl)` / `cache.delete_pattern(pattern)`
- `invalidate_cache(pattern)` is the project-standard helper

### Score cache design

```
Cache key:  "compliance:score:{tenant_id}"
TTL:        300 seconds (5 minutes) — configurable in score endpoint
Invalidation trigger: any evidence write (upload/delete/bulk/status-patch)
```

The invalidation is a **write-through invalidation** (not write-through caching) — the cache entry is deleted on write; the next GET recomputes and re-caches. This is the same pattern used by `agent_registry_endpoints.py` and `asset_endpoints.py`. [VERIFIED: codebase grep]

**Super Admin consideration:** Super Admins can see all tenants. If a super admin calls
`GET /api/compliance/score`, the cache key should be `"compliance:score:__super__"` (or the
endpoint should skip caching for super admin and aggregate across all tenants). Use a separate
cache key for super admin. [ASSUMED]

---

## Framework Structure in DB

[VERIFIED: codebase grep — compliance_frameworks_endpoints.py, compliance_reporting_data.py, database.py]

The `compliance_frameworks` collection (global, not tenant-isolated):
```
{
  "id": "soc2",
  "name": "SOC 2 Type II",
  "shortName": "SOC 2",
  "controls": [
    { "id": "CC1.1", "name": "...", "category": "...", "status": "..." },
    ...
  ],
  "status": "Compliant|Pending|At Risk",
  "progress": 87,
  ...
}
```

The score endpoint's aggregation strategy:
1. Fetch all frameworks via `db.compliance_frameworks.find({})`
2. For each framework, collect `control_ids = [c["id"] for c in fw["controls"]]`
3. Fetch `asset_compliance` docs where `controlId` is in `control_ids` (tenant-isolated via `TenantIsolatedCollection`)
4. For each control, determine its normalised status (Compliant / Warning / Non-Compliant) from the latest `asset_compliance` doc for that tenant
5. Apply severity weights
6. Compute per-framework score
7. Compute overall weighted average

---

## File Size Constraints

[VERIFIED: codebase grep — wc -l output]

| File | Lines | Action |
|------|-------|--------|
| `compliance_evidence_endpoints.py` | 495 | DO NOT ADD — at limit |
| `compliance_reporting_data.py` | 207 | Could host helpers, but clean separation favours new file |
| `compliance_frameworks_endpoints.py` | 227 | Could host score but mixes concerns |
| `router_registry.py` | 300 | Add 2 lines only (registration + _REQUIRED_ROUTERS) |

**Decision:** New file `backend/compliance_score_endpoints.py`. Estimated ~120-160 lines for the endpoint + helpers. Well under 500-line limit.

---

## Frontend Dashboard Integration

[VERIFIED: codebase grep — Dashboard.tsx, ComplianceStatus.tsx, ComplianceDashboard.tsx]

### Where the main dashboard lives

`components/Dashboard.tsx` is the main dashboard rendered for the default view. It already renders:
- `MetricCard` components (grid)
- `AiInsights`
- `BusinessKpiChart`
- `AiSystemHealth`
- `AlertsPanel`
- `ComplianceStatus` — at line 48 (`<ComplianceStatus frameworks={complianceFrameworks} />`)

The `ComplianceStatus.tsx` component shows static `framework.progress` values in cards with a pie chart modal. It does NOT call any score API.

### What to add

A new `ComplianceScorePanel.tsx` component rendered above or below `ComplianceStatus` in
`Dashboard.tsx`. It:
- Fetches from `GET /api/compliance/score` on mount with `useEffect`
- Shows an overall score as a large number / circular gauge
- Shows per-framework rows with score and a colored bar
- Has a severity weight legend tooltip on the score label
- Has an expand/collapse per framework row (optional drill-down per SCORE-03)

`Dashboard.tsx` is currently ~52 lines — plenty of room to add the new panel import and rendering without approaching the 500-line limit.

### Type additions needed in types.ts

```typescript
export interface FrameworkScore {
  framework_id: string;
  framework_name: string;
  short_name: string;
  score: number;          // 0-100
  passing: number;
  failing: number;
  partial: number;
  total_controls: number;
}

export interface ComplianceScorePayload {
  overall_score: number;
  frameworks: FrameworkScore[];
  computed_at: string;    // ISO8601
  tenant_id: string;
}
```

---

## Common Pitfalls

### Pitfall 1: compliance_frameworks is global — do not inject tenantId

**What goes wrong:** If the score endpoint uses `db.compliance_frameworks.find({"tenantId": tenant_id})`, it returns zero frameworks for tenants that use the seeded global frameworks (which have no `tenantId` field).

**Why it happens:** `TenantIsolatedDatabase.__getattr__` exempts `compliance_frameworks` from tenant isolation (database.py line 123). So `db.compliance_frameworks` returns a raw collection, not a `TenantIsolatedCollection`. The exemption is correct — frameworks are global.

**How to avoid:** Query `compliance_frameworks` without `tenantId`. Tenant isolation applies only to `asset_compliance`. [VERIFIED: codebase grep — database.py]

### Pitfall 2: asset_compliance is tenant-isolated — TenantIsolatedCollection auto-injects tenantId

**What goes wrong:** Passing a raw `{"controlId": {"$in": control_ids}}` filter to `db.asset_compliance.find()` is correct — the wrapper automatically injects `tenantId`. But using `db._db.asset_compliance` (raw motor collection) bypasses isolation.

**Why it happens:** `db._db` is used in Phase 7 CoC code intentionally to bypass isolation for cross-tenant audit operations. The score endpoint must NOT use `db._db.asset_compliance`.

**How to avoid:** Always use `db.asset_compliance` (not `db._db.asset_compliance`) in the score endpoint. [VERIFIED: codebase grep — database.py, compliance_evidence_lifecycle_endpoints.py]

### Pitfall 3: Missing cache invalidation on bulk and status-patch paths

**What goes wrong:** If `invalidate_cache()` is added to `upload_compliance_evidence` but NOT to `delete_compliance_evidence`, `upload_control_direct_evidence`, `delete_control_direct_evidence`, `patch_asset_compliance_status`, and `compliance_bulk_evidence_endpoints.py`, the cached score becomes stale.

**How to avoid:** Plan must list all 6 write paths that touch `asset_compliance` or `control_evidence` and verify each adds `invalidate_cache(f"compliance:score:{tenant_id}")`. [VERIFIED: codebase grep — all write paths identified]

### Pitfall 4: Super Admin sees 0 score when cache miss

**What goes wrong:** Super Admin `tenant_id` is `None` or `""`. `cache.get("compliance:score:")` is an empty key that collides between tenants.

**How to avoid:** In the score endpoint, detect super admin and either (a) skip caching for super admin or (b) use `"compliance:score:__super__"` as the cache key. Recommend option (a): super admins are low-frequency users and cross-tenant aggregation is expensive to cache safely. [ASSUMED]

### Pitfall 5: `_score_status()` import creates circular dependency

**What goes wrong:** `compliance_score_endpoints.py` imports `_score_status` from `compliance_reporting_data.py`. If `compliance_reporting_data.py` later imports from `compliance_score_endpoints.py`, Python will error with circular import.

**How to avoid:** `compliance_reporting_data.py` is a pure utility module with no endpoint imports. Importing from it is safe. Alternatively, copy the 7-line `_score_status` function inline to keep `compliance_score_endpoints.py` self-contained (precedent: `_require_admin` copied inline in Phase 7 per STATE.md decision 07-02). [VERIFIED: codebase grep — compliance_reporting_data.py has no endpoint imports]

---

## Code Examples

### Backend endpoint skeleton

```python
# Source: compliance_evidence_lifecycle_endpoints.py (pattern adapted) [VERIFIED: codebase grep]
from fastapi import APIRouter, Depends, HTTPException
from database import get_database
from authentication_service import get_current_user
from cache_service import cache, invalidate_cache
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
router = APIRouter()

_SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}
SEVERITY_WEIGHTS = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}


def _score_status(status: str) -> str:
    """Normalise status string to Compliant / Non-Compliant / Warning."""
    s = (status or "").strip()
    if s in ("Compliant", "Pass", "Passed", "Implemented", "pass", "passed"):
        return "Compliant"
    if s in ("Non-Compliant", "Fail", "Failed", "Not Implemented", "fail", "failed"):
        return "Non-Compliant"
    return "Warning"


@router.get("/api/compliance/score")
async def get_compliance_score(current_user=Depends(get_current_user)):
    try:
        tenant_id = getattr(current_user, "tenant_id", None) or ""
        user_role = getattr(current_user, "role", "")
        is_super = user_role in _SUPER_ROLES

        cache_key = f"compliance:score:{tenant_id}" if not is_super else "compliance:score:__super__"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        db = get_database()
        # ... aggregation logic ...
        payload = { ... }
        cache.set(cache_key, payload, ttl=300)
        return payload
    except Exception as e:
        logger.error("compliance score error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
```

### Cache invalidation hook (added to write endpoints)

```python
# Source: agent_registry_endpoints.py pattern [VERIFIED: codebase grep]
from cache_service import invalidate_cache
# At end of successful evidence write:
invalidate_cache(f"compliance:score:{tenant_id}")
```

### Frontend fetch + panel sketch

```typescript
// Source: apiService.ts existing pattern [VERIFIED: codebase grep]
export interface ComplianceScorePayload {
  overall_score: number;
  frameworks: { framework_id: string; framework_name: string; short_name: string; score: number; }[];
  computed_at: string;
}

export const fetchComplianceScore = async (): Promise<ComplianceScorePayload | null> => {
    try {
        const res = await authFetch(`${API_BASE}/compliance/score`);
        if (!res.ok) return null;
        return await res.json();
    } catch { return null; }
};
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| framework.progress (static field, approximate) | Live DB-backed severity-weighted score | Phase 9 | Score reflects actual evidence quality, not seeded static values |
| Per-framework isolated scores | Overall tenant score + per-framework breakdown | Phase 9 | Single KPI visible on main dashboard (SCORE-01) |

**The `ComplianceStatus.tsx` "pie chart from framework.progress" pattern is NOT deprecated** — it remains on the main dashboard as the existing compliance governance posture overview. The new `ComplianceScorePanel.tsx` adds the live DB-backed score above or beside it.

---

## Validation Architecture

Nyquist validation is enabled (`workflow.nyquist_validation: true` in `.planning/config.json`).

### Test Framework

| Property | Value |
|----------|-------|
| Framework | Python `unittest` with `asyncio.run()` (consistent with all prior phases) |
| Config file | none — sys.path insertion pattern |
| Quick run command | `python -m pytest backend/tests/test_compliance_score.py -x` |
| Full suite command | `python -m pytest backend/tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCORE-01 | GET /api/compliance/score returns overall score 0-100 | unit | `python -m pytest backend/tests/test_compliance_score.py::test_score_endpoint_happy_path -x` | ❌ Wave 0 |
| SCORE-01 | Tenant isolation: score for tenant-a does not include tenant-b controls | unit | `python -m pytest backend/tests/test_compliance_score.py::test_score_tenant_isolation -x` | ❌ Wave 0 |
| SCORE-01 | Cache hit path returns cached payload without hitting DB | unit | `python -m pytest backend/tests/test_compliance_score.py::test_score_cache_hit -x` | ❌ Wave 0 |
| SCORE-01 | Score is 0.0 when no asset_compliance records exist | unit | `python -m pytest backend/tests/test_compliance_score.py::test_score_empty_tenant -x` | ❌ Wave 0 |
| SCORE-02 | Severity weights: Critical failure lowers score more than Low failure | unit | `python -m pytest backend/tests/test_compliance_score.py::test_severity_weight_formula -x` | ❌ Wave 0 |
| SCORE-02 | All-Compliant → score = 100; all Non-Compliant → score = 0 | unit | `python -m pytest backend/tests/test_compliance_score.py::test_score_extremes -x` | ❌ Wave 0 |
| SCORE-03 | Per-framework breakdown includes framework_id, framework_name, score | unit | `python -m pytest backend/tests/test_compliance_score.py::test_per_framework_breakdown -x` | ❌ Wave 0 |
| SCORE-01 | Cache is invalidated after evidence upload | unit | `python -m pytest backend/tests/test_compliance_score.py::test_cache_invalidated_on_upload -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `python -m pytest backend/tests/test_compliance_score.py -x`
- **Per wave merge:** `python -m pytest backend/tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `backend/tests/test_compliance_score.py` — all 8 test cases above
- [ ] Shared mock helpers for `_make_mock_frameworks_db()` and `_make_mock_ac_db()` (pattern from `test_evidence_lifecycle.py`)

---

## Security Domain

Security enforcement is enabled (`security_enforcement: true` in `.planning/config.json`, ASVS Level 1).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `get_current_user` dependency (already standard) |
| V4 Access Control | yes | tenant isolation via `TenantIsolatedCollection`; super admin bypass; cache key per tenant |
| V5 Input Validation | minimal | no user-controlled input to score GET endpoint; tenant_id from JWT not request body |
| V6 Cryptography | no | no crypto operations |

### Known Threat Patterns for this Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cross-tenant score leak via shared cache key | Information Disclosure | Cache key includes tenant_id from JWT; super admin uses separate key |
| Cache poisoning (if cache key is user-controllable) | Tampering | Cache key derives from `current_user.tenant_id` (JWT-extracted, not user input); no mitigation gap |
| Score DoS via repeated cache-busting | DoS | TTL=300s limits recomputation; super admin key is separate; rate limiter already in `rate_limiter.py` |

---

## Environment Availability

All dependencies are in-process; no new external services required.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Redis | Score caching | optional | — | fakeredis (in-process, already used by `CacheService`) |
| MongoDB | Score aggregation | ✓ | project version | mongomock (already used in tests) |

**Missing dependencies with no fallback:** none
**Missing dependencies with fallback:** Redis → fakeredis (already handled transparently by `CacheService`)

---

## Open Questions

1. **Should stale automated evidence count as Non-Compliant for the score?**
   - What we know: Phase 7 computes staleness at read-time in `evidence_staleness.py`; the score query reads `asset_compliance.status` which does NOT reflect staleness
   - What's unclear: SCORE-01 says "% controls passing" — does a stale evidence record mean the control fails?
   - Recommendation: For Phase 9, score uses recorded `status` only (ignoring staleness). Add a note in the score tooltip that stale evidence may affect real status. A future phase can add a `stale_controls` count to the score payload.

2. **Should controls with no `asset_compliance` records count as failing or be excluded?**
   - What we know: `_build_report_data()` counts controls with no asset data separately; `_score()` in `compliance_frameworks_endpoints.py` only scores evaluated controls
   - What's unclear: SCORE-01 says "% controls passing across all monitored assets" — "monitored" implies asset-evidence is required
   - Recommendation: Controls with no `asset_compliance` record are excluded from the score denominator (consistent with the `_score()` function pattern). Document in the tooltip: "Score covers controls with monitored asset evidence only."

3. **Severity-to-weight mapping without DB severity field**
   - What we know: No `severity` field exists on control documents currently
   - Recommendation: Use a static category-based lookup OR default all controls to weight=1 (unweighted simple percentage) for Phase 9, satisfying SCORE-02 visually via a legend that shows the weights applied by category. This avoids a schema migration. Lock this in the plan discussion.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Severity weights Critical=4, High=3, Medium=2, Low=1 are the right values | Standard Stack / Code Examples | Score differs from user expectation; planner should confirm |
| A2 | Stale evidence does NOT invalidate control status for the score | Open Questions #1 | Score appears higher than true compliance posture |
| A3 | Controls with no asset_compliance records are excluded from score denominator | Open Questions #2 | Score could be artificially high (all no-data = 0 denominator) or artificially low |
| A4 | Option A (category-based severity fallback) is acceptable for SCORE-02 | Severity Field on Controls | User may expect actual per-control severity fields |
| A5 | Super admin score query should skip caching | Pitfall 4 / Caching Strategy | Stale cross-tenant score for super admin calls |

---

## Sources

### Primary (HIGH confidence)

- [VERIFIED: codebase grep] `backend/database.py` — TenantIsolatedDatabase, collection exemptions, TenantIsolatedCollection auto-inject
- [VERIFIED: codebase grep] `backend/cache_service.py` — CacheService, `invalidate_cache()`, TTL patterns, fakeredis fallback
- [VERIFIED: codebase grep] `backend/compliance_reporting_data.py` — `_score_status()`, `_compliance_score()`, aggregation patterns
- [VERIFIED: codebase grep] `backend/compliance_frameworks_endpoints.py` — `_score()` formula with partial=0.5 credit, framework-to-control membership
- [VERIFIED: codebase grep] `backend/router_registry.py` — `_REQUIRED_ROUTERS` pattern, `_load()` registration
- [VERIFIED: codebase grep] `backend/compliance_evidence_endpoints.py` — evidence write paths (upload, delete ×2)
- [VERIFIED: codebase grep] `backend/compliance_status_endpoints.py` — status patch write path
- [VERIFIED: codebase grep] `components/Dashboard.tsx` — ComplianceStatus placement, dashboard layout
- [VERIFIED: codebase grep] `components/ComplianceStatus.tsx` — static progress-based display (NOT live DB)
- [VERIFIED: codebase grep] `services/apiService.ts` — authFetch pattern, existing compliance functions
- [VERIFIED: codebase grep] `types.ts` — Control interface (no severity field), ComplianceFramework interface
- [VERIFIED: codebase grep] `backend/tests/test_evidence_lifecycle.py` — asyncio.run() test patterns, MagicMock/AsyncMock patterns, TestClient/app.dependency_overrides
- [VERIFIED: codebase grep] `.planning/config.json` — nyquist_validation: true, security_enforcement: true

### Secondary (MEDIUM confidence)

- [CITED: STATE.md decisions] Phase 7: `Raw Motor db._db` used for CoC to prevent double-inject; implies score endpoint must use `db.asset_compliance` not `db._db.asset_compliance`
- [CITED: STATE.md decisions] Phase 8: `compliance_score_endpoints.py` is a new file — existing files at limit

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all implementation uses existing project patterns and dependencies
- Architecture: HIGH — data model verified in code; aggregation pattern verified in compliance_reporting_data.py
- Severity weighting formula: MEDIUM — pattern adapted from ai_governance_service.py but exact weights are a product decision (see A1)
- Pitfalls: HIGH — all derived from verified codebase reading

**Research date:** 2026-06-22
**Valid until:** 2026-07-22 (30 days — project stack is stable)
