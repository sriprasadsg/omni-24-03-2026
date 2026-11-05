# Phase 84: Staged Patch Rollouts - Pattern Map

**Mapped:** 2026-11-05
**Files analyzed:** 31 (new and modified)
**Analogs found:** 29 / 31 (all cited paths verified git-tracked with `git ls-files`)

Line numbers below were read on 2026-11-05 from the working tree. Re-check them before quoting in a plan, because Phase 84 plans may edit the same files earlier in a wave.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `backend/autonomous_ops/rollout/__init__.py` | config (constants) | n/a | `backend/autonomous_ops/__init__.py` | exact |
| `backend/autonomous_ops/rollout/windows.py` | utility (pure) | transform | `backend/maintenance_service.py` (logic being replaced) | partial (no zoneinfo analog) |
| `backend/autonomous_ops/rollout/rings.py` | service | CRUD | `backend/autonomous_ops/response_settings.py` | exact |
| `backend/autonomous_ops/rollout/start.py` | service | request-response + atomic claim | `backend/autonomous_ops/incidents.py` (unique partial index + attach) | role-match |
| `backend/autonomous_ops/rollout/controller.py` | service (runner) | batch / event-driven loop | `backend/autonomous_ops/sweep.py` + `reconciler.py` | exact |
| `backend/autonomous_ops/rollout/canary.py`, `lines.py` | service | request-response (gate.decide) | `backend/autonomous_ops/sweep_restart.py` (`_request`, `_settle`) | exact |
| `backend/autonomous_ops/rollout/health.py` | utility (pure) | transform | `backend/autonomous_ops/sweep_restart.py` (`_failures`) / `signals.py` | role-match |
| `backend/autonomous_ops/rollout/revert.py` | service | request-response | `backend/autonomous_ops/approvals.py` `undo` (229-275) | exact |
| `backend/autonomous_ops/rollout/dispatcher.py` | service (dispatcher) | request-response | `backend/autonomous_ops/response_dispatch.py` | exact |
| `backend/autonomous_ops/rollout/messages.py` | config (copy) | n/a | `backend/autonomous_ops/response_messages.py` | exact |
| `backend/autonomous_ops/rollout/views.py` | utility | transform | `backend/autonomous_ops/response_views.py` / `incident_views.py` | exact |
| `backend/patch_rollout_endpoints.py` | route | request-response | `backend/autonomous_ops_response_endpoints.py` | exact |
| `backend/migrations/031_patch_rollouts.py` | migration | indexes only | `backend/migrations/028_security_response.py` | exact |
| `backend/autonomous_ops/registry.py` (modify) | config | n/a | itself (`ACTIONS`, 49-58) | exact |
| `backend/autonomous_ops/gate.py` (modify, `execute` gains `expiresAt`) | service | request-response | itself (411-431) | exact |
| `backend/autonomous_ops/delivery.py` (modify, expiry in hold-back) | service | event-driven | itself (`_screen`, `hold_back_autonomous`) | exact |
| `backend/autonomous_ops/reconciler.py` (modify, skip rollout rows) | service | batch | itself (116, 146, 154 dispatcher branches) | exact |
| `backend/autonomous_ops/sweep.py` or `app_startup.py` (modify, start controller loop) | config | loop wiring | `app_startup.py` 508-520 | exact |
| `backend/maintenance_service.py` (modify: time zone, past-midnight) | service | CRUD | itself | exact |
| `backend/patch_core_endpoints.py` (modify: reuse `new_patch_job`, extract revert) | route/service | CRUD | itself (101-152, 253-300) | exact |
| `backend/deployment_service.py` (fence/retire) | service | CRUD | itself | exact |
| `backend/router_registry.py`, `backend/catalogue_mounts_autonomous_ops.py` or patching mount (modify) | config | n/a | lines 345-349 / 22-31 | exact |
| `shared/catalogue-access.json` (modify: `patchManagement` routes += `/api/patch-rollouts`) | config | n/a | line 41 | exact |
| `shared/autonomous-ops-banned-terms.json` + `backend/tests/test_autonomous_ops_copy.py` `EXPECTED_FILES` + `src/__tests__/autonomousOpsCopy.test.ts` | config/test | n/a | the existing `files` list | exact |
| `agent-install/omni-agent-rs/src/capabilities/patch_installer.rs` (modify: `require_reversible`, `mode:"rollout"`, `expiresAt`, boot id) | agent capability | request-response | itself | exact |
| `agent-install/omni-agent-rs/src/capabilities/host_power.rs` | agent capability | request-response | reused unchanged | n/a |
| `shared/agent-response-contract.json` (modify if new verify checks) | contract | n/a | itself | exact |
| `services/patchRolloutsApi.ts` (new) | service | request-response | `services/autonomousOpsIncidentsApi.ts` | exact |
| `components/PatchRolloutsTab.tsx`, `PatchRolloutCard.tsx`, `PatchRolloutRingDetail.tsx`, `PatchRolloutStartDialog.tsx`, `PatchRolloutDialogs.tsx`, `PatchRolloutRings.tsx` | component | request-response + polling | `components/AutonomousOpsIncidentCard.tsx`, `AutonomousOpsResponseSettings.tsx` | role-match |
| `components/AutonomousOpsRolloutCard.tsx` | component | request-response | `components/AutonomousOpsIncidentCard.tsx` | exact |
| `components/MaintenanceWindowDialog.tsx`, `ChangeManagementWindows.tsx` | component | CRUD / read-only | `components/Modal.tsx` + `MaintenanceWindowConfig.tsx` | role-match |
| `components/PatchManagementDashboard.tsx`, `MaintenanceWindowConfig.tsx`, `AgentGroupsDashboard.tsx`, `ChangeManagementDashboard.tsx`, `AutonomousOpsDecisions.tsx` (modify mount points) | component | n/a | tab list in `PatchManagementDashboard.tsx` 42, 257-290 | exact |
| Tests: `backend/tests/test_autonomous_ops_rollout_*.py`, `test_autonomous_ops_structural.py` | test | n/a | `test_autonomous_ops_sweep.py`, `test_autonomous_ops_structural.py`, `test_autonomous_ops_migration.py` | exact |

