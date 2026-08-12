# Milestones

## v4.0 ITAM (IT Asset Management Lifecycle) (Shipped: 2026-08-10)

**Phases completed:** 6 phases, 17 plans, 32 tasks

**Key accomplishments:**

- Prove the Phase 56 architecture end-to-end on one thin slice: an admin creates a Manufacturer through a new tenant-isolated catalog router, then hand-catalogues a manual asset that references it — landing in the existing `assets` collection with the new `assetSource` discriminator, `lifecycleStatus` field, and an atomically generated per-tenant asset tag.
- All five ITAM catalog kinds live behind one generic router via a new CATALOG_MODELS per-kind body registry, plus a router-independent `itam_catalog_service.py` fieldset validator (duplicate keys, identifier-shaped keys, option-less selects) that 56-04's asset write path will import directly.
- Atomic, tenant-isolated check-out endpoint (POST /api/assets/{asset_id}/checkout) with a new append-only assignment_history ledger, proving the entire Phase-57 router/collection/state-transition architecture end-to-end before 57-02/57-03/Phase-61 build on it.
- Atomic check-in endpoint (POST /api/assets/{asset_id}/checkin) that closes the hand-off round trip 57-01 opened, plus the per-asset history read (GET /api/assets/{asset_id}/history) that makes the append-only assignment_history trail actually visible — with all three ITAM-LIFE-04 edge semantics (empty, identical timestamps, tie ordering) pinned by tests.
- POST /api/assets/{asset_id}/audit (attributed audit mark, orthogonal to lifecycle/assignment) and GET /api/assets/reports/overdue-audit (three-branch honest-population report with explicit ageBasis/daysOverdue), closing out ITAM-LIFE-05 and Phase 57.
- GET /api/assets/{asset_id}/label/qr streams a PNG QR code of an asset's bare assetTag, RBAC-gated and tenant-isolated, through a newly registered router built on a pure, DB-free generation service.
- Cleared the SUS-flagged python-barcode legitimacy gate via recorded human sign-off, then pinned python-barcode==0.16.1 (exact version) into backend/requirements.txt and installed it into backend/venv, unblocking Plan 03's Code128 barcode generation.
- Added generate_barcode_png (Code128, python-barcode==0.16.1) and GET /api/assets/{asset_id}/label/barcode alongside the existing QR route, sharing one _resolve_tag_for_label prelude, then proved both generators complete with socket.socket/create_connection/getaddrinfo patched to raise unconditionally, backed by a verified negative control.
- POST /api/assets/labels/sheet renders a printable Avery-5160 PDF (3x10 grid, QR + barcode + tag/name/model text per label) for a caller-ordered, duplicate-honouring list of asset ids, refusing every partial request outright rather than silently trimming or dropping it — completing all three label generators' offline proof and closing out Phase 58.
- PATCH /api/assets/{asset_id}/purchase writes an integer-cents purchase/warranty record with D-02 supplier validation; GET /api/assets/{asset_id}/book-value computes straight-line depreciation at read time, floored at salvage, with structured 200 responses (never a 500) for every missing/partial-policy state.
- Extended the closed `itam.warranty_expiring` event-type vocabulary in both `notification_service.VALID_EVENTS` and `notification_endpoints.RuleCreate`'s `Literal`, plus a 14-test pinned contract for both warranty-alert delivery paths Plan 59-04's sweep will call.
- Warranty expiry/status computed at read time from purchaseDate+warrantyMonths via one pure function (`compute_warranty_status`), classified against a per-tenant configurable alert window (`get_warranty_alert_window`), both exposed read-only through `GET /api/assets/{asset_id}/warranty` — the exact two functions Plan 59-04's background sweep will call, so an operator's on-screen status and their alert condition can never disagree.
- Tenant-isolation-safe background sweep (`run_warranty_alert_pass`) that alerts on expiring/expired asset warranties via both the in-app notification feed and tenant-configured notification rules, registered at application startup with the raw database handle and guarded by a `warrantyAlertSentAt` idempotency marker — completing ITAM-FIN-02 and, with it, all three of Phase 59's requirements.
- Software license catalog CRUD, seat assign/reclaim against a real seat count (polymorphic user/asset target), and read-time remaining/expired-seat visibility — ITAM-LIC-01 complete.
- Accessory/consumable catalog CRUD plus an atomically-guarded checkout/checkin pair — quantity > 1 supported per transaction, over-request rejected outright, available quantity always correct under the guard-in-filter pattern. ITAM-LIC-02 complete.
- Component catalog with nullable-parentAssetId attach/detach (record persists on detach, per D-05) and a hydrated asset-scoped listing route — closing the literal "see it listed on that asset's record" success criterion that a bare id-array response didn't satisfy. ITAM-LIC-03 complete.
- Replaced the 13-line ITAMConsole.tsx placeholder with a real 6-tab admin-gated console covering every backend surface Phases 56-60 shipped — Catalog, Check-Out/In, Procurement & Finance, Licenses & Consumables (including consumables/components, not just licenses), plus Compliance and Software Inventory integration tabs. manage:itam gates the Sidebar entry and route; a pre-existing, currently-broken tsc error (viewPermissionMap missing the 'itam' key) is fixed as part of the same wiring. ITAM-UI-01 complete.

