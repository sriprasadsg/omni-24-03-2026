# Requirements: Enterprise OmniAgent — Security & Compliance Portal

**Defined:** 2026-06-17
**Core Value:** Any tenant can see exactly which compliance controls pass or fail across their endpoints — with evidence proving it — at any moment.

## v1 Requirements

### Rust Agent Evidence Parity

- [x] **RUST-01**: Rust agent heartbeat compliance data (`meta.compliance_enforcement`) is processed by `compliance_evidence_processor` with identical logic to the Python agent
- [x] **RUST-02**: Evidence records written by the Rust agent appear in the same DB schema and format as Python agent evidence, with `agent_type: rust` metadata preserved
- [x] **RUST-03**: All 12 compliance checks the Rust agent reports (Firewall Profiles, Windows Defender, BitLocker Encryption, User Access Control, Remote Desktop Service, SMBv1 Protocol Disabled, Password Policy, Audit Logging Policy, Windows Update Service, PowerShell Script Block Logging, WinRM Status, Secure Boot) produce evidence records mapped to the correct framework control IDs via `COMPLIANCE_CHECK_MAPPINGS`

### Manual Evidence Uploads

- [x] **EVID-01**: Authenticated user can upload a file (PDF, PNG, JPEG, DOCX, XLSX — max 25 MB) as evidence for a specific compliance control
- [x] **EVID-02**: Uploaded evidence is stored per-tenant with control ID, uploader identity, timestamp, and user-provided description
- [x] **EVID-03**: Uploaded evidence appears alongside automated (agent-collected) evidence in the control detail view in the frontend
- [x] **EVID-04**: User can delete their own uploaded evidence; admin can delete any tenant's uploaded evidence
- [x] **EVID-05**: File uploads are validated against an allowlist of MIME types and rejected if the type does not match the extension

### Audit-Ready Export

- [x] **AUDIT-01**: User can export a compliance report for a selected framework as PDF showing: framework name, tenant name, export date, list of controls with Pass/Fail/Partial/No-Data status, and evidence count per control
- [x] **AUDIT-02**: User can export the same report as Excel (XLSX) with one row per control and evidence summary in columns
- [x] **AUDIT-03**: Export includes both automated evidence (agent-collected) and manual evidence (uploaded files) per control, clearly labelled by source
- [x] **AUDIT-04**: Export is strictly scoped per-tenant — a tenant user only sees and exports their own compliance data; cross-tenant data never appears in an export

### Remediation Workflow

- [x] **REM-01**: A failed or non-compliant control can have a remediation task created, with title, assignee (agent or user), due date, and description
- [x] **REM-02**: Remediation tasks are listed in a dedicated view with filterable status: Open, In Progress, Resolved
- [x] **REM-03**: When a remediation task is marked Resolved, a re-scan instruction is dispatched to the assigned agent for the associated control
- [x] **REM-04**: Control compliance status updates automatically when new evidence arrives post-remediation, reflecting the latest agent check result

## v2 Requirements

### Enhanced Evidence Management

- **EVID-V2-01**: Evidence expiry — automated evidence older than a configurable threshold is flagged as stale
- **EVID-V2-02**: Evidence chain-of-custody log — immutable audit trail of who created, updated, or deleted each evidence record
- **EVID-V2-03**: Bulk evidence upload — zip file containing multiple evidence files mapped to multiple controls via a manifest

### Advanced Reporting

- **AUDIT-V2-01**: Scheduled report generation — auto-email audit report on a recurring schedule (daily/weekly/monthly)
- **AUDIT-V2-02**: Trend view — control pass rate over time (30/60/90 day graph)
- **AUDIT-V2-03**: Cross-framework gap analysis — controls failing across multiple frameworks highlighted in a single view

### Remediation Enhancements

- **REM-V2-01**: Remediation task integration with external ticketing systems (Jira, ServiceNow) via webhook
- **REM-V2-02**: SLA tracking — overdue remediation tasks escalated and highlighted
- **REM-V2-03**: Remediation playbook suggestions — AI-suggested fix steps based on the failed control type

## Out of Scope

| Feature | Reason |
|---------|--------|
| New compliance framework definitions | 30+ frameworks already seeded; adding more is a future milestone |
| Agent deployment / installation tooling | Agent install workflow already exists; this milestone is about evidence and compliance |
| Billing and subscription management | Separate concern, not compliance-portal scope |
| Real-time agent streaming evidence | Current pull model (heartbeat) is sufficient; push streaming is a future optimisation |
| Cross-tenant benchmarking | MSP-level aggregate analytics deferred to v2+ |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| RUST-01 | Phase 1 | Complete (01-01) |
| RUST-02 | Phase 1 | Complete (01-01) |
| RUST-03 | Phase 1 | Complete (01-01) |
| EVID-01 | Phase 2 | Complete (02-01) |
| EVID-02 | Phase 2 | Complete (02-01) |
| EVID-03 | Phase 2 | Complete (02-02) |
| EVID-04 | Phase 2 | Complete (02-01) |
| EVID-05 | Phase 2 | Complete (02-01) |
| AUDIT-01 | Phase 3 | Complete (03-02) |
| AUDIT-02 | Phase 3 | Complete (03-02) |
| AUDIT-03 | Phase 3 | Complete (03-01, 03-02) |
| AUDIT-04 | Phase 3 | Complete (03-01) |
| REM-01 | Phase 4 | Complete |
| REM-02 | Phase 4 | Complete |
| REM-03 | Phase 4 | Complete |
| REM-04 | Phase 4 | Complete |

**Coverage:**
- v1 requirements: 16 total
- Mapped to phases: 16
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-17*
*Last updated: 2026-06-20 — all 16 v1 requirements marked complete; milestone v1.0 archived*
