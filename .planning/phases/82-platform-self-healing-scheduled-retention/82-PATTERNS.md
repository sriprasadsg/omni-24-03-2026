# Phase 82: Platform Self-Healing & Scheduled Retention - Pattern Map

**Mapped:** 2026-10-27
**Files analyzed:** 30 (new + modified)
**Analogs found:** 25 / 30 (all analog paths verified git-tracked)

Note: RESEARCH.md (read lines 1-449 of 663) already holds full code samples for the watchdog (polkit rule, unit, OP_MSG ping, sync contract, state machine, gate function). This map points the planner at the REAL repo analogs and exact line anchors; use RESEARCH.md for the new-code bodies.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `deploy/omni-watchdog/omni-watchdog.py` | host script (service) | batch / request-response | none in repo (RESEARCH Pattern 3-5) | no analog |
| `deploy/omni-watchdog/systemd/omni-watchdog.service` + `.timer` | config (unit) | batch | `start-all-services.sh` 470-500 (omni-backup unit/timer heredocs) | role-match |
| `deploy/omni-watchdog/systemd/*.service.d/*.conf` | config (drop-in) | - | live `mongod.service.d/kernel-rseq-check.conf` (not in repo; never touch) | no analog |
| `deploy/omni-watchdog/polkit/49-omni-watchdog.rules` | config | - | RESEARCH Pattern 1 | no analog |
| `deploy/omni-watchdog/etc/*.example`, `INSTALL.md` | config / doc | - | none | no analog |
| `backend/autonomous_ops/selfheal.py` | service + loop | event-driven / batch | `backend/autonomous_ops/reconciler.py` | exact |
| `backend/autonomous_ops/oncall.py` | service (outbox) | pub-sub | `backend/autonomous_ops/notify.py` + `ledger.py` | role-match |
| `backend/autonomous_ops/notify.py` (modify) | service | event-driven | itself | - |
| `backend/autonomous_ops/messages.py` (modify) | utility | transform | itself | - |
| `backend/autonomous_ops/ledger.py` (add `record_platform_health`) | service | CRUD | `ledger.record_control` (140-156) | exact |
| `backend/autonomous_ops/views.py` (modify `list_page`, `bucket_of`) | service | request-response | itself (161-165, 236-262) | - |
| `backend/watchdog_ingest_endpoints.py` | controller | request-response | `backend/autonomous_ops_platform_endpoints.py` | role-match (token auth differs) |
| `backend/autonomous_ops_platform_endpoints.py` (add health, test-alert, retention review/confirm) | controller | request-response | itself | exact |
| `backend/retention_job.py` | service + loop | batch | `backend/retention_service.py` `purge_agent_telemetry` + `reconciler.py` loop | role-match |
| `backend/retention_service.py` (modify: drop `cleanup_audit_logs`) | service | CRUD | itself | - |
| `backend/retention_endpoints.py` (modify `/run`, `/stats`, `/policies`) | controller | request-response | itself | - |
| `backend/app_background_tasks.py` (remove telemetry loop) / `app_startup.py` (register loop) | config | - | `app_startup.py` 505-523 | exact |
| `backend/migrations/025_platform_health.py` | migration | - | `backend/migrations/024_autonomous_ops.py` | exact |
| `backend/tests/test_watchdog_*.py`, `test_platform_health_*.py`, `test_retention_job.py`, `test_retention_gate.py` | test | - | `backend/tests/_autonomous_ops_http.py`, `_mongo_test_db.py`, `test_autonomous_ops_migration.py` | exact |
| `backend/tests/test_route_auth_baseline.py`, `test_autonomous_ops_copy.py`, `shared/autonomous-ops-banned-terms.json` (modify) | test/config | - | themselves | - |
| `components/AutonomousOpsPlatformHealth.tsx` | component | request-response (polled) | `components/AutonomousOpsStatusCard.tsx` | role-match |
| `components/AutonomousOpsRetentionReview.tsx` | component | request-response | `components/AutonomousOpsStopDialog.tsx` + `Modal` | role-match |
| `components/AutonomousOpsHealthBanners.tsx` | component | - | `components/AutonomousOpsStopBanner.tsx` | exact |
| `components/AutonomousOpsActivityList.tsx` (modify `visible`, pill) | component | - | itself | - |
| `components/RetentionPolicyDashboard.tsx` (modify, D-25) | component | CRUD | itself | - |
| `contexts/AutonomousOpsStatusContext.tsx` (modify, Pitfall 10) | provider | polling | itself (lines 1-40) | - |
| `services/autonomousOpsApi.ts` (add calls/types) | service | request-response | itself (`fetchPlatformAutonomousOpsStatus` 142, `pressPlatformStop` 176) | exact |
| `src/__tests__/AutonomousOpsPlatformHealth/RetentionReview/HealthBanners.test.tsx` | test | - | `src/__tests__/AutonomousOpsStopBanner.test.tsx` | exact |

