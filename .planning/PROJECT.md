# Enterprise OmniAgent — Security & Compliance Portal

## What This Is

An AI-powered, multi-tenant security and compliance management platform. Deployed agents (Python and Rust) run on endpoints, collect security telemetry, and automatically generate evidence records mapped to 30+ compliance framework controls (SOC 2, ISO 27001, PCI-DSS, HIPAA, NIST CSF/800-53, CIS, GDPR, CMMC, FedRAMP, HITRUST, and more). MSP operators and their clients use the platform to monitor compliance posture, upload manual evidence, track remediation of failed controls, and export audit-ready reports.

## Core Value

Any tenant can see exactly which compliance controls pass or fail across their endpoints — with evidence proving it — at any moment.

## Current State

**Latest: v3.4 Native Security Scanning & Autonomous Remediation Agent shipped 2026-08-04** (6 phases 50–55, 25 plans, 19/19 requirements). Native offline scan engine — file/URL/IP/hash verdicts against signed bundled feeds, no live lookup (50); agent-side vulnerability detection — signed CVE feed matching, misconfig + secret detection (51); File Integrity Monitoring — event-driven watcher, signed baseline + restart drift detection (52); autonomous remediation — deterministic YAML playbooks, approval gate, rollback, immutable audit trail (53); operator console + API surfacing the whole stack (54); threat-intel correlation, UEBA-triggered predictive containment, outbound SIEM/OCSF webhook (55). See `.planning/milestones/v3.4-ROADMAP.md` / `v3.4-REQUIREMENTS.md`. **Now building: v4.0 ITAM** (asset-lifecycle management, started 2026-08-04 — see Current Milestone below).

