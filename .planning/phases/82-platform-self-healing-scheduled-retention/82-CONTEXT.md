# Phase 82: Platform Self-Healing & Scheduled Retention - Context

**Gathered:** 2026-10-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 82 keeps the platform server healthy from outside the backend, and runs data retention on a schedule:

- an out-of-process **watchdog** (systemd timer + oneshot) that checks the backend, MongoDB, nginx and Ollama (only where Ollama is expected), restarts what fails from a fixed list within a restart budget, and pages once when it gives up
- **warnings** before the HTTPS certificate expires (30/14/7/1 days), when the disk passes 80/90/95 percent, and days ahead of a forecast disk-full; the platform never renews a certificate or deletes a file itself
- **on-call alerting** to PagerDuty or a webhook, deduplicated, with a test alert, a "no working channel" banner and a dead-man's switch for the watchdog itself
- **scheduled retention** per tenant in bounded batches that never touches audit logs, the audit ledger, decision records or compliance evidence; its first run only counts and a Super Admin confirms
- watchdog events in the Autonomous Ops **Activity view at platform scope**, plus a Super Admin **Platform health panel**
- the repo ships unit files, the polkit rule, drop-ins and an install checklist; **the app installs nothing on the live server** (installing is the operator's step)

Requirements: HEAL-01..08 (8). Depends on Phase 81 (stop switch, ledger, platform-scope Activity view, `autonomous_ops.notify` hook). Naming rule from Phase 81 still applies: "Autonomous Ops", never "ASI"/"Autopilot".

</domain>

<decisions>
## Implementation Decisions

### Locked by milestone requirements and earlier phases (not re-decided here)
- Out of scope for v4.3: deleting files to free disk, automatic certificate renewal (agents pin the certificate), the app installing systemd units / editing sudoers or polkit / restarting the live server.
- The Platform tenant is never eligible for tenant autonomy (Phase 81 D-04); the watchdog is how the platform server keeps itself healthy, and it acts under its own fixed list, not the tenant gate.
- Ollama is not installed on this VM: its expected state here is "off", so the watchdog never tries to start it (expected-state registry).
- Retention never touches audit logs, the audit ledger or decision records (HEAL-06). The hash-chained audit ledger keeps its own per-tenant purge (`audit_ledger.purge_expired`, spec C5), untouched by this phase.
- Live-only steps stay the user's: installing the watchdog units, the polkit rule and any drop-ins; stopping/starting MongoDB and the backend for real; alert delivery to the real channel; confirming the first retention count. Never `run-on-ubuntu.sh` (ufw SSH lockout).

### On-call channel
- **D-01:** The platform's on-call channel (PagerDuty routing key and/or webhook URL) lives in a **root-only file on the server** (e.g. `/etc/omni-watchdog/oncall.env`, readable by root and the watchdog's own user only). The watchdog reads it directly and sends pages itself, so paging works when the backend or MongoDB is down. The backend **never** holds or sees the key.
- **D-02:** Supported channel types: **PagerDuty Events v2** (stable `dedup_key` per incident) and a **plain JSON webhook**; Slack/Teams incoming webhooks are served through the webhook type with the right message shape. No email (SMTP is unset on this VM). No new libraries: stdlib HTTP client in the watchdog.
- **D-03:** **One page per incident**, deduplicated by a stable key, then a **"resolved"** message when it recovers. Alerts raised in the same check run are grouped into one page (no alert storm).
- **D-04:** Because only the watchdog holds the key, every on-call message from the backend — including Phase 81's notices (stop pressed, circuit breaker tripped, rate limit hit: 81 D-15/D-18/D-20) — is **handed to the watchdog to deliver** (it arrives within about a minute). `backend/autonomous_ops/notify.py` keeps posting the in-app notice and additionally queues the on-call message; its callers do not change.
- **D-05:** **Dead-man's switch:** the watchdog records a heartbeat every run. If it goes silent for a few minutes, the backend raises an **in-app alarm only** (Super Admin banner + in-app notification); it cannot page because it has no key. **Paging** for a dead watchdog or a dead VM comes from an **optional external heartbeat URL** (PagerDuty heartbeat, Healthchecks.io or similar) that the watchdog pings every run when configured in the same root-only file. The install checklist strongly recommends configuring it.

