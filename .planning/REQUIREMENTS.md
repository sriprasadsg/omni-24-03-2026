# Requirements: Enterprise OmniAgent — v1.1 Evidence Quality & Compliance Scoring

**Defined:** 2026-06-20
**Core Value:** Any tenant can see exactly which compliance controls pass or fail across their endpoints — with trustworthy, current evidence and a numeric score to prove it.

## v1.1 Requirements

### Asset Compliance Status

- [x] **STATUS-01**: A user can manually mark an asset's compliance status for a specific control as Compliant or Non-Compliant from the control detail view; the change is persisted to the backend and immediately reflected in the UI
- [x] **STATUS-02**: Manual status overrides are scoped per-tenant and recorded with the actor's identity, timestamp, and the previous status (enabling reversal)

### Evidence Lifecycle

- [x] **STALE-01**: Automated evidence (agent-collected) older than a configurable threshold (default: 7 days) is flagged as stale in the control detail view and in the compliance report
- [ ] **STALE-02**: The staleness threshold is configurable per-tenant via the Settings page (minimum: 1 day, maximum: 365 days)
- [x] **COC-01**: Every create, update, and delete of an evidence record appends an immutable entry to a per-evidence chain-of-custody log: actor identity, action type, timestamp, and before/after snapshot
- [ ] **COC-02**: The chain-of-custody log for a control's evidence is viewable from the control detail view by users with audit-read permission

### Bulk Evidence Upload

- [ ] **BULK-01**: A user can upload a zip file containing multiple evidence files (PDF, PNG, JPEG, DOCX, XLSX) together with a JSON manifest that maps each file to a control ID
- [ ] **BULK-02**: Files in the zip are extracted and validated individually (MIME type, size ≤ 25 MB per file, magic bytes) before any are stored; the entire batch is rejected with a per-file error report if any file fails validation
- [ ] **BULK-03**: Successfully uploaded bulk evidence files appear in the same control detail view as individually uploaded evidence, with the same Manual badge and delete capability

### Compliance Score

- [ ] **SCORE-01**: Each tenant has a compliance score displayed on the main dashboard: percentage of controls passing across all monitored assets, computed at the time of the last evidence update
- [ ] **SCORE-02**: The compliance score is severity-weighted — Critical and High controls failing count more than Medium and Low — with the weighting visible in a tooltip or legend
- [ ] **SCORE-03**: The score is broken down by framework (e.g., SOC 2: 87%, ISO 27001: 72%) and can be expanded in a panel to show per-framework detail

### UI Carry-forward (from v1.0 UI Audit)

- [x] **UI-01**: Source badges ("Automated" / "Manual") in the evidence table use `text-xs` (12px) instead of `text-[10px]` to meet WCAG AA contrast at their color values

## Out of Scope

| Feature | Reason |
|---------|--------|
| Evidence version history (keeping old files on re-upload) | Storage complexity; chain-of-custody log provides the audit trail without full file versioning |
| Comment threads on controls | Distinct feature with its own UI surface; deferred to v1.2 |
| Scheduled auto-email reports | Requires email infrastructure not yet in scope |
| Jira/ServiceNow webhook for remediation tasks | Deferred to v1.2 remediation enhancements milestone |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| STATUS-01 | Phase 6 | Complete |
| STATUS-02 | Phase 6 | Complete |
| STALE-01 | Phase 7 | Complete |
| STALE-02 | Phase 7 | Pending |
| COC-01 | Phase 7 | Complete |
| COC-02 | Phase 7 | Pending |
| BULK-01 | Phase 8 | Pending |
| BULK-02 | Phase 8 | Pending |
| BULK-03 | Phase 8 | Pending |
| SCORE-01 | Phase 9 | Pending |
| SCORE-02 | Phase 9 | Pending |
| SCORE-03 | Phase 9 | Pending |
| UI-01 | Phase 6 | Complete |

**Coverage:**

- v1.1 requirements: 13 total
- Mapped to phases: 13
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-20*
*Last updated: 2026-06-20 after initial definition*
