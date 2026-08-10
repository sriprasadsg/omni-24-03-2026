# Phase 61 Context: ITAM Console Scaffold & Frontend Implementation

## Domain
Frontend implementation (React) of ITAM Console features, integrating with backend modules (catalog, asset lifecycle, compliance, inventory).

## Canonical Refs
- `backend/itam_catalog_endpoints.py` — ITAM Catalog API
- `backend/itam_lifecycle_endpoints.py` — ITAM Lifecycle API
- `components/AssetComplianceList.tsx` — Compliance UI
- `components/SoftwareInventoryTab.tsx` — Software inventory UI
- `components/itam/ITAMConsole.tsx` — Console scaffold

## Decisions
### Navigation
- Structure: Tabs for main sections (Catalog, Asset Lifecycle, Licenses & Consumables, Procurement & Finance).

### Data Display
- Lists (assets, catalog, history): Paginated tables with search/filter controls.

### Action Workflows
- Check-out, check-in, audit, create: Modal dialogs for all actions.

### Integration
- Integration: Directly integrate existing `AssetComplianceList` and `SoftwareInventoryTab` as tabs/sub-sections.