## Pattern Assignments

### `backend/autonomous_ops/rollout/controller.py` (runner, batch loop)

**Analog:** `backend/autonomous_ops/sweep.py` (153 lines).

One runner, one distributed lock, per-tenant scope, stop skipped, failure per tenant logged (sweep.py 28-35, 85-153):
```python
LOCK_NAME = "autonomous_ops_sweep"
LOCK_TTL_SECONDS = 120
LOCK_RENEW_EVERY = 30
...
async def run_once(db, *, now: Optional[datetime] = None) -> Optional[Dict[str, int]]:
    import distributed_lock
    lock_db = SimpleNamespace(_db=raw(db))        # distributed_lock reads db._db
    async with distributed_lock.lock_with_renewal(lock_db, LOCK_NAME, ttl_seconds=LOCK_TTL_SECONDS,
                                                  renew_every=LOCK_RENEW_EVERY) as handle:
        if not handle.acquired:
            return None
        ...
        return await tick(db, now=now, lost=lambda: handle.lost)

async def sweep_loop() -> None:
    from database import get_database
    while True:
        try:
            counts = await run_once(get_database())
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("autonomous_ops: sweep pass failed: %s", exc)
        await asyncio.sleep(_interval())
```
Use its tenant loop (sweep.py 85-100: stop check, `scope.tenant_scope`, stage failure isolated) with a distinct `LOCK_NAME = "patch_rollout_controller"`. A stopped tenant skips install, advance and approve but still runs revert and settle (research tick diagram). Do not call `gate.decide` while stopped: `_step_tenant_stop` records a refused row per call (gate.py 170-173).

**Wiring:** register the loop in `backend/app_startup.py` next to the sweep (508-520):
```python
from autonomous_ops.sweep import sweep_loop as _autonomous_ops_sweep_loop
asyncio.create_task(_safe_bg_task(_autonomous_ops_sweep_loop(), "autonomous_ops_sweep"),
                    name="autonomous_ops_sweep")
```
**Required-index guard:** copy `_indexes_ready` (sweep.py 112-126) for the unique host claim index so the controller never runs unprotected.

