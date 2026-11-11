# Phase 86: Activity Reporting, Hardening & Live Validation - Pattern Map

**Mapped:** 2026-11-11
**Files analyzed:** 36 new/modified
**Analogs found:** 34 / 36

Note on tracking: every analog below was checked against `git ls-files` except those marked WIP. The export registry set (`backend/export_report_endpoint.py`, `export_service.py`, `app_middleware.py`, `dlp_service.py`, `reporting_endpoints.py`, untracked `export_controls.py`, `email_utils.py`) is uncommitted user work that D-18 commits first as its own commit. Excerpts from those files come from the WORKING TREE and are what HEAD will contain after that commit. Line numbers are working-tree numbers and may shift. `backend/tests/test_audit_export.py` is also modified in the working tree.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `backend/autonomous_ops/reporting/__init__.py` | config (constants) | n/a | `backend/retention_job.py` lines 29-40 (constants block) | role |
| `backend/autonomous_ops/reporting/rule_names.py` | utility | transform | `backend/autonomous_ops/messages.py` (code-owned label dicts; read before writing) | role |
| `backend/autonomous_ops/reporting/stats.py` | service | batch/aggregate | `backend/autonomous_ops/ledger.py` `counts` (311-320) | role |
| `backend/autonomous_ops/reporting/digest.py` | service | event-driven | `backend/plan_notices.py` `announce` (30-60) | exact |
| `backend/autonomous_ops/reporting/digest_text.py` | utility | transform | `backend/autonomous_ops/views.py` `present_row` (pure text builders) | role |
| `backend/autonomous_ops/reporting/digest_job.py` | service (scheduler) | batch | `backend/retention_job.py` (`due`, `run_once`, `retention_loop`) | exact |
| `backend/autonomous_ops/reporting/export.py` | service | file-I/O | `backend/audit_endpoints.py` export (95-115) + `itam_data_service.sanitize_csv_cell` | role |
| `backend/autonomous_ops/reporting/export_pdf.py` | service | file-I/O | `backend/export_service_pdf.py` `_generate_pdf` (133+) | exact |
| `backend/autonomous_ops/reporting/golive.py` | service | CRUD (append-only) | `backend/autonomous_ops/ledger.py` (raw-handle inserts, `ensure_indexes`) | role |
| `backend/autonomous_ops_reporting_endpoints.py` | route | request-response | `backend/autonomous_ops_service_desk_endpoints.py` (read first) / `autonomous_ops_endpoints.py` | exact |
| `backend/autonomous_ops_golive_endpoints.py` | route | request-response | `backend/autonomous_ops_platform_endpoints.py` | exact |
| `backend/autonomous_ops_platform_endpoints.py` (edit `put_shadow`) | route | request-response | itself, lines 217-236 | exact |
| `backend/catalogue_mounts_autonomous_ops.py` (edit MOUNTS) | config | n/a | itself, lines 30-34 | exact |
| `backend/router_registry.py` (add `_load`) | config | n/a | line ~352-355 retention endpoints entry | exact |
| `backend/app_startup.py` (edit) | config | event-driven | lines 540-543 retention task | exact |
| `backend/autonomous_ops/__init__.py` (edit `PROTECTED_COLLECTIONS`) | config | n/a | itself, line 32 | exact |
| `backend/autonomous_ops/views.py` (extract `activity_filter`) | utility | CRUD | itself (`list_page`) | exact |
| `backend/export_report_endpoint.py` (edit, post-D-18) | route | request-response | itself, `REPORT_PERMISSIONS` (WIP) | exact |
| `backend/export_controls.py` (edit `EXPORT_PATHS`) | middleware | request-response | itself, line 20 (WIP) | exact |
| `backend/app_middleware.py` (edit CORS expose_headers) | config | n/a | itself, line ~290 (WIP) | exact |
| `backend/migrations/035_activity_reporting.py` | migration | batch | `backend/migrations/034_plan_licensing.py` (item f indexes) | role |
| `services/autonomousOpsReporting.ts` | service | request-response | `services/autonomousOpsApi.ts` (getJson/failure/withTenant) | exact |
| `components/autonomousOpsStats/StatsCard.tsx` | component | request-response | `components/AutonomousOpsStatusCard.tsx` | exact |
| `components/autonomousOpsStats/StatsRuleTable.tsx` | component | transform | `components/AutonomousOpsActivityList.tsx` | role |
| `components/autonomousOpsStats/TimeSavedBlock.tsx` | component | transform | `components/AutonomousOpsStatusCard.tsx` `Cell`/`Notice` | role |
| `components/autonomousOpsStats/ExportDialog.tsx` | component | file-I/O | `components/AutonomousOpsStopDialog.tsx` + `Modal.tsx`; header read per `exportItamAssetsCsv` | role |
| `components/autonomousOpsStats/ReportExportCard.tsx` | component | file-I/O | `components/ReportingDashboard.tsx` `ExportCard` (159-) | exact |
| `components/autonomousOpsGoLive/GoLiveCard.tsx`, `GoLiveChecklist.tsx`, `GoLiveOrganizations.tsx` | component | CRUD | `components/AutonomousOpsResponseSettingsPlatform.tsx` | exact |
| `components/autonomousOpsGoLive/ShadowDialogs.tsx` | component | request-response | `components/AutonomousOpsResponseSettingsDialogs.tsx` | exact |
| `components/autonomousOpsStats/reportingCopy.ts`, `autonomousOpsGoLive/goLiveCopy.ts` | utility | n/a | `shared/autonomous-ops-banned-terms.json` consumers (copy gate) | partial |
| Copy gate files: `shared/autonomous-ops-banned-terms.json`, `backend/tests/test_autonomous_ops_copy.py`, `src/__tests__/autonomousOpsCopy.test.ts` | config/test | n/a | themselves (EXPECTED_FILES/DIRECTORIES) | exact |
| `backend/tests/test_autonomous_ops_stop_drill.py` | test | event-driven | `test_autonomous_ops_sweep.py` + `test_patch_rollout_shadow_stop.py` | role |
| `backend/tests/test_autonomous_ops_two_tenant.py` | test | batch | `test_retention_job.py` (real-Mongo) | role |
| `backend/tests/test_autonomous_ops_digest.py`, `_stats.py`, `_export.py`, `_golive.py` | test | mixed | `test_retention_job.py`, `test_autonomous_ops_sweep.py` | role |
| `src/__tests__/AutonomousOpsStats*.test.tsx`, `GoLive*.test.tsx` | test | n/a | `src/__tests__/AutonomousOpsStatusCard.test.tsx` | exact |
| `docs/autonomous-ops-go-live.md` | doc | n/a | none | none |

