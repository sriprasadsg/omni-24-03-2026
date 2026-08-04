# Requirements: v4.0

**Defined:** 2026-07-31
**Core Value:** Native Security & Autonomous Remediation capabilities.

## v1 Requirements

### Scale/Perf
- [ ] **SCALE-01**: Backend throughput supports 10x concurrent security scans.
- [ ] **SCALE-02**: Agent resource usage < 5% CPU/50MB RAM during scanning.

### Advanced Security (Correlation)
- [ ] **SEC-01**: Correlate FIM events with VULN findings.
- [ ] **SEC-02**: Threat intelligence correlation engine.

### Operator UX
- [ ] **UX-01**: Real-time security dashboard.
- [ ] **UX-02**: Interactive remediation playbook editor.

### SIEM/Ticketing Integrations
- [ ] **SIEM-01**: Splunk integration for event forwarding.
- [ ] **SIEM-02**: Jira integration for ticket sync.
- [ ] **SIEM-03**: ServiceNow integration for ticket sync.

## v2 Requirements
- [ ] **FUTURE-01**: Cloud Provider infrastructure management.

## v3.4 Requirements (completed — historical, milestone shipped 2026-08-04)

Restored for traceability only — this doc was overwritten to the v4.0 set above on 2026-07-31
without carrying forward the still-active v3.4 milestone's requirement IDs. Full v3.4 requirement
list (NSCAN-*/VULN-*/FIM-*/AUTO-*/INT-01..03) lives per-phase in ROADMAP.md phases 50-54; only the
phase-55 subset is restored here since that's the one a `mark-complete` call actually hit.

- [x] **AUT-03**: Predictive automated containment — UEBA shadow_ai anomaly triggers approval-gated
  remediation via `select_playbook()`'s anomaly branch. (Phase 55, plans 55-02/55-03)
- [x] **INT-04**: Threat intel feeds + correlation engine — `SiemEngine.correlate_native_findings()`
  + VirusTotal client. (Phase 55, plans 55-01/55-05)
- [x] **COMM-01**: Outbound syslog/SIEM webhook (OCSF) at correlation/anomaly/remediation pipeline
  points. (Phase 55, plan 55-04)

**Note:** this v4.0 doc's own Traceability table below maps `SCALE-01`/`SCALE-02` to "Phase 55" —
that phase number is already taken by the v3.4 "Advanced Threat Detection & Response" phase
(complete, see above). Whoever plans v4.0's Phase 55 needs a renumber before execution to avoid
colliding with real completed work.

## Out of Scope
| Feature | Reason |
|---------|--------|
| Third-party SIEM agents | Relying on native agent capability |

## Traceability
| Requirement | Phase | Status |
|-------------|-------|--------|
| SCALE-01 | Phase 55 | Pending |
| SCALE-02 | Phase 55 | Pending |
| SEC-01 | Phase 56 | Pending |
| SEC-02 | Phase 56 | Pending |
| UX-01 | Phase 57 | Pending |
| UX-02 | Phase 57 | Pending |
| SIEM-01 | Phase 58 | Pending |
| SIEM-02 | Phase 58 | Pending |
| SIEM-03 | Phase 58 | Pending |
