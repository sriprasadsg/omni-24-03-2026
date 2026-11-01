"""The block path end to end against the agent contract (Phase 83, plan 83-01, RESP-01 / RESP-02 / RESP-06).
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

A stand-in agent replays the example results of shared/agent-response-contract.json through the REAL
result route (agent_tasks_endpoints.report_instruction_result); the sweep, the gate, the reconciler
and the verify step are the real ones. 83-02 makes the Rust agent produce the same examples.

Value: protects=one finding flagged by two origins on one host becomes exactly one gate-decided block
instruction for the right agent id; the agent's own verify result marks it verified or failed; a block
that is still flagged is never lifted or repeated; fails_when=the instruction goes to the hostname, a
second instruction appears, a verified block is lifted because the finding is still Malicious, or a
failed verify dispatches anything; no_claim=a real firewall (the live round trip is a UAT item).
"""
import ast
import asyncio
import copy
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent_tasks_endpoints
from autonomous_ops import ledger, protected, reconciler, signals, sweep
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_agent, seed_feed_ioc, seed_native_verdict, seed_response_agent, seed_tenant

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(os.path.dirname(_BACKEND), "shared", "agent-response-contract.json"), encoding="utf-8") as fh:
    CONTRACT = json.load(fh)
EXAMPLES = CONTRACT["examples"]
IP = "45.33.32.156"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    monkeypatch.delenv("AUTONOMOUS_OPS_STUCK_DISPATCH_MIN", raising=False)
    monkeypatch.delenv("AUTONOMOUS_OPS_NO_RESULT_MIN", raising=False)
    protected.cache_clear()


@pytest.fixture
async def world(mongo_db):
    """Tenant t1 (shadow off), agent a1 / host-a1 reporting block_ip_ttl, a native Malicious ip
    verdict under the hostname, and a global URLhaus row naming the same address."""
    await ledger.ensure_indexes(mongo_db)
    await signals.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await seed_response_agent(mongo_db, "t1", "a1", hostname="host-a1", tokens=["block_ip_ttl"])
    await seed_native_verdict(mongo_db, "t1", "host-a1", kind="ip", target=IP)
    await seed_feed_ioc(mongo_db, ioc_type="url", value=f"http://{IP}/payload.exe", source_ip=IP, feed="urlhaus")
    return mongo_db


async def post_result(db, task_id, example, *, agent="a1", action="block_ip"):
    """What the agent posts: the contract example wrapped the way instructions.rs wraps it."""
    body = copy.deepcopy(EXAMPLES[example] if isinstance(example, str) else example)
    payload = {"task_id": task_id, "action": action, "type": action, "status": body["status"], "result": body}
    with patch.object(agent_tasks_endpoints, "get_database", return_value=db):
        return await agent_tasks_endpoints.report_instruction_result(agent, payload, _tenant={"id": "t1"})


async def rows(db, tenant="t1"):
    return [r async for r in db.autonomy_actions.find({"tenantId": tenant, "kind": {"$ne": "control"}}, {"_id": 0})]


async def instructions(db, tenant="t1"):
    return [d async for d in db.agent_instructions.find({"tenantId": tenant}, {"_id": 0})]


async def one_block(db):
    """Run one sweep tick and return (row, instruction)."""
    await sweep.tick(db)
    (row,) = await rows(db)
    (doc,) = await instructions(db)
    return row, doc


async def get_row(db, row_id, tenant="t1"):
    return await ledger.get(db, tenant, row_id)


# ------------------------------------------------------------------ the contract file itself

