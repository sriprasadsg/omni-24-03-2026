# Roadmap: Enterprise OmniAgent — Security & Compliance Portal

## Milestones

- **[v1.0](milestones/v1.0-ROADMAP.md)** — Security & Compliance Portal: Rust agent evidence parity, manual evidence uploads, audit-ready PDF/Excel export, remediation workflow. 5 phases, 11 plans, 16/16 requirements. Shipped 2026-06-18.

## v1.1 — Evidence Quality & Compliance Scoring

**Goal:** Make the compliance evidence lifecycle trustworthy end-to-end — from first upload through audit export — by wiring the broken status buttons, adding staleness detection, bulk upload, an immutable audit trail, and a tenant-level compliance score.

**Continues from Phase 6.**

| Phase | Name | Requirements | Status |
|-------|------|--------------|--------|
| 6 | Asset Compliance Status + UI Fix | STATUS-01, STATUS-02, UI-01 | Pending |
| 7 | Evidence Lifecycle (Staleness + Chain-of-Custody) | STALE-01, STALE-02, COC-01, COC-02 | Pending |
| 8 | Bulk Evidence Upload | BULK-01, BULK-02, BULK-03 | Pending |
| 9 | Compliance Score Dashboard | SCORE-01, SCORE-02, SCORE-03 | Pending |

### Phase 6 — Asset Compliance Status + UI Fix

**Goal:** Wire the Mark Compliant / Mark Non-Compliant buttons to a real backend endpoint so compliance status changes persist, and fix the source badge font-size WCAG violation from the v1.0 UI audit.

**Plans:**
- 06-01: Backend — `PATCH /api/assets/{asset_id}/compliance/status` endpoint, tenant-scoped, actor/timestamp/previous-status recorded
- 06-02: Frontend — wire `onUpdateStatus` in `AssetComplianceList.tsx` → API call + optimistic update; fix `text-[10px]` → `text-xs` (UI-01)

### Phase 7 — Evidence Lifecycle (Staleness + Chain-of-Custody)

**Goal:** Automated evidence older than the tenant-configured threshold is flagged stale; every evidence create/update/delete is appended to an immutable chain-of-custody log visible in the control detail view.

**Plans:**
- 07-01: Backend — staleness field on evidence records (default 7-day threshold, configurable per-tenant); chain-of-custody `evidence_audit_log` collection with actor/action/timestamp/snapshot
- 07-02: Frontend — stale badge on evidence rows past threshold; CoC log panel in control detail (collapsible, audit-read permission gate)

### Phase 8 — Bulk Evidence Upload

**Goal:** Auditors can upload a zip file + JSON manifest to attach multiple evidence files to multiple controls in one operation, with per-file validation before any are stored.

**Plans:**
- 08-01: Backend — `POST /api/compliance/evidence/bulk` endpoint; unzip in temp dir; validate each file (MIME, magic bytes, ≤25 MB); commit or reject with per-file error report
- 08-02: Frontend — bulk upload UI in control list header; zip + manifest upload form; per-file validation error display; success summary

### Phase 9 — Compliance Score Dashboard

**Goal:** Each tenant has a live compliance score (% controls passing, severity-weighted) visible on the main dashboard, broken down by framework.

**Plans:**
- 09-01: Backend — `GET /api/compliance/score` endpoint; severity-weighted score calculation; per-framework breakdown; cached per tenant on evidence update
- 09-02: Frontend — compliance score panel on dashboard; per-framework drill-down; severity weight legend tooltip
