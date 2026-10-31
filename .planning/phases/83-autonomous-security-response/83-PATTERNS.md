# Phase 83: Autonomous Security Response - Pattern Map

**Mapped:** 2026-10-31
**Files analyzed:** 47 (new and modified)
**Analogs found:** 45 / 47 (all analog paths verified git-tracked; Rust analogs from `agent-install/omni-agent-rs`, not `agent-rust/`)

Line numbers below are from this session's reads. Where a range was read in 83-RESEARCH.md it is cited by file and line there.

## File Classification

### Backend: new

| New file | Role | Data flow | Closest analog | Match |
|----------|------|-----------|----------------|-------|
| `backend/autonomous_ops/sweep.py` | service (loop) | batch / event-driven | `backend/autonomous_ops/reconciler.py` | exact |
| `backend/autonomous_ops/signals.py` | service | transform + CRUD | `backend/autonomous_ops/reconciler.py` (raw handle + explicit tenantId) and `backend/autonomous_ops/settings.py` | role-match |
| `backend/autonomous_ops/incidents.py` | model/service | CRUD (compare-and-set) | `backend/autonomous_ops/ledger.py` | role-match |
| `backend/autonomous_ops/response_settings.py` | service | CRUD | `backend/autonomous_ops/settings.py` (`load`, `update`, `set_level`) | exact |
| `backend/autonomous_ops/agent_support.py` | utility | request-response | `backend/agent_capabilities.py` (`allowed_for`, `_INSTRUCTIONS`) | role-match |
| `backend/autonomous_ops/verify.py` | service | event-driven | `backend/autonomous_ops/reconciler.py` `_reconcile_dispatches` | role-match |
| `backend/autonomous_ops/followups.py` | service | event-driven | `backend/playbook_engine_actions.py` `gate_request` + `selector_request` | role-match |
| `backend/autonomous_ops_response_endpoints.py` | route | request-response | `backend/autonomous_ops_endpoints.py` (routes) and `backend/autonomous_ops_retention_endpoints.py` (new router file) | exact |
| `backend/migrations/028_security_response.py` | migration | batch | `backend/migrations/027_retention_gate.py` | exact |
| `backend/tests/test_autonomous_ops_sweep*.py`, `_signals`, `_response_endpoints`, `_fence` | test | n/a | `backend/tests/test_autonomous_ops_gate.py`, `_gate_order.py`, `_copy.py` | exact |

### Backend: modified

| File | Change | Closest analog (for the new part) |
|------|--------|-----------------------------------|
| `backend/autonomous_ops/gate.py` | dormancy step, `_agent_of` projection, `_undo_block` keeps `block_id`, new reason codes | itself (`ActionRequest`, `suggest` lines 60-89, 409-411) |
| `backend/autonomous_ops/ledger.py` | `refresh_suggestion` | itself |
| `backend/autonomous_ops/approvals.py` | `_revalidate` calls `agent_support.check`; register `security_response` dispatcher | `register_dispatcher` (lines 65-68) |
| `backend/autonomous_ops/reconciler.py` | verify step, followup hook | itself (lines 140-176) |
| `backend/autonomous_ops/messages.py` | new reason text, `superseded`, copy | itself |
| `backend/autonomous_ops/breaker.py` | count only `verify_failed`, `agent_failed`, `blocked_by_local_security` | itself (`_BAD_STATES`) |
| `backend/autonomous_ops/registry.py` | new commands (`quarantine_file`, `unquarantine_file`, `isolate_host`, `restore_host`, `reboot_host`) | itself |
| `backend/agent_tasks_endpoints.py` | persist whitelisted `verify` and `outcome` | lines 98-111 |
| `backend/agent_heartbeat_endpoints.py` | reply carries `watchedServices`, `isolationConfirmed` | line 531 `enabledCapabilities` |
| `backend/agent_capabilities.py` | `_DATA_KEYS["service_failures"] = "remediation_executor"`, instruction map | line 56 |
| `backend/app_startup.py` | start `sweep_loop` | lines 507-515 (the reconciler start) |
| `backend/router_registry.py` | `_load(app, "autonomous_ops_response_endpoints", "router")` | line 342 |
| `backend/catalogue_mounts_autonomous_ops.py` | guard entry for the new router | line 28 |
| `backend/threat_feed_sync.py` | optional `Auth-Key`, `source_feeds` list (D-26) | itself |
| `backend/playbook_engine_actions.py` | automatic XDR steps suggest only (D-25) | itself (`_fence_automatic_step`, `selector_request`) |
| `backend/correlation_engine_threat.py` | selectors already suggest-only; ensure `xdr-auto` too | itself (`_fallback_select_playbook`) |
| `backend/remediation_playbook_service.py` | `select_playbook` routing (D-05, D-07, D-08) | itself (lines 106-146) |
| swarm `propagate-antibody` service and `soar_engine.py` | fence: honest "nothing sent" answer, no `agents.isolated` | RESEARCH Q12 (read `swarm_service.py`, `soar_engine.py`, `tasks.py` writers) |

