# Phase 61: Frontend ITAM Console - Research

**Researched:** 2026-08-06
**Domain:** React/TypeScript frontend integration console wiring existing FastAPI ITAM backends (Phases 56-60) behind one admin-gated nav entry
**Confidence:** HIGH (all findings verified directly against the checked-out codebase — no external library research needed; this is a pure integration phase)

## Summary

This phase has **zero new backend work and zero new npm packages** — every capability it needs to expose already exists as a working FastAPI route from Phases 56-60. The job is 100% frontend: build API client functions, tab components, and nav wiring that call those routes. The codebase already contains an exact structural precedent for exactly this shape of work — `components/NativeSecurityConsole.tsx` (Phase 50-53's console) — a single tabbed AppView that mounts one component per cluster from `components/nativeSecurity/*.tsx`, each of which independently fetches its own data via `apiService.ts` and uses `showToast` + a shared `Modal` component for actions. Phase 61 should clone this shape verbatim into a new `components/itam/*.tsx` directory, replacing today's 13-line placeholder `ITAMConsole.tsx`.

Three things make this phase harder than a typical "add one dashboard" phase and must shape how the planner sequences waves. First, the frontend `Asset` type and `apiService.ts` currently have **zero ITAM awareness** — no client functions for any of the ~20 ITAM routes exist yet, and the `Asset` interface in `types.ts` is missing every ITAM field (`assetTag`, `lifecycleStatus`, `assetSource`, `manufacturerId`/`modelId`/`categoryId`/`supplierId`/`locationId`, purchase/warranty fields, assignment fields). Second, the prior partial planning attempt already added `'itam'` to the `AppView` union in `types.ts` without adding the matching `viewPermissionMap` entry in `App.tsx` — **this currently breaks `npx tsc --noEmit`** (verified: `error TS2741: Property 'itam' is missing in type ... Record<AppView, Permission>`; `npm run build`'s esbuild pass does not catch it, matching the exact class of gap Phase 47-06's SUMMARY documented). Third, and most important for scope: **Phase 60's backend only implements software licenses (ITAM-LIC-01)** — verified via `router_registry.py`, `itam_models.py`, and a full-repo grep: there is no `Consumable`/`Accessory` or `Component` Pydantic model, no service, no endpoint file, and no router registration for ITAM-LIC-02 (consumables/quantity checkout) or ITAM-LIC-03 (components). The commit tagged "implement software licenses, consumables, and components" touched only `.planning/` doc files, not code. The planner must scope the "Licenses & Consumables" console tab to **licenses only** for this phase, or explicitly flag consumables/components as blocked pending a backend gap-closure plan — building frontend UI against non-existent routes is not an option.

**Primary recommendation:** Clone `NativeSecurityConsole.tsx`'s tabbed-AppView structure into `components/itam/ITAMConsole.tsx` with tab components in `components/itam/`, add ~20 new `apiService.ts` client functions grouped by backend router, extend `types.ts`'s `Asset` interface with the missing ITAM fields, fix the pre-existing `viewPermissionMap['itam']` tsc break as part of Wave 1, and scope the Licenses & Consumables tab to licenses-only (assign/reclaim/expiry) since consumables/components have no backend yet.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| ITAM nav entry + permission gate | Browser / Client | — | Pure client-side route gating (`Sidebar.tsx` + `App.tsx` viewPermissionMap); mirrors every other console in this app — never a backend concern |
| Catalog CRUD (manufacturers/categories/locations/suppliers/models) | API / Backend (existing) | Browser / Client | `itam_catalog_endpoints.py` already implements full CRUD; frontend only needs API client + forms/tables |
| Manual asset creation | API / Backend (existing) | Browser / Client | `itam_asset_endpoints.py POST /api/assets` already implements it end-to-end |
| Check-out / check-in / audit / history | API / Backend (existing) | Browser / Client | `itam_lifecycle_endpoints.py` fully implements the state machine + audit trail; frontend triggers via modal + displays result |
| Warranty / book-value / purchase record | API / Backend (existing) | Browser / Client | `itam_finance_endpoints.py` computes both at read time; frontend is a pure display + one PATCH form |
| Asset tag labels (QR/barcode/PDF sheet) | API / Backend (existing) | Browser / Client | `itam_label_endpoints.py` streams binary responses (PNG/PDF); frontend triggers a download, no local rendering |
| License CRUD + seat assign/reclaim | API / Backend (existing) | Browser / Client | `itam_license_endpoints.py` fully implements it; frontend is CRUD forms + assignment list |
| Consumables checkout (qty>1) | **None — not built** | — | ITAM-LIC-02 has no backend; out of scope for this phase's frontend work until a gap-closure plan exists |
| Component sub-inventory (RAM/HDD/GPU) | **None — not built** | — | ITAM-LIC-03 has no backend; same as above |
| RBAC permission grants (`manage:itam`, `manage:assets`) | API / Backend (existing + new) | Browser / Client | Backend routes already enforce `manage:assets`; the NEW `manage:itam` permission is nav-only and must be added to `rbac_utils.py`/`rbac_service.py` default role grants or admins will never see the nav entry |

## Package Legitimacy Audit

**No new packages required.** This phase is a pure integration of existing backend routes with existing frontend patterns (React, Tailwind, the existing `Modal` component, `showToast` utility, `apiService.ts` fetch wrappers). No `npm install` step belongs in this phase's plan. If a future plan proposes a package (e.g., a table/pagination library), treat that as scope creep to flag — the existing `SoftwareInventoryTab.tsx`/`RemediationQueueTab.tsx` patterns already implement search/filter/pagination-equivalent behavior with plain React state and no dependency.

## Architecture Patterns

### System Architecture Diagram

```
Admin browser
   │
   ▼
Sidebar.tsx nav item "ITAM"  ──(gated by permission: 'manage:itam')──┐
   │                                                                  │
   ▼                                                                  │
App.tsx  case 'itam':  <ITAMConsole/>  (lazy import, ErrorBoundary)  │
   │                                                                  │
   ▼                                                                  ▼
components/itam/ITAMConsole.tsx (tab state: catalog|lifecycle|finance|licenses)
   │
   ├─▶ components/itam/CatalogTab.tsx ──▶ apiService.ts (getCatalogEntities/createCatalogEntity/...)
   │        │                                   │
   │        └─▶ AssetComplianceList.tsx (existing, control-scoped — needs a control picker)
   │        └─▶ SoftwareInventoryTab.tsx (existing, needs inventory/loading/onRefresh/onUninstall props)
   │                                             │
   ├─▶ components/itam/LifecycleTab.tsx ─────────┤
   │        (asset table + Checkout/Checkin/Audit modals + history drill-down)
   │                                             │
   ├─▶ components/itam/FinanceTab.tsx ───────────┤
   │        (purchase-record form + book-value/warranty read panels)
   │                                             │
   └─▶ components/itam/LicensesTab.tsx ──────────┤
            (license CRUD + seat assign/reclaim; consumables/components OUT per backend gap)
                                                  ▼
                                    backend/itam_*_endpoints.py (Phases 56-60, all pre-existing)
                                                  │
                                                  ▼
                                    MongoDB: assets / manufacturers / asset_categories /
                                    locations / suppliers / asset_models / licenses /
                                    license_assignments / assignment_history (all pre-existing)
```

A reader can trace the full round trip: click "ITAM" in the sidebar → console renders with the Catalog tab active → create a Manufacturer/Model → switch to Lifecycle tab → create a manual asset referencing that model → check it out to a user → switch to Finance tab → view its warranty/book-value → switch to Licenses tab → assign a license seat to that asset — all without leaving `ITAMConsole.tsx`, satisfying ROADMAP success criterion 3.

### Recommended Project Structure
```
components/
├── itam/
│   ├── ITAMConsole.tsx          # Top-level tabbed shell — clone NativeSecurityConsole.tsx's shape exactly
│   ├── CatalogTab.tsx           # Manufacturer/Category/Location/Supplier/Model CRUD tables + create/edit modals
│   ├── LifecycleTab.tsx         # Asset table (manual + agent-discovered) + Checkout/Checkin/Audit modals + history drawer
│   ├── FinanceTab.tsx           # Purchase-record form + book-value/warranty read panels, per selected asset
│   └── LicensesTab.tsx          # License CRUD + seat assign/reclaim list (consumables/components deferred)
├── AssetComplianceList.tsx      # EXISTING — control-scoped; needs a control-picker wrapper to integrate per CONTEXT.md
├── SoftwareInventoryTab.tsx     # EXISTING — needs inventory/loading/onRefresh/onUninstall props supplied
```

### Pattern 1: Tabbed console shell (clone verbatim)
**What:** A single stateful AppView component holding `const [tab, setTab] = useState<Tab>(...)` and a `TABS` array, rendering one child component per tab.
**When to use:** Exactly this phase's top-level `ITAMConsole.tsx` — this is the literal Phase 47/48-era precedent named in the ROADMAP goal text (`NativeSecurityConsole.tsx`, built in Phase 50-53 but following the same nav-registration convention Phase 47/48 established for `geoSecurity`/`fleetObservability`).
**Example:**
```tsx
// Source: components/NativeSecurityConsole.tsx (verified in-repo, lines 1-60)
import React, { useState } from 'react';
import { CatalogTab } from './itam/CatalogTab';
import { LifecycleTab } from './itam/LifecycleTab';
import { FinanceTab } from './itam/FinanceTab';
import { LicensesTab } from './itam/LicensesTab';

type Tab = 'catalog' | 'lifecycle' | 'finance' | 'licenses';

const TABS: { id: Tab; label: string }[] = [
  { id: 'catalog', label: 'Catalog' },
  { id: 'lifecycle', label: 'Check-Out/In' },
  { id: 'finance', label: 'Procurement & Finance' },
  { id: 'licenses', label: 'Licenses & Consumables' },
];

export function ITAMConsole() {
  const [tab, setTab] = useState<Tab>('catalog');
  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      <header className="mb-6">
        <h1 className="text-2xl font-bold">IT Asset Management Console</h1>
      </header>
      <nav className="flex gap-1 mb-4 border-b border-gray-700" aria-label="Tabs">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)} aria-current={tab === t.id ? 'page' : undefined}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t.id ? 'border-cyan-500 text-white' : 'border-transparent text-gray-400 hover:text-gray-200'
            }`}>
            {t.label}
          </button>
        ))}
      </nav>
      <main>
        {tab === 'catalog' && <CatalogTab />}
        {tab === 'lifecycle' && <LifecycleTab />}
        {tab === 'finance' && <FinanceTab />}
        {tab === 'licenses' && <LicensesTab />}
      </main>
    </div>
  );
}
```

### Pattern 2: Self-fetching tab component with modal actions (clone verbatim)
**What:** Each tab owns `useState` for its list + loading/error, fetches on mount via `useEffect`, and opens a shared `Modal` (`components/ui/Modal.tsx`) for mutating actions, calling `showToast` on success/failure.
**When to use:** Every one of the four new tab components (`CatalogTab`, `LifecycleTab`, `FinanceTab`, `LicensesTab`).
**Example:**
```tsx
// Source: components/nativeSecurity/RemediationQueueTab.tsx (verified in-repo, lines 1-65)
import React, { useEffect, useState } from 'react';
import { showToast } from '../../utils/toast';
import Modal from '../ui/Modal';
// import { listCatalogEntities, createCatalogEntity } from '../../services/apiService';