## Pattern Assignments

### `backend/autonomous_ops/selfheal.py` and `backend/retention_job.py` (loops under distributed lock)

**Analog:** `backend/autonomous_ops/reconciler.py`

**Lock constants + imports** (lines 20-35):
```python
import asyncio, logging, os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from . import OPEN_STATES, approvals, breaker, ledger, messages, scope
from .scope import raw
LOCK_NAME = "autonomous_ops_reconciler"
LOCK_TTL_SECONDS = 120
LOCK_RENEW_EVERY = 30
def _env_number(name, default): ...
```
**One-runner tick + loop** (lines 150-176):
```python
async def run_once(db, *, now=None):
    import distributed_lock
    lock_db = SimpleNamespace(_db=raw(db))        # distributed_lock reads db._db
    async with distributed_lock.lock_with_renewal(lock_db, LOCK_NAME, ttl_seconds=LOCK_TTL_SECONDS,
                                                  renew_every=LOCK_RENEW_EVERY) as handle:
        if not handle.acquired:
            return None
        return await tick(db, now=now, lost=lambda: handle.lost)

async def reconciler_loop() -> None:
    from database import get_database
    while True:
        try:
            counts = await run_once(get_database())
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("autonomous_ops: reconciler pass failed: %s", exc)
        await asyncio.sleep(_interval())
```
Retention loop: same shape, but per RESEARCH "Scheduling" wake every 5 min and run if `now >= today 02:00 UTC and last_scheduled_run_date < today` (catch-up). Pass `lost=lambda: handle.lost` into the batch loop so it stops on lost lock. Use the raw handle (`scope.raw(db)`) with explicit tenant fields.

**Registration** (`backend/app_startup.py` 505-523): reconciler registered as
```python
asyncio.create_task(_safe_bg_task(_autonomous_ops_reconciler_loop(), "autonomous_ops_reconciler"), name="autonomous_ops_reconciler")
```
Add selfheal sweep + retention job loop the same way; remove `agent_telemetry_retention_loop` from the import tuple (line ~515) and the `create_task` at line 523; delete the function at `app_background_tasks.py` 367-382.

### `backend/retention_job.py` (type registry, bounded deletes)

**Analog:** `backend/retention_service.py` lines 1-55
```python
AGENT_TELEMETRY = {"agent_metrics": ("tenant_id", 30), "asset_metrics": ("tenant_id", 30),
                   "persistence_results": ("tenantId", 90), "logs": ("tenantId", 30)}
def _created_before(days): return {"$lt": ObjectId.from_datetime(datetime.now(timezone.utc) - timedelta(days=int(days)))}
```
and the per-tenant policy read:
```python
async for tenant in raw_db.tenants.find({}, {"_id": 0, "id": 1}): ...
    raw_db.retention_policies.find({"tenantId": tenant_id, "collection": {"$in": list(AGENT_TELEMETRY)}}, {"_id":0,"collection":1,"retention_days":1})
```
Reuse `AGENT_TELEMETRY` and `_created_before`; extend to the RESEARCH type registry (8 types; `agent_uptime_rollups` uses stored field `tenant_id`, Pitfall 5). Replace unbounded `delete_many` with `_id`-batch loop (RESEARCH Pattern 6). Keep `purge_agent_telemetry`'s "tenant None past default" sweep only if the planner wants parity (it currently deletes docs with no tenant).

