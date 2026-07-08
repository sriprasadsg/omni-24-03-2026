# Enterprise OmniAgent — Security & Compliance Portal

## What This Is

An AI-powered, multi-tenant security and compliance management platform. Deployed agents (Python and Rust) run on endpoints, collect security telemetry, and automatically generate evidence records mapped to 30+ compliance framework controls (SOC 2, ISO 27001, PCI-DSS, HIPAA, NIST CSF/800-53, CIS, GDPR, CMMC, FedRAMP, HITRUST, and more). MSP operators and their clients use the platform to monitor compliance posture, upload manual evidence, track remediation of failed controls, and export audit-ready reports.

## Core Value

Any tenant can see exactly which compliance controls pass or fail across their endpoints — with evidence proving it — at any moment.

## Current State

**v1.0 shipped 2026-06-18 — all 4 new capabilities live:**

- Rust agent evidence parity — heartbeats feed `compliance_evidence_processor` identically to the Python agent; `agent_type: rust` preserved in evidence records
- Manual evidence uploads — auditors attach PDF/PNG/DOCX/XLSX (≤25 MB) to controls; magic-byte MIME validation; owner/admin delete with disk cleanup
- Audit-ready export — per-tenant PDF and Excel reports with tenant name, export date, Auto/Manual evidence columns, and STATUS_LEGEND (Pass/Fail/Partial/No-Data)
- Remediation workflow — failed control → assignable task → AI-suggested steps → mark Resolved → re-scan dispatch → real-time WebSocket status update
- Test suite: 378 passed, 0 failed, 1 skipped (baseline for v1.1)
- Cloud provider support expanded from 3 to 10 (AWS, GCP, Azure, OCI, IBM, Alibaba, DigitalOcean, Cloudflare, VMware, Huawei)

## Requirements

### Validated

- ✓ Python agent collects compliance telemetry and sends heartbeats to backend
- ✓ `compliance_evidence_processor` maps agent check names to framework control IDs and writes evidence records
- ✓ 30+ compliance frameworks seeded in database (SOC 2, ISO 27001, PCI-DSS, HIPAA, NIST, CIS, GDPR, CMMC, FedRAMP, HITRUST, DORA, NIS2, and more)
- ✓ Multi-tenant architecture with per-tenant data isolation
- ✓ Compliance controls and evidence displayed in React frontend per control
- ✓ Compliance reporting endpoints (PDF, Excel) with tenant headers and evidence source columns
- ✓ **Rust agent evidence parity** — Rust heartbeat data feeds `compliance_evidence_processor` identically to Python; `agent_type: rust` preserved (Phase 1)
- ✓ **Manual evidence uploads** — auditors attach files to controls; magic-byte MIME validation; owner/admin delete RBAC (Phase 2)
- ✓ **Audit-ready export** — per-tenant PDF/Excel with tenant name, export date, auto/manual evidence columns (Phase 3)
- ✓ **Remediation workflow** — task CRUD, AI suggest, re-scan dispatch, real-time WebSocket updates (Phase 4)

### Out of Scope

- New compliance frameworks beyond those already seeded — 30+ existing frameworks cover stated scope; adding more is a future milestone
- Endpoint agent distribution/deployment tooling — agent install workflow already exists; this milestone was about evidence and compliance
- Billing and subscription management — separate concern not related to compliance portal completeness

## Current Milestone: v1.1 — Evidence Quality & Compliance Scoring

**Status:** Planning | **Started:** 2026-06-20

**Goal:** Make the compliance evidence lifecycle trustworthy end-to-end — from first upload through audit export — by wiring the broken status buttons, adding staleness detection, bulk upload, an immutable audit trail, and a tenant-level compliance score operators can trust.

