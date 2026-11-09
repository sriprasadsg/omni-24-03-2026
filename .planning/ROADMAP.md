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
- ⏸ **v4.2 Catalogue Access Control & Asset Costing** — Role-scoped visibility of the left-nav catalogues enforced on both the sidebar and the backend routes (one effective-permission resolver, a shared catalogue manifest, a deny-by-default route-parity test), plus an organization- and endpoint-level asset cost view in the ITAM console built on the existing book-value and license data. 6 phases (75–80), 17 requirements. In progress — started 2026-10-12. Paused 2026-10-25 for v4.3; resumes after it.
- 🚧 **v4.3 Autonomous Ops** — One per-tenant autonomy level, one policy gate and one stop switch in front of every automatic action, with an audited Activity view and undo; automatic security response, staged patch rollouts, platform self-healing and first-line service-desk answers within limits an operator sets, asking a person only to approve destructive actions. 6 phases (81–86), 55 requirements. In progress — started 2026-10-25.

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
- [x] **Phase 77: Fail-Closed Sidebar, View Gate & Role Visibility** - Users see, reach, and are told about exactly the catalogues their role allows, and role edits take effect without re-login (completed 2026-10-21)
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

**Plans**: 13/13 plans complete
**UI hint**: yes

Plans:
**Wave 1**
- [x] 77-01-PLAN.md — Tracer: one manage:X => view:X/request:X closure in the resolver (itam_admin sees Assets and Certificates) + screen-off markers for switched-off nav screens (D-11, D-16)
- [x] 77-02-PLAN.md — Tracer: render-time view gate with the in-place no-access panel, D-06/D-12 landing, every navigation path (D-05, D-06, D-12)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 77-03-PLAN.md — Tenant custom-role write API: create/edit/delete, ceiling, reserved and fixed names, delete refusal, builtIn flag, permission catalogue (D-01..D-03, D-13, D-15, D-17, D-18)
- [x] 77-04-PLAN.md — Permission-based MFA so custom admin-tier roles cannot skip MFA (D-14)
- [x] 77-05-PLAN.md — Permission refresh on 403 (leading + trailing debounce) and window focus + full-page zero-access screen with Retry and Sign out (D-07, ACC-08)
- [x] 77-13-PLAN.md — Fail-closed sidebar on the gate's evaluateViewAccess, skeleton while permissions are unknown (ACC-06; split out of 77-02)

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 77-06-PLAN.md — Custom roles assignable to users, tenant moves and LDAP/SAML mappings (D-04, D-18)
- [x] 77-07-PLAN.md — "What can this role see" endpoint computed by the delivery pipeline, equal to enforcement (D-09, D-10, D-17)
- [x] 77-08-PLAN.md — Hide unreadable widgets and skip their fetches: startup, notifications, dashboard (D-08, D-17)

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 77-09-PLAN.md — Settings > Roles: "What it can see" panel, Built-in/Custom chips, D-10 tab access, Super Admin tenant targeting
- [x] 77-10-PLAN.md — Backend regression: cross-tenant isolation, super-admin spellings, real-app sample, full suite (SC5)

**Wave 5** *(blocked on Wave 4 completion)*
- [x] 77-11-PLAN.md — Server-backed custom role editor: grantable list, implied and locked permissions, fixed name (D-01, D-02, D-13)

**Wave 6** *(blocked on Wave 5 completion)*
- [x] 77-12-PLAN.md — Delete confirmation and refusal flow, browser-memory role store removed, super-admin checks unified, frontend phase gate (D-03, D-15)

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

## v4.3 — Autonomous Ops (Phases 81–86) — IN PROGRESS

*Execution shape: Phase 81 first; Phases 82, 83 and 85 can then run in parallel; Phase 84 follows 83; Phase 86 closes the milestone after 82–85. Ships inert: shadow mode and the environment dry-run floor stay on until an operator lifts a tenant (Phase 86). v4.2 Phases 75–80 above are untouched and resume after this milestone.*

- [x] **Phase 81: Autonomy Gate, Stop Switch & Activity Ledger** - One code-owned decision gate, a stop switch, write-ahead decision records and a read-only Autonomous Ops screen, with the legacy LLM remediation path removed (completed 2026-11-07)
- [x] **Phase 82: Platform Self-Healing & Scheduled Retention** - An external watchdog restarts what fails within a budget, warns before certificates expire or disks fill, pages on-call, and retention runs on a schedule (completed 2026-11-07)
- [x] **Phase 83: Autonomous Security Response** - Findings become undoable containment on their own and destructive approval cards, each verified, deduplicated and undoable from the Activity screen (completed 2026-11-07)
- [x] **Phase 84: Staged Patch Rollouts** - Ring-based patch rollouts with soak, a real health gate, maintenance windows and one approval per stage; halts on failure and reverts where supported (completed 2026-11-07)
- [ ] **Phase 85: First-Line Service Desk** - New tickets are answered from the knowledge base with citations or escalated by fixed rules, and never answered when the model is unavailable
- [ ] **Phase 86: Activity Reporting, Hardening & Live Validation** - Daily digest, per-rule statistics, export and a time-saved estimate, plus stop drills, two-tenant isolation checks and live validation across every automatic actor
- [x] **Phase 87: Partner and Reseller Channel** - Partners appointed by the Super Admin hold a seat pool, create their own customer organizations and assign seats to them; partner admins see only their customers (completed 2026-11-07)

### Phase 81: Autonomy Gate, Stop Switch & Activity Ledger