## Pattern Assignments

### `backend/autonomous_ops/reporting/digest_job.py` (scheduler, batch)
**Analog:** `backend/retention_job.py` (tracked).

Constants and imports (lines 8-40):
```python
import asyncio, logging, os, time, uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
import retention_gate as gate
from autonomous_ops.scope import raw
LOCK_NAME = "retention_job"; LOCK_TTL_SECONDS = 120; LOCK_RENEW_EVERY = 30
WAKE_EVERY = 300; STARTUP_DELAY = 120; SCHEDULE_HOUR_UTC = 2
_sleep = asyncio.sleep          # indirection so tests can observe and speed up the pauses
```
`due()` (lines 233-239) and `run_once` (lines 260-272): copy exactly, with `SCHEDULE_HOUR_UTC = 7`, `LOCK_NAME = "autonomous_ops_digest"`, and the claim doc (unique `(tenantId, day)`) replacing `last_scheduled_date`:
```python
def due(now, last_scheduled_date):
    now = gate.aware(now).astimezone(timezone.utc)
    if now < now.replace(hour=SCHEDULE_HOUR_UTC, minute=0, second=0, microsecond=0): return False
    return last_scheduled_date is None or last_scheduled_date < now.date()

async with distributed_lock.lock_with_renewal(SimpleNamespace(_db=raw(db)), LOCK_NAME,
        ttl_seconds=LOCK_TTL_SECONDS, renew_every=LOCK_RENEW_EVERY) as handle:
    if not handle.acquired: return None
```
Loop (lines 296-310): `await asyncio.sleep(STARTUP_DELAY)`, `while True: try run_once ... except asyncio.CancelledError: raise; except Exception: logger.error`, `await asyncio.sleep(WAKE_EVERY)`. Registration in `backend/app_startup.py` lines 540-543:
```python
from retention_job import retention_loop as _retention_loop
asyncio.create_task(_safe_bg_task(_retention_loop(), "retention_job"), name="retention_job")
```
Tenant list: `autonomous_ops.sweep._ticked_tenants(db)` (sweep.py lines 55-57). Also copy the self-healing `ensure_indexes`-inside-loop idea from `autonomous_ops/rollout/loop.py` (`_indexes_ready`).

