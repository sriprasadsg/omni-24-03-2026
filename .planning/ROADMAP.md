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
- 🚧 **v4.2 Catalogue Access Control & Asset Costing** — Role-scoped visibility of the left-nav catalogues enforced on both the sidebar and the backend routes (one effective-permission resolver, a shared catalogue manifest, a deny-by-default route-parity test), plus an organization- and endpoint-level asset cost view in the ITAM console built on the existing book-value and license data. 6 phases (75–80), 17 requirements. In progress — started 2026-10-12.

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

### Phase 74: Interactive Remote Desktop Control (Zoho Assist parity)

**Goal:** Upgrade the existing view-only remote-desktop stream (`components/RemoteDesktop.tsx`, `agent-install/omni-agent-rs/src/capabilities/remote_access.rs`) to full attended interactive control: mouse/keyboard input relay from viewer to agent over the existing WebSocket tunnel, Win32 `SendInput`-based replay on the Windows agent, an on-endpoint consent/accept prompt before control is granted, a new `control:remote_access` RBAC permission distinct from the existing `view:remote_access`, and session audit logging. Faster/continuous screen capture (replacing the periodic PowerShell screenshot loop) is in scope as a stretch goal if time allows.
**Requirements**: TBD
**Depends on:** Phase 73
**Plans:** 5 plans

Plans:

- [x] 74-01-PLAN.md — Tracer: one mousemove end-to-end from canvas through the `/user` tunnel to `SendInput`, behind the new `control:remote_access` gate (wave 1)
- [x] 74-02-PLAN.md — Backend: append-only control-session audit trail, real `close_session` kill switch, disconnect/force-kill, agent-authenticated consent reporting, capability probe (wave 2)
- [x] 74-03-PLAN.md — Rust agent: Session-0 consent dialog, persistent stop-control bar, consent-gated full input replay (wave 3)
- [x] 74-04-PLAN.md — Python legacy agent: pywin32 session injection, ctypes `SendInput` relay, closing the dropped-receive gap (wave 3)
- [x] 74-05-PLAN.md — Frontend: four-state control canvas, permission-gated View/Control toggle, disconnect and force-end affordances (wave 3)

## v4.2 — Catalogue Access Control & Asset Costing (Phases 75–80) — IN PROGRESS

- [ ] **Phase 75: Permission Resolver & Single Source of Truth** - Every role, including the ITAM roles, logs in with a complete server-evaluated permission set drawn from one defaults table
- [ ] **Phase 76: Catalogue Manifest & Backend Route Enforcement** - One shared manifest defines each catalogue's permission and routes; priority route groups are guarded; a deny-by-default parity test and gap ledger keep them honest
- [ ] **Phase 77: Fail-Closed Sidebar, View Gate & Role Visibility** - Users see, reach, and are told about exactly the catalogues their role allows, and role edits take effect without re-login
- [ ] **Phase 78: Organization & Endpoint Cost API** - Tenant-isolated, read-only cost summary and per-asset cost computed by the same book-value function as the ITAM KPI tile
- [ ] **Phase 79: License Cost & Per-Endpoint Allocation** - Licenses can carry a cost, and license spend is reported at org level and allocated to endpoints without double-counting
- [ ] **Phase 80: Costs Tab in the ITAM Console** - Operators read and export org and endpoint costs from a Costs tab in the existing ITAM console

### Phase 75: Permission Resolver & Single Source of Truth

**Goal**: Every user, including those on the ITAM roles, receives a complete, server-evaluated permission set at login from one defaults table, so the rest of the milestone can rely on a single answer to "what may this user do".
**Depends on**: Nothing (first phase of this milestone)
**Requirements**: ACC-01, ACC-02
**Success Criteria** (what must be TRUE):
  1. A user holding any of the three ITAM roles (`itam_admin`, `itam_user`, `itam_viewer`) logs in and receives a non-empty effective permission list from both `/login` and `/me`; no role comes back with an empty list.
  2. `/login` and `/me` return the same effective permission set for the same user, because both call one resolver that unions the role document's permissions with that role's defaults (a test proves the two endpoints agree).
  3. Exactly one permission-defaults table exists: the `rbac_utils.DEFAULT_PERMISSIONS` / `rbac_service.default_roles` divergence is gone, a test fails if a second copy drifts, and `control:remote_access` stays distinct from `view:remote_access`.
  4. The `itam_admin`, `itam_user`, and `itam_viewer` role documents exist after startup seeding and appear in an admin's role list, while pre-existing custom roles still resolve correctly with no data migration.