**Goal**: Every automatic action in the platform passes one code-owned decision gate that an operator can stop instantly, that records and audits each decision before anything is dispatched, and whose results appear on a new Autonomous Ops screen — with the legacy LLM-driven remediation path removed, so the engine is safe to switch on.
**Depends on**: Nothing in v4.3 (first phase). Builds on the already-deployed catalogue manifest and per-tenant feature switches; v4.2 Phases 78–80 are not prerequisites.
**Requirements**: GATE-01, GATE-02, GATE-03, GATE-04, GATE-05, GATE-06, GATE-07, GATE-08, GATE-09, GATE-10, GATE-11, GATE-12, GATE-13, GATE-14, ACTV-01, ACTV-03, ACTV-08
**Success Criteria** (what must be TRUE):
  1. Every tenant has an explicit stored autonomy level (Off / Suggest / Undoable-auto): existing tenants receive one from the migration and new tenants default to Undoable-auto. A tenant whose Autonomous Ops screen a Super Admin has not ticked is treated as Off (refused, nothing recorded), and a tenant whose level cannot be read is treated as Suggest. A Super Admin sets the highest level each tenant may use, a tenant admin can choose only at or below it, and changing a level, approving or undoing actions, and flipping the platform stop are separate permissions.
  2. Every automatic action passes one ordered decision function (platform stop, eligibility, tenant stop, level, action class, protected targets, blast-radius cap, cooldown and suppression), and a structural test fails if any other code writes an autonomous agent instruction. Block IP, quarantine file and restart service are classed auto; isolate host, kill process and patch reboot need approval; a playbook can raise a class but never lower it. The platform host, its own IP addresses and the management network can never be blocked, isolated or patched automatically, and a per-decision cap limits how many hosts one decision can touch.
  3. The legacy LLM-driven remediation path (`run_cycle` / `generate_plan` / `execute_plan`) and the 0.90 confidence auto-approve for automatic actions are gone, and a test proves only registry-listed playbook actions can reach the agent queue. Shadow mode is on by default at deployment: the gate records what it would have done and dispatches nothing. A Super Admin can flip a platform-wide stop and a tenant admin a per-tenant stop; either takes effect without a restart — new decisions halt, automatic instructions already queued are held back at the next agent poll, and pending approvals and rollouts freeze. When several automatic actions in a row for a tenant are undone or fail, that tenant drops to Suggest and the on-call channel is told.
  4. Every decision writes an intent record before dispatch (dispatch is refused if the record cannot be written), every state change is mirrored into the hash-chained audit ledger, and decision records are kept longer than generic retention. An approval dispatches exactly once even if clicked twice, and an approval left pending past its expiry counts as denied. Automatic sweeps run one at a time across the deployment, and a two-tenant test shows no action or record crosses tenants. Agent online/offline status refreshes every 5 minutes as documented.
  5. An operator with the Autonomous Ops screen enabled and the matching permission opens it from the catalogue and sees actions in the states Pending, Done, Undone, Failed, Refused and Suggested, each with what ran, why (the rule), the target and the result; in shadow mode "would have done" entries are clearly labelled as a simulation. A copy check fails the build if Autonomous Ops screens or docs use any of the banned terms listed in ACTV-08.

**Plans**: 18/18 plans complete (12/12 original plans executed in 5 waves; 6 gap-closure plans 81-13..81-18 in waves 5-8, not executed)
**UI hint**: yes
**Research**: None — internal composition over code already read (standard patterns).
**Live-only verification** (operator steps, not unit-testable): apply migration 024 and restart the backend; flip the platform stop on the live server and confirm a real agent poll holds back a queued automatic instruction without a restart; confirm agent online/offline status refreshes on the 5-minute cadence. Until Phase 83 adds a security sweep nothing automatic runs, so live Activity data is limited to gate and shadow entries — intended.
**Decisions to settle before planning**: D1–D4 (see `.planning/research/SUMMARY.md`).

Plans:
**Wave 1**
- [x] 81-01-PLAN.md — Tracer: decision core package part 1 (registry with GATE-04 raise-only pinned on the vendored playbooks, settings, write-ahead ledger, ordered gate structure with eligibility/class/shadow steps, the only stamped writers) (GATE-02/03/04/07/09; D-02, D-04, D-16, D-23)
- [x] 81-02-PLAN.md — Tracer: catalogue entry, tenant switch and the four permission strings; approve tier MFA-gated, platform stop platform-only (GATE-13, ACTV-01; D-05..D-09)
- [x] 81-03-PLAN.md — Tracer: agent status cadence fix, lock renewal, tenant-filtered duplicate check, legacy loop removed, folded Rust todo closed (GATE-11/12, GATE-05; D-24)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 81-11-PLAN.md — Tracer: decision core part 2 (never-touch list, host cap, rate limit, dedupe/cooldown, stops and level, both shadow layers, messages module, exhaustive enumeration) (GATE-02/03/04/08/09; D-02, D-04, D-17, D-19, D-20, D-23)
- [x] 81-07-PLAN.md — Read-only Autonomous Ops screen: activity list in six states plus simulation, shared status poller (ACTV-01/03; D-22)

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 81-04-PLAN.md — Approvals (single-use, 24 h expiry), undo, circuit breaker, reconciler under a renewed lock, two-tenant isolation (GATE-10/11/14; D-12, D-13, D-16, D-18)
- [x] 81-05-PLAN.md — Stop switch press/clear and hold-back at every agent delivery path including response tasks (GATE-06; D-11..D-15, D-21)
- [x] 81-06-PLAN.md — XDR auto-playbook fence, selectors record suggestions only, 0.90 confidence bypass removed (GATE-03/05; D-21)
- [x] 81-12-PLAN.md — Tracer: migration 024 gives every tenant an explicit stored level (platform-admin Off) and new tenants get the default at creation (GATE-01; D-01, D-24)

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 81-08-PLAN.md — Remediation routed through the gate (shipped block_ip playbook stays automatic), legacy LLM path deleted, structural tests (GATE-03/04/05/07/10; D-24)
- [x] 81-09-PLAN.md — Tenant and platform API routes with the permission matrix and D-25 name masking (GATE-06/08/09/13, ACTV-01; D-03, D-08, D-10, D-11, D-25)