export function CatalogTab() {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { load(); }, []);
  async function load() {
    setLoading(true); setError(null);
    try { /* setItems(await listCatalogEntities('manufacturers')); */ }
    catch (e: any) { setError(e?.message || 'Failed to load'); }
    finally { setLoading(false); }
  }
  // ... modal-driven create/edit/delete, each wrapped in try/catch + showToast
  return <div>{/* table + Modal */}</div>;
}
```

### Pattern 3: Multi-segment API prefix awareness (backend quirk the frontend must respect)
**What:** `itam_asset_endpoints.py`, `itam_lifecycle_endpoints.py`, `itam_finance_endpoints.py`, and `itam_label_endpoints.py` **all share the `/api/assets` prefix** with the pre-existing `asset_endpoints.py`. Every ITAM route is multi-segment (`/{asset_id}/checkout`, `/{asset_id}/warranty`, `/{asset_id}/label/qr`, `/labels/sheet`) specifically so it cannot collide with `asset_endpoints.py`'s single-segment `GET /{asset_id}`.
**When to use:** When adding `apiService.ts` client functions, always hit the exact documented paths below — do not assume a generic `/api/assets/{id}/...` REST convention without checking this file first, since `GET /api/assets` (list, existing) and `GET /api/assets/{asset_id}` (detail, existing) are owned by a different file/router than the ITAM-specific sub-routes.

### Anti-Patterns to Avoid
- **Building a 5th "Consumables" or "Components" UI against routes that don't exist:** Verified — no such backend surface exists (see Summary). Do not let the plan silently invent a mock/local-only consumables UI; either scope it out explicitly or add a backend gap-closure plan first.
- **Assuming catalog/license list routes are true server-paginated:** They are not (see Common Pitfalls) — only `limit` (cap 500), no `page`/`page_size`. A "paginated table" per CONTEXT.md's decision must paginate client-side over the capped result set for these five endpoints, unlike the real asset list route.
- **Reusing `AssetComplianceList`/`SoftwareInventoryTab` without checking their prop contracts:** Both are dumb, fully-controlled components (Detailed in Common Pitfalls) — dropping `<AssetComplianceList />` into a tab with no data-fetching wrapper will not compile and would not render anything useful even if it did.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Tabbed console navigation | A new tab-router abstraction | The exact `useState<Tab>` + `TABS` array pattern from `NativeSecurityConsole.tsx` | Already proven, already styled consistently, zero new dependencies |
| Confirm/action dialogs | A bespoke dialog component | `components/ui/Modal.tsx` (props: `isOpen`, `onClose`, `title`, `description?`, `children?`, `confirmLabel`, `onConfirm`) | Existing shared component, already used by `RemediationQueueTab.tsx`'s deny-reason flow — matches CONTEXT.md's "Modal dialogs for all actions" decision exactly |
| Toast notifications | `alert()` or a new notification system | `showToast(message, 'success' \| 'error')` from `utils/toast` | Used uniformly across every dashboard in this codebase |
| Client-side search/filter/expand-row table | A table library | The plain-React pattern in `SoftwareInventoryTab.tsx` (`useState` + `useMemo` filter, expand/collapse rows, chip-style badges) | Zero new dependency, matches existing visual language |
| Asset tag label download | Client-side QR/barcode rendering | Direct links/fetches to `GET /api/assets/{id}/label/qr`, `/label/barcode`, `POST /labels/sheet` (all return binary `StreamingResponse`) | Server already generates offline-safe QR/barcode/PDF (Phase 58); duplicating this client-side would violate the "fully offline, no external service" requirement's single source of truth |

**Key insight:** Every "hard part" of this phase's problem domain (state machines, audit trails, tenant isolation, offline label generation, seat-counting concurrency) was already solved in Phases 56-60's backend. The frontend's job is strictly to call it correctly and render the result — introducing any new business logic client-side (e.g., re-deriving warranty status, re-implementing the deployable/deployed guard) would create a second source of truth that can drift from the server (the exact class of bug `itam_finance_endpoints.py`'s docstring explicitly calls out: "an operator's on-screen status and the alert they receive can never disagree").

## Common Pitfalls

### Pitfall 1: `viewPermissionMap['itam']` is already broken and must be fixed in Wave 1
**What goes wrong:** `types.ts`'s `AppView` union already contains `| 'itam'` (added by an earlier, superseded partial attempt), but `App.tsx`'s `viewPermissionMap: Record<AppView, Permission>` has no `itam` key.
**Why it happens:** A prior partial plan/commit added the union member without registering the map entry.
**How to avoid:** Verified via `npx tsc --noEmit`: `error TS2741: Property 'itam' is missing in type ... but required in type 'Record<AppView, Permission>'.` — `npm run build` (esbuild/Vite) does NOT catch this; only `tsc` does. Fix by adding `itam: 'manage:itam'` to `viewPermissionMap` as part of the very first task, and run `npx tsc --noEmit` (not just `npm run build`) as the verification command for that task.
**Warning signs:** `npm run build` reporting success is not sufficient evidence the Sidebar/AppView wiring is complete — this project has hit this exact class of gap before (Phase 47-06 SUMMARY documents the identical failure mode for `geoSecurity`).

### Pitfall 2: `manage:itam` is a brand-new permission string that no role grants yet
**What goes wrong:** If the plan only adds `permission: 'manage:itam'` to the Sidebar nav item and the `viewPermissionMap`, but never adds `"manage:itam"` to any role's default permission list, **no user — including admins — will ever see the nav entry**, because `hasPermission('manage:itam')` will always return false for every role except literal super-admin wildcard roles.
**Why it happens:** Client-side gating (`Sidebar.tsx`'s `hasPermission(item.permission)` filter) and server-side role grants (`rbac_utils.py`'s `DEFAULT_PERMISSIONS` dict and `rbac_service.py`'s `RBACService.default_roles` dict — there are TWO separate dicts that must both be updated, verified via grep) are two independent code paths that must both list the new permission string.
**How to avoid:** Add `"manage:itam"` to the `"admin"` and `"Tenant Admin"` entries in BOTH `backend/rbac_utils.py`'s `DEFAULT_PERMISSIONS` and `backend/rbac_service.py`'s `RBACService.default_roles`. This mirrors exactly how `"manage:assets"` itself was added for Phase 56 (comment: `# Added for ITAM Phase 56-01` appears in both files at the matching lines) — follow that precedent, don't invent a new grant mechanism.
**Warning signs:** Manual UAT logging in as an admin and not seeing the ITAM nav item at all, despite the code compiling and building cleanly.

