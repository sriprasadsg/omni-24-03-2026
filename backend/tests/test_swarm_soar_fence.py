"""Swarm, SOAR, worker-task and delivery fences (Phase 83, plan 83-06, RESP-11 / D-18).

Value: protects=the old containment paths (antibody propagation, the SOAR block and isolate
plugins, the worker tasks, a swarm mission's isolate step) send nothing to an agent on their own,
say so ("not_sent") instead of reporting success, and the dead ``instructions`` queue stays empty;
the new 2.1.16 actions reach an agent only through a gate-stamped instruction;
fails_when=a route or plugin writes the instructions collection, an answer says dispatched or
success for something that was not sent, ``agents.isolated`` is set for a host that received
nothing, a swarm plan (keyword or LLM) queues ``isolate_host``, or an unstamped gate-only command
is returned to an agent at a poll;
no_claim=human-started SOAR and playbook runs through the response tasks (unchanged, covered by
the Phase 81 fence tests) and the Rust agent's handling of the actions.

Real MongoDB (the private test server) through tests/_mongo_test_db.py; no model call.
"""
import asyncio
import inspect
import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import response_messages as rm
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

IP = "45.33.32.156"
USER = SimpleNamespace(tenant_id="t1", role="admin", username="op")


# ---------------------------------------------------------------- the antibody route

async def test_propagate_antibody_writes_nothing_and_says_not_sent(mongo_db, monkeypatch):
    import database
    import swarm_service
    monkeypatch.setattr(database.mongodb, "db", mongo_db, raising=False)
    await mongo_db.agents.insert_one({"id": "a1", "tenantId": "t1", "hostname": "h1", "status": "Online"})
    answer = await swarm_service.propagate_antibody({"threat_type": "ransomware", "indicator": IP}, USER)
    await asyncio.sleep(0.05)
    assert answer["status"] == "not_sent" and answer["dispatched"] == 0
    assert answer["message"] == rm.FENCE["swarm"] and "Autonomous Ops" in answer["message"]
    assert answer["threat_type"] == "ransomware" and answer["indicator"] == IP and answer["antibody_id"]
    assert "Propagating" not in json.dumps(answer)
    assert await mongo_db.instructions.count_documents({}) == 0
    assert await mongo_db.agent_instructions.count_documents({}) == 0


def test_propagate_route_has_no_background_task():
    import swarm_service
    assert "background_tasks" not in inspect.signature(swarm_service.propagate_antibody).parameters
    assert not hasattr(swarm_service, "distribute")


async def test_propagate_still_needs_a_tenant():
    import swarm_service
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as err:
        await swarm_service.propagate_antibody({"indicator": IP}, SimpleNamespace(tenant_id=None))
    assert err.value.status_code == 403


# ---------------------------------------------------------------- the SOAR plugins

def _engine():
    import soar_engine
    return soar_engine.SOAREngine()


async def test_block_plugin_sends_nothing(mongo_db, monkeypatch):
    import database
    monkeypatch.setattr(database.mongodb, "db", mongo_db, raising=False)
    out = await _engine()._plugin_block_ip_firewall({"ip": IP, "agent_id": "a1"}, {"trigger": {}})
    assert out["action"] == "not_sent" and out["ip"] == IP and out["message"] == rm.FENCE["soar"]
    assert await mongo_db.instructions.count_documents({}) == 0
    assert await mongo_db.agent_instructions.count_documents({}) == 0


async def test_isolate_plugin_sends_nothing_and_marks_no_agent_isolated(mongo_db, monkeypatch):
    import database
    monkeypatch.setattr(database.mongodb, "db", mongo_db, raising=False)
    await mongo_db.agents.insert_one({"id": "a1", "tenantId": "t1", "hostname": "h1"})
    out = await _engine()._plugin_isolate_host({"host_id": "a1"}, {"trigger": {}})
    assert out["action"] == "not_sent" and out["host_id"] == "a1" and out["message"] == rm.FENCE["soar"]
    agent = await mongo_db.agents.find_one({"id": "a1"})
    assert "isolated" not in agent and "isolation_time" not in agent       # PROH-83-10
    assert await mongo_db.instructions.count_documents({}) == 0


