# Phase 86: Activity Reporting, Hardening & Live Validation - Research

**Researched:** 2026-11-11
**Domain:** Reporting over the Autonomous Ops decision ledger (daily digest, per-rule statistics, time-saved estimate, CSV/PDF export) plus hardening proofs (stop drill, two-tenant contract tests, shadow-lift gate with a recorded live checklist). Python/FastAPI/Motor backend, React/Tailwind/Vitest UI, reportlab PDFs. No new libraries.
**Confidence:** HIGH for everything read from the code this session (cited file:line); MEDIUM for design recommendations; items tagged `[ASSUMED]` need user confirmation (see Assumptions Log).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
(Copied verbatim from `86-CONTEXT.md` `## Implementation Decisions`; "Carried forward" items included because they constrain the work.)

**Carried forward, not re-decided**
- Only a Super Admin lifts a tenant's shadow flag (81 D-03). The deployment-wide switch can only force shadow on; lifting it is the user's step (env change + restart, research D19).
- Every tenant's own shadow flag defaults on (81 D-02); unticked tenants are Off and record nothing (81 D-23).
- In-app notices go through `autonomous_ops/notify.py` -> `pending_agents.post_to_recipients` (tenant admins) and the on-call outbox (Phase 82). `notify` never raises.
- The decision ledger `autonomy_actions` is the source of truth; every row carries `reason.ruleId`, state, origin and shadow marking. Decision records are outside generic retention.
- SMTP, VirusTotal and Gemini keys are unset on this VM; features that need them degrade, they are not bugs.

**Daily digest (ACTV-04)**
- **D-01:** Delivered as an in-app notice to each tenant's admins through the existing recipients path, and also by email when SMTP is configured (it is not on this VM, so in-app only here). A failed email never blocks the in-app notice.
- **D-02:** Sent once a day at **07:00 UTC** for every tenant (after the 02:00 retention run and the 02:30 backup). Tenants have no stored time zone; no per-tenant hour setting.
- **D-03:** **Quiet days send nothing:** no digest when nothing ran, nothing was undone and nothing is waiting for approval in the last 24 hours.
  - **Amended 2026-11-11 (user, during UI-SPEC):** simulation items count as activity. A day whose only items are shadow-mode "would have done" entries still sends the digest (counts line `0 ran, 0 undone, 0 waiting` plus the simulation section), so admins can watch the observation week. Quiet = nothing ran, undone, waiting and no simulation items.
- **D-04:** Content: counts for ran / undone / waiting, the first **10** items of each section, and a link to the Autonomous Ops screen. Shadow-mode "would have done" items are a **separate, labelled section** (simulation), never counted as ran.

**Statistics and time saved (ACTV-05, ACTV-07)**
- **D-05:** A **Statistics section on the existing Autonomous Ops screen** (no new sidebar item and therefore no new feature switch).
- **D-06:** Window: last **30 days** by default, with a **7 / 30 / 90 day** choice.
- **D-07:** Per rule (`reason.ruleId`): fired, done, approved, denied, undone, failed, refused. Shadow "would have done" counts are a **separate column/series, never mixed** into the real counts.
- **D-08:** Time saved = a **fixed minutes-per-action-kind table kept in code** (for example isolate host 15 min, answer a ticket 8 min), counted **only for actions that really ran and were not undone** (shadow rows and undone rows excluded). Always labelled **"Estimate"** with the method shown on screen. Not editable by tenants or the Super Admin.

**Export (ACTV-06)**
- **D-09:** Two entry points over one builder: an **Export button on the Autonomous Ops screen** (CSV or PDF of what the screen shows) and an **"Autonomous Ops Activity" entry in the existing report registry** (`export_report_endpoint.REPORT_PERMISSIONS` / `/api/reports/export`). Both need `export:reports` **and** `view:autonomous_ops`.
- **D-10:** The export follows the **current filters** (bucket and date range), capped at **5,000 rows**, with a visible note when the cap cut rows off.
- **D-11:** The PDF has a **summary page** (counts, the per-rule table, the time-saved estimate labelled as an estimate) followed by the rows.
- **D-12:** Every export is **recorded in the audit log**: who, which filter, how many rows, which format.

**Drills and going live (research D2/D19, success criteria 4-5)**
- **D-13:** Stop drill = an **automated test suite** that drives the platform stop and a tenant stop against every actor built in 82-85 (security response, patch rollouts, service-desk AI replies, self-healing/retention) and proves: new security decisions halt, queued instructions are held back, pending approvals and rollouts freeze, AI ticket replies pause; plus a **live drill the user walks on the server** and records (D-14).
- **D-14:** The live-only checklist is **recorded in the app**: the Super Admin ticks each live check with a note (firewall round-trip, reboot gate, watchdog stop/start, alert delivery, live stop drill); each tick is stored and audited. The repo also documents how to walk each item.
- **D-15:** A per-tenant **"Lift shadow mode"** button in the platform view (Super Admin only), **disabled until every checklist item is recorded**, with a **typed confirmation of the tenant name**. Turning shadow back on is always allowed, with no gate.
- **D-16:** A tenant must have at least **7 days of shadow records** before the lift is allowed; the control shows the days observed and the "would have done" counts.
- **D-17:** Two-tenant contract tests: one per automatic loop (security response, patch rollouts, service desk, retention) proving nothing crosses tenants, run hermetically (private mongod or mocks), never against the live database.

### Claude's Discretion
- Exact minutes per action kind in the D-08 table (reasonable, documented values; the screen states they are estimates).
- Digest scheduling mechanism (a loop like `retention_job.retention_loop` with a distributed lock, or the APScheduler in `scheduler.py`), idempotency so a restart never sends two digests for the same day, and the digest's stored shape.
- Where the checklist and observation-period state live (collection or tenant settings fields), and whether the existing `PUT /api/autonomous-ops/platform/tenants/{id}/shadow` route enforces the D-15/D-16 gate server-side (it must: the UI gate alone is not enough).
- PDF/CSV builder reuse (`export_service` / `export_service_pdf` / reportlab) and layout.
- Statistics API shape and aggregation strategy over `autonomy_actions` (indexes as needed).

### Deferred Ideas (OUT OF SCOPE)
- Per-tenant digest hour or time zone.
- Editable minutes-per-action table.
- UI for changing level / maximum level and editing the never-touch list (still API-only).

Also out of phase (CONTEXT `<domain>`): changing a tenant's level or maximum level from the UI, editing the never-touch list from the UI, flipping the deployment-wide `AUTONOMOUS_REMEDIATION_DRY_RUN` switch, restarting anything on the live VM. Naming rule: "Autonomous Ops", never "ASI", "Autopilot", "fully autonomous" or an unqualified "rollback".
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ACTV-04 | Daily digest of what ran, what was undone and what waits for approval | Sections "Digest" under Architecture Patterns (tenant-admin-only post path, claim-document idempotency, 07:00 UTC loop, `_waiting_filter` reuse, email via `_resolve_smtp_config`), Pitfalls 1, 4, 5, 6 |
| ACTV-05 | Per-rule statistics (fired, approved, denied, undone) | "Statistics" pattern: one `$group` over `autonomy_actions`, state-to-column map (below), existing `tenant_created` index serves it |
| ACTV-06 | Export the activity log as CSV or PDF | "Export" pattern: one builder, dedicated route plus registry branch, `export_controls.EXPORT_PATHS` edit, audit event, DLP, CSV/PDF injection defences; Pitfall 2 (uncommitted export WIP) |
| ACTV-07 | Honest operator time-saved estimate, labelled as an estimate | Minutes-per-kind table keyed to `registry.ACTIONS` plus `ticket_answer`; only `executed`/`verified` rows count; `ticket_handoff` is 0 |
| Success criteria 4-5 (hardening, no new REQ id) | Stop drill across actors, two-tenant contract tests, live checklist + shadow-lift gate | "Shadow lift gate", "Stop drill" and "Two-tenant contract tests" patterns; go-live document outline; Validation Architecture |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Do what has been asked, nothing more. Never create documentation files unless explicitly requested. **Exception here:** `docs/autonomous-ops-go-live.md` is explicitly required by locked decision D-14 ("The repo also documents how to walk each item") and by 86-UI-SPEC, so it is requested.
- Never save working files or tests to the repo root; use `/src`, `/tests`, `/docs`, `/config`, `/scripts` (backend tests live in `backend/tests/`, vitest in `src/__tests__/`).
- Keep files under 500 lines. `components/ReportingDashboard.tsx` is already 601 lines and `backend/autonomous_ops/views.py` is 448, so new behaviour goes in new files (UI-SPEC already says so for the UI).
- Always read a file before editing it; never commit secrets, credentials or `.env` files (the secret-read guard blocks `backend/.env`; ask the user for any value).
- Validate input at system boundaries (pydantic `Literal`/bounded `Annotated` on every new route parameter).
- Always run tests after code changes; build must succeed before committing. Ruflo/swarm/memory directives are orchestration conventions, not constraints on the research.
- Project rules from memory that bind execution: restarts, UI publishes and `git push` are the user's steps; never touch the live mongod (127.0.0.1:27017); archive, do not delete; the live backend runs from the working tree.

## Summary

Phase 86 is mostly **aggregation and plumbing over data Phase 81-85 already write**. Every decision is one `autonomy_actions` row with a single current `state`, `reason.ruleId`, `command`, `approval.approver`, `undo.undoneAt`, `createdAt`/`finishedAt` and (for simulations) `state == "shadow"`. Per-rule statistics, the digest and the export are all read-only queries over that collection; the existing `(tenantId, createdAt)` and `(tenantId, state, createdAt)` indexes serve them, and the only index worth adding is `(tenantId, finishedAt)` for the digest. The new write paths are small: an idempotency claim collection for the digest, an append-only go-live checks collection, and the server-side gate on the existing shadow route.