**Wave 5** *(blocked on Wave 4 completion)*
- [x] 81-10-PLAN.md — Status card, Stop/Resume dialogs (tenant and platform), app-wide stop banner, ACTV-08 copy check (ACTV-08, GATE-06; D-15, D-22, D-25)

**Gap closure** *(from 81-VERIFICATION.md gaps_found 4/6 and 81-REVIEW.md CR-01, CR-02, WR-01, WR-02, WR-03)*
- [x] 81-13-PLAN.md — Wave 5: Tracer: the gate decides every playbook step and compensation step with its own parameters and registry class, records the decided plan, multi-step rows record no undo (GATE-03/04/08/10, ACTV-01)
- [x] 81-14-PLAN.md — Wave 5: Tracer: picked-up-but-silent instructions fail no_result after a bound (WR-01); a manual level change re-arms a tripped breaker (WR-02) (GATE-07/11/14)
- [x] 81-15-PLAN.md — Wave 6: Tracer: gate.execute / execute_response_task bound to the decided row (command, agent, params, never-touch at dispatch); existing tests aligned (GATE-03/08/10)
- [x] 81-16-PLAN.md — Wave 6: Tracer: tenant-scoped playbook selection; "Undone" only when every compensation step is confirmed, else failed rollback_incomplete with escalation; breaker sees remediation outcomes (GATE-07/08/11/14, ACTV-01)
- [x] 81-17-PLAN.md — Wave 7: Tracer: deployment shadow master fails closed and is read live by every path (WR-03); structural stamp scan survives an unparsable tracked file (GATE-09, GATE-03)
- [x] 81-18-PLAN.md — Wave 8: Tracer: approve re-checks the never-touch list against every recorded step and compensation step; approvals.undo refuses multi-step rows (no_undo) (GATE-08/10, ACTV-01)

### Phase 82: Platform Self-Healing & Scheduled Retention

**Goal**: The platform watches its own health from outside the backend, restarts what fails within a budget, warns well before certificates expire or disks fill, pages the on-call person, and runs data retention on a schedule without ever touching audit evidence.
**Depends on**: Phase 81 (stop switch, decision ledger, platform-scope Activity view, and the 5-minute agent status refresh from GATE-12). Independent of Phases 83–85 — can run in parallel with them.
**Requirements**: HEAL-01, HEAL-02, HEAL-03, HEAL-04, HEAL-05, HEAL-06, HEAL-07, HEAL-08
**Success Criteria** (what must be TRUE):
  1. When MongoDB, the backend or (only where expected) Ollama stops, the watchdog notices within about a minute and restarts it from a fixed allowlist, MongoDB before the backend; once the restart budget is used up it backs off, stops restarting and pages exactly once.
  2. The operator is warned 30, 14, 7 and 1 days before a certificate expires, when a disk passes 80, 90 and 95 percent, and days ahead when a disk will fill at its current growth rate; the platform never renews a certificate or deletes a file on its own.
  3. An operator can send a test alert to the configured webhook or PagerDuty channel and see it arrive once (deduplicated); a banner shows when no working channel is configured, and an alert fires when the watchdog itself stops reporting.
  4. Data retention runs on a schedule per tenant in bounded batches and never touches audit logs, the audit ledger or decision records; its first run is a dry-run count the operator confirms before anything is deleted.
  5. Watchdog events (checks, restarts, warnings, pages) appear in the Activity view at platform scope, and the repo ships the watchdog unit files, service drop-ins and an install checklist — the app itself installs nothing on the live server.

**Plans**: 17/17 plans complete: 14 in 6 waves, plus a gap round of 3 plans in 2 waves

Plans:
**Wave 1**
- [x] 82-01-PLAN.md — Wave 1: Tracer: token-authenticated watchdog sync stores heartbeat and turns events into platform-health ledger rows; leak guard keeps them out of tenant and Platform Support views; migration 025
- [x] 82-02-PLAN.md — Wave 1: Tracer: stdlib-only watchdog package checks MongoDB, backend, nginx, Ollama-expected-state, debounces, spools offline and syncs with the three-source stop
- [x] 82-06-PLAN.md — Wave 1: Tracer: oneshot unit and timer pass systemd-analyze; harness-proven polkit rule, non-clobbering drop-ins, example configs, INSTALL.md; app installs nothing
- [x] 82-09-PLAN.md — Wave 1: Tracer: first nightly retention run only counts; gate per tenant and type, bounded batches, 02:00 UTC catch-up under lock; telemetry loop folded in; migration 027

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 82-03-PLAN.md — Wave 2: Tracer: watchdog restarts a down mongod; budget 3 per 30 min with 1/2/4 min waits, gave-up incident once, re-arm after 1 h, MongoDB before backend, stop pauses restarts
- [x] 82-07-PLAN.md — Wave 2: Tracer: notify() queues on-call messages the watchdog drains; Send test alert request/result loop; watchdog-state function; migration 026
- [x] 82-10-PLAN.md — Wave 2: Tracer: Super Admin reviews and confirms retention counts (stale-proof token); manual run honours the gate; audit logs never deleted; next run time; Activity rows

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 82-04-PLAN.md — Wave 3: Tracer: certificate 30/14/7/1-day, disk 80/90/95 percent and 7-day forecast ladders as deduplicated incidents; never renews or deletes
- [x] 82-08-PLAN.md — Wave 3: Tracer: health summary on the shared status poller, full GET /health document, dead-man in-app alarm once per silence episode

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 82-05-PLAN.md — Wave 4: Tracer: watchdog pages PagerDuty/webhook once per incident with grouping and resolve, delivers outbox and test alerts, pings the external heartbeat; end-to-end contract test
- [x] 82-11-PLAN.md — Wave 4: Tracer: Super Admin health banners (watchdog silent, no working channel) in any scope; typed API surface and shared health chips

