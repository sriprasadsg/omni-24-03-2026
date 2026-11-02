"""RESP-05 / D-15: confirming an isolation, telling the agent, and noticing that it returned on its own.
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py; the routes are mounted as
in production with the identity replaced by a dependency override.

Value: protects=a person with control access can keep an isolated computer isolated with one click (single use,
recorded with their name), only the agent that holds the isolation is told, an isolation that returned by itself is
recorded as such and never as a failure of an automatic action, and no stop, key, view role or other tenant can
confirm; fails_when=two clicks both win, a confirm lands at or after the revert time, a stop lets it through, the
reply names another agent's or tenant's isolation, a confirmed or not-yet-reported row is marked reverted, a revert
and a confirm both take effect, or the revert counts toward the circuit breaker; no_claim=a real agent (its
side is tested in the Rust suite) and the heartbeat route itself, which this plan does not change.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from autonomous_ops import approvals, breaker, isolation, ledger, response_messages as rm, response_settings, sweep, verify
from tests._autonomous_ops_http import _env, api  # noqa: F401  (fixtures)
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_response_agent, seed_tenant

NOW = datetime.now(timezone.utc).replace(microsecond=0)
REVERTS = NOW + timedelta(hours=3)
APPROVER = {"username": "carol@t1.test", "display": "Carol", "tier": "tenant"}
PATH = "/api/autonomous-ops/actions/{}/confirm-isolation"


async def isolate_row(db, rid="iso1", *, tenant="t1", agent="a1", state="verified", reverts=REVERTS, task="task-iso1", **extra):
    doc = {"id": rid, "tenantId": tenant, "kind": "security", "origin": "sweep", "dispatcher": "security_response",
           "command": "isolate_host", "actions": ["isolate_host"], "targets": [agent], "target": agent, "params": {},
           "state": state, "reasonCode": "class_approve", "reasonText": "Why", "dedupeKey": f"{tenant}|{rid}",
           "autoDispatched": False, "instructionIds": [task], "createdAt": NOW - timedelta(hours=1), "updatedAt": NOW,
           "reason": {"ruleId": "sweep:isolate_host", "inputs": {"incidentId": "INC-1"}},
           "approval": {"approver": {"username": "a"}, "expiresAt": NOW}, "verifiedAt": NOW,
           "undo": {"available": True, "action": "restore_host", "params": {}, "undoneAt": None, "undoneBy": None}, **extra}
    if reverts is not None and "isolation" not in extra:
        doc["isolation"] = {"revertsAt": reverts}
    await db.autonomy_actions.insert_one(doc)
    return doc


async def report(db, agent="a1", *, isolation_state="absent", seen=None, **extra):
    """The agent's heartbeat state: ``isolation_state`` None (holds nothing), a dict (holds one), or absent (no report)."""
    update = {"lastSeen": (seen or NOW).isoformat()}
    if isolation_state != "absent":
        update["meta.response_state"] = {"v": 1, "isolation": isolation_state, "boot_time": 1, "active_blocks": 0, **extra}
    await db.agents.update_one({"id": agent}, {"$set": update})


async def get(db, rid="iso1"):
    return await db.autonomy_actions.find_one({"id": rid}, {"_id": 0})


async def audit(db, tenant="t1"):
    return [e["action"] async for e in db.audit_logs.find({"tenantId": tenant})]


@pytest.fixture
async def world(api):
    await ledger.ensure_indexes(api.db)
    await seed_response_agent(api.db, "t1", "a1", hostname="host-a1", tokens=["isolate_host", "restore_host"], last_seen=NOW)
    await seed_response_agent(api.db, "t1", "a2", hostname="host-a2", tokens=["isolate_host", "restore_host"], last_seen=NOW)
    await seed_response_agent(api.db, "t2", "b1", hostname="host-b1", tokens=["isolate_host"], last_seen=NOW)
    return api