def test_the_contract_file_holds_what_the_plan_names():
    assert len(CONTRACT["tokens"]) == 10 and CONTRACT["version"] == 1
    assert set(CONTRACT["commandToken"].values()) <= set(CONTRACT["tokens"])
    assert CONTRACT["rangeToken"] in CONTRACT["tokens"]
    assert CONTRACT["blockTtlSeconds"] == {"min": 3600, "max": 604800, "default": 86400}
    assert CONTRACT["isolationRevertSeconds"] == 14400 and CONTRACT["stillRunningCap"] == 128
    assert CONTRACT["rebootDelaySeconds"] == {"min": 30, "max": 300}
    assert set(CONTRACT["protectedPaths"]) == {"windows", "linux"} and "sshd" in CONTRACT["criticalServices"]
    needed = {"block_applied", "block_already_applied", "block_verify_failed", "unblock_removed", "quarantine_moved",
              "quarantine_moved_still_running", "quarantine_locked", "quarantine_hash_mismatch", "kill_done",
              "kill_gone", "kill_survived", "kill_refused", "restart_done", "isolate_done",
              "isolate_self_test_failed", "restore_done", "reboot_scheduled"}
    assert needed <= set(EXAMPLES)


@pytest.mark.parametrize("name", sorted(EXAMPLES))
def test_every_example_stays_inside_the_contract(name):
    ex = EXAMPLES[name]
    assert ex["status"] in ("success", "error") and ex["outcome"] in CONTRACT["outcomes"]
    assert isinstance(ex["verify"]["ok"], bool) and ex["verify"]["check"] in CONTRACT["checks"]
    for entry in ex.get("still_running", []):
        assert set(entry) == {"pid", "name", "start_time"} and entry["pid"] > 1 and entry["start_time"] > 0
    assert len(ex.get("still_running", [])) <= CONTRACT["stillRunningCap"]


def test_the_four_kill_examples_say_what_the_plan_says():
    assert (EXAMPLES["kill_done"]["status"], EXAMPLES["kill_done"]["outcome"]) == ("success", "killed")
    assert (EXAMPLES["kill_gone"]["status"], EXAMPLES["kill_gone"]["outcome"]) == ("success", "process_gone")
    assert EXAMPLES["kill_survived"]["verify"]["ok"] is False and EXAMPLES["kill_survived"]["still_running"]
    assert (EXAMPLES["kill_refused"]["status"], EXAMPLES["kill_refused"]["outcome"]) == ("error", "refused")
    assert EXAMPLES["kill_refused"]["still_running"] and EXAMPLES["kill_refused"]["error"]


# ------------------------------------------------------------------ the tracer

async def test_tracer_two_origins_one_block_then_verified(world):
    """RESP-01 / RESP-02 / RESP-06: one tick, one row, one instruction to agents.id; the agent's verify
    result moves dispatching -> executed -> verified on the next reconciler tick."""
    row, doc = await one_block(world)
    assert (row["origin"], row["dispatcher"], row["targets"], row["state"]) == ("sweep", "security_response", ["a1"], "dispatching")
    assert row["command"] == "block_ip" and row["autoDispatched"] is True
    assert doc["agent_id"] == "a1" and doc["agent_id"] != "host-a1"          # the agents.id, never the hostname
    assert doc["type"] == "block_ip" and doc["triggered_by"] == "autonomous_ops"
    assert doc["parameters"] == {"ip_address": IP, "ttl_seconds": 86400}     # RESP-02, D-13 default of 24 hours
    assert doc["payload"] == doc["parameters"] and row["instructionIds"] == [doc["id"]]
    assert set(row["reason"]["inputs"]["origins"]) == {"native", "feed:urlhaus"} and row["reason"]["ruleId"] == "sweep:block_ip"

    await post_result(world, doc["id"], "block_applied")
    counts = await reconciler.tick(world)
    assert counts["executed"] == 1 and counts["failed"] == 0
    done = await get_row(world, row["id"])
    assert done["state"] == "verified" and done["verifiedAt"] is not None
    assert done["blockedFrom"] is not None and done["blockedUntil"] is not None
    assert abs((done["blockedUntil"] - done["blockedFrom"]).total_seconds() - 86400) < 60
    stored = (await instructions(world))[0]["result"]
    assert stored["outcome"] == "applied" and stored["verify"] == {"ok": True, "check": "firewall_rule_present"}
    assert stored["expires_in"] == 86400