**Wave 5** *(blocked on Wave 4 completion)*
- [x] 82-12-PLAN.md — Wave 5: Tracer: Platform health section with watchdog and services, certificate, disk and on-call cards and Send test alert
- [x] 82-14-PLAN.md — Wave 5: Tracer: platform-health rows and filter pill in platform Activity only; tenant Retention Policy notices (D-16/D-19/D-25/D-26)

**Wave 6** *(blocked on Wave 5 completion)*
- [x] 82-13-PLAN.md — Wave 6: Tracer: retention review card and Confirm deletion dialog with the stale-count guard

**Gap round** (verification gaps; run with `/gsd-execute-phase 82 --gaps-only`)
- [x] 82-15-PLAN.md — Gap wave 1: Tracer: a tenant the first pass never reached is counted and confirmed before any delete; adoption keys on tenant creation time; each tenant guarded in run_all; confirm refused while the count is incomplete (HEAL-06, HEAL-07)
- [x] 82-16-PLAN.md — Gap wave 1: Tracer: one poison event no longer wedges the watchdog sync; certificate rule ids follow daysLeft, with cert-unreadable for an unreadable file (HEAL-03, HEAL-07)
- [x] 82-17-PLAN.md — Gap wave 2: Tracer: Confirm deletion waits for every row and a complete count; the dialog cannot be dismissed mid-request; Run Cleanup Now reports refusals; UI-SPEC amended (HEAL-06)

**UI hint**: yes
**Research**: Light — polkit/sudoers scoping for the watchdog and its MongoDB authentication path (MongoDB auth is still an open readiness item).
**Live-only verification** (operator steps): install the watchdog units, drop-ins and any scoped sudoers/polkit rule (never `run-on-ubuntu.sh`); stop and start MongoDB and the backend for real; alert delivery to the real on-call channel; confirm the first retention dry-run count before any live run.
**Decisions to settle**: D14–D16 gate go-live, not planning.

### Phase 83: Autonomous Security Response

**Goal**: Security findings turn into containment on their own when it is undoable — block a malicious IP, quarantine a malicious file, restart a failed service — and into one-click approval cards when it is destructive, with each action verified, undoable from the Autonomous Ops screen where an inverse exists, and never repeated or amplified.
**Depends on**: Phase 81 (gate, action registry, ledger, Activity screen). Independent of Phases 82 and 85 — can run in parallel with them; agent-verb groundwork (the Rust/Python parity matrix) can start during Phase 81.
**Requirements**: RESP-01, RESP-02, RESP-03, RESP-04, RESP-05, RESP-06, RESP-07, RESP-08, RESP-09, RESP-10, RESP-11, ACTV-02
**Success Criteria** (what must be TRUE):
  1. A malicious scan verdict, agent vulnerability or file-integrity change becomes a playbook action through the gate, replacing the legacy remediation loop. At Undoable-auto, a malicious single IP address confirmed by two independent signals is blocked for 24 h by default (the agent removes the block at expiry even if it has lost contact with the platform), a malicious file is quarantined (moved, never deleted), and a failed service is restarted within its restart budget; by default a single signal becomes a suggestion, and an IP range or an exhausted restart budget needs approval.
  2. Kill process and isolate host appear as approval cards, one card per incident rather than one per alert; isolation always keeps the agent's management connection open and reverts automatically after a set time unless an operator confirms it.
  3. Each action is verified by its own check (the firewall rule exists, the file is in quarantine), so a successful block is never reverted; the same finding does not create a new action every cycle, and an action an operator undid is not redone for 24 hours.
  4. From the Autonomous Ops screen an operator can approve or deny pending actions and undo done actions that have an inverse (remove a block, restore a quarantined file) with one click.
  5. The Rust agent (with Python agent parity where that agent stays supported) supports restart service, quarantine and restore file, isolate and restore host, and reboot host; each is gated by the tenant's agent-capability ticks, and rules that need one stay dormant until the agent reports support. The swarm "propagate antibody" and SOAR block/isolate paths are fenced so they cannot dispatch automatic containment.

**Plans**: 20/20 plans complete in 10 waves

