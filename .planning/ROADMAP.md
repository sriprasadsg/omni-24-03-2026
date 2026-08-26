# Roadmap: Enterprise OmniAgent — Security & Compliance Portal

## Milestones

- ✅ **[v1.0](milestones/v1.0-ROADMAP.md)** — Security & Compliance Portal: Rust agent evidence parity, manual evidence uploads, audit-ready PDF/Excel export, remediation workflow. 5 phases, 11 plans, 16/16 requirements. Shipped 2026-06-18.
- ✅ **v1.1** — Evidence Quality & Compliance Scoring: compliance status wiring, staleness detection, bulk upload, chain-of-custody audit trail, tenant compliance score. 4 phases, 11 plans, SCORE-01/02/03 + STATUS-01/02 + STALE-01/02 + COC-01/02 + BULK-01/02/03 + UI-01. Shipped 2026-06-22.
- ✅ **v1.2** — Reporting Automation: scheduled compliance report generation and email delivery. 1 phase, SCHED-01/02.
- ✅ **v1.3** — Security Hardening: zip-bomb metadata bypass, bulk-upload DB rollback, ContextVar tenant-context leak. 1 phase, SEC-01/02/03.
- ✅ **v1.4** — Agentic AI Integration: Claude tool-calling wired into the agentic decision loop for autonomous security-finding reasoning and remediation. 1 phase, AI-01/02/03/04.
- ✅ **v1.5** — AI Compliance Narratives: LLM-generated executive summaries, findings narratives, and remediation priorities in scheduled PDF reports. 1 phase, AI-05/06.
- ✅ **v2.0** — GRC Feature Parity: 9 phases (14–22) closing competitive gaps vs Comp AI, Probo, OpenLane, Prowler. Complete — verified 2026-07-05.
- ✅ **v2.1** — Windows PowerShell Evidence + IaC/Container Security: full PowerShell evidence collection for all 28 Windows compliance checks, rebuilt installers (PS1, EXE/Inno Setup), dedicated ingestion API, evidence display updates (Phase 23); IaC (Terraform/CloudFormation/K8s) and container image scanning (Phase 24). Complete — verified 2026-07-05.
- ✅ **v3.0** — Competitive Feature Closure: 14 phases (25–38) closing the 25 gaps from the 2026-07-06 feature-parity audit against Comp AI, Probo, OpenLane Core, and Prowler — cloud-check execution gaps, vendor/risk data completeness, OSCAL/SBOM export, governance documents, a real public Trust Center, AI questionnaire auto-answer, FAIR risk quantification, provider expansion, workflow connectors, passkeys, GraphQL, ReBAC, a spec-compliant MCP server, and an interactive AI security assistant. Complete 2026-07-14.
- ✅ **v3.1** — AI Orchestration Layer: unified LangChain 1.x orchestration (`create_agent` + `init_chat_model`) across the AI compliance auditor, chat assistant, questionnaire auto-answer, and narrative generation surfaces, with citation-required structured outputs, tenant-scoped tools, and an evaluation harness (8 dimensions, Phoenix tracing). 1 phase (39), 12 plans. Complete — UAT 2026-07-19: 7 passed, 0 issues, 2 blocked on live gateway (nightly judged run, 9router passthrough re-test).
- ✅ **[v3.2](milestones/v3.2-ROADMAP.md)** — Agent Modernization & Remediation Ops: Rust agent 2.1.x dependency modernization + intermittent-401 root-cause fix, Jira/ServiceNow ticketing bridge, SLA/escalation on overdue remediation tasks, comment threads on compliance controls, and real CSPM checks for OCI/Alibaba/Cloudflare. 7 phases (40–45), 19 plans, 10/10 requirements. Shipped 2026-07-29. Gap-closure Phase 62 (Settings UI) promoted from backlog 2026-08-10, tracked below.
- ✅ **[v3.3](milestones/v3.3-ROADMAP.md)** — Agent Geo & Fleet Observability: fleet geo map (air-gapped bundled-SVG, clustering, tenant/status filters), location-based security (agent-scoped impossible-travel, alert-only geo-fencing, heuristic VPN/hosting flag), fleet observability (metrics-history charts, uptime timeline, offline + version-drift view), and an immutable per-agent location-history audit trail. 4 phases (46–49), 23 plans, 11/11 requirements. Audit passed. Shipped 2026-07-30.
- ✅ **[v3.4](milestones/v3.4-ROADMAP.md)** — Native Security Scanning & Autonomous Remediation Agent: built-in file/URL/IP/hash scanning (VirusTotal-like), vulnerability detection (Wazuh-like FIM/config-assessment/vuln-detection), file integrity monitoring, and autonomous remediation via playbook system. No external SIEM dependencies. 6 phases (50–55), 19 requirements. Shipped 2026-08-04. Gap-closure phases 63–66 (RBAC/label UI, rotate_key remediation, FIM process attribution, full YARA engine) promoted from backlog 2026-08-11 through 2026-08-23, tracked below.
- ✅ **[v4.0](milestones/v4.0-ROADMAP.md)** — ITAM (IT Asset Management Lifecycle): Snipe-IT-parity asset lifecycle on top of the existing security CMDB — catalog & manual asset cataloging, check-out/check-in with append-only assignment history, offline QR/barcode labels, procurement/warranty/depreciation, software licenses & consumables, and an admin-gated ITAM console. 6 phases (56–61), 17 plans, 17/17 requirements. Shipped 2026-08-10.
- ✅ **[v4.1](milestones/v4.1-ROADMAP.md)** — ITAM-Backlog: closed the gap between the ITAM console and Snipe-IT — user management (LDAP/SAML/2FA/API tokens), custom fields/audit trail/CSV import-export/global settings, procurement & asset workflow, reporting & dashboards, REST API & integrations. 5 phases (69–73), 26 plans, 24/24 requirements. Shipped 2026-08-26. Phases 69/70/72/73 closed `human_needed` (live-environment-only checks, accepted as override); Phase 71 fully `passed`.