### Restart rules and the stop
- **D-06:** A service counts as down after **2 failed checks in a row** (about 2 minutes), so a slow start is not mistaken for a crash.
- **D-07:** Restart budget: **at most 3 restarts within 30 minutes per service**, waiting **1, then 2, then 4 minutes** between attempts. When the budget is used up the watchdog **stops restarting that service and pages once**.
- **D-08:** The budget **re-arms on its own once the service has stayed healthy for 1 hour** (e.g. after someone fixed it by hand). While the service is still down it stays given up — never a restart loop.
- **D-09:** **MongoDB is restarted before the backend.** When both are down, MongoDB is restarted first and must be healthy before the backend is touched.
- **D-10:** The fixed restart list is **MongoDB, the backend, nginx, and Ollama only where it is expected**. **nginx is added** to the services HEAL-01 names (user-approved clarification: if nginx dies the site is unreachable); it shares the same budget rules. — **Reversibility:** reversible — removing a unit from the list and the polkit rule.
- **D-11:** **"Stop all organizations" pauses the watchdog's restarts.** Checks, warnings and pages continue during a stop; only restarts pause. The watchdog reads the stop from MongoDB when it can (`system_settings` doc `type: "autonomous_ops"`), falls back to the **last stop state it saw** (cached locally) when MongoDB is down, and always honours a **local STOP file** on the server.
- **D-12:** The watchdog runs as its own **dedicated system user (`omni-watchdog`)**, not root. A **polkit rule** shipped in the repo (the operator installs it) lets that user restart **only** `mongod`, `omni-backend`, `nginx` (and `ollama` where expected) and nothing else. Only the on-call file and its own state directory are readable/writable to it. — **Reversibility:** costly — changing the privilege model later means the operator re-installs the units and replaces the polkit rule on every server.

### Warnings
- **D-13:** Certificates watched: by default the HTTPS certificate nginx serves (`/etc/nginx/ssl/omni.crt`, which agents also pin via `AGENT_CA_CERT_FILE`), **plus any extra certificate file paths listed in the root-only config**. Warnings at 30, 14, 7 and 1 days before expiry; the warning text says that replacing a pinned certificate needs an agent update. Never renew.
- **D-14:** Disk warnings at **80, 90 and 95 percent**. **Disk-fill forecast:** growth rate measured over the **last 7 days**; warn when the disk is forecast to be full within **14 days**, again at **7 days**, and **page at 1 day**. Never delete files.

### Retention
- **D-15:** **One scheduled retention job for all routine data:** everything the manual job covers today (system metrics, notifications, agent location history, agent uptime rollups) **except audit logs**, **plus** the four agent telemetry collections (`agent_metrics`, `asset_metrics`, `persistence_results`, `logs`). The existing separate `agent_telemetry_retention_loop` is **folded into this job**, so one job, one dry-run and one report cover everything. Never touched: audit logs, the audit ledger, decision records (`autonomy_actions`), compliance evidence. Per-tenant periods come from the existing `retention_policies`. — **Reversibility:** costly — deleted documents cannot be restored; D-18/D-19 are the safety gates. Consequence to surface in the install checklist: until the first count is confirmed, the telemetry purge that runs daily today also waits, so the confirm should happen soon after deploy.
- **D-16:** The manual route (`POST /api/retention/run`) **stops deleting audit logs too**, everywhere. It keeps cleaning everything else.
- **D-17:** The job runs **nightly at 02:00 UTC**, tenant by tenant, in **small bounded batches with short pauses** so MongoDB stays responsive on the 2-vCPU server. The next scheduled run time is shown (the existing `/stats` `next_scheduled` field and the Platform health panel).
- **D-18:** **First run = count only.** It counts what would be deleted per tenant and per data type and deletes nothing. A **Super Admin confirms once for all tenants**; from then on the nightly job deletes.
- **D-19:** When a tenant **shortens** a retention period, the next run goes **back to count-only for that tenant and data type** until a Super Admin confirms; other tenants and unchanged data types keep deleting. **Lengthening** a period needs no confirmation.