### Frontend

| File | Role | Data flow | Closest analog | Match |
|------|------|-----------|----------------|-------|
| `components/AutonomousOpsDecisions.tsx` | component | polling | `components/AutonomousOpsRetentionReview.tsx` (`RETENTION_POLL_MS`) | exact |
| `components/AutonomousOpsIncidentCard.tsx` | component | request-response | `components/AutonomousOpsActivityList.tsx` (row actions) | role-match |
| `components/AutonomousOpsRowActions.tsx` | component | request-response | `components/AutonomousOpsActivityList.tsx` | role-match |
| `components/AutonomousOpsResponseSettings.tsx` | component | CRUD form | `components/AutonomousOpsRetentionReview.tsx` + `NotificationPreferencesDashboard.tsx` (`role="switch"`) | role-match |
| `components/AutonomousOpsResponseSettingsDialogs.tsx` | component | request-response | `components/AutonomousOpsRetentionConfirmDialog.tsx` | exact |
| `services/autonomousOpsApi.ts` | service | request-response | itself | exact |
| `components/AutonomousOpsActivity.tsx`, `App.tsx` (`onOpenView`), `components/SwarmDashboard.tsx` (message), `shared/autonomous-ops-banned-terms.json` | modified | | themselves | exact |

### Agent (Rust, `agent-install/omni-agent-rs/src`)

| File | Role | Data flow | Closest analog | Match |
|------|------|-----------|----------------|-------|
| `capabilities/response_state.rs` | utility/store | file-I/O + timer | `capabilities/fim_baseline.rs` (state file) and `config.rs` `save` | role-match |
| `capabilities/firewall.rs` | service | request-response | `capabilities/remediation_actions.rs` `block_ip`/`unblock_ip` (lines ~187-232) | exact |
| `capabilities/quarantine.rs` | service | file-I/O | `capabilities/remediation_actions.rs` `restore_file` (~158-176) | role-match |
| `capabilities/service_watch.rs` | service | event-driven | `capabilities/remediation_actions.rs` `disable_service`; `capabilities/process_monitor.rs` (periodic collector) | role-match |
| `capabilities/remediation_actions.rs` (mod) | service | request-response | itself | exact |
| `instructions.rs` (mod) | dispatcher | request-response | its existing arms (lines 515-545) | exact |
| `capabilities/mod.rs` (mod) | config | heartbeat adopt | `update_enabled_from_heartbeat` (lines 203-215) | exact |
| `heartbeat.rs` (mod) | transform | request-response | existing `meta.*` build near line 538-553 | exact |
| `Cargo.toml` | config | n/a | version bump 2.1.15 -> 2.1.16 only | exact |

No-analog list: none strict. Weakest: `incidents.py` (no existing compare-and-set incident store), `service_watch.rs` (no existing service watcher), the Linux/Windows isolation logic in `firewall.rs` (only single-rule precedent).

## Pattern Assignments

### `backend/autonomous_ops/sweep.py` (service, batch)

**Analog:** `backend/autonomous_ops/reconciler.py`

**Imports and constants** (lines 26-45):
```python
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Callable, Dict, Optional

from . import OPEN_STATES, approvals, breaker, ledger, messages, scope
from .scope import raw

LOCK_NAME = "autonomous_ops_reconciler"     # use "autonomous_ops_sweep"
LOCK_TTL_SECONDS = 120
LOCK_RENEW_EVERY = 30
```

**Per-tenant tick** (lines 140-151): `with scope.tenant_scope(tenant_id):` inside try/except that logs and continues; check `lost()` between tenants.

**Single-runner and loop** (lines 153-176), copy verbatim:
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
            logger.error(...)
        await asyncio.sleep(_interval())
