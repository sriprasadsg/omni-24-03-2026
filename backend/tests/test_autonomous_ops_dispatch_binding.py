"""Decide-time half of Gap 1 (81-VERIFICATION, CR-01): the gate checks EVERY step and EVERY
compensation step of a playbook, each with its own parameters, and records the decided plan.

proves=GATE-03 GATE-04 GATE-08 GATE-10 ACTV-01 (plans 81-13, 81-15, 81-18)
fails_when=a later step or a compensation step aimed at a never-touch address is accepted, a
step that is not a registered auto/approve command (or a compensation step that is not
undo_only) reaches a recorded decision, the decided row loses its steps/rollback, or a
multi-step row offers a one-instruction undo.

Real throwaway Mongo (tests/_mongo_test_db.py); nothing here reaches a live system.
"""
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from autonomous_ops import approvals, dispatch_check, gate, ledger, protected
from autonomous_remediation_service import AutonomousRemediationService, RemediationFinding
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import agent_that_completes, seed_agent, seed_platform_stop, seed_tenant

BAD = "127.0.0.1"          # on the platform never-touch list
GOOD_1, GOOD_2 = "203.0.113.7", "203.0.113.8"


def _block(ip):
    return {"action": "block_ip", "params": {"ip_address": ip}}


def _unblock(ip):
    return {"action": "unblock_ip", "params": {"ip_address": ip}}


@pytest.fixture
async def live(mongo_db):  # noqa: F811
    protected.cache_clear()
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await seed_agent(mongo_db, "t1", "a1")
    with patch.dict(os.environ, {"AUTONOMOUS_REMEDIATION_DRY_RUN": "false"}), \
         patch("autonomous_remediation_service.get_database", return_value=mongo_db), \
         patch("autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN", False, create=True), \
         patch("autonomous_remediation_service.VERIFY_TIMEOUT_SEC", 0), \
         patch("soc_integration_service.push_ocsf_event", new=AsyncMock()):
        yield mongo_db


def _request(steps, rollback=None, *, key="k1", playbook_raise=False, actions=None, dispatcher="remediation"):
    return gate.ActionRequest(
        tenant_id="t1", kind="security", origin="remediation",
        actions=actions if actions is not None else [s.get("action") if isinstance(s, dict) else s for s in steps],
        targets=["a1"], params=(steps[0].get("params", {}) if steps and isinstance(steps[0], dict) else {}),
        dedupe_key=f"t1|{key}", dispatcher=dispatcher, playbook_raise=playbook_raise,
        steps=steps, rollback=rollback)


async def _decide(db, steps, rollback=None, **kw):
    return await gate.decide(db, _request(steps, rollback, **kw), master_shadow=False)


async def _row_of(db, decision):
    return await db.autonomy_actions.find_one({"id": decision.action_id}, {"_id": 0})


async def _operator_playbook(db, steps, rollback=None):
    """Seed the vendored set, then an operator block_ip playbook that by-name selection prefers."""
    from remediation_playbook_service import sync_default_playbooks_to_db
    await sync_default_playbooks_to_db(db)
    await db.remediation_playbooks.insert_one({
        "id": "op-block-ip", "name": "block_ip", "tenantId": "t1", "source": "operator",
        "finding_class": "nscan", "match": {"scan_type": "ip"}, "steps": steps, "rollback": rollback or []})


def _finding(fid="f-1"):
    return RemediationFinding(finding_id=fid, finding_type="nscan", severity="critical", tenant_id="t1",
                              agent_id="a1", resource_id=GOOD_1, details={"type": "ip", "verdict": "Malicious"})


# ------------------------------------------------------------ tracer: through remediate()

async def test_second_step_on_a_never_touch_ip_is_refused_through_remediate(live):
    await _operator_playbook(live, [{"action": "block_ip", "params": {"ip_address": "{{finding.resource_id}}"}},
                                    {"action": "block_ip", "params": {"ip_address": BAD}}])
    with agent_that_completes("Clean"):
        result = await AutonomousRemediationService().remediate(_finding())
    assert result["status"] == "refused" and result["reason"] == "protected_target", result
    rows = [r async for r in live.autonomy_actions.find({}, {"_id": 0})]
    assert len(rows) == 1 and rows[0]["state"] == "refused" and rows[0]["reasonCode"] == "protected_target"
    assert await live.agent_instructions.count_documents({}) == 0