Plans:
**Wave 1**
- [x] 83-01-PLAN.md — Tracer: one two-source IP becomes one verified, undoable block (backend, agent contract file)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 83-02-PLAN.md — The real Rust agent speaks the contract: time-limited block, claims, verify, support report
- [x] 83-03-PLAN.md — All server copy and row fields (canUndo, undoHint, suggestion, blockedUntil)

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 83-04-PLAN.md — Agent block complete: offline expiry, reboot safety, refusals, range blocks
- [x] 83-05-PLAN.md — Origins, two-source rule, feed key, decision memory, per-host cap, migration 028
- [x] 83-06-PLAN.md — Fences: swarm, SOAR, worker tasks, automatic XDR, delivery rule for new commands

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 83-07-PLAN.md — Response settings API: two-source switch, block length, watched services, bulk apply
- [x] 83-08-PLAN.md — Dormancy in the sweep, gate and approval; honest breaker; range needs approval
- [x] 83-09-PLAN.md — Agent quarantine and restore, kill bound to an executable

**Wave 5** *(blocked on Wave 4 completion)*
- [x] 83-10-PLAN.md — Undo on Done rows and suggestions in volume
- [x] 83-11-PLAN.md — Incidents, quarantine decisions, protected paths, select_playbook, isolation proposal
- [x] 83-12-PLAN.md — Agent isolation with management carve-out, self-test and automatic revert

**Wave 6** *(blocked on Wave 5 completion)*
- [x] 83-13-PLAN.md — Response settings panel and dialogs
- [x] 83-14-PLAN.md — Agent service watching, restart and reboot
- [x] 83-15-PLAN.md — Vulnerability and file-change suggestions, one row per host
- [x] 83-16-PLAN.md — Kill cards for running files, bounded retry, failed undo stays visible

**Wave 7** *(blocked on Wave 6 completion)*
- [x] 83-17-PLAN.md — Restart budget and the watched list in the heartbeat reply

**Wave 8** *(blocked on Wave 7 completion)*
- [x] 83-18-PLAN.md — Incident cards route, confirm isolation, automatic revert noticed

**Wave 9** *(blocked on Wave 8 completion)*
- [x] 83-19-PLAN.md — Needs your decision section and incident cards

**Wave 10** *(blocked on Wave 9 completion)*
- [x] 83-20-PLAN.md — Agent 2.1.16, all gates together, the user's live list

**UI hint**: yes
**Research**: Needed (`/gsd-plan-phase --research-phase 83`) — cross-platform agent semantics (idempotent firewall rules, refcounted undo, `netsh` vs Defender heuristics, native APIs, isolate with management carve-out, per-action verify); re-run the `db.instructions` grep before fencing swarm and SOAR.
**Live-only verification** (operator steps): firewall block and unblock round-trip on real Linux and Windows endpoints (EILT0197 with Defender); a block expiring while its agent is offline; quarantine and restore; isolate with the management connection kept open and the automatic revert; service restart; publish and roll out the new agent.
**Decisions to settle before planning**: D5–D8 (see `.planning/research/SUMMARY.md`).

### Phase 84: Staged Patch Rollouts

**Goal**: Operators run patch rollouts in rings, each stage gated by a soak period and a real health check that halts the rollout — and reverts where the operating system supports it — on failure, inside the maintenance window, with one approval per stage for anything risky.
**Depends on**: Phase 81 (gate, ledger, stop freezes rollouts) and Phase 83 (undo, dedupe and suppression conventions, blast-radius handling, and the reboot-host agent action from RESP-10). Independent of Phases 82 and 85.
**Requirements**: PTCH-01, PTCH-02, PTCH-03, PTCH-04, PTCH-05, PTCH-06, PTCH-07
**Success Criteria** (what must be TRUE):
  1. An operator can define rollout rings per tenant (a canary ring, then larger stages); a rollout moves to the next ring only after its soak period has passed and its health gate is green.
  2. The health gate combines the install result, the post-install inventory, a fresh heartbeat after reboot and key services, and missing data halts the rollout; a stage also halts when more than a set share of its hosts fail, once a minimum sample size is reached.
  3. A failed stage halts the rollout and reverts the patch where the operating system supports it, and the screen says "halts on failure; reverts where supported" without ever promising an unqualified revert.
  4. A rollout installs or advances only inside the maintenance window recorded in Change Management; outside the window nothing is installed.
  5. Installs run on their own only in the canary ring and only for patch classes marked reversible; every other install and every reboot waits for one approval per stage. The platform's own host is never patched by a rollout, a host belongs to at most one active rollout, and patch instructions expire.

**Plans**: 29/29 plans complete in 7 waves

Plans:
**Wave 1**
- [x] 84-01-PLAN.md — Tracer: one canary host installs one reversible patch on its own through the gate inside the window, and the rollout completes
- [x] 84-02-PLAN.md — Contracts: agent rollout tokens and params, all server copy, UI copy and types, copy gate over whole directories

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 84-03-PLAN.md — Approval lines, window-deferred dispatcher, line approve and deny, a deny or expiry halts the ring, canary rate cap
- [x] 84-04-PLAN.md — Instructions expire at delivery, the reconciler leaves rollout rows alone, the old staged-deployment revert is fenced
- [x] 84-05-PLAN.md — Maintenance windows in the tenant's time zone (past midnight, DST, weekdays), typed routes, Change Management read route
- [x] 84-06-PLAN.md — Rings from agent groups, full preflight, left-out hosts with reasons, one active rollout per host
- [x] 84-07-PLAN.md — Rust agent: reversibility check before install, per-job revert state, two tokens
- [x] 84-22-PLAN.md — Controller loop under a renewed lock, index guard, restart resume, migration 031

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 84-08-PLAN.md — Restart lines, new-boot check, full health gate, failure share, hosts not reached
- [x] 84-09-PLAN.md — `/api/patch-rollouts` routes and server-built views under the Patching catalogue entry
- [x] 84-10-PLAN.md — Approval card list and line approve and deny on the Autonomous Ops response router
- [x] 84-11-PLAN.md — Rust agent: `service_state` in the heartbeat, plus its token
- [x] 84-12-PLAN.md — Settings windows rework, Change Management windows, ring chip on Agent Groups

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 84-13-PLAN.md — A halted ring is reverted where supported (undo, also during a stop); the breaker ignores reverts
- [x] 84-14-PLAN.md — Rollouts tab, window strip and rollout card on the Patching screen
- [x] 84-15-PLAN.md — Rollout approval card in Needs your decision

