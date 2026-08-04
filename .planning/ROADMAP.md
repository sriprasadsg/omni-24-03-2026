# Roadmap: Enterprise OmniAgent — Security & Compliance Portal

## Milestones

- **[v1.0](milestones/v1.0-ROADMAP.md)** — Security & Compliance Portal: Rust agent evidence parity, manual evidence uploads, audit-ready PDF/Excel export, remediation workflow. 5 phases, 11 plans, 16/16 requirements. Shipped 2026-06-18.
- **v1.1** — Evidence Quality & Compliance Scoring: compliance status wiring, staleness detection, bulk upload, chain-of-custody audit trail, tenant compliance score. 4 phases, 11 plans, SCORE-01/02/03 + STATUS-01/02 + STALE-01/02 + COC-01/02 + BULK-01/02/03 + UI-01. Shipped 2026-06-22.
- **v1.2** — Reporting Automation: scheduled compliance report generation and email delivery. 1 phase, SCHED-01/02.
- **v2.0** — GRC Feature Parity: 9 phases (14–22) closing competitive gaps vs Comp AI, Probo, OpenLane, Prowler. Complete — verified 2026-07-05.
- **v2.1** — Windows PowerShell Evidence + IaC/Container Security: full PowerShell evidence collection for all 28 Windows compliance checks, rebuilt installers (PS1, EXE/Inno Setup), dedicated ingestion API, evidence display updates (Phase 23, complete); IaC (Terraform/CloudFormation/K8s) and container image scanning (Phase 24, complete — verified 2026-07-05).
- **v3.0** — Competitive Feature Closure: 14 phases (25–38) closing the 25 gaps from the 2026-07-06 feature-parity audit against Comp AI, Probo, OpenLane Core, and Prowler — cloud-check execution gaps, vendor/risk data completeness, OSCAL/SBOM export, governance documents, a real public Trust Center, AI questionnaire auto-answer, FAIR risk quantification, provider expansion, workflow connectors, passkeys, GraphQL, ReBAC, a spec-compliant MCP server, and an interactive AI security assistant. In progress — Phase 25 planning underway.
- **v3.1** — AI Orchestration Layer: unified LangChain 1.x orchestration (`create_agent` + `init_chat_model`) across the AI compliance auditor, chat assistant, questionnaire auto-answer, and narrative generation surfaces, with citation-required structured outputs, tenant-scoped tools, and an evaluation harness (8 dimensions, Phoenix tracing). 1 phase (39), 12 plans. Complete — UAT 2026-07-19: 7 passed, 0 issues, 2 blocked on live gateway (nightly judged run, 9router passthrough re-test).
- **[v3.2](milestones/v3.2-ROADMAP.md)** — Agent Modernization & Remediation Ops: Rust agent 2.1.x dependency modernization + intermittent-401 root-cause fix, Jira/ServiceNow ticketing bridge, SLA/escalation on overdue remediation tasks, comment threads on compliance controls, and real CSPM checks for OCI/Alibaba/Cloudflare. 7 phases (40–45 + 999.1 backlog), 19 plans, 10/10 requirements. Shipped 2026-07-29.
- **[v3.3](milestones/v3.3-ROADMAP.md)** — Agent Geo & Fleet Observability: fleet geo map (air-gapped bundled-SVG, clustering, tenant/status filters), location-based security (agent-scoped impossible-travel, alert-only geo-fencing, heuristic VPN/hosting flag), fleet observability (metrics-history charts, uptime timeline, offline + version-drift view), and an immutable per-agent location-history audit trail. 4 phases (46–49), 23 plans, 11/11 requirements. Audit passed. Shipped 2026-07-30.
- **[v3.4](milestones/v3.4-ROADMAP.md)** — Native Security Scanning & Autonomous Remediation Agent: built-in file/URL/IP/hash scanning (VirusTotal-like), vulnerability detection (Wazuh-like FIM/config-assessment/vuln-detection), file integrity monitoring, and autonomous remediation via playbook system. No external SIEM dependencies. 6 phases (50–55), 19 requirements. Shipped 2026-08-04.
- **v4.0** — ITAM (IT Asset Management Lifecycle): Snipe-IT-parity asset lifecycle on top of the existing security CMDB — catalog & manual asset cataloging, check-out/check-in with append-only assignment history, offline QR/barcode labels, procurement/warranty/depreciation, software licenses & consumables, and an admin-gated ITAM console. 6 phases (56–61), 17 requirements. Roadmap defined 2026-08-04 — not started.

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

**Plans:** 2/2 plans complete

- [x] 13-01-PLAN.md — Backend TDD: `compliance_narrative_service.py` (_sanitise, _trim_to_words, NarrativeOutput, generate_executive_summary, generate_framework_narrative, enrich_report_data), wire into `_generate_report` / `_build_pdf` in scheduled_reports_service.py, 8-test suite (AI-05, AI-06)
- [x] 13-02-PLAN.md — Verification fix: replace asyncio.get_event_loop() with asyncio.run() in 5 async tests (order-independence), extract _process_due_schedule helper to bring scheduled_reports_service.py under 500 lines (CLAUDE.md compliance)

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

---

## v2.0 — GRC Feature Parity

**Goal:** Close all feature gaps identified in the June 2026 audit against Comp AI, Probo, OpenLane Core, and Prowler. Add SaaS OAuth evidence, evidence review workflow, control grouping, privacy/legal modules, 14 new compliance frameworks, 300+ cloud checks, multi-account scanning, notification routing, domain scanning, and API extensions (MCP, OCSF, CLI, DigitalOcean).

**Status:** Complete — verified 2026-07-05, all 9 phases' test suites pass and dashboards wired into navigation

**Phases:**

| Phase | Name | Status |
|-------|------|--------|
| 14 | SaaS Evidence Integration (GitHub, Jira, Okta, GWS, Slack OAuth) | Complete |
| 15 | Evidence Review Workflow (approve/reject/comment thread) | Complete |
| 16 | Program Control Grouping (named programs + status rollup) | Complete |
| 17 | Cloud Checks Expansion (67 → 300+ checks) | Complete |
| 18 | Privacy & Legal Modules (TIA, LIA, Notices, Contracts) | Complete |
| 19 | Additional Compliance Frameworks (14 new: FedRAMP High, ISO 27017/18, OWASP, BSI C5, etc.) | Complete |
| 20 | Multi-Account Cloud Scanning (AWS Orgs, Azure Mgmt Groups, GCP Orgs) | Complete |
| 21 | Notification Routing & Domain Scanner | Complete |
| 22 | API Extensions (MCP server, OCSF, CLI, DigitalOcean checks) | Complete |

---

## Phase 22: API Extensions

**Goal:** Expose compliance data via MCP protocol for AI assistant integrations, add OCSF-formatted output for SIEM ingestion, expand cloud checks to DigitalOcean, and ship a CLI tool.

**Requirements:** API-01, API-02, API-03, API-04

**Plans:** 1 plan