# ------------------------------------------------------------------ the revert time is recorded

async def test_settle_records_when_the_host_returns_by_itself_and_no_block_window(mongo_db):
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await isolate_row(mongo_db, "x", state="executed", reverts=None)
    body = {"result": {"outcome": "isolated", "verify": {"ok": True, "check": "management_connection_open"}}}
    row = await ledger.get(mongo_db, "t1", "x")
    assert await verify.settle(mongo_db, "t1", row, body, now=NOW) == "verified"
    saved = await get(mongo_db, "x")
    assert saved["isolation"]["revertsAt"].replace(tzinfo=timezone.utc) == NOW + timedelta(seconds=14400)
    assert "blockedUntil" not in saved                      # an isolation has a revert time, not a block window
    # an isolation another row already holds has no revert of its own to confirm
    await isolate_row(mongo_db, "y", state="executed", reverts=None, dedupeKey="k2")
    again = {"result": {"outcome": "already_applied", "verify": {"ok": True, "check": "management_connection_open"}}}
    assert await verify.settle(mongo_db, "t1", await ledger.get(mongo_db, "t1", "y"), again, now=NOW) == "verified"
    assert "isolation" not in await get(mongo_db, "y")
    # a body that does carry expires_in is believed
    await isolate_row(mongo_db, "z", state="executed", reverts=None, dedupeKey="k3")
    timed = {"result": {**body["result"], "expires_in": 600}}
    await verify.settle(mongo_db, "t1", await ledger.get(mongo_db, "t1", "z"), timed, now=NOW)
    assert (await get(mongo_db, "z"))["isolation"]["revertsAt"].replace(tzinfo=timezone.utc) == NOW + timedelta(seconds=600)


# ------------------------------------------------------------------ the route

async def test_confirm_is_recorded_with_the_persons_name_and_an_audit_event(world):
    await isolate_row(world.db)
    done = await world.call("POST", PATH.format("iso1"), role="security_analyst", username="sam@t1.test")
    assert done.status_code == 200 and done.json()["status"] == "confirmed"
    assert done.json()["action"]["id"] == "iso1" and done.json()["action"]["state"] == "verified"
    saved = await get(world.db)
    assert saved["isolation"]["confirmedBy"]["username"] == "sam@t1.test" and saved["isolation"]["confirmedAt"] is not None
    assert saved["state"] == "verified"                      # nothing about the state changes
    assert "autonomous_ops.isolation_confirmed" in await audit(world.db)
    again = await world.call("POST", PATH.format("iso1"), role="tenant_admin")
    assert again.status_code == 409 and again.json()["detail"] == "This decision was already made."
    assert (await audit(world.db)).count("autonomous_ops.isolation_confirmed") == 1


async def test_who_may_confirm(world):
    await isolate_row(world.db)
    for role in ("analyst", "platform_support"):
        got = await world.call("POST", PATH.format("iso1") + ("?tenantId=t1" if role == "platform_support" else ""), role=role)
        assert got.status_code == 403, role
    key = await world.call("POST", PATH.format("iso1"), role="tenant_admin", auth="api_key",
                           scopes=["view:autonomous_ops", "control:autonomous_ops", "manage:autonomous_ops"])
    assert key.status_code == 403
    other = await world.call("POST", PATH.format("iso1"), role="security_analyst", tenant="t2")
    assert other.status_code == 404                           # another organization's row does not exist for it
    assert (await world.call("POST", PATH.format("iso1") + "?tenantId=t1", role="security_analyst", tenant="t2")).status_code == 403
    assert (await get(world.db))["isolation"].get("confirmedAt") is None
    assert (await world.call("POST", PATH.format("iso1"), role="super_admin")).status_code == 400       # must name a tenant
    assert (await world.call("POST", PATH.format("iso1") + "?tenantId=t1", role="super_admin")).status_code == 200