**Wave 5** *(blocked on Wave 4 completion)*
- [x] 84-16-PLAN.md — Resume and Cancel, completion with hosts not reached (7-day close), Activity row copy
- [x] 84-17-PLAN.md — Start dialog with preflight, Rollout rings card

**Wave 6** *(blocked on Wave 5 completion)*
- [x] 84-18-PLAN.md — Ring detail, Resume and Cancel dialogs
- [x] 84-19-PLAN.md — Draft a rollout link and Roll out in rings button
- [x] 84-20-PLAN.md — Shadow mode runs rollouts as simulations; a stop freezes rollouts without false halts

**Wave 7** *(blocked on Wave 6 completion)*
- [x] 84-21-PLAN.md — Agent 2.1.17, all gates together, the validation map, the user's live list

**Gap closure (verification gaps_found 3/5):** 7 plans in 4 waves
- [x] 84-23-PLAN.md — Held or Suggest-level canary rows become Install lines; refusals retry; breaker ignores not-delivered (CR-01, CR-02, WR-01)
- [x] 84-24-PLAN.md — Manual job rollback refuses rollout jobs with 409 (WR-10)
- [x] 84-25-PLAN.md — Agent: a not-installed or masked service reads `absent`; the gate drops it only if it was absent before the change, and fails a service the change removed (CR-03) *(after 84-27)*
- [x] 84-26-PLAN.md — Agent: apt downgrade `--no-remove`, no reinstall on revert, strict require_reversible, durable job records (CR-04, WR-13..15)
- [x] 84-27-PLAN.md — In-flight work has a bounded end; denied hosts not shown installed; stuck dispatching rows and jobs recovered (WR-02..04, WR-06) *(after 84-23)*
- [x] 84-28-PLAN.md — Cancel a running rollout per D-16: stop new work, keep every patch (no revert), release claims once in-flight work settles; no Resume mid-cancel (WR-03) *(after 84-27)*
- [x] 84-29-PLAN.md — All gates together; VALIDATION, SECURITY (T-84-65..78) and review dispositions *(after all)*

**UI hint**: yes
**Research**: Needed (`/gsd-plan-phase --research-phase 84`) — per-OS patch reversibility matrix; health-gate signals; confirm the existing patch-revert path dispatches real agent work (OS patching was fake end to end until 2026-10-12).
**Live-only verification** (operator steps): a real canary install plus reboot on a disposable host; revert on a supported OS; the post-reboot heartbeat feeding the gate; maintenance-window enforcement; the per-stage reboot approval click.
**Decisions to settle before planning**: D10–D13 (see `.planning/research/SUMMARY.md`).

### Phase 85: First-Line Service Desk

**Goal**: New first-line tickets get a cited answer drafted from the tenant's knowledge base — posted, drafted or escalated by fixed rules — and anything the system is unsure of, anything sensitive, and everything while the language model is unavailable goes to a person.
**Depends on**: Phase 81 (level, gate, ledger, stop). Independent of Phases 82–84 — can run in parallel with them. Live validation needs Ollama installed on the server (operator step).
**Requirements**: DESK-01, DESK-02, DESK-03, DESK-04, DESK-05, DESK-06, DESK-07
**Success Criteria** (what must be TRUE):
  1. A new ticket that the knowledge base covers gets an answer with cited articles: at Undoable-auto a qualifying answer is posted marked "AI-assisted", at Suggest it is an internal draft, and the ticket closes only when the requester confirms.
  2. A ticket is escalated to a person, never answered, when no article matches well enough, when the requester asks for a person, or when it concerns security, billing, legal or account access; the model's own confidence is never used to decide. The operator sees a knowledge-gap list of the questions escalated because no article covered them.
  3. Ticket text can never trigger an action; links and HTML are stripped before the model sees it, and a prompt-injection test set passes.
  4. When the language model is unavailable or only the mock provider is active, the ticket is escalated and no placeholder answer is ever posted.
  5. Answers are generated asynchronously, one at a time, with timeouts sized for the CPU-only server, and the real response time is measured on it; a starter set of general IT help-desk articles (password reset, VPN, printer, agent tray app) can be seeded into a tenant's knowledge base.

**Plans**: 28/29 plans executed: 23 in 6 waves, plus a gap round of 6 plans in 5 waves (not executed)

