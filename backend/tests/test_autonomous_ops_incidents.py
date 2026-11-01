"""Incidents: one host's burst of alerts is one incident, and isolation is proposed once per incident
(Phase 83, plan 83-11, RESP-09 / D-16 / D-24). Real MongoDB (skips without one) through the throwaway
database of tests/_mongo_test_db.py.

Value: protects=alerts on one host stay one incident until the host has been quiet for exactly an hour,
a restart or a race neither splits nor loses one, the count is evidence and not sweep cycles, and a person
is asked about isolating a host once per incident and never on the machine's own say-so;
fails_when=the 60 minute edge moves, two incidents are open for one host, a tick counts as evidence, the
process clock moves lastAlertAt, an isolate row is automatic or doubled, or a host that cannot isolate
gets a line;
no_claim=a real agent (instructions are only written, never sent anywhere).
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import agent_support, ledger, protected, signals, sweep
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import (seed_feed_ioc, seed_native_verdict, seed_response_agent, seed_tenant)

IP = "45.33.32.156"
T0 = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
NOW = T0
MIN = timedelta(minutes=1)
HOUR = timedelta(hours=1)
TOKENS = ("block_ip_ttl", "quarantine_file", "isolate_host")


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()


async def _open(db, tenant="t1", agent="a1"):
    return [d async for d in db.autonomy_incidents.find({"tenantId": tenant, "agentId": agent, "closed": False})]


# ------------------------------------------------------------------ the quiet gap (D-16)

async def test_two_items_59_minutes_apart_are_one_incident(mongo_db):
    from autonomous_ops import incidents
    first = await incidents.attach(mongo_db, "t1", "a1", T0)
    second = await incidents.attach(mongo_db, "t1", "a1", T0 + 59 * MIN)
    assert first["id"] == second["id"] and first["id"].startswith("INC-")
    (doc,) = await _open(mongo_db)
    assert doc["alertCount"] == 2 and _utc(doc["lastAlertAt"]) == T0 + 59 * MIN and _utc(doc["startedAt"]) == T0


async def test_an_item_exactly_60_minutes_after_the_last_opens_a_new_incident_and_closes_the_old(mongo_db):
    from autonomous_ops import incidents
    first = await incidents.attach(mongo_db, "t1", "a1", T0)
    second = await incidents.attach(mongo_db, "t1", "a1", T0 + HOUR)          # exactly 60 minutes
    assert first["id"] != second["id"]
    old = await mongo_db.autonomy_incidents.find_one({"id": first["id"]})
    assert old["closed"] is True and old["alertCount"] == 1
    (current,) = await _open(mongo_db)
    assert current["id"] == second["id"] and current["alertCount"] == 1


async def test_a_long_attack_stays_one_incident_because_each_item_extends_it(mongo_db):
    from autonomous_ops import incidents
    ids = {(await incidents.attach(mongo_db, "t1", "a1", T0 + i * 50 * MIN))["id"] for i in range(8)}   # 6 hours
    assert len(ids) == 1 and len(await _open(mongo_db)) == 1


async def test_an_older_item_arriving_late_attaches_without_moving_lastAlertAt_back(mongo_db):
    from autonomous_ops import incidents
    first = await incidents.attach(mongo_db, "t1", "a1", T0 + 30 * MIN)
    late = await incidents.attach(mongo_db, "t1", "a1", T0 + 10 * MIN)
    assert late["id"] == first["id"]
    (doc,) = await _open(mongo_db)
    assert doc["alertCount"] == 2 and _utc(doc["lastAlertAt"]) == T0 + 30 * MIN


async def test_get_open_answers_only_while_the_host_has_not_been_quiet_for_an_hour(mongo_db):
    from autonomous_ops import incidents
    made = await incidents.attach(mongo_db, "t1", "a1", T0)
    assert (await incidents.get_open(mongo_db, "t1", "a1", T0 + 59 * MIN))["id"] == made["id"]
    assert await incidents.get_open(mongo_db, "t1", "a1", T0 + HOUR) is None
    assert await incidents.get_open(mongo_db, "t1", "other", T0) is None


# ------------------------------------------------------------------ one open incident, restart safety

async def test_concurrent_attaches_for_a_new_host_end_with_one_open_incident(mongo_db):
    from autonomous_ops import incidents
    await incidents.ensure_indexes(mongo_db)
    made = await asyncio.gather(*[incidents.attach(mongo_db, "t1", "a1", T0 + i * MIN) for i in range(8)])
    assert len({m["id"] for m in made}) == 1
    (doc,) = await _open(mongo_db)
    assert doc["alertCount"] == 8


async def test_the_unique_index_refuses_a_second_open_incident_for_a_host(mongo_db):
    from pymongo.errors import DuplicateKeyError
    from autonomous_ops import incidents
    await incidents.ensure_indexes(mongo_db)
    base = {"tenantId": "t1", "agentId": "a1", "closed": False, "alertCount": 1}
    await mongo_db.autonomy_incidents.insert_one({**base, "id": "INC-1"})
    with pytest.raises(DuplicateKeyError):
        await mongo_db.autonomy_incidents.insert_one({**base, "id": "INC-2"})
    await mongo_db.autonomy_incidents.insert_one({**base, "id": "INC-3", "closed": True})      # closed ones may pile up
    await mongo_db.autonomy_incidents.insert_one({**base, "id": "INC-4", "agentId": "a2"})


async def test_a_fresh_process_on_the_same_database_continues_the_same_incident(mongo_db):
    from motor.motor_asyncio import AsyncIOMotorClient
    from autonomous_ops import incidents
    first = await incidents.attach(mongo_db, "t1", "a1", T0)
    client = AsyncIOMotorClient(os.getenv("MONGO_TEST_URL", "mongodb://127.0.0.1:27017"))
    try:
        again = await incidents.attach(client[mongo_db.name], "t1", "a1", T0 + 5 * MIN)
    finally:
        client.close()
    assert again["id"] == first["id"] and again["alertCount"] == 2


async def test_incidents_of_two_hosts_and_two_tenants_never_mix(mongo_db):
    from autonomous_ops import incidents
    a = await incidents.attach(mongo_db, "t1", "a1", T0)
    b = await incidents.attach(mongo_db, "t1", "a2", T0)
    c = await incidents.attach(mongo_db, "t2", "a1", T0)
    assert len({a["id"], b["id"], c["id"]}) == 3
    assert await mongo_db.autonomy_incidents.count_documents({"closed": False}) == 3


async def test_ensure_indexes_is_repeatable_and_indexes_the_ledger_by_incident(mongo_db):
    from autonomous_ops import incidents
    await incidents.ensure_indexes(mongo_db)
    await incidents.ensure_indexes(mongo_db)
    open_index = [i for i in (await mongo_db.autonomy_incidents.index_information()).values()
                  if i.get("unique") and i.get("partialFilterExpression")]
    assert len(open_index) == 1 and open_index[0]["partialFilterExpression"] == {"closed": False}
    keys = [tuple(k for k, _ in i["key"]) for i in (await mongo_db.autonomy_actions.index_information()).values()]
    assert ("tenantId", "reason.inputs.incidentId", "state") in keys


async def test_migration_028_creates_the_incident_indexes(mongo_db):
    import importlib
    migration = importlib.import_module("migrations.028_security_response")
    await migration.up(mongo_db)
    await migration.up(mongo_db)
    assert any(i.get("unique") and i.get("partialFilterExpression")
               for i in (await mongo_db.autonomy_incidents.index_information()).values())


# ------------------------------------------------------------------ the sweep feeds and reads incidents

async def _world(db, *, shadow=False, tokens=TOKENS, two_signal=None, level="undoable_auto"):
    await ledger.ensure_indexes(db)
    await signals.ensure_indexes(db)
    from autonomous_ops import incidents
    await incidents.ensure_indexes(db)
    await seed_tenant(db, "t1", shadow=shadow, level=level)
    await seed_response_agent(db, "t1", "a1", hostname="host-a1", tokens=list(tokens), last_seen=NOW)
    if two_signal is not None:
        await db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"response": {"twoSignal": two_signal}}})


async def _native(db, at, target=IP):
    await seed_native_verdict(db, "t1", "host-a1", kind="ip", target=target, created_at=at - 5 * MIN)


async def _feed(db, at):
    await seed_feed_ioc(db, ioc_type="url", value=f"http://{IP}/x", source_ip=IP, feed="urlhaus", updated_at=at)


async def _tick(db, at):
    await db.agents.update_one({"id": "a1"}, {"$set": {"lastSeen": at.isoformat()}})
    return await sweep.tick(db, now=at)


async def _rows(db, command=None):
    flt = {"tenantId": "t1", "kind": {"$ne": "control"}}
    if command:
        flt["command"] = command
    return [r async for r in db.autonomy_actions.find(flt, {"_id": 0}).sort("createdAt", 1)]


async def test_a_corroborated_finding_row_carries_the_incident_and_a_suggestion_does_not(mongo_db):
    await _world(mongo_db)
    await _native(mongo_db, NOW)
    await _tick(mongo_db, NOW)
    (suggestion,) = await _rows(mongo_db)
    assert suggestion["state"] == "suggested" and "incidentId" not in suggestion["reason"]["inputs"]
    await _feed(mongo_db, NOW)
    await _tick(mongo_db, NOW + MIN)
    (acting,) = [r for r in await _rows(mongo_db, "block_ip") if r["state"] != "expired"]
    (incident,) = await _open(mongo_db)
    assert acting["reason"]["inputs"]["incidentId"] == incident["id"]


async def test_the_same_evidence_seen_on_ten_ticks_counts_once_and_the_clock_never_moves_lastAlertAt(mongo_db):
    await _world(mongo_db)
    await _native(mongo_db, NOW)
    await _feed(mongo_db, NOW)
    for i in range(10):
        await _tick(mongo_db, NOW + (30 + i) * MIN)
    (incident,) = await _open(mongo_db)
    assert incident["alertCount"] == 2                                  # native and urlhaus, once each
    assert _utc(incident["lastAlertAt"]) == NOW                         # the evidence time, not the tick time


async def test_a_host_quiet_for_an_hour_gets_a_fresh_incident_from_the_next_new_evidence(mongo_db):
    await _world(mongo_db, two_signal=False)
    await _native(mongo_db, NOW)
    await _tick(mongo_db, NOW)
    (first,) = await _open(mongo_db)
    other = "46.101.1.7"
    await seed_native_verdict(mongo_db, "t1", "host-a1", kind="ip", target=other, created_at=NOW + HOUR + 5 * MIN)
    await _tick(mongo_db, NOW + HOUR + 10 * MIN)
    (second,) = await _open(mongo_db)
    assert second["id"] != first["id"]
    assert (await mongo_db.autonomy_incidents.find_one({"id": first["id"]}))["closed"] is True


# ------------------------------------------------------------------ isolation is proposed once per incident (D-24)

IP2 = "46.101.1.7"


async def _confirm(db, at, ip=IP, *, feed=True):
    """The native scan flags an address and (when ``feed``) URLhaus lists it: two different origins."""
    await seed_native_verdict(db, "t1", "host-a1", kind="ip", target=ip, created_at=at - 5 * MIN)
    if feed:
        await seed_feed_ioc(db, ioc_type="url", value=f"http://{ip}/x", source_ip=ip, feed="urlhaus", updated_at=at)


async def _isolate_rows(db):
    return await _rows(db, "isolate_host")


async def _instruction_types(db):
    return sorted([d["type"] async for d in db.agent_instructions.find({"tenantId": "t1"}, {"type": 1})])


async def test_a_corroborated_finding_adds_one_isolate_approval_beside_the_automatic_action(mongo_db):
    await _world(mongo_db)
    await _confirm(mongo_db, NOW)
    await _tick(mongo_db, NOW)
    (block,) = await _rows(mongo_db, "block_ip")
    (isolate,) = await _isolate_rows(mongo_db)
    (incident,) = await _open(mongo_db)
    assert block["state"] == "dispatching"
    assert isolate["state"] == "awaiting_approval" and isolate["autoDispatched"] is False
    assert isolate["reason"]["inputs"]["incidentId"] == block["reason"]["inputs"]["incidentId"] == incident["id"]
    assert isolate["targets"] == ["a1"] and isolate["params"] == {} and isolate["dispatcher"] == "security_response"
    assert isolate["dedupeKey"] == f"t1|sweep|isolate_host|a1|{incident['id']}"
    assert isolate["reasonText"] == block["reasonText"] and isolate["reasonText"].startswith("Two sources agree:")
    assert incident["isolateProposed"] is True
    assert await _instruction_types(mongo_db) == ["block_ip"]            # nothing isolates on its own


async def test_a_second_corroborated_finding_in_the_same_incident_adds_no_second_isolate_row(mongo_db):
    await _world(mongo_db)
    await _confirm(mongo_db, NOW)
    await _tick(mongo_db, NOW)
    await _confirm(mongo_db, NOW + 10 * MIN, IP2)
    await _tick(mongo_db, NOW + 15 * MIN)
    assert len(await _rows(mongo_db, "block_ip")) == 2 and len(await _isolate_rows(mongo_db)) == 1
    assert len(await _open(mongo_db)) == 1


async def test_a_new_incident_may_propose_isolation_again(mongo_db):
    await _world(mongo_db)
    await _confirm(mongo_db, NOW)
    await _tick(mongo_db, NOW)
    later = NOW + 2 * HOUR
    await _confirm(mongo_db, later, IP2)
    await _tick(mongo_db, later + 5 * MIN)
    isolates = await _isolate_rows(mongo_db)
    assert len(isolates) == 2 and len({r["reason"]["inputs"]["incidentId"] for r in isolates}) == 2


async def test_one_signal_with_the_rule_on_proposes_nothing(mongo_db):
    await _world(mongo_db)
    await _confirm(mongo_db, NOW, feed=False)
    await _tick(mongo_db, NOW)
    assert await _isolate_rows(mongo_db) == []
    assert [r["state"] for r in await _rows(mongo_db, "block_ip")] == ["suggested"]


async def test_one_signal_with_the_rule_off_proposes_isolation(mongo_db):
    await _world(mongo_db, two_signal=False)
    await _confirm(mongo_db, NOW, feed=False)
    await _tick(mongo_db, NOW)
    (isolate,) = await _isolate_rows(mongo_db)
    assert isolate["state"] == "awaiting_approval" and isolate["reasonText"].startswith("This organization's two-source rule is off")


async def test_a_host_that_cannot_isolate_gets_no_line_and_the_claim_is_not_spent(mongo_db):
    await _world(mongo_db, tokens=("block_ip_ttl", "quarantine_file"))
    await _confirm(mongo_db, NOW)
    await _tick(mongo_db, NOW)
    assert await _isolate_rows(mongo_db) == []
    assert len(await _rows(mongo_db, "block_ip")) == 1
    (incident,) = await _open(mongo_db)
    assert incident["isolateProposed"] is False


async def test_at_suggest_level_the_isolate_line_is_a_suggested_row_and_nothing_is_dispatched(mongo_db):
    await _world(mongo_db, level="suggest")
    await _confirm(mongo_db, NOW)
    await _tick(mongo_db, NOW)
    (isolate,) = await _isolate_rows(mongo_db)
    assert isolate["state"] == "suggested" and isolate["autoDispatched"] is False
    assert await _instruction_types(mongo_db) == []


async def test_in_shadow_the_isolate_line_is_a_simulation_that_would_have_needed_approval(mongo_db):
    await _world(mongo_db, shadow=True)
    await _confirm(mongo_db, NOW)
    await _tick(mongo_db, NOW)
    (isolate,) = await _isolate_rows(mongo_db)
    assert isolate["state"] == "shadow" and isolate["wouldHave"] == "needs_approval"
    assert await _instruction_types(mongo_db) == []


async def test_a_refusal_that_records_nothing_gives_the_claim_back(mongo_db, monkeypatch):
    from autonomous_ops import gate
    real = gate.decide

    async def refuse_isolation(db, req, **kw):
        if req.actions == ["isolate_host"]:
            return gate.Decision("refuse", "refused", "duplicate", trace=[])
        return await real(db, req, **kw)

    monkeypatch.setattr(gate, "decide", refuse_isolation)
    await _world(mongo_db)
    await _confirm(mongo_db, NOW)
    await _tick(mongo_db, NOW)
    assert await _isolate_rows(mongo_db) == []
    (incident,) = await _open(mongo_db)
    assert incident["isolateProposed"] is False


async def test_claim_isolate_has_one_winner_and_release_gives_it_back(mongo_db):
    from autonomous_ops import incidents
    made = await incidents.attach(mongo_db, "t1", "a1", T0)
    wins = await asyncio.gather(*[incidents.claim_isolate(mongo_db, "t1", made["id"]) for _ in range(6)])
    assert wins.count(True) == 1
    await incidents.release_isolate(mongo_db, "t1", made["id"])
    assert await incidents.claim_isolate(mongo_db, "t1", made["id"]) is True
    assert await incidents.claim_isolate(mongo_db, "t1", "INC-nope") is False


async def test_the_isolate_line_is_never_sent_to_the_dispatcher_by_a_tick(mongo_db, monkeypatch):
    from autonomous_ops import response_dispatch
    sent = []
    real = response_dispatch.send

    async def spy(db, row):
        sent.append(row.get("command"))
        return await real(db, row)

    monkeypatch.setattr(response_dispatch, "send", spy)
    for level in ("undoable_auto", "suggest"):
        await _world(mongo_db, level=level)
        await _confirm(mongo_db, NOW)
        await _tick(mongo_db, NOW)
    assert "isolate_host" not in sent and "block_ip" in sent
    assert all(r["state"] != "dispatching" for r in await _isolate_rows(mongo_db))