async def test_refusals_have_their_own_words(world):
    await isolate_row(world.db, "late", reverts=NOW - timedelta(seconds=1), task="t-late")
    await world.db.autonomy_actions.insert_one({**(await get(world.db, "late")), "id": "blk", "command": "block_ip",
                                                "dedupeKey": "k-blk"})
    await isolate_row(world.db, "gone", state="rolled_back", reasonCode="auto_reverted", dedupeKey="k-gone")
    await isolate_row(world.db, "never", state="awaiting_approval", reverts=None, dedupeKey="k-never")
    cases = {"late": rm.API_DETAIL["revert_passed"], "gone": rm.API_DETAIL["revert_passed"],
             "blk": rm.API_DETAIL["not_isolated"], "never": rm.API_DETAIL["not_isolated"]}
    for rid, text in cases.items():
        got = await world.call("POST", PATH.format(rid), role="security_analyst")
        assert (got.status_code, got.json()["detail"]) == (409, text), rid
    assert (await world.call("POST", PATH.format("nope"), role="security_analyst")).status_code == 404
    assert "autonomous_ops.isolation_confirmed" not in await audit(world.db)


async def test_a_stop_refuses_the_confirm_and_changes_nothing(world):
    await isolate_row(world.db)
    await world.db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"stop": {"active": True}}})
    got = await world.call("POST", PATH.format("iso1"), role="security_analyst")
    assert got.status_code == 409 and "stopped" in got.json()["detail"]
    assert (await get(world.db))["isolation"].get("confirmedAt") is None
    assert await audit(world.db) == [] or "autonomous_ops.isolation_confirmed" not in await audit(world.db)


# ------------------------------------------------------------------ the edges

async def test_a_confirm_at_the_revert_time_is_refused_and_one_millisecond_earlier_succeeds(mongo_db):
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await isolate_row(mongo_db, "edge", reverts=REVERTS)
    assert await isolation.confirm(mongo_db, "t1", "edge", APPROVER, now=REVERTS) == {"status": "refused", "reason": "revert_passed"}
    assert (await get(mongo_db, "edge"))["isolation"].get("confirmedAt") is None
    just = await isolation.confirm(mongo_db, "t1", "edge", APPROVER, now=REVERTS - timedelta(milliseconds=1))
    assert just["status"] == "confirmed"


async def test_two_confirms_at_once_have_one_winner(mongo_db):
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await isolate_row(mongo_db, "race")
    first, second = await asyncio.gather(isolation.confirm(mongo_db, "t1", "race", APPROVER, now=NOW),
                                         isolation.confirm(mongo_db, "t1", "race", dict(APPROVER, username="dan"), now=NOW))
    assert sorted([first["status"], second["status"]]) == ["already_handled", "confirmed"]
    events = [e async for e in mongo_db.audit_logs.find({"action": "autonomous_ops.isolation_confirmed"})]
    assert len(events) == 1


async def test_a_confirm_and_the_automatic_revert_in_one_moment_end_in_exactly_one_of_them(mongo_db):
    """The agent reports nothing held; the click and the sweep arrive together just before the revert time."""
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await seed_response_agent(mongo_db, "t1", "a1", hostname="host-a1", tokens=["isolate_host"], last_seen=NOW)
    await report(mongo_db, isolation_state=None)
    for n in range(12):
        rid = f"r{n}"
        await isolate_row(mongo_db, rid, reverts=REVERTS, dedupeKey=f"k{n}", task=f"t{n}")
        click = isolation.confirm(mongo_db, "t1", rid, APPROVER, now=REVERTS - timedelta(milliseconds=1))
        await asyncio.gather(click, isolation.run(mongo_db, "t1", None, None, REVERTS))
        saved = await get(mongo_db, rid)
        confirmed = bool((saved.get("isolation") or {}).get("confirmedAt"))
        assert confirmed != (saved["state"] == "rolled_back"), saved          # one outcome, never both or neither


# ------------------------------------------------------------------ the agent is told