**Plans**: 5/5 plans executed

Plans:
**Wave 1**
- [x] 75-01-PLAN.md — Tracer: single table (rbac_defaults.py) + effective_permissions resolver through /login and /me; verify_permission/RBACService delegate; golden sets (wave 1)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 75-02-PLAN.md — Startup mirrors the table into 11 shared role docs via {name, tenantId}; signup + MFA verify deliver resolver permissions (wave 2)
- [x] 75-03-PLAN.md — Real GET /api/roles (manage:users or manage:rbac); frontend fails closed, role-list cache cleared (wave 2)
- [x] 75-04-PLAN.md — Bundle assignment super-admin only (D-06); shared role-assignment ceiling for user CRUD (D-18/D-20/D-21) (wave 2)

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 75-05-PLAN.md — LDAP/SAML mapping ceiling + apply-time super-admin block (D-22); archive one-off scripts; AST drift guard (wave 3)

### Phase 76: Catalogue Manifest & Backend Route Enforcement

**Goal**: Each in-scope left-nav catalogue is defined once in a shared manifest, and the backend refuses what the sidebar would hide, with a deny-by-default test that fails whenever the two drift.
**Depends on**: Phase 75
**Requirements**: ACC-03, ACC-04, ACC-05
**Success Criteria** (what must be TRUE):
  1. One shared manifest maps every left-nav catalogue to its required permission and backend route(s); `Sidebar.tsx` and the `App.tsx` view-permission lookup both read it, the two divergent tables are gone, and each of the 9 previously mismatched views resolves to exactly one permission.
  2. A user lacking the matching `view:` permission receives 403, not data, from the Assets, ITAM, Settings, financial, identity, and security-operations route groups, while a user holding it still gets 200; asset read responses no longer expose purchase-cost fields to a user without `view:itam`.
  3. Agent enrollment and heartbeat traffic on `/api/agents/*` and existing API-key callers on the ITAM routers keep working unchanged after the guards land.
  4. A committed gap ledger lists every router that remains unguarded, and the deny-by-default route-parity test fails if an in-scope catalogue route is unguarded or an unguarded router is missing from the ledger.
  5. A frontend test fails when the sidebar and the manifest drift (for example, a nav item added with no manifest entry).

**Plans**: 15/15 plans executed (gap-closure plans 76-13..76-15 done; re-verification pending)

Plans:
**Wave 1**
- [x] 76-01-PLAN.md — Tracer: MDM end to end (manifest seed, catalogue_guard, mount registry, route walker + parity helper, frontend reader)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 76-02-PLAN.md — Complete catalogue manifest (202 views, D-08/D-09/D-11, confirmed route ownership) + manifest tests

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 76-03-PLAN.md — Sidebar.tsx and App.tsx read the manifest; frontend drift test
- [x] 76-04-PLAN.md — Guards: Assets, ITAM, Certificates; asset finance-field strip (D-04/D-10)
- [x] 76-05-PLAN.md — Guards: agents console, remote access, chat/support, jobs (agent routes untouched)
- [x] 76-06-PLAN.md — Guards: patching, deployments, software, device management
- [x] 76-07-PLAN.md — Guards: Security detection and response catalogues
- [x] 76-08-PLAN.md — Guards: Security posture (cloud, app, data, vulnerabilities)
- [x] 76-09-PLAN.md — Guards: billing, FinOps, tenants, users/roles/API keys, SSO/LDAP admin
- [x] 76-10-PLAN.md — Guards: settings, platform operations, integrations
- [x] 76-12-PLAN.md — Guards: agent data-plane routers (tasks, security scans, telemetry, agentic tasks, uninstall; agent ingest untouched)

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 76-11-PLAN.md — Gap ledger, strict deny-by-default parity, final regression