@pytest.mark.parametrize("position", [0, 1, 2])
async def test_protected_ip_in_first_middle_and_last_of_three_steps_is_refused(live, position):
    ips = [GOOD_1, GOOD_2, "203.0.113.9"]
    ips[position] = BAD
    decision = await _decide(live, [_block(ip) for ip in ips])
    assert decision.outcome == "refuse" and decision.reason == "protected_target"
    assert await live.agent_instructions.count_documents({}) == 0
    assert (await _row_of(live, decision))["state"] == "refused"


async def test_an_unparsable_ip_in_the_second_step_is_invalid_target(live):
    await _operator_playbook(live, [{"action": "block_ip", "params": {"ip_address": "{{finding.resource_id}}"}},
                                    {"action": "block_ip", "params": {"ip_address": "999.1.1.1"}}])
    with agent_that_completes("Clean"):
        result = await AutonomousRemediationService().remediate(_finding("f-2"))
    assert result["status"] == "refused" and result["reason"] == "invalid_target", result


async def test_a_protected_ip_in_a_compensation_step_is_refused(live):
    decision = await _decide(live, [_block(GOOD_1)], rollback=[_unblock(BAD)])
    assert decision.outcome == "refuse" and decision.reason == "protected_target"


async def test_second_step_ip_lookup_failure_fails_closed(live):
    with patch("autonomous_ops.protected.check", new=AsyncMock(side_effect=RuntimeError("list unreadable"))):
        decision = await _decide(live, [_block(GOOD_1), _block(GOOD_2)])
    assert decision.outcome == "refuse" and decision.reason == "protected_target"


async def test_benign_two_step_playbook_dispatches_both_steps_and_records_the_plan(live):
    await _operator_playbook(live, [{"action": "block_ip", "params": {"ip_address": "{{finding.resource_id}}"}},
                                    {"action": "block_ip", "params": {"ip_address": GOOD_2}}])
    with agent_that_completes("Clean"):
        result = await AutonomousRemediationService().remediate(_finding("f-3"))
    assert result["status"] != "refused", result
    (row,) = [r async for r in live.autonomy_actions.find({}, {"_id": 0})]
    assert row["reasonCode"] == "class_auto" and row["autoDispatched"] is True
    assert row["steps"] == [{"command": "block_ip", "params": {"ip_address": GOOD_1}},
                            {"command": "block_ip", "params": {"ip_address": GOOD_2}}]
    assert row["rollback"] == []
    sent = [d["payload"] async for d in live.agent_instructions.find({"type": "block_ip"})]
    assert sent == [{"ip_address": GOOD_1}, {"ip_address": GOOD_2}]


async def test_a_request_without_steps_derives_them_and_decides_as_before(live):
    request = gate.ActionRequest(
        tenant_id="t1", kind="security", origin="remediation", actions=["block_ip"], targets=["a1"],
        params={"ip_address": GOOD_1}, dedupe_key="t1|single", dispatcher="remediation")
    decision = await gate.decide(live, request, master_shadow=False)
    assert decision.state == "dispatching" and decision.reason == "class_auto"
    row = await _row_of(live, decision)
    assert row["steps"] == [{"command": "block_ip", "params": {"ip_address": GOOD_1}}] and row["rollback"] == []
    assert row["undo"]["available"] is True and row["undo"]["action"] == "unblock_ip"
    assert row["params"] == {"ip_address": GOOD_1}


async def test_a_one_step_playbook_decides_exactly_as_before(live):
    decision = await _decide(live, [_block(GOOD_1)], rollback=[_unblock(GOOD_1)])
    assert decision.state == "dispatching" and decision.reason == "class_auto"
    row = await _row_of(live, decision)
    assert row["rollback"] == [{"command": "unblock_ip", "params": {"ip_address": GOOD_1}}]
    assert row["undo"]["available"] is True


# ------------------------------------------------------------ class checks on every step