---

### `backend/autonomous_ops/rollout/canary.py`, `lines.py` (gate.decide callers)

**Analog:** `backend/autonomous_ops/sweep_restart.py` `_request` (166-184) and `_settle` (187-209).

```python
return gate.ActionRequest(
    tenant_id=tenant_id, kind="security", origin="sweep", actions=[COMMAND], targets=[agent_id],
    params={"service_name": service}, dedupe_key=key, playbook_raise=over_budget,
    reason={"ruleId": RULE_ID, "inputs": inputs}, reason_text=text, dispatcher=response_dispatch.DISPATCHER_NAME)
```
```python
if decision.state == "dispatching":
    row = await ledger.get(db, tenant_id, decision.action_id)
    if row is not None:
        sent = await response_dispatch.send(db, row)
```
Adapt: `dispatcher="patch_rollout"`, dedupe key `tenant|rollout|<id>|<ring>|<host>|<attempt>` (never reuse a key after undo within 24 h: `suppressed_by_undo`, gate.py 299-302). One row per host in the canary (HOST_CAP = 1). Approval-line rows are one anchor row per (rollout, ring, line) with identical params for every target (dispatch_check.bind compares params, see RESEARCH Pattern 2). Pre-check each host with `agent_support.check(...)` as in `_one` (sweep_restart.py 213-216).

---

### `backend/autonomous_ops/rollout/dispatcher.py` (approvals dispatcher, window-deferred)

**Analog:** `backend/autonomous_ops/response_dispatch.py` (69 lines), whole file.

```python
DISPATCHER_NAME = "security_response"
async def send(db, row):
    result = await gate.execute(db, row["tenantId"], row["id"], command=row.get("command"),
                                agent_id=(row.get("targets") or [None])[0], params=row.get("params") or {},
                                kind="action")
    if result.get("status") == "queued":
        return result
    reason = result.get("reason")
    if reason == "stopped":
        await ledger.transition(db, row["tenantId"], row["id"], ("approved", "dispatching"), "cancelled_by_stop",
                                reasonCode="platform_stop", reasonText=messages.REASON_TEXT["platform_stop"])
    else:
        await ledger.transition(..., "failed", reasonCode="dispatch_failed", ...)
    return result

async def dispatcher(db, row, approver):
    return await send(db, row)

approvals.register_dispatcher(DISPATCHER_NAME, dispatcher)
```
Phase 84 delta: `dispatcher()` first checks the window (`windows.is_open`); closed returns a non-refusal answer and leaves the row `approved`; the controller later dispatches `approved` rows of this dispatcher (gate `_authorise` moves `approved` to `dispatching` itself, gate.py 395-398). Import must register the dispatcher in every process that approves (same note as sweep.py docstring: "Importing this module also registers..."). Pass `expiresAt` through `gate.execute` for D-04.

---

### `backend/autonomous_ops/rollout/revert.py` (undo-pattern revert, stop-exempt)

**Analog:** `backend/autonomous_ops/approvals.py` `undo` (229-275).

```python
spec = registry.resolve(row.get("command"))
if spec is None or not spec.undo:
    return {"status": "no_undo"}
params = decision_row.undo_block(spec, row.get("params") or {}, claim=claim)["params"]
block = {"available": True, "action": spec.undo, "params": params, "undoneAt": _now(None), "undoneBy": dict(actor)}
won = await ledger.transition(db, tenant_id, action_id, _UNDOABLE, "undone", actor=actor, undo=block)
if won is None:
    return {"status": "already_handled"}
result = await gate.execute(db, tenant_id, action_id, command=spec.undo, agent_id=targets[0], params=params, kind="undo")
if result.get("status") != "queued":
    await ledger.transition(db, tenant_id, action_id, ("undone",), row["state"], actor=actor, undo=..., finishedAt=row.get("finishedAt"))
    return {"status": "refused", "reason": result.get("reason") or "dispatch_failed"}
```
Phase 84 delta: params carry only what that host actually installed plus a NEW revert job id (per-host `new_patch_job`); actor is a system actor (the revert runs on its own, D-15); register `ActionSpec("install_patches", "auto", undo="rollback_patches")` and `ActionSpec("rollback_patches", "undo_only")` in `registry.py` (the existing registry entries at 49-58 show the shape). Undo is stop-exempt: `STOP_EXEMPT_KINDS = ("undo", "compensate")` (`autonomous_ops/__init__.py` ~66) and gate.py 391. Note `approvals.undo` also calls `breaker.evaluate` after (270-274): decide whether a rollout revert counts toward the breaker (CONTEXT discretion item).

