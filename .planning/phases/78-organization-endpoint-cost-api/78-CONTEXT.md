# Phase 78: Organization & Endpoint Cost API - Context

**Gathered:** 2026-11-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Read-only cost API for one tenant at a time: `GET /api/itam/costs/summary` (total purchase cost, current depreciated book value, coverage), `GET /api/itam/costs/assets` (paginated per-asset cost, agent endpoints included) and `GET /api/itam/costs/assets/{id}`. Every figure comes from one shared per-asset computation that the ITAM KPI tile and the "Asset value" pre-built report also call, proven by a parity test and a golden-value table. Disposed and Retired assets leave current book value by default, with the same rule in the KPI, the report and the cost view. Every cost route needs `view:itam`, a real tenant (400 otherwise) and a two-tenant isolation test. Requirements: COST-01, COST-02, COST-03, COST-06, COST-07.

**In this phase as well (from discussion):** the KPI route and the Asset value report adopt the same tenant rule and the same Disposed/Retired rule, and the existing ITAM KPI tile gets a small fix so it renders the new response correctly (D-13, D-14).

**Not in this phase:** license cost field and per-endpoint license allocation (Phase 79, COST-04/05); the Costs tab, coverage banner, shared currency formatting and export (Phase 80, COST-08); consumable/component cost, currency/FX, TCO/forecasting, and an MSP cross-tenant cost rollup (COST-F1..F4).

</domain>

<decisions>
## Implementation Decisions

### Carried forward (already locked, not re-asked)
- Cost routes are gated by `view:itam` through the canonical `_require_itam_viewer` imported from `backend/itam_asset_endpoints.py` (accepts `view:itam` or `manage:assets`, role check first, then API-key scope narrowing). Never a copied guard (v4.2 research Pitfall 15; the duplicate in `itam_catalog_endpoints.py` is a known drift case), never `view:finops`.
- Phase 76 D-04/D-10 already strip purchase cost, book value, warranty fields and `supplierId` from `/api/assets*` for callers without `view:itam`; nothing to redo here.
- Compute at read time: no stored rollups, no snapshot job, no `$lookup`, no `@cached` on cost routes (REQUIREMENTS v4.2 out-of-scope table, COST-07).
- Integer cents end to end, one implicit currency per tenant; no `* 100` / `/ 100` and no float sums in new cost code. PO/request float-dollar fields are never rolled into cost totals.
- Depreciation stays the Phase 59 D-04 definition in `itam_finance_service.compute_book_value` (whole-year steps on the purchase anniversary, integer division, floor at salvage). The rollup must not "improve" it.
- Phase 72 decision: every report/KPI reuses the owning surface's computation verbatim. One `now` per request for the whole rollup.

### Disposed & retired rule (COST-06)
- **D-01:** Only `disposed` and `retired` leave the current book-value total. `archived` and `broken` stay in (still owned, still worth something); `deployable` and `deployed` stay in. An asset with no `lifecycleStatus` reads as `deployable` (existing read-time default).
- **D-02:** One explicit filter (for example `includeDisposed=true`; Claude names it) works the same on the summary and the per-asset list. Without it, Disposed/Retired assets are absent from the list and from both totals, so the list rows add up to the summary. With it, the summary's purchase total includes their purchase cost (the "historical purchase total") and the list returns their rows carrying their status.
- **D-03:** A Disposed/Retired row shown through the filter has book value `null` with reason `disposed` or `retired`, never `0` and never a depreciated "as if still owned" value. Its purchase cost is still shown. Book-value totals never include them, with or without the filter.
- **D-04:** The existing "Asset value" pre-built report (`itam_reporting_prebuilt._build_asset_value_rows`) follows the same default and drops Disposed/Retired rows, so tile, report and cost view agree row for row (roadmap SC3). The KPI tile's lifecycle-status pie chart keeps counting every status, because it is an inventory count, not money. **Visible change:** a tenant with disposed or retired assets sees the "Total Asset Value" tile drop.

### Endpoint list contents (COST-03)
- **D-05:** `/costs/assets` lists every tenant asset by default (manual ITAM records and agent-discovered computers, same population and count as the Assets page), with an "agent endpoints only" filter. Unpriced agent computers appear as "not tracked" rows, so the coverage gap stays visible.
- **D-06:** For an asset that is an agent endpoint (linked only via `agents.assetId`, never by hostname), the row carries the agent id, hostname, status and last seen, read from the `agents` collection in one batched tenant-scoped `$in` query. Not from the asset's own `agentStatus`: the heartbeat stamps "Online" there and nothing sets it back.
- **D-07:** When an agent-discovered asset and a hand-entered asset match on serial number (the agent asset's `hardwareKey` `serial:<value>` against the manual asset's `serialNumber`), both rows carry a "possible duplicate" marker naming the other asset, and the summary reports a duplicate count. Never auto-merge and never move cost between rows; both rows still count.
- **D-08:** Default order is book value high to low, with "not tracked" rows last and name/asset tag as a stable tiebreak (the same order as the Asset value report). Book value is not stored, so the per-asset set is computed for the whole tenant and then paged. Totals are never computed from one page.

