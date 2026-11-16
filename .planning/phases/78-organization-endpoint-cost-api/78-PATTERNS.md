# Phase 78: Organization & Endpoint Cost API - Pattern Map

**Mapped:** 2026-11-16
**Analogs found:** all files have an analog (new service/router/resolver are role-match; tests exact/role-match)
All paths below are git-tracked. Line counts are current (500-line cap noted).

## File Classification

| File | Status / lines now | Role | Data flow | Closest analog | Match |
|---|---|---|---|---|---|
| backend/itam_cost_service.py | NEW | service (pure, no FastAPI) | batch/transform | backend/itam_reporting_kpis.py `_compute_asset_value_kpi` (L53-124) | exact |
| backend/itam_tenant_scope.py | NEW | utility/dependency | request-response | backend/tenant_middleware.py L194-208 + tenant_context.get_tenant_id | role-match |
| backend/itam_cost_endpoints.py | NEW | route | request-response, paginated | backend/itam_kpi_endpoints.py (52) + itam_finance_endpoints.get_asset_book_value | exact |
| backend/router_registry.py | MOD 443 | config | n/a | L119-120 `_load(...)` lines | exact |
| backend/catalogue_mounts_assets.py | MOD 64 | config | n/a | L55-56 MOUNTS entries | exact |
| backend/itam_reporting_kpis.py | MOD 316 | service | batch | itself (replace loop L75-124) | exact |
| backend/itam_kpi_endpoints.py | MOD 52 | route | request-response | itself (replace L38-43 tenant guard) | exact |
| backend/itam_reporting_prebuilt.py | MOD 476 (24 spare) | service | batch | itself `_build_asset_value_rows` L109-~190 | exact |
| backend/itam_reporting_filters.py | MOD 499 (1 spare!) | service | transform | itself; do not grow, move code out if touched | n/a |
| backend/itam_reporting_endpoints.py (run/export routes) | MOD (not counted) | route | request-response | itself, `tenant_id = getattr(current_user, "tenant_id", None)` at L67, 113, 151, 222, 260, 301, 331 | exact |
| backend/itam_finance_endpoints.py | MOD 232 (only if reusing helpers) | route | request-response | itself L130-170 | exact |
| backend/tests/test_itam_cost_*.py (5 new) | NEW | test | - | tests/test_itam_reporting_kpis.py (464) `_make_kpi_app` L402-413; isolation/scale: tests/_mongo_test_db.py `mongo_db` | exact / role |
| tests/test_itam_reporting_kpis.py (464), test_itam_reporting_prebuilt.py (420), test_catalogue_slice_assets.py (158) | MOD | test | - | themselves | exact |
| Frontend: components/itam/ItamKpiPanel.tsx (214), ITAMConsole.tsx (190), itamI18n.tsx (104), types.ts (2451), src/__tests__/ITAMKpiPanel.test.tsx (203), ITAMConsole.test.tsx (246) | MOD | component/types/test | - | themselves | exact |
| services/apiService.ts (6358), App.tsx (2140), components/itam/ReportsPanel.tsx (374) | MOD, **UNCOMMITTED USER CHANGES** (git diff: apiService +10, App.tsx +36/-16, ReportsPanel -1) | | | | |

D-14 touches only ItamKpiPanel.tsx, fetchItamKpis, types.ts, itamI18n.tsx and the KPI test. Executors must edit apiService.ts / App.tsx / ReportsPanel.tsx surgically (read first, never checkout/stash/reformat) and never commit the user's hunks (stage with `git add -p`).

## Pattern Assignments

