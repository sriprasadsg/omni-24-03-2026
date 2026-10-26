---
phase: 81-autonomy-gate-stop-switch-activity-ledger
reviewed: 2026-10-26T00:00:00Z
depth: standard
files_reviewed: 93
files_reviewed_list:
  - App.tsx
  - backend/agent_capabilities.py
  - backend/agent_instruction_endpoints.py
  - backend/agent_tasks_endpoints.py
  - backend/app_background_tasks.py
  - backend/app_startup.py
  - backend/authentication_endpoints.py
  - backend/autonomous_ops/__init__.py
  - backend/autonomous_ops/approvals.py
  - backend/autonomous_ops/breaker.py
  - backend/autonomous_ops/delivery.py
  - backend/autonomous_ops/gate.py
  - backend/autonomous_ops/ledger.py
  - backend/autonomous_ops/messages.py
  - backend/autonomous_ops/notify.py
  - backend/autonomous_ops/protected.py
  - backend/autonomous_ops/reconciler.py
  - backend/autonomous_ops/registry.py
  - backend/autonomous_ops/scope.py
  - backend/autonomous_ops/settings.py
  - backend/autonomous_ops/stop.py
  - backend/autonomous_ops/views.py
  - backend/autonomous_ops_endpoints.py
  - backend/autonomous_ops_platform_endpoints.py
  - backend/autonomous_remediation_service.py
  - backend/backend_safety.py
  - backend/catalogue_mounts_autonomous_ops.py
  - backend/correlation_engine_threat.py
  - backend/deployment_result_endpoints.py
  - backend/distributed_lock.py
  - backend/migrations/024_autonomous_ops.py
  - backend/playbook_engine_actions.py
  - backend/playbook_engine_execution.py
  - backend/rbac_defaults.py
  - backend/remediation_control_endpoints.py
  - backend/response_orchestrator.py
  - backend/router_registry.py
  - backend/tenant_endpoints.py
  - backend/tests/_autonomous_ops_http.py
  - backend/tests/_route_walk.py
  - backend/tests/autonomy_support.py
  - backend/tests/test_admin_mfa_required.py
  - backend/tests/test_agent_capabilities.py
  - backend/tests/test_agent_instruction_poll_tenant_scoping.py
  - backend/tests/test_autonomous_ops_approvals.py
  - backend/tests/test_autonomous_ops_breaker.py
  - backend/tests/test_autonomous_ops_copy.py
  - backend/tests/test_autonomous_ops_endpoints.py
  - backend/tests/test_autonomous_ops_endpoints_writes.py
  - backend/tests/test_autonomous_ops_gate.py
  - backend/tests/test_autonomous_ops_gate_order.py
  - backend/tests/test_autonomous_ops_isolation.py
  - backend/tests/test_autonomous_ops_ledger.py
  - backend/tests/test_autonomous_ops_migration.py
  - backend/tests/test_autonomous_ops_permissions.py
  - backend/tests/test_autonomous_ops_protected.py
  - backend/tests/test_autonomous_ops_reconciler.py
  - backend/tests/test_autonomous_ops_registry.py
  - backend/tests/test_autonomous_ops_stop.py
  - backend/tests/test_autonomous_ops_structural.py
  - backend/tests/test_autonomous_ops_xdr_fence.py
  - backend/tests/test_autonomous_remediation_loop.py
  - backend/tests/test_catalogue_manifest.py
  - backend/tests/test_catalogue_slice_autonomous_ops.py
  - backend/tests/test_closure_delivery.py
  - backend/tests/test_custom_role_mfa.py
  - backend/tests/test_distributed_lock.py
  - backend/tests/test_monitor_agent_status.py
  - backend/tests/test_platform_roles.py
  - backend/tests/test_rbac_defaults.py
  - backend/tests/test_remediation_guards.py
  - backend/tests/test_response_orchestrator_tenant.py
  - backend/tests/test_role_visibility.py
  - backend/tests/test_ueba_remediation_trigger.py
  - components/AutonomousOpsActivity.tsx
  - components/AutonomousOpsActivityList.tsx
  - components/AutonomousOpsStatusCard.tsx
  - components/AutonomousOpsStopBanner.tsx
  - components/AutonomousOpsStopDialog.tsx
  - components/sidebarPresentation.tsx
  - contexts/AutonomousOpsStatusContext.tsx
  - services/autonomousOpsApi.ts
  - shared/autonomous-ops-banned-terms.json
  - shared/catalogue-access.json
  - shared/tenant-feature-switches.json
  - src/__tests__/AutonomousOpsActivity.test.tsx
  - src/__tests__/AutonomousOpsStatusCard.test.tsx
  - src/__tests__/AutonomousOpsStatusCardStates.test.tsx
  - src/__tests__/AutonomousOpsStopBanner.test.tsx
  - src/__tests__/_autonomousOpsCardHarness.tsx
  - src/__tests__/autonomousOpsCopy.test.ts
  - src/__tests__/catalogueAccess.test.ts
  - types.ts