### `backend/retention_endpoints.py` (modify)
Existing `POST /run` (lines ~66-79) builds `policies` from `retention_policies` and calls `svc.run_cleanup(policies=..., tenant_id=...)`; `/stats` returns `"next_scheduled": None` (line ~110). Change: remove audit deletion (D-16: `RetentionService.cleanup_audit_logs` in `retention_service.py` and its call in `run_cleanup`), make `/run` gate-aware (D-26), fill `next_scheduled` from a pure next-02:00-UTC function, refuse writes to the `audit_logs` policy (409, Open Question 4). Auth guard here is `require_auth` + `_RETENTION_ADMIN_ROLES` role check.

### `backend/autonomous_ops/ledger.py` -> new `record_platform_health`

**Analog:** `record_control` (lines 140-156)
```python
doc = {"id": "AO-" + uuid.uuid4().hex, "tenantId": tenant_id, "kind": "control", "state": "recorded",
       "scope": scope, "controlEvent": event, "actor": dict(actor or {}), ...,
       "createdAt": now, "updatedAt": now, "finishedAt": now}
try: await _actions(db).insert_one(doc)
except Exception as exc: raise LedgerUnavailable(...) from exc
doc.pop("_id", None)
await _mirror(db, tenant_id, event, doc, actor)
```
Differences: `kind: "platform_health"` (NOT `control`, anti-pattern), `tenantId: PLATFORM_TENANT_ID`, closed event enum, watchdog-supplied unique `id` (duplicate-key = already ingested; add unique index on that id in migration 025). `ensure_indexes` pattern at lines 85-96.

### `backend/autonomous_ops/views.py` (leak guard)
`list_page` (236-262): platform tenant scope = `own = {"tenantId": tenant_id}` returns every platform row; add `include_platform_health=False` default that ANDs `{"kind": {"$ne": "platform_health"}}`; only the platform route passes True. `bucket_of` (161-165): `return _STATE_BUCKET.get(row.get("state"), "refused")` -- map `kind == "platform_health"` first. `_STATE_BUCKET` is built from `BUCKET_STATES` (line 29); do not add the new bucket there (`ledger.counts` iterates it).

### `backend/autonomous_ops/notify.py` (modify, D-04)
Current body (whole file, 24 lines): `notify(db, tenant_id, *, title, message, severity, metadata)` posts via `pending_agents.post_to_recipients(raw(db), {"id": tenant_id}, ...)` inside try/except that only logs a warning ("notify never raises"). Keep the signature and the never-raises contract; add `await oncall.enqueue(...)` in its own try/except after the in-app post.

### `backend/watchdog_ingest_endpoints.py` and platform routes
**Analog:** `backend/autonomous_ops_platform_endpoints.py`
Imports/router (lines 13-38):
```python
router = APIRouter(prefix="/api/platform/autonomous-ops", tags=["Autonomous Ops (platform)"])
async def _require_platform_autonomy_control(user=Depends(get_current_user_or_api_key)):
    if not (await has_platform_permission(user, PLATFORM_CONTROL_PERMISSION)
            and _rbac_service._scopes_allow(user, PLATFORM_CONTROL_PERMISSION)):
        raise _forbidden(f"Missing required permission: {PLATFORM_CONTROL_PERMISSION}")
    return user
```
Route shape (lines 61-73): `@router.get("/status")` with `Depends(_require_platform_autonomy_control)` + `Depends(_require_interactive_session)`, try/except `HTTPException: raise`, `except Exception as exc: raise _unavailable(exc) from exc`. New Super Admin routes (health, health/test-alert, retention/review, retention/confirm) copy this exactly. Existing routes: status 61, actions 76, stop 101, resume 120, max-level 141, shadow 165, never-touch 190/202/225. Extend `get_platform_status` payload with `health`.
Token routes (`/api/internal/watchdog/sync|results`) have NO user auth: check `hmac.compare_digest` against the credential file/env, loopback client only, reject `X-Forwarded-*`; add both to `REVIEWED_UNAUTHENTICATED` in `backend/tests/test_route_auth_baseline.py` line 17 with a "Credential checked inside the handler" comment (Pitfall 17). Do not make the router required at startup.