---

### `backend/autonomous_ops/rollout/rings.py` (settings load/validate/save)

**Analog:** `backend/autonomous_ops/response_settings.py` (228 lines) plus `settings.py`. Copy: dataclass with `readable` flag, `load(db, tenant)` returning safe defaults when unreadable, `validate_changes` raising `SettingsError` subclasses with UI sentences, `save(...)` writing one control ledger row and one audit event naming the person, and `PlatformTenantError` mapped to 409 (see endpoint below). Ring membership is a snapshot into `patch_rollout_hosts` at Start; groups come from `agent_group_endpoints.py` (collection access pattern; router header at lines 1-14: `APIRouter(prefix="/api/agent-groups")`, `require_permission`, `get_database`).

---

### `backend/autonomous_ops/rollout/start.py` (atomic one-rollout-per-host claim)

**Analog:** `backend/autonomous_ops/incidents.py` `ensure_indexes` (56-63): unique partial index.
```python
await _coll(db).create_index([("tenantId", 1), ("agentId", 1)], unique=True,
                             partialFilterExpression={"closed": False}, name="incident_one_open")
```
Adapt to `patch_rollout_hosts`: unique on `(tenantId, agentId)` with `partialFilterExpression={"active": True}`; start does one `insert_many(ordered=False)` and treats per-host `DuplicateKeyError` as "left out" with the owning rollout name (D-13). Job creation per host: `new_patch_job(...)` from `patch_core_endpoints.py` 101-128 (signature `job_id, tenant_id, patch_ids, target_assets, agent_ids, created_by, deployment_type, scheduled_at, now, status`). Patch id validation: `installable_patch_id` / `pending_entry_id` (78-98). Never call `patch_instruction()` (131-150) from the controller: it writes unstamped instructions and the structural test fails any non-gate queue writer.

---

### `backend/autonomous_ops/rollout/health.py` (pure verdict)

**Analog:** `sweep_restart._failures` (82-100) for reading agent heartbeat/service-failure fields from `agents` with the raw handle and a bounded projection (`_failing_agents`, 227-233). Keep `ring_verdict(hosts, ring_settings, now)` pure (no db) and test it exhaustively (RESEARCH "Ring verdict" sketch, lines 438-455). Boot identity: the Rust agent already exposes `sysinfo::System::boot_time()` (`isolation.rs` 480, `system_patching.rs` 59); research §2 covers the heartbeat field.

---

### `backend/patch_rollout_endpoints.py` (routes `/api/patch-rollouts`)

**Analog:** `backend/autonomous_ops_response_endpoints.py`.

Imports and router (lines 19-43):
```python
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, StrictBool, StrictInt, StringConstraints
from api_key_auth import get_current_user_or_api_key
from autonomous_ops import PLATFORM_TENANT_ID, ...
from autonomous_ops_endpoints import (_decision_error, _require_control, _require_interactive_session,
                                      _require_manage, _tenant_for, _unavailable)
from database import get_database
router = APIRouter(prefix="/api/autonomous-ops", tags=["Autonomous Ops"])
```
Write route (104-129): `user=Depends(_require_manage), _session=Depends(_require_interactive_session)`, body model with strict types, `try: db = get_database(); tenant = await _tenant(db, user, tenantId) ... except HTTPException: raise ... except Exception as exc: raise _unavailable(exc) from exc`. Platform tenant refusal: 409 (`_tenant`, 70-74). Resume needs manage plus typed reason; Cancel needs manage; Start and Resume use interactive session. Permission names live in `shared/catalogue-access.json` line 41 (`patchManagement`: permission `view:patching`, write `manage:patches`, routes `/api/patches`, `/api/repo`): add `/api/patch-rollouts` to `routes`, and the mount guard for that slice (`catalogue_mounts_*.py`; autonomous-ops example 22-31 maps `("autonomous_ops_response_endpoints", "router"): AUTONOMOUS_OPS_GUARD`) must be extended for the new router module. Register with `_load(app, "patch_rollout_endpoints", "router")` in `backend/router_registry.py` (list at ~52-55 and calls at 345-349). A `test_catalogue_slice_*` test pins strings against the JSON.