findings:
  critical: 2
  warning: 9
  info: 4
  total: 15
status: issues_found
---

# Phase 81: Code Review Report

**Reviewed:** 2026-10-26
**Depth:** standard
**Files Reviewed:** 93
**Status:** issues_found

## Summary

The committed phase changes (diff base 6e7664746..HEAD) were reviewed; the user's uncommitted working-tree edits were not reported. The package `backend/autonomous_ops/` is carefully built: tenant isolation through the raw handle with explicit tenantId everywhere, compare-and-set transitions, fail-closed stop reads, write-ahead ledger rows, and delivery hold-back hooks on all three mounted instruction/response polls. The two routers enforce interactive-session and per-tenant resolution correctly. I found no cross-tenant read/write path and no injection route.

The defects concentrate where the gate meets the remediation service. The gate decides on one request (first playbook step's parameters) while `autonomous_remediation_service` goes on to execute every step and every rollback step with parameters the gate never evaluated, and it records a rollback as done without checking that it happened. Several lifecycle edges (reconciler for picked-up-but-silent instructions, circuit breaker after a manual level change, fail-open parsing of the shadow master switch) leave rows or safety state wrong.

No structural (fallow) findings were supplied for this review.

## Critical Issues

### CR-01: Gate evaluates only the first playbook step; later steps and rollback steps run with parameters the gate never checked

**File:** `backend/autonomous_remediation_service.py:440-459` (request built), `backend/autonomous_remediation_service.py:717-740` (per-step dispatch), `backend/autonomous_ops/gate.py:205-233` and `:453-472`
**Issue:** `_remediate` builds one `ActionRequest` whose `params` are the rendered params of `steps[0]` only (`first_params`), while `actions` lists every step. `gate._step_protected_targets` then runs the never-touch IP check for every spec's `ip_params` against that one shared `params` dict. `_dispatch_step` later calls `gate.execute(..., command=ACTION_MAP[action], params=<this step's own params>)` for steps 2..n and for rollback steps (kind `compensate`). `gate.execute` only checks the ledger row's state and the stop; it does not check that `command`, `agent_id` or `params` match what the row was decided on, nor that the command is in the registry. Consequences:
1. Never-touch bypass (GATE-08): an operator-authored playbook (tenant admins create them through `remediation_playbook_endpoints`, validated only against `ACTION_MAP`, and a playbook named `block_ip` overrides the vendored one in `select_playbook`'s `by_name`) with steps `[block_ip <benign ip>, block_ip <platform/management ip>]` passes the gate (only step 1's IP is checked) and then blocks the protected address.
2. Approval-card integrity (GATE-10): the card the person approves shows only the first step's command (`row.command`, `row.params`); the approved dispatch runs the whole stored playbook.
3. `_step_class` (gate.py:185) only validates `specs[0].cls`; a later `undo_only` or `probe` command is treated as automatic.
4. Rollback steps are never classified, never IP-checked and never registry-checked.

The vendored single-step playbooks are not affected, which is why the tests pass; the hole is the operator-playbook path the same service supports.
**Fix:** Make the gate the check for exactly what is dispatched.
```python
# gate.py: bind a dispatch to the decided row
async def execute(db, tenant_id, action_id, *, command, agent_id, params, kind="action"):
    row, reason = await _authorise(db, tenant_id, action_id, kind)
    if row is None:
        return {"status": "refused", "reason": reason}
    if registry.resolve(command) is None:
        return {"status": "refused", "reason": "unregistered_action"}
    if agent_id not in (row.get("targets") or []):
        return {"status": "refused", "reason": "target_mismatch"}
    spec = registry.resolve(command)
    for key in spec.ip_params:
        if params.get(key) is not None and await protected.check(db, tenant_id, ip=params[key]):
            return {"status": "refused", "reason": "protected_target"}