- [x] 22-01-PLAN.md — Backend: mcp_server_endpoints.py (/api/mcp), ocsf_endpoints.py (/api/ocsf), 10 DO checks, scripts/omni-cli.py (Click); Frontend: ApiExtensionsDashboard.tsx

---

## Phase 21: Notification Routing & Domain Scanner

**Goal:** Route GRC event notifications to Slack/email/webhook channels via configurable rules; add a lightweight domain/subdomain scanner with TLS cert and DNS inspection.

**Requirements:** NOTIF-01, NOTIF-02, SCAN-01, SCAN-02

**Plans:** 1 plan

- [x] 21-01-PLAN.md — Backend: notification_service.py, notification_endpoints.py, domain_scanner_service.py, domain_scanner_endpoints.py, 7-test suite; Frontend: NotificationsDashboard.tsx

---

## Phase 20: Multi-Account Cloud Scanning

**Goal:** Register and scan multiple cloud accounts across AWS Organizations, Azure Management Groups, and GCP organizations from a single platform with aggregated results.

**Requirements:** CLD-01, CLD-02, CLD-03

**Plans:** 1 plan

- [x] 20-01-PLAN.md — Backend: cloud_accounts_service.py, cloud_accounts_endpoints.py, 8-test suite; Frontend: CloudAccountsDashboard.tsx

---

## Phase 19: Additional Compliance Frameworks

**Goal:** Add 14 new compliance framework JSON files (ENS, MAS TRM, IRAP, ISO 27017, ISO 27018, BSI C5, FFIEC, OWASP Top 10, TISAX, AWS Well-Architected, RBI CSF, TIC 3.0, KISA ISMS, FedRAMP High) to reach parity with Comp AI and Probo framework libraries.

**Requirements:** FW-01

**Plans:** 1 plan

- [x] 19-01-PLAN.md — 14 framework JSON files in backend/frameworks/

---

## Phase 18: Privacy & Legal Modules

**Goal:** Add Transfer Impact Assessments, Legitimate Interest Assessments, Privacy Notice versioning, and Contract Lifecycle tracking for GDPR/CCPA GRC teams.

**Requirements:** PRIV-01, PRIV-02, PRIV-03, PRIV-04

**Plans:** 1 plan

- [x] 18-01-PLAN.md — Backend: privacy_service.py, privacy_endpoints.py, 8-test suite; Frontend: PrivacyLegalDashboard.tsx (4 tabs)

---

## Phase 17: Cloud Checks Expansion

**Goal:** Expand cloud security check library from 67 to 300+ checks covering EKS, Lambda, CloudFront, WAF, SNS, SQS, ElasticSearch, Route53, ACM, Inspector, SSM, Backup, Azure App Service, ACR, AKS, GCP BigQuery, GKE.

**Requirements:** CC-EXP-01, CC-EXP-02

**Plans:** 1 plan

- [x] 17-01-PLAN.md — Expand CLOUD_CHECKS list; split into per-provider modules if needed to stay under 500 lines

---

## Phase 16: Program Control Grouping

**Goal:** Group compliance controls into named programs (e.g., "Access Control Program") with live status rollup (compliant/at_risk/in_progress) based on control pass/fail rates.

**Requirements:** PROG-01, PROG-02, PROG-03

**Plans:** 1 plan

- [x] 16-01-PLAN.md — Backend: program_service.py, program_endpoints.py, 7-test suite; Frontend: ProgramsDashboard.tsx

---

## Phase 15: Evidence Review Workflow

**Goal:** Per-evidence approval/reject/request-changes workflow with comment threads, so evidence must be reviewer-approved before counting toward the compliance score.

**Requirements:** REV-01, REV-02, REV-03

**Plans:** 1 plan

- [x] 15-01-PLAN.md — Backend: evidence_review_service.py, evidence_review_endpoints.py, 8-test suite; Frontend: EvidenceReviewPanel.tsx

---

## Phase 14: SaaS Evidence Integration

**Goal:** Automatically pull compliance evidence from GitHub, Jira, Okta, Google Workspace, and Slack via OAuth 2.0 — eliminating manual upload burden for the most common SaaS-sourced control evidence.

**Requirements:** SAAS-01, SAAS-02, SAAS-03, SAAS-04

**Plans:** 2/2 plans complete

- [x] 14-01-PLAN.md — Backend: saas_integration_service.py (OAuth + per-provider evidence pull), saas_integration_endpoints.py (/api/saas), 10-test suite
- [x] 14-02-PLAN.md — Frontend: SaaSIntegrationsDashboard.tsx (5 provider cards, OAuth popup flow); router registration

---

## Phase 10: Scheduled Compliance Reports

**Goal:** Tenant admins can configure a recurring report schedule (daily/weekly/monthly) per framework; the backend generates and emails a PDF compliance report to configured recipients on each run; delivery history is viewable from the Reports page.

**Requirements:** SCHED-01, SCHED-02

**Plans:** 2/2 plans executed — COMPLETE

Plans:

- [x] 10-01-PLAN.md — Backend TDD: framework_id schema, _generate_pdf wiring, delivery log collection, GET /history endpoint, SMTP validation (Wave 1)
- [x] 10-02-PLAN.md — Frontend: framework picker in create modal, run-now URL fix, per-card delivery history panel (Wave 2)

---

## Phase 23: Windows PowerShell Evidence Collection

**Milestone:** v2.1

**Goal:** Rebuild all Windows installation files (PS1 scripts, EXE/Inno Setup installer)
with comprehensive PowerShell evidence collection for all 28 Windows compliance checks.
Evidence POSTs to a new `/api/powershell-evidence/submit` endpoint and appears in the
existing compliance evidence pages. Adds an Inno Setup EXE installer for click-to-install
deployment.

**Requirements:** WIN-PS-01 (28 checks), WIN-PS-02 (POST to backend), WIN-PS-03 (display in evidence pages), WIN-PS-04 (EXE installer)

**Plans:** 3/3 plans complete — 3/3 executed