### `backend/migrations/025_platform_health.py`
**Analog:** `backend/migrations/024_autonomous_ops.py` (whole file): `DESCRIPTION = "..."`, `async def up(db: AsyncIOMotorDatabase)`, import owning modules inside `up`, call each module's `ensure_indexes(db)`, `logger.info("migration 024: ...")`. Test analog: `backend/tests/test_autonomous_ops_migration.py`.

### `deploy/omni-watchdog/systemd/*` (unit files)
**Analog:** `start-all-services.sh` 470-500 (style only; do NOT edit this script, HEAL-08)
```
[Unit]
Description=Omni-Agent AI backup (MongoDB + platform keys)
After=mongod.service
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/omni-backup      # root-owned copy, not the checkout
...
[Timer]
OnCalendar=*-*-* 02:30:00 UTC
RandomizedDelaySec=15min
Persistent=true
```
Copy: root-owned installed script path, `Type=oneshot`, `[Install]` WantedBy timers. Use `OnBootSec=60`/`OnUnitActiveSec=60`, `TimeoutStartSec=45` (not `RuntimeMaxSec`). Full unit text in RESEARCH Pattern 2. Retention at 02:00 UTC precedes backup at 02:30.

### `components/AutonomousOpsHealthBanners.tsx`
**Analog:** `components/AutonomousOpsStopBanner.tsx` (rendered by it as the single shell slot per UI-SPEC)
Imports (lines 1-4):
```tsx
import React from 'react';
import { useAutonomousOpsStatus } from '../contexts/AutonomousOpsStatusContext';
import type { StopView } from '../services/autonomousOpsApi';
import { AlertOctagonIcon } from './icons';
```
Props style: `interface BannerProps { currentView: string; onViewDetails: () => void; }`; date helper `formatStopDate` (line 6) is reusable. Read `platformStatus.health` from `useAutonomousOpsStatus()`.

### `components/AutonomousOpsPlatformHealth.tsx` / `AutonomousOpsRetentionReview.tsx`
Analogs: `components/AutonomousOpsStatusCard.tsx` (readout `dl` cell, card, polled status via the shared hook; do NOT use `StatTile`, H1), `components/AutonomousOpsStopDialog.tsx` + `components/Modal.tsx` for the `Confirm deletion` dialog, `AutonomousOpsActivityList.tsx` for `StateChip`/`formatWhen`/`OUTLINE_CHIP`/`SECONDARY_BUTTON`. Toasts via `utils/toast` `showToast`. Permission via `useUser`/`hasPermission`. Executor must read the 81-UI-SPEC-derived structure in `82-UI-SPEC.md` sections for exact copy.

### `services/autonomousOpsApi.ts` (modify)
Existing: `AutonomousOpsRowBucket = Exclude<AutonomousOpsBucket, 'all'> | 'control'` (line 8) -> add `'platform_health'`; `PlatformAutonomousOpsStatus` (69) gains `health`; calls follow `fetchPlatformAutonomousOpsStatus` (142) and `pressPlatformStop` (176) for fetch/post + `AutonomousOpsApiError` (89) handling (409 review-token stale guard reuses it).

### `contexts/AutonomousOpsStatusContext.tsx` (modify, Pitfall 10)
`resolveAutonomousOpsScope` returns `tenant` for a Super Admin viewing a tenant, so `platformStatus` is not fetched; additionally fetch `fetchPlatformAutonomousOpsStatus` when the user holds `control:platform_autonomous_ops`, keeping one poller at `STATUS_POLL_MS = 30_000`.