```
and in `_remediate`, either restrict a remediation request to single-step playbooks, or render all steps' params and have the gate check every step's IP parameters (a per-step `params` list on `ActionRequest`), validate every `specs[i].cls` in `("auto", "approve")`, and validate rollback actions (they are `undo_only` commands) before the row is created.

### CR-02: Rollback is recorded as "rolled_back" (shown to the person as "Undone.") without checking that any compensation happened

**File:** `backend/autonomous_remediation_service.py:683-692`
**Issue:** After a failed verification the code dispatches each rollback step with `_dispatch_step(..., "compensate")` but never inspects the returned status. `_dispatch_step` returns `{"status": "refused"}` when `gate.execute` refuses (insert failure, `not_dispatchable`), and `"FAILURE"` or `"TIMEOUT"` when the agent fails or does not answer in 60 s. All of those are appended to `rollback_dispatched` and the row is then moved `failed -> rolled_back` unconditionally, and the result is returned with `rollback_dispatched: True`. `views.STATE_RESULT["rolled_back"]` renders "Undone.", the Activity bucket is "undone", and the breaker counts the row as a clean undo. A block that was never lifted, a service that was never re-enabled, is shown to the operator as put back.
**Fix:**
```python
rollback_dispatched = []
for step in rollback_steps:
    rollback_dispatched.append(await self._dispatch_step(finding, step, action_id, "compensate"))
all_ok = all(r.get("status") == "SUCCESS" for r in rollback_dispatched)
await write_audit(db, tenant_id, {**base_record, "stage": "rollback_dispatched",
                                  "rollback_steps": rollback_dispatched, "complete": all_ok})
if all_ok:
    await self._mark(db, tenant_id, action_id, ("failed",), "rolled_back")
else:
    await self._mark(db, tenant_id, action_id, ("failed",), "failed",
                     reasonCode="rollback_incomplete",
                     reasonText="The check afterwards failed and putting it back was not confirmed.")
    # raise the same human-review alert the no-rollback branch raises
result["rollback_dispatched"] = all_ok
```
Add `rollback_incomplete` to `messages.REASON_TEXT`.

## Warnings

### WR-01: A dispatched instruction that is picked up but never reports leaves its row in "dispatching" forever

**File:** `backend/autonomous_ops/reconciler.py:37-41, 89-105`
**Issue:** The reconciler only fails a stale row when the latest instruction status is missing or in `{"pending", "queued"}`. The poll endpoints set status `sent` (agent_tasks_endpoints) or `delivered` (deployment_result_endpoints), neither of which is in `_SUCCESS`, `_FAILURE` or `_UNDELIVERED`. An agent that takes the instruction and then crashes, is uninstalled or loses connectivity leaves the row in `dispatching` indefinitely: it stays in the Pending bucket, keeps the tenant in every reconciler pass, and its `open_dedupe` unique-index entry blocks that action for that tenant forever. Response tasks have the opposite problem: `get_pending_tasks` never marks `queued` tasks as delivered, so a task that was delivered and is still running is failed `not_delivered` after 30 minutes (and later counts as a breaker failure).
**Fix:** Treat any non-terminal status other than a result as "no outcome yet" and apply a second, longer timeout (for example `AUTONOMOUS_OPS_NO_RESULT_MIN`, default 24 h) that fails the row with a distinct reason code, for example `no_result`:
```python
_IN_FLIGHT = _UNDELIVERED | {"sent", "delivered", "in_progress", "running"}
elif old and (status is None or status in _IN_FLIGHT):
    reason = "not_delivered" if status in (None, *_UNDELIVERED) else "no_result"