### backend/itam_cost_endpoints.py (route)
**Analog:** backend/itam_kpi_endpoints.py
```python
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from auth_types import TokenData
from database import get_database
from itam_asset_endpoints import _require_itam_viewer   # imported, never redefined (L20)
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/itam/kpis", tags=["ITAM KPIs"])   # use /api/itam/costs

    db = get_database()
    try:
        return await compute_itam_kpis(db, tenant_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("ITAM KPI computation failed for tenant %s: %s", tenant_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
```
Replace the 403 tenant guard (L38-43) with the shared resolver (400). Guard `_require_itam_viewer` (itam_asset_endpoints.py L68-90) = verify_permission view:itam OR manage:assets, then `_rbac_service._scopes_allow` for API keys (D-16).
Per-asset 404 for id outside tenant: copy `_load_asset` use in itam_finance_endpoints.py L149. Pagination: `from pagination_utils import PaginationParams, paginate`; `paginate(items, page, page_size)` takes the full sorted list (pagination_utils.py L52); `PaginationParams` has page=1, page_size=50. Compute totals from the full set, never the page (D-08). No `@cached`, no `$lookup`.
Reason strings: `REASON_NO_PURCHASE_RECORD="no_purchase_record"`, `REASON_NO_DEPRECIATION_POLICY="no_depreciation_policy_assigned"` (itam_finance_service.py L47-48).

### backend/itam_cost_service.py (pure service, db passed in)
**Analog:** itam_reporting_kpis.py L53-124 (module docstring L12-14: imports no FastAPI symbol).
```python
model_ids = sorted({a["modelId"] for a in assets if a.get("modelId")})
models_by_id = {}
if model_ids:
    model_docs = await db.asset_models.find(
        {"id": {"$in": model_ids}},
        {"_id": 0, "id": 1, "usefulLifeYears": 1, "salvageValueCents": 1},
    ).to_list(length=None)
    models_by_id = {m["id"]: m for m in model_docs}
now = datetime.now(timezone.utc)      # ONE now per request, pass it in
...
if purchase_cost is None or purchase_date is None: ... continue
if (not model_doc or model_doc.get("usefulLifeYears") is None or model_doc.get("salvageValueCents") is None): ...
try:
    result = compute_book_value(purchase_date=..., purchase_cost_cents=..., useful_life_years=..., salvage_value_cents=..., now=now)
except ValueError: ...
```
Imports: `from itam_finance_service import compute_book_value, REASON_*`; `from itam_models import DEFAULT_LIFECYCLE_STATUS, LifecycleStatus` (missing lifecycleStatus -> deployable: `asset.get("lifecycleStatus") or DEFAULT_LIFECYCLE_STATUS.value`, kpis L45). compute_book_value (finance_service L70-115): int division, floor at salvage, years clamp >=0, raises ValueError on bad life/date. Agents: one `db.agents.find({"assetId": {"$in": ids}}, projection)` (D-06; the asset find projection in prebuilt L127-130 shows projection style; add hardwareKey, serialNumber, lifecycleStatus, agentId). Duplicate marker D-07: `from seat_identity import normalize_serial` (seat_identity.py L27-33: strips, rejects junk/placeholder serials, returns upper-case or None); hardwareKey form is `serial:<value>` (asset_identity.py). Compare normalised values.
hasData convention: empty/no contributor -> `None` + `hasData: False` (kpis L65-73).

### backend/itam_tenant_scope.py (shared resolver, D-13/D-15)
**Analog:** tenant_middleware.py L194-208: JWT tenant_id overridden by `X-Tenant-ID` only when `rbac_defaults.platform_tier(role) == "owner"`, then `set_tenant_id(tenant_id)`. The resolved value is readable via `tenant_context.get_tenant_id()` (the same ContextVar database.py scopes by). Resolver: read `get_tenant_id()`; if falsy or `"platform-admin"` raise HTTPException 400; else return it. Do NOT re-implement the owner rule (Support/Billing then get 400 automatically). Planner: verify in a test that Owner+header gives the header tenant and `current_user.tenant_id` stays `platform-admin` (CONTEXT L98). Because middleware may not run in the `make_test_app` unit apps, tests need to call `set_tenant_id` / use the real-app probe.

### Registration
router_registry.py L119-120:
```python
    _load(app, "itam_reporting_endpoints", "router")    # ITAM Phase 72 Reporting Router
    _load(app, "itam_kpi_endpoints",       "router")    # ITAM Phase 72 KPI Router
```
add `_load(app, "itam_cost_endpoints", "router")`.
catalogue_mounts_assets.py L55-56 (the file is the guard, route lives under /api/itam so itam catalogue):
```python
    ("itam_kpi_endpoints", "router"): ITAM_API_KEY_GUARD,
    ("itam_reporting_endpoints", "router"): ITAM_API_KEY_GUARD,
```
add `("itam_cost_endpoints", "router"): ITAM_API_KEY_GUARD,`. `test_assets_slice_parity` (test_catalogue_slice_assets.py L22-30) uses `run_real_app_walk` + `parity_offenders`; add a probe `_case("/api/itam/costs/summary", role, scopes=..., api_key=True)` per `_case` helper L12-18 for D-16 scope narrowing.