### `backend/autonomous_ops/reporting/digest.py` (service, event-driven)
**Analog:** `backend/plan_notices.py` lines 30-60. Do not use `autonomous_ops/notify.py` (posts to the platform feed and on-call).
```python
import pending_agents
await pending_agents._post_in_app(
    _raw(db), tenant_id, title, message, "info",
    {"event": event, "tenantId": tenant_id, "audience": pending_agents.TENANT_ADMIN_AUDIENCE, **details})
```
Wrap in `try/except Exception: logger.warning(...)` (never raises). Email: `_resolve_smtp_config(db, tenant)` from `auth_password_reset_endpoints.py` (committed `422af6095`), called under `scope.tenant_scope(tenant_id)`; `email_service.send_email(...)` inside `asyncio.wait_for(..., 30)`. Waiting count: `incident_views._waiting_filter(now)`. Exclude `kind in ("control","platform_health")`.

### `backend/autonomous_ops/reporting/stats.py` (service, aggregate)
**Analog:** `backend/autonomous_ops/ledger.py` `counts` (311-320) and indexes (87-96). Use the RESEARCH Pattern 2 pipeline (`$match` on `tenantId`, `createdAt`, `kind $nin`; `$group` on rule/command/state/approved) through `scope.raw` with an explicit `tenantId`. Fold in Python by the Pattern 1 state-to-column table; `MINUTES_PER_KIND` per D-19.

### `backend/autonomous_ops/reporting/export.py` and `export_pdf.py` (file-I/O)
**Analogs:** `backend/audit_endpoints.py` lines 95-115 (audit + CSV), `backend/itam_data_service.py:63` (`sanitize_csv_cell`), `backend/export_service_pdf.py` lines 133-163 (WIP: reportlab doc setup).

CSV and audit (audit_endpoints.py):
```python
await audit_ledger.event("export.audit_log", scope["tenant_id"] or "platform-admin",
    actor={"email": current_user.username, "role": current_user.role, "tenantId": current_user.tenant_id},
    ip=request.client.host if request.client else None, rows=len(rows), filters={...})
out = io.StringIO(); writer = csv.writer(out); writer.writerow(_CSV_FIELDS)
headers = {"Content-Disposition": 'attachment; filename="audit-log.csv"'}
```
Use event name `autonomous_ops.export` with `format, bucket, days, rows, total, truncated`. PDF: copy `SimpleDocTemplate(landscape(letter), margins 0.5*inch)`, `cell_style = ParagraphStyle("cell", fontSize=7, leading=9, wordWrap='CJK')`, `header_style`; add the summary page (counts, per-rule table, Estimate) before the rows with `PageBreak`; wrap every cell in `xml.sax.saxutils.escape` (the analog does not escape: `Paragraph(str(row.get(h, "—")), cell_style)`). Set `X-Export-Rows`, `X-Export-Total`, `X-Export-Truncated`; 204 on zero rows. Call `dlp_service.scan_export(rows, tenant_id)` first and 403 on a block (as `export_report_endpoint`).

### `backend/autonomous_ops_reporting_endpoints.py` (route)
**Analog:** `backend/autonomous_ops_platform_endpoints.py` (tracked; style of the `put_*` handlers) plus the tenant helpers in `autonomous_ops_endpoints.py`.
```python
try:
    db = get_database()
    caller = await views.build_caller(user)
    ...
except HTTPException:
    raise
except Exception as exc:
    raise _unavailable(exc) from exc
```
Mount: add to `catalogue_mounts_autonomous_ops.py` MOUNTS (lines 30-34):
`("autonomous_ops_reporting_endpoints", "router"): AUTONOMOUS_OPS_GUARD,` and a `_load` line in `router_registry.py` beside the retention one. Validate with `Literal[7, 30, 90]` and bounded `Annotated`. Platform tenant -> 409 via `messages.API_DETAIL["platform_tenant"]`. Add the module to the whitelist tuple in `tests/test_catalogue_slice_autonomous_ops.py` (~line 97).

