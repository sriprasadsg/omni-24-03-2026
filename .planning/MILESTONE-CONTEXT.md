# Milestone Context — v4.0: IT Asset Management (ITAM) Lifecycle

> Captured by /gsd-new-milestone goal-gathering on 2026-07-30. Held as context because v3.3
> is still in progress — consume this file when v3.3 is archived and /gsd-new-milestone re-runs
> (it goes straight to requirements → roadmap using the scope below).

## Version

**v4.0** (major) — ITAM asset-lifecycle is a new product pillar, distinct from the existing
security/observability CMDB. Major bump signals the scope.

## Goal

Add a full Snipe-IT-parity IT Asset Management lifecycle on top of the existing platform:
manage physical/virtual assets through procurement → assignment → maintenance → retirement,
with people checking gear in and out, licenses/consumables, and financial/warranty tracking —
turning the security-monitoring "asset inventory" into a true ITAM system.

## Why now / gap analysis (from codebase survey 2026-07-30)

The project today has a **security/observability CMDB** only: assets are auto-discovered
monitored endpoints (hostname/IP/OS/serial/type/criticality/vulns/patch-status), via
`asset_endpoints.py` + `AssetManagementDashboard`/`AssetIntelligenceDashboard`/`SoftwareInventoryTab`.
**All Snipe-IT ITAM lifecycle concepts are absent** (0 matches across backend): check-in/out,
assignment/ownership to a person, status lifecycle labels, licenses+seats, accessories/consumables/
components, warranty, depreciation, purchase/procurement, manufacturer/supplier/model catalog,
physical audit, asset tags/QR labels, requestable assets. `maintenance_service.py` is
maintenance-*windows* scheduling (not per-asset repair records); `software_endpoints.py` is
patch/deploy (not license seats).

## Target features (all 4 clusters IN scope)

### Cluster A — Lifecycle + check-in/out
- Assign assets to users and/or locations; check-out and check-in flows.
- Status lifecycle labels (deployable / deployed / archived / retired / disposed / broken).
- Assignment history / audit trail per asset.

### Cluster B — Procurement + finance
- Purchase cost, purchase date, PO number, supplier.
- Warranty tracking + expiry alerts.
- Depreciation schedules (straight-line at minimum).

### Cluster C — Catalog + org
- Manufacturers, asset models, categories, suppliers, locations.
- Custom fields on assets.
- Asset tags + QR/barcode label generation.

### Cluster D — Licenses + consumables
- Software license seats: assign / reclaim, seat counts, expiry.
- Accessories, consumables, components with check-out/quantities.

## Key context / constraints for requirements + roadmap

- **Reuse the existing asset surface, don't fork it.** New ITAM data should extend the existing
  `assets` model / `asset_endpoints.py` where sensible, and a manual-asset path is needed
  (Snipe-IT assets are hand-catalogued; current assets are agent-auto-discovered — the milestone
  must support assets that have NO agent).
- **Tenant isolation** applies to every new collection/endpoint (project-wide invariant).
- **Offline-first / air-gapped** posture is a platform value — label/QR generation and all data
  must work without external services.
- Admin-gated nav pages follow the established pattern (Phase 47 SecuritySettingsDashboard /
  Phase 48 FleetObservabilityDashboard): new AppView + App.tsx + Sidebar entry + permission gate.
- Files < 500 lines; validate input at boundaries; tests via `backend/venv/bin/python -m pytest`.
- Likely REQ categories (roadmapper to formalize): `ITAM-LIFE` (lifecycle/checkout),
  `ITAM-FIN` (procurement/finance/warranty/depreciation), `ITAM-CAT` (catalog/tags/labels),
  `ITAM-LIC` (licenses/consumables/accessories).

## Out of scope (explicit — for the requirements step)

- Deep accounting/GL integration beyond basic depreciation.
- Multi-currency finance.
- Physical RFID hardware integration (QR/barcode label generation only, not scanner drivers).
- Migrating the existing security CMDB semantics — ITAM is additive, not a replacement.

## Numbering / sequencing note

- Continue phase numbering from v3.3's last phase. v3.3 phase **49 (Fleet Geo Map / GMAP-01/02/03)**
  is being **deferred** at v3.3 close — decide during archive whether GMAP carries into v4.0 as its
  first phase or stays backlog. `999.1` (Remediation SLA Settings UI) remains backlog.