---

## v3.4 Native Security Scanning & Autonomous Remediation Agent (Shipped: 2026-08-04)

**Phases completed:** 6 phases (50–55), 25 plans

**Key accomplishments:**

- Native offline scan engine (Phase 50): file scanning against a bundled hash-signature + aho-corasick literal-match set (yara-x rejected at spike — bloat/cross-compile risk, full YARA support deferred to backlog 999.4), URL/IP/domain/hash reputation via signed bundled threat-intel feeds, ed25519-verified signed-bundle update mechanism reused by phases 51/52 — no live lookup at scan time (NSCAN-01/02/03).
- Agent-side vulnerability detection engine (Phase 51): signed CVE feed matching (replaces hardcoded patterns), Linux dpkg/rpm package enumeration, SSH/port misconfiguration + exposed-secret detection, prioritized findings piped into the real `vulnerabilities` store (VULN-01/02/03).
- File Integrity Monitoring (Phase 52): event-driven `notify`-crate watcher (inotify/ReadDirectoryChangesW), rich before/after-hash + process/user change events, ed25519-signed baseline snapshots with restart drift detection (FIM-01/02/03).
- Autonomous remediation engine (Phase 53): deterministic YAML playbook system (6 vendored playbooks, no LLM in the execution path), finding→playbook→execute→verify→complete pipeline, approval gate for destructive actions, rollback on verify-fail, per-agent concurrency cap, immutable append-only audit trail (AUTO-01/02/03/04).
- Operator console + API (Phase 54): tabbed `NativeSecurityConsole.tsx` (Findings / Remediation Queue with approve-deny / Playbooks / Audit), nav-wired under `manage:active_response`, backed by `security_ops_endpoints.py` exposing every agent security function (INT-01/02/03).
- Threat intel correlation + predictive containment + SIEM integration (Phase 55): `SiemEngine.correlate_native_findings()` feeds native findings into the existing rule-evaluation loop; UEBA `shadow_ai` anomalies trigger approval-gated `kill_process` containment; outbound OCSF webhook push at correlation/anomaly/remediation points; real VirusTotal v3 client replacing the dead capability class that had silently broken the `/api/threat-intel/correlate-native` route (INT-04, AUT-03, COMM-01) — the last open verification gap (55-VERIFICATION.md gap #1) confirmed resolved at this milestone close.
- select_playbook() gains a deterministic `finding_type == "anomaly"` branch mapping shadow_ai_detected + a real agent_id onto the existing kill_process playbook, with every other anomaly honestly falling through to no_playbook — zero new action surface, zero LLM.
- UEBA's `report_shadow_ai` endpoint becomes the FIRST production caller of Phase 53's `remediate()` engine — a shadow_ai_detected event with a real agent_id fires a fail-closed, deduped, fire-and-forget, approval-gated `kill_process` containment dispatch; every other anomaly type stays `no_playbook`.
- Outbound OCSF (class_uid=2004) push from correlation/anomaly/remediation pipelines to subscribed SIEM webhooks, fire-and-forget, via the existing SSRF-safe HMAC-signed webhook_service — reusing `notification_manager`'s dispatch pattern and `ocsf_endpoints.py`'s payload shape.
- Rewrote the abandoned `backend/virustotal_client.py` (undefined-`BaseCapability` NameError) into a real synchronous VirusTotal API v3 client behind `get_virustotal_client()`, closing 55-VERIFICATION.md gap #1 and making `POST /api/threat-intel/correlate-native` reachable (200) for the first time.

---

## v3.3 Agent Geo & Fleet Observability (Shipped: 2026-07-30)

**Phases completed:** 4 phases (46–49), 23 plans

**Key accomplishments:**

- Immutable per-agent location-history audit trail: append-only `agent_location_history` with NAT-flip de-noise, per-tenant toggle, 365-day retention, and an ASN/VPN-enrichment foundation (GeoLite2-ASN + bundled X4BNet heuristic) — front-loaded with its privacy/legal review gate (GAUD-01/02).
- Agent-scoped geo security detectors reusing the existing alert fan-out: heuristic (never "detected") VPN/hosting badge, impossible-travel via haversine + time window keyed by `agent_id`, and per-tenant alert-only geo-fence with admin config endpoints (GSEC-01/02/03).
- Fleet observability: per-agent CPU/memory/disk history charts + selectable-range uptime timeline (daily rollups), and an admin-gated aggregate offline + version-drift view (`GET /api/fleet/observability`) (FOBS-01/02/03).
- Air-gapped Fleet Geo Map: self-contained bundled-SVG equirectangular basemap (zero new deps, no tile servers), client-side grid clustering, tenant/status filters, and marker drill-down, backed by a new cross-tenant `GET /api/fleet/geo` endpoint cloning the 48-03 tenant-gating (GMAP-01/02/03).
- Milestone audit passed (11/11 requirements, cross-phase integration confirmed live: the map reads phase-46 geo enrichment + phase-48 status through `geoip_service` + `monitor_agent_status`).

---

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
