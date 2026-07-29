# Milestones

## v3.2 Agent Modernization & Remediation Ops (Shipped: 2026-07-28)

**Phases completed:** 7 phases, 19 plans, 50 tasks

**Key accomplishments:**

- Shipped modernized Rust endpoint agent as version 2.1.3 — reqwest pinned to native-tls, Windows PE cross-compiled and committed, backend heartbeat gate advanced to auto-push to registered agents
- Added the missing `revoked_tokens.jti` unique MongoDB index that `refresh_access_token`'s atomic-consume logic already claimed existed, plus a live-Mongo concurrent-refresh regression test proving exactly-one-winner semantics.
- Three new CIS/Security-Center-aligned check catalogs (OCI, Alibaba, Cloudflare — 29 checks total) wired into the single `RUNNABLE_PROVIDERS` gate so `run_checks()` actually evaluates them and their results count toward CSPM coverage.
- 1. [Rule 1 - Bug] Resolved cryptography/pyOpenSSL downgrade breaking webauthn
- 1. [Rule 3 - Blocking] OCI: used a separate real-client helper instead of un-mocking `_make_oci_client()` in place
- Fixed the addCloudAccount name/credentials field-mapping bug that silently discarded every stored credential, added OCI/Alibaba/Cloudflare-specific credential inputs to the connect-account modal, and surfaced the backend's existing `simulated` flag with a SIMULATED badge plus the three new providers in the Cloud Checks dashboard.
- Three new `elif` branches wire `poll_oci_cspm_findings`/`poll_alibaba_cspm_findings`/`poll_cloudflare_cspm_findings` into `scan_account()`'s existing decrypt-and-ingest ladder, closing the last gap between the Phase 41 check catalogs (41-01) and ingest functions (41-03) — a real scan now imports findings before `run_checks()` evaluates them.
- Tenant-scoped `control_comments` collection with role-gated POST / open GET routes, registered in the live app router.
- Plain-text @mention parsing resolves to a tenant user's email and fires exactly one in-app-only notification (`channels=[]`) per mention, wired into the existing comment POST without ever failing the comment write.
- Two thin `apiService.ts` wrappers, a fetch-on-mount `ControlCommentsPanel` with XSS-safe @mention highlighting and a role-gated composer, mounted unconditionally in `FrameworkDetail.tsx`'s expanded control row right after the Chain of Custody panel — confirmed live in a browser (render, post+persist, cross-user @mention notification delivery, non-reviewer read-only view, escaped comment text).
- New `backend/ticketing_bridge.py` module wiring `compliance_remediation_tasks` to the existing Jira/ServiceNow connectors via an alert-shape adapter, with a 5-minute close-loop scheduler that auto-resolves tasks through the reused `update_task`, and 14 passing hermetic unit tests.
- `create_task` now auto-creates a Jira/ServiceNow ticket for critical/high/medium priority remediation tasks via `ticketing_bridge`, wrapped in a non-blocking try/except so a ticketing outage never prevents task creation.
- `POST /tasks/{task_id}/create-ticket` route exposes the manual "Create Ticket" action with Literal-validated provider and tenant scoping, and the close-loop scheduler is now registered at app startup with the raw `_mdb.db` object (5th scheduler block, cloning `tickets_escalation_service`'s exact shape).
- Three-state Ticketing section added to `RemediationTaskModal.tsx` — Create Ticket button with a Jira/ServiceNow provider picker (D-02), a read-only provider/ref/link display once a ticket exists, and a non-blocking error toast on failure (D-04) — closing REM-01's frontend gap on top of the Plan 01-03 backend.
- New `compliance_remediation_sla_service.py` (day-scale `compute_remediation_sla`, tiered `compute_escalation_level`, configurable `get_sla_at_risk_window`), `create_task` SLA defaults, `compliance_remediation_tasks` compound indexes, and the full 18-test Wave-0 scaffold (`test_compliance_remediation_sla.py`) all five later 44-02/44-03 plans verify against.
- `run_sla_pass`/`start_remediation_sla_scheduler` added to `compliance_remediation_sla_service.py` — a raw-db background sweep that tiers `escalation_level` on breach, writes an immutable `remediation_escalations` entry, and notifies the resolved assignee plus all tenant admins in-app; registered in `app_startup.py` against `mongodb.db`, never `get_database()`.
- New `compliance_remediation_sla_endpoints.py` exposing a tenant-scoped, read-only GET for the append-only escalation history (SLA-02) and an admin-gated GET/PATCH pair for the per-tenant at-risk window (D-02), registered in `router_registry.py` so it's reachable in the live app.
- SLA status badge column in RemediationDashboard.tsx plus a read-only, append-only escalation history panel (new EscalationHistoryPanel.tsx) in RemediationTaskModal.tsx, backed by a new apiService.fetchRemediationEscalations client — human-verified end-to-end including notification delivery and tenant isolation.
- reqwest pinned to native-tls-only via `default-features = false`, and `omni-agent-2.1.3-windows.exe` rebuilt in place with the rustls/aws-lc-rs/webpki stack proven absent by `strings`.

---