async def test_the_heartbeat_reply_lists_only_this_agents_confirmed_isolations(world):
    await isolate_row(world.db, "c1", task="TASK-A1", isolation={"revertsAt": REVERTS, "confirmedAt": NOW})
    await isolate_row(world.db, "u1", task="TASK-UNCONFIRMED", agent="a1", dedupeKey="k-u1")
    await isolate_row(world.db, "c2", task="TASK-A2", agent="a2", dedupeKey="k-c2", isolation={"confirmedAt": NOW, "revertsAt": REVERTS})
    await isolate_row(world.db, "c3", task="TASK-T2", tenant="t2", agent="b1", dedupeKey="k-c3", isolation={"confirmedAt": NOW, "revertsAt": REVERTS})
    await isolate_row(world.db, "gone", task="TASK-UNDONE", state="undone", dedupeKey="k-gone", isolation={"confirmedAt": NOW, "revertsAt": REVERTS})
    permitted = {"remediation_executor"}
    assert await response_settings.heartbeat_reply(world.db, "t1", "a1", permitted) == {"watchedServices": [], "isolationConfirmed": ["TASK-A1"]}
    assert (await response_settings.heartbeat_reply(world.db, "t1", "a2", permitted))["isolationConfirmed"] == ["TASK-A2"]
    assert (await response_settings.heartbeat_reply(world.db, "t2", "b1", permitted))["isolationConfirmed"] == ["TASK-T2"]
    assert (await response_settings.heartbeat_reply(world.db, "t2", "a1", permitted)).get("isolationConfirmed") is None   # not that tenant's agent
    # no confirmed isolation: the key is left out so a reply stays small; the capability tick does not gate it
    await world.db.autonomy_actions.delete_many({"tenantId": "t1"})
    assert await response_settings.heartbeat_reply(world.db, "t1", "a1", permitted) == {"watchedServices": []}
    await isolate_row(world.db, "c4", task="TASK-NOCAP", isolation={"confirmedAt": NOW, "revertsAt": REVERTS})
    assert await response_settings.heartbeat_reply(world.db, "t1", "a1", set()) == {"isolationConfirmed": ["TASK-NOCAP"]}


async def test_the_reply_never_fails_a_heartbeat(world, monkeypatch):
    async def broken(*a, **k):
        raise RuntimeError("database away")
    monkeypatch.setattr(isolation, "confirmed_ids", broken)
    assert await response_settings.heartbeat_reply(world.db, "t1", "a1", {"remediation_executor"}) == {"watchedServices": []}


# ------------------------------------------------------------------ an isolation that ended on its own

async def test_an_unconfirmed_isolation_the_agent_no_longer_holds_is_recorded_as_returned(world):
    await isolate_row(world.db, reverts=NOW - timedelta(minutes=1))
    await report(world.db, isolation_state=None)
    counts = await sweep.tick(world.db, now=NOW)                      # the stage is part of the real sweep
    assert counts["reverted"] == 1
    saved = await get(world.db)
    assert saved["state"] == "rolled_back" and saved["reasonCode"] == "auto_reverted" and saved["finishedAt"] is not None
    page = await world.call("GET", "/api/autonomous-ops/actions?bucket=undone", role="security_analyst")
    item = page.json()["items"][0]
    assert item["resultText"] == "Returned to the network automatically after 4 hours. Nobody confirmed the isolation."
    assert item["canUndo"] is False and item["bucket"] == "undone"
    assert "autonomous_ops.rolled_back" in await audit(world.db)


