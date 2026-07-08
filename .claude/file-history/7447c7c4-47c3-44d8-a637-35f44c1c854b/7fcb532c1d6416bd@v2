# Enterprise OmniAgent — Security & Compliance Portal

## What This Is

An AI-powered, multi-tenant security and compliance management platform. Deployed agents (Python and Rust) run on endpoints, collect security telemetry, and automatically generate evidence records mapped to 30+ compliance framework controls (SOC 2, ISO 27001, PCI-DSS, HIPAA, NIST CSF/800-53, CIS, GDPR, CMMC, FedRAMP, HITRUST, and more). MSP operators and their clients use the platform to monitor compliance posture, upload manual evidence, track remediation of failed controls, and export audit-ready reports.

## Core Value

Any tenant can see exactly which compliance controls pass or fail across their endpoints — with evidence proving it — at any moment.

## Requirements

### Validated

- ✓ Python agent collects compliance telemetry and sends heartbeats to backend — existing
- ✓ `compliance_evidence_processor` maps agent check names to framework control IDs and writes evidence records — existing
- ✓ 30+ compliance frameworks seeded in database (SOC 2, ISO 27001, PCI-DSS, HIPAA, NIST, CIS, GDPR, CMMC, FedRAMP, HITRUST, DORA, NIS2, and more) — existing
- ✓ Multi-tenant architecture with per-tenant data isolation — existing
- ✓ Compliance controls and evidence displayed in React frontend per control — existing
- ✓ Compliance reporting endpoints (PDF, Excel) partially implemented — existing

### Active

- [ ] **Rust agent evidence parity** — Rust agent heartbeat data feeds through `compliance_evidence_processor` identically to the Python agent; every control the Python agent populates, the Rust agent populates too
- [ ] **Manual evidence uploads** — Auditors can attach files, screenshots, and documents to individual controls for controls that cannot be auto-collected from endpoints
- [ ] **Audit-ready export** — Per-tenant, per-framework PDF/Excel export with control status, evidence links, and metadata ready to hand to an auditor
- [ ] **Remediation workflow** — Failed control triggers an assignable remediation task; task is tracked to resolution; re-scan is triggered; evidence is updated; control status advances to pass

### Out of Scope

- New compliance frameworks beyond those already seeded — the 30+ existing frameworks cover the stated scope; adding more is a future milestone
- Endpoint agent distribution/deployment tooling — agent install workflow already exists; this milestone is about evidence and compliance, not deployment
- Billing and subscription management — separate concern not related to compliance portal completeness

## Context

**Codebase state:** The platform is a brownfield FastAPI (Python) backend + React/TypeScript frontend. The backend has extensive compliance infrastructure — `compliance_evidence_processor.py` with `COMPLIANCE_CHECK_MAPPINGS` (agent check names → control IDs), `admin_evidence_service.py`, `evidence_automation_service.py`, `compliance_automation_service.py`, and 30+ framework definition files under `backend/frameworks/`. The Python agent at `agent-install/agent/` works end-to-end. The Rust agent at `agent-rust/` reports the same 40+ capability checks via heartbeat but does not currently wire through the evidence processor on the backend side.

**Multi-tenant:** Each tenant has isolated data. Compliance posture, evidence, and reports are scoped per tenant. MSP operators manage multiple tenants.

**Agent duality:** Two agents exist for the same purpose — Python agent (cross-platform, richer AI stack) and Rust agent (Windows-native service, lower footprint, no Python runtime). Both send heartbeats to the same backend endpoints. Evidence collection from the Python agent works; Rust agent compliance checks arrive in heartbeat `meta.compliance_enforcement` but backend processing parity is incomplete.

**Evidence processor:** `COMPLIANCE_CHECK_MAPPINGS` already maps 40+ check names to framework control IDs across ISO 27001 (A.x.x), PCI-DSS (PCI-x.x), SOC 2 (CC6.x), NIST CSF (PR./DE./ID.), HIPAA (164.xxx), FedRAMP, HITRUST. The processor is called from `agent_heartbeat_endpoints.py`.

**Codebase map:** `.planning/codebase/` contains full architecture, stack, conventions, and concerns analysis.

## Constraints

- **Tech stack**: FastAPI + SQLAlchemy + PostgreSQL backend; React + TypeScript + Vite frontend — no framework changes
- **Compatibility**: Rust agent must produce evidence records in the same schema as the Python agent so the frontend and reporting layer need no agent-type-specific logic
- **Security**: All evidence uploads must be scanned; file size limits enforced; tenant isolation must hold for uploaded files
- **File size**: Backend files must stay under 500 lines (per project conventions)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Rust agent evidence wired server-side (not client-side) | Backend already has `compliance_evidence_processor`; adding client-side mapping in Rust would duplicate and diverge | — Pending |
| Manual evidence stored as tenant-scoped file uploads, linked to control ID | Auditors need attachments, not just text notes; file-based evidence is standard in GRC tools | — Pending |
| Remediation tasks modelled as lightweight records (not full ticketing system) | Avoids scope creep; existing `ticket_reporter` capability can bridge to external ticketing | — Pending |
| Audit export reuses existing PDF/Excel infrastructure | `compliance_reporting_pdf.py` and `compliance_reporting_excel.py` already exist; extend rather than replace | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-17 after initialization*