```
Env interval helper: `_env_number("AUTONOMOUS_OPS_RECONCILE_INTERVAL_SEC", 60)` (lines 48-62); use `AUTONOMOUS_OPS_SWEEP_INTERVAL_SEC`.

**Start-up wiring** (`backend/app_startup.py` lines 507-515):
```python
from autonomous_ops.reconciler import reconciler_loop as _autonomous_ops_reconciler_loop
asyncio.create_task(_safe_bg_task(_autonomous_ops_reconciler_loop(), "autonomous_ops_reconciler"),
                    name="autonomous_ops_reconciler")
```
Note: `app_startup.py` has uncommitted hunks from other work; stage by path and commit only your own hunks.

**Gate entry** (do not use `remediate()`): build `gate.ActionRequest` as in `backend/playbook_engine_actions.py` `gate_request` lines 20-39 (kind `"security"`, `reason={"ruleId", "inputs"}`, `dedupe_key`, `playbook_raise`, `dispatcher`). Sweep uses `dispatcher="security_response"`, `origin="sweep"`. Suggestions use `gate.suggest` (gate.py 409-411) with a different dedupe key (`...|sweep-suggest|...`) than actions (`...|sweep|...`).

---

### `backend/autonomous_ops/signals.py`, `incidents.py`, `followups.py`

**Analogs:** reconciler.py for raw-handle plus explicit `tenantId` (never the ambient ContextVar; `from .scope import raw`). For `followups.py`, reuse `gate_request` shape from `backend/playbook_engine_actions.py` lines 20-39, and `kill executed -> gate.decide(quarantine_file)` with key suffix `|retry`.

Key rules (RESEARCH Anti-Patterns, lines 275-281): read `edr_ioc` through the raw handle with `{"tenantId": {"$exists": False}, "source_feed": ...}`; never count `description`/`evidence` free text; hostname -> `agents.id` via `{tenantId, $or:[{id},{hostname}]}` and skip on ambiguity; use the sweep's own `firstSeenAt`, never `edr_ioc.last_seen`.

---

### `backend/autonomous_ops/response_settings.py` (service, CRUD)

**Analog:** `backend/autonomous_ops/settings.py` (functions `load` l.54, `update` l.154, `set_level` l.161, `set_max_level` l.194, `ensure_indexes` l.218). Copy its load/validate/update shape and the `actor` recording; every change writes a ledger control row and an audit event (D-04). "All tenants" = loop over tenants calling the same per-tenant writer.

---

### `backend/autonomous_ops_response_endpoints.py` (route)

**Analogs:** `backend/autonomous_ops_endpoints.py` (447 lines, so do not extend it) and `backend/autonomous_ops_retention_endpoints.py` (new-router-file precedent).

**Imports and router** (retention endpoints lines 14-35):
```python
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from autonomous_ops import ledger, views
from autonomous_ops.scope import raw
from autonomous_ops_endpoints import _require_interactive_session, _unavailable
from database import get_database
router = APIRouter(prefix="/api/autonomous-ops", tags=["Autonomous Ops"])
```
Writes: `Depends(_require_manage)` plus `Depends(_require_interactive_session)` (see `put_level`, lines 250-257); approve/deny/undo analogs at lines 414-444 use `_require_control` and the `_decide` helper (l.387). Tenant resolution via `_tenant_for(db, user, tenant_id, write=True)` (l.40). Registration: `router_registry.py` line 340-342 and guard entry in `catalogue_mounts_autonomous_ops.py` line 28. Confirm-isolation requires the approve-tier permission and MFA like approve. Validate service names with `^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$`, max 50, block length 3600..604800 s.

---

### `backend/migrations/028_security_response.py` (migration)

**Analog:** `backend/migrations/027_retention_gate.py` (full file, 20 lines):
```python
DESCRIPTION = "Scheduled retention: gate, count and run-summary indexes"
logger = logging.getLogger(__name__)

async def up(db: AsyncIOMotorDatabase) -> None:
    import retention_gate
    await retention_gate.ensure_indexes(db)
    logger.info("migration 027: retention gate indexes ensured")
