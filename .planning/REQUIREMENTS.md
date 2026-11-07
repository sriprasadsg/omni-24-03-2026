# Requirements: Autonomous Ops (v4.3), plus paused v4.2

**Defined:** 2026-10-25
**Core Value:** Any tenant can see exactly which compliance controls pass or fail across their endpoints — with evidence proving it — at any moment.
**Goal (v4.3):** The platform handles routine security response, patching, its own health and first-line support on its own within per-tenant limits, and asks a person only to approve destructive actions.
**Naming rule:** the feature is "Autonomous Ops" — never "ASI", never "Autopilot" (Windows Autopilot already exists).
**Locked decisions:** per-tenant level Off / Suggest / Undoable-auto (default Undoable-auto); undoable actions (block IP, quarantine file, restart a service) run on their own, destructive ones (isolate host, kill process, patch reboot) wait for one approval click; fixed, tested rules choose every action and the LLM only summarises and suggests. Research: `.planning/research/SUMMARY.md`.

**v4.2 is paused, not complete** — its open requirements (ACC-03, COST-01..08) are kept unchanged in the second half of this file and resume after v4.3.

## v1 Requirements (v4.3)

### 1. Autonomy Policy & Safety Core

- [ ] **GATE-01**: Each tenant has an autonomy level (Off / Suggest / Undoable-auto) stored in the database; new tenants default to Undoable-auto and every existing tenant is given an explicit stored level by migration.
- [ ] **GATE-02**: Only tenants whose Autonomous Ops screen a Super Admin has ticked are eligible for autonomous actions, and a tenant whose level cannot be read is treated as Suggest (fail closed).
- [x] **GATE-03**: Every autonomous action passes one decision function that applies, in order: platform stop, tenant eligibility, tenant stop, level, action class, protected targets, blast-radius cap, cooldown and suppression — and only that gate writes autonomous agent instructions (a structural test fails on any other writer).
- [x] **GATE-04**: Action classes come from a code-owned registry (auto or approval, plus the undo action): block IP, quarantine file and restart service are auto; isolate host, kill process and patch reboot need approval; a playbook's YAML may raise a class but never lower it.
- [ ] **GATE-05**: No autonomous path dispatches an LLM-written script or an LLM-chosen action: the legacy `run_cycle` / `generate_plan` / `execute_plan` path is removed, the 0.90 confidence auto-approve bypass no longer applies to autonomous actions, and a test proves only registry-listed playbook actions reach the agent queue.
- [ ] **GATE-06**: A Super Admin can flip a platform-wide stop and a tenant admin a per-tenant stop; a stop takes effect without a restart, halts new decisions, holds back autonomous instructions already queued at agent delivery, and freezes pending approvals and rollouts.
- [x] **GATE-07**: Every autonomous decision writes an intent record before dispatch (dispatch is refused if the record cannot be written), every state change is mirrored into the hash-chained audit ledger, and decision records are kept longer than generic retention.
- [x] **GATE-08**: The platform host, its own IP addresses and the management network can never be blocked, isolated or patched autonomously, and a per-decision cap limits how many hosts one decision can touch.
- [x] **GATE-09**: The operator can run in shadow mode (on by default at deployment), in which the gate records what it would have done without dispatching anything.
- [x] **GATE-10**: An approval dispatches exactly once even if clicked twice (atomic, single-use), and an approval left pending past its expiry counts as denied.
- [x] **GATE-11**: Autonomous sweeps run one at a time across the deployment (lock with renewal), set the tenant explicitly on every write and reset tenant context per tenant; a two-tenant test proves no autonomous action or record crosses tenants.
- [ ] **GATE-12**: Agent online/offline status refreshes every 5 minutes as documented, pinned by a test, and the offline notification names the agents that actually went offline, so health checks read current data. (Corrected 2026-10-25: the loop already polls every 30 s; the earlier "3600 s sleep" premise was a misread.)
- [ ] **GATE-13**: Changing a tenant's level, approving or undoing actions, and flipping the platform stop are separate permissions; a Super Admin sets the highest level a tenant may use and tenant admins can choose only at or below it.
- [x] **GATE-14**: When several autonomous actions in a row for a tenant are undone or fail, that tenant drops to Suggest automatically and the on-call channel is told (circuit breaker).

### 2. Security Response