**Target features (13 requirements, 4 phases):**
- STATUS-01/02: Wire Mark Compliant / Mark Non-Compliant buttons to backend (`PATCH /api/assets/{id}/compliance/status`)
- STALE-01/02: Flag automated evidence older than configurable threshold (default 7 days) as stale
- COC-01/02: Immutable chain-of-custody log per evidence record (create/update/delete events)
- BULK-01/02/03: Bulk evidence upload via zip file + JSON manifest mapping files to control IDs
- SCORE-01/02/03: Tenant compliance score (severity-weighted %) with per-framework breakdown on dashboard
- UI-01: Source badge `text-[10px]` → `text-xs` WCAG AA fix (carry-forward from v1.0 audit F-08)

**Phase plan:** Phases 6–9 (continues v1.0 phase numbering)

---

## v2 Backlog Candidates

Previously labeled "Next Milestone Goals" — replaced by v1.1 scope above. Remaining candidates:

- AUDIT-V2-01: Scheduled report generation (auto-email)
- REM-V2-01: External ticketing system integration (Jira/ServiceNow webhook)
- REM-V2-02: SLA tracking for overdue remediation tasks
- Comment threads on controls
- 10-provider CSPM posture scans (OCI, IBM, Alibaba, DigitalOcean, Cloudflare, Huawei, VMware now supported)

## Context

**Codebase state (v1.0):** FastAPI (Python 3.12) backend + React/TypeScript frontend. All four compliance portal capabilities are live. `compliance_evidence_processor.py` with `COMPLIANCE_CHECK_MAPPINGS` maps 40+ check names to control IDs across 30+ frameworks. Both Python and Rust agents produce identically-structured evidence records. Manual upload endpoint at `/api/assets/{id}/compliance/evidence` with magic-byte validation. Compliance reporting at `/api/compliance-reports` generates PDF and XLSX with tenant headers and evidence source columns. Remediation workflow at `/api/compliance-remediation` with WebSocket real-time updates via `broadcast_remediation_update`. Integration test suite (`test_e2e_integration.py`) verifies all cross-tenant isolation boundaries.

**Multi-tenant:** Each tenant has isolated data. Compliance posture, evidence, reports, and remediation tasks are scoped per tenant. Five cross-tenant isolation boundaries verified in integration tests (report download, report list, task CRUD, evidence upload, first-heartbeat tenant assignment).

**Test baseline:** 378 passed, 0 failed, 1 skipped across 11 test files. 92 cross-test isolation failures from `importlib.reload()` contamination and Python 3.12 asyncio event-loop lifecycle fixed in post-milestone cleanup.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Rust agent evidence wired server-side (not client-side) | Backend already has `compliance_evidence_processor`; adding client-side mapping in Rust would duplicate and diverge | Done — `agent_type` kwarg passed from heartbeat endpoint; 0 Rust-side changes needed |
| Manual evidence stored as tenant-scoped file uploads, linked to control ID | Auditors need attachments, not just text notes; file-based evidence is standard in GRC tools | Done — upload/delete endpoints, magic-byte MIME validation, disk cleanup |
| Remediation tasks modelled as lightweight records (not full ticketing system) | Avoids scope creep; existing `ticket_reporter` capability can bridge to external ticketing | Done — `compliance_remediation_tasks` collection, CRUD + AI suggest; Jira bridge deferred to v1.1 |
| Audit export reuses existing PDF/Excel infrastructure | `compliance_reporting_pdf.py` and `compliance_reporting_excel.py` already exist; extend rather than replace | Done — tenant header and Auto/Manual evidence columns added to both; STATUS_LEGEND constant |
| asyncio.run() over pytest-asyncio in tests | pytest-asyncio not installed; asyncio.run() creates fresh loop per call, no Python 3.12 lifecycle issues | Done — consistent across all 7 test files added in v1.0 |
| compliance_remediation_tasks collection name | Avoids collision with `remediation_tasks` used by continuous_compliance_service | Done |
| broadcast_remediation_update list() snapshot copy | Prevents set-mutation-during-iteration; matches broadcast_mitre_heatmap pattern | Done |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-20 — v1.0 milestone archived*