### `backend/autonomous_ops_golive_endpoints.py` and `put_shadow` gate
**Analog:** `backend/autonomous_ops_platform_endpoints.py` lines 217-236:
```python
@router.put("/tenants/{tenant_id}/shadow", ...)
async def put_shadow(body: ShadowBody, tenant_id: str = Path(..., max_length=views.TENANT_ID_MAX),
    user=Depends(_require_platform_autonomy_control), _session=Depends(_require_interactive_session)):
    try:
        db = get_database()
        tenant = await _real_tenant(db, tenant_id)
        caller = await views.build_caller(user)
        out = await settings.set_shadow(db, tenant, body.shadow, actor=await views.actor_for(db, caller))
```
Insert the gate between `caller` and `set_shadow`: when `body.shadow is False` and the stored flag is True, `blockers = await golive.lift_blockers(db, tenant)`; non-empty -> `HTTPException(409, detail=<plain sentence>)`. After success, `audit_ledger.event("autonomous_ops.shadow_lifted"|"shadow_restored", tenant, actor=..., ...)` (D-21: audit event only, no `control` row). The new routes reuse `_require_platform_autonomy_control` and `_require_interactive_session`.

### `backend/autonomous_ops/reporting/golive.py` (append-only records)
**Analog:** `ledger.py` raw-handle insert style; audit event style `audit_ledger.event("autonomous_ops.golive_check_recorded", PLATFORM_TENANT_ID, actor=..., checkId=..., note=...)`. Note body: `Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=500)]`, `check_id: Literal[...]` of the five ids. Add `autonomy_golive_checks` to `PROTECTED_COLLECTIONS` (`autonomous_ops/__init__.py:32`) and update the assertion at `tests/test_autonomous_ops_ledger.py:327`. A structural test (style of `test_autonomous_ops_structural.py`) asserts no update/delete on the collection.

### `backend/export_report_endpoint.py` / `export_controls.py` / `app_middleware.py` edits (WIP, after D-18 commit)
`REPORT_PERMISSIONS` (lines 20-40): add `"Autonomous Ops Activity": ("view:autonomous_ops",)`. Insert the AO branch before `set_tenant_id("platform-admin")` and before `service = ExportService()`. `export_controls.EXPORT_PATHS` (line 20, regex anchored `^/api/(...)$`): append `|autonomous-ops/export`. `app_middleware.py` ~line 290: add `X-Export-Rows`, `X-Export-Total` to `expose_headers` (`X-Export-Truncated` is already there). Keep edits small.

### `backend/migrations/035_activity_reporting.py`
**Analog:** `backend/migrations/034_plan_licensing.py`: module docstring listing steps, `DESCRIPTION = "..."`, `logger`, `async def` steps over the raw handle, idempotent (a second run changes nothing). Indexes only: `autonomy_actions (tenantId, finishedAt)`, `autonomy_digests` unique `(tenantId, day)`, `autonomy_golive_checks (checkId, recordedAt -1)`. Look at the `up`-style entry function at the bottom of 034 before copying.

### `services/autonomousOpsReporting.ts`
**Analog:** `services/autonomousOpsApi.ts` lines 291-320. Import and reuse the exported `getJson`, `failure`, `withTenant`:
```ts
export const withTenant = (url: string, tenantId?: string | null) =>
    tenantId ? `${url}?tenantId=${encodeURIComponent(tenantId)}` : url;
export async function getJson<T>(url: string): Promise<T> { const res = await authFetch(url); if (!res.ok) throw await failure(res); return res.json(); }
```
`${API_BASE}/autonomous-ops/statistics`. The export call is a sibling that reads the `X-Export-*` headers (precedent `exportItamAssetsCsv` in `services/apiService.ts` ~5764-5774).

### UI components
- Collapsed cards (`StatsCard`, `GoLiveCard`): `components/AutonomousOpsStatusCard.tsx` lines 1-50 (class constants `OUTLINE_CHIP`, `AMBER_CHIP`, `SIMULATION_CHIP`, `DIVIDER`, `SKELETON`; `Cell`, `Notice`; `useUser`, `resolveAutonomousOpsScope`, `useAutonomousOpsStatus`; icons from `./icons`). Every class string comes from there; no new tokens.
- Dialogs (`ExportDialog`, `ShadowDialogs`): `AutonomousOpsStopDialog.tsx` / `AutonomousOpsResponseSettingsDialogs.tsx` (typed-confirmation and Modal usage).
- Platform go-live pieces: `AutonomousOpsResponseSettingsPlatform.tsx`.
- `ReportExportCard`: `ReportingDashboard.tsx` line 159, classes `bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md flex justify-between items-center`; mount point near line 553 after Agent Health.
- Icons: only those listed in the UI-SPEC (`BarChart3Icon`, `DownloadIcon`, `ClipboardCheckIcon`, `ShieldCheckIcon`, ...); `SigmaIcon`, `TimerIcon`, `UnlockIcon` do not exist.
- Tests: `src/__tests__/AutonomousOpsStatusCard.test.tsx` (+ `StatusCardStates`).