@pytest.mark.parametrize("steps", [
    [_block(GOOD_1), _unblock(GOOD_2)],                                   # undo_only as a main step
    [_block(GOOD_1), {"action": "scan_ip", "params": {"target": GOOD_2}}],  # probe as a main step
    [_block(GOOD_1), {"action": "format_disk", "params": {}}],            # not registered
    [_block(GOOD_1), "block_ip"],                                          # not even a step dict
])
async def test_a_main_step_that_is_not_auto_or_approve_is_refused(live, steps):
    decision = await _decide(live, steps)
    assert decision.outcome == "refuse" and decision.reason == "unregistered_action"
    assert await live.agent_instructions.count_documents({}) == 0


async def test_a_compensation_step_must_be_undo_only(live):
    bad = await _decide(live, [_block(GOOD_1)], rollback=[_block(GOOD_1)], key="bad")
    assert bad.outcome == "refuse" and bad.reason == "unregistered_action"
    unknown = await _decide(live, [_block(GOOD_1)], rollback=[{"action": "format_disk", "params": {}}], key="unk")
    assert unknown.reason == "unregistered_action"
    malformed = await _decide(live, [_block(GOOD_1)], rollback="unblock_ip", key="mal")
    assert malformed.reason == "unregistered_action"
    good = await _decide(live, [_block(GOOD_1)], rollback=[_unblock(GOOD_1)], key="good")
    assert good.state == "dispatching"


async def test_steps_that_disagree_with_actions_or_are_empty_are_refused(live):
    mismatch = await _decide(live, [{"action": "kill_process", "params": {}}], actions=["block_ip"], key="mm")
    assert mismatch.outcome == "refuse" and mismatch.reason == "unregistered_action"
    empty = await _decide(live, [], actions=["block_ip"], key="empty")
    assert empty.outcome == "refuse" and empty.reason == "unregistered_action"
    short = await _decide(live, [_block(GOOD_1)], actions=["block_ip", "block_ip"], key="short")
    assert short.reason == "unregistered_action"


async def test_an_approve_step_in_second_position_makes_the_whole_request_a_card(live):
    decision = await _decide(live, [_block(GOOD_1), {"action": "kill_process", "params": {"path": "/tmp/x"}}])
    assert decision.outcome == "needs_approval" and decision.reason == "class_approve"
    row = await _row_of(live, decision)
    assert row["state"] == "awaiting_approval"
    assert [s["command"] for s in row["steps"]] == ["block_ip", "kill_process"]
    assert await live.agent_instructions.count_documents({}) == 0


async def test_only_an_explicit_gate_class_raises_a_benign_playbook(live):
    decision = await _decide(live, [_block(GOOD_1), _block(GOOD_2)], playbook_raise=True)
    assert decision.outcome == "needs_approval" and decision.reason == "playbook_raised"


async def test_a_multi_step_row_offers_no_undo(live):
    decision = await _decide(live, [_block(GOOD_1), _block(GOOD_2)])
    assert decision.state == "dispatching" and decision.reason == "class_auto"
    row = await _row_of(live, decision)
    assert row["undo"]["available"] is False and row["undo"]["action"] is None and row["undo"]["params"] == {}


async def test_the_first_refusing_step_decides_the_recorded_reason(live):
    decision = await _decide(live, [_block("999.1.1.1"), _block(BAD)])
    assert decision.reason == "invalid_target"
    decision = await _decide(live, [_block(BAD), _block("999.1.1.1")], key="k2")
    assert decision.reason == "protected_target"


# ------------------------------------------------------------ 81-15: execute-time binding

async def _exec(db, aid, command="block_ip", agent="a1", params=None, kind="action"):
    return await gate.execute(db, "t1", aid, command=command, agent_id=agent,
                              params={"ip_address": GOOD_2} if params is None else params, kind=kind)


async def _decided_two(db):
    decision = await _decide(db, [_block(GOOD_1), _block(GOOD_2)])
    assert decision.state == "dispatching", decision
    return decision.action_id