- [x] **RESP-01**: A security sweep turns native findings (malicious scan verdict, agent vulnerability, file-integrity change) into playbook actions through the gate, replacing the legacy remediation loop.
- [ ] **RESP-02**: At Undoable-auto a malicious single IP address is blocked automatically for a set time (default 24 h); the agent removes the block at expiry even if it has lost contact with the platform, an operator can undo it from the Activity view, and blocking a range needs approval.
- [ ] **RESP-03**: At Undoable-auto a malicious file is quarantined automatically (moved, never deleted) and an operator can restore it with one click.
- [ ] **RESP-04**: A failed service on an endpoint is restarted automatically within a restart budget; once the budget is used up further restarts need approval.
- [x] **RESP-05**: Kill process and isolate host appear as approval cards; isolation always keeps the agent's management connection open and reverts automatically after a set time unless an operator confirms it.
- [ ] **RESP-06**: Each action is verified by its own check (e.g. the firewall rule exists, the file is in quarantine), not by re-reading the original finding, so a successful block is never rolled back.
- [ ] **RESP-07**: The same finding does not create a new action every cycle (dedupe per tenant, finding and action), and an action an operator undid is not redone for 24 hours.
- [ ] **RESP-08**: By default an action runs on its own only when two independent signals agree (e.g. scan verdict and threat intel); a single signal becomes a suggestion (corroboration rule). A tenant admin can turn the rule off for their tenant and a Super Admin for any or all tenants.
- [x] **RESP-09**: A burst of related alerts on one host becomes one approval card per incident, not one per alert (incident grouping).
- [ ] **RESP-10**: The Rust agent (with Python agent parity where that agent stays supported) gains restart service, quarantine and restore file, isolate and restore host, and reboot host; each new action is gated by the tenant's agent-capability ticks, and rules that need it stay dormant until the agent reports support.
- [x] **RESP-11**: Existing fan-out paths that bypass the gate (swarm "propagate antibody", SOAR block/isolate plugins) are fenced so they cannot dispatch autonomous containment.

### 3. Staged Patching

- [ ] **PTCH-01**: An operator can define rollout rings per tenant (a canary ring, then larger stages); a rollout moves to the next ring only after a soak period and a passing health gate.
- [ ] **PTCH-02**: The health gate combines the install result, the post-install inventory, a fresh heartbeat after reboot and key services; missing data halts the rollout.
- [ ] **PTCH-03**: A stage also halts when more than a set share of its hosts fail, with a minimum sample size (failure-rate gate).
- [ ] **PTCH-04**: A failed stage halts the rollout and reverts the patch where the operating system supports it; the UI says "halts on failure; reverts where supported" and never promises an unqualified rollback.
- [ ] **PTCH-05**: Rollouts run only inside the maintenance window recorded in Change Management.
- [ ] **PTCH-06**: Installs run on their own only in the canary ring and only for patch classes marked reversible; other installs and every reboot need one approval per stage.
- [ ] **PTCH-07**: The platform's own host is never patched by a rollout, a host is in at most one active rollout, and patch instructions expire.

### 4. Platform Self-Healing

- [ ] **HEAL-01**: A watchdog running outside the backend (systemd timer) checks backend readiness, MongoDB and Ollama (only where Ollama is expected) every minute and restarts a failed service from a fixed allowlist, MongoDB before the backend.
- [ ] **HEAL-02**: Restarts follow a budget with backoff; when the budget is used up the watchdog stops restarting and pages once.
- [ ] **HEAL-03**: The operator is warned 30, 14, 7 and 1 days before a certificate expires and when a disk passes 80, 90 and 95 percent; the platform never renews certificates or deletes files on its own.
- [ ] **HEAL-04**: The operator is warned days ahead when a disk will fill at its current growth rate (disk-growth forecast).
- [ ] **HEAL-05**: On-call alerts go to a configured webhook or PagerDuty with deduplication; the operator can send a test alert, sees a banner when no working channel is configured, and is alerted when the watchdog itself stops reporting.
- [ ] **HEAL-06**: Data retention runs on a schedule per tenant in bounded batches, never touches audit logs, the audit ledger or decision records, and its first run is a dry-run count the operator confirms.
- [ ] **HEAL-07**: Watchdog events (checks, restarts, warnings, pages) appear in the Activity view at platform scope.
- [ ] **HEAL-08**: The repo ships the watchdog unit files, service drop-ins and an install checklist; installing them on the live server stays the operator's step.