async def test_a_failed_verify_ends_failed_and_dispatches_nothing(world):
    row, doc = await one_block(world)
    await post_result(world, doc["id"], "block_verify_failed")
    counts = await reconciler.tick(world)
    assert counts["failed"] == 1
    done = await get_row(world, row["id"])
    assert (done["state"], done["reasonCode"]) == ("failed", "verify_failed")
    assert done["reasonText"] and len(await instructions(world)) == 1         # no unblock, no second instruction


async def test_an_already_applied_block_is_verified_too(world):
    row, doc = await one_block(world)
    await post_result(world, doc["id"], "block_already_applied")
    await reconciler.tick(world)
    assert (await get_row(world, row["id"]))["state"] == "verified"


@pytest.mark.parametrize("example", ["block_applied", "block_verify_failed"])
async def test_a_block_that_is_still_flagged_is_never_lifted_or_repeated(world, example):
    """PROH-83-06: still Malicious after the result is a reason to keep a block, not to lift it."""
    row, doc = await one_block(world)
    await post_result(world, doc["id"], example)
    await reconciler.tick(world)
    before = await get_row(world, row["id"])
    await seed_native_verdict(world, "t1", "host-a1", kind="ip", target=IP,
                              created_at=datetime.now(timezone.utc) + timedelta(minutes=5))
    for _ in range(5):
        await reconciler.tick(world)
    after = await get_row(world, row["id"])
    assert after["state"] == before["state"] and after.get("verifiedAt") == before.get("verifiedAt")
    assert len(await instructions(world)) == 1 and len(await rows(world)) == 1
    assert (await get_row(world, row["id"]))["undo"]["undoneAt"] is None


# ------------------------------------------------------------------ the verify path never reads findings

def _names(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            yield node.id
        elif isinstance(node, ast.Attribute):
            yield node.attr
            if node.attr == "security_scan_results":
                yield "security_scan_results"
        elif isinstance(node, ast.Constant) and node.value == "security_scan_results":
            yield "security_scan_results"
        elif isinstance(node, ast.alias):
            yield node.name.split(".")[-1]


def _offences(src):
    tree = ast.parse(src)
    banned = {"remediate", "_dispatch_and_verify", "_check_nscan_resolved", "security_scan_results",
              "autonomous_remediation_service"}
    found = {n for n in _names(tree) if n in banned}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and "autonomous_remediation_service" in node.module:
            found.add("autonomous_remediation_service")
    return sorted(found)


def test_verify_path_never_reads_findings():
    """protects=RESP-06: the verify step, the dispatcher and the reconciler never name the old verify
    that re-reads a finding and rolls back; the scanner has a negative control."""
    assert _offences("from autonomous_remediation_service import X\nsvc.remediate(f)\n") == [
        "autonomous_remediation_service", "remediate"]
    assert _offences("x = db.security_scan_results\ny = db['security_scan_results']\n") == ["security_scan_results"]
    assert _offences("await self._dispatch_and_verify(f)\nself._check_nscan_resolved(f)\n") == [
        "_check_nscan_resolved", "_dispatch_and_verify"]
    for name in ("verify.py", "response_dispatch.py", "reconciler.py"):
        with open(os.path.join(_BACKEND, "autonomous_ops", name), encoding="utf-8") as fh:
            assert _offences(fh.read()) == [], name


# ------------------------------------------------------------------ shadow and refusals

async def test_shadow_records_would_have_and_writes_no_instruction(mongo_db):
    await ledger.ensure_indexes(mongo_db)
    await signals.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=True)
    await seed_response_agent(mongo_db, "t1", "a1", hostname="host-a1", tokens=["block_ip_ttl"])
    await seed_native_verdict(mongo_db, "t1", "host-a1", kind="ip", target=IP)
    await seed_feed_ioc(mongo_db, ioc_type="url", value=f"http://{IP}/p", source_ip=IP, feed="urlhaus")
    await sweep.tick(mongo_db)
    (row,) = await rows(mongo_db)
    assert row["state"] == "shadow" and row["wouldHave"] == "allow_auto"
    assert await instructions(mongo_db) == []