Three findings change the plan shape. **(1) The export path the context treats as existing is uncommitted user work:** `backend/export_report_endpoint.py` (the whole `REPORT_PERMISSIONS` registry and DLP scan), `backend/export_service.py` (`fetch_rows`/`render`), `backend/export_controls.py` (untracked: daily allowance, audit, bulk-export DLP), the `ExportControlMiddleware` registration in `backend/app_middleware.py` and `backend/email_utils.py` (untracked) are in the working tree only; HEAD has none of `REPORT_PERMISSIONS`/`ExportControlMiddleware`. Phase 87 hit exactly this failure (verification gap, `422af6095`). The plan must start with a decision checkpoint to commit that export set (or only the hunks Phase 86 needs) and must verify on a `git archive` snapshot. **(2) `notify.notify` is the wrong call for the digest:** it posts to the platform tenant's feed and queues an on-call page; the tenant-admin-only precedent is `plan_notices.announce` -> `pending_agents._post_in_app(... {"audience": "tenant_admins"})`. **(3) The stop drill must not "prove" retention pauses:** the Phase 82 design is that a platform stop does not pause retention (`test_the_platform_stop_does_not_pause_retention` exists), so the drill asserts the documented behaviour for retention and the watchdog's restart pause separately.

**Primary recommendation:** Build one `backend/autonomous_ops/reporting/` package (stats, digest, export, go-live, rule names) added to the copy gate as a *directory*, add two thin route modules (tenant statistics+export under `AUTONOMOUS_OPS_GUARD`, platform go-live beside the retention endpoints), enforce the lift gate inside `put_shadow`, ship migration 035 as indexes only, write the drill and two-tenant tests as new `test_autonomous_ops_*.py` files on the private mongod (27998), and gate the export work behind a "commit the user's export WIP first" checkpoint.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Per-rule statistics, time-saved estimate, window choice | API / Backend (one `$group`, code-owned minutes table) | Browser (renders, period pills) | Numbers must be computed where tenant isolation and the shadow/real split are enforced; the browser only formats |
| Daily digest scheduling and idempotency | API / Backend (background loop + Mongo claim doc + distributed lock) | Database (unique index) | Must survive restarts and multiple workers; no browser involvement |
| Digest delivery (in-app, email) | API / Backend | Database (`notifications`), SMTP | Tenant-admin audience filter is enforced at read time by `notification_audience.reader_filter` |
| CSV/PDF export, row cap, truncation signals | API / Backend | Browser (download + banner from headers) | Server owns permission, tenant scope, DLP, audit and the cap |
| Export audit | API / Backend (`audit_ledger.event`) | `ExportControlMiddleware` (generic `data.export`) | The middleware records path/bytes/rows only; filter and format need an explicit event |
| Go-live checklist records | API / Backend + Database (append-only collection) | Browser (inline form) | Evidence must be server-stored with the actor and audited |
| Shadow-lift gate | API / Backend (`put_shadow`) | Browser (disabled button, reasons) | "The UI gate alone is not enough" (CONTEXT specifics); server returns reason codes the UI words |
| Stop drill / two-tenant contract tests | Test suite (pytest, private mongod) | Live walk by the user (go-live document) | Automated proof of the code paths; live proof is operator-only |

## Standard Stack

No new library is needed. Everything is already installed and in use.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI + pydantic | fastapi 0.141.1 [VERIFIED: `backend/venv/bin/python -m pip list`] | New routes, `Literal`/`Annotated` input validation | Every existing Autonomous Ops route uses it |
| Motor / PyMongo | motor 3.7.1, pymongo 4.18.2 [VERIFIED: pip list] | Aggregation, claim documents, indexes | `autonomous_ops.scope.raw` handle with explicit `tenantId` |
| reportlab | 5.0.1 [VERIFIED: `import reportlab; reportlab.Version`] | PDF summary page + rows table (platypus) | Already used by `export_service_pdf.py` |
| aiosmtplib / `email_service` | aiosmtplib 5.1.3 [VERIFIED: pip list] | Email | Use `email_service.send_email` with `_resolve_smtp_config` (committed at HEAD), the Phase 87 precedent; not `email_utils` (untracked) |
| pytest + pytest-asyncio | pytest 9.1.1, pytest-asyncio 1.4.0, `asyncio_mode = auto` [VERIFIED: pip list; `pytest.ini`] | Backend tests | Existing suites |
| vitest | `^5.0.0` [VERIFIED: `package.json` scripts/devDependencies line `"vitest": "^5.0.0"`] | UI tests | Existing suites |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `distributed_lock.lock_with_renewal` | in repo | One digest runner at a time | Same shape as `retention_job.run_once` (`lock_db = SimpleNamespace(_db=raw(db))`) |
| `itam_data_service.sanitize_csv_cell` | in repo (`backend/itam_data_service.py:63`) | CWE-1236 formula-injection guard for every CSV cell | Every exported text cell (targets, hosts, ticket titles are attacker-influenced) |
| `xml.sax.saxutils.escape` | stdlib | reportlab `Paragraph` parses mini-HTML; escape every server string | Every PDF cell |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Retention-style loop + Mongo claim doc | APScheduler in `scheduler.py` | A scheduler job still needs the claim doc for restart/multi-worker idempotency; the loop pattern is already proven here and testable with injected `now` |
| `email_utils.send_email_async` | `email_service.send_email` + `_resolve_smtp_config` | `email_utils` is env-based (defaults to `localhost:587`, so "configured" cannot be told) and untracked; the DB-config path answers "SMTP configured?" by `_resolve_smtp_config(...) is not None` |

**Installation:** none. **Version verification:** versions above were read from the venv this session (`pip list`, `reportlab.Version`), not from training data.

## Package Legitimacy Audit

No external packages are installed by this phase (backend or frontend), so the `package-legitimacy` gate has nothing to check. Packages removed due to SLOP: none. Packages flagged SUS: none.

## Architecture Patterns

### System Architecture Diagram

```
                      (07:00 UTC, every 5 min wake)
 digest_loop --lock--> due(now, claims)? --no--> sleep
      |                       | yes
      |            for tenant in sweep._ticked_tenants (not platform)
      |                       |
      |         INSERT claim {tenantId, day} (unique) --DuplicateKey--> skip (already sent/quiet)
      |                       |
      |         ledger queries (window = 24h ending 07:00 UTC of `day`)
      |           ran/undone by finishedAt, simulation by createdAt, waiting = incident_views._waiting_filter
      |                       |
      |         quiet (all four empty)? --yes--> claim.state="quiet", send nothing
      |                       | no
      |         build text (counts line, <=10 items/section, simulation section)
      |                       |
      |         pending_agents._post_in_app(tenant, audience=tenant_admins)   [in-app, never on-call, never platform feed]
      |                       |
      |         _resolve_smtp_config(tenant)? yes -> email_service.send_email per tenant admin (wait_for 30 s, failures logged)
      |                       |
      |         claim.state="sent", sentAt, counts

 Browser (Autonomous Ops screen, tenant scope)
   StatsCard --GET /api/autonomous-ops/statistics?days=7|30|90[&tenantId]-->  stats.compute (one $group over autonomy_actions)
   Export dialog --GET /api/autonomous-ops/export?format&bucket&days[&tenantId]--> export.build -> DLP -> audit -> file + X-Export-* headers (204 when 0 rows)
 Browser (Reporting screen)
   card --GET /api/reports/export?type=Autonomous Ops Activity&format--> (refuse platform staff) -> export.build (all states, 30 d)

 Super Admin (platform scope)
   Going live card --GET /api/platform/autonomous-ops/golive--> checks(latest of 5) + per-org {daysObserved, wouldHaveDone, blockers}
   record check   --POST /api/platform/autonomous-ops/golive/checks/{id} {note}--> append-only insert + audit event
   Lift shadow    --PUT /api/platform/autonomous-ops/tenants/{id}/shadow {shadow:false}--> put_shadow: gate(blockers)? 409 : set_shadow + audit
```

### Recommended Project Structure
```
backend/
├── autonomous_ops/reporting/        # NEW package; add the DIRECTORY to the copy gate (not file by file)
│   ├── __init__.py                  # constants: WINDOWS=(7,30,90), MINUTES_PER_KIND, EXPORT_ROW_CAP=5000, DIGEST_HOUR_UTC=7
│   ├── rule_names.py                # code-owned ruleId -> plain name (fallback: the id)
│   ├── stats.py                     # state->column map, aggregation, time saved
│   ├── digest.py                    # window queries, claim, post, email
│   ├── digest_text.py               # pure text builders (in-app + email)
│   ├── digest_job.py                # due(), run_once(), digest_loop()
│   ├── export.py                    # rows (via views.present_row), CSV, filename, caps
│   ├── export_pdf.py                # summary page + rows table
│   └── golive.py                    # checks (append-only), observation days, lift blockers
├── autonomous_ops_reporting_endpoints.py        # GET /api/autonomous-ops/statistics, /export (tenant router, AUTONOMOUS_OPS_GUARD)
├── autonomous_ops_golive_endpoints.py           # GET /golive, POST /golive/checks/{id} (platform router)
└── migrations/035_activity_reporting.py         # indexes only
components/autonomousOpsStats/ , components/autonomousOpsGoLive/ , services/autonomousOpsReporting.ts   # per 86-UI-SPEC
docs/autonomous-ops-go-live.md
```

### Pattern 1: Ledger row shape and the state-to-column map (Q1)

Row fields written by `decision_row.build_row` [VERIFIED: `backend/autonomous_ops/decision_row.py:79-100`], quoted: `"tenantId": req.tenant_id, "kind": req.kind, "origin": req.origin, "dispatcher": req.dispatcher,`, `"command": spec.name if spec else None,`, `"state": state, "level": ctx.level, "shadow": ctx.shadow is not None,`, `"wouldHave": outcome if state == "shadow" else None,`, `"reason": req.reason or {"ruleId": f"gate:{req.origin}", "inputs": {}},`, `"approval": {"requiredBy": ..., "expiresAt": ..., "approver": None, "decidedAt": None},`, `"undo": undo_block(...)`, `"autoDispatched": state == "dispatching",`, `"createdAt": ctx.now, "updatedAt": ctx.now,`. `finishedAt` is added by `ledger.create_intent`/`transition`.