```
Indexes only, idempotent (`create_index` with an unchanged definition is a no-op). Put an `ensure_indexes(db)` in `signals.py`/`incidents.py` and call it from the migration, like `settings.ensure_indexes`. Do not run against the live DB; tests use `tests/_mongo_test_db.py`.

---

### `backend/autonomous_ops/gate.py`, `approvals.py` (dormancy and dispatcher)

**Analog:** `approvals.register_dispatcher(name, fn)` (approvals.py 65-68): `fn(db, row, approver)` async, called with the row already `approved`, returns a dict. Register `security_response` there; it calls `gate.execute(db, tenant, action_id, command=..., agent_id=..., params=..., kind="action")`. New reason codes go into `gate.REASON_CODES` and `messages.REASON_TEXT`; `test_autonomous_ops_gate_order.py` enumerates step order, so insert the dormancy step at a fixed position and update that test. `dispatch_check.bind` requires undo params to equal decided params, so `_undo_block` must carry `block_id`.

---

### `backend/threat_feed_sync.py` (D-26)

**Analog:** itself. Current fetch (lines 56-88): `session.post(URLHAUS_RECENT, data={"limit": MAX_PER_SOURCE}, timeout=aiohttp.ClientTimeout(total=30))`, 401 handled at debug level. Add the key without logging it:
```python
ABUSE_CH_AUTH_KEY = os.getenv("ABUSE_CH_AUTH_KEY", "")   # next to OTX_API_KEY (line ~43)
headers = {"Auth-Key": ABUSE_CH_AUTH_KEY} if ABUSE_CH_AUTH_KEY else {}
session.post(URLHAUS_RECENT, data=..., headers=headers, ...)    # same for BAZAAR_EXPORT
```
Behaviour unchanged when unset. `source_feeds`: `_upsert_iocs` (lines 185-203) uses `$set: ioc` keyed by `(ioc_type, ioc_value)`, which overwrites `source_feed`. Change to `{"$set": ioc_without_source_feeds, "$addToSet": {"source_feeds": ioc["source_feed"]}}` and keep `source_feed` for existing readers. Update the module docstring schema. Never put the key in a log line.

---

### `backend/playbook_engine_actions.py` and `backend/correlation_engine_threat.py` (D-25)

**Analog:** itself. `AUTOMATIC_EXECUTORS = frozenset({"xdr-auto", "ai-selector", "fallback-selector"})` (l.9). Today `_fence_automatic_step` (l.78-117) runs `gate.decide` and, on `allow_auto`, `gate.execute_response_task` (a `response_tasks` write the Rust agent never reads). Change: for an automatic executor build the request with `gate_request(...)` (l.20) and call `gate.suggest(self.db, req)` instead of `decide`, return the "Suggested only" string (the existing suggest branch, l.112-113), and never call `execute_response_task`. Human-started runs return None at l.88 and stay unchanged.
Selectors already suggest-only (`correlation_engine_threat._fallback_select_playbook` lines 105-136 uses `selector_request` + `gate.suggest`); verify `_ai_select_playbook` (l.48) does the same, and add a test that no automatic executor reaches `allow_auto` or `needs_approval`.

---

### `backend/remediation_playbook_service.py` `select_playbook` (D-05, D-07, D-08)

**Analog:** itself, lines 106-146. Current routes to change:
```python
if finding_type == "fim":
    return by_name.get("restore_file")            # D-08: leaves the sweep -> suggestion only
if finding_type == "nscan":
    if scan_type == "ip": return by_name.get("block_ip")
    return by_name.get("kill_process")            # D-05: non-IP malicious file -> quarantine_file
if finding_type == "vuln":
    ... patch_package / disable_service           # D-07: suggestion only, both routes
