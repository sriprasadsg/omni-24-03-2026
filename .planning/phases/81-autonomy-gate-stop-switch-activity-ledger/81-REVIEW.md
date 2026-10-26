---
phase: 81-autonomy-gate-stop-switch-activity-ledger
reviewed: 2026-10-26T00:00:00Z
depth: standard
files_reviewed: 21
files_reviewed_list:
  - backend/autonomous_ops/approvals.py
  - backend/autonomous_ops/dispatch_check.py
  - backend/autonomous_ops/gate.py
  - backend/autonomous_ops/messages.py
  - backend/autonomous_ops/reconciler.py
  - backend/autonomous_ops/settings.py
  - backend/autonomous_remediation_service.py
  - backend/remediation_playbook_service.py
  - backend/tests/autonomy_support.py
  - backend/tests/test_autonomous_ops_approvals.py
  - backend/tests/test_autonomous_ops_breaker.py
  - backend/tests/test_autonomous_ops_dispatch_binding.py
  - backend/tests/test_autonomous_ops_gate.py
  - backend/tests/test_autonomous_ops_ledger.py
  - backend/tests/test_autonomous_ops_reconciler.py
  - backend/tests/test_autonomous_ops_remediation_truth.py
  - backend/tests/test_autonomous_ops_stop.py
  - backend/tests/test_autonomous_ops_structural.py
  - backend/tests/test_autonomous_remediation_loop.py
  - backend/tests/test_remediation_guards.py
  - backend/tests/test_ueba_remediation_trigger.py
findings:
  critical: 0
  warning: 10
  info: 6
  total: 16
status: issues_found
---

# Phase 81: Code Review Report (gap round 81-13..81-18, incremental)

**Reviewed:** 2026-10-26
**Depth:** standard
**Files Reviewed:** 21 (the gap-round source and test files; diff base 840b6d9a2..HEAD plus surrounding code)
**Status:** issues_found

## Summary

The gap round closes both critical findings from the previous report and the three targeted warnings. This is a complete record: it states the disposition of each targeted finding, carries forward the deliberately deferred ones (WR-04..WR-09, IN-01..IN-04) with their original IDs, and adds new findings from the gap-round code (WR-10..WR-13, IN-05..IN-07). No critical issue was found in the committed gap-round code. The user's uncommitted working-tree edits were not judged. No structural (fallow) findings were supplied.

### Disposition of the targeted findings

| ID | Status | Evidence |
|----|--------|----------|
| CR-01 (gate checks only step 1) | **Resolved**, with one residual presentation gap (WR-10) | `dispatch_check.classify` (`dispatch_check.py:67-80`) requires every main step to resolve with class auto or approve and every compensation step to be `undo_only`, and refuses if `steps` disagrees with `actions` (`steps_consistent`, `:55-64`). `gate._step_class` (`gate.py:184-194`) uses it, and `_step_protected_targets` (`gate.py:225-228`) runs `ip_refusal` over `spec_pairs`, i.e. every main and compensation step with its own params. The service now sends per-step params (`_gate_steps`, `autonomous_remediation_service.py:103-108, 449-457`) instead of the first step's. At dispatch, `_authorise` calls `dispatch_check.bind` (`gate.py:439`), which refuses an unregistered command, an agent not in the row's `targets`, a command of the wrong class for the kind, a (command, params) pair that is not one of the decided steps, and re-checks IP parameters against the current never-touch list (fail closed on read errors). `approvals._revalidate` re-checks `row_pairs(row)` (every step plus rollback, `approvals.py:102`), and `undo` refuses a multi-step row (`approvals.py:212`). I traced the vendored `block_ip`, `disable_service` and `rotate_key` playbooks and the XDR response-task path (`playbook_engine_actions` passes the same `task_params` to `decide` and `execute_response_task`); each binds correctly. |
| Cross-tenant playbook selection | **Resolved** | `load_playbooks(db, tenant_id)` (`remediation_playbook_service.py:172-182`) reads the vendored files from disk plus `{"tenantId": tenant_id}` documents only, and `select_playbook` filters again with `_belongs` (`:96-124`): an untenanted document counts only when `source == "vendored"`, a tenanted one only for the same non-empty tenant id. A creator with no tenant id gets a document that nobody can select (fail closed). |
| CR-02 (rolled_back regardless of compensation result) | **Resolved** | `autonomous_remediation_service.py:695-718`: every rollback step is attempted, and the row goes `failed -> rolled_back` only when all return `SUCCESS`; otherwise it stays `failed` with `rollback_incomplete` (text added in `messages.py:79`), an escalation alert is raised and the breaker is evaluated. `ledger.transition` accepts `failed -> failed`, so the reason code is replaced correctly. Residual robustness issue in WR-13. |
| WR-01 (picked-up-but-silent instruction stays dispatching) | **Resolved** | `reconciler.py:114-121` fails a row whose latest instruction has any status other than pending/queued/success/failure once `updatedAt` is older than `AUTONOMOUS_OPS_NO_RESULT_MIN` (default 1440, floor = the not-delivered bound, `:64-67`), reason `no_result`, with a compare-and-set on `updatedAt`. The response-task half of the old finding (a task delivered but still `queued` is failed as `not_delivered` after 30 minutes) is unchanged; I judge it acceptable because response tasks report within seconds and the mislabel only matters for a task that runs longer than 30 minutes. See WR-12 for a new reconciler/remediation race. |
| WR-02 (manual level change leaves breaker disabled) | **Resolved** | `settings.set_level` (`settings.py:174-190`) clears `breaker` atomically with `find_one_and_update(... ReturnDocument.BEFORE)` when the level becomes `undoable_auto`, and records `level_restored` when a breaker was actually set. Suggest and Off intentionally leave it. `above_max` is checked first, so a refused change clears nothing. Covered by `test_autonomous_ops_breaker.py:200-241`. |
| WR-03 (shadow master fails open; read once at import) | **Resolved** | `settings.master_shadow` (`settings.py:100-111`) is off only for `0/false/no/off` after strip/lower, so unset, empty and unrecognised values stay in shadow. The service no longer holds an import-time copy or passes `master_shadow=` (`autonomous_remediation_service.py:28, 471`), so `gate.decide` reads the variable on every decision for every entry point. A structural test pins both facts. |
| Structural-scan crash | **Resolved** | `_parse` returns None for a file that does not parse; the stamp scan falls back to a textual match and an unparsable file on the autonomous path fails the test (`test_autonomous_ops_structural.py`). |