### 5. Service Desk

- [ ] **DESK-01**: A new first-line ticket gets an answer drafted from the tenant's knowledge base with cited articles; at Undoable-auto a qualifying answer is posted marked "AI-assisted", at Suggest it is an internal draft, and the ticket closes only when the requester confirms.
- [ ] **DESK-02**: A ticket is escalated to a person, never answered, when no article matches well enough, when the requester asks for a person, or when it concerns security, billing, legal or account access; the model's own confidence is never used to decide.
- [ ] **DESK-03**: Ticket text can never trigger an action; links and HTML are stripped before the model sees it, and a prompt-injection test set passes.
- [ ] **DESK-04**: When the language model is unavailable or only the mock provider is active, the ticket is escalated; no placeholder answer is ever posted.
- [ ] **DESK-05**: Answers are generated asynchronously one at a time with timeouts sized for the CPU-only server, and the real response time is measured on it.
- [ ] **DESK-06**: The operator sees the questions that had to be escalated because no article covered them (knowledge-gap list).
- [ ] **DESK-07**: A starter set of general IT help-desk articles (password reset, VPN, printer, agent tray app) is available to seed a tenant's knowledge base.

### 6. Activity View

- [x] **ACTV-01**: An Autonomous Ops screen (catalogue entry, tenant switch and permissions) lists actions as Pending, Done, Undone, Failed, Refused and Suggested, each with what ran, why (the rule), the target and the result.
- [x] **ACTV-02**: An operator can approve or deny pending actions and undo done actions that have an inverse, from the same screen.
- [ ] **ACTV-03**: In shadow mode the screen shows "would have done" entries clearly labelled as a simulation.
- [ ] **ACTV-04**: Each tenant gets one daily digest: what ran, what was undone, and what is waiting for approval.
- [ ] **ACTV-05**: The operator can see per-rule statistics: how often each rule fired and was approved, denied or undone.
- [ ] **ACTV-06**: The operator can export the activity log as CSV or PDF.
- [ ] **ACTV-07**: The screen shows an estimate of operator time saved, labelled as an estimate.
- [ ] **ACTV-08**: A copy check fails the build if Autonomous Ops screens or docs use "ASI", "Autopilot", "fully autonomous" or an unqualified "rollback".

### 7. Partner Channel

- [ ] **PART-01**: A Super Admin appoints a partner organization (its own users, login, MFA and audit trail, no endpoints and no seats of its own) from a Partners screen, sets its seat pool, pool expiry and screen ceiling, sees every partner's pool used and free, and can suspend or reinstate it; a suspended partner's users cannot sign in or move seats, and its customers keep running.
- [ ] **PART-02**: A partner admin creates a customer organization, assigns it seats from the partner's pool and invites the customer's first admin by email, who then runs the organization with the same rights as the admin of a directly created organization.
- [ ] **PART-03**: Seats handed out never exceed the partner's pool, enforced atomically under concurrent requests; a partner can lower a customer's seats only down to what that customer uses, and a Super Admin cannot shrink a pool below what is handed out.
- [ ] **PART-04**: After a pool's expiry date the partner can neither create customers nor hand out seats, and its customers' licences follow the existing expiry rule (new agents held, running agents keep working).
- [ ] **PART-05**: Partner admins and partner viewers reach only their own partner's customers, and only seats and usage (name, seats assigned and used, agents online and total, licence expiry), through every route; partner roles never gain a tenant or platform permission, and a partner viewer cannot change anything.
- [ ] **PART-06**: A partner ticks screens for each customer only within the screen ceiling the Super Admin set for that partner; the server refuses any screen outside it.
- [ ] **PART-07**: Only a Super Admin moves a customer to another partner or back to a direct customer; its seats return to the old partner's pool and the move is recorded in the audit ledger; every organization that existed before this phase stays a direct customer.
- [ ] **PART-08**: A partner sees a usage roll-up: pool size, seats handed out and free, and per customer the seats assigned and used, agents online and licence expiry, with a CSV export; no invoicing.

## v2 Requirements (v4.3 deferred)

- **AOPS-F1**: Per-tenant custom autonomy rules authored in the UI.
- **AOPS-F2**: A full on-call product (escalation tiers, acknowledge, repeat paging) instead of webhook/PagerDuty delivery.
- **AOPS-F3**: Mapping autonomous actions to compliance-control evidence.
- **AOPS-F4**: Known-bad patch list shared across tenants.