Plans:
**Wave 1**
- [x] 85-02-PLAN.md — Contracts: every server sentence, the four starter IT articles, the frozen tray contract, UI copy and types, copy gate over the new directories
- [x] 85-03-PLAN.md — Autonomous Ops layer: the gate seam for a ticket action (ticket_answer and ticket_withdraw for the service desk only, the ticket-ownership step, the row's desk field, Activity words), a separate desk rate pool, desk rows outside the Phase 81 breaker, the hand-off row writer and the audited desk-field updater

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 85-01-PLAN.md — Tracer: a portal ticket gets one cited answer through the gate (post at Undoable-auto with Post answers, staff draft by default) and the requester reads it back

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 85-04-PLAN.md — Gate edges and the D-03 outcome matrix: desk hourly pool to drafts, drafts never expire, approve/deny closed, undo handler registry, agent queue and reconciler fenced, Activity desk rows
- [x] 85-05-PLAN.md — Sanitiser and prompt hardened; fixed rules before the model (sensitive, fulfilment, critical, ask-for-a-person, tenant words); English heuristic
- [x] 85-06-PLAN.md — Retrieval cut-off re-pinned on the real starters; strict output checks
- [x] 85-07-PLAN.md — Loopback model client (DESK-04 guard, busy, timeout), CPU-sized timeouts, structural fence around the desk
- [x] 85-08-PLAN.md — Comment visibility flag and notification privacy (recipient filter, no staff-only previews)
- [x] 85-09-PLAN.md — Who raised it: both agent routes stamp raised_via; intake level, stop and screen checks
- [x] 85-10-PLAN.md — Tray: Raise a Ticket on the new route, My tickets window, answer pop-up, agent embeds the second script
- [x] 85-11-PLAN.md — Desk settings: switch, words, restore, status line; routes mounted and required
- [x] 85-12-PLAN.md — Hand-off through the tenant's queue rules, staff-only reason, requester notice, gap rows

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 85-13-PLAN.md — Full pipeline (every stage, every hand-off, stop and moved-ticket edges) and the prompt-injection set
- [x] 85-14-PLAN.md — Portal: send, edit, discard drafts; This fixed it and I still need help; cited articles; working-day return date
- [x] 85-15-PLAN.md — Knowledge Base back end: Help desk mark and edit, idempotent starter copy, grouped knowledge-gap list
- [x] 85-16-PLAN.md — Autonomous Ops screen: Service desk settings card and desk Activity rows with Undo

**Wave 5** *(blocked on Wave 4 completion)*
- [x] 85-17-PLAN.md — Worker under a renewed lock, 10-minute queue limit and caps, three-working-day return, migration 032, startup
- [x] 85-18-PLAN.md — Undo a posted answer (also during a stop) and the desk-only breaker
- [x] 85-19-PLAN.md — Tray routes: create, My tickets list, confirm, help, cited article; enforced projection and contract tests
- [x] 85-20-PLAN.md — Ticket screen: draft panel, requester panel, cited articles, Reply to requester, Waiting on customer
- [x] 85-21-PLAN.md — Knowledge Base screen: Help desk switch, article dialog, Add starter IT articles, Knowledge gaps tab
- [x] 85-22-PLAN.md — Operator script: measure the real CPU speed, run the eval sets live, calibrate on a real knowledge base

**Wave 6** *(blocked on Wave 5 completion)*
- [x] 85-23-PLAN.md — Agent 2.1.18, all gates together, the validation map, the user's live list

**Gap closure (verification gaps_found 6/7):** 6 plans in 5 waves
- [x] 85-24-PLAN.md — Output checks run on the folded answer (hidden, full-width, ideographic-dot and look-alike characters) and the folded text is what is posted or drafted; the loopback model client ignores proxy settings (CR-101, WR-101)
- [x] 85-25-PLAN.md — The reporter's own ticket JSON on every ticket route carries only what the requester may read, with no drafts and no desk fields; T-85-77 becomes a mitigation (CR-401 server half)
- [x] 85-26-PLAN.md — The ticket screen's comment list fails closed for the reporter, driven by the same case table as the server (CR-401 UI half) *(after 85-24, 85-25)*
- [x] 85-27-PLAN.md — A failure after a visible desk answer never produces a contradicting hand-off or a stuck ledger row; send_draft moves the status first (WR-102, WR-103) *(after 85-26)*
- [x] 85-28-PLAN.md — Staff-only comment notices are hidden from the reporter in the feed and on the socket; one recipient filter for list, mark-read, read-all and delete (WR-201, WR-202) *(after 85-27)*
- [ ] 85-29-PLAN.md — A gap article must be a Help desk article (422); stable TTL, migration and --sets tests; the whole Phase 85 gate, VALIDATION and review dispositions (WR-203, WR-301..303) *(after all)*

**UI hint**: yes
**Research**: Needed (`/gsd-plan-phase --research-phase 85`) — measure `llama3.2:3b` CPU tokens per second once Ollama exists; calibrate the retrieval threshold; build prompt-injection and escalation eval sets.
**Live-only verification** (operator steps): install Ollama and pull `llama3.2:3b`; measure real CPU response time; calibrate the retrieval threshold on a real knowledge base; a real ticket round trip including requester confirmation.
**Decisions to settle before planning**: D18 (see `.planning/research/SUMMARY.md`).

### Phase 86: Activity Reporting, Hardening & Live Validation

**Goal**: Operators get the daily digest, per-rule statistics, export and an honest time-saved estimate, and the whole of Autonomous Ops is proven safe end to end — stop drills, two-tenant isolation and a live-only checklist — before any tenant is lifted out of shadow mode.
**Depends on**: Phases 82, 83, 84 and 85 (the digest, statistics, export and drills cover every automatic actor).
**Requirements**: ACTV-04, ACTV-05, ACTV-06, ACTV-07
**Success Criteria** (what must be TRUE):
  1. Each tenant receives one daily digest of what ran, what was undone and what is waiting for approval.
  2. An operator can see per-rule statistics (how often each rule fired and was approved, denied or undone) and export the activity log as CSV or PDF.
  3. The screen shows an estimate of operator time saved, labelled as an estimate.
  4. A live stop drill across every actor shows that the platform stop and a tenant stop halt new security decisions, hold back queued instructions, freeze pending approvals and patch rollouts, and pause AI ticket replies (this re-verifies GATE-06 against the actors built in Phases 82–85).
  5. A two-tenant contract test per automatic loop (security response, patch rollouts, service desk, retention) shows nothing crosses tenants, and the live-only checklist (firewall round-trip, reboot gate, watchdog stop/start, alert delivery) is walked and recorded before any tenant is lifted out of shadow mode.

**Plans**: TBD
**UI hint**: yes
**Research**: None — UI, tests and copy checks (standard patterns).
**Live-only verification** (operator steps): kill-switch drills on the live server (queued instructions, pending approvals, rollouts, AI ticket replies); the observe-first soak and per-tenant lift out of shadow mode; digest delivery; CSV and PDF export download.
**Decisions to settle**: D2 (who lifts shadow mode, and when) and D19 gate go-live (see `.planning/research/SUMMARY.md`).

### Phase 87: Partner and Reseller Channel

**Goal**: The platform can sell through partners the way a vendor appoints dealers: a Super Admin appoints partner organizations and gives each a pool of agent seats, a partner creates and manages its own customer organizations and assigns seats to each from its pool, a partner admin sees only that partner's customers, and usage rolls up per partner.
**Depends on**: Nothing in v4.3. It builds on the per-tenant seat licence (C2), the enrollment controls (C4) and the Phase 77 tenant roles, all complete.
**Requirements**: PART-01, PART-02, PART-03, PART-04, PART-05, PART-06, PART-07, PART-08
**Success Criteria** (what must be TRUE):
  1. A Super Admin appoints a partner with a seat pool (for example 1,000 seats), an expiry date and a screen ceiling from a Partners screen, sees every partner's pool used and free, and can suspend a partner, which locks its users out while its customers keep running.
  2. A partner admin creates a customer organization with seats from the pool and invites its first admin, who then runs it like any direct customer; screens can be ticked for that customer only within the partner's ceiling.
  3. Seats handed out never exceed the pool, even under concurrent requests; a customer's seats can be lowered only to what it uses; a pool cannot shrink below what is handed out; after a pool expires no customer can be created and no seat handed out.
  4. Partner admins and partner viewers reach only their own customers' seats and usage through every route, and a two-partner test shows that no partner sees another partner's customers or any customer's security data.
  5. A Super Admin can move a customer to another partner or back to direct, with its seats returned and the move audited; organizations that existed before this phase stay direct; each partner has a per-customer usage list with a CSV export.

**Plans**: 15/15 plans complete

Plans:
**Wave 1**
- [x] 87-01-PLAN.md — Stored-shape decision and tracer (appoint, customer from pool, overview)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 87-15-PLAN.md — Registration drift: frontend unions, sidebar icons and pinned counts (wave 2, before every expansion plan)

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 87-02-PLAN.md — Partner roles fenced: own permissions only, MFA for admins, partner orgs only
- [x] 87-03-PLAN.md — Pool completed: allotment floor, pool floor, moves, reconcile, migration 029
- [x] 87-04-PLAN.md — Suspension chokepoint in the token verifier, login and refresh
- [x] 87-05-PLAN.md — Partner allowlist middleware and route-walk proof
- [x] 87-06-PLAN.md — Invites: seven-day single-use links and the public status route
- [x] 87-07-PLAN.md — Frontend ground: partner client, portal role gate, suspended exit, chips, screen picker

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 87-08-PLAN.md — Super Admin partner management: appoint, edit, suspend, moves
- [x] 87-09-PLAN.md — Partner portal API: customers, seats, screens, team, isolated usage
- [x] 87-10-PLAN.md — Licence writers pool-aware, pool expiry holds new agents, MSSP filters
- [x] 87-11-PLAN.md — Partners screen and its dialogs
- [x] 87-12-PLAN.md — Partner portal page, modals, team and CSV
- [x] 87-13-PLAN.md — Accept invite page

**Wave 5** *(blocked on Wave 4 completion)*
- [x] 87-14-PLAN.md — Shell wiring and phase gates

**UI hint**: yes

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 75. Permission Resolver & Single Source of Truth | 5/5 | In Progress | - |
| 76. Catalogue Manifest & Backend Route Enforcement | 15/15 | In Progress | - |
| 77. Fail-Closed Sidebar, View Gate & Role Visibility | 13/13 | Complete    | 2026-10-21 |
| 78. Organization & Endpoint Cost API | 0/TBD | Not started | - |
| 79. License Cost & Per-Endpoint Allocation | 0/TBD | Not started | - |
| 80. Costs Tab in the ITAM Console | 0/TBD | Not started | - |
| 81. Autonomy Gate, Stop Switch & Activity Ledger | 18/18 | Complete    | 2026-11-07 |
| 82. Platform Self-Healing & Scheduled Retention | 17/17 | Complete    | 2026-11-07 |
| 83. Autonomous Security Response | 20/20 | Complete    | 2026-11-07 |
| 84. Staged Patch Rollouts | 29/29 | Complete    | 2026-11-07 |
| 85. First-Line Service Desk | 28/29 | In Progress | - |
| 86. Activity Reporting, Hardening & Live Validation | 0/TBD | Not started | - |
| 87. Partner and Reseller Channel | 15/15 | Complete    | 2026-11-07 |
