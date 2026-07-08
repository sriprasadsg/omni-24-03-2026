# Roadmap: Enterprise OmniAgent — Security & Compliance Portal

## Milestones

- **[v1.0](milestones/v1.0-ROADMAP.md)** — Security & Compliance Portal: Rust agent evidence parity, manual evidence uploads, audit-ready PDF/Excel export, remediation workflow. 5 phases, 11 plans, 16/16 requirements. Shipped 2026-06-18.
- **v1.1** — Evidence Quality & Compliance Scoring: compliance status wiring, staleness detection, bulk upload, chain-of-custody audit trail, tenant compliance score. 4 phases, 11 plans, SCORE-01/02/03 + STATUS-01/02 + STALE-01/02 + COC-01/02 + BULK-01/02/03 + UI-01. Shipped 2026-06-22.
- **v1.2** — Reporting Automation: scheduled compliance report generation and email delivery. 1 phase, SCHED-01/02.

## v1.1 — Evidence Quality & Compliance Scoring

**Goal:** Make the compliance evidence lifecycle trustworthy end-to-end — from first upload through audit export — by wiring the broken status buttons, adding staleness detection, bulk upload, an immutable audit trail, and a tenant-level compliance score.

**Status:** Complete — all 4 phases delivered, 415 tests pass

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

---

## v1.2 — Reporting Automation

**Goal:** Tenant admins can schedule compliance reports to be auto-generated and emailed on a recurring cadence, and view delivery history.

**Status:** Complete — Phase 10 delivered, SCHED-01/02 verified

---

## v1.3 — Security Hardening

**Goal:** Close the 3 open security and data-integrity findings from the Phase 8 code review: zip-bomb metadata bypass, bulk upload partial-write without DB rollback, and ContextVar tenant context leak on exception paths.

**Status:** Complete — Phase 11 delivered, SEC-01/02 verified

---

## v1.4 — Agentic AI Integration

**Goal:** Wire Claude tool-calling into the existing agentic decision loop so the LLM can autonomously reason about security findings, select security capabilities, and execute remediation actions — replacing the current stub handler with real Claude-powered decision-making.

**Status:** Complete — Phase 12 delivered, AI-01/02/03/04 verified

---

## v1.5 — AI Compliance Narratives

**Goal:** Wire the existing LLM (`ai_service.py:generate_text`) into the Phase 10 scheduled PDF report generator to add AI-generated executive summaries, per-framework findings narratives, and remediation priorities to each compliance report.

**Status:** Planned

---

## Phase 13: AI Compliance Report Narratives

**Goal:** Add LLM-generated narrative sections to scheduled compliance PDF reports — an executive summary of the tenant's compliance posture, per-framework findings narrative with top failing controls, and a prioritised remediation paragraph — using the existing `ai_service.py:generate_text` API wired into `_build_pdf` in `scheduled_reports_service.py`.

**Requirements:** AI-05, AI-06

**Plans:** 1 plan

- [ ] 13-01-PLAN.md — Backend TDD: `compliance_narrative_service.py` (_sanitise, _trim_to_words, NarrativeOutput, generate_executive_summary, generate_framework_narrative, enrich_report_data), wire into `_generate_report` / `_build_pdf` in scheduled_reports_service.py, 8-test suite (AI-05, AI-06)

---

## Phase 12: Agentic AI Integration

**Goal:** Wire Claude (claude-sonnet-4-6) tool-calling into the agentic_poller → execute_agentic_task path in the backend so the LLM can reason about live security findings, select from a defined tool set of security capabilities, and log each decision with reasoning and result for auditability. Graceful degradation to rule-based fallback when the API is unreachable.

**Requirements:** AI-01, AI-02, AI-03, AI-04

**Plans:** 2/2 plans complete

- [x] 12-01-PLAN.md — Backend TDD: `agentic_service.py` (AgenticService, two-turn Claude tool-calling, 5 tool schemas, fallback), `agentic_tasks_endpoints.py` (GET agentic-tasks + POST result), `agent_ai_decisions` MongoDB collection + indexes, router registration, 8-test suite (AI-01, AI-02, AI-03, AI-04)
- [x] 12-02-PLAN.md — Eval + Tracing: Arize Phoenix wiring in `app_startup.py`, Promptfoo eval harness with 5 reference fixtures and 0.85 pass threshold (AI-01, AI-02)

---

## Phase 11: Security Hardening

**Goal:** Fix three verified security/data-integrity gaps in the compliance evidence pipeline: replace spoofable ZipInfo metadata pre-check with bounded streaming, add DB-level rollback to the bulk evidence commit loop, and ensure ContextVar tenant context is cleaned up on exception paths.

**Requirements:** SEC-01, SEC-02, SEC-03

**Plans:** 1/1 plans complete

**Status:** Complete — Phase 11 delivered, SEC-01/02 verified

- [x] 11-01-PLAN.md — Backend TDD: `total_actual_bytes` cross-entry accumulator inside chunk while-loop replacing spoofable infolist pre-check (SEC-01); compensating `delete_many` DB rollback with `inserted_ids` tracking in commit-loop except block (SEC-02); 3 new/updated tests (14 total pass)

---

## Phase 10: Scheduled Compliance Reports

**Goal:** Tenant admins can configure a recurring report schedule (daily/weekly/monthly) per framework; the backend generates and emails a PDF compliance report to configured recipients on each run; delivery history is viewable from the Reports page.

**Requirements:** SCHED-01, SCHED-02

**Plans:** 2/2 plans executed — COMPLETE

Plans:

- [x] 10-01-PLAN.md — Backend TDD: framework_id schema, _generate_pdf wiring, delivery log collection, GET /history endpoint, SMTP validation (Wave 1)
- [x] 10-02-PLAN.md — Frontend: framework picker in create modal, run-now URL fix, per-card delivery history panel (Wave 2)