## Out of Scope (v4.3)

| Feature | Reason |
|---------|--------|
| "Artificial super intelligence" or any claim of it | Does not exist; the feature is rule-based automation and must never be marketed otherwise |
| LLM choosing an action, target or parameters | Locked decision 3: fixed, tested rules decide; the LLM only summarises and suggests |
| Auto-approval from a confidence score | An approval-required action must always wait for a person |
| Rebooting endpoints without approval | Reboots are destructive per the locked split |
| Deleting files to free disk space | Irreversible; disk issues are warned and paged, not fixed by deletion |
| Automatic certificate renewal | Agents pin the backend certificate; a silent renewal would cut them off |
| Cross-tenant autonomy (one decision acting in several tenants) | Multi-tenant isolation; MSP-wide actions stay manual |
| Editable activity records | Records are evidence; corrections are new records |
| The app installing systemd units, editing sudoers or restarting the live server | Live-server changes stay the operator's step |
| Self-learning rules or a larger/GPU model | Out of reach on the 2 vCPU / 7 GB / no-GPU server and contrary to fixed rules |

---

# Paused milestone v4.2: Catalogue Access Control & Asset Costing

**Defined:** 2026-10-12. **Status:** paused 2026-10-25 for v4.3; resumes afterwards.
**Goal:** Give tenants role-scoped visibility of the left-nav catalogues and a cost view of their assets at organization and endpoint level, both built on systems already shipped (RBAC, ITAM finance). No new permission model; one minimal additive cost field.

## v1 Requirements (v4.2)

### 1. Catalogue Access Control

- [x] **ACC-01**: `/login` and `/me` return a server-evaluated *effective* permission set (role-doc permissions unioned with defaults) from a single resolver, so no role logs in with an empty permission list.
- [x] **ACC-02**: The drifted permission defaults (`rbac_utils.DEFAULT_PERMISSIONS` vs `rbac_service.default_roles`) are collapsed into one source of truth, and the missing `itam_admin/itam_user/itam_viewer` role documents are seeded.
- [ ] **ACC-03**: A single shared catalogue manifest maps each left-nav catalogue to its required permission and its backend route(s); the frontend reads it instead of the divergent `Sidebar.tsx` / `App.tsx viewPermissionMap` tables (the 9 mismatched views reconciled).
- [x] **ACC-04**: Backend route-permission guards are added to the priority unguarded router groups (Assets, ITAM, Settings, financial, identity, security-operations); routers not yet guarded are recorded in a committed gap ledger. Agent-authenticated `/api/agents/*` routes are excluded by design.
- [x] **ACC-05**: A deny-by-default route-parity test fails when an in-scope catalogue's routes are not guarded per the manifest, plus a frontend test that fails on manifest/sidebar drift.
- [x] **ACC-06**: The sidebar fails closed (a catalogue is hidden unless the user holds its permission — no fail-open fallback), a render-time gate guards the active view and every navigation path, and a user with no permitted catalogue sees a clear no-access/empty state with a guaranteed landing view and sign-out (no empty-sidebar lockout).
- [x] **ACC-07**: An admin "what can this role see" view lists which catalogues each role can access.
- [x] **ACC-08**: The client refreshes its effective permissions on a 403 and on window focus, so a role-permission edit takes effect without a full re-login.
- [x] **ACC-09**: Regression tests prove catalogue visibility and route guards hold per role and per tenant, including super-admin / `platform-admin` handling.

### 2. Asset Costing (Organization & Endpoint)