```

### WR-02: Setting the level by hand while the breaker is tripped silently disables the breaker for that tenant

**File:** `backend/autonomous_ops/settings.py:159-171` (with `backend/autonomous_ops/breaker.py:42`)
**Issue:** `PUT /settings/level` (`set_level`) writes only `level`. The tripped `breaker` document stays set. `breaker.evaluate` returns early when `s.breaker is not None`, so after a manager raises the level back with the ordinary level route (not `restore-level`) the circuit breaker can never trip again for that tenant, and the status card keeps showing the "Lowered from ..." notice. Nothing tells the operator.
**Fix:** In `set_level`, when the stored `breaker` is non-null and the new level is above `suggest`, either clear it in the same update (and write a `level_restored` control row) or refuse with `{"status": "breaker_tripped"}` so the person uses `restore-level`.

### WR-03: The shadow-mode master switch fails open on an unrecognised value, and the remediation path reads it only once at import

**File:** `backend/autonomous_remediation_service.py:28, 460`; `backend/autonomous_ops/settings.py:100-103`
**Issue:** `AUTONOMOUS_REMEDIATION_DRY_RUN` is the deployment-wide "nothing is carried out" switch (D-02). Both parsers treat only `1/true/yes` as on, so any other value, including `on`, `y`, `enabled`, or `"true "` (the service's copy does not `strip()`), turns shadow mode off and makes the deployment live. Also `autonomous_remediation_service` evaluates the variable once at import and passes it as `master_shadow=`, while `settings.master_shadow()` documents "read on every call" and the XDR fence calls `gate.decide` without an argument. The two autonomous entry points can therefore disagree after an environment change, and operators who flip the variable at runtime see only the XDR path change.
**Fix:** Make shadow the default and require an explicit off value, and use one reader:
```python
def master_shadow() -> bool:
    return os.getenv(_MASTER_ENV, "true").strip().lower() not in ("0", "false", "no", "off")
```
and in `_remediate` call `gate.decide(db, request)` with no `master_shadow` override (delete the module constant).

### WR-04: The tenant never-touch list shows platform-wide stored entries to every tenant viewer

**File:** `backend/autonomous_ops/views.py:343-357`; `backend/autonomous_ops_endpoints.py:302-317`
**Issue:** `visible_entries` hides built-in entries that expose this server (interface addresses, env hosts, platform agents) from non-staff, and says "no platform address is disclosed". Stored platform-scope entries (`scope == "platform"`, added by a Super Admin, typically the platform's own servers, gateways or other infrastructure IPs and host names, plus a free-text note) have `builtin=False`, so they are passed through `entry_view` unchanged to any tenant user holding only `view:autonomous_ops` (including the analyst role).
**Fix:** Apply the same rule to stored platform entries:
```python
if (entry.builtin and entry.id not in general or entry.scope == "platform") and not viewer_is_platform_staff:
    hidden = True
    continue
