# Phase 78: Organization & Endpoint Cost API - Research

**Researched:** 2026-11-16
**Domain:** Multi-tenant read-only cost rollup over the existing ITAM `assets` / `asset_models` / `agents` collections (FastAPI + Motor, React tile fix)
**Confidence:** HIGH (every finding is in-repo and was read or executed this session; no external library is introduced)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Carried forward (already locked, not re-asked)**
- Cost routes are gated by `view:itam` through the canonical `_require_itam_viewer` imported from `backend/itam_asset_endpoints.py` (accepts `view:itam` or `manage:assets`, role check first, then API-key scope narrowing). Never a copied guard (v4.2 research Pitfall 15; the duplicate in `itam_catalog_endpoints.py` is a known drift case), never `view:finops`.
- Phase 76 D-04/D-10 already strip purchase cost, book value, warranty fields and `supplierId` from `/api/assets*` for callers without `view:itam`; nothing to redo here.
- Compute at read time: no stored rollups, no snapshot job, no `$lookup`, no `@cached` on cost routes (REQUIREMENTS v4.2 out-of-scope table, COST-07).
- Integer cents end to end, one implicit currency per tenant; no `* 100` / `/ 100` and no float sums in new cost code. PO/request float-dollar fields are never rolled into cost totals.
- Depreciation stays the Phase 59 D-04 definition in `itam_finance_service.compute_book_value` (whole-year steps on the purchase anniversary, integer division, floor at salvage). The rollup must not "improve" it.
- Phase 72 decision: every report/KPI reuses the owning surface's computation verbatim. One `now` per request for the whole rollup.

**Disposed & retired rule (COST-06)**
- **D-01:** Only `disposed` and `retired` leave the current book-value total. `archived` and `broken` stay in (still owned, still worth something); `deployable` and `deployed` stay in. An asset with no `lifecycleStatus` reads as `deployable` (existing read-time default).
- **D-02:** One explicit filter (for example `includeDisposed=true`; Claude names it) works the same on the summary and the per-asset list. Without it, Disposed/Retired assets are absent from the list and from both totals, so the list rows add up to the summary. With it, the summary's purchase total includes their purchase cost (the "historical purchase total") and the list returns their rows carrying their status.
- **D-03:** A Disposed/Retired row shown through the filter has book value `null` with reason `disposed` or `retired`, never `0` and never a depreciated "as if still owned" value. Its purchase cost is still shown. Book-value totals never include them, with or without the filter.
- **D-04:** The existing "Asset value" pre-built report (`itam_reporting_prebuilt._build_asset_value_rows`) follows the same default and drops Disposed/Retired rows, so tile, report and cost view agree row for row (roadmap SC3). The KPI tile's lifecycle-status pie chart keeps counting every status, because it is an inventory count, not money. **Visible change:** a tenant with disposed or retired assets sees the "Total Asset Value" tile drop.

**Endpoint list contents (COST-03)**
- **D-05:** `/costs/assets` lists every tenant asset by default (manual ITAM records and agent-discovered computers, same population and count as the Assets page), with an "agent endpoints only" filter. Unpriced agent computers appear as "not tracked" rows, so the coverage gap stays visible.
- **D-06:** For an asset that is an agent endpoint (linked only via `agents.assetId`, never by hostname), the row carries the agent id, hostname, status and last seen, read from the `agents` collection in one batched tenant-scoped `$in` query. Not from the asset's own `agentStatus`: the heartbeat stamps "Online" there and nothing sets it back.
- **D-07:** When an agent-discovered asset and a hand-entered asset match on serial number (the agent asset's `hardwareKey` `serial:<value>` against the manual asset's `serialNumber`), both rows carry a "possible duplicate" marker naming the other asset, and the summary reports a duplicate count. Never auto-merge and never move cost between rows; both rows still count.
- **D-08:** Default order is book value high to low, with "not tracked" rows last and name/asset tag as a stable tiebreak (the same order as the Asset value report). Book value is not stored, so the per-asset set is computed for the whole tenant and then paged. Totals are never computed from one page.

**Missing or partial cost data (COST-02)**
- **D-09:** An asset with a purchase price but no usable depreciation policy (no model, model without `usefulLifeYears`/`salvageValueCents`, or inputs that raise `ValueError`) counts in the purchase total, and its book value is `null` ("not tracked") with the existing reason `no_depreciation_policy_assigned`, left out of the book-value total. This is the same as the KPI and `GET /api/assets/{id}/book-value` today.
- **D-10:** Coverage is two counts plus a per-reason breakdown: "priced" (counts toward the purchase total) of total, "valued" (counts toward book value) of total, and counts per reason: no purchase record, no depreciation policy, unreadable date, disposed/retired, future purchase date, possible duplicate. A total with no contributing asset is `null` with `hasData: false` (the KPI convention), never `0`.
- **D-11:** A $0 purchase price is priced (donated or built in-house) and distinct from no price. A future purchase date keeps today's math (full price, since years elapsed clamps to 0) so every surface agrees, and the asset is flagged `futurePurchaseDate` and counted in the breakdown.
- **D-12:** The asset-level `useful_life_years` / `salvage_value` (float dollars) fields on the Asset models stay ignored. The model-level policy is the only depreciation source, exactly as `get_asset_book_value` resolves it today. No screen writes those fields.

**Tenant rule and the KPI tile (COST-07)**
- **D-13:** One shared tenant resolver serves the cost routes, the KPI route (`/api/itam/kpis`) and the Asset value report run/export routes. It takes the request's tenant context (a Platform Owner's `X-Tenant-ID` switcher choice, otherwise the caller's own tenant) and returns **400** when that context is `platform-admin` or empty, so no route ever returns a total blended across tenants. Today a Super Admin's tile sums every tenant's assets, because `fetchItamKpis()` sends no `X-Tenant-ID` and the route accepts `platform-admin` as a tenant. - **Reversibility:** reversible - one helper; reverting restores the blended Super Admin tile.
- **D-14:** Small tile fix in this phase, in `components/itam/ItamKpiPanel.tsx` and `fetchItamKpis` only: show "Not tracked" instead of `$0.00` when the book value is null, add a "Valued X of Y assets" line, send the Super Admin's selected tenant with the KPI request, and show a "Select a tenant" state when none is chosen. No other UI work; the Costs tab stays in Phase 80.
- **D-15:** Only the Platform Owner tier can choose a tenant (the existing `X-Tenant-ID` rule in `backend/tenant_middleware.py`). Platform Support and Platform Billing always get 400 on these routes; widening the override is not part of this phase.
- **D-16:** ITAM API keys may read the cost routes exactly as they read `/book-value` and `/kpis`: the owner's role first, then the key's scopes must allow `view:itam` or `manage:assets`; anything else gets 403. A scope-narrowing test proves it. - **Reversibility:** costly - once integrators read cost data through API keys, withdrawing it breaks their calls.