### itam_reporting_prebuilt._build_asset_value_rows (MOD, 476 lines)
Current: finds assets with purchase record (L122-131), repeats the model batch (L133-140), loops with `_cents_to_dollars` (hard-coded `$`, keep), `_dash`, `_EM_DASH`, sort by `_sortKey` desc, unvalued last. Replace the data loop with the shared service (shrinks file); keep row formatting. Drop disposed/retired by default (D-04). Net line change must stay under 500.
KPI refactor: `_compute_asset_value_kpi` keeps `statusBreakdown` over ALL assets (D-04) but totals come from the service; `totalBookValueCents` becomes None/hasData False when nothing valued (D-10). `compute_itam_kpis` caller takes tenant from the resolver. Existing `withoutPolicyCount` key: keep for tile compatibility, add valued/total counts.

### Tests
**Unit/route** analog test_itam_reporting_kpis.py L402-413:
```python
def _make_kpi_app(mock_db, monkeypatch, permission_ok=True):
    def get_mock_tenant_db():
        return MockTenantIsolatedDatabase(mock_db, "tenant-a")
    monkeypatch.setattr(itam_kpi_endpoints, "get_database", get_mock_tenant_db)
    monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=permission_ok))
    app, _ = make_test_app(itam_kpi_endpoints.router)
```
(name-binding patch: patch `get_database` on `itam_cost_endpoints`; `make_test_app` in tests/conftest.py L198). 403 test pattern at L429-432.
**Isolation/scale (real Mongo)**: `from tests._mongo_test_db import mongo_db` (fixture L25-38 skips if Mongo is down, creates `omni_test_<hex>` DB; ensure it is dropped, test-DB leak was fixed earlier). Use for two-tenant isolation (D-13 matrix: Owner with/without X-Tenant-ID, Support/Billing -> 400) and ~20k-asset timing.
Parity test: seed one tenant, call `compute_itam_kpis`, `_build_asset_value_rows`, and the cost summary, compare totals; golden table for `compute_book_value` (life=1, salvage>=cost, cost=0, leap-day purchase 02-29, anniversary boundary, future date).

## Shared Patterns
- Guard: import `_require_itam_viewer` from itam_asset_endpoints only (never the copy in itam_catalog_endpoints.py).
- 500 handling: log tenant + exc, generic "Internal server error", re-raise HTTPException (kpi endpoints L48-52).
- Integer cents everywhere; no `*100`, `/100`, float sums in new code (the report's `_cents_to_dollars` stays display only).
- One `now` per request passed into the service; compute on read, no stored rollup.
- Tenant: every cost/KPI/report-run/export route calls the resolver; `db = get_database()` stays the tenant-scoped wrapper (`platform-admin` skips scoping in database.py, hence the 400).
- Frontend: `authFetch(url, { tenantId })` adds `X-Tenant-ID` (apiService.ts L302-317). `fetchItamKpis` (L6159-6163) is currently `authFetch(`${API_BASE}/itam/kpis`)` with no tenantId; add an optional `tenantId` param. Bug: ItamKpiPanel.tsx L100 `formatCurrency(assetValue.totalBookValueCents ?? 0)` -> show i18n "Not tracked" when null; `formatCurrency` at L21. i18n strings live in components/itam/itamI18n.tsx.

## No Analog Found
| Item | Reason |
|---|---|
| Duplicate-by-serial marker + summary duplicate count | No existing cross-asset pairing; build from seat_identity.normalize_serial plus hardwareKey `serial:` parsing |
| Coverage breakdown payload | New shape; follow hasData/None convention |

## Metadata
Searched: backend/*.py itam_*, tenant_middleware, tenant_context, pagination_utils, seat_identity, tests; frontend apiService/ItamKpiPanel. Pre-existing risk: itam_reporting_filters.py is at 499/500 lines, move code to a new module if any edit is needed.