```

### WR-05: Approving a remediation card runs the whole dispatch, poll and verify cycle inside the HTTP request

**File:** `backend/autonomous_remediation_service.py:559-581`; `backend/autonomous_ops/approvals.py:157-170`; `backend/remediation_control_endpoints.py:127-134`
**Issue:** The `remediation` dispatcher calls `_dispatch_and_verify`, which waits up to `STEP_POLL_TIMEOUT_SEC` (60 s) per step, `VERIFY_TIMEOUT_SEC` (60 s) for verification plus another 60 s for the scan probe, and then compensation. `ueba_service` explicitly runs the same function in a background task because it "can block up to ~120s". Both approve routes (`/api/autonomous-ops/actions/{id}/approve` and `/api/remediation/{id}/approve`) await it inline, so a reverse proxy with a 60 s timeout will cut the response while the work continues; the user sees a failure, clicks again and gets `already_handled`.
**Fix:** Have `dispatch_approved_remediation` do only the CAS and first dispatch, then schedule `_dispatch_and_verify` with `asyncio.create_task` (kept in a module-level set), and return `{"status": "dispatching"}`. `approvals.approve` already treats any non-"refused" dict as dispatched.

### WR-06: `monitor_agent_status` can mark an agent that just checked in as Offline

**File:** `backend/app_background_tasks.py:38-51`
**Issue:** The rewrite first reads the stale Online agents, then updates by id with `{"id": {"$in": ids}, "status": "Online"}`. The previous single `update_many` carried the `lastSeen < threshold` condition, so it was atomic. Now an agent whose heartbeat lands between the read and the write is flipped to Offline (and a websocket event and `agent.offline` notification are sent for it) although it is online; it only recovers on its next heartbeat. The notification loop also iterates all `stale` agents, not the ones the update actually changed.
**Fix:** Keep the staleness condition in the write, and notify only ids confirmed changed:
```python
result = await db.agents.update_many(
    {"id": {"$in": ids}, "status": "Online", "lastSeen": {"$lt": threshold}},
    {"$set": {"status": "Offline"}})
flipped = [a for a in stale if a["id"] in {d["id"] async for d in
           db.agents.find({"id": {"$in": ids}, "status": "Offline"}, {"id": 1, "_id": 0})}]