States [VERIFIED: `backend/autonomous_ops/__init__.py:48-60`]: `OPEN_STATES = ("suggested", "awaiting_approval", "approved", "dispatching")`, `TERMINAL_STATES = ("shadow", "executed", "verified", "failed", "rolled_back", "undone", "denied", "expired", "cancelled_by_stop", "refused")`, buckets `"pending": ("awaiting_approval", "approved", "dispatching")`, `"simulation": ("shadow",)` (full table in the file). Rows of `kind` `"control"` and `"platform_health"` are not decisions and must be excluded from statistics, digest and the summary counts [VERIFIED: `ledger.py:147` `"kind": "control", "state": "recorded"`; `ledger.py:177` `"kind": "platform_health", "state": "recorded"`].

Indexes today [VERIFIED: `ledger.py:87-96`]: `id_unique`, `tenant_created` `[("tenantId", 1), ("createdAt", -1), ("id", -1)]`, `tenant_state_created` `[("tenantId", 1), ("state", 1), ("createdAt", -1)]`, `state_expiry`, partial unique `open_dedupe`.

**Recommended mapping** (one pass over `(ruleId, command, state, approved)` groups; `approved` = `approval.approver` is non-null):

| Column | Rule |
|--------|------|
| Fired | every non-shadow, non-control, non-platform_health row created in the window |
| Done | `state in ("executed", "verified")` |
| Approved | `approval.approver != null` (a person approved or sent it; survives later `undone`/`failed`/`refused`) |
| Denied | `state == "denied"` (a person said no; desk discard also sets `denied`) |
| Undone | `state in ("undone", "rolled_back")` |
| Failed | `state == "failed"` |
| Refused | `state in ("refused", "expired", "cancelled_by_stop")` `[ASSUMED]` (see A2; the UI-SPEC glossary says "blocked by a limit or a never-touch entry", so the one glossary line must be widened to also cover a stop and an approval nobody answered) |
| Would have done | `state == "shadow"`, own column, never summed into the others |

Approver is recorded on approval by `approvals.approve` [VERIFIED: `approvals.py:173` `**{"approval.approver": dict(approver), "approval.decidedAt": now})`], on deny [`approvals.py:221`], and by the desk for a person-sent draft (`service_desk/lifecycle.py` `"approval.approver": who`) and a discarded one (`"denied"` with the same fields). Automatic rows keep `approver: None`.

### Pattern 2: Statistics aggregation (Q3)

```python
# Source: derived from ledger.counts (ledger.py:311-320) and the indexes above
pipeline = [
    {"$match": {"tenantId": tenant_id, "createdAt": {"$gte": since},
                "kind": {"$nin": ["control", "platform_health"]}}},          # uses tenant_created
    {"$group": {"_id": {"rule": "$reason.ruleId", "cmd": "$command", "state": "$state",
                        "approved": {"$ne": [{"$ifNull": ["$approval.approver", None]}, None]}},
                "n": {"$sum": 1}}},
]
```
Fold the groups in Python with the table above. Rows are bounded (decisions kept 365 days; 90 days max window), so no `$facet` or new index is needed. Always pass `tenantId` explicitly (raw handle, no ambient ContextVar: `scope.raw`).

**Routes** live in a new tenant module mounted under `AUTONOMOUS_OPS_GUARD` (add a `MOUNTS` entry in `backend/catalogue_mounts_autonomous_ops.py:30-34` and a `_load` line in `router_registry.py` beside line ~355; `autonomous_ops_endpoints.py` is 451 lines so it cannot take them). Reuse the helpers there: `_tenant_for`, `views.build_caller`, `views.holds`, `_unavailable`. `GET /api/autonomous-ops/statistics?days=7|30|90[&tenantId=]`; response carries `rules[]` (id, name, seven counts, `wouldHaveDone`), `totals`, `timeSaved {minutes, perKind[]}`, `canExport`, `generatedAt`, `shadowOnly`. Platform tenant -> 409 via `messages.API_DETAIL["platform_tenant"]` (as `post_stop` does).

Frontend fetch: add `services/autonomousOpsReporting.ts`; reuse the exported `getJson`, `failure`, `withTenant` from `services/autonomousOpsApi.ts` [VERIFIED: lines 291, 302, 314]; `API_BASE` already ends in `/api` (`${API_BASE}/autonomous-ops/status`).

### Pattern 3: Time-saved table (Q3)

Action kinds in `registry.ACTIONS` [VERIFIED: `backend/autonomous_ops/registry.py:41-72`]: auto `block_ip`, `quarantine_file`, `restart_service`, `install_patches`, `ticket_answer`; approve `isolate_host`, `kill_process`, `reboot_host`, `upgrade_software`, `restore_file`, `disable_service`, `rotate_key`, `rollback_ransomware`; undo-only `unblock_ip`, `enable_service`, `unquarantine_file`, `restore_host`, `rotate_key_rollback`, `rollback_patches`, `ticket_withdraw`; probes `scan_file`, `scan_ip`, `scan_url`, `scan_hash`. The desk also writes `command = "ticket_handoff"` rows, state `executed` [VERIFIED: `ledger.py:213` `HANDOFF_COMMAND = "ticket_handoff"`, `ledger.py:235-250`].

Count `state in ("executed", "verified")` rows only (shadow/undone excluded by state), `minutes = MINUTES_PER_KIND.get(command, 0)`. Recommended values `[ASSUMED]` (D-08 leaves them to discretion; user should glance at them because the headline claim rests on them):

| Command | Min | Command | Min |
|---------|-----|---------|-----|
| `isolate_host` | 15 (CONTEXT example) | `rotate_key` | 20 |
| `ticket_answer` | 8 (CONTEXT example) | `rollback_ransomware` | 30 |
| `block_ip` | 10 | `restore_file` | 15 |
| `quarantine_file` | 15 | `disable_service` | 10 |
| `restart_service` | 10 | `reboot_host` | 10 |
| `kill_process` | 10 | `upgrade_software` | 10 |
| `install_patches` | 10 (per host, see A3) | every other command, incl. `ticket_handoff`, undo-only, probes | 0 |

Return the whole table (including zero-count kinds) in `perKind[]` for the "Show minutes per kind of action" disclosure; `Total` equals the sum of subtotals (UI-SPEC backstop). Format minutes per R16 in the UI, never a decimal.

### Pattern 4: Daily digest (Q2, D-01..D-04)

**Post to tenant admins only.** `notify.notify` does two extra things [VERIFIED: `backend/autonomous_ops/notify.py:20-31`]: `pending_agents.post_to_recipients(...)` and `await oncall.enqueue(...)`; and `post_to_recipients` first posts to the platform feed [VERIFIED: `backend/pending_agents.py:276` `await _post_in_app(raw, PLATFORM_TENANT_ID, title, message, severity, metadata)`]. The existing tenant-admin-only path is `plan_notices.announce` calling `pending_agents._post_in_app(raw, tenant_id, title, message, "info", {"event": ..., "tenantId": ..., "audience": pending_agents.TENANT_ADMIN_AUDIENCE, ...})` [VERIFIED: `backend/plan_notices.py:42-46`; `TENANT_ADMIN_AUDIENCE = "tenant_admins"` at `pending_agents.py:46`]. An audience-tagged notice is stored once and never pushed on the tenant socket (`notification_audience.broadcastable`, line 52) and is read only by users holding `*` or `manage:agents` [VERIFIED: `notification_audience.py` `if "*" not in perms and "manage:agents" not in perms:`], i.e. tenant admins. Tag `metadata` `{"source": "autonomous_ops", "event": "autonomous_ops.daily_digest", "audience": "tenant_admins", "day": "<YYYY-MM-DD>", "counts": {...}}`.