### Pitfall 3: Catalog and License list routes are NOT server-paginated
**What goes wrong:** CONTEXT.md's Decision says "Lists (assets, catalog, history): Paginated tables with search/filter controls." `GET /api/itam/catalog/{kind}` and `GET /api/itam/licenses` both accept only a `limit` query param (default 200, max 500) — there is no `page`/`page_size`/cursor. Only the pre-existing `GET /api/assets` (the legacy asset list route in `asset_endpoints.py`) has true server pagination via `paginate_mongo_query`.
**Why it happens:** The five catalog kinds and licenses are expected to be low-cardinality (tenants rarely have hundreds of manufacturers/models/licenses), so the original phases didn't build cursor pagination for them.
**How to avoid:** For Catalog and Licenses tabs, fetch up to the 500-item cap in one call and paginate/filter **client-side** (clone `SoftwareInventoryTab.tsx`'s `useMemo`-based search/filter pattern). For the Lifecycle tab's asset table, use the real `GET /api/assets` route's `page`/`page_size` params directly.
**Warning signs:** A UI that silently breaks past 500 catalog/license entries, or a plan task that assumes a `page` param exists on `/api/itam/catalog/{kind}` and gets a silently-ignored query param (FastAPI will just not error — the extra param is simply unused).

### Pitfall 4: `AssetComplianceList` and `SoftwareInventoryTab` are fully-controlled, not self-fetching
**What goes wrong:** CONTEXT.md's Integration decision says to "Directly integrate existing `AssetComplianceList` and `SoftwareInventoryTab` as tabs/sub-sections." Both components take zero internal data-fetching — `AssetComplianceList` requires `{control, assets, complianceData, onUpdateStatus, onUploadEvidence, onIngestEvidence, onDeleteEvidence, onEvidenceReviewed?}` (verified: `components/AssetComplianceList.tsx` lines 27-40) and is inherently **per-control**, not a general asset browser. `SoftwareInventoryTab` requires `{inventory, loading, onRefresh, onUninstall}` (verified: `components/SoftwareInventoryTab.tsx` lines 23-28) and expects per-agent software inventory data, not ITAM catalog data.
**Why it happens:** Both components were built for their original hosts (`FrameworkDetail.tsx` for compliance-per-control, `SoftwareDeployment.tsx` for agent software inventory) which already own the data-fetching and prop-wiring logic — see `FrameworkDetail.tsx` lines 340-400 and `SoftwareDeployment.tsx` lines 280-330 for the exact wiring to clone.
**How to avoid:** Neither component fits cleanly into the four named ROADMAP tabs (Catalog / Check-Out-In / Procurement-Finance / Licenses-Consumables) — they represent a fifth/sixth conceptual cluster (compliance-per-control, software-inventory-per-agent). The planner should either (a) add them as two additional top-level tabs beyond the four ROADMAP-named ones (e.g., "Compliance" and "Software Inventory"), each with its own data-fetching wrapper cloned from `FrameworkDetail.tsx`/`SoftwareDeployment.tsx`, or (b) confirm with the user whether this integration is truly in-scope for ITAM-UI-01 vs. a nice-to-have cross-link. This is flagged as an Open Question below — do not silently guess which of the four named tabs they belong under, since neither fits.
**Warning signs:** A plan task that drops `<AssetComplianceList control={?} assets={?} complianceData={?} .../>` into, say, the Catalog tab with no control-picker and no compliance-data fetch will not compile (missing required props) and, even if stubbed with `any`, will render nothing meaningful without a control selected.

### Pitfall 5: Frontend `Asset` type has zero ITAM field awareness
**What goes wrong:** `types.ts`'s `export interface Asset` (line 742) has no `assetTag`, `lifecycleStatus`, `assetSource`, `manufacturerId`, `modelId`, `categoryId`, `supplierId`, `locationId`, `purchaseCostCents`, `purchaseDate`, `poNumber`, `warrantyMonths`, `assignedToType`, `assignedToId`, `checkedOutAt`/`checkedOutBy`, `checkedInAt`/`checkedInBy`, `lastAuditedAt`, `customFields`, or `expectedReturnDate` fields — all of which the backend already writes and returns on every asset document.
**Why it happens:** `Asset` was defined for the original agent-discovered CMDB use case (Phase 1-55) and was never extended when Phases 56-60 added ITAM fields to the same `assets` collection (by design — one collection, additive fields, per the milestone's central architecture decision).
**How to avoid:** Extend the `Asset` interface (or define a new `ItamAssetFields` interface intersected with `Asset`) as an early task, before any tab component tries to render these fields — otherwise every read of `asset.lifecycleStatus` etc. is a silent `any`-typed access or a tsc error depending on how it's typed.
**Warning signs:** `tsc` errors on `asset.lifecycleStatus`/`asset.assetTag` access, or resorting to `(asset as any).lifecycleStatus` casts scattered through new components (a code-smell the plan-checker should reject).

## Code Examples

### Exact backend routes to wire (verified via direct file reads — use these paths verbatim)

```
# Catalog (Phase 56) — backend/itam_catalog_endpoints.py, prefix /api/itam/catalog
# kind ∈ {manufacturers, categories, locations, suppliers, models}
POST   /api/itam/catalog/{kind}              body: kind-specific (see itam_models.py)
GET    /api/itam/catalog/{kind}?limit=200    -> List[Dict]  (no page/page_size — cap 500)
GET    /api/itam/catalog/{kind}/{entity_id}  -> Dict
PATCH  /api/itam/catalog/{kind}/{entity_id}  body: partial update
DELETE /api/itam/catalog/{kind}/{entity_id}  -> 204 (409 if assets still reference it)

# Manual asset creation (Phase 56) — backend/itam_asset_endpoints.py, prefix /api/assets
POST   /api/assets   body: ManualAssetCreate (name, assetTag?, manufacturerId?, modelId?,
                      categoryId?, supplierId?, locationId?, serialNumber?, type?, notes?,
                      lifecycleStatus?, customFields?, purchaseCostCents?, purchaseDate?,
                      poNumber?, warrantyMonths?)

# Lifecycle (Phase 57) — backend/itam_lifecycle_endpoints.py, prefix /api/assets
POST   /api/assets/{asset_id}/checkout   body: {targetType: 'user'|'location', targetId, note?, expectedReturnDate?}
POST   /api/assets/{asset_id}/checkin    body: {note?}
GET    /api/assets/{asset_id}/history?limit=100  -> {assetId, entries: [...]}
POST   /api/assets/{asset_id}/audit      body: {auditedAt?, note?}
GET    /api/assets/reports/overdue-audit?limit=200  -> {intervalDays, cutoff, count, rows}

# Finance (Phase 59) — backend/itam_finance_endpoints.py, prefix /api/assets
PATCH  /api/assets/{asset_id}/purchase   body: {purchaseCostCents?, purchaseDate?, poNumber?, supplierId?, warrantyMonths?}
GET    /api/assets/{asset_id}/book-value  -> {assetId, modelId, purchaseCostCents, purchaseDate, bookValueCents|null, reason?, usefulLifeYears?, salvageValueCents?}
GET    /api/assets/{asset_id}/warranty    -> {assetId, purchaseDate, warrantyMonths, alertWindowDays, warrantyAlertSentAt, ...status fields}

# Labels (Phase 58) — backend/itam_label_endpoints.py, prefix /api/assets
GET    /api/assets/{asset_id}/label/qr       -> image/png (StreamingResponse, download)
GET    /api/assets/{asset_id}/label/barcode  -> image/png (StreamingResponse, download)
POST   /api/assets/labels/sheet   body: {assetIds: string[]}  -> application/pdf (max 500 ids, all-or-nothing refusal on any unresolved id or missing assetTag)

# Licenses (Phase 60 — LICENSES ONLY, consumables/components NOT implemented) —
# backend/itam_license_endpoints.py, prefix /api/itam/licenses
POST   /api/itam/licenses                body: {name, manufacturerId?, seatCount, expiryDate?, isReassignable?, notes?}
GET    /api/itam/licenses?limit=200      -> List[Dict]  (no page/page_size — cap 500)
GET    /api/itam/licenses/{license_id}   -> Dict
PATCH  /api/itam/licenses/{license_id}   body: partial update
POST   /api/itam/licenses/{license_id}/assign   body: {targetType: 'user'|'asset', targetId, note?}
GET    /api/itam/licenses/{license_id}/assignments  -> List[Dict]
DELETE /api/itam/licenses/assignments/{assignment_id}?note=...  -> 204
```

All ITAM routes above require `Depends(_require_itam_admin)` server-side, which checks `verify_permission(current_user, "manage:assets")` — this is the SAME permission for every ITAM backend route regardless of which console tab calls it. `manage:itam` (the new nav permission) is purely a client-side gate on top of this; it does not replace `manage:assets` on the backend.

### apiService.ts client function pattern to clone
```typescript
// Source: services/apiService.ts — existing getAgentLocationTracking/setAgentLocationTracking
// pattern (cited by Phase 47-06's own plan as the clone target for new settings-style resources).
// Apply the same shape for every ITAM route: typed interface, graceful GET fallback, throwing PATCH/POST.
export interface ItamCatalogEntity {
  id: string;
  name: string;
  notes?: string;
  [key: string]: any; // per-kind fields vary (manufacturerId, seatCount, etc. — see itam_models.py)
}

export async function listCatalogEntities(kind: string): Promise<ItamCatalogEntity[]> {
  const res = await authFetch(`/api/itam/catalog/${kind}`);
  if (!res.ok) throw new Error(`Failed to load ${kind}`);
  return res.json();
}

export async function createCatalogEntity(kind: string, payload: Record<string, any>): Promise<ItamCatalogEntity> {
  const res = await authFetch(`/api/itam/catalog/${kind}`, { method: 'POST', body: JSON.stringify(payload) });
  if (!res.ok) throw new Error(`Failed to create ${kind}`);
  return res.json();
}
```
(Exact `authFetch`/header conventions must be copied from an existing neighboring function in `apiService.ts` — the file already has ~30 similar functions to clone from; do not invent a new fetch wrapper.)

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Standalone per-feature dashboards wired individually into `Sidebar.tsx` | One tabbed "Console" AppView per major subsystem (`NativeSecurityConsole`, and now `ITAMConsole`) | Phase 50-53 (native security), continuing into Phase 61 | Reduces sidebar sprawl; groups related backend surfaces under one nav entry and one permission gate |
| `assets` collection scoped only to agent-discovered CMDB data | `assets` collection additionally carries ITAM fields via `assetSource` discriminator (`agent` \| `manual`) | Phase 56 (2026-08-04 session) | Frontend `Asset` type must be treated as a superset type going forward — any new asset-related feature must check both discriminator values |

**Deprecated/outdated:** None — this is a young milestone (v4.0, defined 2026-08-04) with no legacy patterns to migrate away from.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `AssetComplianceList`/`SoftwareInventoryTab` should become two ADDITIONAL tabs beyond the four ROADMAP-named ones, rather than nested inside one of the four | Pitfall 4 / Don't Hand-Roll | If wrong, the planner may nest them awkwardly inside "Catalog" where they don't conceptually belong, or the user may actually want them omitted from this Console entirely and left reachable only from their current hosts (`FrameworkDetail.tsx`/`SoftwareDeployment.tsx`) — this should be confirmed with the user before locking the tab layout (see Open Questions) |
| A2 | Consumables (ITAM-LIC-02) and Components (ITAM-LIC-03) should be explicitly descoped from this phase's frontend rather than stubbed with placeholder UI | Summary / Architectural Responsibility Map | If wrong (i.e., the user actually wants a backend gap-closure sub-plan folded into Phase 61), the phase's scope grows to include new backend Pydantic models/service/endpoints/router registration — a materially larger phase than "frontend console" implies |
| A3 | `manage:itam` should be granted to the same roles that already hold `manage:assets` (admin, Tenant Admin, and super-admin-equivalent wildcard roles) rather than a narrower or broader set | Pitfall 2 | If wrong, either admins can't see the console (too narrow) or non-admin roles gain unintended nav visibility (too broad) — low risk since it's client-side-only, but should still match the ROADMAP's explicit "admin-gated" framing |

## Open Questions

1. **Where do `AssetComplianceList` and `SoftwareInventoryTab` belong in the console's tab layout?**
   - What we know: CONTEXT.md explicitly says to integrate both directly as tabs/sub-sections; ROADMAP success criterion 2 names exactly four sections (Catalog, Check-Out/In, Procurement & Finance, Licenses & Consumables) with no mention of compliance or software inventory.
   - What's unclear: Whether these two are meant to become a 5th/6th top-level tab, sub-tabs nested under Catalog, or whether the user actually wants a lighter cross-link (e.g., a "View compliance" button on an asset row that navigates to the existing `FrameworkDetail.tsx` flow) rather than a full re-hosted tab.
   - Recommendation: Surface this as an explicit AskUserQuestion during `/gsd-discuss-phase` or planning — don't silently pick one; the two candidate answers (extra tabs vs. cross-link) produce meaningfully different task lists.

2. **Should Phase 61 include a backend gap-closure sub-plan for ITAM-LIC-02/03 (consumables/components), or defer them entirely?**
   - What we know: REQUIREMENTS.md's traceability table already marks ITAM-LIC-02/ITAM-LIC-03 as mapped to "Phase 60" — but Phase 60's actual committed code only implements licenses. No consumables/components backend exists anywhere in the tree (verified via `router_registry.py`, full-repo grep, and `itam_models.py`).
   - What's unclear: Whether this is a known, accepted gap (Phase 60 was mis-scoped/mis-labeled and someone will circle back with a dedicated phase) or whether the user expects Phase 61 to notice and close it inline.
   - Recommendation: Flag this to the user before planning locks in a 4-tab layout — the safest default is to scope the "Licenses & Consumables" tab to licenses-only for this phase and file the consumables/components gap as a new backlog item, since inventing frontend UI against nonexistent routes is never correct.

3. **Is a control-picker required for AssetComplianceList's per-control model to make sense inside an ITAM context, given ITAM assets aren't the same population as compliance-audited assets?**
   - What we know: `AssetComplianceList` requires a single `control: Control` prop and shows all `assets` against that one control's compliance status — it was designed for `FrameworkDetail.tsx`'s per-control drill-down, not a general asset-compliance overview.
   - What's unclear: Whether an ITAM-console "Compliance" tab should let the user pick a control from a dropdown (extra UI not in CONTEXT.md's decisions) or whether a different, coarser compliance summary view is actually what's wanted.
   - Recommendation: Depends on the answer to Open Question 1 — if the answer is "cross-link only," this question is moot.

## Environment Availability

Skipped — this phase has no external tool/service/runtime dependencies beyond the project's existing Node/npm toolchain, which is already confirmed working (verified: `npm run build` succeeds in this environment).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Vitest 3.2.4 (frontend), pytest (backend — not touched by this phase) |
| Config file | `vite.config.ts` (embedded `test` block, `setupFiles: ['./src/__tests__/setup.ts']`) |
| Quick run command | `npx vitest run <path-to-new-test-file>` |
| Full suite command | `npm run test` (= `vitest run`) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ITAM-UI-01 | `manage:itam` permission gates Sidebar/App view | unit | `npx tsc --noEmit` (Record<AppView,Permission> completeness) + `grep -c "itam" App.tsx components/Sidebar.tsx` | ❌ Wave 0 — no existing test targets `ITAMConsole` |
| ITAM-UI-01 | Console renders 4 tabs and switches between them | component | `npx vitest run components/itam/__tests__/ITAMConsole.test.tsx` | ❌ Wave 0 — new test file needed |
| ITAM-UI-01 | apiService client functions target the correct exact paths | unit | `npx vitest run services/__tests__/itamApiService.test.ts` (mock fetch, assert URL/method/body) | ❌ Wave 0 — new test file needed |

Manual/UAT verification (per this project's established convention for every console-wiring phase — 47-06, 48-05, 29-04 etc.) remains the authoritative check for "can an admin complete a full round trip without leaving the console" (ROADMAP success criterion 3) — no existing automated harness drives the real browser UI in this repo; every prior console-wiring phase logged this as a Manual-Only gate item, and Phase 61 should do the same.

### Sampling Rate
- **Per task commit:** `npx tsc --noEmit && npm run build` (both — tsc catches the Record<AppView,Permission> class of bug that build misses)
- **Per wave merge:** `npm run test` (full vitest suite) + `npx tsc --noEmit && npm run build`
- **Phase gate:** Full suite green before `/gsd-verify-work`; manual UAT round-trip walkthrough as the human-judgment item

### Wave 0 Gaps
- [ ] `components/itam/__tests__/ITAMConsole.test.tsx` — covers tab-switching + permission-gated render
- [ ] `services/__tests__/itamApiService.test.ts` — covers every new apiService function's URL/method/body shape (mocked fetch, no live backend)
- [ ] No shared fixture/mocking gap identified — existing `src/__tests__/setup.ts` already provides the vitest environment used by other component tests in this repo

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | no | Unchanged — reuses existing `authFetch`/session handling, no new auth surface |
| V3 Session Management | no | Unchanged |
| V4 Access Control | yes | Client-side gate: new `manage:itam` permission on Sidebar/App view (defense-in-depth only). Authoritative gate: every backend ITAM route already enforces `manage:assets` via `_require_itam_admin` — this phase must NOT weaken or bypass that; it only adds a nav-level client gate on top |
| V5 Input Validation | yes | All validation happens server-side already (Pydantic models with `extra="forbid"`, `ge=0`/`gt=0` constraints, ISO-8601 date validators) — the frontend forms should mirror these constraints for UX (e.g., don't let the user submit a negative `seatCount`) but must never treat client-side validation as the authoritative check |
| V6 Cryptography | no | No new crypto surface — label generation (QR/barcode) is pre-existing server-side code from Phase 58, untouched by this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Client-side-only nav gate bypassed via direct URL/hash manipulation to reach `#itam` | Elevation of Privilege | Not a real risk here specifically — the underlying data routes (`manage:assets`-gated) are still enforced server-side even if a user manually navigates to the `itam` view hash; the nav gate is UX-only, exactly as documented for `geoSecurity`/`nativeSecurity` precedents. Confirm this pattern holds (it does, per every ITAM backend route's `Depends(_require_itam_admin)`) rather than re-verifying from scratch |
| Cross-tenant asset/catalog/license id probing via the new frontend forms | Information Disclosure | Already mitigated server-side — every ITAM route resolves ids through the `TenantIsolatedDatabase`/`TenantIsolatedCollection` wrapper, so a cross-tenant id produces the same 404 as a nonexistent one (verified in multiple docstrings across `itam_finance_endpoints.py`, `itam_label_endpoints.py`, `itam_lifecycle_endpoints.py`). The frontend must not add any client-side id-existence check that could leak more information than the 404 already does |
| Asset-tag/PO-number/note fields rendered unsanitized into the DOM (stored-XSS-adjacent) | Tampering | React's default JSX escaping already covers text rendering; the one exception to watch is `itam_label_endpoints.py`'s `Content-Disposition` filename sanitization (`_safe_filename_part`) which is already server-side — the frontend does not need to re-sanitize filenames itself, just trigger the download normally (`<a href>`/`window.open` on the streamed URL) |

## Sources

### Primary (HIGH confidence — direct codebase reads this session)
- `components/NativeSecurityConsole.tsx`, `components/nativeSecurity/{FindingsTab,RemediationQueueTab,PlaybooksTab,AuditTab}.tsx` — tabbed-console + modal/toast pattern
- `backend/itam_catalog_endpoints.py`, `itam_asset_endpoints.py`, `itam_lifecycle_endpoints.py`, `itam_finance_endpoints.py`, `itam_label_endpoints.py`, `itam_license_endpoints.py`, `itam_license_service.py`, `itam_models.py`, `router_registry.py` — full route/model inventory
- `App.tsx`, `components/Sidebar.tsx`, `types.ts` — AppView/Permission/viewPermissionMap wiring, confirmed via `npx tsc --noEmit` and `npm run build` runs in this session
- `backend/rbac_utils.py`, `backend/rbac_service.py` — permission grant mechanism (two separate default-role dicts)
- `components/AssetComplianceList.tsx`, `components/SoftwareInventoryTab.tsx`, `components/FrameworkDetail.tsx`, `components/SoftwareDeployment.tsx` — existing component prop contracts and their current hosts
- `.planning/phases/47-agent-scoped-geo-security-detectors/47-06-PLAN.md` + `47-06-SUMMARY.md` — the exact precedent phase for "nav-registration for a new admin-gated panel," including the tsc-vs-build gap it hit
- `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, `.planning/phases/61-frontend-itam-console/61-CONTEXT.md`, `.planning/phases/60-licenses-consumables/*` — requirement/decision/history context
- `git show --stat 431d8d7`, `git log` on `itam_license_*` files — confirmed the consumables/components backend gap

### Secondary (MEDIUM confidence)
None — every claim in this document was directly verified against the checked-out repository this session; no external web research was needed since this is a pure internal-integration phase.

### Tertiary (LOW confidence)
None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new libraries; every pattern cloned from working in-repo code
- Architecture: HIGH — console shell pattern directly copied from a real, shipped precedent (`NativeSecurityConsole.tsx`)
- Pitfalls: HIGH — all five pitfalls verified directly (tsc error reproduced, grep-confirmed permission dict duplication, grep-confirmed absence of consumables/components code, direct prop-contract reads)

**Research date:** 2026-08-06
**Valid until:** No external dependency drift risk (internal-only integration) — re-verify only if Phase 60 gains consumables/components backend work before Phase 61 executes, or if `components/itam/ITAMConsole.tsx` / `types.ts`'s `AppView` union changes again before planning begins.
