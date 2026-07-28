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

**v1.1 Phase 6 shipped 2026-06-21:**

- Compliance status override — `PATCH /api/assets/{id}/compliance/status` with tenant isolation, immutable `status_history` (changedBy/changedAt/previous_status), and `manual_override` flag
- Frontend wired — "Mark Compliant / Mark Non-Compliant" buttons in `AssetComplianceList` call backend endpoint; success refreshes data, failure shows toast error
- WCAG AA badge fix — evidence source badges use `text-xs` (previously non-standard `text-[10px]`)

## Requirements

### Validated

- ✓ **Compliance status override** — PATCH endpoint persists status with immutable history, tenant isolation, manual_override flag (Phase 6)
- ✓ **Frontend status buttons wired** — Mark Compliant/Non-Compliant call backend; toast on error; data refresh on success (Phase 6)
- ✓ **WCAG AA source badges** — text-xs replaces text-[10px] for evidence source badges (Phase 6 / UI-01)
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

## Current Milestone: v3.2 — Agent Modernization & Remediation Ops

**Status:** Complete — all 10 requirements verified (Phases 40-45; see .planning/v3.2-MILESTONE-AUDIT.md) | **Started:** 2026-07-20

**Goal:** Finish the Rust agent 2.1.x dependency modernization and the outstanding 401 auth-session bug, then close real (verified, not assumed) gaps in remediation operations — bridging remediation tasks to existing ticketing connectors, SLA/escalation on overdue tasks, comment threads on controls, and CSPM checks for the 3 cloud providers that are currently dropdown-only stubs.

**Target features:**
- Rust agent 2.1.x dependency modernization — reqwest 0.12→0.13, sysinfo 0.32→0.39, tokio-tungstenite 0.23→0.30, rusqlite 0.32→0.40, hostname 0.3→0.4, serde_yaml→serde_yml/serde_norway migration (only `src/config.rs`), 2.1.3 exe rebuild (corrected from 2.1.0 — 2.1.0/2.1.1/2.1.2 already shipped; HANDOFF task 11, shipping tree = `agent-install/omni-agent-rs`)
- 401 Unauthorized auth-session bug investigation (HANDOFF task 10, never investigated)
- Remediation-to-ticketing bridge: wire `compliance_remediation_service` task create/update to the existing Jira/ServiceNow connectors in `ticketing_service.py` — reuse, don't rebuild (currently zero overlap; connectors only serve security-alert tickets)
- SLA/escalation for compliance remediation tasks: `due_date` breach detection + escalation scoped to `compliance_remediation_tasks` (existing `tickets_escalation_service.py` is a different domain, not reusable as-is)
- Comment threads on compliance controls: new `control_id`-linked comment model/endpoint/UI (genuinely absent; can clone `tickets_endpoints.py`'s comment-thread pattern)
- CSPM posture checks for OCI, Alibaba, Cloudflare — real check definitions and `RUNNABLE_PROVIDERS` inclusion (currently allowlisted but zero check logic; DigitalOcean already has real checks, IBM/Huawei/VMware are not cloud providers in this platform — those names only exist as unrelated SIEM/EDR integrations)

**Phase plan:** Phases 40-45 — all executed and verified (40 Rust Modernization & Session Reliability, 41 CSPM Expansion, 42 Comment Threads, 43 Ticketing Bridge, 44 SLA & Escalation, 45 close RUST-01 TLS gap)

---

## v2 Backlog Candidates

(none currently — the prior list was mostly stale: scheduled-report auto-email was already shipped in Phase 10, and ticketing/SLA/comment-threads/CSPM-providers were promoted into the v3.2 milestone above after verification against the actual codebase, 2026-07-20)

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
| Provider-allowlist widening (Phase 25, CHK-01) touches all 4 duplicated gate locations in lockstep, not just the named execution gate | Leaving account registration narrower than execution would leave the multi-account UI flow still broken | Done — `cloud_checks_service.py`, `cloud_checks_endpoints.py`, `cloud_account_endpoints.py`, `mcp_server_endpoints.py` all widened together |
| CloudFormation container-scan "simulated" data is labeled, not fail-closed (Phase 25, CHK-03) | Labeled simulated data is more useful to the user than an empty/error result when Trivy isn't installed; matches the existing `finops_service` simulated-spend precedent | Done — explicit `simulated` field + SIMULATED badge at 3 dashboard sites, verified via live browser run, not just code inspection |

**Note (2026-07-06, resolved 2026-07-20):** This file's Requirements/Milestone sections had drifted since v1.1 and weren't kept current through v2.0/v2.1/v3.0/v3.1 — a pre-existing maintenance gap. Corrected at the v3.2 milestone kickoff (2026-07-20): Current Milestone and v2 Backlog Candidates rewritten against verified codebase state (one backlog item, scheduled-report auto-email, turned out to already be shipped in Phase 10). The Validated/Out of Scope requirement lists below still predate v2.0+ and remain a known gap — full catch-up still deferred to a proper `/gsd-complete-milestone` pass.

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-29 — v3.2 milestone shipped (Phases 40-45, 10/10 requirements; see .planning/milestones/v3.2-ROADMAP.md)*