```
Keep `rotate_key`/`restore_file`/`disable_service` playbooks in the registry as approval-only (D-09). Keep the function a pure deterministic lookup. Check the vendored playbook set loaded by `load_default_playbooks()` has a `quarantine_file` entry; add one if not. Protected-path handling (D-28): add a path-prefix check (System32, SysWOW64, WinSxS, /usr/bin, /usr/sbin, /bin, /sbin, /boot, agent install and quarantine dirs; case-insensitive and separator-normalised on Windows) in the sweep and set `playbook_raise=True` so the gate answers `needs_approval` (`gate.py:192-193`). Put the prefix list in one shared module (e.g. `autonomous_ops/protected.py`, which already holds `parse_ip` and `check`) and mirror it in the agent.

---

### `backend/agent_tasks_endpoints.py` (verify persistence)

**Analog:** lines 98-111, the `$set` on `agent_instructions`:
```python
"result": {"message": message_text, "error": error_msg, "raw_status": raw_status},
```
Add `"verify"` and `"outcome"` from `result`, whitelisted and size-bounded (`verify = {ok: bool, check: str<=64}`; `outcome: str<=64`). Reconciler's verify step reads them.

---

### `backend/agent_capabilities.py` and `agent_heartbeat_endpoints.py`

`_DATA_KEYS` (line 56) is a dict of meta key -> capability; add `"service_failures": "remediation_executor"`. The heartbeat reply already returns `"enabledCapabilities": sorted(permitted_caps)` (line 531); add `watchedServices` (only when the tenant holds `remediation_executor`) and `isolationConfirmed` beside it. `agent_support.py` reads `agents.meta.response_actions.tokens` (stored wholesale by `agent_heartbeat_endpoints.py` line 157 `update_data[f"meta.{key}"] = value`).

---

### `components/AutonomousOpsDecisions.tsx` (component, polling)

**Analog:** `components/AutonomousOpsRetentionReview.tsx`.
```tsx
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { fetchRetentionReview } from '../services/autonomousOpsApi';
import { useUser } from '../contexts/UserContext';
import { formatWhen } from './AutonomousOpsActivityList';
import { SECONDARY_BUTTON } from './AutonomousOpsHealthCards';
import { HEALTH_SKELETON, HealthCell, HealthChip, HealthNotice } from './AutonomousOpsHealthChips';
export const RETENTION_POLL_MS = 30_000;
const MUTED = 'break-words text-xs text-gray-500 dark:text-gray-400';
```
Fetch functions live in `services/autonomousOpsApi.ts`; add new types and functions there. Per 83-UI-SPEC: `AutonomousOpsActivityList.tsx` is 439 lines, so do not extend it; keep every new file under 500 lines.

### `components/AutonomousOpsResponseSettingsDialogs.tsx`
**Analog:** `components/AutonomousOpsRetentionConfirmDialog.tsx` (exports `RetentionConfirmDialog`, `plural`) for the confirm modal shape; wrap `components/Modal.tsx`.

### Copy gate (every new frontend file and server message module)
Add each to `files` in `shared/autonomous-ops-banned-terms.json` in the same plan that creates it (enforced by `backend/tests/test_autonomous_ops_copy.py`). Never write "ASI", "Autopilot" or "fully autonomous".

---

### Rust: `capabilities/firewall.rs` (+ `response_state.rs`, `quarantine.rs`, `service_watch.rs`)

**Analog:** `agent-install/omni-agent-rs/src/capabilities/remediation_actions.rs`. Current `block_ip` (lines ~187-205) uses cfg-gated bodies and fixed argv:
```rust
#[cfg(target_os = "linux")]
{ run_privileged_command("iptables", &["-I", "INPUT", "-s", &ip.to_string(), "-j", "DROP"]) }
#[cfg(target_os = "windows")]
{ let rule_name = format!("OmniAgent_Block_{ip}");
  run_privileged_command("netsh", &["advfirewall","firewall","add","rule",
     &format!("name={rule_name}"), "dir=in", "action=block", &format!("remoteip={ip}")]) }
#[cfg(not(any(target_os = "linux", target_os = "windows")))]
{ Err(RemediationError::OperationFailed("block_ip is unsupported on this platform.".to_string())) }
```
Keep this three-way cfg split, `RemediationError` variants, and `run_privileged_command` as the only spawn helper (one argv element per parameter, never a shell string). Replace `-I` with `-C` check then `-A` in a dedicated chain, `-w` on every call, `ip6tables` for IPv6, add `dir=out` rule on Windows.
`validate_ip` (`ip_address.parse::<IpAddr>()`) must be tightened: refuse non-global, platform host, gateway, DNS. `validate_service_name` already exists (alnum, `- _ .`, no leading `-`, short critical list); extend the list with Windows-critical names.
`quarantine.rs`: model refusal style on `restore_file` (empty path -> `InvalidPath`, never guess); use `symlink_metadata`, hash-bound move, manifest `<id>.json`.
`response_state.rs`: write `response_state.json` atomically (temp + rename) beside `config.yaml`; reuse `config::save` conventions. Expiry/revert sweeper is a separate tokio task every 15 s plus a startup pass.

### Rust: `instructions.rs` (new arms)

**Analog:** arms at lines 515-545:
```rust
"block_ip" => {
    let ip = item.get("parameters").and_then(|p| p.get("ip_address")).and_then(|v| v.as_str()).unwrap_or("");
    match crate::capabilities::remediation_actions::block_ip(ip).await {
        Ok(()) => serde_json::json!({"status": "success", "message": "IP block initiated"}),
        Err(e) => serde_json::json!({"status": "error", "error": e.to_string()}),
    }
}
```
New arms return `{"status","outcome","verify":{"ok","check"}}`. Unknown commands fall to `Agent does not support instruction '<x>'` (lines 586-593), which is why dormancy must be decided backend-side. Long actions (restart service, isolate self-test) go in `tokio::spawn` because `poll` is awaited by the heartbeat loop. Windows-only code needs `#[cfg(target_os = "windows")]`; do not run `cargo build`.