---

### `backend/migrations/031_patch_rollouts.py`

**Analog:** `backend/migrations/028_security_response.py` (27 lines): `DESCRIPTION`, `async def up(db: AsyncIOMotorDatabase)`, delegating to `ensure_indexes` functions in the package, `create_index` idempotent, log line. Indexes only (no backfill). Also copy the migration test pattern from `backend/tests/test_autonomous_ops_migration.py`. Next number is 031 (030 is the last tracked: `030_hash_reset_tokens.py`).

---

### `backend/autonomous_ops/delivery.py` (modify: expiry)

**Analog:** itself. Add `expiresAt` enforcement inside `hold_back_autonomous` (152-167), reusing the `mark(item, status, why)` helper in `_screen` (100-125):
```python
await coll.update_one({key: item[key], "status": pending},
                      {"$set": {"status": status, "error": why, "refused_at": datetime.now(timezone.utc).isoformat()}})
```
Terminal `status: "refused"`, `error: "instruction_expired"`. Keep the contract that a list with no stamped item and no `expiresAt` returns unchanged and touches no database (see the early `if not instructions: return instructions`). Undo kinds stay exempt from the stop check at delivery.py ~125 (`kind not in STOP_EXEMPT_KINDS`).

---

### `backend/autonomous_ops/gate.py` (modify: `execute` optional `expiresAt`)

**Analog:** itself, `execute` doc build (411-431). The stamp is written only here and in `execute_response_task`; add an optional kwarg, e.g. `expires_at: Optional[datetime] = None`, setting `doc["expiresAt"]` as a BSON datetime. Do not add a second stamp writer (structural test).

---

### `backend/autonomous_ops/reconciler.py` (modify)

**Analog:** itself. Its dispatcher branches (lines 116 for `remediation` multi-step ownership, 146, 154, 199 for `security_response`) show how a dispatcher "owns" a row; add a skip for `dispatcher == "patch_rollout"` (the controller owns its lifecycle), modelled on the remediation `_owned_by_sender` style check at 116.

---

### `backend/autonomous_ops/rollout/messages.py`, `views.py`

**Analog:** `backend/autonomous_ops/response_messages.py` (copy dicts `REASON_TEXT`, `WHY_TEMPLATES`, `fill`) and `response_views.py`/`incident_views.py` (payload builders with per-line `canApprove`/`canDeny` flags computed from the caller via `views.build_caller`, `views.actor_for`). Copy rules: ACTV-08. Use "revert", "put back", never "rollback"; a line with "roll back" must contain "where supported".

---

### Copy-gate registration (every new `.py`/`.ts(x)` copy file)

**Source:** `shared/autonomous-ops-banned-terms.json` `files` array (rule `rollback` at line 10 is `\broll(?:ed|ing)?[ -]?back\b` unless line contains "where supported"). Add in the SAME plan that creates each file: `backend/autonomous_ops/rollout/messages.py`, `.../views.py`, `backend/patch_rollout_endpoints.py`, `services/patchRolloutsApi.ts`, and all new `components/PatchRollout*.tsx`, `AutonomousOpsRolloutCard.tsx`, `MaintenanceWindowDialog.tsx`, `ChangeManagementWindows.tsx`. Three places must change together: the JSON, `EXPECTED_FILES` in `backend/tests/test_autonomous_ops_copy.py` (lines 20-60), and the hard-coded list in `src/__tests__/autonomousOpsCopy.test.ts`. Do NOT add `OsPatchesTab.tsx` or `ChangeManagementDashboard.tsx` (old "rollback" copy). Note `backend/patch_core_endpoints.py` also contains `rollback` and must stay off the list.