```
(or use a per-agent `find_one_and_update` with the same filter and collect the winners).

### WR-07: The UEBA containment path defeats the gate's own dedupe, so a repeated anomaly opens a new approval card every second

**File:** `backend/autonomous_remediation_service.py:448`; caller `backend/ueba_service.py:100-123`
**Issue:** The gate dedupes on `dedupe_key = tenant|playbook|finding_type|finding_id`. UEBA builds `finding_id` with a timestamp to the second (`UEBA-{agent}-{rule}-{%Y%m%d%H%M%S}`), so every event gets a distinct key and never matches an open row. The caller's own guard, `is_duplicate_task(action="remediate_anomaly")`, looks for `response_tasks` rows that nothing writes (the string appears nowhere else), so it never fires either. Each shadow-AI event for the same agent therefore creates its own `kill_process` approval card (approval class) and fills the ledger.
**Fix:** Give anomalies a stable finding id (`UEBA-{agent}-{rule}`) so the gate's open-row dedupe applies, and remove the dead `is_duplicate_task` call.

### WR-08: Fenced automatic playbook steps lose the old 10-minute duplicate guard, and nothing replaces it once an automatic row finishes

**File:** `backend/playbook_engine_actions.py:224-238` (guard now bypassed by the early `return fenced`); `backend/autonomous_ops/gate.py:280-301`
**Issue:** For an automatic run `_action_block_ip` returns at `if fenced is not None` before the existing `response_tasks` duplicate check. The gate's dedupe refuses only while a row is open (`suggested`, `awaiting_approval`, `approved`, `dispatching`), a shadow row is younger than 24 h, or an undone row is younger than 24 h. Once an automatic action reaches `executed` (terminal, so it leaves the unique `open_dedupe` index) a repeated XDR correlation immediately opens a fresh decision for the same tenant, command, agent and target. For `quarantine_file` the second attempt fails (file already moved), which writes `failed` rows, and three of them trip the circuit breaker and drop the tenant to Suggest; `restart_service` can restart up to the 20 per hour rate limit. GATE-03 names "cooldown", but cooldown is only applied after shadow and undo.
**Fix:** Add a short cooldown for finished automatic rows to `_step_dedupe` (for example `state in ("executed","verified","failed")` and `createdAt > now - timedelta(minutes=10)` returns `duplicate`), or key the gate's open-dedupe on the playbook execution rather than leaving the window empty.

### WR-09: The remediation deny route stores an unvalidated, unbounded reason

**File:** `backend/remediation_control_endpoints.py:137-149`
**Issue:** `body: Dict[str, Any] = Body(default={})` and `reason = (body or {}).get("reason", "")` accept any JSON value and any length. The value is stored in `approval.reason` and in `remediation_audit` (immutable audit records). The sibling route `/api/autonomous-ops/actions/{id}/deny` caps the reason at 500 characters and requires a string. CLAUDE.md requires validation at system boundaries.
**Fix:** Use the same model: `class DenyBody(BaseModel): reason: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]] = None`, or import `DecisionBody` from `autonomous_ops_endpoints`.

## Info

### IN-01: Dead code left behind by the removal of the scheduled cycle

**File:** `backend/autonomous_remediation_service.py:126-380`, `:29, :46, :120-124`; `backend/autonomous_ops/ledger.py:175-191`
**Issue:** `scan_for_remediable_findings` (about 250 lines) has no caller since `autonomous_remediation_loop` was deleted (the only live caller of the service is `ueba_service.remediate`). `MAX_AUTO_SEVERITY` and `_severity_within_ceiling` are used only by it, `SEVERITY_ORDER` only by `response_orchestrator`. It also references `_tctx` in `finally` blocks that can raise `UnboundLocalError` if `set_tenant_id` fails. `ledger.list_actions` is unused (the routes use `views.list_page`).
**Fix:** Delete the scan method and its helpers (move `SEVERITY_ORDER` next to its one user), or document and test it as retained API; delete `ledger.list_actions` or make `views.list_page` use it.

### IN-02: Mislabelled and fragile reason handling

**File:** `backend/autonomous_ops/approvals.py:165-167`; `backend/autonomous_ops/gate.py:321-326`
**Issue:** When a stop lands after approval, the row is failed with reason code `platform_stop` even for a tenant stop, so the Activity text says "stopped for the whole platform". `_display_target` calls `req.params.get(key)` while every neighbour uses `req.params or {}`; a request with `params=None` and an IP-bearing spec raises `AttributeError` out of `decide` instead of being refused.
**Fix:** Pass the real code (`platform_stop` or `tenant_stop`, which `gate._stopped` could return) and use `(req.params or {}).get(key)`.

### IN-03: `_step_class` accepts "approve" style classification by inspection of the first action only, leaving unreachable states in the trace

**File:** `backend/autonomous_ops/gate.py:181-192`
**Issue:** The first spec decides `unregistered_action`; later specs are not class-checked (see CR-01). In addition, the multi-action `actions` list is stored in the row but only `command = specs[0].name` and the first action's undo block are shown or used, so the Activity row for a three-step playbook reads as one action.
**Fix:** Covered by CR-01; also show a "+N more steps" suffix in `views._action_label` when `len(row["actions"]) > 1`.

### IN-04: Core safety tests skip silently when no MongoDB is reachable

**File:** `backend/tests/_mongo_test_db.py` (fixture), used by `test_autonomous_ops_gate*.py`, `_stop.py`, `_approvals.py`, `_reconciler.py`, `_breaker.py`, `_xdr_fence.py`, `_endpoints*.py`
**Issue:** `mongo_db` calls `pytest.skip` when `127.0.0.1:27017` is not reachable. On a CI runner or developer machine without Mongo the whole gate, stop, approval, ledger and isolation suite reports "skipped" and the run is green, so the phase's guarantees are unverified without anyone noticing.
**Fix:** Fail (not skip) when `CI` or a `REQUIRE_MONGO` environment variable is set, and print a summary of skipped Autonomous Ops tests in the CI job.

---

_Reviewed: 2026-10-26_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