### Rust: `capabilities/mod.rs` and `heartbeat.rs`

**Analog:** `update_enabled_from_heartbeat` (lines 203-215) and `changed_selection` (lines 237-240):
```rust
pub fn changed_selection(current: Option<&[String]>, body: &Value) -> Option<Vec<String>> {
    let list = serde_json::from_value::<Vec<String>>(body.get("enabledCapabilities")?.clone()).ok()?;
    (current != Some(list.as_slice())).then_some(list)
}
```
Copy for `watchedServices`, persist through `crate::config::save(cfg)` and warn on failure. Add `meta.response_actions` and `meta.service_failures` next to the existing `version`/`meta.capabilities` build (`heartbeat.rs` ~538-553). `capabilities/mod.rs` has uncommitted hunks: commit only your own. Add a `#[cfg(test)]` module like `selection_tests` (mod.rs line ~243).

## Shared Patterns

### Only the gate writes stamped instructions
**Source:** `backend/autonomous_ops/gate.py` (`execute`, `execute_response_task`); `backend/tests/test_autonomous_ops_structural.py` fails on a second stamped writer.
**Apply to:** sweep, followups, dispatcher, fences. Never `db.agent_instructions.insert_one` directly.

### Raw handle and explicit tenant
**Source:** `backend/autonomous_ops/scope.py` (`raw`, `tenant_scope`), used throughout `reconciler.py`.
**Apply to:** every new backend module. `edr_ioc` is not tenant-exempt, so tenant-wrapper reads silently miss global feed rows.

### Permission and session on writes
**Source:** `autonomous_ops_endpoints.py` `_require_manage` (l.120), `_require_control` (l.115), `_require_interactive_session` (l.99).
**Apply to:** settings PUTs (manage), approve/deny/undo/confirm-isolation (control plus MFA session).

### Dormancy before decision
**Source:** `agent_capabilities.allowed_for`, `agents.meta.response_actions.tokens`.
**Apply to:** sweep (no row for dormant), gate (unrecorded refusal), `approvals._revalidate` (re-check at approve time).

### Copy and naming rules (ACTV-08)
**Source:** `shared/autonomous-ops-banned-terms.json`, `backend/tests/test_autonomous_ops_copy.py`, `messages.REASON_TEXT`.
**Apply to:** all new server messages (including fence answers in swarm and SOAR) and UI strings.

### Tests
**Source:** `backend/tests/test_autonomous_ops_gate.py` header (Value/protects/fails_when/no_claim docstring), `from tests._mongo_test_db import mongo_db`, `tests.autonomy_support` (`seed_agent`, `seed_tenant`, `seed_platform_stop`). Private mongod on port 27998 with `GLIBC_TUNABLES=glibc.pthread.rseq=1`. Frontend: vitest (`vitest run`). Do not run the full suite or cargo build here.

## No Analog Found / Weak

| File | Role | Data flow | Reason |
|------|------|-----------|--------|
| `backend/autonomous_ops/incidents.py` | store | CAS grouping by quiet gap | No grouping store exists; use `find_one_and_update` per RESEARCH Q4 |
| `capabilities/service_watch.rs` | service | event-driven | No service watcher in the agent; model the periodic loop on `process_monitor.rs` |
| Isolation (`firewall.rs`) | service | stateful rollback | Only single-rule precedent; follow RESEARCH Q7 ordering (state first, carve-out, verify, block, self-test) |

## Metadata

**Analog search scope:** `backend/`, `backend/autonomous_ops/`, `backend/migrations/`, `backend/tests/`, `components/`, `services/`, `agent-install/omni-agent-rs/src/`
**Tracked-source check:** `git ls-files` confirmed for `reconciler.py`, `threat_feed_sync.py`, `remediation_actions.rs`, `instructions.rs`, `AutonomousOpsActivity.tsx`, `027_retention_gate.py`.
**Not read in full (planner should open before editing):** `gate.py` decide steps, `ledger.py`, `approvals._revalidate`, `registry.py`, `swarm_service.py`/`soar_engine.py` fence sites, `AutonomousOpsActivityList.tsx`, `heartbeat.rs` meta build, vendored default playbooks.
**Pattern extraction date:** 2026-10-31