async def test_run_log_marks_the_node_not_sent_and_the_run_goes_on(mongo_db, monkeypatch):
    import database
    monkeypatch.setattr(database.mongodb, "db", mongo_db, raising=False)
    playbook = {"name": "contain", "nodes": [
        {"id": "n1", "type": "block_ip_firewall", "data": {"ip": IP, "agent_id": "a1"}},
        {"id": "n2", "type": "isolate_host", "data": {"host_id": "a1"}},
        {"id": "n3", "type": "send_slack_message", "data": {"message": "x"}},
    ], "edges": [{"source": "n1", "target": "n2"}, {"source": "n2", "target": "n3"}]}
    engine = _engine()
    engine.plugins["send_slack_message"] = lambda data, ctx: asyncio.sleep(0, {"action": "skipped"})
    run = await engine.execute_playbook(playbook, {"agent_id": "a1"})
    by_node = {entry["node_id"]: entry for entry in run["log"]}
    assert by_node["n1"]["status"] == "not_sent" and by_node["n2"]["status"] == "not_sent"
    assert by_node["n3"]["status"] == "success"            # a step that did something is still success
    assert run["status"] != "failed" and run["status"] == "completed"
    assert "success" not in (by_node["n1"]["status"], by_node["n2"]["status"])
    assert await mongo_db.instructions.count_documents({}) == 0


# ---------------------------------------------------------------- the worker tasks

def test_remediation_script_task_answers_not_sent_at_once(monkeypatch):
    import tasks
    import pymongo

    def boom(*a, **k):
        raise AssertionError("the worker must not open a database client")

    monkeypatch.setattr(pymongo, "MongoClient", boom)
    out = tasks.execute_remediation_script.run("Get-Process", "powershell", "a1", "t1")
    assert out["status"] == "not_sent" and out["output"] == rm.FENCE["worker"]


def test_periodic_patch_scan_queues_no_instruction_and_keeps_its_sla_part(monkeypatch):
    import tasks
    import pymongo
    import patch_service

    class Coll:
        def __init__(self, name, docs, log):
            self.name, self.docs, self.log = name, docs, log

        def find(self, *a, **k):
            return list(self.docs)

        def insert_one(self, doc):
            self.log.append((self.name, "insert_one", doc))

        def update_one(self, *a, **k):
            self.log.append((self.name, "update_one", a))

    log = []
    colls = {
        "agents": Coll("agents", [{"id": "a1", "tenant_id": "t1"}], log),
        "software_inventory": Coll("software_inventory", [
            {"name": "pkg", "agent_id": "a1", "is_outdated": True, "current_version": "1", "latest_version": "2",
             "update_status": "pending"}], log),
        "compliance_alerts": Coll("compliance_alerts", [], log),
        "instructions": Coll("instructions", [], log),
    }

    class Db:
        def __getattr__(self, name):
            return colls[name]

    class Client:
        def __init__(self, *a, **k):
            pass

        def __getitem__(self, name):
            return Db()

        def close(self):
            pass

    class Sla:
        def check_software_sla(self, item):
            return {"breached": True, "sla_days": 7, "age_days": 9}

    monkeypatch.setattr(pymongo, "MongoClient", Client)
    monkeypatch.setattr(patch_service, "get_patch_service", lambda: Sla())
    out = tasks.run_periodic_patch_scan.run()
    assert not [entry for entry in log if entry[0] == "instructions"]
    assert out["breaches_found"] == 1
    assert [entry for entry in log if entry[0] == "compliance_alerts"]


# ---------------------------------------------------------------- the swarm mission (A-83-SWARM-MISSION)

