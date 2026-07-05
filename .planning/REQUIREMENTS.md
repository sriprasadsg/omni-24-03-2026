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

- [x] **AI-05**: The scheduled compliance PDF report includes an AI-generated executive summary paragraph (≤ 150 words) describing the tenant's overall compliance posture for the reporting period; the summary is generated by `ai_service.generate_text` and injected into `_build_pdf` before the metrics table
- [x] **AI-06**: Each framework section in the PDF includes an AI-generated findings narrative (≤ 200 words per framework) that names the top 3 failing controls by name and suggests remediation priorities in plain language; narrative generation failures are logged and fall back to a static template so report delivery is never blocked

## v2.0 Requirements

**Implementation status note (updated 2026-07-05):** Phases 14–22 are now all verified complete — backend code, tests, and (per this session's audit) actual frontend nav wiring. As of the 2026-07-02 backfill, most of the bugs blocking checkboxes below (broken test collection, mock-patching mismatches, auth-wiring 401s) had already been fixed in the tree but the requirement statuses hadn't been re-checked; this session re-ran every test suite directly and confirmed passing, and found + fixed a second class of gap the 07-02 backfill didn't check for: five dashboards (`SaaSIntegrationsDashboard`, `PrivacyLegalDashboard`, `CloudAccountsDashboard`, `NotificationsDashboard`, `ApiExtensionsDashboard`) were fully built but had zero references outside their own component file — no lazy import, no route, no Sidebar nav entry — identical to the gap `16-VERIFICATION.md` caught for `ProgramsDashboard` on 2026-07-04. All five now have nav entries (commit wiring them into `App.tsx`/`Sidebar.tsx`/`types.ts`). ROADMAP.md/STATE.md phase-status tables still need a matching update — flagged as a follow-up.

### Evidence Review Workflow (Phase 15)

- [x] **REV-01**: Any authenticated user can submit an evidence item for review (`POST /api/evidence/{evidence_id}/submit-for-review`); a user with role `admin`, `super_admin`, or `compliance_reviewer` can then approve, reject, or request changes on it (`PATCH /api/evidence/{evidence_id}/review/{review_id}`), with a comment required for reject/request-changes decisions
- [x] **REV-02**: A review decision updates the evidence's status accordingly — `approved` (counts toward compliance score), `rejected`, or `needs_revision` — and the full review thread (reviewer, decision, comment, timestamp) is retrievable via `GET /api/evidence/{evidence_id}/reviews`, sorted newest-first
- [x] **REV-03**: A tenant's pending-review evidence queue is listable (`GET /api/evidence/pending-review`) and every review read/write is scoped to the acting user's own tenant — a reviewer in one tenant cannot view or decide on another tenant's review records

### SaaS Evidence Integration (Phase 14)

- [x] **SAAS-01**: OAuth 2.0 authorization code flow for GitHub, Jira, Okta, Google Workspace, and Slack, each with `/authorize` and `/callback` endpoints; access/refresh tokens stored Fernet-encrypted in `saas_connections`
- [x] **SAAS-02**: Per-provider evidence pull (GitHub PRs/advisories/branch-protection/code-scanning, Jira compliance issues, Okta MFA/user list, Google Workspace 2SV/sharing, Slack retention policy) mapped via `COMPLIANCE_CHECK_MAPPINGS`; `POST /api/saas/connections/{id}/pull-evidence` writes to `control_evidence` with `source='saas-{provider}'`
- [x] **SAAS-03**: `GET /api/saas/connections` lists tenant connections with status/last_synced/evidence_count; `DELETE /api/saas/connections/{id}` revokes the token and removes the record
- [x] **SAAS-04**: `SaaSIntegrationsDashboard.tsx` shows all 5 provider cards with an OAuth popup connect flow, per-integration last-synced/evidence-count display, and a Pull Evidence Now action

*Verified complete: `saas_integration_service.py`/`saas_integration_endpoints.py`/`SaaSIntegrationsDashboard.tsx` all exist, `saas_integration_endpoints` is registered in `router_registry.py`, and `pytest tests/test_saas_integration.py` passes 10/10. Only phase in this milestone with a `SUMMARY.md`/`REVIEW.md` on disk.*

### Program Control Grouping (Phase 16)

- [x] **PROG-01**: `POST /api/programs` creates a named program (name, description, framework_id, owner, control_ids); `PUT /api/programs/{id}/controls` manages membership via `{add, remove}`
- [x] **PROG-02**: `GET /api/programs/{id}` returns the program with a computed `status_rollup` (total/passing/failing/not_assessed, with compliant ≥80%-passing / at_risk / in_progress thresholds); `GET /api/programs` lists all programs with rollup summaries
- [x] **PROG-03**: `DELETE /api/programs/{id}` removes the program document without deleting underlying evidence

*Verified complete 2026-07-05: the `TestClient` import bug was fixed (`tests/test_program_service.py` now collects and 7/7 pass, re-run directly). `ProgramsDashboard.tsx` was also wired into `App.tsx`/`Sidebar.tsx` navigation (commit `0048555`, then independently re-confirmed reachable this session) — a `16-VERIFICATION.md` from 2026-07-04 had caught it as orphaned before that fix landed.*

### Cloud Checks Expansion (Phase 17)

- [x] **CC-EXP-01**: Cloud check library expanded from 67 to 300+ checks across AWS (EKS, Lambda, CloudFront, WAF, SNS, SQS, ElasticSearch, Route53, ACM, Inspector, SSM, Backup), Azure (App Service, ACR, AKS), and GCP (BigQuery, GKE)
- [x] **CC-EXP-02**: Each new check carries `id`/`name`/`description`/`provider`/`service`/`severity`/`control_ids`/`remediation_steps`; checks organized into per-provider modules imported by `cloud_checks_service.py`

*Verified complete: `cloud_checks_service.py` imports AWS (147) + Azure (77) + GCP (69) + K8s (20) + DigitalOcean (10, added in Phase 22) = 323 total, confirmed by direct import — exceeds the 300+ target. `tests/test_cloud_checks_expansion.py` remains an empty stub (no dedicated correctness test suite), which is a real test-coverage gap worth filling but does not block the requirement text as written.*

### Privacy & Legal Modules (Phase 18)

- [x] **PRIV-01**: Transfer Impact Assessments (`POST /api/privacy/tia`) and Legitimate Interest Assessments (`POST /api/privacy/lia`) with their respective required fields
- [x] **PRIV-02**: Privacy Notices with versioning — `GET`/`POST /api/privacy/notices`, `GET /api/privacy/notices/{id}/versions`
- [x] **PRIV-03**: Contract Lifecycle tracking — `POST /api/privacy/contracts`, `GET /api/privacy/contracts/expiring` (30-day window)
- [x] **PRIV-04**: `PrivacyLegalDashboard.tsx` with 4 tabs (TIA/LIA/Notices/Contracts), backed by a passing 8-test suite

*Verified complete 2026-07-05: the `get_database` mock-patching mismatch was fixed — `pytest tests/test_privacy_service.py` passes 8/8, re-run directly. `PrivacyLegalDashboard.tsx` was orphaned (zero references outside its own file, distinct from the older `PrivacyDashboard.tsx` which was wired) until this session added its nav entry under Governance & Compliance.*

### Additional Compliance Frameworks (Phase 19)

- [x] **FW-01**: 14 new compliance framework modules (ENS, MAS TRM, IRAP, ISO 27017, ISO 27018, BSI C5, FFIEC, OWASP Top 10, TISAX, AWS Well-Architected, RBI CSF, TIC 3.0, KISA ISMS, FedRAMP High) added to `backend/frameworks/`

*Verified complete 2026-07-05: all 14 files exist as `.py` modules (not `.json` as originally planned — matches the existing convention used by the 35+ pre-existing frameworks like `gdpr.py`/`hipaa.py`/`soc2.py`), each with substantive `CONTROLS` lists, and all 14 are imported and registered in `compliance_frameworks_endpoints.py`'s framework map. This was previously marked "not started" because that check only looked for `.json` files.*

### Multi-Account Cloud Scanning (Phase 20)

- [x] **CLD-01**: `POST /api/cloud-accounts` registers a cloud account (provider, account_id, account_name, encrypted `credentials_ref`, environment); `GET /api/cloud-accounts` lists registered accounts
- [x] **CLD-02**: `POST /api/cloud-accounts/{id}/scan` triggers an async check run; `GET /api/cloud-accounts/{id}/results` returns per-account results
- [x] **CLD-03**: `GET /api/cloud-accounts/summary` returns an aggregated cross-account view; `POST /api/cloud-accounts/discover-org` discovers AWS Organizations member accounts

*Verified complete 2026-07-05: `cloud_account_endpoints.py` exists (module name is singular "account", not "accounts" as the plan's file list said) with all 6 routes, registered in `router_registry.py`. `pytest tests/test_cloud_accounts.py` passes 14/14, re-run directly. `CloudAccountsDashboard.tsx` was orphaned until this session added its nav entry under Security (SecOps).*

### Notification Routing & Domain Scanner (Phase 21)

- [x] **NOTIF-01**: `POST /api/notifications/channels` creates a channel (slack/email/webhook); `POST /api/notifications/rules` creates a routing rule (event_type, channel_ids, severity_filter)
- [x] **NOTIF-02**: `notification_service.send_notification()` matches rules to channels and delivers via Slack webhook, logged email (SMTP deferred), or generic webhook POST
- [x] **SCAN-01**: `GET /api/domain-scanner/scan?domain=...` returns subdomains, open ports (common set), TLS cert info, and DNS record types
- [x] **SCAN-02**: `POST`/`GET /api/domain-scanner/scheduled` registers and lists domains for periodic scanning

*Verified complete 2026-07-05: the auth-wiring bug behind the 401s was fixed — `pytest tests/test_notification_service.py` passes 7/7, re-run directly. `NotificationsDashboard.tsx` (which bundles both the notification-routing and domain-scanner tabs) was orphaned until this session added its nav entry under Automation & Intelligence.*

### API Extensions (Phase 22)

- [x] **API-01**: MCP protocol server — `GET /api/mcp/tools` lists tools (`list_frameworks`, `get_control_status`, `run_cloud_check`, `list_findings`, `get_compliance_score`); `POST /api/mcp/execute/{tool_name}` executes one
- [x] **API-02**: OCSF-formatted output — `GET /api/ocsf/findings` (`class_uid: 2004`) and `GET /api/ocsf/cloud-checks` (`class_uid: 5001`)
- [x] **API-03**: 10 DigitalOcean cloud checks added to `CLOUD_CHECKS` (firewall, managed DB encryption, Spaces public access, LB SSL, droplet monitoring, VPC isolation, DB backups, k8s auto-upgrade, App Platform HTTPS, snapshot retention)
- [x] **API-04**: CLI tool (`backend/scripts/omni-cli.py`, Click) with `frameworks`/`scan`/`findings`/`score` commands calling the local API

*Verified complete 2026-07-05: `mcp_server_endpoints`/`ocsf_endpoints` registered and expose the expected routes, `scripts/omni-cli.py` exists, and the 10 DO checks are present in `cloud_checks_service.py`. No dedicated test suite exists for this phase (none was in the original plan's file list either), so correctness beyond "code loads and routes exist" is unverified — a coverage gap, not a functionality gap. `ApiExtensionsDashboard.tsx` was orphaned until this session added its nav entry under DevSecOps & Engineering.*

## v2.1 Requirements

### IaC & Container Security (Phase 24)

- [x] **IAC-01**: `POST /api/iac/scan` accepts code content or a git repo URL and returns check results (`check_id`, `severity`, `status`, `message`, `line_ref`) across 25+ checks spanning Terraform, CloudFormation, and Kubernetes manifests
- [x] **IAC-02**: `POST /api/container/scan` accepts an `image_name:tag` and returns vulnerability results (Trivy-backed when available, simulated fallback otherwise); `GET /api/iac/results` and `GET /api/container/results` return tenant-scoped scan history
- [x] **IAC-03**: `POST`/`GET /api/iac/scan-config` manages scanner config (excluded paths, severity threshold, auto-scan); all 8 unit tests in `test_iac_scanner.py` pass

*Verified complete 2026-07-05: all 16 `24-REVIEW.md` findings (5 critical — inverted Terraform PASS/FAIL logic, Kubernetes always-FAIL override, missing CloudFormation checks, broken RBAC test override, dashboard/API type mismatch — plus 8 warning + 3 info findings) were fixed across commits `4b9b0f6`..`0acb855`. `pytest tests/test_iac_scanner.py` passes 8/8, re-run directly. Dashboard restyled from inline dark theme to Tailwind per `24-UI-SPEC.md` and wired into `App.tsx`/`Sidebar.tsx`/`types.ts` navigation (`view: 'iacContainer'`, Security (SecOps)) — confirmed reachable via production build chunk output, avoiding the orphaned-dashboard pattern seen in phases 14/18/20/21/22.*

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
| REV-01 | Phase 15 | Complete |
| REV-02 | Phase 15 | Complete |
| REV-03 | Phase 15 | Complete |
| SAAS-01 | Phase 14 | Complete |
| SAAS-02 | Phase 14 | Complete |
| SAAS-03 | Phase 14 | Complete |
| SAAS-04 | Phase 14 | Complete |
| PROG-01 | Phase 16 | Complete |
| PROG-02 | Phase 16 | Complete |
| PROG-03 | Phase 16 | Complete |
| CC-EXP-01 | Phase 17 | Complete |
| CC-EXP-02 | Phase 17 | Complete |
| PRIV-01 | Phase 18 | Complete |
| PRIV-02 | Phase 18 | Complete |
| PRIV-03 | Phase 18 | Complete |
| PRIV-04 | Phase 18 | Complete |
| FW-01 | Phase 19 | Complete |
| CLD-01 | Phase 20 | Complete |
| CLD-02 | Phase 20 | Complete |
| CLD-03 | Phase 20 | Complete |
| NOTIF-01 | Phase 21 | Complete |
| NOTIF-02 | Phase 21 | Complete |
| SCAN-01 | Phase 21 | Complete |
| SCAN-02 | Phase 21 | Complete |
| API-01 | Phase 22 | Complete |
| API-02 | Phase 22 | Complete |
| API-03 | Phase 22 | Complete |
| API-04 | Phase 22 | Complete |
| IAC-01 | Phase 24 | Complete |
| IAC-02 | Phase 24 | Complete |
| IAC-03 | Phase 24 | Complete |

**Coverage:**

- v1.1 requirements: 13 total, all complete
- v1.2 requirements: 2 total, all complete
- v1.3 requirements: 3 total, 2 complete
- v1.4 requirements: 4 total, all complete
- v1.5 requirements: 2 total, 0 complete
- v2.0 requirements: 30 total, all 30 complete as of 2026-07-05 (re-ran every phase's test suite directly and fixed 5 orphaned-dashboard nav-wiring gaps — see per-phase notes above and the milestone note at the top of this section)
- v2.1 requirements: 3 total (IAC-01..03), all complete — verified 2026-07-05 (8/8 tests pass, dashboard restyled and wired into navigation)
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-20*
*Last updated: 2026-07-02 — Phase 15 REV-01/02/03 backfilled and verified complete; remaining v2.0 phases (14, 16–22) backfilled with as-found implementation status*