async def test_execute_binds_command_agent_and_params_to_the_decided_steps(live):
    await seed_tenant(live, "t2", shadow=False)
    await seed_agent(live, "t2", "a2")
    aid = await _decided_two(live)
    cases = [
        (dict(params={"ip_address": "203.0.113.9"}), "step_mismatch"),
        (dict(params={"ip_address": BAD}), "step_mismatch"),
        (dict(agent="a2"), "target_mismatch"),
        (dict(command="restart_service", params={}), "step_mismatch"),
        (dict(command="format_disk", params={}), "unregistered_action"),
        (dict(command="scan_ip", params={"target": "x"}), "step_mismatch"),
    ]
    for kwargs, reason in cases:
        assert await _exec(live, aid, **kwargs) == {"status": "refused", "reason": reason}, kwargs
    assert await live.agent_instructions.count_documents({}) == 0
    assert (await _exec(live, aid))["status"] == "queued"
    assert (await _exec(live, aid, params={"ip_address": GOOD_1}))["status"] == "queued"
    assert await live.agent_instructions.count_documents({"triggered_by": "autonomous_ops"}) == 2


async def test_two_identical_decided_steps_may_each_be_dispatched(live):
    aid = (await _decide(live, [_block(GOOD_1), _block(GOOD_1)])).action_id
    assert (await _exec(live, aid, params={"ip_address": GOOD_1}))["status"] == "queued"
    assert (await _exec(live, aid, params={"ip_address": GOOD_1}))["status"] == "queued"


async def test_params_compare_by_canonical_json_and_a_changed_representation_is_refused(live):
    from autonomous_ops import dispatch_check
    assert dispatch_check.same_params({"a": 1, "b": 2}, {"b": 2, "a": 1}) is True
    assert dispatch_check.same_params(None, {}) is True
    assert dispatch_check.same_params({"port": 5}, {"port": "5"}) is False
    aid = (await _decide(live, [{"action": "restart_service", "params": {"port": 5}}])).action_id
    assert (await _exec(live, aid, command="restart_service", params={"port": "5"}))["reason"] == "step_mismatch"
    assert (await _exec(live, aid, command="restart_service", params={"port": 5}))["status"] == "queued"


async def test_a_never_touch_entry_added_after_the_decision_refuses_the_dispatch(live):
    aid = await _decided_two(live)
    await protected.add_entry(live, scope="tenant", tenant_id="t1", kind="ip", value=GOOD_2, actor="admin")
    assert await _exec(live, aid) == {"status": "refused", "reason": "protected_target"}
    assert (await _exec(live, aid, params={"ip_address": GOOD_1}))["status"] == "queued"
    assert await live.agent_instructions.count_documents({"payload.ip_address": GOOD_2}) == 0


async def test_an_unreadable_never_touch_list_refuses_the_dispatch(live):
    aid = await _decided_two(live)
    with patch("autonomous_ops.protected.check", new=AsyncMock(side_effect=RuntimeError("down"))):
        assert await _exec(live, aid) == {"status": "refused", "reason": "protected_target"}
    assert await live.agent_instructions.count_documents({}) == 0


async def test_an_unparsable_decided_ip_is_invalid_target_at_dispatch(live):
    row = await ledger.create_intent(live, {
        "tenantId": "t1", "kind": "security", "origin": "remediation", "state": "dispatching",
        "actions": ["block_ip"], "command": "block_ip", "targets": ["a1"], "params": {"ip_address": "999.1.1.1"},
        "steps": [{"command": "block_ip", "params": {"ip_address": "999.1.1.1"}}], "rollback": []})
    assert await _exec(live, row["id"], params={"ip_address": "999.1.1.1"}) == {
        "status": "refused", "reason": "invalid_target"}


async def test_compensate_needs_a_decided_undo_only_step(live):
    aid = (await _decide(live, [_block(GOOD_1)], rollback=[_unblock(GOOD_1)])).action_id
    ok = dict(command="unblock_ip", kind="compensate")
    assert (await _exec(live, aid, params={"ip_address": GOOD_1}, **ok))["status"] == "queued"
    assert (await _exec(live, aid, params={"ip_address": "203.0.113.99"}, **ok))["reason"] == "step_mismatch"
    assert (await _exec(live, aid, command="block_ip", params={"ip_address": GOOD_1},
                        kind="compensate"))["reason"] == "step_mismatch"
    bare = (await _decide(live, [_block(GOOD_2)], rollback=[], key="k2")).action_id
    assert (await _exec(live, bare, params={"ip_address": GOOD_2}, **ok))["reason"] == "step_mismatch"