No cross-tenant read or write path, injection route or new authorization gap was found in the changed code.

## Critical Issues

None.

## Warnings

### WR-10: An approval card for a multi-step playbook shows only the first step

**File:** `backend/autonomous_ops/views.py:179-190, 216-232`; `backend/autonomous_ops/gate.py:350-358`
**Issue:** The gate now records the whole plan in `steps` and `rollback`, and the dispatch is bound to it, but `present_row` still renders the row from `row.command` and `row.target` only (`_action_label` reads `command`, `target` is the first spec's IP or `targets[0]`). A person approving a two-step operator playbook (for example `restart_service` then `block_ip <other address>`) sees one action. The gap is narrower than the old CR-01 (the second step is now IP-checked, class-checked and bound to the row), but the approval no longer shows everything it authorises (GATE-10), and the Activity list reads a three-step row as one action.
**Fix:** When `len(row.get("steps") or []) > 1`, append "and N more step(s)" to the label (and list every step's command and target in the card detail). Do the same for rollback steps.

### WR-11: A multi-step playbook that fails part-way leaves the earlier steps applied with no put-back and no escalation

**File:** `backend/autonomous_remediation_service.py:659-674`
**Issue:** Steps run in order, and on the first step that is not `SUCCESS` (refused, `FAILURE` or `TIMEOUT`) the row is marked `failed` with `dispatch_failed` ("not confirmed by the host") and the method returns `unverified`. Steps that already succeeded are neither compensated nor escalated: compensation only runs after a failed verification. The gate now deliberately admits multi-step operator playbooks, so this is reachable: step 1 disables a service, step 2 fails, and the Activity shows a plain failure while the service stays disabled. A `TIMEOUT` is also recorded as failed although the instruction can still run after the 60 s poll window, and the reconciler ignores the row once it is terminal.
**Fix:** After a failed step with at least one earlier `SUCCESS`, either run the compensation steps for the steps already done (and apply the CR-02 rule: `rolled_back` only when confirmed, otherwise `rollback_incomplete` plus `_escalate`), or at minimum raise the `_escalate` alert with the list of steps applied. Record in the reason text that earlier steps ran.

### WR-12: The reconciler can complete a ledger row in the middle of a multi-step remediation, and step 2 is then refused

**File:** `backend/autonomous_ops/reconciler.py:99-105`; `backend/autonomous_remediation_service.py:659-663`; `backend/autonomous_ops/gate.py:56`
**Issue:** While `_dispatch_and_verify` runs, the row is `dispatching` and `_latest_status` looks at the last linked instruction. Once step 1's instruction reports success, the reconciler (every 60 s) moves the row to `executed`. If that happens inside the 2 s poll gap before the service writes step 2, `gate.execute` finds state `executed`, which is not in `_DISPATCHABLE["action"] = ("approved", "dispatching")`, returns `not_dispatchable`, and the remediation fails with `dispatch_failed` although step 1 succeeded (and, per WR-11, nothing is put back). The window is a few percent per step boundary and grows with slow polling. Single-step playbooks are not affected because the service writes the same transition itself.
**Fix:** Do not let the reconciler claim rows owned by a live remediation. For example, make `_dispatch_and_verify` hold a `remediation_inflight` lease marker the reconciler honours (skip rows whose `remediationId` has an unexpired lease), or have the reconciler treat a row whose `steps` has more than one entry as complete only when the number of linked instructions equals the number of steps.

### WR-13: `_escalate` can raise, which skips the breaker evaluation and leaves the request row stuck in "dispatching"

**File:** `backend/autonomous_remediation_service.py:709-722, 727-742`
**Issue:** In the verify-failed branch `_escalate` (an `alerts.insert_one` plus an audit write) runs before `_evaluate_breaker` and before `remediation_requests` is updated. Neither is guarded, so a transient database error in the alert insert propagates out of `_dispatch_and_verify` (only the lease is released in `finally`). The safety control that exists to stop repeated bad automatic actions (`_evaluate_breaker`) is skipped, the `remediation_requests` row stays `dispatching`, and the caller sees an exception. CR-02 made this path run for every incomplete rollback, so it is reachable more often than the old no-rollback branch.
**Fix:** Make `_escalate` never raise (wrap in `try/except`, log) and call `_evaluate_breaker` before it, or put both in the `finally` ordering so the breaker evaluation and the request-status update always run.

### WR-04: The tenant never-touch list shows platform-wide stored entries to every tenant viewer (carried forward, unchanged)

**File:** `backend/autonomous_ops/views.py:343-357`; `backend/autonomous_ops_endpoints.py:302-317`
**Issue:** `visible_entries` hides built-in entries that expose this server from non-staff, but stored platform-scope entries (added by a Super Admin: platform servers, gateways, free-text note) have `builtin=False` and are passed through to any tenant user with only `view:autonomous_ops`.
**Fix:** Treat `entry.scope == "platform"` like a hidden built-in for non-staff viewers:
```python
if (entry.builtin and entry.id not in general or entry.scope == "platform") and not viewer_is_platform_staff:
    hidden = True
    continue
```

### WR-05: Approving a remediation card runs the whole dispatch, poll and verify cycle inside the HTTP request (carried forward, unchanged)

**File:** `backend/autonomous_remediation_service.py:559-581`; `backend/autonomous_ops/approvals.py:153-166`; `backend/remediation_control_endpoints.py:127-134`
**Issue:** The `remediation` dispatcher awaits `_dispatch_and_verify`, which can block up to 60 s per step, 60 s for verification, 60 s for the scan probe, plus compensation. `ueba_service` runs the same function in a background task for this reason. Both approve routes await it inline, so a proxy timeout cuts the response while the work continues, and a second click returns `already_handled`.
**Fix:** Have `dispatch_approved_remediation` do the compare-and-set and schedule `_dispatch_and_verify` with `asyncio.create_task` (held in a module-level set), returning `{"status": "dispatching"}`; `approvals.approve` already treats any non-refused dict as dispatched.

### WR-06: `monitor_agent_status` can mark an agent that just checked in as Offline (carried forward, unchanged)

**File:** `backend/app_background_tasks.py:38-51`
**Issue:** The stale agents are read first and then updated by id with `status: "Online"` but without the `lastSeen < threshold` condition, so a heartbeat landing between the read and the write is overwritten, and the notification loop covers all `stale` agents rather than those actually changed.
**Fix:** Keep the staleness condition in the write (`{"id": {"$in": ids}, "status": "Online", "lastSeen": {"$lt": threshold}}`) and notify only agents confirmed changed (or use a per-agent `find_one_and_update` with that filter).

### WR-07: The UEBA containment path defeats the gate's own dedupe, so a repeated anomaly opens a new approval card every second (carried forward, unchanged)

**File:** `backend/autonomous_remediation_service.py:448-460` (dedupe key); caller `backend/ueba_service.py:100-123`
**Issue:** The dedupe key includes `finding_id`, which UEBA builds with a timestamp to the second, so each event gets a distinct key; the caller's own `is_duplicate_task(action="remediate_anomaly")` looks for `response_tasks` rows nothing writes.
**Fix:** Use a stable finding id (`UEBA-{agent}-{rule}`) so the open-row dedupe applies, and remove the dead `is_duplicate_task` call.

### WR-08: Fenced automatic playbook steps lose the old 10-minute duplicate guard, and nothing replaces it once an automatic row finishes (carried forward, unchanged)

**File:** `backend/playbook_engine_actions.py:224-238`; `backend/autonomous_ops/gate.py:279-300`
**Issue:** For an automatic run `_action_block_ip` returns at `if fenced is not None` before the `response_tasks` duplicate check. The gate dedupes only open rows, shadow rows younger than 24 h and undone rows younger than 24 h; once an automatic action reaches `executed` or `failed` a repeated correlation opens a fresh decision at once. Repeated `quarantine_file` attempts fail and three failures trip the breaker; `restart_service` can restart up to the 20 per hour limit. The same applies to a `failed` row with `rollback_incomplete`.
**Fix:** Add a short cooldown for recently finished automatic rows (`state in ("executed","verified","failed")`, `createdAt` within ten minutes) to `_step_dedupe`.

### WR-09: The remediation deny route stores an unvalidated, unbounded reason (carried forward, unchanged)

**File:** `backend/remediation_control_endpoints.py:137-149`
**Issue:** `body: Dict[str, Any]` and `reason = (body or {}).get("reason", "")` accept any JSON value and length into `approval.reason` and the immutable `remediation_audit`. The sibling route `/api/autonomous-ops/actions/{id}/deny` caps the reason at 500 characters and requires a string.
**Fix:** Reuse `DecisionBody` from `autonomous_ops_endpoints` (or a model with `StringConstraints(strip_whitespace=True, max_length=500)`).

## Info

### IN-01: Dead code left behind by the removal of the scheduled cycle (carried forward; still applies)

**File:** `backend/autonomous_remediation_service.py:126-380`, `:29, :46, :120-124`; `backend/autonomous_ops/ledger.py:175-191`
**Issue:** `scan_for_remediable_findings` (about 250 lines) has no caller; `MAX_AUTO_SEVERITY` and `_severity_within_ceiling` are used only by it; `ledger.list_actions` is unused. The service file is 904 lines against the project's 500-line rule (CLAUDE.md), and the dead scan is most of the excess.
**Fix:** Delete the scan method and its helpers (or move them out and test them as retained API) and delete or use `ledger.list_actions`.

### IN-02: Mislabelled and fragile reason handling (carried forward; still applies)

**File:** `backend/autonomous_ops/approvals.py:161-163`; `backend/autonomous_ops/gate.py:320-325`
**Issue:** A stop that lands after approval fails the row with reason code `platform_stop` even for a tenant stop. `_display_target` calls `req.params.get(key)` while its neighbours guard with `req.params or {}`; `params=None` with an IP-bearing spec raises `AttributeError` out of `decide`.
**Fix:** Pass the real code (`platform_stop` or `tenant_stop`) and use `(req.params or {}).get(key)`.

### IN-03: Superseded

The class-check part of the old IN-03 (only the first spec's class was validated) is fixed by `classify`. The presentation part (a multi-step row reads as one action) is now WR-10.

### IN-04: Core safety tests skip silently when no MongoDB is reachable (carried forward; still applies)

**File:** `backend/tests/_mongo_test_db.py` and every real-database test, including the new `test_autonomous_ops_dispatch_binding.py`, `test_autonomous_ops_remediation_truth.py` and the breaker tests
**Issue:** The `mongo_db` fixture calls `pytest.skip` when `127.0.0.1:27017` is unreachable, so the gate, binding, rollback-truth and breaker guarantees report "skipped" and the run is green on a machine without Mongo.
**Fix:** Fail instead of skip when `CI` or `REQUIRE_MONGO` is set, and print a skipped-test summary for the Autonomous Ops suites.

### IN-05: `step_count` treats a legacy row with several `actions` as one step

**File:** `backend/autonomous_ops/dispatch_check.py:130-135`
**Issue:** For a row written before the plan was recorded (no `steps` list) it returns 1 whenever `command` is set. The old service wrote `actions` for every playbook step and `command` for the first, so such a legacy multi-step row still passes the `step_count(row) > 1` guard in `approvals.undo` and can be "undone" by one instruction, the ACTV-01 gap the guard exists to close. It only matters for rows that predate the gap round (likely none outside development databases).
**Fix:** In the legacy branch return `max(1, len(row["actions"]))` when `actions` is a non-empty list.

### IN-06: Tests patch a module attribute that no longer exists

**File:** `backend/tests/test_autonomous_ops_remediation_truth.py:100, 160`; `backend/tests/test_autonomous_ops_dispatch_binding.py:43`
**Issue:** `patch("autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN", False, create=True)` creates an attribute that the service no longer reads (a structural test asserts it is absent). The patch is dead and suggests the old override still matters; the environment patch beside it is what turns shadow off.
**Fix:** Delete the three `create=True` patches.

### IN-07: `load_playbooks` truncates silently and relies on database order for overrides

**File:** `backend/remediation_playbook_service.py:180-181`
**Issue:** `to_list(length=200)` drops a tenant's playbooks beyond the first 200 without notice, and "a later document of the same name overrides an earlier one" depends on Mongo's natural order because the query has no sort. Selection is documented as deterministic.
**Fix:** Sort by `createdAt`/`id` before extending the list, and log a warning when the 200 cap is reached.

---

_Reviewed: 2026-10-26_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