---

### `agent-install/omni-agent-rs/src/capabilities/patch_installer.rs` (modify)

**Analog:** itself (416 lines). Relevant anchors:
- `parse_job` (49-64) reads `payload.patch_ids` / `payload.job_id`; extend to read `require_reversible`, `mode`, `expiresAt` the same way (also under `parameters`).
- `patch_result(patch_id, status, message, reboot)` (67) and `summarize` (73) produce the per-patch result; use status `"skipped"` for ids that do not apply to a host when `mode == "rollout"` (existing skip example at 364: `results.push(patch_result(pkg, "skipped", ...))`).
- `triage` (86) filters invalid ids; `run` (103) is the entry; Linux `install`/`rollback` (330, 372) use the saved previous-version state (`load_state`/`save_state`, 257-261) to refuse a downgrade when no recorded version exists; Windows PowerShell block (~149) emits `skipped` entries and is where `IsUninstallable` is checked pre-install (D-05).
- Reboot flag: `patch_result(..., reboot: bool)` and `reboot_required()` (318) feed the Reboot line.
Build rule: agent changes ship only in a published binary (2.1.16 built, not published); keep `shared/agent-response-contract.json` (e.g. `rebootDelaySeconds` min 30 max 300, line 30; `reboot_host` mapping at 14 and 25) consistent with `host_power.rs`. Run Rust tests per the memory note: `CARGO_PROFILE_DEV_DEBUG=0` with `target/nodebug`.

---

### Frontend: `services/patchRolloutsApi.ts`

**Analog:** `services/autonomousOpsIncidentsApi.ts` (header 1-10):
```ts
import { API_BASE, authFetch } from './apiService';
import { failure, getJson, withTenant } from './autonomousOpsApi';
```
Server-decided flags on every line/card (`canApprove`, `canDeny`), types exported next to functions, no role inference in the browser, strings rendered as React text only.

### Frontend: `components/AutonomousOpsRolloutCard.tsx`, rollout components

**Analog:** `components/AutonomousOpsIncidentCard.tsx` (378 lines): imports (1-17), constants (`DEADLINE_CHIP`, `MUTED`, `TEXT_BUTTON`, 26-34), pure helpers `minutesLeft`/`formatExpires` (38-45), `useUser`, `showToast` from `../utils/toast`, `StateChip`/`formatWhen` from `AutonomousOpsActivityList`, `SECONDARY_BUTTON` from `AutonomousOpsHealthCards`, `ACCENT_BUTTON, plain, plural` from `AutonomousOpsResponseSettingsDialogs`. Reuse these exports rather than redefining; the UI-SPEC says the rollout card is a separate file because the incident card is already 378 lines. `AutonomousOpsDecisions.tsx` merges the new card into the section (UI-SPEC 275).

### Frontend: mounting the Rollouts tab

**Analog:** `components/PatchManagementDashboard.tsx` (439 lines; keep under 500). Tab union at line 42 `useState<'patches' | 'approvals' | 'software-updates' | 'os-patches'>`, tab array at 257, tab buttons at 272-274, panels at `activeTab === 'patches' && (...)` (287). Add `'rollouts'` to the union and array and render `<PatchRolloutsTab/>` only; all behaviour lives in the new files. `onOpenView` payload and `App.tsx` change per UI-SPEC 342. `MaintenanceWindowDialog.tsx` is built on `components/Modal.tsx` (UI-SPEC: `size="md"`, `showClose={false}`, `closeOnBackdrop={false}`), replacing the hand-built modal in `MaintenanceWindowConfig.tsx`.

---

### Tests (backend)