### Missing or partial cost data (COST-02)
- **D-09:** An asset with a purchase price but no usable depreciation policy (no model, model without `usefulLifeYears`/`salvageValueCents`, or inputs that raise `ValueError`) counts in the purchase total, and its book value is `null` ("not tracked") with the existing reason `no_depreciation_policy_assigned`, left out of the book-value total. This is the same as the KPI and `GET /api/assets/{id}/book-value` today.
- **D-10:** Coverage is two counts plus a per-reason breakdown: "priced" (counts toward the purchase total) of total, "valued" (counts toward book value) of total, and counts per reason: no purchase record, no depreciation policy, unreadable date, disposed/retired, future purchase date, possible duplicate. A total with no contributing asset is `null` with `hasData: false` (the KPI convention), never `0`.
- **D-11:** A $0 purchase price is priced (donated or built in-house) and distinct from no price. A future purchase date keeps today's math (full price, since years elapsed clamps to 0) so every surface agrees, and the asset is flagged `futurePurchaseDate` and counted in the breakdown.
- **D-12:** The asset-level `useful_life_years` / `salvage_value` (float dollars) fields on the Asset models stay ignored. The model-level policy is the only depreciation source, exactly as `get_asset_book_value` resolves it today. No screen writes those fields.

### Tenant rule and the KPI tile (COST-07)
- **D-13:** One shared tenant resolver serves the cost routes, the KPI route (`/api/itam/kpis`) and the Asset value report run/export routes. It takes the request's tenant context (a Platform Owner's `X-Tenant-ID` switcher choice, otherwise the caller's own tenant) and returns **400** when that context is `platform-admin` or empty, so no route ever returns a total blended across tenants. Today a Super Admin's tile sums every tenant's assets, because `fetchItamKpis()` sends no `X-Tenant-ID` and the route accepts `platform-admin` as a tenant. — **Reversibility:** reversible — one helper; reverting restores the blended Super Admin tile.
- **D-14:** Small tile fix in this phase, in `components/itam/ItamKpiPanel.tsx` and `fetchItamKpis` only: show "Not tracked" instead of `$0.00` when the book value is null, add a "Valued X of Y assets" line, send the Super Admin's selected tenant with the KPI request, and show a "Select a tenant" state when none is chosen. No other UI work; the Costs tab stays in Phase 80.
- **D-15:** Only the Platform Owner tier can choose a tenant (the existing `X-Tenant-ID` rule in `backend/tenant_middleware.py`). Platform Support and Platform Billing always get 400 on these routes; widening the override is not part of this phase.
- **D-16:** ITAM API keys may read the cost routes exactly as they read `/book-value` and `/kpis`: the owner's role first, then the key's scopes must allow `view:itam` or `manage:assets`; anything else gets 403. A scope-narrowing test proves it. — **Reversibility:** costly — once integrators read cost data through API keys, withdrawing it breaks their calls.

### Claude's Discretion
- Where the shared per-asset computation lives (research suggested a pure `backend/itam_cost_service.py` with `db` passed in, one projected `assets` find, one `asset_models` `$in`, one `agents` `$in`, a Python loop) and how the KPI and the report are refactored onto it.
- Response field names and shape, reason-code strings for the new reasons (disposed, retired, future date, duplicate), filter parameter names, and the 404 for an asset id outside the tenant.
- Pagination style (`PaginationParams` page/page_size is the existing convention; keyset is optional), as long as D-08's full-set sort holds and totals never depend on the page.
- Serial-number normalisation for D-07 (case, whitespace, placeholder serials such as "To Be Filled By O.E.M." that must not match).
- Golden-value table cases (research list: life=1, salvage >= cost, cost=0, leap-day purchase, anniversary boundary, future date) and the large-tenant timing test (research suggested about 20k assets).
- Exact copy for the D-14 tile states (subject to existing ITAM i18n in `itamI18n.tsx`).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Scope and requirements
- `.planning/ROADMAP.md` § "Phase 78: Organization & Endpoint Cost API": goal and the 5 success criteria.
- `.planning/REQUIREMENTS.md` § "Paused milestone v4.2", "2. Asset Costing": COST-01/02/03/06/07, v2 deferrals COST-F1..F4, the v4.2 out-of-scope table.

### Research (v4.2, archived)
- `.planning/milestones/v4.2-research/SUMMARY.md`: Feature 2 design (`itam_cost_service.py`, `itam_cost_endpoints.py`), open decisions D-1..D-3 (D-2 and D-3 now settled above).
- `.planning/milestones/v4.2-research/PITFALLS.md`: Pitfalls 8 (tenant leakage: `$lookup`, `@cached`, raw handles), 9 (depreciation math and policy source), 10 (null vs 0, coverage, agent vs manual duplicates), 11 (currency), 12 (double counting), 13 (performance: batched reads, no N+1, never paginate a total), 15 (guard drift and API-key scope), 18 (rollup drift), 19 (UTC, one `now`).
- `.planning/milestones/v4.2-research/ARCHITECTURE.md`, `.planning/milestones/v4.2-research/FEATURES.md`: cost service/endpoint layout and feature table T2-01..12.