**Phase 63 (Close gap: ITAM-LIC-02/03 RBAC + ITAM-CAT-05 label UI) complete 2026-08-11** — gap closure against `v4.0-MILESTONE-AUDIT.md`, 2 plans, both audit BLOCKERs closed. 63-01: `backend/itam_consumable_endpoints.py` (7 routes) and `backend/itam_component_endpoints.py` (5 routes across 2 router objects) switched from bare `Depends(get_current_user)` to `Depends(_require_itam_admin)`, matching every sibling ITAM router — non-admins now 403 on all 12 routes. 63-02: Phase 58's three offline label routes (QR/barcode/PDF sheet), live since Phase 58 but never called by any frontend code, are now reachable via a new per-row `Label` action + 3-item menu in `components/itam/LifecyclePanel.tsx`, wired through 3 new `apiService.ts` functions and a `triggerLabelDownload` blob helper using the server-supplied filename. Code review: 0 critical, 2 warnings (RBAC test classes assert 403 on only 1-2 of the routes they gate, not every route individually — functionally correct today per direct code inspection, but a thin regression net). Verified 11/11 must-haves — 1 accepted via override: `itam_catalog_endpoints.py` (pre-existing since Phase 56, outside this phase's scope) keeps its own local `_require_itam_admin` copy instead of importing the canonical one; functionally identical (same `manage:assets` check, same 403), tracked as a follow-up in `deferred-items.md` rather than fixed here. Full backend suite 1844 passed/35 skipped/3 pre-existing unrelated fails; full frontend suite 184/184 pass. One item remains human-only: live-browser download/filename confirmation (jsdom can't intercept real downloads, same accepted gap as `exportReport`).

**Phase 62 (Remediation SLA Settings UI) complete 2026-08-10** — gap closure, 1 plan, SLA-03 done. Built the UI consumer for the `GET/PATCH /api/settings/remediation-sla` endpoint that had been live with no UI since v3.2 Phase 44-03 (flagged twice by UI audits as a deliberate, tracked deferral). New unrestricted "Remediation" tab in `SettingsDashboard.tsx` mounting `RemediationSlaSettings.tsx`, a byte-for-byte clone of `EvidenceSettings.tsx` (one declared typography exception for the 2-weight ceiling); two new `apiService.ts` wrappers (`fetchRemediationSlaWindow` soft-fails to a default, `saveRemediationSlaWindow` throws — asymmetric by design). No client-side permission gate on the tab or save button, matching the endpoint's own unrestricted-GET/admin-gated-PATCH posture — a non-admin's 403 surfaces the same generic error toast as any other failure. Zero backend changes. Full scoped suite green (24 files/175 tests); code review found no blockers (3 non-blocking warnings: no permission gate is by design per the threat model, plus two pre-existing UX/a11y patterns inherited verbatim from the clone source). Verified 9/9 must-haves. This phase postdates v4.0's 2026-08-10 ship date and is tracked as a standalone gap closure, not part of the ITAM milestone.

**Phase 59 (Procurement & Finance — Warranty & Depreciation) complete 2026-08-06** — 4 plans, ITAM-FIN-01/02/03 all done. `itam_finance_service.py`: purchase cost/date/PO/supplier on `PATCH /purchase`, straight-line book value at read time (`GET /book-value`), warranty status + per-tenant alert window (`GET /warranty`), and a background `run_warranty_alert_pass` sweep delivering expiry alerts via both the in-app feed and tenant-configured notification rules, registered at startup with the raw db handle alongside the platform's other raw-database schedulers. Code review found and fixed a real critical bug: the sweep's raw-handle delivery path wrote notifications with no `tenantId` field, making every warranty alert invisible to the tenant it was meant to notify — fixed in `notification_service.py`. Two prior commits (`72a236f`, `490e850`) had added most of this phase's code outside the normal plan/task/commit/SUMMARY process and bundled in unrelated Phase 60/61 work; this session closed the resulting gaps rather than re-executing from scratch. Full backend suite: 1805 passed / 35 skipped / 3 pre-existing unrelated fails. **Flagged for Phase 60: `backend/tests/test_itam_license.py` fails collection (`IndentationError`) — its backend (`itam_license_service.py`/`itam_license_endpoints.py`) was committed alongside Phase 59 work with no plan and no passing tests; do not assume it works.**

**Phase 57 (Lifecycle & Check-In/Out) complete 2026-08-05** — 3 plans, ITAM-LIFE-02/03/04/05 all done. New `backend/itam_lifecycle_endpoints.py` + `backend/itam_lifecycle_service.py`: atomic deployable-gated checkout to a user or location, checkin returns to stock, append-only `assignment_history` collection (separate collection, mirrors the existing `remediation_audit_service.py` insert-only pattern), physical-audit mark + query-time overdue-audit report (fixed 12-month interval). Code review found and fixed 1 critical bug (malformed `createdAt` timestamp silently broke the overdue-report's date math for manually-created assets) plus 5 warnings (no-rollback on history-write failure, unvalidated date strings, disposed assets not excluded from overdue report, stale comment, duplicate router registrations). Full backend suite: 1645 passed / 35 skipped / 3 pre-existing unrelated fails.

<details><summary>Earlier milestones (v1.0 → v3.2)</summary>

**v1.0 shipped 2026-06-18 — all 4 new capabilities live:**

- Rust agent evidence parity — heartbeats feed `compliance_evidence_processor` identically to the Python agent; `agent_type: rust` preserved in evidence records
- Manual evidence uploads — auditors attach PDF/PNG/DOCX/XLSX (≤25 MB) to controls; magic-byte MIME validation; owner/admin delete with disk cleanup
- Audit-ready export — per-tenant PDF and Excel reports with tenant name, export date, Auto/Manual evidence columns, and STATUS_LEGEND (Pass/Fail/Partial/No-Data)
- Remediation workflow — failed control → assignable task → AI-suggested steps → mark Resolved → re-scan dispatch → real-time WebSocket status update
- Test suite: 378 passed, 0 failed, 1 skipped (baseline for v1.1)
- Cloud provider support expanded from 3 to 10 (AWS, GCP, Azure, OCI, IBM, Alibaba, DigitalOcean, Cloudflare, VMware, Huawei)

**v1.1 Phase 6 shipped 2026-06-21:**

- Compliance status override — `PATCH /api/assets/{id}/compliance/status` with tenant isolation, immutable `status_history` (changedBy/changedAt/previous_status), and `manual_override` flag
- Frontend wired — "Mark Compliant / Mark Non-Compliant" buttons in `AssetComplianceList` call backend endpoint; success refreshes data, failure shows toast error
- WCAG AA badge fix — evidence source badges use `text-xs` (previously non-standard `text-[10px]`)

</details>

## Requirements

### Validated

- ✓ **Compliance status override** — PATCH endpoint persists status with immutable history, tenant isolation, manual_override flag (Phase 6)
- ✓ **Frontend status buttons wired** — Mark Compliant/Non-Compliant call backend; toast on error; data refresh on success (Phase 6)
- ✓ **WCAG AA source badges** — text-xs replaces text-[10px] for evidence source badges (Phase 6 / UI-01)
- ✓ Python agent collects compliance telemetry and sends heartbeats to backend
- ✓ `compliance_evidence_processor` maps agent check names to framework control IDs and writes evidence records
- ✓ 30+ compliance frameworks seeded in database (SOC 2, ISO 27001, PCI-DSS, HIPAA, NIST, CIS, GDPR, CMMC, FedRAMP, HITRUST, DORA, NIS2, and more)
- ✓ Multi-tenant architecture with per-tenant data isolation
- ✓ Compliance controls and evidence displayed in React frontend per control
- ✓ Compliance reporting endpoints (PDF, Excel) with tenant headers and evidence source columns
- ✓ **Rust agent evidence parity** — Rust heartbeat data feeds `compliance_evidence_processor` identically to Python; `agent_type: rust` preserved (Phase 1)
- ✓ **Manual evidence uploads** — auditors attach files to controls; magic-byte MIME validation; owner/admin delete RBAC (Phase 2)
- ✓ **Audit-ready export** — per-tenant PDF/Excel with tenant name, export date, auto/manual evidence columns (Phase 3)
- ✓ **Remediation workflow** — task CRUD, AI suggest, re-scan dispatch, real-time WebSocket updates (Phase 4)
- ✓ **Native offline file/URL/IP/hash scanning** — signed bundled feeds, ed25519-verified update mechanism, no live lookup (v3.4 Phase 50, NSCAN-01/02/03)
- ✓ **Agent-side vulnerability detection** — signed CVE feed matching, misconfig + exposed-secret checks, prioritized findings (v3.4 Phase 51, VULN-01/02/03)
- ✓ **File Integrity Monitoring** — event-driven native-OS watcher, signed baseline + restart drift detection (v3.4 Phase 52, FIM-01/02/03)
- ✓ **Autonomous remediation engine** — YAML playbooks, approval gate, rollback on verify-fail, concurrency cap, immutable audit trail (v3.4 Phase 53, AUTO-01/02/03/04)
- ✓ **Native security operator console + API** — findings/remediation-queue/playbooks/audit tabs, full agent-security API surface (v3.4 Phase 54, INT-01/02/03)
- ✓ **Threat-intel correlation + predictive containment + SIEM webhook** — `SiemEngine.correlate_native_findings()`, UEBA shadow_ai auto-containment, outbound OCSF push, real VirusTotal v3 client (v3.4 Phase 55, INT-04/AUT-03/COMM-01)
- ✓ **ITAM check-out/check-in lifecycle** — deployable-gated checkout to a user or location, checkin returns to stock and clears assignment, append-only `assignment_history` audit trail, physical-audit mark + overdue-audit report (v4.0 Phase 57, ITAM-LIFE-02/03/04/05)
- ✓ **Remediation SLA settings UI** — Remediation tab exposes the at-risk-window field via the existing GET/PATCH endpoint, unrestricted visibility matching the endpoint's own gate, non-admin save surfaces the shared generic error toast (Phase 62 gap closure, SLA-03)

### Out of Scope

- New compliance frameworks beyond those already seeded — 30+ existing frameworks cover stated scope; adding more is a future milestone
- Endpoint agent distribution/deployment tooling — agent install workflow already exists; this milestone was about evidence and compliance
- Billing and subscription management — separate concern not related to compliance portal completeness
- Live VirusTotal lookup at native scan time — offline-first design; signed bundled feeds only (v3.4). The VirusTotal v3 client added in Phase 55 serves the separate threat-intel correlation surface, not the NSCAN scan path.
- Third-party SIEM agents — native agent capability supersedes them for v3.4's scope; outbound OCSF webhook (COMM-01) is the integration point instead
- Full YARA-rule engine — yara-x rejected at the Phase 50 spike (pulls in wasmtime/cranelift JIT, cross-compile risk); hash-signature + aho-corasick literal matching shipped instead, full YARA support deferred to backlog item 999.4

## Current Milestone: v4.0 ITAM

**Goal:** Add a full Snipe-IT-parity IT Asset Management lifecycle on top of the existing security/observability CMDB: manage physical/virtual assets through procurement → assignment → maintenance → retirement, with people checking gear in and out, licenses/consumables, and financial/warranty tracking — turning the security-monitoring "asset inventory" into a true ITAM system.

**Target features (all 4 clusters in scope):**
- **Cluster A — Lifecycle + check-in/out:** assign assets to users/locations, check-out/check-in flows, status lifecycle labels (deployable/deployed/archived/retired/disposed/broken), assignment history/audit trail.
- **Cluster B — Procurement + finance:** purchase cost/date/PO number/supplier, warranty tracking + expiry alerts, depreciation schedules (straight-line at minimum).
- **Cluster C — Catalog + org:** manufacturers, asset models, categories, suppliers, locations, custom fields, asset tags + QR/barcode label generation.
- **Cluster D — Licenses + consumables:** software license seats (assign/reclaim/expiry), accessories/consumables/components with check-out + quantities.

**Key constraints:** reuse the existing `assets` model / `asset_endpoints.py` where sensible — don't fork it; support manual (non-agent) assets since Snipe-IT-style assets are hand-catalogued, unlike the current agent-auto-discovered inventory; tenant isolation on every new collection/endpoint; offline-first/air-gapped (label/QR generation with no external services); admin-gated nav pages following the Phase 47/48 pattern (new AppView + App.tsx + Sidebar entry + permission gate).

**Out of scope:** deep accounting/GL integration beyond basic depreciation; multi-currency finance; physical RFID hardware integration (QR/barcode generation only, no scanner drivers); migrating existing security-CMDB semantics (ITAM is additive).

**Phase plan:** TBD — continues numbering from Phase 55 (v4.0 starts at Phase 56)

---

## v2 Backlog Candidates

(none currently — the prior list was mostly stale: scheduled-report auto-email was already shipped in Phase 10, and ticketing/SLA/comment-threads/CSPM-providers were promoted into the v3.2 milestone above after verification against the actual codebase, 2026-07-20)

## Context

**Codebase state (v1.0):** FastAPI (Python 3.12) backend + React/TypeScript frontend. All four compliance portal capabilities are live. `compliance_evidence_processor.py` with `COMPLIANCE_CHECK_MAPPINGS` maps 40+ check names to control IDs across 30+ frameworks. Both Python and Rust agents produce identically-structured evidence records. Manual upload endpoint at `/api/assets/{id}/compliance/evidence` with magic-byte validation. Compliance reporting at `/api/compliance-reports` generates PDF and XLSX with tenant headers and evidence source columns. Remediation workflow at `/api/compliance-remediation` with WebSocket real-time updates via `broadcast_remediation_update`. Integration test suite (`test_e2e_integration.py`) verifies all cross-tenant isolation boundaries.

**Multi-tenant:** Each tenant has isolated data. Compliance posture, evidence, reports, and remediation tasks are scoped per tenant. Five cross-tenant isolation boundaries verified in integration tests (report download, report list, task CRUD, evidence upload, first-heartbeat tenant assignment).

**Test baseline:** 378 passed, 0 failed, 1 skipped across 11 test files. 92 cross-test isolation failures from `importlib.reload()` contamination and Python 3.12 asyncio event-loop lifecycle fixed in post-milestone cleanup.

**Codebase state (v3.4, 2026-08-04):** Native security stack now lives alongside the compliance portal: agent-side scan/vuln/FIM modules in `agent-install/omni-agent-rs` (the shipped Rust agent tree — see the two-agent-tree caveat, `agent-rust/` is the older/download-endpoint tree), backend ingestion + correlation in `backend/security_ops_endpoints.py`, `backend/siem_engine.py`, `backend/remediation_playbook_service.py`, `backend/autonomous_remediation_service.py`, `backend/soc_integration_service.py`, `backend/virustotal_client.py`. Frontend operator console: `components/NativeSecurityConsole.tsx` + `components/nativeSecurity/*` tabs, nav-gated on `manage:active_response`. Full backend suite: 1547 passed / 35 skipped / 3 pre-existing unrelated fails (`test_agentic_ai` tool_choice kwarg, `test_e2e_integration` golden path, `test_rust_heartbeat_parity` agent_type field) as of the v3.4 close session.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Rust agent evidence wired server-side (not client-side) | Backend already has `compliance_evidence_processor`; adding client-side mapping in Rust would duplicate and diverge | Done — `agent_type` kwarg passed from heartbeat endpoint; 0 Rust-side changes needed |
| Manual evidence stored as tenant-scoped file uploads, linked to control ID | Auditors need attachments, not just text notes; file-based evidence is standard in GRC tools | Done — upload/delete endpoints, magic-byte MIME validation, disk cleanup |
| Remediation tasks modelled as lightweight records (not full ticketing system) | Avoids scope creep; existing `ticket_reporter` capability can bridge to external ticketing | Done — `compliance_remediation_tasks` collection, CRUD + AI suggest; Jira bridge deferred to v1.1 |
| Audit export reuses existing PDF/Excel infrastructure | `compliance_reporting_pdf.py` and `compliance_reporting_excel.py` already exist; extend rather than replace | Done — tenant header and Auto/Manual evidence columns added to both; STATUS_LEGEND constant |
| asyncio.run() over pytest-asyncio in tests | pytest-asyncio not installed; asyncio.run() creates fresh loop per call, no Python 3.12 lifecycle issues | Done — consistent across all 7 test files added in v1.0 |
| compliance_remediation_tasks collection name | Avoids collision with `remediation_tasks` used by continuous_compliance_service | Done |
| broadcast_remediation_update list() snapshot copy | Prevents set-mutation-during-iteration; matches broadcast_mitre_heatmap pattern | Done |
| Provider-allowlist widening (Phase 25, CHK-01) touches all 4 duplicated gate locations in lockstep, not just the named execution gate | Leaving account registration narrower than execution would leave the multi-account UI flow still broken | Done — `cloud_checks_service.py`, `cloud_checks_endpoints.py`, `cloud_account_endpoints.py`, `mcp_server_endpoints.py` all widened together |
| CloudFormation container-scan "simulated" data is labeled, not fail-closed (Phase 25, CHK-03) | Labeled simulated data is more useful to the user than an empty/error result when Trivy isn't installed; matches the existing `finops_service` simulated-spend precedent | Done — explicit `simulated` field + SIMULATED badge at 3 dashboard sites, verified via live browser run, not just code inspection |
| Native scanning uses signed bundled feeds, never live VirusTotal/NVD lookups at scan time (v3.4 Phase 50/51) | Offline-first platform value — air-gapped deployments must scan without external network access | Done — ed25519-signed SQLite bundle + delta updates |
| yara-x rejected in favor of hash-signature DB + aho-corasick literal matching (v3.4 Phase 50) | yara-x pulls in wasmtime/cranelift JIT — bloat and cross-compile risk for the shipped Windows/Linux agent binary | Done — full YARA-rule support deferred to backlog 999.4 |
| Autonomous remediation is backend-orchestrated (extends `autonomous_remediation_service`, dispatches via existing `agent_instructions` queue), not a new agent-local engine (v3.4 Phase 53) | Reuses the existing engine's dry-run/severity-ceiling/dedup rather than duplicating safety logic in two places | Done — deterministic YAML playbooks, no LLM in the execution path |
| UEBA `shadow_ai` anomaly containment honors the identical approval gate as manual remediation, no confidence/severity bypass (v3.4 Phase 55, D-04) | A predictive/automated trigger must never have weaker safety guarantees than a human-initiated one | Done — dedicated regression test proves no bypass |
| Checkout-to-location overwrites the asset's existing `locationId` rather than adding a separate `assignedLocationId` (v4.0 Phase 57, D-02) | `locationId` means "where the asset currently is" — one field, not a home/current split | Done — costly-rated (not one-way): prior value stays recoverable from the append-only `assignment_history` ledger the same task authors |
| Overdue-audit interval fixed at 12 months, not per-tenant/per-model configurable (v4.0 Phase 57, D-03) | v1 scope discipline — a config value can be made configurable later without a migration | Done |

**Note (2026-07-06, resolved 2026-07-20):** This file's Requirements/Milestone sections had drifted since v1.1 and weren't kept current through v2.0/v2.1/v3.0/v3.1 — a pre-existing maintenance gap. Corrected at the v3.2 milestone kickoff (2026-07-20): Current Milestone and v2 Backlog Candidates rewritten against verified codebase state (one backlog item, scheduled-report auto-email, turned out to already be shipped in Phase 10). The Validated/Out of Scope requirement lists below still predate v2.0+ and remain a known gap — full catch-up still deferred to a proper `/gsd-complete-milestone` pass.

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-08-11 — Phase 63 (Close gap: ITAM-LIC-02/03 RBAC + ITAM-CAT-05 label UI) complete*