**Analogs:** `backend/tests/test_autonomous_ops_sweep.py` (loop/lock/tick), `test_autonomous_ops_structural.py` (only the gate writes the stamp, every delivery path keeps the hold-back; every scanner has a negative control; scans tracked files only), `test_autonomous_ops_registry.py` (registry pins: update when `install_patches`/`rollback_patches` are added), `test_autonomous_ops_dispatch_binding.py`, `test_autonomous_ops_migration.py`, `test_autonomous_ops_copy.py`, `_autonomous_ops_http.py` (HTTP harness for route tests), `test_autonomous_ops_response_rows.py` (row shapes). Pure-function tests for `windows.py` and `ring_verdict` need no fixtures.

## Shared Patterns

### Gate-only agent writes
**Source:** `backend/autonomous_ops/gate.py` `execute` 411-431 (stamp `{"actionId", "tenantId", "kind"}`, `triggered_by: STAMP_SOURCE`).
**Apply to:** every rollout install, reboot, revert. `_DISPATCHABLE = {"action": ("approved","dispatching"), "probe": ..., "compensate": ..., "undo": ("undone",)}` (gate.py 58-59).

### Raw handle with explicit tenantId
**Source:** `from .scope import raw`, `scope.tenant_scope` in sweep.py. Never use the ambient tenant ContextVar outside `tenant_scope`. Copy docstring convention "Raw Mongo handle with an explicit tenantId; the ambient tenant ContextVar is never used."
**Apply to:** all `rollout/*.py` modules (they inherit `autonomous_ops` structural tests; each file under 500 lines per CLAUDE.md).

### Route error and permission shape
**Source:** `backend/autonomous_ops_response_endpoints.py` 104-129 (`_require_manage`, `_require_interactive_session`, `_tenant`, `_unavailable`, `HTTPException` pass-through).
**Apply to:** `patch_rollout_endpoints.py`. API keys never approve (Phase 81 D-10).

### Approval flow limits
**Source:** `approvals.py` `approve` (133-195), `deny` (197), `expire_due` (207): 24 h TTL counts as denied; `register_dispatcher(name, fn)` (65). Constants in `autonomous_ops/__init__.py`: `HOST_CAP = 1`, `RATE_LIMIT_PER_WINDOW = 20`, `APPROVAL_TTL = timedelta(hours=24)`, `BREAKER_THRESHOLD = 3` (lines ~36-40).

### Background runner under lock
**Source:** `sweep.py` (above) and `reconciler.py` 28-60 (`LOCK_NAME`, `LOCK_TTL_SECONDS`, `LOCK_RENEW_EVERY`, per-tenant failure isolation, ContextVar back to None after every tick).

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `backend/autonomous_ops/rollout/windows.py` | utility | transform | No `zoneinfo`/IANA window math exists. `maintenance_service.py` `is_in_maintenance_window` (UTC only, midnight-unsafe, uses `start_time <= now_time <= end_time`) is the behaviour being replaced. Use the RESEARCH.md "Window occurrences" sketch (stdlib, ran successfully) and test DST and past-midnight cases. |
| Boot-identity heartbeat field and agent-side expiry (Rust + backend heartbeat ingest) | agent capability | event-driven | `boot_time` exists only in isolation state and `system_patching.rs`; no heartbeat-carried boot id for a reboot-then-return check. Follow RESEARCH §2 and the contract file. |

## Notes for the planner

- `backend/maintenance_service.py` uses `self.db.<collection>` directly and ISO strings; the tenant-scoped DB wrapper auto-scopes tenants (memory: tenant boundary hardening), but rollout code uses `raw(db)` with explicit `tenantId`.
- `backend/deployment_service.py` and `POST /api/patches/deployment-jobs/{id}/rollback` (patch_core_endpoints.py 253-300) queue instructions without the gate; plans must fence them and extract the revert into a gated service function rather than extend them.
- The auto-mode memory note stands: git push and UI publish are the user's.

## Metadata

**Analog search scope:** `backend/autonomous_ops/`, `backend/*endpoints*.py`, `backend/migrations/`, `backend/tests/`, `shared/`, `services/`, `components/`, `agent-install/omni-agent-rs/src/capabilities/`
**Files read or grepped:** about 30
**Pattern extraction date:** 2026-11-05