## Phases

<details>
<summary>✅ v1.1 — Evidence Quality & Compliance Scoring (Phases 6–9) — SHIPPED 2026-06-22</summary>

- [x] Phase 6: Asset Compliance Status + UI Fix
- [x] Phase 7: Evidence Lifecycle (Staleness + Chain-of-Custody)
- [x] Phase 8: Bulk Evidence Upload
- [x] Phase 9: Compliance Score Dashboard

</details>

<details>
<summary>✅ v1.2 — Reporting Automation (Phase 10)</summary>

- [x] Phase 10: Scheduled Compliance Reports

</details>

<details>
<summary>✅ v1.3 — Security Hardening (Phase 11)</summary>

- [x] Phase 11: Security Hardening

</details>

<details>
<summary>✅ v1.4 — Agentic AI Integration (Phase 12)</summary>

- [x] Phase 12: Agentic AI Integration

</details>

<details>
<summary>✅ v1.5 — AI Compliance Narratives (Phase 13)</summary>

- [x] Phase 13: AI Compliance Report Narratives

</details>

<details>
<summary>✅ v2.0 — GRC Feature Parity (Phases 14–22) — verified 2026-07-05</summary>

- [x] Phase 14: SaaS Evidence Integration
- [x] Phase 15: Evidence Review Workflow
- [x] Phase 16: Program Control Grouping
- [x] Phase 17: Cloud Checks Expansion
- [x] Phase 18: Privacy & Legal Modules
- [x] Phase 19: Additional Compliance Frameworks
- [x] Phase 20: Multi-Account Cloud Scanning
- [x] Phase 21: Notification Routing & Domain Scanner
- [x] Phase 22: API Extensions

</details>

<details>
<summary>✅ v2.1 — Windows PowerShell Evidence + IaC/Container Security (Phases 23–24) — verified 2026-07-05</summary>

- [x] Phase 23: Windows PowerShell Evidence Collection
- [x] Phase 24: IaC & Container Security

</details>

<details>
<summary>✅ v3.0 — Competitive Feature Closure (Phases 25–38) — complete 2026-07-14</summary>

- [x] Phase 25: Cloud Checks Execution Gaps
- [x] Phase 26: Vendor and Risk Data Completeness
- [x] Phase 27: Compliance Export Formats (OSCAL and SBOM)
- [x] Phase 28: Governance Document Management
- [x] Phase 29: Public Trust Center
- [x] Phase 30: AI Questionnaire Auto-Answer
- [x] Phase 31: FAIR Risk Quantification
- [x] Phase 32: Cloud and SaaS Provider Expansion
- [x] Phase 33: Workflow Automation Connectors
- [x] Phase 34: Passkey and WebAuthn Authentication
- [x] Phase 35: GraphQL API
- [x] Phase 36: Fine-Grained Relationship-Based Authorization
- [x] Phase 37: Spec-Compliant MCP Server
- [x] Phase 38: Interactive AI Security Assistant

</details>

<details>
<summary>✅ v3.1 — AI Orchestration Layer (Phase 39) — UAT 2026-07-19</summary>

- [x] Phase 39: LangChain AI Integration

</details>

<details>
<summary>✅ v3.4 gap-closure backlog (Phases 62–66) — promoted 2026-08-10 through 2026-08-23</summary>

- [x] Phase 62: Remediation SLA Settings UI
- [x] Phase 63: Close gap: ITAM-LIC-02/03 RBAC + ITAM-CAT-05 label UI
- [x] Phase 64: rotate_key autonomous-remediation action
- [x] Phase 65: FIM process attribution via fanotify
- [x] Phase 66: Full YARA-rule engine for native scan

</details>

<details>
<summary>✅ v4.1 — ITAM-Backlog (Phases 69–73) — SHIPPED 2026-08-26</summary>

- [x] Phase 69: User Management
- [x] Phase 70: Core Data, Audit & Customization
- [x] Phase 71: Procurement & Asset Workflow
- [x] Phase 72: Reporting & Dashboards
- [x] Phase 73: API & Integrations

Full detail archived to `milestones/v4.1-ROADMAP.md`.

</details>