async def test_the_sweep_waits_when_it_cannot_tell(world):
    """Each row has its own agent. All of them are past their revert time except `early`."""
    past, held = NOW - timedelta(minutes=1), {"id": "t", "active": True, "confirmed": False, "revert_in_seconds": 9000}
    plan = {  # row id: (agent report, revertsAt, extra row fields)
        "held": (held, past, {}),                                   # the host still holds it
        "silent": ("absent", past, {}),                             # the host never reported a state
        "unreadable": (None, past, {}),                             # ... or reported that it could not read it
        "early": (None, NOW + timedelta(minutes=5), {}),            # nothing held, but the time is not up
        "kept": (None, past, {"isolation": {"revertsAt": past, "confirmedAt": NOW - timedelta(hours=1)}}),
    }
    for rid, (state, reverts, extra) in plan.items():
        agent = "g-" + rid
        await seed_response_agent(world.db, "t1", agent, hostname="host-" + agent, tokens=["isolate_host"], last_seen=NOW)
        await isolate_row(world.db, rid, agent=agent, reverts=reverts, dedupeKey="k-" + rid, task="t-" + rid, **extra)
        await report(world.db, agent, isolation_state=state, **({"state_unreadable": True} if rid == "unreadable" else {}))
    await isolate_row(world.db, "other", tenant="t2", agent="b1", reverts=past, dedupeKey="k-o", task="t-o")
    await report(world.db, "b1", isolation_state=None)
    counts = await isolation.run(world.db, "t1", None, None, NOW)
    assert counts["reverted"] == 0
    for rid in plan:
        assert (await get(world.db, rid))["state"] == "verified", rid
    assert (await get(world.db, "other"))["state"] == "verified"        # another tenant's row is never touched by t1's pass


async def test_the_revert_time_is_pulled_in_to_what_the_agent_reports_never_pushed_out(world):
    await isolate_row(world.db, reverts=NOW + timedelta(hours=4))
    await report(world.db, isolation_state={"id": "task-iso1", "active": True, "confirmed": False, "revert_in_seconds": 3600})
    assert (await isolation.run(world.db, "t1", None, None, NOW))["pulled_in"] == 1
    assert (await get(world.db))["isolation"]["revertsAt"].replace(tzinfo=timezone.utc) == NOW + timedelta(hours=1)
    await report(world.db, isolation_state={"id": "task-iso1", "active": True, "confirmed": False, "revert_in_seconds": 7200})
    assert (await isolation.run(world.db, "t1", None, None, NOW))["pulled_in"] == 0
    assert (await get(world.db))["isolation"]["revertsAt"].replace(tzinfo=timezone.utc) == NOW + timedelta(hours=1)


async def test_the_revert_does_not_count_toward_the_circuit_breaker(world):
    for n in range(4):
        await isolate_row(world.db, f"iso{n}", reverts=NOW - timedelta(minutes=1), dedupeKey=f"k{n}", task=f"t{n}",
                          agent="a1", autoDispatched=True)      # even if a row were counted as automatic, this ending is not a failure
    await report(world.db, isolation_state=None)
    assert (await isolation.run(world.db, "t1", None, None, NOW))["reverted"] == 4
    assert await ledger.recent_finished_auto(world.db, "t1") == []
    assert not await breaker.evaluate(world.db, "t1", now=NOW)


# ------------------------------------------------------------------ undoing a confirmed isolation

async def test_undo_of_an_isolation_sends_restore_host_with_its_isolation_id(world):
    await isolate_row(world.db, task="task-iso1", isolation={"revertsAt": REVERTS, "confirmedAt": NOW},
                      undo={"available": True, "action": "restore_host", "params": {}, "undoneAt": None, "undoneBy": None})
    await world.db.agents.update_one({"id": "a1"}, {"$set": {"lastSeen": datetime.now(timezone.utc).isoformat()}})
    out = await approvals.undo(world.db, "t1", "iso1", actor=APPROVER)
    assert out["status"] == "undone", out
    sent = [d async for d in world.db.agent_instructions.find({"tenantId": "t1", "type": "restore_host"}, {"_id": 0})]
    assert len(sent) == 1 and sent[0]["parameters"] == {"isolation_id": "task-iso1"}
    assert (await get(world.db))["state"] == "undone"