async def test_only_one_origin_produces_no_block(world):
    """Plan 83-05: one origin records a suggestion (nothing to approve) and sends nothing."""
    await world.edr_ioc.delete_many({})
    await sweep.tick(world)
    (row,) = await rows(world)
    assert row["state"] == "suggested" and row["reason"]["inputs"]["suggestionOnly"] is True
    assert await instructions(world) == []


async def test_two_origins_more_than_a_day_apart_do_not_corroborate(world):
    """D-03: the window is 24 hours between the sweep's own first sightings."""
    now = datetime.now(timezone.utc)
    await world.edr_ioc.delete_many({})
    await sweep.tick(world, now=now - timedelta(hours=30))               # native seen first, alone
    await seed_feed_ioc(world, ioc_type="url", value=f"http://{IP}/p", source_ip=IP, feed="urlhaus",
                        updated_at=now)
    await sweep.tick(world, now=now)
    (row,) = await rows(world)               # still only the suggestion the first sighting recorded
    assert row["state"] == "suggested" and row["dedupeKey"].startswith("t1|sweep-suggest|")
    assert await instructions(world) == []


async def test_a_hostname_shared_by_two_agents_produces_no_row(world):
    await seed_response_agent(world, "t1", "a2", hostname="HOST-A1", tokens=["block_ip_ttl"])
    await sweep.tick(world)
    assert await rows(world) == [] and await instructions(world) == []


async def test_a_hostname_from_another_tenant_produces_no_row(world):
    await seed_tenant(world, "t2", shadow=False)
    await seed_response_agent(world, "t2", "b1", hostname="host-b1", tokens=["block_ip_ttl"])
    await world.security_scan_results.delete_many({})
    await seed_native_verdict(world, "t1", "host-b1", kind="ip", target=IP)     # t1's row names t2's host
    await sweep.tick(world)
    assert await rows(world) == [] and await rows(world, "t2") == [] and await instructions(world, "t2") == []


async def test_an_agent_without_the_token_gets_no_block(world):
    await world.agents.update_one({"id": "a1"}, {"$set": {"meta.response_actions.tokens": []}})
    await sweep.tick(world)
    assert await rows(world) == [] and await instructions(world) == []


# ------------------------------------------------------------------ edge cases of the verify step

async def _applied_row(db, example):
    row, doc = await one_block(db)
    await post_result(db, doc["id"], example)
    return row, doc


async def test_verify_true_false_and_absent_are_three_different_outcomes(world):
    """Edge RESP-06 adjacency + empty: no verify block leaves the row executed and dispatches nothing."""
    without_verify = {k: v for k, v in EXAMPLES["block_applied"].items() if k != "verify"}
    row, doc = await _applied_row(world, without_verify)
    await reconciler.tick(world)
    done = await get_row(world, row["id"])
    assert done["state"] == "executed" and done.get("reasonCode") != "verify_failed"
    assert len(await instructions(world)) == 1
    await reconciler.tick(world)
    assert (await get_row(world, row["id"]))["state"] == "executed"


async def test_the_reader_takes_the_latest_instruction_id(world):
    """Edge RESP-06 ordering: with two ids the reconciler reads the latest, as it does today."""
    row, doc = await one_block(world)
    await post_result(world, doc["id"], "block_verify_failed")                  # the FIRST id says failed ...
    second = dict(doc, id="second-instruction", status="SUCCESS",
                  result={"outcome": "applied", "verify": {"ok": True, "check": "firewall_rule_present"},
                          "expires_in": 3600})
    await world.agent_instructions.insert_one(dict(second))
    await world.autonomy_actions.update_one({"id": row["id"]}, {"$push": {"instructionIds": "second-instruction"}})
    await reconciler.tick(world)
    assert (await get_row(world, row["id"]))["state"] == "verified"             # ... the LATEST id says ok