async def test_probe_is_any_probe_command_with_the_agent_bound(live):
    aid = await _decided_two(live)
    assert (await _exec(live, aid, command="scan_ip", params={"target": "x"}, kind="probe"))["status"] == "queued"
    assert (await _exec(live, aid, command="block_ip", params={"ip_address": GOOD_1},
                        kind="probe"))["reason"] == "step_mismatch"
    assert (await _exec(live, aid, command="scan_ip", agent="nope", params={}, kind="probe"))["reason"] == "target_mismatch"


async def test_undo_is_bound_to_the_recorded_undo_action_and_params(live):
    aid = (await _decide(live, [_block(GOOD_1)])).action_id
    await ledger.transition(live, "t1", aid, ("dispatching",), "undone")
    assert (await _exec(live, aid, command="restart_service", params={}, kind="undo"))["reason"] == "step_mismatch"
    assert (await _exec(live, aid, command="unblock_ip", params={"ip_address": GOOD_2},
                        kind="undo"))["reason"] == "step_mismatch"
    assert (await _exec(live, aid, command="unblock_ip", params={"ip_address": GOOD_1},
                        kind="undo"))["status"] == "queued"


async def test_refusal_order_stop_and_state_come_before_the_binding(live):
    aid = await _decided_two(live)
    await seed_platform_stop(live)
    assert (await _exec(live, aid, params={"ip_address": BAD}))["reason"] == "stopped"
    waiting = (await _decide(live, [{"action": "isolate_host", "params": {}}], key="k3")).action_id
    assert (await _exec(live, waiting, command="restart_service", params={}))["reason"] == "not_dispatchable"
    assert (await _exec(live, waiting, command="restart_service", params={}, kind="bogus"))["reason"] == "invalid_kind"
    assert (await _exec(live, "AO-none"))["reason"] == "not_found"


async def test_a_refused_binding_leaves_an_approved_row_approved(live):
    aid = (await _decide(live, [{"action": "isolate_host", "params": {}}])).action_id
    assert await ledger.transition(live, "t1", aid, ("awaiting_approval",), "approved")
    assert (await _exec(live, aid, command="kill_process", params={}))["reason"] == "step_mismatch"
    assert (await ledger.get(live, "t1", aid))["state"] == "approved"
    assert (await _exec(live, aid, command="isolate_host", params={}))["status"] == "queued"
    assert (await ledger.get(live, "t1", aid))["state"] == "dispatching"


async def test_the_response_task_writer_binds_too(live):
    aid = (await _decide(live, [_block(GOOD_1)])).action_id
    args = dict(agent_id="a1", playbook_execution_id=None)
    bad = await gate.execute_response_task(live, "t1", aid, action="block_ip", params={}, **args)
    assert bad == {"status": "refused", "reason": "step_mismatch"}
    ok = await gate.execute_response_task(live, "t1", aid, action="block_ip", params={"ip_address": GOOD_1}, **args)
    assert ok["status"] == "queued" and await live.response_tasks.count_documents({}) == 1


async def test_an_altered_step_through_the_service_is_refused_and_the_row_fails(live):
    """CR-01 end to end: the stored playbook is changed between decision and dispatch."""
    await _operator_playbook(live, [{"action": "block_ip", "params": {"ip_address": "{{finding.resource_id}}"}},
                                    {"action": "block_ip", "params": {"ip_address": GOOD_2}}])
    finding = _finding("f-9")
    decision = await _decide(live, [_block(GOOD_1), _block(GOOD_2)], key="svc")
    altered = {"name": "block_ip", "rollback": [], "steps": [
        {"action": "block_ip", "params": {"ip_address": GOOD_1}}, {"action": "block_ip", "params": {"ip_address": BAD}}]}
    with agent_that_completes("Clean"):
        result = await AutonomousRemediationService()._dispatch_and_verify("R-1", finding, altered, decision.action_id)
    assert result["status"] == "unverified"
    assert [s["status"] for s in result["steps_dispatched"]] == ["SUCCESS", "refused"]
    assert (await ledger.get(live, "t1", decision.action_id))["state"] == "failed"
    sent = [d["payload"] async for d in live.agent_instructions.find({"type": "block_ip"})]
    assert sent == [{"ip_address": GOOD_1}]