### Screen
- **D-20:** A **Super Admin-only "Platform health" panel on the Autonomous Ops screen** (platform scope, next to the platform stop and platform activity from Phase 81) shows: service states (MongoDB, backend, nginx, Ollama expected-off), watchdog last seen, restart-budget state, certificate expiry, disk usage and forecast, on-call channel status, **Send test alert**, the next retention run, and the **retention count review with Confirm** (D-18/D-19).
- **D-21:** **Send test alert:** the Super Admin clicks the button; the backend records a test request; the watchdog picks it up within a minute, sends it, and reports the outcome; the panel shows "Sent at HH:MM, delivered" or the error. The backend never sees the key (D-01).
- **D-22:** The **"no working on-call channel" banner** and the panel are visible to **Super Admin only**. Tenants never see platform internals.
- **D-23:** Watchdog events (checks that changed state, restarts, warnings, pages, test results) appear in the Activity view **at platform scope, Super Admin only**. They must not leak into tenant views (Phase 81's tenant query already includes platform-scope **stop control** rows for tenant viewers — watchdog events must not ride that path).
- **D-24:** **Before the watchdog is installed:** the panel shows **"Watchdog not installed"** with a link to the install checklist. The dead-man's switch (D-05) **arms only after the first heartbeat ever arrives**, so nothing alarms about a watchdog that was never installed. Disk and certificate checks wait for the watchdog (the backend does not run them meanwhile).

### UI-phase amendments (user-decided 2026-10-27, during /gsd-ui-phase 82)
- **D-25:** The tenant retention screen that edits per-tenant periods is `components/RetentionPolicyDashboard.tsx` (over `/api/retention/policies`); `RetentionPoliciesDashboard.tsx` named in canonical refs is a different screen (`/api/retention-tiers`). On that screen the **audit-logs card keeps its row but loses its Edit button** and shows the note "Audit logs are kept by the audit ledger's own schedule, not by this cleanup." (follows from D-16).
- **D-26:** The **manual "Run cleanup now"** (`POST /api/retention/run`) **honours the same count-only gate** as the nightly job: data types still waiting for confirmation (first run, or a shortened period per D-19) are only counted until a Super Admin confirms; everything already confirmed is deleted as usual. One rule everywhere, so the review cannot be bypassed with Run now. Extends D-16.

### Claude's Discretion
- Which warnings page versus only appear in the panel/Activity (suggested default: every threshold crossing is one deduplicated on-call message, PagerDuty severity rising from info to critical — e.g. 30-day cert and 80% disk as info, 1-day cert, 95% disk and 1-day forecast as critical).
- Exact rule for "no working channel" (suggested: no channel configured, or the last test/delivery failed).
- How the watchdog reads the stop and writes its events/heartbeat (direct MongoDB with its own credentials versus a backend endpoint with a token, with a local spool when the backend is down) — a research item: MongoDB authentication is still an open readiness item and the research recommends a stdlib-only watchdog.
- Which filesystems are measured (at least the one holding `/` and the MongoDB data directory — the same 247 GB disk on this VM).
- Check method per service (backend readiness URL, MongoDB ping, nginx port probe), batch size and pause length for retention, the exact on-call/heartbeat file format, and the Activity row shape for watchdog events.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope and research
- `.planning/ROADMAP.md` — Phase 82 section: goal, 5 success criteria, live-only verification list, "Decisions to settle: D14–D16 gate go-live"
- `.planning/REQUIREMENTS.md` — HEAL-01..08 and the v4.3 Out of Scope table (no file deletion, no cert renewal, app installs nothing)
- `.planning/research/SUMMARY.md` — Phase 82 "Delivers" list, D14 (on-call channel), D15 (user installs units/drop-ins/rules, never run-on-ubuntu.sh), D16 (first retention run manual after dry-run)
- `.planning/research/ARCHITECTURE.md` — Pattern 6 (host watchdog as a second enforcement point, stop read from Mongo / cache / STOP file, dead-man heartbeat, NDJSON spool + ingest), proposed `backend/autonomous_ops/selfheal.py`, `retention_job.py`, `scripts/omni-watchdog.py`. NOTE: research assumed the watchdog runs as root; D-12 overrides that (dedicated user + polkit).
- `.planning/research/STACK.md` — systemd timer + oneshot, PagerDuty Events v2, stdlib-only watchdog, no new dependencies
- `.planning/research/PITFALLS.md` — restart loops, alert storms, retention pitfalls
- `.planning/research/FEATURES.md` — restart budget/backoff, expected-state registry, on-call channel test

### Prior phase decisions that constrain this phase
- `.planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-CONTEXT.md` — D-04 (Platform tenant never eligible), D-11..D-15 (stop behaviour, on-call notice on stop), D-18 and D-20 (on-call told on breaker/rate limit), D-22 (API-only settings precedent), D-25 (platform stop shown as "Platform administrator" to tenants)
- `.planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-UI-SPEC.md` — the Autonomous Ops screen design contract the Platform health panel extends

### Code the phase changes or must respect
- `backend/retention_service.py` — `AGENT_TELEMETRY` map, `purge_agent_telemetry`, `RetentionService.run_cleanup` (calls `cleanup_audit_logs` — D-16 removes that)
- `backend/retention_endpoints.py` — `_POLICY_DEFAULTS`, manual `POST /api/retention/run`, `/stats`
- `backend/app_background_tasks.py` — `agent_telemetry_retention_loop` (folded into the job, D-15), `audit_maintenance_loop` (audit ledger purge, leave alone)
- `backend/audit_ledger.py` — `purge_expired` (leave alone), `replay_spool` (spool-and-replay idiom to reuse for watchdog events)
- `backend/autonomous_ops/notify.py` — the hook Phase 82 extends (D-04)
- `backend/autonomous_ops/settings.py` — `platform_stop` / `system_settings` doc `type: "autonomous_ops"` the watchdog reads (D-11)
- `backend/autonomous_ops/views.py` — platform-scope queries (tenant views include platform stop control rows, ~lines 240–285; D-23)
- `backend/autonomous_ops/ledger.py`, `backend/autonomous_ops_platform_endpoints.py` — platform-scope Activity rows and Super Admin routes the panel builds on
- `backend/notification_endpoints.py` — existing tenant channel test (`POST /api/notifications/test/{channel}`) and PagerDuty Events v2 payload shape to mirror
- `backend/soar_connectors_messaging.py` — PagerDuty connector using `dedup_key`
- `backend/system_health_endpoints.py` — existing `/api/system/health|services|resources` checks
- `components/AutonomousOpsActivity.tsx`, `components/AutonomousOpsStatusCard.tsx`, `components/AutonomousOpsStopBanner.tsx`, `contexts/AutonomousOpsStatusContext.tsx` — the screen, card, app-wide banner and shared poller the panel and the "no working channel" banner join
- `components/RetentionPoliciesDashboard.tsx` — where tenant admins set retention periods (D-19 triggers on a shortened period)
- `start-all-services.sh` — existing generated-unit / publish style (`publish_frontend`, nginx site install) for the shipped unit templates

### Live server facts (not in the repo)
- `/etc/systemd/system/omni-backend.service` — runs as `User=azureuser`; `AGENT_CA_CERT_FILE=/etc/nginx/ssl/omni.crt`
- `/etc/systemd/system/mongod.service.d/` — existing drop-ins (kernel 7.0 fix); new drop-ins must not clobber them
- `/etc/nginx/ssl/omni.crt` — self-signed, CN 10.0.0.4, expires 2029-01-15, pinned by agents
- `omni-backup.timer` — existing timer precedent on the server
- Single 247 GB disk, 69% used on 2026-10-27; MongoDB 8.0 without authentication (open readiness item)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `retention_service.py` / `retention_policies`: per-tenant periods and per-collection delete helpers the scheduled job wraps.
- `audit_ledger.replay_spool`: NDJSON spool-and-replay pattern for watchdog events written while MongoDB/backend are down.
- `autonomous_ops` package (Phase 81): ledger rows, platform scope, the stop document, `notify`, Super Admin platform routes and the screen's shared status poller.
- Tenant notification channels (`notification_endpoints.py`) and the SOAR PagerDuty connector: payload shapes for Events v2 and webhooks (the watchdog re-implements them with stdlib, since it must not import the backend).

### Established Patterns
- Background loops in `app_background_tasks.py` with a distributed lock (Phase 81 hardened the scheduler: one runner at a time with lock renewal).
- Platform-only Super Admin routes under `/api/platform/autonomous-ops` with `control:platform_autonomous_ops`.
- Secrets stay with the user; restarts and installs on the live VM are the user's step (project memory).

### Integration Points
- `autonomous_ops.notify` → on-call queue the watchdog drains (D-04).
- Platform scope of the Autonomous Ops screen → new Platform health panel (D-20) and Super Admin banner (D-22).
- `POST /api/retention/run` and `/stats` → reuse the scheduled job's body, drop audit-log deletion (D-16), fill `next_scheduled` (D-17).

</code_context>

<specifics>
## Specific Ideas

- Watchdog should be "boring": a timer plus a oneshot cannot hang silently the way a daemon can; stdlib only, so it still runs when the backend's virtualenv is broken.
- "One switch stops everything": the platform stop pauses watchdog restarts too, but never silences checks, warnings or pages (D-11).
- Retention errs on the side of counting first: first run, and any shortened period, wait for a Super Admin (D-18/D-19).

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. (Tenant certificate-inventory expiry warnings and an email on-call channel were mentioned as options only, not requested.)

</deferred>

---

*Phase: 82-platform-self-healing-scheduled-retention*
*Context gathered: 2026-10-27*
