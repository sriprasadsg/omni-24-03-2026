# Requirements: Enterprise OmniAgent — v1.1 Evidence Quality & Compliance Scoring

**Defined:** 2026-06-20
**Core Value:** Any tenant can see exactly which compliance controls pass or fail across their endpoints — with trustworthy, current evidence and a numeric score to prove it.

## v1.1 Requirements

### Asset Compliance Status

- [x] **STATUS-01**: A user can manually mark an asset's compliance status for a specific control as Compliant or Non-Compliant from the control detail view; the change is persisted to the backend and immediately reflected in the UI
- [x] **STATUS-02**: Manual status overrides are scoped per-tenant and recorded with the actor's identity, timestamp, and the previous status (enabling reversal)

### Evidence Lifecycle

- [x] **STALE-01**: Automated evidence (agent-collected) older than a configurable threshold (default: 7 days) is flagged as stale in the control detail view and in the compliance report
- [x] **STALE-02**: The staleness threshold is configurable per-tenant via the Settings page (minimum: 1 day, maximum: 365 days)
- [x] **COC-01**: Every create, update, and delete of an evidence record appends an immutable entry to a per-evidence chain-of-custody log: actor identity, action type, timestamp, and before/after snapshot
- [x] **COC-02**: The chain-of-custody log for a control's evidence is viewable from the control detail view by users with audit-read permission

### Bulk Evidence Upload

- [x] **BULK-01**: A user can upload a zip file containing multiple evidence files (PDF, PNG, JPEG, DOCX, XLSX) together with a JSON manifest that maps each file to a control ID
- [x] **BULK-02**: Files in the zip are extracted and validated individually (MIME type, size ≤ 25 MB per file, magic bytes) before any are stored; the entire batch is rejected with a per-file error report if any file fails validation
- [x] **BULK-03**: Successfully uploaded bulk evidence files appear in the same control detail view as individually uploaded evidence, with the same Manual badge and delete capability

### Compliance Score

- [x] **SCORE-01**: Each tenant has a compliance score displayed on the main dashboard: percentage of controls passing across all monitored assets, computed at the time of the last evidence update
- [x] **SCORE-02**: The compliance score is severity-weighted — Critical and High controls failing count more than Medium and Low — with the weighting visible in a tooltip or legend
- [x] **SCORE-03**: The score is broken down by framework (e.g., SOC 2: 87%, ISO 27001: 72%) and can be expanded in a panel to show per-framework detail

### UI Carry-forward (from v1.0 UI Audit)

- [x] **UI-01**: Source badges ("Automated" / "Manual") in the evidence table use `text-xs` (12px) instead of `text-[10px]` to meet WCAG AA contrast at their color values

## v1.2 Requirements

### Scheduled Reports

- [x] **SCHED-01**: A tenant admin can configure a report schedule (daily / weekly / monthly) per framework; on each scheduled run the backend generates a PDF compliance report and emails it to one or more configured recipient addresses
- [x] **SCHED-02**: The scheduled report delivery history (run timestamp, framework, recipient addresses, delivery status) is viewable from the Reports page; failed deliveries surface an error message

## v1.3 Requirements

### Security Hardening

- [x] **SEC-01**: The bulk evidence zip upload endpoint validates total uncompressed size using bounded streaming reads (not spoofable ZipInfo metadata), so a crafted zip with falsified `file_size=0` entries cannot bypass the 200 MB uncompressed guard
- [x] **SEC-02**: The bulk evidence commit loop performs DB-level rollback (deletes already-inserted `control_evidence` records) on any mid-batch exception, so a partial batch failure never leaves orphaned evidence records in the database
- [ ] **SEC-03**: The ContextVar tenant context (`tenant_context.py`) is cleaned up on exception paths — a request that errors mid-flight cannot leak its tenant ID into the next async task running on the same thread

## v1.4 Requirements

### Agentic AI Integration

- [x] **AI-01**: The backend agentic task endpoint uses Claude (claude-sonnet-4-6) with structured tool-calling to reason about the agent's security context and select which capability to invoke — replacing the current stub that ignores the LLM response
- [x] **AI-02**: Claude has access to ≥ 5 security capability tools (compliance check, vulnerability scan, threat hunt, persistence scan, process snapshot) defined as JSON tool schemas; the LLM-selected tool is dispatched to the agent via the existing instruction channel
- [x] **AI-03**: Each agentic LLM invocation is logged with reasoning chain, selected tool, input parameters, agent response, and outcome — stored in an `agent_ai_decisions` collection per-tenant for auditability
- [x] **AI-04**: The agentic task path degrades gracefully when the Claude API is unreachable — falls back to existing rule-based decisions rather than erroring or blocking the agent

## v1.5 Requirements

### AI Compliance Narratives

- [ ] **AI-05**: The scheduled compliance PDF report includes an AI-generated executive summary paragraph (≤ 150 words) describing the tenant's overall compliance posture for the reporting period; the summary is generated by `ai_service.generate_text` and injected into `_build_pdf` before the metrics table
- [ ] **AI-06**: Each framework section in the PDF includes an AI-generated findings narrative (≤ 200 words per framework) that names the top 3 failing controls by name and suggests remediation priorities in plain language; narrative generation failures are logged and fall back to a static template so report delivery is never blocked

## Out of Scope

| Feature | Reason |
|---------|--------|
| Evidence version history (keeping old files on re-upload) | Storage complexity; chain-of-custody log provides the audit trail without full file versioning |
| Comment threads on controls | Distinct feature with its own UI surface; deferred to v1.2+ |
| Jira/ServiceNow webhook for remediation tasks | Deferred to a future milestone |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| STATUS-01 | Phase 6 | Complete |
| STATUS-02 | Phase 6 | Complete |
| STALE-01 | Phase 7 | Complete |
| STALE-02 | Phase 7 | Complete |
| COC-01 | Phase 7 | Complete |
| COC-02 | Phase 7 | Complete |
| BULK-01 | Phase 8 | Complete |
| BULK-02 | Phase 8 | Complete |
| BULK-03 | Phase 8 | Complete |
| SCORE-01 | Phase 9 | Complete |
| SCORE-02 | Phase 9 | Complete |
| SCORE-03 | Phase 9 | Complete |
| UI-01 | Phase 6 | Complete |
| SCHED-01 | Phase 10 | Complete |
| SCHED-02 | Phase 10 | Complete |
| SEC-01 | Phase 11 | Complete |
| SEC-02 | Phase 11 | Complete |
| SEC-03 | Phase 11 | Planned |
| AI-01 | Phase 12 | Complete |
| AI-02 | Phase 12 | Complete |
| AI-03 | Phase 12 | Complete |
| AI-04 | Phase 12 | Complete |
| AI-05 | Phase 13 | Planned |
| AI-06 | Phase 13 | Planned |

**Coverage:**

- v1.1 requirements: 13 total, all complete
- v1.2 requirements: 2 total, all complete
- v1.3 requirements: 3 total, 2 complete
- v1.4 requirements: 4 total, all complete
- v1.5 requirements: 2 total, 0 complete
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-20*
*Last updated: 2026-06-22 after Phase 12 bootstrapped*
