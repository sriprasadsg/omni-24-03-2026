# Roadmap: Enterprise OmniAgent — Security & Compliance Portal

## Milestones

- **[v1.0](milestones/v1.0-ROADMAP.md)** — Security & Compliance Portal: Rust agent evidence parity, manual evidence uploads, audit-ready PDF/Excel export, remediation workflow. 5 phases, 11 plans, 16/16 requirements. Shipped 2026-06-18.

## v1.1 — Evidence Quality & Compliance Scoring

**Goal:** Make the compliance evidence lifecycle trustworthy end-to-end — from first upload through audit export — by wiring the broken status buttons, adding staleness detection, bulk upload, an immutable audit trail, and a tenant-level compliance score.

---

## Phase 6: Asset Compliance Status + UI Fix

**Goal:** Wire the Mark Compliant / Mark Non-Compliant buttons to a real backend endpoint so compliance status changes persist, and fix the source badge font-size WCAG violation from the v1.0 UI audit.

**Requirements:** STATUS-01, STATUS-02, UI-01

**Plans:**

2/2 plans complete

2/2 plans complete

- [x] 06-02-PLAN.md

1/2 plans executed

- 06-02: Frontend — wire `onUpdateStatus` in `AssetComplianceList.tsx` → API call + optimistic update; fix `text-[10px]` → `text-xs` (UI-01)

---

## Phase 7: Evidence Lifecycle (Staleness + Chain-of-Custody)

**Goal:** Automated evidence older than the tenant-configured threshold is flagged stale; every evidence create/update/delete is appended to an immutable chain-of-custody log visible in the control detail view.

**Requirements:** STALE-01, STALE-02, COC-01, COC-02

**Plans:** 3/3 plans complete

- [x] 07-01-PLAN.md — Backend helpers: `evidence_staleness.py` (read-time staleness), `evidence_coc.py` (immutable CoC append), `evidence_audit_log` indexes, Wave-0 tests (STALE-01, COC-01 foundation)
- [x] 07-02-PLAN.md — Backend endpoints: staleness settings GET/PATCH + CoC read endpoints, 4 CoC interceptors, staleness injection into evidence GET, router registration, integration tests (STALE-01/02, COC-01/02)
- [x] 07-03-PLAN.md — Frontend: amber stale badge, Evidence settings tab, collapsible Chain-of-Custody panel gated on `view:audit_log`, API service functions (STALE-01/02, COC-02)

---

## Phase 8: Bulk Evidence Upload

**Goal:** Auditors can upload a zip file + JSON manifest to attach multiple evidence files to multiple controls in one operation, with per-file validation before any are stored.

**Requirements:** BULK-01, BULK-02, BULK-03

**Plans:** 2/2 plans complete

- [x] 08-01-PLAN.md — Backend: POST /api/compliance/evidence/bulk endpoint, validate-all-before-commit, zip-bomb/zip-slip guards, CoC integration, router registration, test suite (BULK-01, BULK-02, BULK-03)
- [x] 08-02-PLAN.md — Frontend: BulkEvidenceUploadModal.tsx, FrameworkDetail trigger button, uploadBulkEvidence in apiService, per-file 422 error display, success summary (BULK-01, BULK-02, BULK-03)

---

## Phase 9: Compliance Score Dashboard

**Goal:** Each tenant has a live compliance score (% controls passing, severity-weighted) visible on the main dashboard, broken down by framework.

**Requirements:** SCORE-01, SCORE-02, SCORE-03

**Plans:** 2/2 plans complete

- [x] 09-01-PLAN.md — Backend: compliance_score_endpoints.py, severity-weighted aggregation, cache invalidation on 6 write paths, router registration, 8-test suite (SCORE-01, SCORE-02, SCORE-03)
- [x] 09-02-PLAN.md — Frontend: ComplianceScorePanel.tsx with overall gauge, per-framework accordion, severity weight tooltip; Dashboard.tsx mount; fetchComplianceScore in apiService; FrameworkScore types (SCORE-01, SCORE-02, SCORE-03)