# ------------------------------------------------------------ 81-18: approval-time re-check and undo

APPROVER = {"username": "alice", "display": "Alice", "tier": "tenant"}
LATE = "203.0.113.9"
_ISOLATE = {"action": "isolate_host", "params": {}}


async def _card_of(db, steps, rollback=None, key="card"):
    decision = await _decide(db, steps, rollback, key=key, dispatcher="instruction")
    assert decision.outcome == "needs_approval", decision
    return decision.action_id


async def _late_entry(db, ip=LATE):
    await protected.add_entry(db, scope="tenant", tenant_id="t1", kind="ip", value=ip, actor="admin")


async def _assert_refused_protected(db, aid):
    out = await approvals.approve(db, "t1", aid, approver=APPROVER)
    assert out == {"status": "refused", "reason": "protected_target"}, out
    row = await ledger.get(db, "t1", aid)
    assert row["state"] == "refused" and row["reasonCode"] == "protected_target"
    assert await db.agent_instructions.count_documents({}) == 0


async def test_approve_rechecks_every_recorded_step(live):
    aid = await _card_of(live, [_ISOLATE, _block(LATE)])
    await _late_entry(live)
    await _assert_refused_protected(live, aid)


async def test_approve_still_dispatches_a_benign_multi_step_card(live):
    aid = await _card_of(live, [_ISOLATE, _block(LATE)])
    out = await approvals.approve(live, "t1", aid, approver=APPROVER)
    assert out["status"] == "dispatched", out
    assert await live.agent_instructions.count_documents({}) == 1


async def test_approve_rechecks_the_last_of_three_steps(live):
    aid = await _card_of(live, [_ISOLATE, _block(GOOD_2), _block(LATE)])
    await _late_entry(live)
    await _assert_refused_protected(live, aid)


async def test_approve_rechecks_a_compensation_step(live):
    aid = await _card_of(live, [_ISOLATE, _block(GOOD_2)], rollback=[_unblock(LATE)])
    await _late_entry(live)
    await _assert_refused_protected(live, aid)


async def test_an_unreadable_never_touch_list_refuses_the_approval(live):
    aid = await _card_of(live, [_ISOLATE, _block(LATE)])
    with patch("autonomous_ops.protected.check", new=AsyncMock(side_effect=RuntimeError("down"))):
        await _assert_refused_protected(live, aid)


async def test_a_legacy_row_without_steps_is_rechecked_from_command_and_params(live):
    row = await ledger.create_intent(live, {
        "tenantId": "t1", "kind": "security", "origin": "test", "state": "awaiting_approval",
        "actions": ["block_ip"], "command": "block_ip", "targets": ["a1"], "params": {"ip_address": LATE},
        "dispatcher": "instruction", "approval": {"expiresAt": datetime.now(timezone.utc) + timedelta(hours=1)}})
    await _late_entry(live)
    await _assert_refused_protected(live, row["id"])


def test_row_pairs_covers_steps_then_rollback_and_the_legacy_shape():
    pairs = dispatch_check.row_pairs({
        "steps": [{"command": "isolate_host", "params": {}}, {"command": "block_ip", "params": {"ip_address": GOOD_1}}],
        "rollback": [{"command": "unblock_ip", "params": {"ip_address": GOOD_2}}, "junk"]})
    assert [(s.name if s else None, p) for s, p in pairs] == [
        ("isolate_host", {}), ("block_ip", {"ip_address": GOOD_1}), ("unblock_ip", {"ip_address": GOOD_2}), (None, {})]
    legacy = dispatch_check.row_pairs({"command": "block_ip", "params": {"ip_address": GOOD_1}})
    assert [(s.name, p) for s, p in legacy] == [("block_ip", {"ip_address": GOOD_1})]
    multi = dispatch_check.row_pairs({"actions": ["block_ip", "block_ip"], "command": "block_ip",
                                      "params": {"ip_address": GOOD_1}})
    assert len(multi) == 2 and all(p == {"ip_address": GOOD_1} for _, p in multi)
    assert dispatch_check.row_pairs({"steps": [{"command": "block_ip"}], "rollback": "x"})[0][1] == {}