def test_the_keyword_map_never_picks_isolate_host():
    import swarm_endpoints
    for goal in ("isolate the host", "quarantine and block the attacker", "scan and block"):
        kinds = [i["type"] for i in swarm_endpoints._goal_to_instructions(goal)]
        assert "isolate_host" not in kinds, goal
    assert [i["type"] for i in swarm_endpoints._goal_to_instructions("scan and isolate")] == ["vulnerability_scan"]
    assert swarm_endpoints.CONTAINMENT_MISSION_TYPES == {"isolate_host"}


async def _run_mission(mongo_db, monkeypatch, plan):
    import ai_service as ai_module
    import swarm_endpoints
    monkeypatch.setattr(swarm_endpoints, "get_database", lambda: mongo_db)
    monkeypatch.setattr(swarm_endpoints, "missions", {"m1": {"id": "m1", "status": "Running", "logs": []}})

    class Fake:
        is_configured = True

        async def initialize(self):
            pass

        async def generate_text(self, prompt, source=None):
            self.prompt = prompt
            return json.dumps(plan)

    fake = Fake()
    monkeypatch.setattr(ai_module, "ai_service", fake)
    await mongo_db.agents.insert_one({"id": "a1", "tenantId": "t1", "hostname": "h1", "status": "Online"})
    await swarm_endpoints.run_swarm_lifecycle("m1", "contain the attacker", "t1")
    return fake, swarm_endpoints.missions["m1"]


async def test_an_llm_plan_with_isolate_host_is_filtered_and_logged(mongo_db, monkeypatch):
    plan = [{"type": "vulnerability_scan", "instruction": "Scan"}, {"type": "isolate_host", "instruction": "Cut it off"},
            {"type": "log_collection", "instruction": "Ship logs"}]
    fake, mission = await _run_mission(mongo_db, monkeypatch, plan)
    queued = [d["type"] async for d in mongo_db.agent_instructions.find({})]
    assert sorted(queued) == ["log_collection", "vulnerability_scan"]       # the other steps still run
    messages = [m.message for m in mission["logs"]]
    assert messages.count(rm.FENCE["swarm_mission"]) == 1
    assert "isolate_host" not in fake.prompt                                 # never offered to the model
    assert await mongo_db.instructions.count_documents({}) == 0


async def test_a_plan_that_is_only_isolate_host_falls_back_without_it(mongo_db, monkeypatch):
    _, mission = await _run_mission(mongo_db, monkeypatch, [{"type": "isolate_host", "instruction": "Cut it off"}])
    queued = [d["type"] async for d in mongo_db.agent_instructions.find({})]
    assert queued and "isolate_host" not in queued
    assert [m.message for m in mission["logs"]].count(rm.FENCE["swarm_mission"]) == 1


# ---------------------------------------------------------------- nothing writes the dead queue

def test_the_old_modules_do_not_import_a_database_client_for_the_dead_queue():
    import soar_engine
    import swarm_service
    import tasks
    for module in (swarm_service, soar_engine, tasks):
        src = inspect.getsource(module)
        assert "instructions.insert" not in src, module.__name__


# ---------------------------------------------------------------- delivery: gate-only commands (T-83-25)

async def _live(db):
    from autonomous_ops import ledger, protected
    from tests.autonomy_support import seed_agent, seed_tenant
    protected.cache_clear()
    await ledger.ensure_indexes(db)
    await seed_tenant(db, "t1", shadow=False)
    await db.tenants.update_one({"id": "t1"}, {"$set": {"agentCapabilities": ["all"]}})
    await seed_agent(db, "t1", "a1")


async def _queued(db, **doc):
    base = {"agent_id": "a1", "tenantId": "t1", "status": "pending", "payload": {}}
    await db.agent_instructions.insert_one({**base, **doc})
    return await db.agent_instructions.find({"id": doc["id"]}).to_list(1)


