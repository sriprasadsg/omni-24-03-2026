# Phase 86: Activity Reporting, Hardening & Live Validation - Context

**Gathered:** 2026-11-11
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous); the user accepted every recommended answer in all four areas

<domain>
## Phase Boundary

Operators get a daily digest, per-rule statistics, CSV/PDF export of the activity log and an estimate of operator time saved, and the whole of Autonomous Ops is proven safe end to end before any tenant leaves shadow mode: an automated stop drill across every automatic actor, a two-tenant contract test per automatic loop, and a live-only checklist the Super Admin records in the app. Lifting a tenant's shadow flag gets a Super Admin control for the first time (it was API-only in Phase 81, D-22), gated on that checklist and a minimum observation period.

Requirements: ACTV-04, ACTV-05, ACTV-06, ACTV-07. Depends on Phases 82-85 (the digest, statistics, export and drills cover every automatic actor). All of 82-85 are implemented; 85's last UAT item waits on a Windows PC and does not block this phase.

Not in this phase: changing a tenant's level or maximum level from the UI, editing the never-touch list from the UI (both stay API-only), flipping the deployment-wide `AUTONOMOUS_REMEDIATION_DRY_RUN` switch, restarting anything on the live VM. Naming rule: "Autonomous Ops", never "ASI", "Autopilot", "fully autonomous" or an unqualified "rollback" (ACTV-08 copy check covers new screens and docs).

</domain>

<decisions>
## Implementation Decisions

### Carried forward, not re-decided
- Only a Super Admin lifts a tenant's shadow flag (81 D-03). The deployment-wide switch can only force shadow on; lifting it is the user's step (env change + restart, research D19).
- Every tenant's own shadow flag defaults on (81 D-02); unticked tenants are Off and record nothing (81 D-23).
- In-app notices go through `autonomous_ops/notify.py` -> `pending_agents.post_to_recipients` (tenant admins) and the on-call outbox (Phase 82). `notify` never raises.
- The decision ledger `autonomy_actions` is the source of truth; every row carries `reason.ruleId`, state, origin and shadow marking. Decision records are outside generic retention.
- SMTP, VirusTotal and Gemini keys are unset on this VM; features that need them degrade, they are not bugs.

### Daily digest (ACTV-04)
- **D-01:** Delivered as an in-app notice to each tenant's admins through the existing recipients path, and also by email when SMTP is configured (it is not on this VM, so in-app only here). A failed email never blocks the in-app notice.
- **D-02:** Sent once a day at **07:00 UTC** for every tenant (after the 02:00 retention run and the 02:30 backup). Tenants have no stored time zone; no per-tenant hour setting.
- **D-03:** **Quiet days send nothing:** no digest when nothing ran, nothing was undone and nothing is waiting for approval in the last 24 hours.
- **D-04:** Content: counts for ran / undone / waiting, the first **10** items of each section, and a link to the Autonomous Ops screen. Shadow-mode "would have done" items are a **separate, labelled section** (simulation), never counted as ran.

### Statistics and time saved (ACTV-05, ACTV-07)
- **D-05:** A **Statistics section on the existing Autonomous Ops screen** (no new sidebar item and therefore no new feature switch).
- **D-06:** Window: last **30 days** by default, with a **7 / 30 / 90 day** choice.
- **D-07:** Per rule (`reason.ruleId`): fired, done, approved, denied, undone, failed, refused. Shadow "would have done" counts are a **separate column/series, never mixed** into the real counts.
- **D-08:** Time saved = a **fixed minutes-per-action-kind table kept in code** (for example isolate host 15 min, answer a ticket 8 min), counted **only for actions that really ran and were not undone** (shadow rows and undone rows excluded). Always labelled **"Estimate"** with the method shown on screen. Not editable by tenants or the Super Admin.

### Export (ACTV-06)
- **D-09:** Two entry points over one builder: an **Export button on the Autonomous Ops screen** (CSV or PDF of what the screen shows) and an **"Autonomous Ops Activity" entry in the existing report registry** (`export_report_endpoint.REPORT_PERMISSIONS` / `/api/reports/export`). Both need `export:reports` **and** `view:autonomous_ops`.
- **D-10:** The export follows the **current filters** (bucket and date range), capped at **5,000 rows**, with a visible note when the cap cut rows off.
- **D-11:** The PDF has a **summary page** (counts, the per-rule table, the time-saved estimate labelled as an estimate) followed by the rows.
- **D-12:** Every export is **recorded in the audit log**: who, which filter, how many rows, which format.