- [x] 23-01-PLAN.md — Backend: `POST /api/powershell-evidence/submit` endpoint + 6-test TDD suite
- [x] 23-02-PLAN.md — PowerShell: rebuild win-install.ps1, new Collect-Evidence.ps1 (28 checks), rebuild agent/installer/*.ps1, new OmniAgent-Setup.iss (Inno Setup EXE)
- [x] 23-03-PLAN.md — Frontend: AgentInstallation.tsx Windows tab (3-step flow, 28 checks panel, EXE download link); PowerShell source badge

**Files created/modified:**

- `backend/powershell_evidence_endpoints.py` — evidence ingestion API
- `backend/tests/test_powershell_evidence.py` — 6 passing tests
- `backend/static/win-install.ps1` — service install + evidence setup
- `backend/static/Collect-Evidence.ps1` — 28-check collector
- `backend/agent_download_endpoints.py` — `/api/agent/collect-evidence-script` endpoint
- `agent-rust/install-service.ps1` — evidence collection + scheduled task
- `agent/installer/install_agent.ps1` — evidence setup
- `agent/installer/Configure-Agent.ps1` — evidence config fields
- `agent/installer/Collect-Evidence.ps1` / `agent/dist/installer/Collect-Evidence.ps1` — bundled copies
- `agent/installer/uninstall_agent.ps1` / `agent/dist/installer/uninstall_agent.ps1` — scheduled task cleanup
- `agent/installer/OmniAgent-Setup.iss` — Inno Setup 6 EXE builder
- `components/WindowsInstallTab.tsx` — 3-step install UI + 28-checks panel
- `components/AssetComplianceList.tsx` — purple "PS" source badge
- `components/AgentInstallation.tsx` — Windows tab integration

## v3.0 — Competitive Feature Closure

**Goal:** Close the 25 remaining gaps identified in the 2026-07-06 feature-parity audit against Comp AI, Probo, OpenLane Core, and Prowler (see the audit artifact for full evidence). Ordered in three risk tiers: cheap fixes to existing partial work first, medium-scope new features next, the four biggest architectural bets (GraphQL, ReBAC, real MCP protocol, public Trust Center) last.

**Status:** 14 of 14 phases executed as of 2026-07-14 — full backend suite 946 passed / 22 skipped / 0 failed, frontend build clean. Runtime UAT cleared for 28 and 30 (7 real defects found and fixed, commit 368f01d9). Phase 29 re-execution complete: all 4 plans (29-01..29-04) genuinely re-executed and committed 2026-07-14 after UAT proved the original TRUST-01/02/03 implementation was never committed. Phase 35 GraphQL UAT cleared 2026-07-14 — integration suite covers all 8 UAT items (evidence/risks/users/tenants queries, cross-tenant isolation, per-root RBAC). UAT files for 33/34 created 2026-07-14 with all automatable items passing. Runtime verification 2026-07-14 against live services closed the 32 human items (4/4, attack-path simulated-flag defect + posture-results 500 fixed) and the 33 live round trip (signed delivery HMAC-verified; 3 webhook defects fixed). Remaining human-only: 34 real-browser passkey ceremony (needs physical authenticator), optional hosted n8n/Zapier account test.

**Phases:**

| Phase | Name | Tier | Status |
|-------|------|------|--------|
| 25 | Cloud Checks Execution Gaps | 1 — quick fixes | Complete (2026-07-06) |
| 26 | Vendor and Risk Data Completeness | 1 — quick fixes | Complete (2026-07-09) |
| 27 | Compliance Export Formats (OSCAL and SBOM) | 1 — quick fixes | Complete (2026-07-13, UAT pass) |
| 28 | Governance Document Management | 2 — medium | Complete — runtime UAT passed 2026-07-14 (4 defects found and fixed, see 28-UAT.md) |
| 29 | Public Trust Center | 3 — architectural | Complete — all 4 plans executed (2026-07-14): TRUST-01 DB persistence, TRUST-02 public route + NDA flow + standalone public page, TRUST-03 custom-domain resolution + admin frontend |
| 30 | AI Questionnaire Auto-Answer | 2 — medium | Complete — runtime UAT passed 2026-07-14 (8/8 items; 3 defects found and fixed, see 30-UAT.md) |
| 31 | FAIR Risk Quantification | 2 — medium | Complete (2026-07-10) |
| 32 | Cloud and SaaS Provider Expansion | 2 — medium | Complete — 4/4 must-haves verified at runtime 2026-07-14 (2 defects found+fixed; PyPI publisher evidence recorded, see 32-VERIFICATION.md) |
| 33 | Workflow Automation Connectors | 2 — medium | Complete — UAT 9/9 pass 2026-07-14 incl. live signed-delivery round trip with HMAC verify (3 defects found+fixed, see 33-UAT.md) |
| 34 | Passkey and WebAuthn Authentication | 3 — architectural | Complete — UAT 6/7 pass 2026-07-14 (test_passkey_auth.py 6/6, frontend UI present); real-browser ceremony human-pending (see 34-UAT.md) |
| 35 | GraphQL API | 3 — architectural | Complete — integration suite covers all 8 UAT items (test_graphql.py 10/10, 2026-07-14) |
| 36 | Fine-Grained Relationship-Based Authorization | 3 — architectural | Complete — openfga_sdk installed, test_rebac.py 4/4 pass |
| 37 | Spec-Compliant MCP Server | 3 — architectural | Complete (2026-07-13, tests 12/12) |
| 38 | Interactive AI Security Assistant | 3 — architectural | Complete (2026-07-13, tests 5/5) |

---

## Phase 25: Cloud Checks Execution Gaps

**Milestone:** v3.0 (Tier 1 — quick fixes)

**Goal:** Close the gap between what `cloud_checks_service.py` catalogs and what it actually runs. Kubernetes and DigitalOcean checks are defined but never evaluated by `run_checks()`; CloudFormation IaC scanning returns an explicit "not yet implemented" stub instead of real rules; container image scanning silently fakes CVE results when Trivy isn't installed instead of saying so.

**Requirements:** CHK-01 (K8s + DigitalOcean checks actually evaluated), CHK-02 (real CloudFormation rule engine at parity with the existing Terraform/K8s rule counts), CHK-03 (container scan fails closed / labels simulated results instead of presenting them as real)

**Depends on:** Phase 24

**Plans:** 3/3 plans complete
**Wave 1**

- [x] 25-01-PLAN.md — CHK-01: widen the four provider-allowlist gates (RUNNABLE_PROVIDERS, cloud-checks /run, cloud-account registration, MCP run_cloud_check) so k8s + DigitalOcean checks are actually evaluated; fill the empty test_cloud_checks_expansion.py stub
- [x] 25-02-PLAN.md — CHK-02: real CloudFormation rule engine (18 cfn-* rules at parity with Terraform) in iac_scanner_service.py, fix the YAML-CFN `_detect_provider` bug, remove the "not yet implemented" stub

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 25-03-PLAN.md — CHK-03: explicit `simulated` flag on container scan results + prominent SIMULATED badge across the dashboard summary/table/history (labeling, not fail-closed)

---

## Phase 26: Vendor and Risk Data Completeness

**Milestone:** v3.0 (Tier 1 — quick fixes)

**Goal:** Extend the existing vendor and risk modules to close three data-completeness gaps found in the audit: DPA lifecycle is a checkbox flag (BAA already has a full create/sign/terminate lifecycle — DPA should match it), subprocessor discovery doesn't exist at all, and the risk register scores a single blended `risk_score` instead of distinguishing inherent (pre-mitigation) from residual (post-mitigation) risk.

**Requirements:** VRISK-01 (DPA lifecycle tracking), VRISK-02 (subprocessor discovery on the vendor record), RISK-01 (inherent vs. residual risk scoring)

**Depends on:** None (parallel-safe with Phase 25)

**Plans:** 5 plans
**Wave 1**

- [x] 26-01-PLAN.md — VRISK-01: DPA lifecycle (create/sign/terminate) as a new /api/dpa router cloned from BAA, with vendor_id + explicit RBAC gate [Wave 1]
- [x] 26-02-PLAN.md — VRISK-02 backend: subprocessor add/list/remove on the vendor doc ($push/$pull) + tests [Wave 1]
- [x] 26-03-PLAN.md — RISK-01 backend: additive inherent/residual risk scoring in risk_service/risk_endpoints + tests [Wave 1]

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 26-04-PLAN.md — VRISK-02 frontend: VendorDetailModal (subprocessor list/add/remove + DPA status), wired into VendorManagement [Wave 2]
- [x] 26-05-PLAN.md — RISK-01 frontend: Residual Score column in RiskRegister + residual inputs in RiskFormModal [Wave 2]

---

## Phase 27: Compliance Export Formats (OSCAL and SBOM)

**Milestone:** v3.0 (Tier 1 — quick fixes)

**Goal:** Add two machine-readable export formats the awesome-compliance audit flagged as table stakes for "audit-ready" output, alongside the existing PDF/Excel/CSV/OCSF exports: OSCAL-conformant JSON for control/evidence data, and SBOM (CycloneDX or SPDX) for scanned container images and assets.

**Requirements:** EXP-01 (OSCAL export), EXP-02 (SBOM export)

**Depends on:** None

**Plans:** 2 plans, 1 wave

- [x] 27-01-PLAN.md — OSCAL assessment-results export endpoint + builder + tests + dashboard button (EXP-01)
- [x] 27-02-PLAN.md — CycloneDX 1.6 SBOM export for scanned container images + tests + dashboard button (EXP-02)

---

## Phase 28: Governance Document Management

**Milestone:** v3.0 (Tier 2 — medium)

**Goal:** Add real governance-document management — versioned policy/procedure documents with an approval workflow (reusing the existing generic `approval_service.py` engine rather than building a new one) and electronic signature capture with signed-PDF export. Today `policy_endpoints.py` is if/then automation rules, not governance docs — this is genuinely new surface, not an extension.

**Requirements:** DOC-01 (versioned documents + approval workflow), DOC-02 (e-signature capture + signed-PDF export)

**Depends on:** None

**Plans:** 3 plans, 3 waves

**Wave 1**

- [x] 28-01-PLAN.md — DOC-01 backend: versioned governance documents (embedded versions[]) + approval delegation to the existing `approval_service.py` engine; publish gated on live approval status

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 28-02-PLAN.md — DOC-02 backend: ESIGN/UETA-baseline e-signature capture (server-derived identity/IP/UA/timestamp, approval re-check) + signed-PDF export (reportlab + html.escape)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 28-03-PLAN.md — Frontend: `GovernanceDocumentsDashboard.tsx` + mandatory `App.tsx`/`Sidebar.tsx`/`types.ts` nav-wiring (DOC-01/DOC-02)

---

## Phase 29: Public Trust Center

**Milestone:** v3.0 (Tier 2 — medium)

**Goal:** Turn the existing internal-only trust module into a real customer-facing Trust Center: move `trust_service.py` off its in-memory singleton onto the database, add an actual unauthenticated public route (every route currently requires `get_current_user`), build a real NDA-gated access-request flow for an external visitor, and support serving the page from a custom domain.

**Requirements:** TRUST-01 (DB-backed persistence), TRUST-02 (real public route + NDA gating flow), TRUST-03 (custom domain)

**Depends on:** Phase 28 (governance documents feed the trust center's public document library)

**Plans:** 4/4 plans complete

**Wave 1**

- [x] 29-01-PLAN.md — TRUST-01/03 backend: DB-back trust_service.py (trust_profiles/trust_access_requests), repoint admin routes at the async service, trust_slug/trust_domain on db.tenants + test scaffold *(re-executed and committed 2026-07-14: 21ed35b3/435213be/86575edb — prior claimed completion was phantom, verified via git log --all)*

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 29-02-PLAN.md — TRUST-02/03 backend: public GET/POST routes (set_tenant_id resolution, private-URL-stripped view, NDA consent, rate limits) + Host-header custom-domain resolution *(re-executed and committed 2026-07-14: 1ee31791/1bcc8361/fac0c4e9 — prior claimed completion was phantom; this run verified via git log and a genuinely green 17/17 test_trust_center.py + 936/22/0 full suite)*
- [x] 29-03-PLAN.md — TRUST-01/03 admin frontend: TrustCenter.tsx profile edit form + Custom Domain field + Copy Link + approve/deny toasts/aria-labels, apiService.updateTrustProfile() *(re-executed and committed 2026-07-14: cda3692c/d43c89cd/e3a045bc — prior claimed completion was phantom; this run verified via npm run build + npx tsc --noEmit clean, edit form extracted to new TrustProfileEditForm.tsx to respect 500-line limit)*

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 29-04-PLAN.md — TRUST-02 public page: standalone static trust-page.html (vanilla JS) + GET /trust/{slug} FileResponse route in app.py *(executed and committed 2026-07-14: 795aa444/b6b82a15 — prior claimed completion was phantom (see 29-UAT.md); this run verified via TestClient live route/page checks, structural+copy grep checks, and a genuinely green full suite 940/22/0)*

---

## Phase 30: AI Questionnaire Auto-Answer

**Milestone:** v3.0 (Tier 2 — medium)

**Goal:** Today the platform only sends questionnaires *out* to vendors (`questionnaire_service.py`). Add the inverse: when this tenant receives an inbound security questionnaire, draft answers grounded in its own evidence/control data via RAG, and hold every draft for human review before it can be marked submitted.

**Requirements:** RAG-01 (grounded auto-draft from evidence/control data), RAG-02 (mandatory human review gate before submission)

**Depends on:** None

**Plans:** 6 plans
**Wave 1**

- [x] 30-01-PLAN.md — Tenant-scope rag_service.py + add temperature/max_tokens to ai_service (RAG-01)
- [x] 30-02-PLAN.md — Inbound-questionnaire intake service/endpoints (.xlsx/.csv + manual) (RAG-01)
- [x] 30-03-PLAN.md — Answer-review state machine + submit guard, RBAC, server-derived identity (RAG-02)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 30-04-PLAN.md — Grounded answer-draft service (RAG + generation + insufficient-evidence fallback) (RAG-01)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 30-05-PLAN.md — End-to-end HTTP test + opt-in RAGAS/Phoenix eval scaffold (RAG-01/02)
- [x] 30-06-PLAN.md — Frontend: inbound intake UI + evidence-grounded review queue + nav wiring (RAG-01/02)

---

## Phase 31: FAIR Risk Quantification

**Milestone:** v3.0 (Tier 2 — medium)

**Goal:** Add an optional FAIR-style quantitative layer (loss magnitude range × event frequency → dollarized loss-exceedance) to the risk register, alongside the existing qualitative likelihood×impact scoring — for risks where a dollar figure matters more than a heatmap position.

**Requirements:** FAIR-01 (quantitative loss-exceedance scoring as an alternative/addition to qualitative risk scoring)

**Depends on:** Phase 26 (extends the risk register work from that phase)

**Plans:** 3 plans — Complete (2026-07-10)
**Wave 1**

- [x] 31-01-PLAN.md — Backend: run_fair_simulation() Monte Carlo + validated FairInputs + tenant-scoped POST /{id}/fair-simulation + pytest suite (FAIR-01)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 31-02-PLAN.md — Frontend: runFairSimulation API + Risk type + new RiskFairModal.tsx + FAIR column/trigger in RiskRegister.tsx (FAIR-01)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 31-03-PLAN.md — Human-verify checkpoint: FAIR quantify flow reachable and usable in the running app (FAIR-01)

---

## Phase 32: Cloud and SaaS Provider Expansion

**Milestone:** v3.0 (Tier 2 — medium)

**Goal:** Close the remaining provider-breadth gaps versus Prowler: OCI/Alibaba/Cloudflare currently only store connection config with no real polling, Microsoft 365 and MongoDB Atlas aren't scanned providers at all, and GitHub/Okta/Google Workspace/Slack/Jira only support evidence-pull (no native posture checks). Also upgrade attack-path visualization to prefer real findings over the demo-seed fallback, and label the fallback clearly when it's showing.

**Requirements:** PROV-01 (real polling for OCI/Alibaba/Cloudflare), PROV-02 (M365 + MongoDB Atlas as scanned providers), PROV-03 (native posture checks for the 5 OAuth SaaS providers), PROV-04 (attack-path prefers real findings, labels demo fallback)

**Depends on:** Phase 25 (same cloud-checks subsystem)

**Plans:** 5 plans, 2 waves
**Wave 1**

- [x] 32-01-PLAN.md — PROV-01: OCI/Alibaba/Cloudflare real-poll SIEM ingest modules + dispatch/secret-set wiring + package-legitimacy checkpoint (Wave 1)
- [x] 32-02-PLAN.md — PROV-02/PROV-01: M365 + MongoDB Atlas check catalogs, four-gate lockstep widening, additive simulated provenance flag (Wave 1)
- [x] 32-03-PLAN.md — PROV-03: native SaaS posture checks reusing pull_*_evidence into saas_check_results (Wave 1)
- [x] 32-04-PLAN.md — PROV-04: rewire attack-path endpoint to the real service, simulated flag + edge-field fix + SIMULATED badge (Wave 1)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 32-05-PLAN.md — PROV-02: M365 (Graph secureScores) + MongoDB Atlas (Admin API) real findings ingestion into cloud_findings + scan hook (Wave 2)

---

## Phase 33: Workflow Automation Connectors

**Milestone:** v3.0 (Tier 2 — medium)

**Goal:** The generic webhook system (`webhook_service.py`) can already point at an n8n or Zapier webhook URL, but there's no dedicated connector for either. Ship a real n8n community node and a Zapier integration so GRC event notifications reach either platform without hand-built HTTP config.

**Requirements:** WF-01 (n8n community node), WF-02 (Zapier integration)

**Depends on:** None

**Plans:** 4 plans, 2 waves
**Wave 1**

- [x] 33-01-PLAN.md — API-key authentication path (hash-at-rest + get_current_user_or_api_key + wire webhook routes) [Wave 1]
- [x] 33-02-PLAN.md — Outbound webhook HMAC-SHA256 signing fix (clone ticket_webhook_service, sign exact bytes) [Wave 1]

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 33-03-PLAN.md — n8n community node (WF-01) — integrations/n8n-nodes-omniagent/ [Wave 2]
- [x] 33-04-PLAN.md — Zapier integration (WF-02) — integrations/zapier-omniagent/ [Wave 2]

---

## Phase 34: Passkey and WebAuthn Authentication

**Milestone:** v3.0 (Tier 3 — architectural)

**Goal:** Add WebAuthn/FIDO2 passkey registration and login as an alternative to password/SSO/TOTP. SAML, OIDC, and TOTP MFA already exist (`sso_service.py`, `mfa_service.py`) — passkeys are the one auth method OpenLane has that this platform doesn't.

**Requirements:** AUTH-01 (WebAuthn passkey registration + login, alongside existing auth methods — no regression to SAML/OIDC/TOTP)

**Depends on:** None

**Plans:** 1/1 plans complete

- [x] 34-PLAN.md — WebAuthn passkey registration + login (py_webauthn backend, browser-JSON options, credential-id normalization), frontend passkey login/management UI (commit a1e23c8d); test_passkey_auth.py passes

---

## Phase 35: GraphQL API

**Milestone:** v3.0 (Tier 3 — architectural)

**Goal:** Stand up a GraphQL layer alongside the existing FastAPI REST surface for the core compliance/evidence/risk data model, matching Probo and OpenLane. The hard part isn't the schema — it's making sure every resolver enforces the same tenant-isolation and RBAC checks the REST endpoints already have, so the new surface can't become an auth bypass.

**Requirements:** GQL-01 (GraphQL endpoint + schema for core read queries), GQL-02 (resolvers enforce tenant isolation + RBAC at parity with REST)

**Depends on:** None

**Plans:** 1/1 plans complete (3 execution summaries)

- [x] 35-PLAN.md — strawberry-graphql /api/graphql endpoint; resolvers enforce per-resolver tenant isolation + RBAC at REST parity (user resolved once in router context); strawberry installed 2026-07-13 (commit cd66ce1e), resolver auth rework committed 2026-07-14; test_graphql.py passes. UAT: all 8 items covered by integration tests 2026-07-14 (test_graphql.py 10/10, see 35-UAT.md)

---

## Phase 36: Fine-Grained Relationship-Based Authorization

**Milestone:** v3.0 (Tier 3 — architectural)

**Goal:** Evaluate OpenFGA/Zanzibar-style relationship-based authorization against the current RBAC model (`rbac_service.py`). This is the riskiest item in the milestone — start with a design doc and a recommendation, and only migrate a single high-value resource type's permission checks if the recommendation is to adopt, without regressing RBAC behavior anywhere else.

**Requirements:** REBAC-01 (design doc + recommendation), REBAC-02 (migrate one resource type's checks, conditional on REBAC-01's recommendation)

**Depends on:** None

**Plans:** 1/1 plans complete (3 execution summaries)

- [x] 36-PLAN.md — REBAC-01 design doc + OpenFGA recommendation (backend/36-DESIGN.md), REBAC-02 pilot migration; openfga_sdk installed 2026-07-13 (commit cd66ce1e), test_rebac.py 4/4 pass

---

## Phase 37: Spec-Compliant MCP Server

**Milestone:** v3.0 (Tier 3 — architectural)

**Goal:** Replace the current REST-shaped `/api/mcp` endpoint (no `mcp` SDK, not a real stdio/SSE transport) with a spec-compliant MCP server, so this platform's tools are usable by actual MCP clients (Claude Desktop, etc.), not just a REST-API-shaped imitation.

**Requirements:** MCP-01 (spec-compliant MCP server via the official SDK), MCP-02 (all existing tool-catalog entries remain available through it)

**Depends on:** None

**Plans:** 1/1 plans complete

- [x] 37-PLAN.md — FastMCP spec-compliant server (backend/mcp_server.py) replacing the REST-shaped /api/mcp endpoint; REST router removed from router_registry; test_mcp_server.py 12/12 pass

---

## Phase 38: Interactive AI Security Assistant

**Milestone:** v3.0 (Tier 3 — architectural)

**Goal:** Add a Prowler-Lighthouse-equivalent conversational assistant — a chat UI where a user asks natural-language questions about their compliance/security posture and gets answers grounded in live findings data, with sources cited. `chat_window.py` today is an unrelated admin-to-endpoint-user remote chat tool, not an AI assistant.

**Requirements:** ASSIST-01 (conversational chat UI), ASSIST-02 (answers grounded in live compliance/findings data, sources cited)

**Depends on:** Phase 30 (reuses the RAG grounding infrastructure built there)

**Plans:** 3/3 plans complete

- [x] 38-01/02/03 — backend chat API + RAG grounding (ai_assistant_service/endpoints), frontend AIAssistantChat.tsx integration, test_ai_assistant.py 5/5 pass (includes tenant-isolation + empty-query coverage)

---

## Phase 24: IaC & Container Security

**Milestone:** v2.1

**Goal:** Implement Infrastructure-as-Code scanning (Terraform, CloudFormation, Kubernetes
manifests — 25+ checks) and container image vulnerability scanning (Trivy-backed, with a
simulated fallback), closing the #1 gap versus Checkov, Trivy, and Snyk identified in the
June 2026 audit.

**Requirements:** IAC-01 (IaC scan endpoint + 25+ checks across Terraform/CloudFormation/Kubernetes), IAC-02 (container image scan endpoint + historical results), IAC-03 (scan-config endpoint + 8 passing tests)

**Depends on:** Phase 23

**Plans:** 1/1 complete — all 16 review findings fixed, dashboard restyled and wired into navigation, verified 2026-07-05

- [x] 24-01-PLAN.md — Backend: `iac_scanner_service.py` + `container_scanner_service.py`, `/api/iac` + `/api/container` endpoints, 8-test TDD suite; Frontend: `IacContainerDashboard.tsx` (IaC Scanner + Container Scanner tabs). All 16 `24-REVIEW.md` findings fixed (inverted PASS/FAIL logic, Kubernetes always-fail override, missing CloudFormation checks, broken test auth override, dashboard/API type mismatch, plus 8 warning/info findings) — 8/8 tests pass, re-run and confirmed. Dashboard restyled from inline dark theme to Tailwind per `24-UI-SPEC.md`, and wired into `App.tsx`/`Sidebar.tsx`/`types.ts` navigation (`view: 'iacContainer'`, Security (SecOps) section) — confirmed reachable via build chunk output.

## v3.1 — AI Orchestration Layer

**Goal:** Unify the platform's AI surfaces behind LangChain as a model-agnostic orchestration layer, per the AI-SPEC design contract generated 2026-07-17.

**Phases:**

| Phase | Name | Status |
|-------|------|--------|
| 39 | LangChain AI Integration | Complete (12/12) — UAT 2026-07-19: 7 passed, 0 issues, 2 blocked on live gateway (nightly judged run, 9router passthrough re-test) |

---

## Phase 39: LangChain AI Integration

**Milestone:** v3.1

**Goal:** Migrate the platform's existing AI surfaces — AI compliance auditor (`ai_auditor_endpoints.py`), Phase 38 grounded chat assistant (`ai_assistant_service.py` / `/api/assistant/chat` — legacy `/api/ai/chat` and `ChatAssistant.tsx` explicitly deferred per 39-CONTEXT.md), questionnaire auto-answer RAG (`rag_service.py`), narrative generation (`compliance_narrative_service.py`) — onto LangChain 1.x (`create_agent` + `init_chat_model`) as a model-agnostic orchestration layer over the 9router gateway with Ollama fallback, with citation-required structured outputs, tenant-scoped tools, and the evaluation harness specified in 39-AI-SPEC.md (Phoenix tracing, 8 eval dimensions, online guardrails).

**Requirements:** Per 39-AI-SPEC.md design contract (framework decision, guardrails, eval strategy) — no standalone REQUIREMENTS.md IDs registered yet

**Depends on:** Phase 30 (RAG tenant isolation), Phase 38 (AI assistant surfaces)

**Plans:** 12/12 plans executed

Plans:

- [x] 39-01-PLAN.md — Pin + install LangChain 1.x runtime stack (legitimacy checkpoint)
- [x] 39-02-PLAN.md — 9router passthrough smoke test + eval harness scaffold (markers, two-tenant fixtures)
- [x] 39-03-PLAN.md — Shared citation-required schemas + one citation/control-ID validator
- [x] 39-04-PLAN.md — Model factory + persistent tenant-prefixed checkpointer + LangChain tracing wiring
- [x] 39-05-PLAN.md — Agent substrate: tenant-closed tools + versioned prompts + online guardrail hooks
- [x] 39-06-PLAN.md — Auditor migration onto create_agent (AuditFinding + citation validation + shim)
- [x] 39-07-PLAN.md — Phase 38 assistant chat migration onto create_agent (+ checkpointer memory + shim)
- [x] 39-08-PLAN.md — Questionnaire auto-answer migration (CitedAnswer + RAG-02 gate preserved + shim)
- [x] 39-09-PLAN.md — Narrative generation migration (NarrativeOutput + fail-closed fallback + shim)
- [x] 39-10-PLAN.md — 48-example reference dataset (gold controls, Q&A, chat, adversarial) + loader
- [x] 39-11-PLAN.md — Six code-based eval dimensions (phase gate: traceability, conservative status, fidelity, tenant isolation, provenance, RAG-02)
- [x] 39-12-PLAN.md — Three judged eval dimensions (questionnaire honesty, chat relevance, retrieval quality — nightly)

---

## v3.2 — Agent Modernization & Remediation Ops

**Goal:** Finish the Rust agent 2.1.0 dependency modernization and the outstanding 401 auth-session bug, then close real (verified, not assumed) gaps in remediation operations — bridging remediation tasks to existing ticketing connectors, SLA/escalation on overdue tasks, comment threads on controls, and CSPM checks for the 3 cloud providers that are currently dropdown-only stubs. Per the 2026-07-20 research summary: the Rust agent work is a fully independent toolchain track that can run in parallel with everything else; the four remediation-ops features are sequenced by risk — CSPM checks and comment threads first (structurally isolated, new-pattern risk validated cheaply), then the ticketing bridge before SLA/escalation, since both mutate the same `compliance_remediation_tasks` document.

**Status:** Roadmap defined 2026-07-20. Not started — continues phase numbering from Phase 39.

**Phases:**

| Phase | Name | Status |
|-------|------|--------|
| 40 | Rust Agent Modernization & Session Reliability | Complete |
| 41 | CSPM Provider Expansion (OCI, Alibaba, Cloudflare) | Complete |
| 42 | Comment Threads on Compliance Controls | Complete |
| 43 | Remediation-to-Ticketing Bridge | Complete |
| 44 | Remediation SLA & Escalation | Complete |

---

<details>
<summary>✅ v3.2 Agent Modernization & Remediation Ops (Phases 40–45) — SHIPPED 2026-07-29</summary>

Full phase detail archived to [milestones/v3.2-ROADMAP.md](milestones/v3.2-ROADMAP.md).
Requirements: [milestones/v3.2-REQUIREMENTS.md](milestones/v3.2-REQUIREMENTS.md) · Audit: [milestones/v3.2-MILESTONE-AUDIT.md](milestones/v3.2-MILESTONE-AUDIT.md).

- [x] Phase 40: Rust Agent Modernization & Session Reliability (RUST-01, SESS-01)
- [x] Phase 41: CSPM Provider Expansion — OCI/Alibaba/Cloudflare (CSPM-01/02/03)
- [x] Phase 42: Comment Threads on Compliance Controls (CMT-01)
- [x] Phase 43: Remediation-to-Ticketing Bridge (REM-01/02)
- [x] Phase 44: Remediation SLA & Escalation (SLA-01/02)
- [x] Phase 45: Close gap RUST-01 — TLS backend explicit decision

</details>

## v3.4 — Native Security Scanning & Autonomous Remediation Agent

**Goal:** Build native security scanning and autonomous remediation into the OmniAgent — replacing external integrations (VirusTotal API, Wazuh SIEM) with built-in, offline-first agent modules.

**Phases:**

| Phase | Name | Status |
|-------|------|--------|
| 50 | Native Security Scanning | Complete |
| 51 | Vulnerability Detection Engine | Complete |
| 52 | File Integrity Monitoring | Complete |
| 53 | Autonomous Remediation | Complete |
| 54 | Integration & Operator UI | Complete |
| 55 | Advanced Threat Detection & Response | Complete |

---

<details>
<summary>✅ v3.4 Native Security Scanning & Autonomous Remediation Agent (Phases 50–55) — SHIPPED 2026-08-04</summary>

Full phase detail archived to [milestones/v3.4-ROADMAP.md](milestones/v3.4-ROADMAP.md).
Requirements: [milestones/v3.4-REQUIREMENTS.md](milestones/v3.4-REQUIREMENTS.md).

- [x] Phase 50: Native Security Scanning (NSCAN-01/02/03)
- [x] Phase 51: Vulnerability Detection Engine (VULN-01/02/03)
- [x] Phase 52: File Integrity Monitoring (FIM-01/02/03)
- [x] Phase 53: Autonomous Remediation (AUTO-01/02/03/04)
- [x] Phase 54: Integration & Operator UI (INT-01/02/03)
- [x] Phase 55: Advanced Threat Detection & Response (INT-04, AUT-03, COMM-01)

</details>

---

## v4.0 — ITAM (IT Asset Management Lifecycle)

**Goal:** Add a full Snipe-IT-parity IT Asset Management lifecycle on top of the existing security/observability CMDB: manage physical/virtual assets through procurement → assignment → maintenance → retirement, with people checking gear in and out, licenses/consumables, and financial/warranty tracking — turning the security-monitoring "asset inventory" into a true ITAM system. Extends the existing `assets` collection with a source discriminator (per research: every cross-cutting feature already assumes one `assets` collection is the CMDB) rather than forking a parallel `itam_assets` collection.

**Status:** Roadmap defined 2026-08-04. Not started — continues phase numbering from Phase 55.

**Phases:**

| Phase | Name | Status |
|-------|------|--------|
| 56 | Catalog & Foundation | Complete    |
| 57 | Lifecycle & Check-In/Out | Not started |
| 58 | Asset Tags & Offline Labels | Not started |
| 59 | Procurement & Finance (Warranty & Depreciation) | Not started |
| 60 | Licenses & Consumables | Not started |
| 61 | Frontend ITAM Console | Not started |

---

## Phase 56: Catalog & Foundation

**Milestone:** v4.0

**Goal:** Establish the ITAM catalog layer and the additive fields (`assetSource` discriminator, `lifecycleStatus`) that every later phase builds on: normalized Manufacturer/Model/Category/Location/Supplier reference data, custom fields attached at the model level, and the ability to hand-catalogue a manual (non-agent) asset with a unique per-tenant asset tag that coexists with agent-discovered assets.

**Requirements:** ITAM-CAT-01 (Manufacturer/Model/Category/Location catalog CRUD), ITAM-CAT-02 (manual asset creation with unique per-tenant asset tag + source discriminator), ITAM-CAT-03 (Suppliers catalog entity), ITAM-CAT-04 (custom fields grouped into fieldsets, attached at the model level), ITAM-LIFE-01 (lifecycleStatus field, distinct from agent connectivity status)

**Success Criteria:**

1. Admin can create, edit, and delete Manufacturer, Model, Category, Location, and Supplier entries, each referenced by ID from assets.
2. Admin can create a manual (non-agent) asset with a unique per-tenant asset tag; it appears in the asset list alongside agent-discovered assets, distinguishable by source.
3. Admin can define custom fields grouped into fieldsets at the model level, and those fields appear on assets using that model.
4. Every asset — agent-discovered or manual — carries a distinct lifecycle status (deployable/deployed/archived/retired/disposed/broken) that is separate from its agent connectivity/heartbeat status.

**Depends on:** Nothing (first phase of v4.0; reuses and extends the existing `assets` model)

**Plans:** 2/2 plans complete

- [x] 56-01-PLAN.md — Tracer slice: Manufacturer catalog CRUD + `POST /api/assets` manual creation + `assetSource`/`lifecycleStatus` fields + atomic per-tenant asset-tag counter [Wave 1]
- [x] 56-02-PLAN.md — Remaining catalog kinds: Category/Location/Supplier CRUD + asset Model (references Manufacturer+Category) + custom fields/fieldsets [Wave 2]

**Status:** 56-01 executed 2026-08-04 (commits `1218c37`, `e1d377f`, `329a698`) — 13/13 tests pass, full backend suite 1564 passed / 34 skipped / 6 pre-existing unrelated fails, no regressions. See `56-01-SUMMARY.md`. 56-02 planned, not yet executed.

---

## Phase 57: Lifecycle & Check-In/Out

**Milestone:** v4.0

**Goal:** Give users a real "who has this" workflow — assign assets to a person or location, return them to stock, and keep a trustworthy, append-only history of every hand-off, plus a way to confirm assets are still where records say they are.

**Requirements:** ITAM-LIFE-02 (check out to a user or location, gated on deployable status), ITAM-LIFE-03 (check in, returns to stock and clears assignment), ITAM-LIFE-04 (append-only assignment history/audit trail), ITAM-LIFE-05 (mark physically audited + overdue-audit report)

**Success Criteria:**

1. User can check out a deployable-status asset to a user or a location; checkout is rejected for assets not in a deployable-typed status.
2. User can check in an asset, returning it to stock/available and clearing its current assignment.
3. Every check-out/check-in is recorded in an append-only assignment history visible per asset (who, where, when).
4. User can mark an asset as physically audited on a given date and pull a report of assets overdue for audit.

**Depends on:** Phase 56 (lifecycleStatus field + manual asset records)

**Plans:** 3 plans
**Wave 1**

- [ ] 57-01-PLAN.md — Tracer slice: check-out to a user end-to-end (new lifecycle router + append-only `assignment_history` service + registration), then location targets, refusal paths and the concurrency guarantee, plus Phase-57 indexes [Wave 1]

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 57-02-PLAN.md — Check-in returns the asset to stock and clears its assignment; per-asset history read with its empty/tie/ordering edge semantics and structural immutability [Wave 2]

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 57-03-PLAN.md — Mark physically audited (attributed, orthogonal to checkout state) and the query-time overdue-audit report with an explicit age basis [Wave 3]

---

## Phase 58: Asset Tags & Offline Labels

**Milestone:** v4.0

**Goal:** Let users print physical asset-tag labels — QR and 1D barcode, in a ready-to-print PDF sheet — entirely offline, so labeling works in air-gapped deployments with no external service or network call.

**Requirements:** ITAM-CAT-05 (printable QR + 1D barcode label / PDF label sheet, fully offline)

**Success Criteria:**

1. User can generate a QR code and a 1D barcode encoding an asset's tag.
2. User can export a printable PDF label sheet for one or more assets.
3. Label generation succeeds with outbound network access blocked (no external service or network call).

**Depends on:** Phase 56 (stable asset tag field)

**Plans:** TBD

---

## Phase 59: Procurement & Finance (Warranty & Depreciation)

**Milestone:** v4.0

**Goal:** Give every asset a financial record — purchase cost/date/PO/supplier, warranty tracking with proactive expiry alerts, and a computed book value — without any external accounting/GL integration.

**Requirements:** ITAM-FIN-01 (purchase cost, purchase date, PO number, supplier), ITAM-FIN-02 (warranty tracking + expiry alerts via existing notification/webhook infra), ITAM-FIN-03 (straight-line depreciation, model-level, computed at read time)

**Success Criteria:**

1. Admin can record and view purchase cost, purchase date, PO number, and supplier on an asset.
2. Admin sees each asset's warranty status/expiry and receives an alert as the warranty approaches or passes expiry, delivered through the existing notification/webhook infrastructure.
3. Admin can view an asset's current book value, computed at read time from a straight-line depreciation schedule assigned at the model level (no persisted mutable value, no external GL integration).

**Depends on:** Phase 56 (Model entity for model-level depreciation policy)

**Plans:** TBD

---

## Phase 60: Licenses & Consumables

**Milestone:** v4.0

**Goal:** Track software licenses, consumables, and components as first-class ITAM sub-inventory — seats assigned/reclaimed against a real seat count, consumables checked out in quantity, and components attached to a parent asset.

**Requirements:** ITAM-LIC-01 (software licenses: seat counts, assign/reclaim to user or asset, expiry tracking), ITAM-LIC-02 (accessories/consumables with quantity-aware checkout, quantity > 1 supported), ITAM-LIC-03 (components attached to a parent asset)

**Success Criteria:**

1. Admin can create a software license with a seat count, assign a seat to a user or asset, reclaim it, and see remaining/expired seats.
2. Admin can create an accessory/consumable and check it out in a quantity greater than one in a single transaction, with available quantity correctly decremented.
3. Admin can attach a component (RAM/HDD/GPU-style item) to a parent asset and see it listed on that asset's record.

**Depends on:** Phase 56 (tenant-isolation/RBAC scaffolding; architecturally independent of Phases 57-59)

**Plans:** TBD

---

## Phase 61: Frontend ITAM Console

**Milestone:** v4.0

**Goal:** Make every ITAM capability from Phases 56-60 reachable and usable from one admin-gated console, following the same nav pattern used for the native security operator console (Phase 47/48).

**Requirements:** ITAM-UI-01 (admin-gated nav entry — new AppView + App.tsx route + Sidebar entry + dedicated `manage:itam` permission)

**Success Criteria:**

1. An admin user sees an "ITAM" entry in the Sidebar, gated by a new `manage:itam` permission and invisible to non-admin/non-permitted users.
2. Selecting the ITAM nav entry opens a dedicated console (new AppView) with sections for Catalog, Check-Out/In, Procurement & Finance, and Licenses & Consumables.
3. From the console, a user can complete at least one full round trip per cluster — e.g. create a catalog asset, check it out, view its warranty/finance tab, and assign a license — without leaving the ITAM console.

**Depends on:** Phases 56, 57, 58, 59, 60 (integrates every backend surface)

**Plans:** TBD

**UI hint:** yes

---

## Backlog

### Phase 999.1: Remediation SLA Settings UI (BACKLOG)

**Goal:** [Captured for future planning] Build the Remediation SLA settings surface (At-Risk Window field). Backend `GET/PATCH /api/settings/remediation-sla` has been live since 44-03 but has no UI consumer — deliberately deferred during Phase 44, flagged twice by UI audits (44-UI-REVIEW.md).
**Requirements:** TBD
**Plans:** 0 plans

Plans:

- [ ] TBD (promote with /gsd-review-backlog when ready)

### Phase 999.2: `rotate_key` remediation action (BACKLOG)

**Goal:** [Deferred from Phase 53 by review] Add a `rotate_key` autonomous-remediation action (agent command + playbook) with a concrete, tested, reversible allowlisted target set. Deferred because the original scope was under-specified + dangerous + hard to make reversible. Ship after the four reversible actions (kill/restore/block/disable) are proven.
**Requirements:** extends AUTO-02
**Plans:** 0 plans

### Phase 999.3: FIM process attribution via fanotify (BACKLOG)

**Goal:** [Deferred from Phase 52 by review] Add Linux fanotify-based PID → real process-tree attribution to FIM change events, fully satisfying FIM-02's "process tree" clause (the `notify`-based watcher provides it only best-effort). Windows USN Journal equivalent optional.
**Requirements:** completes FIM-02
**Plans:** 0 plans

### Phase 999.4: Full YARA-rule engine for native scan (BACKLOG)

**Goal:** [Deferred from Phase 50 at execution] Add real YARA-rule evaluation to the agent's native file scanner. Phase 50 rejected `yara-x` because it pulls `wasmtime` + `cranelift` (a JIT engine — unacceptable bloat + cross-compile risk for the lean agent) and shipped a fallback (SHA256 hash-signature DB + `aho-corasick` literal-pattern matching over the feed's rule string literals). A future engine could revisit yara-x with a leaner backend, a WASM-free YARA interpreter, or a compiled-rule subset — only if it cross-compiles to `x86_64-pc-windows-gnu` cleanly and stays reasonably sized.
**Requirements:** completes NSCAN-01 (full YARA rules)
**Plans:** 0 plans