**Window and sources** (all via the raw handle, explicit `tenantId`):
- window end = 07:00 UTC of the claim's `day`; start = end - 24 h (a late catch-up reports the same fixed window, so digests never overlap or leave gaps).
- Ran: `state in ("executed","verified")`, `finishedAt` in window. Undone: `state in ("undone","rolled_back")`, `finishedAt` in window. `ledger.transition` overwrites `finishedAt` on every terminal move [VERIFIED: `ledger.py:132-133` `if to_state in TERMINAL_STATES: sets.setdefault("finishedAt", now)`: `sets` carries the caller's fields only, so each terminal transition sets a new time], so a row's `finishedAt` is its latest terminal time (an executed->verified move can re-date it; accepted, see Pitfall 7).
- Simulation: `state == "shadow"`, `createdAt` in window.
- Waiting: the current set `incident_views._waiting_filter(now)` [VERIFIED: `incident_views.py:68-79`, three `$or` conditions: awaiting_approval, level-suggest parked suggestions, unconfirmed isolation], so the digest count equals the screen's "Needs your decision". Desk drafts (`suggestionOnly: True`) are excluded by that filter; this is intended (they are sent on the ticket, not approved in Activity).
- Exclude `kind` `control`/`platform_health` everywhere.

**Quiet day** (D-03 amended): quiet iff ran = undone = waiting = simulation = 0. A shadow-only day sends `0 ran, 0 undone, 0 waiting` plus the simulation section. Failed/refused-only days send nothing (the locked UI-SPEC has no failed group; see Open Question 3).

**Idempotency (survives restart and multiple workers).** Do not use `notifications` (30-day retention type) as the record. New collection `autonomy_digests`, unique index `(tenantId, day)` (`day` = UTC `YYYY-MM-DD`). Per tenant: `insert_one({"tenantId", "day", "state": "claimed", "claimedAt"})`; `DuplicateKeyError` means someone already handled it (sent or quiet) -> skip; after posting `update_one(... {"$set": {"state": "sent"|"quiet", "sentAt", "counts", "email": {"sent": n, "failed": m}}})`. This is at-most-once by design ("a restart never sends two"); a crash between claim and post loses that day's digest (state stays `claimed`, logged on the next pass, never re-sent) `[ASSUMED]` see A4. A quiet day also writes a claim (state `quiet`), so the 5-minute wake is one cheap query, not a recompute per tenant. Wrap the pass in `distributed_lock.lock_with_renewal(SimpleNamespace(_db=raw(db)), "autonomous_ops_digest", ttl_seconds=120, renew_every=30)` exactly like `retention_job.run_once` [VERIFIED: `retention_job.py:260-272`, `lock_db = SimpleNamespace(_db=raw(db))`, `distributed_lock reads db._db`]. The unique index is the correctness guard; the lock only avoids duplicate work.

**Scheduling at 07:00 UTC.** Copy the retention loop [VERIFIED: `retention_job.py:296-310` `retention_loop` waits `STARTUP_DELAY` then every `WAKE_EVERY` (300 s) calls `run_once`; `due()` at line 233 is true from the hour on while no run is recorded for today]. `due(now, claimed_days)`: `now >= 07:00 UTC` and no claim for `now.date()` exists for the tenant. Register in `backend/app_startup.py` right after the retention task (lines 540-543):
```python
from autonomous_ops.reporting.digest_job import digest_loop as _digest_loop
asyncio.create_task(_safe_bg_task(_digest_loop(), "autonomous_ops_digest"), name="autonomous_ops_digest")
```
A catch-up limit of the same UTC day is sufficient. The loop calls `ensure_indexes` itself on first pass (idempotent), because migration 034 is committed but not applied and 035 will only run at the user's next restart; the rollout loop already does this self-healing (`rollout/loop.py:_indexes_ready`).

**Tenant list.** Reuse `sweep._ticked_tenants(db)` [VERIFIED: `sweep.py:55-57`: tenants whose `enabledFeatures` contains `view:autonomous_ops`, minus `PLATFORM_TENANT_ID`]. A stop does not suppress the digest (it reports, it does not act); a tenant at level Off but ticked still gets its digest if there is activity.

**Email.** Recipients: users with `tenantId == tenant` and `role in TENANT_ADMIN_ROLE_NAMES` [VERIFIED: `backend/auth_roles.py:17` `TENANT_ADMIN_ROLE_NAMES: Tuple[str, ...] = ("admin", "Admin", "Tenant Admin", "tenant_admin")`; query shape as `compliance_remediation_sla_service._tenant_admin_emails`]. SMTP is "configured" iff `_resolve_smtp_config(db, tenant_id)` returns a document [VERIFIED: `auth_password_reset_endpoints.py:48-77`, returns the first of own `smtp_config`, tenant `emailConfig`, platform `emailConfig` with `smtpPasswordEncrypted`, else None; committed at HEAD `422af6095`]. It reads `db.smtp_config` through the tenant wrapper (line 62), so call it inside `scope.tenant_scope(tenant_id)` (as the sweep does) and with the wrapper `get_database()`; do not pass the raw handle. Send with `email_service.send_email(smtp_config=smtp, to_email=addr, subject, body_text, body_html)` per admin, each inside `asyncio.wait_for(..., 30)` and `try/except` (its SMTP call has no timeout of its own and returns `{'success': False}` on failure). Link: the SPA has no per-screen URL (`App.tsx` switches on state), so the link is `FRONTEND_URL` (the invite pattern: no http(s) `FRONTEND_URL` -> skip the email and log once, in-app still goes) plus the words "Open Autonomous Ops in the sidebar". Strip CR/LF from the organization name before it goes into the subject (header injection). Keep `email_utils` out of this.

**Text.** Pure functions in `digest_text.py` render the UI-SPEC section 5 shapes. Needs: a rule-name map (below), a past-tense verb map for the simulation lines (`block_ip` -> "blocked", ...; the existing `messages.SIMULATION_WOULD_HAVE` is a different sentence shape), and `views.present_row` for `actionLabel`/`host`/`target`. Cap `target` at ~80 characters and each section at 10 items (message size stays bounded).

**Rule names.** There is no id-to-name table today [VERIFIED: ruleIds found in `sweep_security.py:54-57` `sweep:block_ip`, `sweep:single_signal`, `sweep:quarantine_file`, `sweep:isolate_host`; `followups.py:40` `sweep:kill_process`; `sweep_restart.py:45` `sweep:restart_service`; `sweep_suggestions.py:41` `sweep:suggest_vulnerability`, `sweep:suggest_file_change`; `rollout/__init__.py:28` `LINES = ("install", "reboot", "revert_reboot")` giving `rollout:install|reboot|revert_reboot` plus `rollout:canary_install`; `service_desk/outcomes.py:54` `service_desk:answer`; `ledger.py:239` `service_desk:handoff`; `decision_row.py:90` fallback `gate:{origin}`]. Add `rule_names.py` (code-owned dict; unknown ids display the id itself, so a new rule never breaks a report).

### Pattern 5: Export (Q4, D-09..D-12)

**Today** (working tree, uncommitted): `export_report_endpoint.py` defines `REPORT_PERMISSIONS = {...}` (line 20) mapping a type to a tuple of view permissions, the route depends on `require_permission("export:reports")`, requires any of the type's permissions via `verify_permission`, and for Super Admin sets `set_tenant_id("platform-admin")` and `tenant_id = None` [VERIFIED: `export_report_endpoint.py:56-60` `is_admin = getattr(user, "role", "") in _SUPER_ROLES` / `if is_admin: set_tenant_id("platform-admin")` / `tenant_id = None if is_admin else getattr(user, "tenant_id", None)`]. It runs `dlp_service.scan_export(rows, tenant_id)`, then `service.render(type, format, rows)` and sets `X-Export-Rows` (line 79). `ExportService.render` builds CSV via `csv.DictWriter` and PDF via `ExportServicePDFMixin._generate_pdf` (`Paragraph(str(row.get(h, "—")), cell_style)`, no escaping, no summary page).

**Recommendation: one builder, two entry points, builder outside `ExportService`.**
- `reporting/export.py: async def build(db, tenant_id, *, bucket, days, fmt, caller) -> ExportResult(content|None, filename, media_type, shown, total, truncated)`. Rows come from the same filter `views.list_page` builds (extract that filter into a small `views.activity_filter(tenant_id, bucket)` helper so the export is "what the screen shows" incl. platform stop control rows, D-25 names; `views.py` has room: 448 lines, the extraction is net-zero), sorted `createdAt` desc, `limit(EXPORT_ROW_CAP)` (5,000) plus `count_documents(flt)` for `total`. Use `views.present_row` for display strings, plus the approver's `display` read from the raw row. State column shows the word `Simulation` for `state == "shadow"` (UI-SPEC section 3).
- Dedicated route `GET /api/autonomous-ops/export?format=csv|pdf&bucket=<Bucket>&days=7|30|90|all[&tenantId=]` in the new tenant router: `views.resolve_tenant` (a tenant role always means its own tenant; platform owner must name one; Support cannot), explicit `export:reports` AND `view:autonomous_ops` checks via `views.holds` (the guard already requires the view permission), refuse `tenant == PLATFORM_TENANT_ID`. Zero rows -> `204` with `X-Export-Total: 0` and no body (the dialog shows the blue block; no empty file, no daily-allowance count). Headers: `Content-Disposition`, `X-Export-Rows` (rows in the file; `export_controls` reads exactly this) [VERIFIED: `export_controls.py:136` `if k.lower() == b"x-export-rows" and v.isdigit():`], `X-Export-Total`, `X-Export-Truncated: true` when cut. `X-Export-Truncated` is already in the CORS `expose_headers` [VERIFIED: `app_middleware.py:290`]; add `X-Export-Rows` and `X-Export-Total` there (same file, uncommitted WIP) so a cross-origin UI can read them. `exportReport` does not expose headers, so add a sibling call in `services/autonomousOpsReporting.ts` (UI-SPEC open item 3); the audit-log precedent `exportItamAssetsCsv` already returns `{ truncated }` from `X-Export-Truncated` [VERIFIED: `services/apiService.ts:5764-5774`].
- Registry entry: add `"Autonomous Ops Activity": ("view:autonomous_ops",)` to `REPORT_PERMISSIONS` and an early branch before `service = ExportService()`:
  ```python
  if type == AO_REPORT:
      if is_admin or tenant_id in (None, "platform-admin"):      # staff with no organization context must not leak the cross-tenant path
          raise HTTPException(status_code=403, detail="Open an organization in Tenants, then export from its Autonomous Ops screen.")
      result = await ao_export.build(get_database(), tenant_id, bucket="all", days=30, fmt=format, caller=user)
  ```
  The branch must run **before** `set_tenant_id("platform-admin")`/`tenant_id = None` are applied for admins, and must not reuse `service.fetch_rows` (whose `_fetch_data` has no `Autonomous Ops Activity` case and would return `[]`). Keep the edit small because the file is user WIP (Pitfall 2). Zero rows on the registry path: return a header-only CSV / summary-only PDF (the existing `exportReport` helper would otherwise download an empty file for a 204).
- **Audit (D-12).** The middleware's generic `data.export` event carries only path/bytes/rows [VERIFIED: `export_controls.py:95-97` `await audit_ledger.event("data.export", who.get("tenantId") or "platform-admin", actor=..., path=path, bytes=size, rows=rows)`; path excludes the query string], so add an explicit event like the audit-log export does [VERIFIED: `audit_endpoints.py:105-112` `audit_ledger.event("export.audit_log", ..., actor={...}, ip=..., rows=len(rows), filters={...})`]: `audit_ledger.event("autonomous_ops.export", tenant_id, actor={"email": user.username, "role": user.role, "tenantId": ...}, outcome="success", ip=..., format=fmt, bucket=bucket, days=days, rows=shown, total=total, truncated=truncated)`. Also extend `EXPORT_PATHS` in `backend/export_controls.py:20` with `|autonomous-ops/export` so the daily allowance, bulk-export DLP incident and the generic audit apply to the dedicated route (the regex is anchored on `^/api/(...)$`).
- **DLP**: call `dlp_service.scan_export(rows, tenant_id)` on the built rows before rendering; on a blocking finding answer 403 exactly like the registry route does.
- **Injection**: pass every CSV text cell through `itam_data_service.sanitize_csv_cell`; escape every PDF cell with `xml.sax.saxutils.escape` before `Paragraph`. Targets, hosts and ticket titles come from agents and requesters (Pitfall 3).
- **Cap note in the file** (UI-SPEC R4): a final CSV row `Note` / sentence, and the PDF summary page states it.

### Pattern 6: Shadow lift gate and go-live records (Q5, D-14..D-16)

**Today.** `put_shadow` [VERIFIED: `backend/autonomous_ops_platform_endpoints.py:217-236`] runs `settings.set_shadow(db, tenant, body.shadow, actor=...)` after `_real_tenant`; `set_shadow` [VERIFIED: `autonomous_ops/settings.py:209-215`] only does `update(db, tenant_id, {"shadow": shadow}, actor=actor)` (sets `updatedAt`/`updatedBy`). It writes **no audit event of its own**; the generic `AuditMiddleware` records the PUT with the route *template* and body *keys* only (no tenant id value, no value of `shadow`) [VERIFIED: `audit_middleware.py` docstring lines 1-12 "the route template as the action ... the top-level keys of a JSON body. Body values are never stored"]. So the lift must add its own audit event (`autonomous_ops.shadow_lifted` / `shadow_restored` in the **tenant's** chain with the evidence) and the platform route should require an interactive session (already: `_require_interactive_session`).

**Server gate** (in `put_shadow`, only when the request lifts, i.e. `body.shadow is False` and the stored flag is currently `True`): compute `golive.lift_blockers(db, tenant)`:
- `checks_missing` when fewer than 5 distinct check ids have a record (return `recorded`/5);
- `no_shadow_records` when the tenant has zero `state == "shadow"` rows; `days_short` when `daysObserved < 7`;
- `unreadable` when the observation query fails (fail closed).
Any blocker -> `HTTPException(409, detail=<sentence>)` with a structured `reasons` list (codes + numbers) so the UI words them; `set_shadow` is not called. Turning shadow **on** is never gated; a repeat lift when already lifted is a no-op that skips the gate. The 409 detail is plain text so `failure()` in `autonomousOpsApi.ts` (reads `body.detail` as a string) shows it; carry the codes in a sibling key if `detail` stays a string. The deployment-wide switch does not block (R10); GET reports it so the UI can show the blue note (`settings.master_shadow()` [VERIFIED: `settings.py:111-117`]).

**Days of shadow records (D-16).** Recommendation `[ASSUMED]` (A5): `daysObserved` = whole UTC days between the tenant's **first** shadow-state row and now, requiring at least one row; `wouldHaveDone` = count of `state == "shadow"` rows. Both are index-served by `tenant_state_created` (`find({tenantId, state:"shadow"}).sort(createdAt, 1).limit(1)`, `count_documents`). The alternative ("distinct UTC days that hold a shadow row") is stricter and literally "days of shadow records" but can never pass for a legitimately quiet tenant; the user should pick (Open Question 1).

**Checklist storage.** New append-only collection `autonomy_golive_checks`: `{id, checkId, note, recordedBy: {username, display}, recordedAt}`, index `(checkId, recordedAt -1)`. Module exposes insert + read only (a structural test asserts no `update`/`delete` call names the collection, the style of `test_autonomous_ops_structural.py`). Latest record per check = `$group` with `$first` after a `recordedAt` sort. Checks are **platform-wide** (five ids, not per tenant), matching "0 of 5 checks recorded" and "Record all 5 go-live checks first (3 of 5 recorded)": ids `firewall_round_trip`, `reboot_gate`, `watchdog_stop_start`, `alert_delivery`, `live_stop_drill`. Route `POST /api/platform/autonomous-ops/golive/checks/{check_id}` with `check_id: Literal[...]` and body `note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=500)]` (R9). Each record writes `audit_ledger.event("autonomous_ops.golive_check_recorded", PLATFORM_TENANT_ID, actor=..., checkId=..., note=...)`. Add `autonomy_golive_checks` to `PROTECTED_COLLECTIONS` (`autonomous_ops/__init__.py:32`) so no retention path can ever delete the evidence; that makes `tests/test_autonomous_ops_ledger.py:327` (`assert PROTECTED_COLLECTIONS == {"autonomy_actions", "autonomy_settings", "autonomy_never_touch"}`) fail, so update that assertion in the same plan (the retention tests iterate `NEVER_DELETED` generically). Do not add `autonomy_digests` (not evidence).

**Platform routes.** `GET /api/platform/autonomous-ops/golive` -> `{checks: [5 x {id, recorded, recordedBy, recordedAt, note}], recordedCount, organizations: [{id, name, shadow, daysObserved, wouldHaveDone, canLift, reasons[]}], masterShadow}`. "Organizations" = tenants with `view:autonomous_ops` ticked = `sweep._ticked_tenants` (R12). Both routes use `_require_platform_autonomy_control` + `_require_interactive_session` [VERIFIED: `autonomous_ops_platform_endpoints.py:46-52`, `_require_platform_autonomy_control`], which only owners pass. **Platform Support never holds `control:platform_autonomous_ops`** (it is in `PLATFORM_ONLY_PERMISSIONS`, and `platform_support`'s default list contains `view:autonomous_ops` but not it, nor `export:reports`), so the UI-SPEC row "Platform Support: Going live read-only" cannot occur: the card is Super Admin only (Open Question 6). Put these routes in a new module `autonomous_ops_golive_endpoints.py` registered beside `autonomous_ops_retention_endpoints` in `router_registry.py:352`, and add it to the module whitelist in `tests/test_catalogue_slice_autonomous_ops.py` (the `record["module"] in (...)` tuple around line 97) and, for the shadow gate itself, edit `put_shadow` in place (the file is 292 lines).

### Pattern 7: Stop drill (Q6, D-13)

What each actor's stop check is today (all read the stop fresh, nothing cached):

| Actor | Stop check | Existing test |
|-------|-----------|---------------|
| Gate (every new decision) | `gate._step_platform_stop` (`gate.py:142-151`) and `gate._stopped` (`gate.py:378-387`: "Anything unreadable counts as stopped (fail closed)") | `test_autonomous_ops_gate*.py` |
| Security-response sweep | `sweep.tick` returns on an active platform stop and skips a stopped or Off tenant (`sweep.py:66-77`) | `test_autonomous_ops_sweep.py::test_the_platform_stop_makes_the_pass_do_nothing`, `::test_an_unticked_off_or_stopped_tenant_gets_nothing` |
| Queued instructions / response tasks | `delivery` hold-back + `stop.press` bulk `cancel_undelivered` (`stop.py:181-210`) | `test_autonomous_ops_stop.py` (tracer, platform, response tasks, unreadable stop) |
| Pending approvals | `approvals.approve`: `if await gate._stopped(db, tenant_id): return {"status": "stopped"}`; deny/undo allowed | `test_autonomous_ops_approvals.py` |
| Patch rollouts | controller marks a running rollout `stoppedSince`, makes no decision/refused row, settles results and reverts (`rollout/controller.py:38-52, 298-317, 342-346`) | `test_patch_rollout_shadow_stop.py` (tenant and platform scope, re-offer after clear) |
| AI ticket replies | desk intake queues no job when stopped (`service_desk/intake.py:66-73, 103`); pipeline hands off quietly with `desk_stopped` (`service_desk/pipeline.py:52-79`) | `test_service_desk_intake.py`, `_worker.py:205`, `_pipeline.py:210`, `_gate.py:100-113` |
| Retention | **not paused by design** ("Retention is not an autonomous action, so the platform stop does not pause it", `retention_job.py:259-262`) | `test_retention_job.py:431` `test_the_platform_stop_does_not_pause_retention` |
| Watchdog restarts | paused by D-11 (STOP file / DB / cache); checks and pages continue | `test_watchdog_sync.py` (three-source stop), `_watchdog_restart_world.py` |

Each actor is covered in isolation, **no single test drives them together**. The missing artifact is one suite (`test_autonomous_ops_stop_drill.py`) that builds one hermetic world per scope (a ticked tenant `t1` with shadow off, an agent, a rollout, a desk ticket, queued stamped instruction, an `awaiting_approval` card), presses the **platform** stop and then a **tenant** stop through the real `stop.press`, and asserts the five criterion-4 items in one place, plus: undo/compensate still flow (`STOP_EXEMPT_KINDS`), retention keeps running (documented exception), nothing is written to an agent queue, a second tenant is unaffected by a tenant stop, and after `stop.clear` the frozen work resumes without a flood (rollout re-offered as a new attempt, no stale card fires). Reuse `tests/autonomy_support.py` (`seed_tenant`, `seed_agent`, `seed_platform_stop`), `tests/rollout_support.py`, `tests/service_desk_support.py`.

### Pattern 8: Two-tenant contract tests (D-17)

Existing cross-tenant coverage is per-feature (e.g. `test_autonomous_ops_approvals.py:128` `cross_tenant_target`, `test_retention_job.py:259` uptime rollups); **none is a per-loop contract**. Add `test_autonomous_ops_two_tenant.py` with one test per loop, each seeding `t1` and `t2` with the same-shaped data and running the real loop entry point, then asserting every row, instruction, notice and counter lands only under its own `tenantId`: security response (`sweep.tick`), patch rollouts (`rollout.controller.tick` / `loop.run_once`), service desk (`service_desk.worker` pass), retention (`retention_job.run_all`), plus the two new reporting surfaces (statistics, export, digest: tenant A's rows never appear in B's numbers, file, or notice). Hermetic = the private mongod via `tests/_mongo_test_db.mongo_db` (never 27017).

### Anti-Patterns to Avoid
- **Calling `notify.notify` for the digest:** pages the on-call channel and copies the digest into the platform feed (Pattern 4).
- **Building the export on the user's uncommitted export files without a commit checkpoint:** reproduces the Phase 87 verification gap (Pitfall 2).
- **Summing simulation rows into any real column or headline number** (locked in D-07/D-08, UI-SPEC "simulation marks").
- **Gating shadow lift only in the UI** (CONTEXT specifics) or gating shadow-on.
- **Ambient tenant ContextVar** in any new module: every filter and insert names `tenantId` on the raw handle (`scope.raw`), as the package does.
- **Importing an LLM client** anywhere under `autonomous_ops/` (structural test `test_no_llm_on_the_autonomous_path`).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| One runner at a time across workers | a bespoke lock | `distributed_lock.lock_with_renewal` with the `SimpleNamespace(_db=raw(db))` shim | Handles expiry, renewal, loss signal |
| Once-per-day-per-tenant | in-memory "last sent" flag | unique index `(tenantId, day)` claim doc | Survives restart and multiple workers |
| Tenant admins only | filtering recipients in code | `_post_in_app` with `audience: tenant_admins` | `reader_filter` enforces it on every read route (`test_notification_audience_structure.py` scans for bypasses) |
| "Waiting for approval" | a second definition | `incident_views._waiting_filter(now)` | One definition keeps digest = screen |
| Rows as the screen shows them (names, D-25) | re-deriving labels | `views.present_row` + the extracted filter | Tenant never sees which platform person acted |
| CSV formula safety | own escaping | `itam_data_service.sanitize_csv_cell` | CWE-1236 handled once |
| PDF text safety | raw strings into `Paragraph` | `xml.sax.saxutils.escape` | reportlab parses mini-markup; `<` or `&` in a ticket title breaks or alters the page |
| SMTP config lookup | env vars | `_resolve_smtp_config` + `email_service.send_email` | Tenant/platform config precedence already solved (Phase 87) |
| Audit of an export | own log | `audit_ledger.event` (hash-chained, spools on failure) | `audit_endpoints.export_audit_logs` is the pattern |

**Key insight:** every hard part (isolation, audience, locking, audit, escaping) already has one owner in this repo; Phase 86's risk is wiring them correctly and registering the new files in the copy gate, not inventing anything.

## Common Pitfalls

### Pitfall 1: The digest leaks to on-call and the platform feed
**What goes wrong:** `notify.notify` -> `post_to_recipients` posts to `platform-admin` first and `oncall.enqueue` pages the channel.
**How to avoid:** `_post_in_app` with the tenant-admin audience only. **Warning sign:** a `notifications` row with `tenantId: platform-admin` and `metadata.event == autonomous_ops.daily_digest`, or an `oncall_outbox` row. Test both are absent.

### Pitfall 2: Export work rests on uncommitted user files (highest planning risk)
**What goes wrong:** At HEAD `git show HEAD:backend/export_report_endpoint.py | grep -c REPORT_PERMISSIONS` is `0`; `git ls-files backend/export_controls.py backend/email_utils.py` is empty; `git show HEAD:backend/app_middleware.py | grep -c ExportControl` is `0`. `git status` shows ` M backend/export_report_endpoint.py`, ` M backend/export_service.py`, ` M backend/app_middleware.py`, ` M backend/dlp_service.py`, ` M backend/reporting_endpoints.py`, ` M backend/tests/test_audit_export.py`, `?? backend/export_controls.py`, `?? backend/email_utils.py`. The live backend runs from the working tree, so UAT can pass while a clean checkout fails (Phase 87, `422af6095`, verification `gaps_found`).
**How to avoid:** the first plan that touches these files opens with a `checkpoint:decision` (commit the export set as one user-approved commit, or commit only the Phase 86 hunks as 87 did with `git apply --cached --unidiff-zero`), and the phase verification runs on a `git archive` snapshot (needs `pytest.ini` copied, or every async test fails). The structural tests also scan tracked files only, so untracked new files are not checked until committed.

### Pitfall 3: Attacker-controlled text in files
**What goes wrong:** targets, hostnames and ticket titles flow into CSV (formula injection when a cell starts with `=`, `+`, `-`, `@`, tab, CR) and into reportlab `Paragraph` (markup). **How to avoid:** `sanitize_csv_cell` and `escape` on every cell; test with `=HYPERLINK(...)` and `<b>` / `&` values.

### Pitfall 4: Double digests and silent loss
**What goes wrong:** keying idempotency on `notifications` (30-day retention) or on process memory; or recomputing quiet days every wake. **How to avoid:** claim doc (Pattern 4), written for quiet days too; `ensure_indexes` inside the loop because migration 035 may not have run.

### Pitfall 5: SMTP "configured" test is wrong
**What goes wrong:** `email_utils.send_email_async` defaults `SMTP_HOST` to `localhost` and tries it. **How to avoid:** `_resolve_smtp_config(...) is not None`; call it under `tenant_scope` (it reads `db.smtp_config` via the wrapper); `wait_for` around each send; a failure only logs.

### Pitfall 6: A day with failed or refused work only is silent
Locked UI-SPEC has no failed group, so the digest stays quiet. Not a bug; document it so nobody "fixes" it (Open Question 3).

### Pitfall 7: `finishedAt` is the latest terminal time
An `executed` row later moved to `verified` is re-dated; counted once per digest (in the window of its last terminal move). Rare edge (verify follows within minutes): a row that straddles the 07:00 boundary can appear in two consecutive digests' "ran". Acceptable; do not chase it.

### Pitfall 8: Service-desk hand-offs look like "Done"
`record_desk_event` writes `ticket_handoff` rows as `state: "executed"` (`ledger.py:235-250`), so they land in Done. Keep them visible under their own rule (`service_desk:handoff`) but give them 0 minutes (never "time saved"), and say so in the glossary if shown (Open Question 4).

### Pitfall 9: The UI-SPEC's firewall example cannot work
The check-form helper example "Blocked 203.0.113.9, the firewall refused it" uses TEST-NET-3, which the agent refuses as non-global [VERIFIED: `agent-install/omni-agent-rs/src/capabilities/net_safety.rs:34-36` "Every network that is not on the public internet ... 192.0.2/24, 192.168/16, 198.18/15, 198.51.100/24, 203.0.113/24"]. The go-live document and the helper text must name a real public address the operator controls.

### Pitfall 10: Tests pointing at the live mongod
`conftest._drop_test_database` connects to `MONGODB_URL` or `MONGO_URI` else `mongodb://localhost:27017` at session end [VERIFIED: `backend/tests/conftest.py:37`]; `tests/_mongo_test_db.py` uses `MONGO_TEST_URL` else 27017. Always set **all three** to the private mongod. A skipped DB test did not run (the fixture skips when unreachable).

### Pitfall 11: Copy gate registration is three-sided
`shared/autonomous-ops-banned-terms.json` `files`/`directories`, `EXPECTED_FILES` + `EXPECTED_DIRECTORIES` in `backend/tests/test_autonomous_ops_copy.py` (lines 24, 221) and `EXPECTED_FILES`, `EXPECTED_DIRECTORIES` and the literal `FRONTEND_DIRECTORIES` list in `src/__tests__/autonomousOpsCopy.test.ts` must all change together or the "agreed list" tests fail. `backend/autonomous_ops/` itself is **not** a scanned directory (only `backend/autonomous_ops/rollout` is), so a new `backend/autonomous_ops/reporting` directory must be added; the two top-level endpoint modules and the go-live doc go in `files`.

## Code Examples

### Claim then send (idempotent digest)
```python
# Pattern: retention_job.run_once (lock) + unique-index claim. Source: backend/retention_job.py:260-272, distributed_lock.py
from pymongo.errors import DuplicateKeyError
async def _claim(db, tenant_id: str, day: str, now) -> bool:
    try:
        await raw(db).autonomy_digests.insert_one(
            {"tenantId": tenant_id, "day": day, "state": "claimed", "claimedAt": now})
        return True
    except DuplicateKeyError:
        return False                      # sent, quiet, or claimed by another runner
```

### Server-side lift gate
```python
# in put_shadow, after _real_tenant(...) and before set_shadow
if body.shadow is False and (await settings.load(db, tenant)).shadow is True:
    blockers = await golive.lift_blockers(db, tenant)      # [] when allowed
    if blockers:
        raise HTTPException(status_code=409, detail=golive.blocker_sentence(blockers))
out = await settings.set_shadow(db, tenant, body.shadow, actor=actor)
await audit_ledger.event("autonomous_ops.shadow_lifted" if body.shadow is False else "autonomous_ops.shadow_restored",
                         tenant, actor={...}, daysObserved=..., wouldHaveDone=..., checksRecorded=5)
```

### CSV and PDF cell safety
```python
from itam_data_service import sanitize_csv_cell
from xml.sax.saxutils import escape
csv_row = [sanitize_csv_cell(v) for v in values]
pdf_cell = Paragraph(escape(str(value)), cell_style)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Per-tenant export via `ExportService._fetch_data` | `fetch_rows` + `render` split with DLP scan between (uncommitted) | user WIP, 2026-11 | New type must fit the split or bypass it with its own builder |
| Notices through `notify.notify` | audience-tagged `_post_in_app` (`plan_notices.announce`, Phase 88) | Phase 85/88 | Digest uses the audience path |
| Hand-rolled "run daily" | retention-style loop + `due()` + distributed lock | Phase 82 | Reuse for digest |

**Deprecated/outdated:** the UI-SPEC role row "Platform Support read-only Going live" (unreachable, Pitfall 9/Open Question 6); the CONTEXT canonical ref to `export_report_endpoint.REPORT_PERMISSIONS` as if committed (it is working-tree only).

## Go-live document outline (Q8): `docs/autonomous-ops-go-live.md`

Add the file to the copy-gate `files` list (docs are in ACTV-08 scope; avoid the unqualified "roll back"). One section per check; each states prerequisite, steps, what to record in the note. Sources are the Phase 81-85 Manual-Only tables.

| # | Check | Prerequisites | Steps and expected result | Source |
|---|-------|---------------|---------------------------|--------|
| 1 | Firewall round-trip | A test tenant (shadow off, level Undoable-auto, Autonomous Ops ticked) with a real agent at **2.1.16 or later** (response tokens in `meta.response_actions`); a Linux host with root, and Windows with Defender on | Block a **public** test address you control (non-global addresses are refused by the agent), confirm the host firewall refuses it, then Undo from Activity and confirm it works again; both directions, IPv4 and IPv6 | 83-VALIDATION Manual-Only rows "Firewall round trip", "Publish and roll out agent 2.1.16"; `net_safety.rs:34-36` |
| 2 | Reboot gate | Non-platform tenant with an enrolled Rust agent at **2.1.17 or later** on a disposable host, a rings setup and an open maintenance window | Start a rollout; confirm the Reboot line waits on a card, nothing restarts before approval, one approval covers the stage, post-reboot heartbeat feeds the gate | 84-VALIDATION Manual-Only rows |
| 3 | Watchdog stop and start | Watchdog installed per `deploy/omni-watchdog/INSTALL.md` (memory: not installed on Omniai-copy); never `run-on-ubuntu.sh` | `sudo systemctl stop omni-watchdog.timer`, wait more than 5 minutes (`SILENT_AFTER = 300`, `selfheal.py:57`): Platform health shows **Silent** (and one in-app alarm); `sudo systemctl start omni-watchdog.timer`: **Running** within about two minutes (INSTALL.md section 8). Optionally stop a watched service and see it restart, MongoDB first | 82-VALIDATION Manual-Only rows; INSTALL.md sections 7, 8, 11 |
| 4 | Alert delivery | On-call channel configured in the root-only `/etc/omni-watchdog/oncall.env` | Press **Send test alert** on Platform health; exactly one alert arrives and resolves; the "no working channel" banner clears | 82-VALIDATION row "Test alert reaches the real on-call channel"; INSTALL.md section 8 |
| 5 | Live stop drill | A test tenant, a queued stamped instruction, an `awaiting_approval` card, a running rollout, a portal ticket with Ollama running (installed 2026-11-10, 127.0.0.1:11434) | **Stop all organizations**: next real agent poll does not deliver the instruction, Approve answers "stopped", rollout shows paused, the ticket is handed to a person (`desk_stopped`), no new automatic decision is recorded; then **Resume all organizations** with a reason and confirm things continue; repeat with a tenant-only stop | 81-VALIDATION row "Platform stop holds back a queued instruction"; 84/85 rows |

Reconcile UI-SPEC R15 wording from the finished document (R15 says the document is the authority). R15 check 3 says "Stop the watchdog service"; the real units are a `oneshot` service run by `omni-watchdog.timer`, so stop the **timer**. The exact in-app trigger for a controlled test block (check 1) and a patch that needs a reboot (check 2) is not recorded in any prior phase artifact; the executor must confirm it with the user (Open Question 5).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Minutes-per-kind values in Pattern 3 (block 10, quarantine 15, restart 10, kill 10, reboot 10, upgrade 10, restore 15, disable 10, rotate key 20, ransomware restore 30, patch install 10 per host; isolate 15 and answer 8 are the CONTEXT examples) | Pattern 3 | Headline "time saved" over- or understated; user should approve (it is an "Estimate" and fixed in code) |
| A2 | `Refused` column = `refused` + `expired` + `cancelled_by_stop` (denied separate), and the glossary line is widened accordingly | Pattern 1 | Counts disagree with the UI-SPEC glossary wording unless reworded; alternative is to leave expired/cancelled in no column |
| A3 | A rollout install row (one per host and attempt) counts the same minutes as a manual install | Pattern 3 | Many hosts inflate the estimate |
| A4 | Digest idempotency is at-most-once (claim before send); a crash between claim and post loses that day's digest | Pattern 4 | A digest silently missed vs a risk of duplicates if at-least-once were chosen |
| A5 | "Days of shadow records" = whole days from the tenant's first shadow row to now (needs one row), not distinct days with a row | Pattern 6 | Too easy to pass for a tenant with one stale row; or, if distinct days is intended, quiet tenants can never lift |
| A6 | Digest sends the same UTC day only (no multi-day catch-up) and a stop does not suppress it | Pattern 4 | A long outage skips a day's digest |
| A7 | A person-sent or approved action counts toward time saved the same as an automatic one (D-08 literal reading) | Pattern 3 | Estimate includes actions where a person still clicked |
| A8 | Hand-off rows appear as their own rule with 0 minutes and count in Done | Pitfall 8 | Headline Done inflated if hand-offs should be hidden |
| A9 | Digest emails skip entirely when `FRONTEND_URL` is not an http(s) address (invite pattern) | Pattern 4 | Admins get no email on a deployment without `FRONTEND_URL`; in-app still delivered |
| A10 | New `autonomy_golive_checks` joins `PROTECTED_COLLECTIONS`; `autonomy_digests` does not | Pattern 6 | If protected, one existing test assertion must change (listed) |
| A11 | Checks are platform-wide (five records), not per organization | Pattern 6 | If per-org checks were intended the gate and UI copy change |

## Open Questions

> RESOLVED 2026-11-11: 1 -> D-20 (since the first record); 2 -> D-18 (executor commits the 7-file export WIP set first); 3 -> stays quiet (default); 4 -> keep with 0 minutes (default); 5 -> confirm with the user when the go-live document is written; 6 -> Super Admin only (default); 7 -> D-21 (audit event only). A1 -> D-19 accepted.

1. **How is "7 days of shadow records" counted?**
   - What we know: D-16 says "at least 7 days of shadow records", UI shows "5 of 7 days".
   - What's unclear: first-row-to-now span versus distinct days holding a row.
   - Recommendation: span with at least one row (A5). Ask the user to confirm before 86-0x plans the gate.
2. **Who commits the export WIP?** (Pitfall 2) Recommend a `checkpoint:decision` at the start of the export plan: commit the whole set as the user's work, or commit only Phase 86 hunks. The plan must not proceed on assumption.
3. **Failed or refused-only days.** The digest stays quiet (UI-SPEC has three groups). Recommend leaving as locked and noting it in the plan so nobody adds a group.
4. **Hand-offs in the statistics.** Keep as their own rule with 0 minutes, or hide from Done? Recommend keep (honest), 0 minutes.
5. **Live trigger for checks 1 and 2.** No prior phase records a repeatable operator trigger for a controlled test block or a reboot-needing patch; the go-live document author must confirm both with the user on the server (cannot be verified from the repo).
6. **UI-SPEC Platform Support row.** Support cannot reach platform routes (no `control:platform_autonomous_ops`), so "read-only Going live" is moot; recommend recording the Super Admin-only reality in the plan and not adding a read-only permission.
7. **Control row for lift/restore.** Optional: also write a `control` row (`shadow_lifted`/`shadow_restored`) so the tenant's Activity shows it; needs labels in `messages.CONTROL_LABELS`, the `AutonomousOpsControlEvent` union and the row chip. Recommend audit event only (smaller scope) unless the user wants tenant visibility.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python venv | backend tests | yes | 3.12.3 [VERIFIED: `backend/venv/bin/python --version` output in this session] | none needed |
| Private mongod on 127.0.0.1:27998 | DB-semantics tests, drills, contract tests | yes, **already listening** (seen by `ss -ltn`; started outside this session) | `/usr/bin/mongod` exists | start per 85-VALIDATION: `GLIBC_TUNABLES=glibc.pthread.rseq=1 /usr/bin/mongod --dbpath <scratch> --port 27998 --bind_ip 127.0.0.1 --fork --logpath <scratch>/m.log --pidfilepath <scratch>/m.pid` (kernel 7.0 needs the GLIBC tunable, memory `mongodb-kernel-7-dropin.md`) |
| Live mongod 127.0.0.1:27017 | nothing | listening, **must not be touched** | n/a | n/a |
| Node + vitest | UI tests | yes (node v20.20.2, `node_modules/.bin/vitest`) | vitest ^5.0.0 | n/a |
| reportlab | PDF | yes | 5.0.1 | n/a |
| SMTP / `FRONTEND_URL` | digest email | unknown/unset on this VM (memory: SMTP unset; `.env` not readable) | n/a | in-app only; tests mock SMTP |
| Watchdog installed, on-call channel, agent 2.1.16/2.1.17+, Windows PC | live checklist only | no (live, operator steps) | n/a | the user walks them; not needed for automated tests |

**Missing with no fallback for automated work:** none. Whether the mongod on 27998 belongs to another running session is unknown; tests create uniquely named throwaway databases and drop them.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 + pytest-asyncio 1.4.0 (`asyncio_mode = auto`), vitest ^5.0.0 |
| Config file | `pytest.ini` (repo root; needed on any snapshot), `backend/tests/conftest.py`, `package.json` |
| DB fixture | `backend/tests/_mongo_test_db.py` (`mongo_db`, uniquely named throwaway database, skips if unreachable); helpers `tests/autonomy_support.py`, `tests/rollout_support.py`, `tests/service_desk_support.py`, HTTP harness `tests/_autonomous_ops_http.py` (`Api`, `api` fixture) |
| Quick run command | `MONGO_TEST_URL=mongodb://127.0.0.1:27998 MONGODB_URL=mongodb://127.0.0.1:27998 MONGO_URI=mongodb://127.0.0.1:27998 backend/venv/bin/python -m pytest backend/tests/test_autonomous_ops_stats.py backend/tests/test_autonomous_ops_digest.py backend/tests/test_autonomous_ops_copy.py -q -p no:cacheprovider` |
| Full suite command | the same prefix with `backend/tests/test_autonomous_ops_*.py backend/tests/test_catalogue_slice_autonomous_ops.py backend/tests/test_catalogue_route_parity.py backend/tests/test_route_auth_baseline.py backend/tests/test_patch_rollout_*.py backend/tests/test_service_desk_*.py backend/tests/test_retention_job.py backend/tests/test_audit_export.py backend/tests/test_notification_*.py -q -p no:cacheprovider` (run from the repo root; known pre-existing failure: `test_catalogue_route_parity.py::test_ledger_ratchets`, 9 named routes, predates the phase); UI: `npx vitest run src/__tests__` and `npm run build` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ACTV-04 | Quiet day sends nothing; shadow-only day sends digest with `0 ran, 0 undone, 0 waiting` + simulation section; sections capped at 10; counts exact | unit (pure text) + real-Mongo | `pytest backend/tests/test_autonomous_ops_digest.py -q` | Wave 0 |
| ACTV-04 | Tenant-admin audience only: no platform-feed row, no on-call outbox row, not broadcastable | real-Mongo | same file | Wave 0 |
| ACTV-04 | One digest per tenant per UTC day across repeated `run_once`, two concurrent runners, simulated restart; `due()` false before 07:00 and true after until claimed | real-Mongo, injected `now` | same file | Wave 0 |
| ACTV-04 | Email only when `_resolve_smtp_config` returns config; failure or hang never blocks the in-app notice; CR/LF stripped from subject | mocked SMTP | same file | Wave 0 |
| ACTV-05 | State->column map (approved via `approval.approver`, denied/refused/undone/failed), shadow separate, control/platform_health excluded, window 7/30/90, tenant scoped | real-Mongo | `pytest backend/tests/test_autonomous_ops_stats.py -q` | Wave 0 |
| ACTV-07 | Minutes table covers every `registry.ACTIONS` command + `ticket_handoff` (completeness test), counts only executed/verified, 0 for shadow/undone/handoff, total = sum of subtotals, labelled estimate in payload | unit + real-Mongo | same file | Wave 0 |
| ACTV-06 | CSV/PDF content, summary page, state word `Simulation`, 5,000 cap with `X-Export-Total`/`X-Export-Truncated`/note row, zero rows -> 204, filters (bucket, days) | HTTP + real-Mongo | `pytest backend/tests/test_autonomous_ops_export.py -q` | Wave 0 |
| ACTV-06 | Needs `export:reports` AND `view:autonomous_ops`; registry type refuses Super Admin/Support with no organization; no cross-tenant leak; audit event with who/filter/rows/format; DLP block honoured; `EXPORT_PATHS` matches new path; CSV formula and PDF markup injection | HTTP matrix | same file | Wave 0 |
| Shadow gate | Lift refused (409) with <5 checks or <7 days or no records or unreadable; allowed when met; shadow-on never gated; repeat lift no-op; non-Super Admin 403; audit event written | HTTP + real-Mongo | `pytest backend/tests/test_autonomous_ops_golive.py -q` | Wave 0 |
| Checklist | Five ids only, note 10-500, append-only (latest shown, earlier kept), audit per record, structural no-update/delete, `PROTECTED_COLLECTIONS` updated | HTTP + structural | same file | Wave 0 |
| Success criterion 4 | One drill suite: platform stop and tenant stop across gate/sweep, queued instructions, approvals, rollouts, desk replies; undo exempt; retention keeps running; other tenant unaffected; clean resume | real-Mongo integration | `pytest backend/tests/test_autonomous_ops_stop_drill.py -q` | Wave 0 |
| Success criterion 5 / D-17 | Per-loop two-tenant contract (sweep, rollout controller, desk worker, retention) + statistics/export/digest isolation | real-Mongo | `pytest backend/tests/test_autonomous_ops_two_tenant.py -q` | Wave 0 |
| Migration 035 | Indexes only (`tenant_finished`, `digest_once_per_day`, go-live index), second run changes nothing | real-Mongo | `pytest backend/tests/test_migration_035_activity_reporting.py -q` (pattern: `test_autonomous_ops_migration.py`) | Wave 0 |
| ACTV-08 | New files/dirs registered; no banned term in new code, doc and UI | static | `pytest backend/tests/test_autonomous_ops_copy.py -q`; `npx vitest run src/__tests__/autonomousOpsCopy.test.ts` | exists (needs list edits) |
| Catalogue | New routes mounted/guarded; platform module whitelisted | static | `pytest backend/tests/test_catalogue_slice_autonomous_ops.py backend/tests/test_catalogue_route_parity.py -q` | exists (needs edits) |
| UI | StatsCard (period, summary, estimate chip, simulation line, empty/error), per-rule table, ExportDialog (format, period, cap note, zero rows, 403), ReportExportCard disabled reasons, GoLiveCard (5 checks, record form, gate reasons, typed-name confirm, shadow-back dialog) | vitest | `npx vitest run src/__tests__/autonomousOpsStats.test.tsx src/__tests__/autonomousOpsGoLive.test.tsx` | Wave 0 |

Name new backend files `test_autonomous_ops_*.py` so the existing phase globs pick them up.

### Sampling Rate
- **Per task commit:** the task's new test file plus `test_autonomous_ops_structural.py`, `test_autonomous_ops_copy.py` (prefixed with the 27998 env).
- **Per wave merge:** the full suite command above plus touched vitest files.
- **Phase gate:** full suite green (except the known `test_ledger_ratchets` names), `npx vitest run src/__tests__`, `npm run build`, run again on a `git archive` snapshot with `pytest.ini`, before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] The six backend test files above plus the migration test and the two vitest files; none exist.
- [ ] Edits to existing tests: `test_autonomous_ops_copy.py` and `autonomousOpsCopy.test.ts` (lists), `test_autonomous_ops_ledger.py:327` (protected set), `test_catalogue_slice_autonomous_ops.py` (mount dict and platform module tuple).
- [ ] No framework install needed.

## Security Domain

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Interactive session for platform writes (`_require_interactive_session`); API keys cannot record checks or lift shadow |
| V3 Session Management | no (unchanged) | n/a |
| V4 Access Control | yes | `export:reports` AND `view:autonomous_ops` (`views.holds`); platform routes `control:platform_autonomous_ops` (`has_platform_permission`); `views.resolve_tenant` (a tenant role never names another tenant); registry type refuses staff without an organization |
| V5 Input Validation | yes | pydantic `Literal` for format/bucket/check id, `days` limited to {7,30,90,all}, bounded `note` (10-500), `tenant_id` max length (`views.TENANT_ID_MAX`) |
| V6 Cryptography | no | none added (SMTP secrets stay encrypted in `emailConfig`) |
| V7 Logging/Audit | yes | `audit_ledger.event` for export, check record, lift/restore; never log note text or SMTP secrets at info |
| V8 Data Protection | yes | `dlp_service.scan_export` on rows; tenant-scoped queries; no secret in any file |
| V13 API | yes | rate/size: 5,000-row cap, daily export allowance via `ExportControlMiddleware.EXPORT_PATHS` |

### Known Threat Patterns
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cross-tenant read via the registry's Super Admin path (`set_tenant_id("platform-admin")`, `tenant_id=None`) | Information Disclosure | Refuse the AO type for staff/no-organization before elevation; statistics/export always filter `tenantId` |
| CSV formula injection (CWE-1236) in targets/titles | Tampering | `sanitize_csv_cell` |
| PDF markup injection / broken page | Tampering | `escape` before `Paragraph` |
| Email header injection via organization name in subject | Tampering | strip CR/LF from subject parts |
| Lifting shadow by calling the API directly | Elevation of Privilege | Gate enforced inside `put_shadow`; Super Admin + interactive session only |
| Forged or overwritten go-live evidence | Repudiation | Append-only collection + audit event per record + protected collection |
| Digest reaching non-admin users or the platform feed | Information Disclosure | `audience: tenant_admins` via `_post_in_app` only (host details are sensitive, spec C3 comment in `notification_audience.py`) |
| Stop bypass by new loops | Elevation of Privilege | The digest and statistics are read-only; nothing new writes an agent queue (structural tests stay green; no LLM import) |
| Mail/SMTP hang stalling the loop | Denial of Service | `asyncio.wait_for` per send; the lock TTL renews |

## Sources

### Primary (HIGH confidence)
- Repository files opened this session (cited inline with path and line): `backend/autonomous_ops/{__init__,ledger,decision_row,notify,scope,registry,views,settings,stop,approvals,gate,sweep,incident_views,selfheal}.py`, `backend/autonomous_ops_{endpoints,platform_endpoints,retention_endpoints}.py`, `backend/catalogue_mounts_autonomous_ops.py`, `backend/router_registry.py`, `backend/export_{report_endpoint,service,service_pdf,controls}.py`, `backend/retention_job.py`, `backend/distributed_lock.py`, `backend/app_startup.py`, `backend/app_middleware.py`, `backend/pending_agents.py`, `backend/plan_notices.py`, `backend/notification_audience.py`, `backend/email_service.py`, `backend/email_utils.py`, `backend/auth_password_reset_endpoints.py`, `backend/partner_invites.py`, `backend/audit_ledger.py`, `backend/audit_middleware.py`, `backend/audit_endpoints.py`, `backend/itam_data_service.py`, `backend/dlp_service.py`, `backend/rbac_defaults.py`, `backend/auth_roles.py`, `backend/migrations/{runner,024,032,034}*.py`, `backend/service_desk/{outcomes,lifecycle}.py`, `agent-install/omni-agent-rs/src/capabilities/net_safety.rs`, `deploy/omni-watchdog/INSTALL.md`, `shared/autonomous-ops-banned-terms.json`, `shared/catalogue-access.json`, `backend/tests/{conftest,_mongo_test_db,_autonomous_ops_http,test_autonomous_ops_copy,test_autonomous_ops_stop,test_patch_rollout_shadow_stop,test_retention_job,test_catalogue_slice_autonomous_ops}.py`, `src/__tests__/autonomousOpsCopy.test.ts`, `components/AutonomousOpsActivity.tsx`, `services/autonomousOpsApi.ts`, `services/apiService.ts`, `.planning/phases/81-85/*-VALIDATION.md`.
- `git status` / `git show HEAD:...` / `git ls-files` for the uncommitted-export finding (run this session).
- `backend/venv/bin/python -m pip list`, `reportlab.Version`, `ss -ltn` (environment).

### Secondary (MEDIUM confidence)
- Design recommendations built from the above (claim-doc idempotency, state-to-column map, `autonomy_golive_checks` shape): consistent with repo patterns, not externally validated.

### Tertiary (LOW confidence)
- Minutes-per-kind values and the shadow-days definition (Assumptions A1, A5): training-knowledge judgement, user to confirm.

No external documentation lookup was needed (no new library or API); the research-plan/Context7 seam was not used for that reason.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH, nothing new, versions read from the venv.
- Architecture: HIGH for where each thing lives and the stop/loop/lock/audience facts (all read from code); MEDIUM for the chosen designs.
- Pitfalls: HIGH for the uncommitted-export finding (git evidence), the notify leak and the non-global firewall example (code), MEDIUM for the remaining edge cases.

**Research date:** 2026-11-11
**Valid until:** about 2026-11-18 for the export-WIP finding (it changes as soon as the user commits); about 30 days for the rest.