async def test_two_passes_write_one_audit_event_per_state_change(world):
    """Edge RESP-06 concurrency: executed and verified are compare-and-set."""
    row, doc = await _applied_row(world, "block_applied")
    seen = []
    original = ledger._mirror

    async def spy(db, tenant_id, event, r, actor=None):
        seen.append((r.get("id"), event))
        return await original(db, tenant_id, event, r, actor)

    with patch.object(ledger, "_mirror", spy):
        await asyncio.gather(reconciler.tick(world), reconciler.tick(world))
    mine = [event for rid, event in seen if rid == row["id"]]
    assert sorted(mine) == ["executed", "verified"]


# ------------------------------------------------------------------ undo removes only this block's claim (Task 3)

ACTOR = {"username": "alice", "display": "Alice", "tier": "tenant"}


async def _verified_block(db):
    row, doc = await one_block(db)
    await post_result(db, doc["id"], "block_applied")
    await reconciler.tick(db)
    return await get_row(db, row["id"]), doc


async def test_undo_sends_one_unblock_that_names_the_original_block_instruction(world):
    """ACTV-02: block_id is the task id of the original block, read from the row, never from a request."""
    from autonomous_ops import approvals, dispatch_check
    row, block_doc = await _verified_block(world)
    out = await approvals.undo(world, "t1", row["id"], actor=ACTOR)
    assert out["status"] == "undone" and out["dispatch"]["status"] == "queued"
    docs = await instructions(world)
    (unblock,) = [d for d in docs if d["type"] == "unblock_ip"]
    assert len(docs) == 2 and unblock["triggered_by"] == "autonomous_ops" and unblock["autonomy"]["kind"] == "undo"
    assert unblock["agent_id"] == "a1" and unblock["parameters"] == {"ip_address": IP, "block_id": block_doc["id"]}
    after = await get_row(world, row["id"])
    assert unblock["parameters"]["block_id"] == after["instructionIds"][0] == block_doc["id"]
    assert after["state"] == "undone" and after["undo"]["undoneBy"] == ACTOR
    assert after["undo"]["params"] == unblock["parameters"]
    # bind accepts exactly this dispatch and nothing else
    assert await dispatch_check.bind(world, "t1", after, command="unblock_ip", agent_id="a1",
                                     params=unblock["parameters"], kind="undo") is None
    assert await dispatch_check.bind(world, "t1", after, command="unblock_ip", agent_id="a1",
                                     params={"ip_address": IP, "block_id": "someone-elses-claim"},
                                     kind="undo") == "step_mismatch"


async def test_a_dispatcher_other_than_security_response_keeps_the_old_undo_params(world):
    from autonomous_ops import approvals, gate
    req = gate.ActionRequest(tenant_id="t1", kind="security", origin="test", actions=["block_ip"], targets=["a1"],
                             params={"ip_address": IP}, dedupe_key="t1|plain|block", reason={"ruleId": "t", "inputs": {}})
    d = await gate.decide(world, req, master_shadow=False)
    out = await gate.execute(world, "t1", d.action_id, command="block_ip", agent_id="a1", params={"ip_address": IP})
    await world.agent_instructions.update_one({"id": out["task_id"]}, {"$set": {"status": "SUCCESS"}})
    await reconciler.tick(world)
    assert (await get_row(world, d.action_id))["state"] == "executed"
    assert (await approvals.undo(world, "t1", d.action_id, actor=ACTOR))["status"] == "undone"
    (unblock,) = [x async for x in world.agent_instructions.find({"type": "unblock_ip"}, {"_id": 0})]
    assert unblock["parameters"] == {"ip_address": IP}