### Tests
- Backend: `backend/tests/_autonomous_ops_http.py` (`Api` mounts both routers, identity per request, `NOW` constant, `probe_real_app`), `backend/tests/_mongo_test_db.py` (`mongo_db`, throwaway `omni_test_*`), `backend/tests/autonomy_support.py` (`seed_tenant`, `seed_platform_stop`). Watchdog tests import the hyphenated script via `importlib.util.spec_from_file_location`.
- UI: `src/__tests__/AutonomousOpsStopBanner.test.tsx` header: `vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: vi.fn() }))`, `vi.mock('../../utils/toast', ...)`, wrap in `UserContext` + `AutonomousOpsStatusProvider`, helper `statusPayload(over)` builders. Harness: `src/__tests__/_autonomousOpsCardHarness.tsx`.
- Copy gate: add every new component and server message module to `shared/autonomous-ops-banned-terms.json` `files`, `EXPECTED_FILES` in `backend/tests/test_autonomous_ops_copy.py`, and `src/__tests__/autonomousOpsCopy.test.ts` in the same plan that creates the file (Pitfall 18).

## Shared Patterns

### Platform-scope Super Admin auth
**Source:** `backend/autonomous_ops_platform_endpoints.py` 31-38 (`_require_platform_autonomy_control`) + `_require_interactive_session` from `autonomous_ops_endpoints`. **Apply to:** all new `/api/platform/autonomous-ops/*` routes.

### Raw Mongo handle with explicit tenant
**Source:** `autonomous_ops/scope.py` `raw(db)`; views.py docstring: "raw Mongo handle and an explicit tenantId are used everywhere; ambient tenant ContextVar never read". **Apply to:** retention_job, selfheal, oncall, ledger additions.

### Never-raise side effects
**Source:** `autonomous_ops/notify.py` try/except-log. **Apply to:** oncall enqueue, ingest mirror writes.

### Spool-and-replay (idempotent by id)
**Source:** `backend/audit_ledger.py` `replay_spool` (209-240): rename to `.replaying`, skip ids already stored, keep failed lines, unlink. **Apply to:** watchdog's local NDJSON event spool (re-implemented stdlib in the script) and any backend replay.

### Distributed lock + renewal
**Source:** `reconciler.py` run_once above. **Apply to:** selfheal sweep, retention job.

### User-visible text from messages.py only
**Source:** `backend/autonomous_ops/messages.py`; watchdog sends structured fields, backend renders text (closed event enum).

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `deploy/omni-watchdog/omni-watchdog.py` | host script | batch | No stdlib host scripts in repo; use RESEARCH Patterns 3-5 and Code Examples (OP_MSG ping, cert, statvfs). Closest style reference: `scripts/backup-omni.sh` (root-owned installed copy convention). |
| `polkit/49-omni-watchdog.rules` | config | - | RESEARCH Pattern 1 (ES5, node harness-tested) |
| `systemd/*.service.d/*.conf` drop-ins | config | - | Live drop-in not in repo; new file names only (`50-omni-restart.conf`, `10-omni-watchdog.conf`) |
| `etc/*.example`, `INSTALL.md` | config/doc | - | none |
| `AutonomousOpsRetentionReview.tsx` table | component | - | No review/confirm table precedent; compose from Modal + Activity list primitives per UI-SPEC |

## Metadata

**Analog search scope:** backend/autonomous_ops/, backend root retention/endpoints/startup files, backend/migrations, backend/tests helpers, components/AutonomousOps*, contexts, services, src/__tests__, start-all-services.sh
**Files read:** CONTEXT, RESEARCH (lines 1-449), reconciler, notify, ledger, views, platform endpoints, retention_service/endpoints, app_startup, migration 024, StopBanner, status context, api service (targeted ranges)
**Pattern extraction date:** 2026-10-27