**Wave 5 (gap closure)** *(blocked on Wave 4 completion)*
- [x] 76-13-PLAN.md — WR-01 routes: agent-tolerant and platform-read guard variants; agent-tolerant guards on the agent-capable reads (installer download, response-task poll, agent-chat list)

**Wave 6 (gap closure)** *(blocked on Wave 5 completion)*
- [x] 76-14-PLAN.md — WR-01 gate: parity gate covers agent-capable routes; reviewed agentCapableRoutes and exemptRoutes lists in the ledger

**Wave 7 (gap closure)** *(blocked on Wave 6 completion)*
- [x] 76-15-PLAN.md — WR-05: tenant email, license, allowlist and install-key reads role-gated (tenant admin + platform staff); branding exemption reworded; gate refuses self-service exemptions on tenant/user paths

### Phase 77: Fail-Closed Sidebar, View Gate & Role Visibility

**Goal**: A user sees, can reach, and is told about exactly the catalogues their role allows, and a role-permission edit takes effect without a full re-login.
**Depends on**: Phase 76
**Requirements**: ACC-06, ACC-07, ACC-08, ACC-09
**Success Criteria** (what must be TRUE):
  1. A catalogue the user lacks permission for is absent from the sidebar, and reaching it by URL hash, deep link, or any in-app navigation shows a no-access state instead of its content; there is no fail-open fallback when permissions are missing or unknown.
  2. A user with no permitted catalogue sees a clear no-access state with a guaranteed landing view and a working Sign out, never an empty sidebar they cannot leave (an `itam_viewer` without `view:dashboard` still lands somewhere valid).
  3. An admin opens a "what can this role see" view and sees, for each role, which catalogues it can access, matching what the backend enforces.
  4. After an admin edits a role's permissions, the affected user's sidebar updates on the next window focus or 403 response, without logging out and back in.
  5. Regression tests prove catalogue visibility and route guards hold per role and per tenant, including super-admin and `platform-admin` handling, and that one tenant's role edit never changes another tenant's users.

**Plans**: 1/13 plans executed
**UI hint**: yes

Plans:
**Wave 1**
- [x] 77-01-PLAN.md — Tracer: one manage:X => view:X/request:X closure in the resolver (itam_admin sees Assets and Certificates) + screen-off markers for switched-off nav screens (D-11, D-16)
- [ ] 77-02-PLAN.md — Tracer: render-time view gate with the in-place no-access panel, D-06/D-12 landing, every navigation path (D-05, D-06, D-12)

**Wave 2** *(blocked on Wave 1 completion)*
- [ ] 77-03-PLAN.md — Tenant custom-role write API: create/edit/delete, ceiling, reserved and fixed names, delete refusal, builtIn flag, permission catalogue (D-01..D-03, D-13, D-15, D-17, D-18)
- [ ] 77-04-PLAN.md — Permission-based MFA so custom admin-tier roles cannot skip MFA (D-14)
- [ ] 77-05-PLAN.md — Permission refresh on 403 (leading + trailing debounce) and window focus + full-page zero-access screen with Retry and Sign out (D-07, ACC-08)
- [ ] 77-13-PLAN.md — Fail-closed sidebar on the gate's evaluateViewAccess, skeleton while permissions are unknown (ACC-06; split out of 77-02)

**Wave 3** *(blocked on Wave 2 completion)*
- [ ] 77-06-PLAN.md — Custom roles assignable to users, tenant moves and LDAP/SAML mappings (D-04, D-18)
- [ ] 77-07-PLAN.md — "What can this role see" endpoint computed by the delivery pipeline, equal to enforcement (D-09, D-10, D-17)
- [ ] 77-08-PLAN.md — Hide unreadable widgets and skip their fetches: startup, notifications, dashboard (D-08, D-17)

**Wave 4** *(blocked on Wave 3 completion)*
- [ ] 77-09-PLAN.md — Settings > Roles: "What it can see" panel, Built-in/Custom chips, D-10 tab access, Super Admin tenant targeting
- [ ] 77-10-PLAN.md — Backend regression: cross-tenant isolation, super-admin spellings, real-app sample, full suite (SC5)