### `backend/tests/test_autonomous_ops_stop_drill.py`
**Analogs:** `test_autonomous_ops_sweep.py` lines 89-94:
```python
async def test_the_platform_stop_makes_the_pass_do_nothing(mongo_db):
    await _world(mongo_db, "t1")
    await seed_platform_stop(mongo_db)
    await sweep.tick(mongo_db)
    assert await _rows(mongo_db, "t1") == []
```
plus `test_patch_rollout_shadow_stop.py`, `test_service_desk_intake.py`, `test_autonomous_ops_approvals.py`, `test_retention_job.py::test_the_platform_stop_does_not_pause_retention` (asserts the documented exception). Helpers: `tests/autonomy_support.py` (`seed_tenant(db, tenant_id, *, level, max_level, shadow, ...)`, `seed_agent`, `seed_platform_stop`), `tests/rollout_support.py`, `tests/service_desk_support.py`.

### Two-tenant and new backend tests (real Mongo)
**Analog:** `test_retention_job.py` header (lines 1-30):
```python
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_tenant
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-...")
NOW = datetime(2026, 10, 27, 9, 0, 0, tzinfo=timezone.utc)
```
Run only on the private mongod: set `MONGO_TEST_URL`, `MONGODB_URL` and `MONGO_URI` all to it (conftest teardown otherwise touches 27017). Inject `now`.

### Copy gate
Update three sides together: `shared/autonomous-ops-banned-terms.json` (`files`/`directories`: add `backend/autonomous_ops/reporting`, `components/autonomousOpsStats`, `components/autonomousOpsGoLive`, the two endpoint modules, `services/autonomousOpsReporting.ts`, the go-live doc), `backend/tests/test_autonomous_ops_copy.py` (`EXPECTED_FILES` ~24, `EXPECTED_DIRECTORIES` ~221), `src/__tests__/autonomousOpsCopy.test.ts` (`EXPECTED_*`, `FRONTEND_DIRECTORIES`). Do not add `ReportingDashboard.tsx`.

## Shared Patterns

- **Tenant isolation:** `from autonomous_ops.scope import raw`; every filter names `tenantId` explicitly; no ambient ContextVar; never import an LLM client under `autonomous_ops/` (structural test).
- **Endpoint error shape:** `except HTTPException: raise` / `except Exception as exc: raise _unavailable(exc) from exc` (platform endpoints file).
- **Notices never raise:** try/except with `logger.warning` (`plan_notices.announce`).
- **Audit:** `audit_ledger.event(name, tenant, actor={"email","role","tenantId"}, ...)`; note `AuditMiddleware` stores only route template and body keys, so explicit events are needed for shadow lift, go-live checks and exports.
- **Injection safety:** `sanitize_csv_cell` for CSV, `escape` for PDF.
- **File size:** each file under 500 lines (`views.py` 448, `autonomous_ops_endpoints.py` 451, `ReportingDashboard.tsx` 601 are already near or over; extract, do not grow).
- **Naming:** never "ASI", "Autopilot", "fully autonomous"; use "undo", "simulation".

## No Analog Found

| File | Reason |
|---|---|
| `docs/autonomous-ops-go-live.md` | No existing operator runbook for go-live; follow the RESEARCH outline and UI-SPEC. Pitfall 9: do not use 203.0.113.9 as the firewall example. |
| `reportingCopy.ts` / `goLiveCopy.ts` | No existing per-feature copy-constants module found; keep the strings in one module read by tests and the copy gate (UI-SPEC). |

## Metadata

**Analog search scope:** `backend/` (autonomous_ops, endpoints, migrations, tests), `components/`, `services/`, `src/__tests__/`.
**Pattern extraction date:** 2026-11-11.
**Caveat:** `rule_names.py`, `digest_text.py`, `GoLive*` and `StatsRuleTable` analogs were chosen from file names and the RESEARCH/UI-SPEC and were not read line by line; the planner's executor should read each before copying.