### Claude's Discretion
- Where the shared per-asset computation lives (research suggested a pure `backend/itam_cost_service.py` with `db` passed in, one projected `assets` find, one `asset_models` `$in`, one `agents` `$in`, a Python loop) and how the KPI and the report are refactored onto it.
- Response field names and shape, reason-code strings for the new reasons (disposed, retired, future date, duplicate), filter parameter names, and the 404 for an asset id outside the tenant.
- Pagination style (`PaginationParams` page/page_size is the existing convention; keyset is optional), as long as D-08's full-set sort holds and totals never depend on the page.
- Serial-number normalisation for D-07 (case, whitespace, placeholder serials such as "To Be Filled By O.E.M." that must not match).
- Golden-value table cases (research list: life=1, salvage >= cost, cost=0, leap-day purchase, anniversary boundary, future date) and the large-tenant timing test (research suggested about 20k assets).
- Exact copy for the D-14 tile states (subject to existing ITAM i18n in `itamI18n.tsx`).

### Deferred Ideas (OUT OF SCOPE)
- Letting Platform Billing (or Support) pick a tenant for cost reads: raised and declined for this phase (D-15). It would change the platform-role tenant-override rule.
- Removing or honouring the unused asset-level `useful_life_years` / `salvage_value` fields (D-12): a cleanup candidate, not this phase.
- Already tracked elsewhere: license cost (Phase 79), Costs tab and export (Phase 80), COST-F1..F4.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| COST-01 | Org and endpoint cost reuse the same per-asset book-value computation as the KPI tile, enforced by a parity test | Shared pure `compute_asset_cost` over `compute_book_value`; KPI, `asset_value` report and cost routes all call it; `utc_now` seam + golden table + real-Mongo parity test (Architecture Patterns 1, Validation) |
| COST-02 | `GET /api/itam/costs/summary` returns purchase total + book value + coverage; unpriced = null never 0 | Summary shape, `hasData` convention, reason precedence that sums to total (Pattern 2, Pitfalls 4-5) |
| COST-03 | `/costs/assets` (paginated) and `/assets/{id}` return per-asset cost; endpoints joined only via `agents.assetId` | One batched `agents` read, `paginate()` over the full sorted set, 404 for foreign ids (Pattern 3, Don't Hand-Roll) |
| COST-06 | Disposed/retired excluded from book value by default; historical purchase totals only behind explicit filter; same rule in KPI and cost view | `INACTIVE_STATUSES` constant in the one shared function; `includeDisposed` filter (Pattern 1) |
| COST-07 | Every cost route requires explicit tenant (400 for platform-admin), no `$lookup`/request-cache, mandatory two-tenant isolation test | `resolve_itam_tenant` reading the header directly (ambient tenant is overwritten by auth - Pitfall 1), explicit `tenantId` in every filter, real-Mongo isolation test (Security Domain, Validation) |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Do what was asked; nothing more. Do not create files unless necessary (new service/endpoint/test files named in this research are the necessary ones); no documentation files beyond the phase artifacts.
- Keep files under 500 lines. **Two files this phase touches are already at the cap:** `backend/itam_reporting_prebuilt.py` (476 lines) and `backend/itam_reporting_filters.py` (499 lines). Refactors there must shrink or hold line counts, never grow them. [VERIFIED: `wc -l` this session]
- Validate input at system boundaries (query params via `Query(..., ge=, le=)`, enum-checked filters).
- Never commit secrets/.env. Never save tests to repo root (use `backend/tests/`, `src/__tests__/`).
- Always read a file before editing. Always run tests after code changes; verify the build (`npm run build && npm test` is the project line; the phase's own commands are below).
- No `Co-Authored-By` trailer unless `.claude/settings.json` sets `attribution.commit`. [VERIFIED: `grep attribution .claude/settings.json` returned nothing]
- Project memory (user's standing decisions): backend restarts, UI publishes and `git push` are the user's; plans must not include a deploy step. Never run the claude-flow CLI from a worktree.

## Summary

Phase 78 is a read-only rollup built on code that already exists: `compute_book_value` (pure, Phase 59), the batched KPI loop in `itam_reporting_kpis.py`, the asset-value report loop in `itam_reporting_prebuilt.py`, and a fourth copy inside `itam_reporting_filters._compute_finance_result` (the custom report builder's "Book Value" column - not named in CONTEXT). The recommended design is one pure function `compute_asset_cost(asset, model_doc, now)` plus thin loaders in a new `backend/itam_cost_service.py`; the KPI, the report, the summary route and the list/detail routes all call it. No new library is needed.

**The single most important finding is a flaw in the premise of D-13.** CONTEXT assumes the Platform Owner's `X-Tenant-ID` choice is visible to a handler as the ambient tenant (`get_tenant_id()`). It is not. `TenantMiddleware` sets the override, but `verify_token_async` (reached through `get_current_user`, and through `get_current_user_or_api_key`, so through `_require_itam_viewer`) then calls `_set_tenant_id(tenant_id)` with the **token's** tenant, i.e. `platform-admin`, and the database wrapper skips scoping for that value. I proved this by running a probe app: an Owner token with `X-Tenant-ID: tenant-b` yields `{"ambient":"platform-admin"}` on both dependency routes and `{"ambient":"tenant-b"}` only on a route with no auth dependency. Consequences: (1) the resolver must read the header itself (owner tier, session auth only) rather than `get_tenant_id()`; (2) after resolving it must `set_tenant_id(resolved)` so the KPI route's other collections (licenses, assignments, settings) are also scoped; (3) every cost-service query must carry an explicit `tenantId` filter, because under a `platform-admin` ambient the wrapper adds none. Without this the Owner-with-header path returns blended data - the exact leak COST-07 forbids.

Second finding: D-15 says Platform Billing "always gets 400". Billing's built-in permissions do not include `view:itam`, so it is refused with **403** by the guard before the resolver runs; only Platform Support (which holds `view:itam`) and the Owner reach the 400. Confirmed by probing the real app: billing 403, support and Super Admin reach the handler.

**Primary recommendation:** Build `itam_cost_service.py` (pure `compute_asset_cost` + loaders), `itam_tenant_scope.py` (`resolve_itam_tenant(request, current_user)` reading the header and calling `set_tenant_id`), `itam_cost_endpoints.py` (prefix `/api/itam/costs`, registered in `router_registry.py` **and** added to `catalogue_mounts_assets.MOUNTS` with `ITAM_API_KEY_GUARD`), refactor KPI + report + custom-builder loops onto the shared function behind a single `utc_now` seam, and gate the phase on a real-Mongo, real-middleware two-tenant test.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Per-asset cost + book value computation | API / Backend (pure service module) | - | Phase 59 D-04 / Phase 72: computed at read time, one function, never stored |
| Tenant resolution (400 on platform-admin) | API / Backend (request layer) | - | Header + role + auth source are request facts; must run before any DB read |
| Tenant isolation of reads | Database wrapper (`TenantIsolatedCollection`) **plus** explicit `tenantId` in every filter | API / Backend | Wrapper skips scoping for `platform-admin`; the explicit filter is the control that holds on the Owner path |
| `view:itam` gate + API-key scope narrowing | API / Backend (`_require_itam_viewer` + catalogue mount guard) | - | Existing canonical guard; mount guard needed for Phase 76 parity |
| Paging, sorting, filtering of cost rows | API / Backend (Python over the full set) | - | Book value is not stored (D-08); totals must never depend on a page |
| Agent endpoint join | Database (`agents` collection, one batched read) | API / Backend | Join only via `agents.assetId` (D-06) |
| Duplicate-serial marking | API / Backend | - | Pure Python over the already-loaded asset set |
| KPI tile null/valued rendering, tenant header | Browser / Client | - | D-14; the tenant choice lives in `App.tsx` state `viewingTenantId` |
| Currency formatting | Browser / Client | - | Integer cents on the wire; shared formatting is Phase 80 |

## Standard Stack

### Core (all already in the repo - no installs)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.141.1 | Router, `Depends`, `Query` validation | Existing stack [VERIFIED: venv import this session] |
| Motor / PyMongo | 3.7.1 / 4.18.2 | Batched `find(...).to_list` reads | Existing stack [VERIFIED: venv import this session] |
| Pydantic | 2.13.5 | Optional response models (codebase convention is `Dict[str, Any]`) | Existing stack [VERIFIED] |
| `itam_finance_service.compute_book_value` | in-repo | The single depreciation function | Locked by CONTEXT |
| `pagination_utils.paginate` | in-repo | Python-side paging of an in-memory list (returns `items,total,page,pageSize,totalPages,hasNext,hasPrev`) | Matches `/api/assets` envelope (pagination_utils.py `paginate`) |
| `seat_identity.normalize_serial` | in-repo | Serial normalisation incl. junk placeholders | Already used to build `hardwareKey` |
| React 19-era app, Vitest 5.0.0, recharts | in-repo | Tile fix + tests | Existing |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest 9.1.1 + pytest-asyncio 1.4.0 | installed | Backend tests (`asyncio_mode = auto`) | All backend tests [VERIFIED: venv] |
| `tests/_mongo_test_db.mongo_db` | in-repo fixture | Throwaway real-Mongo DB (`omni_test_<uuid>`), skips if unreachable | Isolation, parity and scale tests |
| `tests/_route_walk.probe_real_app` | in-repo helper | Status codes from the real app in a fresh interpreter | 403/400 route-level probes |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Python loop over projected docs | Mongo `$group`/`$lookup` aggregation | Forbidden by COST-07 (`$lookup`) and cannot reuse `compute_book_value` verbatim |
| `mongomock_motor` for isolation test | Real mongod | `database.py` can fall back to mongomock, but a mock cannot prove the wrapper's `platform-admin` bypass semantics; real mongod 8.0.34 is running locally |
| Keyset pagination | `paginate()` page/page_size | Keyset gives nothing here: the whole set is computed anyway (D-08) |

**Installation:** none. **Package Legitimacy Audit:** this phase installs no external package; the gate is not applicable.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none) | - | - | - | - | - | No new dependencies |

**Packages removed due to [SLOP] verdict:** none. **Packages flagged [SUS]:** none.

## Architecture Patterns

### System Architecture Diagram

```
 Browser (ITAM Reports tab: ItamKpiPanel)                API client (session or API key)
   fetchItamKpis(tenantId?)  --X-Tenant-ID-->                  |
                                  \                            |
                                   v                           v
 TenantMiddleware (sets ambient tenant; owner-tier X-Tenant-ID override)
        |
        v   router-level: catalogue mount guard (ITAM_API_KEY_GUARD)  -> 403 if no view:itam / manage:assets / key scope
        v   route-level:  _require_itam_viewer                         -> 403
        v   verify_token_async  --> OVERWRITES ambient tenant with the TOKEN's tenant (platform-admin for Owner)
        |
        v   resolve_itam_tenant(request, user)
              owner-tier + session auth + X-Tenant-ID -> that tenant; else token tenant
              empty / "platform-admin" -> HTTP 400 (before any DB read)
              set_tenant_id(resolved)  (re-aligns DB wrapper; middleware finally-block resets)
        |
        +--> GET /api/itam/costs/summary ----------+
        +--> GET /api/itam/costs/assets (paged) ---+--> itam_cost_service
        +--> GET /api/itam/costs/assets/{id} ------+        1 x assets.find({tenantId,...}, projection)
        +--> GET /api/itam/kpis  (refactored) -----+        1 x asset_models.find({tenantId, id:{$in}})
        +--> POST /reports/prebuilt/asset_value ---+        1 x agents.find({tenantId, assetId:{$in}})   (cost routes only)
                                                            for each asset: compute_asset_cost(asset, model, now)
                                                                 -> compute_book_value (Phase 59, unchanged)
                                                            sort (book desc, null last, name/tag) -> paginate()
                                                            totals + coverage from the FULL list, never a page
        |
        v   dict -> JSON (integer cents, null when unknown)
```

### Recommended Project Structure
```
backend/
├── itam_cost_service.py        # NEW, pure: compute_asset_cost, load_*, build_costs, summarize, utc_now (no FastAPI import)
├── itam_tenant_scope.py        # NEW: resolve_itam_tenant(request, current_user) -> str
├── itam_cost_endpoints.py      # NEW: router prefix /api/itam/costs
├── itam_reporting_kpis.py      # MOD: _compute_asset_value_kpi -> shared function (316 lines, room)
├── itam_kpi_endpoints.py       # MOD: resolver (400 instead of 403-no-tenant)
├── itam_reporting_prebuilt.py  # MOD: _build_asset_value_rows -> shared function (476 lines: must shrink)
├── itam_reporting_filters.py   # MOD (optional, see Open Q3): _compute_finance_result (499 lines: must not grow)
├── itam_reporting_endpoints.py # MOD: resolver on prebuilt run/export
├── router_registry.py          # MOD: one _load line after itam_kpi_endpoints
└── catalogue_mounts_assets.py  # MOD: one MOUNTS entry (ITAM_API_KEY_GUARD)
components/itam/ItamKpiPanel.tsx, ITAMConsole.tsx ; App.tsx (prop) ; services/apiService.ts
backend/tests/test_itam_cost_service.py, test_itam_cost_endpoints.py, test_itam_cost_parity.py,
              test_itam_cost_isolation.py, test_itam_cost_scale.py
```

### Pattern 1: One pure per-asset function, one `now`, one status rule
**What:** `compute_asset_cost(asset, model_doc, now)` returns every field the three surfaces need; loaders and aggregation are separate. The KPI passes the `assets` list it already read (its projection already has `lifecycleStatus`, `modelId`, `purchaseCostCents`, `purchaseDate`) so there is no extra read.
**When to use:** all book-value figures in the platform from now on.
**Example (skeleton; new names are proposals, existing values quoted in the sections below):**
```python
# backend/itam_cost_service.py  - imports no FastAPI symbol (matches itam_reporting_kpis.py)
from datetime import datetime, timezone
from itam_finance_service import (
    REASON_NO_DEPRECIATION_POLICY, REASON_NO_PURCHASE_RECORD, compute_book_value,
)
from itam_models import DEFAULT_LIFECYCLE_STATUS, LifecycleStatus

INACTIVE_STATUSES = frozenset({LifecycleStatus.DISPOSED.value, LifecycleStatus.RETIRED.value})
REASON_UNREADABLE_DATE = "unreadable_purchase_date"      # NEW (proposal)

def utc_now() -> datetime:                                # the ONE patch point for tests
    return datetime.now(timezone.utc)

def _is_cents(v) -> bool:                                 # bool is an int subclass; floats must not pass
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0

def compute_asset_cost(asset, model_doc, now):
    status = asset.get("lifecycleStatus") or DEFAULT_LIFECYCLE_STATUS.value
    cost, date = asset.get("purchaseCostCents"), asset.get("purchaseDate")
    row = {"assetId": asset.get("id"), "lifecycleStatus": status,
           "purchaseCostCents": cost if _is_cents(cost) else None,
           "bookValueCents": None, "reason": None, "flags": []}
    row["priced"] = row["purchaseCostCents"] is not None           # D-11: 0 is priced
    if status in INACTIVE_STATUSES:                                 # D-03
        row["reason"] = status; return row
    if not row["priced"] or date is None:
        row["reason"] = REASON_NO_PURCHASE_RECORD; return row
    life = (model_doc or {}).get("usefulLifeYears"); salv = (model_doc or {}).get("salvageValueCents")
    if not (isinstance(life, int) and not isinstance(life, bool) and life > 0 and _is_cents(salv)):
        row["reason"] = REASON_NO_DEPRECIATION_POLICY; return row   # D-09
    try:
        r = compute_book_value(purchase_date=date, purchase_cost_cents=cost,
                               useful_life_years=life, salvage_value_cents=salv, now=now)
    except (ValueError, TypeError):                                 # TypeError: str date etc. (see Pitfall 3)
        row["reason"] = REASON_UNREADABLE_DATE; return row
    row["bookValueCents"] = r["bookValueCents"]; row["yearsElapsed"] = r["yearsElapsed"]
    # future-date flag: compare the same parsed date compute_book_value used (D-11)
    return row
```
Reason precedence is deliberate: lifecycle -> `no_purchase_record` -> `no_depreciation_policy_assigned` -> `unreadable_purchase_date`. It matches `get_asset_book_value` (cost or date `None` -> `no_purchase_record`; missing/invalid policy -> `no_depreciation_policy_assigned`) and gives every null-book-value row exactly one reason, so `valued + sum(reason counts) == total in scope` can be asserted as an invariant.

### Pattern 2: Summary shape (recommended; field names are discretion)
```
{ "tenantId", "computedAt", "includeDisposed": false,
  "purchaseTotal":  {"cents": int|null, "hasData": bool},   # null + false when no priced asset
  "bookValueTotal": {"cents": int|null, "hasData": bool},
  "coverage": {"total": n_in_scope, "priced": n, "valued": n,
               "excludedByLifecycle": n_disposed_or_retired_hidden,   # 0 when includeDisposed=true
               "reasons": {"no_purchase_record": n, "no_depreciation_policy_assigned": n,
                           "unreadable_purchase_date": n, "disposed": n, "retired": n,
                           "futurePurchaseDate": n},
               "possibleDuplicatePairs": n} }
```
`total` is the number of rows in scope so list rows add up to the summary (D-02). `disposed`/`retired` reasons are non-zero only when the filter is on. Future-date and duplicate are non-exclusive flags counted separately.

### Pattern 3: Endpoint list/detail
- `GET /summary`, `GET /assets?page=&page_size=&includeDisposed=&agentOnly=`, `GET /assets/{id}`; literal `summary` and `assets` segments cannot shadow each other.
- Order inside every handler: guard (403) -> `resolve_itam_tenant` (400) -> `get_database()` -> service. Resolve **before** `get_database()` so the 400 never depends on DB state.
- List: compute all rows, sort with `key=(book is None, -(book or 0), name or "", assetTag or "")`, then `paginate(rows, page, page_size)` from `pagination_utils`. Cap `page_size` with `Query(50, ge=1, le=100)` (the `/api/assets` cap).
- Detail: tenant-scoped `find_one({"tenantId": t, "id": asset_id})`, 404 for unknown **and** foreign ids (same body), one `asset_models.find_one`, one `agents.find` by `assetId`. A disposed asset requested by id returns 200 with `bookValueCents: null`, `reason: "disposed"` (recommended; see Open Q6).
- 500 handling: copy `itam_kpi_endpoints.get_itam_kpis` (log, generic `"Internal server error"`).

### Pattern 4: Tenant resolver (replaces the broken ambient assumption)
```python
# backend/itam_tenant_scope.py
from fastapi import HTTPException, Request, status
import rbac_defaults
from tenant_context import set_tenant_id

def resolve_itam_tenant(request: Request, current_user) -> str:
    tenant = current_user.tenant_id
    override = request.headers.get("X-Tenant-ID")
    # Same rule as tenant_middleware.py:196-205, but session-only: the middleware never saw a Bearer token for API keys
    if override and current_user.auth_source == "session" \
            and rbac_defaults.platform_tier(current_user.role) == "owner":
        tenant = override
    if not tenant or tenant == rbac_defaults.PLATFORM_TENANT_ID:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="Select a tenant: cost figures cover one organization at a time.")
    set_tenant_id(tenant)   # TenantMiddleware's finally-block resets it (tenant_middleware.py:161,219)
    return tenant
```
Call it from the handler body (not a sync `Depends`, which would run in a threadpool copy of the context and not propagate `set_tenant_id`). Share the owner rule with the middleware by extracting a tiny helper if the planner wants zero drift (middleware and resolver then call one function).

### Anti-Patterns to Avoid
- **Reading `get_tenant_id()` in the handler/resolver** - returns the token tenant, not the switcher choice (Pitfall 1).
- **Relying on the wrapper alone for scoping** - `_inject_tenant_id` returns the filter untouched for `platform-admin` (database.py:68-70). Put `{"tenantId": tenant_id}` in every `assets`, `asset_models`, `agents` filter.
- **Calling `get_asset_book_value` in a loop** - `find_one` on `asset_models` per call is N+1.
- **`@cached`, `finance_filtered`, `$lookup`, `* 100`, float sums, `db._db`** in cost code.
- **Adding code to `itam_reporting_prebuilt.py`/`itam_reporting_filters.py`** without removing more than you add (476/499 lines, 500 cap).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Depreciation | A new formula or "monthly" variant | `compute_book_value` verbatim | Phase 59 D-04 is the platform definition; any rollup variation breaks parity |
| Serial normalisation / junk placeholders | A new regex list | `seat_identity.normalize_serial` (strips, upper-cases, rejects `to be filled by o.e.m.`, `unknown`, `n/a`, all-same-character, ...) | It is what produced the agent asset's `hardwareKey` |
| Paging an in-memory list | Manual slice math + new envelope | `pagination_utils.paginate` | Same envelope as `/api/assets` |
| Auth + API-key scope narrowing | A cost-specific guard | `_require_itam_viewer` + `ITAM_API_KEY_GUARD` mount | Pitfall 15; Phase 76 parity test enforces the mount |
| Real-DB test database | Ad hoc DB creation | `tests/_mongo_test_db.mongo_db` | Throwaway name, drop-after, skip-if-down |
| Platform-role detection | String comparison on role names | `rbac_defaults.platform_tier(role)` | Handles every spelling/alias |

**Key insight:** every hard part (math, identity, paging, auth, test DB) already exists; the new work is wiring, one pure function, and refusing the three tenant-scoping traps below.

## Common Pitfalls

### Pitfall 1: The Owner's `X-Tenant-ID` is overwritten after the middleware (D-13's premise is wrong)
**What goes wrong:** the resolver reads `get_tenant_id()` and sees `platform-admin`; or reads the header correctly but leaves the ambient unset, so the wrapper does not scope and `db.assets.find({})` returns every tenant.
**Why it happens:** `verify_token_async` ends with `_set_tenant_id(tenant_id)` using the token's tenant (authentication_service.py:511; sync twin at :408). [VERIFIED: probe this session, `/home/azureuser/.../scratchpad/ctxprobe.py`: output `/probe/session ... "ambient":"platform-admin"`, `/probe/viewer ... "ambient":"platform-admin"`, `/probe/nodep ... "ambient":"tenant-b"`]
**How to avoid:** Pattern 4 (header read in the resolver, owner + session only, `set_tenant_id`) **and** explicit `tenantId` in each cost query. Test it end to end with the real `TenantMiddleware`.
**Warning signs:** Owner-with-header test returns another tenant's totals or 0 rows; the KPI tile for a Super Admin still blends after the change.

### Pitfall 2: `platform-admin` ambient skips the wrapper
**What goes wrong:** any reachable path with ambient `platform-admin` and no explicit filter reads all tenants (database.py:68-70: `if tenant_id == "platform-admin": return filter_query ...`).
**How to avoid:** the service raises `ValueError` for an empty or `platform-admin` `tenant_id` argument and always filters `{"tenantId": tenant_id}`. A unit test calls the service with a platform-admin-ambient wrapper and asserts only tenant A's rows come back.

### Pitfall 3: `compute_book_value` does not guard types
**What goes wrong:** a string `purchaseCostCents` raises `TypeError` (not `ValueError`), so the current KPI/report/`get_asset_book_value` would 500 on such a document; a float cost silently returns a float book value (`66667.5`); `True` is accepted as `useful_life_years`. [VERIFIED: ran the function this session: `bad ('2024-03-01', '100000', 3, 0) TypeError unsupported operand type(s) for -: 'str' and 'int'`; `bad ('2024-03-01', 100000.5, 3, 0) {'bookValueCents': 66667.5, ...}`; `bad ('2024-03-01', 100000, True, 0) {'bookValueCents': 0, 'yearsElapsed': 1, ...}`]
**How to avoid:** validate with `_is_cents` / positive-int-not-bool before the call and catch `(ValueError, TypeError)`; do **not** change `compute_book_value` itself (locked). Writes are validated (`Field(None, ge=0)` on `purchaseCostCents`) but CSV import and direct writes are not guaranteed to be.

### Pitfall 4: Book value can exceed purchase cost, and the whole-year step surprises
**What goes wrong:** with salvage greater than cost the floor at salvage lifts the book value above cost; a recorded test that "improves" this breaks Phase 59 parity. [VERIFIED: ran: `salvage>=cost {'bookValueCents': 150000, 'yearsElapsed': 2, 'annualDepreciationCents': -16667}` for cost 100000, salvage 150000, life 3]
**How to avoid:** pin it in the golden table as the platform definition; do not clamp in the rollup.

### Pitfall 5: KPI `hasData` and zero semantics change under D-10
**What goes wrong:** today `_compute_asset_value_kpi` returns `totalBookValueCents: 0` when assets exist but none is valued (test asserts `== 0`, test_itam_reporting_kpis.py:123). D-14 needs the tile to show "Not tracked", so the KPI must return `null` for the total while keeping `hasData: True` (assets exist; the status pie is still meaningful). If `hasData` were set False the tile would say "No data yet" and never reach the "Not tracked" copy.
**How to avoid:** KPI `hasData` = tenant has assets; add `valuedCount` and `inScopeAssetCount`; keep `assetCount` = all assets (pie total, back-compatible); redefine `withoutPolicyCount` as in-scope not-valued. The summary route has its own per-total `hasData`.

### Pitfall 6: Platform Billing gets 403, not 400
**What goes wrong:** a test written from D-15 ("Support and Billing always 400") fails for Billing. `platform_billing` holds only `manage:pending_agents`, `manage:tenant_license`, `view:audit_log`, `view:platform_alerts`, `view:platform_cost`, `view:profile`, `view:tenants` (rbac_defaults.py:149-152) - no `view:itam`. [VERIFIED: `probe_real_app` this session on `/api/itam/kpis`: `('platform_support', 500), ('platform_billing', 403), ('Super Admin', 500)` - 500 is only the probe's unreachable DB, i.e. the handler was reached]
**How to avoid:** assert Support -> 400, Billing -> 403 (both satisfy the intent "never a blended total"). See Open Q1.

### Pitfall 7: Router not added to the catalogue mount map
**What goes wrong:** `test_assets_slice_parity` fails (`expected catalogue_guard("itam", ...)`) because `itam_cost_endpoints` has no mount guard. Add `("itam_cost_endpoints", "router"): ITAM_API_KEY_GUARD,` next to line 55 of `catalogue_mounts_assets.py`; no manifest edit (the `itam` catalogue already owns `/api/itam`). Router-level guard runs before the route's `_require_itam_viewer`, both yielding 403 before the resolver's 400.

### Pitfall 8: Existing tests encode the old behaviour
Must change: `test_itam_reporting_kpis.py:123` (`totalBookValueCents == 0` -> `None`), `:440-447` (`no tenant id` expects 403 -> 400), any assertion on `withoutPolicyCount`/`assetCount`; `test_itam_reporting_prebuilt.py` (rows for disposed/retired must be absent; sort tie-break). The `_boom(db, tenant_id)` monkeypatch at `test_itam_reporting_kpis.py:~455` pins the `compute_itam_kpis(db, tenant_id)` signature - keep it.

### Pitfall 9: Two `now` values / midnight flake
KPI creates `now` twice (`compute_itam_kpis` and again inside `_compute_asset_value_kpi`). Funnel every cost computation through `itam_cost_service.utc_now()`; tests `monkeypatch.setattr(itam_cost_service, "utc_now", lambda: FIXED)` so the parity test cannot flake on an anniversary day.

### Pitfall 10: Agent join traps
- Several `agents` docs may point at one `assetId`; pick deterministically (latest `lastSeen`) and expose `agentCount`; never multiply asset rows.
- The tenant-isolated `agents.find` hides `Pending`/`Rejected` agents (database.py:45), so such an asset shows no agent - acceptable, document it.
- Use `agents.status`/`lastSeen`, not the asset's `agentStatus` (heartbeat stamps `"Online"`, agent_heartbeat_endpoints.py:266).
- "Agent endpoints only" filter = has at least one joined agent doc; do not filter on the asset's `agentId`/`hardwareKey`.

### Pitfall 11: Duplicate detection scope
Agent side = asset whose `hardwareKey` starts with `serial:`; hand-entered side = asset with **no** `hardwareKey` whose `normalize_serial(serialNumber)` equals the key's value (heartbeat also stamps `serialNumber` on agent assets, so exclude hardware-keyed assets from the manual side). `uuid:`/`mac:` keys never participate (weak identity). Both rows keep their own cost; the summary counts pairs.

### Pitfall 12: Frontend threading is wider than D-14 states
`ITAMConsole` receives only `tenants` and `isSuperAdminView`; the Owner's selection is `viewingTenantId` in `App.tsx:346` and is not passed down. `fetchItamKpis()` takes no argument and the tile test mocks `../../services/apiService` with only `fetchItamKpis` (ITAMKpiPanel.test.tsx:15-17). D-14 therefore needs `App.tsx` (pass `viewingTenantId`) and `ITAMConsole.tsx` (forward it) in addition to the two named files. Separately, once D-13 puts the 400 on the report run/export routes, the Super Admin's Reports tab gets a 400 whether or not a tenant is selected, because `runItamPrebuiltReport`/`generateItamReport` send no `tenantId` (see Open Q2).

## Code Examples

### Endpoint wiring (pattern from `itam_kpi_endpoints.py`, quoted guard)
```python
# backend/itam_cost_endpoints.py
router = APIRouter(prefix="/api/itam/costs", tags=["ITAM Costs"])

@router.get("/summary", response_model=Dict[str, Any])
async def get_cost_summary(
    request: Request,
    includeDisposed: bool = Query(False),
    current_user: TokenData = Depends(_require_itam_viewer),   # imported from itam_asset_endpoints, never copied
):
    tenant_id = resolve_itam_tenant(request, current_user)      # 400 before any DB access
    db = get_database()
    try:
        return await build_cost_summary(db, tenant_id, include_inactive=includeDisposed)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("ITAM cost summary failed for tenant %s: %s", tenant_id, exc)
        raise HTTPException(status_code=500, detail="Internal server error")
```
Registration: `_load(app, "itam_cost_endpoints", "router")` after the `itam_kpi_endpoints` line (router_registry.py:120) and the MOUNTS entry in Pitfall 7.

### Loader pattern (explicit tenantId, one read per collection)
```python
assets = await db.assets.find({"tenantId": tenant_id}, PROJECTION).to_list(length=None)
model_ids = sorted({a["modelId"] for a in assets if a.get("modelId")})
models = {m["id"]: m for m in await db.asset_models.find(
    {"tenantId": tenant_id, "id": {"$in": model_ids}},
    {"_id": 0, "id": 1, "usefulLifeYears": 1, "salvageValueCents": 1}).to_list(length=None)} if model_ids else {}
agents = await db.agents.find(
    {"tenantId": tenant_id, "assetId": {"$in": [a["id"] for a in assets]}},
    {"_id": 0, "id": 1, "assetId": 1, "hostname": 1, "status": 1, "lastSeen": 1}).to_list(length=None)
```
PROJECTION must add `hardwareKey`, `serialNumber` (duplicates) to the KPI projection's fields (`id, assetTag, name, lifecycleStatus, modelId, purchaseCostCents, purchaseDate`). A single `$in` of ~20k asset ids is roughly 20k x ~30 bytes, far below the 16 MB BSON limit [ASSUMED estimate - the scale test measures it]; if it proves slow, fall back to `{"tenantId": t, "assetId": {"$exists": True, "$ne": None}}` (bounded by agent count) - both satisfy D-06's no-per-asset-query intent.

### Golden-value table (outputs produced by running `compute_book_value` this session; tuple = purchase_date, cost, life, salvage, now)
| Case | Inputs | `bookValueCents` / `yearsElapsed` |
|------|--------|-----------------------------------|
| life=1, day before anniversary | `"2024-03-01",100000,1,10000`, 2025-02-28 | 100000 / 0 |
| life=1, on anniversary | same, 2025-03-01 | 10000 / 1 |
| salvage > cost | `"2024-03-01",100000,3,150000`, 2026-06-01 | 150000 / 2 (exceeds cost) |
| salvage == cost | `"2024-03-01",100000,3,100000`, 2026-06-01 | 100000 / 2 |
| cost = 0 | `"2024-03-01",0,3,0`, 2026-06-01 | 0 / 2 |
| leap-day purchase, 28 Feb | `"2024-02-29",120000,4,0`, 2025-02-28 | 120000 / 0 |
| leap-day purchase, 1 Mar | same, 2025-03-01 | 90000 / 1 |
| anniversary boundary, day before | `"2023-06-15",150000,3,15000`, 2024-06-14 | 150000 / 0 |
| anniversary boundary, on day | same, 2024-06-15 | 105000 / 1 |
| future purchase date | `"2030-01-01",100000,3,10000`, 2026-11-16 | 100000 / 0 |
| integer division | `"2020-01-01",100001,3,0`, 2026-11-16 | 2 / 3 (annual 33333) |
| past end of life | `"2015-01-01",100000,3,10000`, 2026-11-16 | 10000 / 3 |
| `Z`-suffixed datetime | `"2024-03-01T00:00:00Z",100000,2,0`, 2026-11-16 | 0 / 2 |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Three (actually four) copies of the book-value loop (KPI, asset-value report, `get_asset_book_value`, custom builder `_compute_finance_result`) | One pure `compute_asset_cost` | This phase | Parity enforceable by test |
| KPI counts every lifecycle status in money | Disposed/Retired excluded from book value (D-01/D-04) | This phase | Visible tile drop for tenants with such assets |
| Tile shows `$0.00` for "nothing valued" | `null` + "Not tracked" | This phase | Removes a fabricated zero |

**Deprecated/outdated:** CONTEXT's note that the report loop is "the third copy" undercounts: `itam_reporting_filters.py:269-305` is a fourth (custom report "Book Value" column).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | "Priced" = valid non-negative integer `purchaseCostCents` regardless of whether a purchase date exists; a cost-without-date asset counts in the purchase total but has book value `null`, reason `no_purchase_record` | Pattern 1/2 | Purchase total differs from a stricter "cost AND date" reading; the report (which lists only cost+date assets) and cost list populations differ slightly |
| A2 | New reason/flag strings: `unreadable_purchase_date`, `disposed`, `retired`, `futurePurchaseDate`, `possibleDuplicate` | Pattern 1/2 | Cosmetic; Phase 80 UI/export will key on them, so confirm before 80 |
| A3 | A single `agents.assetId $in` with ~20k ids is acceptable on this VM; 20k-asset request completes within a few seconds | Loader, Validation | Needs the fallback agent query or a looser timing bound; measured by the scale test |
| A4 | Apply the 400 resolver to **both** prebuilt run/export routes (all report keys), not only `asset_value` | Pattern 4 / Open Q2 | Other prebuilt reports also 400 for a Super Admin with no tenant (behaviour change beyond asset value) |
| A5 | `GET /costs/assets/{id}` for a disposed/retired asset returns 200 with null book value and its reason | Pattern 3 | A 404 reading would hide a legitimately requested record |
| A6 | Header override is honoured only for session auth (`auth_source == "session"`), matching the middleware which acts only on a Bearer JWT | Pattern 4 | An Owner-role API key could not choose a tenant (no way to today either) |
| A7 | Custom report builder's finance column (`itam_reporting_filters._compute_finance_result`) should call the shared function for its value but keep listing rows regardless of status | Open Q3 | If left alone, a fourth copy can drift and a disposed asset shows a depreciated value in custom reports |
| A8 | 400 detail copy "Select a tenant: cost figures cover one organization at a time." | Pattern 4 | Wording only |

## Open Questions

1. **D-15 says Billing "always 400"; the guard gives 403.**
   - What we know: billing lacks `view:itam` (rbac_defaults.py:149-152); probe confirmed 403. Support and Owner reach the resolver.
   - What's unclear: whether the user wants Billing to see 400 (would require granting `view:itam`, widening a role - contradicts D-15's own "not part of this phase").
   - Recommendation: keep 403 for Billing, 400 for Support/Owner-without-tenant; word the isolation test accordingly and note it in the plan.

2. **D-13 breaks the Super Admin's Reports tab; D-14 says "no other UI work".**
   - What we know: `runItamPrebuiltReport` and `generateItamReport` send no `tenantId`; after D-13 they 400 for every Owner (selected tenant or not); `itamThrow` surfaces the `detail` text.
   - Recommendation: thread `viewingTenantId` from `App.tsx` -> `ITAMConsole` -> `ItamKpiPanel` (required by D-14) **and** pass `{ tenantId }` in those two report calls (two small signature additions). If the user holds D-14 strictly, accept the 400 + detail message for Owners on the Reports tab until Phase 80.

3. **Custom report builder's "Book Value" column (fourth copy).**
   - Recommendation: replace the inline compute in `_compute_finance_result` with `compute_asset_cost(...)["bookValueCents"]` (net line reduction; file is at 499), leave its row selection untouched, add one parity assertion. Decide whether a Disposed asset in a custom report should show `null` (follows D-03) - recommended yes.

4. **KPI `assetCount` meaning.** Recommendation: keep it = all assets (pie total), add `inScopeAssetCount` and `valuedCount`; tile line "Valued X of Y assets" uses those two.

5. **Does an Owner with an `X-Tenant-ID` naming a non-existent tenant get 400/404 or an empty summary?** Existing switcher behaviour validates nothing. Recommendation: empty summary with `hasData: false` (no tenant-existence oracle); `platform-admin` as the header value -> 400.

6. **Detail route for inactive assets** - see A5.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python venv | backend + tests | yes | 3.12.3 | - |
| pytest / pytest-asyncio | backend tests | yes | 9.1.1 / 1.4.0 | - |
| mongod (local, `127.0.0.1:27017`) | isolation, parity, scale tests | yes (active) | 8.0.34 | `mongo_db` fixture skips; a skipped isolation test is **not** an acceptable phase gate - run it |
| Node / npx / vitest | frontend tests, build | yes | 20.20.2 / 5.0.0 | - |
| Redis | not used by cost routes | n/a | - | - |

**Missing dependencies:** none. **Deploy note:** backend runs from the checkout and UI publish are the user's actions (project memory); the phase plan ends at committed + green tests.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 + pytest-asyncio (auto mode); Vitest 5.0.0 |
| Config file | repo-root `pytest.ini` (asyncio_mode = auto); `vitest` via package scripts (`workflow.test_command: npx vitest run src/__tests__`) |
| Quick run command | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_service.py backend/tests/test_itam_cost_endpoints.py -q -p no:cacheprovider` (run from repo root) |
| Full phase command | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_service.py backend/tests/test_itam_cost_endpoints.py backend/tests/test_itam_cost_parity.py backend/tests/test_itam_cost_isolation.py backend/tests/test_itam_cost_scale.py backend/tests/test_itam_reporting_kpis.py backend/tests/test_itam_reporting_prebuilt.py backend/tests/test_itam_reporting_builder.py backend/tests/test_itam_finance_bookvalue.py backend/tests/test_catalogue_slice_assets.py -q -p no:cacheprovider` |
| Frontend | `npx vitest run src/__tests__/ITAMKpiPanel.test.tsx src/__tests__/ITAMConsole.test.tsx` and `npm run build` (repo root) |

Baseline: the three existing suites that this phase edits (`test_itam_reporting_kpis`, `_prebuilt`, `test_itam_finance_bookvalue`) currently pass, 55 tests in 2.1 s. [VERIFIED: run this session]

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| COST-01 | Golden table satisfied by `compute_asset_cost`; KPI total == report column sum (parsed) == summary book total == per-asset `/book-value` for the same seeded tenant under one patched `utc_now` | unit + real-Mongo | `pytest backend/tests/test_itam_cost_service.py backend/tests/test_itam_cost_parity.py` | no - Wave 0 |
| COST-02 | Unpriced -> `null` (never 0); `hasData:false` when nothing priced/valued; `valued + sum(reasons) == total` invariant; $0 price priced; type-garbage (str/float cost) -> unreadable, never 500 | unit + route | `pytest backend/tests/test_itam_cost_service.py backend/tests/test_itam_cost_endpoints.py` | no - Wave 0 |
| COST-03 | Paged list adds up to summary; agent rows via `agents.assetId` only; multi-agent asset single row; duplicate pairs marked, both counted; sort order; `agentOnly`; detail 404 for foreign id | route + real-Mongo | `pytest backend/tests/test_itam_cost_endpoints.py backend/tests/test_itam_cost_isolation.py` | no - Wave 0 |
| COST-06 | Disposed/retired out of lists and both totals by default; `includeDisposed` adds purchase total + rows with null book + reason; archived/broken stay; KPI pie still counts all statuses; report drops them | unit + parity | `pytest backend/tests/test_itam_cost_service.py backend/tests/test_itam_cost_parity.py backend/tests/test_itam_reporting_kpis.py backend/tests/test_itam_reporting_prebuilt.py` | partly (KPI/prebuilt edits) |
| COST-07 | 403 without `view:itam`; API-key scope narrowing (`view:itam` ok, `manage:assets` ok, `view:assets` 403); 400 for Owner without header, Support 400, Billing 403; Owner + header sees only that tenant (real `TenantMiddleware`); tenant A never sees B on summary/list/detail/KPI/report; module source has no `$lookup`, no `cached`, no `finance_filtered` | route + real-Mongo + static | `pytest backend/tests/test_itam_cost_isolation.py backend/tests/test_catalogue_slice_assets.py` | no - Wave 0 (+ extend slice test) |
| Scale | 20k-asset tenant: <= 3 collection reads (assert by counting `find` calls) and wall-clock under a generous bound | real-Mongo | `pytest backend/tests/test_itam_cost_scale.py` | no - Wave 0 |
| D-14 | Tile: "Not tracked" when total null; "Valued X of Y assets"; "Select a tenant" when Owner has none; `fetchItamKpis(tenantId)` passes `X-Tenant-ID`; prop threading | vitest | `npx vitest run src/__tests__/ITAMKpiPanel.test.tsx src/__tests__/ITAMConsole.test.tsx` | files exist, extend |

### Sampling Rate
- **Per task commit:** the quick command (service + endpoints), plus the file's own existing suite when a refactor touches KPI/report/builder.
- **Per wave merge:** the full phase command, then `npx vitest run src/__tests__/ITAMKpiPanel.test.tsx src/__tests__/ITAMConsole.test.tsx` when the frontend wave lands.
- **Phase gate:** full phase command + `npm run build` + `npx vitest run src/__tests__` green before `/gsd-verify-work`; confirm the isolation and parity tests actually ran (not skipped).

### Wave 0 Gaps
- [ ] `backend/tests/test_itam_cost_service.py` - golden table, reason precedence invariant, type guards, INACTIVE rule, duplicates, serial junk, sort, `platform-admin` argument refused, static no-`$lookup`/`cached` scan (REQ COST-01/02/03/06/07)
- [ ] `backend/tests/test_itam_cost_endpoints.py` - mocked-guard route tests (pattern: `_make_kpi_app` in `test_itam_reporting_kpis.py`), pagination, filters, 404
- [ ] `backend/tests/test_itam_cost_parity.py` - three-way parity (KPI JSON, report rows parsed with `Decimal`, summary) over one seeded tenant incl. disposed/retired/no-policy/future/garbage rows; also `compute_asset_cost` == `get_asset_book_value` route body for each seeded asset
- [ ] `backend/tests/test_itam_cost_isolation.py` - real Mongo + real `TenantMiddleware` + real `TenantIsolatedDatabase(mongo_db)` patched into the endpoint modules' `get_database`; tokens from `create_access_token` with `mfa_verified: True` (as in the probe); the Owner-header regression for Pitfall 1; Support 400 / Billing 403
- [ ] `backend/tests/test_itam_cost_scale.py` - 20k assets via `insert_many`, spy counting `find` calls, soft time bound
- [ ] Extend `backend/tests/test_catalogue_slice_assets.py` - probes for `/api/itam/costs/summary` (nobody 403, `itam_viewer` allowed, API-key scopes); `test_assets_slice_parity` then covers the mount automatically
- [ ] Update `test_itam_reporting_kpis.py` (lines 123, 440-447), `test_itam_reporting_prebuilt.py` per Pitfall 8
- Framework install: none.

## Security Domain

`security_enforcement` is enabled (absent = enabled); ASVS level 1, block on high. [VERIFIED: `.planning/config.json` `security_enforcement: true`, `security_asvs_level: 1`, `security_block_on: "high"`]

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | inherited | JWT / API key via `get_current_user_or_api_key` (unchanged) |
| V3 Session Management | inherited | Existing token revocation; nothing new |
| V4 Access Control | **yes** | `_require_itam_viewer` + `ITAM_API_KEY_GUARD` mount; `resolve_itam_tenant`; explicit `tenantId` filters; 404 (not 403) for foreign asset ids |
| V5 Input Validation | yes | `Query(..., ge=1, le=100)` on paging, boolean filters typed by FastAPI; no user text reaches a Mongo operator; asset id used only as an equality value |
| V6 Cryptography | no | none introduced |
| V7/V8 Errors & data protection | yes | generic 500 detail (T-72-10 precedent), financial data only to `view:itam`/`manage:assets` holders; Phase 76 already strips finance from `/api/assets*` |

### Known Threat Patterns for FastAPI + Mongo multi-tenant read APIs

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cross-tenant read via `platform-admin` wrapper bypass (BOLA at tenant level) | Information Disclosure | Resolver 400s on `platform-admin`/empty; service refuses such an argument; explicit `tenantId` in every filter; real-Mongo two-tenant test |
| Owner override silently ignored then blended (Pitfall 1) | Information Disclosure | Header read in the resolver + `set_tenant_id`; end-to-end middleware test |
| Non-owner spoofing `X-Tenant-ID` | Elevation of Privilege | Honour only when `platform_tier(role) == "owner"` and session auth; test with a tenant admin sending another tenant's id |
| API key with narrow scope reads cost | Elevation of Privilege | Catalogue guard + `_require_itam_viewer` scope check; scope-narrowing test |
| IDOR on `/costs/assets/{id}` | Information Disclosure | Tenant-scoped `find_one`; identical 404 for unknown and foreign ids |
| Resource exhaustion (full-tenant recompute per page request) | Denial of Service | One projected read per collection, `page_size` capped, scale test; no `@cached` allowed (leak risk), so accept recompute cost |
| Stack trace / internals in errors | Information Disclosure | Catch-all -> `"Internal server error"` |
| Cost fields leaking to non-ITAM roles | Information Disclosure | Guard on every route; cost routes do not use `finance_filtered` (that decorator strips fields; it belongs to `/api/assets*`) |

## Sources

### Primary (HIGH confidence) - in-repo, read or executed this session
- `.planning/phases/78-organization-endpoint-cost-api/78-CONTEXT.md` (all of it), `.planning/REQUIREMENTS.md` (COST-01..07 lines 152-158), `.planning/config.json`
- `backend/itam_finance_service.py:47-48,70-115` (reason constants, `compute_book_value`); executed against 13 golden cases and 4 bad-input cases
- `backend/itam_reporting_kpis.py` (all), `itam_kpi_endpoints.py` (all), `itam_reporting_prebuilt.py:96-189`, `itam_reporting_filters.py:267-305`, `itam_reporting_endpoints.py` (all), `itam_finance_endpoints.py` (all)
- `backend/itam_asset_endpoints.py:38-93` (guards), `catalogue_mounts_assets.py` (all; line 55 mount, line 20 `ITAM_READ`), `catalogue_guards.py:60-160`, `router_registry.py:106-121`
- `backend/tenant_middleware.py:127-219`, `authentication_service.py:343-410,440-514,523-526`, `api_key_auth.py:287-300`, `tenant_context.py`, `database.py:45-155,476-483`, `rbac_defaults.py:24-36,126-152,286-292`, `auth_types.py`
- `backend/asset_identity.py`, `seat_identity.py:14-33,77-85`, `agent_heartbeat_endpoints.py:152-158,256-309`, `asset_endpoints.py:63-106,371-430`, `itam_models.py:39-58,100-160,270-320`, `pagination_utils.py`
- Frontend: `components/itam/ItamKpiPanel.tsx`, `ITAMConsole.tsx:1-140`, `services/apiService.ts:300-345,5977-6004,6100-6163`, `App.tsx:346,1734,1922`, `src/__tests__/ITAMKpiPanel.test.tsx:1-80`
- Tests/infra: `backend/tests/_mongo_test_db.py`, `conftest.py`, `itam_reporting_test_support.py`, `test_itam_reporting_kpis.py`, `test_catalogue_slice_assets.py`, `_catalogue_parity.py`, `_route_walk.py`, `test_autonomous_ops_isolation.py` (two-tenant precedent)
- `.planning/milestones/v4.2-research/PITFALLS.md` Pitfalls 8-13, 15, 18, 19; `ARCHITECTURE.md` Feature 2
- Executed probes (scratchpad): `/tmp/claude-1000/-home-azureuser-enterprise-omni-agent-ai-platform/36148a2d-b952-441f-b9d8-f06cc2d77d38/scratchpad/ctxprobe.py` (ambient tenant after auth), `golden.py` (golden values), `probe_roles.py` (role -> status on `/api/itam/kpis`)

### Secondary / Tertiary
- None. No external documentation, Context7 or web source was needed: the phase introduces no external library, and every behaviour claimed was observed in the repo or by execution. The research-plan/classify-confidence seams were therefore not used.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - nothing new; versions read from the venv.
- Architecture: HIGH - the tenant-context finding is reproduced empirically; shared-function design follows the existing KPI pattern.
- Pitfalls: HIGH for 1-9, 11 (executed/read); MEDIUM for performance (A3, measure in the scale test).

**Research date:** 2026-11-16
**Valid until:** 2026-12-16 (in-repo; re-check `authentication_service.verify_token_async` and `tenant_middleware` if either changes - Pitfall 1 depends on them)