async def _stamped_row(db):
    """A decided ledger row the stamp can point at (a block_ip decision at allow_auto)."""
    from autonomous_ops import gate
    req = gate.ActionRequest(tenant_id="t1", kind="security", origin="test", actions=["block_ip"], targets=["a1"],
                             params={"ip_address": IP}, dedupe_key="t1|block_ip|a1|" + IP,
                             reason={"ruleId": "test", "inputs": {}}, dispatcher="instruction")
    decision = await gate.decide(db, req, master_shadow=False)
    assert decision.outcome == "allow_auto", decision
    return decision.action_id


@pytest.mark.parametrize("name", ["quarantine_file", "unquarantine_file", "restart_service", "isolate_host",
                                  "restore_host", "reboot_host"])
async def test_an_unstamped_gate_only_command_is_refused_at_delivery(mongo_db, name):
    from autonomous_ops import delivery
    await _live(mongo_db)
    items = await _queued(mongo_db, id=f"i-{name}", type=name, instruction="Swarm mission: x")
    kept = await delivery.hold_back_autonomous(mongo_db, "t1", items)
    assert kept == []
    stored = await mongo_db.agent_instructions.find_one({"id": f"i-{name}"})
    assert stored["status"] == "refused" and stored["error"] == "autonomy_gate_required"
    assert stored["refused_at"]


async def test_the_instruction_text_counts_as_well_as_the_type(mongo_db):
    from autonomous_ops import delivery
    await _live(mongo_db)
    items = await _queued(mongo_db, id="i-text", type="general_task", instruction="Isolate-Host: the server")
    assert await delivery.hold_back_autonomous(mongo_db, "t1", items) == []
    assert (await mongo_db.agent_instructions.find_one({"id": "i-text"}))["error"] == "autonomy_gate_required"


async def test_a_stamped_gate_only_command_passes(mongo_db):
    from autonomous_ops import delivery
    await _live(mongo_db)
    action_id = await _stamped_row(mongo_db)
    items = await _queued(mongo_db, id="i-ok", type="isolate_host",
                          autonomy={"actionId": action_id, "tenantId": "t1", "kind": "action"})
    kept = await delivery.hold_back_autonomous(mongo_db, "t1", items)
    assert [i["id"] for i in kept] == ["i-ok"]
    assert (await mongo_db.agent_instructions.find_one({"id": "i-ok"}))["status"] == "pending"


async def test_an_unstamped_block_ip_and_a_list_without_such_rows_pass_unchanged(mongo_db):
    from autonomous_ops import delivery
    await _live(mongo_db)
    items = await _queued(mongo_db, id="i-blk", type="block_ip", instruction="block_ip")
    assert await delivery.hold_back_autonomous(mongo_db, "t1", items) == items
    assert (await mongo_db.agent_instructions.find_one({"id": "i-blk"}))["status"] == "pending"

    plain = await _queued(mongo_db, id="i-scan", type="vulnerability_scan", instruction="scan")
    before = await mongo_db.agent_instructions.find({}).to_list(10)
    assert await delivery.hold_back_autonomous(mongo_db, "t1", plain) == plain
    assert await mongo_db.agent_instructions.find({}).to_list(10) == before         # nothing written


async def test_a_mixed_poll_keeps_the_rest_and_refuses_only_the_gate_only_command(mongo_db):
    from autonomous_ops import delivery
    await _live(mongo_db)
    await _queued(mongo_db, id="m1", type="isolate_host", instruction="x")
    await _queued(mongo_db, id="m2", type="log_collection", instruction="x")
    items = await mongo_db.agent_instructions.find({}).to_list(10)
    kept = await delivery.hold_back_autonomous(mongo_db, "t1", items)
    assert [i["id"] for i in kept] == ["m2"]
    assert (await mongo_db.agent_instructions.find_one({"id": "m1"}))["status"] == "refused"


def test_the_gate_only_list_is_the_six_new_actions():
    from autonomous_ops import delivery
    assert delivery.GATE_ONLY_COMMANDS == ("quarantine_file", "unquarantine_file", "restart_service",
                                           "isolate_host", "restore_host", "reboot_host")