- [ ] **COST-01**: Organization and endpoint cost reuse the *same* per-asset book-value computation as the existing ITAM KPI tile (Phase 72), enforced by a parity test so the tile, report, and cost view cannot disagree.
- [ ] **COST-02**: A read-only org-level cost summary (`/api/itam/costs/summary`, gated by `view:itam`) returns the tenant's total purchase cost and current depreciated book value, with coverage reported and assets lacking cost shown as null (never 0).
- [ ] **COST-03**: Endpoint/asset-level cost (`/api/itam/costs/assets` paginated and `/assets/{id}`) returns per-asset purchase cost and book value; endpoints are assets (joined only via `agents.assetId`).
- [ ] **COST-04**: One optional integer-cents cost field (with a billing basis) is added to the License model, with a minimal UI input, so license spend can be recorded. Consumables and components are deferred.
- [ ] **COST-05**: Org license spend and per-endpoint allocation of *asset-assigned* license seats are reported; user-assigned seats surface as an "unattributed" bucket, with the invariant `sum(endpoint allocations) + unallocated == org license spend`.
- [ ] **COST-06**: Disposed/retired assets are excluded from current book-value totals by default and included in historical purchase totals only behind an explicit filter — the same rule applied in the KPI and the cost view.
- [ ] **COST-07**: Every cost route requires an explicit tenant (a `platform-admin` context with no tenant returns 400), uses no `$lookup` or request-cache, and is covered by a mandatory two-tenant isolation test.
- [ ] **COST-08**: A "Costs" tab in the existing ITAM console (no new sidebar module or permission) shows the org summary and per-asset breakdown with a coverage banner, shared currency formatting, and export through the existing report registry.

## v2 Requirements (v4.2 deferred)

- **COST-F1**: Consumable and component cost fields and rollups.
- **COST-F2**: Display/selectable currency and FX (single implicit currency per tenant in v4.2).
- **COST-F3**: Idle-seat / renewal-cost forecasting and true total-cost-of-ownership.
- **COST-F4**: MSP cross-tenant cost rollup for platform operators.
- **ACC-F1**: ITAM/console *tab-level* permission gating (cost lives under `view:itam` in v4.2).
- **ACC-F2**: Guarding the remaining (non-priority) unguarded routers recorded in the gap ledger.

## Out of Scope (v4.2)

| Feature | Reason |
|---------|--------|
| New permission model / OPA / Casbin / CASL engine | Reuse the existing RBAC (`rbac_utils` / `db.roles`); the milestone aligns and hardens it, not replaces it |
| Guarding all ~188 catalogues this milestone | Priority groups + tracked gap ledger instead (decision D-4) — caps milestone size while closing the real exposure |
| User-RBAC guards on agent-authenticated `/api/agents/*` routes | Those use agent auth, not user permissions; guarding them with user RBAC would break telemetry |
| Persisted cost rollups / caching / background snapshot jobs | Compute at read time; a rollup cache keyed on tenant ContextVar leaks across tenants |
| Multi-currency / FX / chargeback | Single implicit currency per tenant for v4.2 |
| Rolling purchase-order / request money into cost totals | PO/request fields are float dollars vs asset integer cents — mixing units double-counts |
| Backend enforcement of tenant `enabledFeatures` | It is a UI-only gate today; changing that is out of scope (noted in the verification matrix) |

## Traceability

Each requirement maps to exactly one phase. v4.2 rows populated 2026-10-12; v4.3 rows populated 2026-10-25 by the v4.3 roadmap.