### Prior phase decisions
- `.planning/phases/76-catalogue-manifest-backend-route-enforcement/76-CONTEXT.md`: D-03 (`manage:X` satisfies `view:X` for reads), D-04/D-10 (finance-field strip on `/api/assets*`), D-05 (deny-by-default parity test plus gap ledger).
- `.planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-CONTEXT.md`: D-11 closure in `/me`, D-17 (Super Admin with no tenant selected).
- `.planning/phases/75-permission-resolver-single-source-of-truth/75-CONTEXT.md`: one resolver, super-admin handling.
- `.planning/PROJECT.md` Key Decisions: Phase 59 D-04 (depreciation computed at read time, never stored), Phase 72 (reuse the owning computation verbatim).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/itam_finance_service.py` `compute_book_value(...)`: the single depreciation function; `REASON_NO_PURCHASE_RECORD`, `REASON_NO_DEPRECIATION_POLICY` reason strings.
- `backend/itam_reporting_kpis.py` `_compute_asset_value_kpi` / `compute_itam_kpis`: the batched pattern (one projected `assets` find, one `asset_models` `$in`), `hasData` convention. Today it includes every lifecycle status and returns `totalBookValueCents: 0` when assets exist but none is valued (both change under D-01 and D-10).
- `backend/itam_reporting_prebuilt.py` `_build_asset_value_rows`: the third copy of the same loop (rows sorted by book value desc); must move onto the shared computation. It formats with a hard-coded `$` (`_cents_to_dollars`); currency display is Phase 80 / COST-F2.
- `backend/itam_finance_endpoints.py` `get_asset_book_value`: per-asset route with `computedAt`; does a per-call `asset_models.find_one` (fine for one asset, N+1 if looped).
- `backend/itam_asset_endpoints.py` `_require_itam_viewer`: the guard to import.
- `backend/pagination_utils.py` `PaginationParams` (page, page_size=50) / `PaginatedResponse`.
- `backend/asset_identity.py`: `hardwareKey` values `serial:`/`uuid:`/`mac:` stamped on agent-discovered assets (commit 91c85e11d); the input for D-07.

### Established Patterns
- `TenantIsolatedCollection` prepends a tenant `$match` / filter, but the `platform-admin` context skips scoping for reads (`backend/database.py`), which is why D-13 refuses that context outright.
- Tenant context comes from `backend/tenant_middleware.py`: the JWT `tenant_id`, overridden by `X-Tenant-ID` only for `rbac_defaults.platform_tier(role) == "owner"`. `TokenData.tenant_id` stays `platform-admin` for a Super Admin, so routes that read `current_user.tenant_id` (the KPI and report routes today) cannot see the switcher choice.
- Agent-discovered assets get `asset-{hostname}` or a hardware-bound id via `agents.assetId`; the heartbeat (`backend/agent_heartbeat_endpoints.py`) stamps `agentId`, `agentStatus: "Online"`, `hardwareKey` on the asset and never writes `purchaseCostCents`, `purchaseDate` or `modelId`.
- `itam_lifecycle_endpoints._overdue_query` already excludes `disposed` (WR-03), a precedent for status-based exclusion.

### Integration Points
- New router (for example `backend/itam_cost_endpoints.py`, prefix `/api/itam/costs`) registered in `backend/router_registry.py` next to `itam_kpi_endpoints` / `itam_reporting_endpoints`.
- `shared/catalogue-access.json`: the `itam` catalogue's routes already include the `/api/itam` prefix, so `/api/itam/costs` falls under it; the Phase 76 parity test must see the new router as guarded.
- Frontend for D-14 only: `components/itam/ItamKpiPanel.tsx` (`formatCurrency(assetValue.totalBookValueCents ?? 0)` is the `$0.00` bug), `services/apiService.ts` `fetchItamKpis` / `authFetch` (`tenantId` option adds `X-Tenant-ID`), `types.ts` KPI types.

</code_context>

<specifics>
## Specific Ideas

- Tile, report and cost summary must show identical figures for the same tenant (roadmap SC3); the parity test should run all three over one seeded tenant and compare them, plus the golden-value table for `compute_book_value`.
- The two-tenant isolation test covers every cost route plus the KPI and report routes now on the shared tenant rule, including a Platform Owner with and without `X-Tenant-ID`, and Platform Support/Billing (always 400).

</specifics>

<deferred>
## Deferred Ideas

- Letting Platform Billing (or Support) pick a tenant for cost reads: raised and declined for this phase (D-15). It would change the platform-role tenant-override rule.
- Removing or honouring the unused asset-level `useful_life_years` / `salvage_value` fields (D-12): a cleanup candidate, not this phase.
- Already tracked elsewhere: license cost (Phase 79), Costs tab and export (Phase 80), COST-F1..F4.

</deferred>

---

*Phase: 78-organization-endpoint-cost-api*
*Context gathered: 2026-11-16*