async def test_an_expired_block_can_no_longer_be_undone_and_nothing_is_written(world):
    from autonomous_ops import approvals
    row, _ = await _verified_block(world)
    await world.autonomy_actions.update_one(
        {"id": row["id"]}, {"$set": {"blockedUntil": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    out = await approvals.undo(world, "t1", row["id"], actor=ACTOR)
    assert out == {"status": "refused", "reason": "not_undoable"}
    assert (await get_row(world, row["id"]))["state"] == "verified" and len(await instructions(world)) == 1


async def test_later_ticks_add_no_row_and_no_instruction_while_the_block_lasts(world):
    row, _ = await _verified_block(world)
    for _ in range(10):
        await sweep.tick(world)
        await reconciler.tick(world)
    assert len(await rows(world)) == 1 and len(await instructions(world)) == 1
    assert (await get_row(world, row["id"]))["state"] == "verified"


async def test_after_an_undo_ticks_inside_a_day_add_no_instruction(world):
    from autonomous_ops import approvals
    row, _ = await _verified_block(world)
    await approvals.undo(world, "t1", row["id"], actor=ACTOR)
    for _ in range(5):
        await sweep.tick(world)
    # Plan 83-05: the sweep records ONE refused row saying why, however many ticks pass, and sends nothing.
    assert sorted(r["state"] for r in await rows(world)) == ["refused", "undone"]
    assert len(await instructions(world)) == 2                                      # the block and its unblock only


# ------------------------------------------------------------------ the row builder moved out of the gate

def test_claim_keys_name_the_three_undo_commands():
    from autonomous_ops import decision_row
    assert decision_row.CLAIM_KEYS == {"unblock_ip": "block_id", "unquarantine_file": "quarantine_id",
                                       "restore_host": "isolation_id"}


def test_undo_block_with_and_without_a_claim():
    from autonomous_ops import decision_row, registry
    block, quarantine = registry.resolve("block_ip"), registry.resolve("quarantine_file")
    isolate, restart = registry.resolve("isolate_host"), registry.resolve("restart_service")
    plain = decision_row.undo_block(block, {"ip_address": IP, "ttl_seconds": 86400})
    assert plain["params"] == {"ip_address": IP} and plain["action"] == "unblock_ip" and plain["available"] is True
    claimed = decision_row.undo_block(block, {"ip_address": IP, "ttl_seconds": 86400}, claim="abc")
    assert claimed["params"] == {"ip_address": IP, "block_id": "abc"}
    assert decision_row.undo_block(quarantine, {"path": "/x", "sha256": "h"}, claim="q1")["params"] == {"quarantine_id": "q1"}
    assert decision_row.undo_block(isolate, {}, claim="i1")["params"] == {"isolation_id": "i1"}
    assert decision_row.undo_block(quarantine, {"path": "/x"})["params"] == {"path": "/x"}      # as before: no claim, no change
    assert decision_row.undo_block(restart, {"service": "x"}, claim="c")["available"] is False      # nothing to undo
    assert decision_row.undo_block(block, {"ip_address": IP}, multi=True, claim="c")["params"] == {}


def test_reason_text_keeps_the_callers_words_only_for_security_response():
    from autonomous_ops import decision_row, gate, messages
    mine = gate.ActionRequest(tenant_id="t", kind="security", origin="sweep", actions=["block_ip"], targets=["a"],
                              params={}, dedupe_key="k", reason_text="OWN WORDS", dispatcher="security_response")
    other = gate.ActionRequest(tenant_id="t", kind="security", origin="x", actions=["block_ip"], targets=["a"],
                               params={}, dedupe_key="k", reason_text="OWN WORDS", dispatcher="instruction")
    for code in ("class_auto", "suggest_requested", "playbook_raised", "class_approve", "suppressed_by_undo"):
        assert decision_row.reason_text(mine, "needs_approval", code) == "OWN WORDS", code
    assert decision_row.reason_text(mine, "refuse", "protected_target") == messages.REASON_TEXT["protected_target"]
    assert decision_row.reason_text(other, "needs_approval", "class_approve") == messages.REASON_TEXT["class_approve"]
    assert decision_row.reason_text(other, "allow_auto", "class_auto") == "OWN WORDS"       # as today
    assert decision_row.reason_text(mine, "allow_auto", "class_auto") == "OWN WORDS"


def test_the_gate_and_approvals_stay_under_500_lines():
    for name in ("gate.py", "approvals.py", "decision_row.py", "sweep_security.py", "sweep.py"):
        with open(os.path.join(_BACKEND, "autonomous_ops", name), encoding="utf-8") as fh:
            assert len(fh.read().splitlines()) < 500, name