**Wave 5** *(blocked on Wave 4 completion)*
- [ ] 77-11-PLAN.md — Server-backed custom role editor: grantable list, implied and locked permissions, fixed name (D-01, D-02, D-13)

**Wave 6** *(blocked on Wave 5 completion)*
- [ ] 77-12-PLAN.md — Delete confirmation and refusal flow, browser-memory role store removed, super-admin checks unified, frontend phase gate (D-03, D-15)

### Phase 78: Organization & Endpoint Cost API

**Goal**: A tenant user with ITAM view access can read the organization's total asset cost and each endpoint's cost, computed by the same function that feeds the ITAM KPI tile, and can never see another tenant's numbers.
**Depends on**: Phase 76
**Requirements**: COST-01, COST-02, COST-03, COST-06, COST-07
**Success Criteria** (what must be TRUE):
  1. `GET /api/itam/costs/summary` returns the tenant's total purchase cost and current depreciated book value together with coverage (assets with cost data versus total), and assets lacking cost data are reported as null, never as 0.
  2. `GET /api/itam/costs/assets` (paginated) and `GET /api/itam/costs/assets/{id}` return each asset's purchase cost and book value, including agent-discovered endpoints, which are assets joined only via `agents.assetId`.
  3. The ITAM KPI tile, the existing asset-value report, and the cost summary show identical figures for the same tenant, enforced by a parity test over a shared per-asset computation and a golden-value table.
  4. Disposed and retired assets are excluded from current book value by default and counted in historical purchase totals only when an explicit filter is set, with the same rule in the KPI and the cost view.
  5. Every cost route returns 403 without `view:itam`, returns 400 for a `platform-admin` context with no tenant, and passes a two-tenant isolation test proving tenant A never sees tenant B's cost data.

**Plans**: TBD

### Phase 79: License Cost & Per-Endpoint Allocation

**Goal**: A tenant can record what a license costs and see license spend at organization level and allocated to individual endpoints, with every cent accounted for.
**Depends on**: Phase 78
**Requirements**: COST-04, COST-05
**Success Criteria** (what must be TRUE):
  1. An ITAM admin can enter an optional license cost (whole cents plus a billing basis) in the license form and see it displayed as formatted currency, and licenses without a cost still load and save exactly as before.
  2. The organization cost summary reports total license spend with coverage, treating licenses with no cost as "not tracked" rather than 0.
  3. An endpoint's cost view shows the license cost allocated from seats assigned to that asset, and seats assigned to users appear in a separate "unattributed" bucket rather than being pinned to an endpoint.
  4. For every tested seat configuration, including licenses with more than 1,000 seats, the sum of endpoint allocations plus the unallocated amount equals organization license spend.
  5. License cost lines stay tenant-isolated, proven by a two-tenant test on the extended cost routes.

**Plans**: TBD
**UI hint**: yes

### Phase 80: Costs Tab in the ITAM Console

**Goal**: Operators can read the organization summary and per-endpoint cost breakdown inside the existing ITAM console and export what they see.
**Depends on**: Phase 79
**Requirements**: COST-08
**Success Criteria** (what must be TRUE):
  1. A "Costs" tab appears in the ITAM console for users with ITAM access, with no new sidebar module and no new permission, and is absent for users without it.
  2. The tab shows total purchase cost, current book value, and license spend, with a coverage banner stating how many assets lack cost data and how disposed assets are treated.
  3. A paginated per-asset table shows purchase cost, book value, and allocated license cost, renders missing values as "not tracked" instead of $0, and formats every amount through the shared currency formatter.
  4. Exporting the cost view through the existing report registry downloads the same figures shown on screen.

**Plans**: TBD
**UI hint**: yes

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 75. Permission Resolver & Single Source of Truth | 5/5 | In Progress | - |
| 76. Catalogue Manifest & Backend Route Enforcement | 15/15 | In Progress | - |
| 77. Fail-Closed Sidebar, View Gate & Role Visibility | 1/13 | In Progress | - |
| 78. Organization & Endpoint Cost API | 0/TBD | Not started | - |
| 79. License Cost & Per-Endpoint Allocation | 0/TBD | Not started | - |
| 80. Costs Tab in the ITAM Console | 0/TBD | Not started | - |