| Requirement | Phase | Status |
|-------------|-------|--------|
| ACC-01 | Phase 75 | Complete |
| ACC-02 | Phase 75 | Complete |
| ACC-03 | Phase 76 | Gaps Found |
| ACC-04 | Phase 76 | Complete |
| ACC-05 | Phase 76 | Complete |
| ACC-06 | Phase 77 | Complete |
| ACC-07 | Phase 77 | Complete |
| ACC-08 | Phase 77 | Complete |
| ACC-09 | Phase 77 | Complete |
| COST-01 | Phase 78 | Pending |
| COST-02 | Phase 78 | Pending |
| COST-03 | Phase 78 | Pending |
| COST-04 | Phase 79 | Pending |
| COST-05 | Phase 79 | Pending |
| COST-06 | Phase 78 | Pending |
| COST-07 | Phase 78 | Pending |
| COST-08 | Phase 80 | Pending |
| GATE-01 | Phase 81 | Gaps Found |
| GATE-02 | Phase 81 | Gaps Found |
| GATE-03 | Phase 81 | Complete |
| GATE-04 | Phase 81 | Complete |
| GATE-05 | Phase 81 | Gaps Found |
| GATE-06 | Phase 81 | Gaps Found |
| GATE-07 | Phase 81 | Complete |
| GATE-08 | Phase 81 | Complete |
| GATE-09 | Phase 81 | Complete |
| GATE-10 | Phase 81 | Complete |
| GATE-11 | Phase 81 | Complete |
| GATE-12 | Phase 81 | Gaps Found |
| GATE-13 | Phase 81 | Gaps Found |
| GATE-14 | Phase 81 | Complete |
| ACTV-01 | Phase 81 | Complete |
| ACTV-03 | Phase 81 | Gaps Found |
| ACTV-08 | Phase 81 | Gaps Found |
| HEAL-01 | Phase 82 | Gaps Found |
| HEAL-02 | Phase 82 | Gaps Found |
| HEAL-03 | Phase 82 | Gaps Found |
| HEAL-04 | Phase 82 | Gaps Found |
| HEAL-05 | Phase 82 | Gaps Found |
| HEAL-06 | Phase 82 | Gaps Found |
| HEAL-07 | Phase 82 | Gaps Found |
| HEAL-08 | Phase 82 | Gaps Found |
| RESP-01 | Phase 83 | Complete |
| RESP-02 | Phase 83 | Pending |
| RESP-03 | Phase 83 | Pending |
| RESP-04 | Phase 83 | Pending |
| RESP-05 | Phase 83 | Complete |
| RESP-06 | Phase 83 | Pending |
| RESP-07 | Phase 83 | Pending |
| RESP-08 | Phase 83 | Pending |
| RESP-09 | Phase 83 | Complete |
| RESP-10 | Phase 83 | Pending |
| RESP-11 | Phase 83 | Complete |
| ACTV-02 | Phase 83 | Complete |
| PTCH-01 | Phase 84 | Gaps Found |
| PTCH-02 | Phase 84 | Gaps Found |
| PTCH-03 | Phase 84 | Gaps Found |
| PTCH-04 | Phase 84 | Gaps Found |
| PTCH-05 | Phase 84 | Gaps Found |
| PTCH-06 | Phase 84 | Gaps Found |
| PTCH-07 | Phase 84 | Gaps Found |
| DESK-01 | Phase 85 | Pending |
| DESK-02 | Phase 85 | Pending |
| DESK-03 | Phase 85 | Pending |
| DESK-04 | Phase 85 | Pending |
| DESK-05 | Phase 85 | Pending |
| DESK-06 | Phase 85 | Pending |
| DESK-07 | Phase 85 | Pending |
| ACTV-04 | Phase 86 | Pending |
| ACTV-05 | Phase 86 | Pending |
| ACTV-06 | Phase 86 | Pending |
| ACTV-07 | Phase 86 | Pending |
| PART-01 | Phase 87 | Pending |
| PART-02 | Phase 87 | Pending |
| PART-03 | Phase 87 | Pending |
| PART-04 | Phase 87 | Pending |
| PART-05 | Phase 87 | Pending |
| PART-06 | Phase 87 | Pending |
| PART-07 | Phase 87 | Pending |
| PART-08 | Phase 87 | Pending |

**Coverage:**
- v4.3 v1 requirements: 63 total (GATE 14, RESP 11, PTCH 7, HEAL 8, DESK 7, ACTV 8, PART 8) — 55 mapped to Phases 81–86 by the v4.3 roadmap (2026-10-25); PART-01..08 added 2026-11-02 for Phase 87 from 87-CONTEXT.md D-01..D-16; no orphans, no duplicates
- v4.2 v1 requirements: 17 total (ACC 9, COST 8) — mapped to Phases 75–80, unchanged

**Per phase (v4.3):** Phase 81 = 17 (GATE-01..14, ACTV-01, ACTV-03, ACTV-08) | Phase 82 = 8 (HEAL-01..08) | Phase 83 = 12 (RESP-01..11, ACTV-02) | Phase 84 = 7 (PTCH-01..07) | Phase 85 = 7 (DESK-01..07) | Phase 86 = 4 (ACTV-04..07)

**Per phase (v4.2):** Phase 75 = 2 (ACC-01, ACC-02) | Phase 76 = 3 (ACC-03, ACC-04, ACC-05) | Phase 77 = 4 (ACC-06..09) | Phase 78 = 5 (COST-01, 02, 03, 06, 07) | Phase 79 = 2 (COST-04, COST-05) | Phase 80 = 1 (COST-08)

---
*Requirements defined: 2026-10-12 (v4.2), 2026-10-25 (v4.3)*
*Last updated: 2026-10-25 after the v4.3 roadmap mapped all 55 requirements to Phases 81–86 (v4.2 paused, rows unchanged)*