### Drills and going live (research D2/D19, success criteria 4-5)
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

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope and research
- `.planning/ROADMAP.md` — "Phase 86" block: goal, 5 success criteria, live-only verification list, "Decisions to settle: D2 and D19"
- `.planning/REQUIREMENTS.md` — ACTV-04..07 (and ACTV-08 copy rule)
- `.planning/research/SUMMARY.md` — D2 (observe-first soak, who lifts shadow), D19 (go-live is the user's step)

### Prior phase decisions that constrain this phase
- `.planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-CONTEXT.md` — D-02/D-03 shadow layers and who lifts, D-14 resume reason, D-22 screen scope, D-23 unticked tenants
- `.planning/phases/82-platform-self-healing-scheduled-retention/82-CONTEXT.md` — watchdog, on-call outbox, retention schedule, live-only steps stay the user's
- `.planning/phases/83-autonomous-security-response/83-CONTEXT.md`, `84-staged-patch-rollouts/84-CONTEXT.md`, `85-first-line-service-desk/85-CONTEXT.md` — the actors the drills and contract tests cover

### Code the phase changes or must respect
- `backend/autonomous_ops/ledger.py` (rows, `counts`, `list_actions`, states), `settings.py` (shadow, `set_shadow`), `stop.py`, `notify.py`
- `backend/autonomous_ops_platform_endpoints.py` (`PUT /tenants/{tenant_id}/shadow`, platform status/actions)
- `backend/export_report_endpoint.py`, `export_service.py`, `export_service_pdf.py` (report registry, CSV/PDF)
- `backend/retention_job.py` (02:00 UTC loop pattern), `backend/app_startup.py` (background task wiring), `backend/email_utils.py`
- `components/AutonomousOps*.tsx` (screen, status card, activity list)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `autonomy_actions` ledger rows already carry `reason.ruleId`, state, origin and shadow marking: per-rule statistics and the digest are aggregations over it.
- `notify.notify` / `pending_agents.post_to_recipients` deliver in-app notices to tenant admins; `email_utils.send_email_async` sends mail when SMTP is configured.
- `export_report_endpoint.REPORT_PERMISSIONS` + `ExportService` give a CSV/PDF registry with export permission checks; `services/apiService.ts` `exportReport(type, format)` downloads from it.
- `retention_job.retention_loop` shows the daily-at-a-fixed-UTC-hour loop pattern started from `app_startup.py`.

### Established Patterns
- Raw Mongo handle with an explicit `tenantId` on every filter (`autonomous_ops/scope.raw`), timezone-aware UTC datetimes, `notify` never raises.
- Platform-only routes live in `autonomous_ops_platform_endpoints.py` and need the platform Super Admin; tenant routes never change shadow.
- Copy check (ACTV-08) runs over Autonomous Ops screens and docs.
- Tests run via `backend/venv/bin/python -m pytest`; never against the live mongod on 27017.

### Integration Points
- New Statistics section + Export button on the Autonomous Ops screen; checklist and Lift control in the platform view (`AutonomousOpsPlatformHealth` / platform status area).
- New report type "Autonomous Ops Activity" in the report registry.
- New background digest loop registered in `app_startup.py`.

</code_context>

<specifics>
## Specific Ideas

- Digest and statistics must never present shadow "would have done" entries as real actions; they are labelled as a simulation everywhere.
- The time-saved figure is always labelled "Estimate" with its method visible.
- The shadow lift gate must be enforced by the server route, not only the button.

</specifics>

<deferred>
## Deferred Ideas

- Per-tenant digest hour or time zone.
- Editable minutes-per-action table.
- UI for changing level / maximum level and editing the never-touch list (still API-only).

</deferred>

---

*Phase: 86-activity-reporting-hardening-live-validation*
*Context gathered: 2026-11-11 (smart discuss, all recommendations accepted)*
