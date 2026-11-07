"""Staged patch rollouts, gap plan 84-23: a canary row the gate holds is an approval line, never a wedge.

Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py. Time is frozen by
passing ``now`` to the real controller tick; approvals go through the real ``lines.approve_line`` /
``deny_line`` and ``approvals`` paths; the stand-in agent posts a 2.1.16-shaped result through the real
``record_agent_patch_result`` path.

Value: protects=PTCH-06 / PTCH-01 / KD-84-G1: a canary row recorded as ``suggested`` or ``awaiting_approval`` is
the ring's Install line (with Approve and Deny, halting on deny or expiry), a refused canary row is retried as a
new attempt and then fails with a reason, an approved held install stores its job and instruction ids so its
result is read, and a not-delivered rollout row never trips the circuit breaker;
fails_when=a held canary row is stored as the host's automatic install (the host waits for ever with no card), a
Suggest tenant gets no Install card, a refusal parks the host, an approved install is sent but never settled, or
three undelivered rollout rows lower the tenant's level; no_claim=a real agent, a real restart or the live database.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import approvals, breaker, gate, ledger, protected
from autonomous_ops import views as ops_views
from autonomous_ops.rollout import cards, controller, installs, lines, start, store
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.rollout_support import (fresh_scan, post_result, seed_rings, seed_rollout_agent, seed_rollout_tenant,
                                   seed_window, success_result)

T = "t1"
NOW = datetime.now(timezone.utc).replace(second=0, microsecond=0)
BOOT = 1_700_000_000
TOKENS = ("reboot_host", "patch_reversible_check")
ACTOR = {"id": "u1", "name": "Ann"}
APPROVER = {"id": "u2", "name": "Bo"}
RINGS = [{"key": "canary", "name": "Canary", "groupIds": ["G1"], "soakHours": 1},
         {"key": "rest", "name": "Everyone else", "groupIds": [], "soakHours": 1}]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()


def hhmm(moment):
    return moment.strftime("%H:%M")


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def base(db, *, level="undoable_auto"):
    """A ticked tenant at ``level``, two rings (the canary ring is group G1) and a window open at NOW."""
    await ledger.ensure_indexes(db)
    await store.ensure_indexes(db)
    await seed_rollout_tenant(db, T)
    await db.autonomy_settings.update_one({"tenantId": T}, {"$set": {"level": level}})
    await seed_rings(db, T, RINGS)
    await seed_window(db, T, start=hhmm(NOW - timedelta(hours=1)), end=hhmm(NOW + timedelta(hours=3)))


async def host(db, agent_id, *, canary=False, tokens=TOKENS, pending=("openssl",)):
    await seed_rollout_agent(db, T, agent_id, hostname=f"host-{agent_id}", platform="Linux", tokens=tokens,
                             pending=list(pending), boot_time=BOOT, last_seen=NOW)
    if canary:
        await db.agent_group_members.replace_one({"group_id": "G1", "agent_id": agent_id},
                                                 {"group_id": "G1", "agent_id": agent_id, "tenantId": T}, upsert=True)
        await db.agent_groups.replace_one({"id": "G1"}, {"id": "G1", "tenantId": T, "name": "G1"}, upsert=True)


async def begin(db, patch_ids=("openssl",)):
    out = await start.start_rollout(db, T, name="Nov", patch_ids=list(patch_ids), actor=ACTOR, now=NOW)
    assert out["status"] == "started", out
    return out["rolloutId"]


async def rows(db, **extra):
    flt = {"tenantId": T, "dispatcher": "patch_rollout", **extra}
    return [r async for r in db.autonomy_actions.find(flt, {"_id": 0}).sort([("createdAt", 1), ("id", 1)])]


async def instructions(db):
    return [i async for i in db.agent_instructions.find({"tenantId": T}, {"_id": 0})]


async def host_doc(db, agent_id):
    return await db.patch_rollout_hosts.find_one({"tenantId": T, "agentId": agent_id}, {"_id": 0})


async def online_at(db, moment):
    await db.agents.update_many({"tenantId": T}, {"$set": {"lastSeen": moment.isoformat(), "status": "Online"}})


def caller():
    return ops_views.Caller(user=None, tier=None, interactive=True, is_super=False, can_control=True,
                            can_manage=False, can_platform=False)


def escalate_canary(monkeypatch):
    """Make the gate hold the canary's own automatic request for a person (as the hourly limit would)."""
    real = gate.decide

    async def holding(db, req, **kw):
        if (req.reason or {}).get("ruleId") == "rollout:canary_install":
            req.playbook_raise = True
        return await real(db, req, **kw)

    monkeypatch.setattr(gate, "decide", holding)


def refuse_canary(monkeypatch):
    """Make the gate record a refusal for the canary's own automatic request (a stop pressed in between)."""
    real = gate.decide

    async def refusing(db, req, **kw):
        if (req.reason or {}).get("ruleId") == "rollout:canary_install":
            return gate.Decision(outcome="refuse", state="refused", reason="tenant_stop", action_id="AO-refused-x",
                                 recorded=True)
        return await real(db, req, **kw)

    monkeypatch.setattr(gate, "decide", refusing)


async def pass_the_canary(db, rollout_id, *, level_before_last=None):
    """Tick the canary host through install, result, soak and a fresh scan so ring 1 is current."""
    await controller.tick(db, now=NOW)
    job = await db.patch_deployment_jobs.find_one({"rolloutId": rollout_id, "dispatchedAgents": "a1"})
    await post_result(db, job["id"], "a1", success_result(["openssl"]))
    await controller.tick(db, now=NOW + timedelta(minutes=2))
    installed = aware((await host_doc(db, "a1"))["installReportedAt"])
    await fresh_scan(db, "a1", [], installed + timedelta(minutes=10))
    later = installed + timedelta(minutes=61)
    await online_at(db, later)
    if level_before_last:
        await db.autonomy_settings.update_one({"tenantId": T}, {"$set": {"level": level_before_last}})
    await controller.tick(db, now=later)
    return later


# ---------------------------------------------------------------- Task 1: the tracer

async def test_a_suggest_level_canary_row_becomes_the_install_line_and_nothing_is_sent(mongo_db):
    db = mongo_db
    await base(db, level="suggest")
    await host(db, "a1", canary=True)
    await begin(db)
    await controller.tick(db, now=NOW)

    found = await rows(db)
    assert [(r["state"], r["reason"]["ruleId"]) for r in found] == [("suggested", "rollout:canary_install")]
    doc = await host_doc(db, "a1")
    assert doc["lineActionIds"]["install"] == [found[0]["id"]] and doc["linePatchIds"] == ["openssl"]
    assert (doc["state"], doc["waitReason"]) == ("waiting", "approval") and doc.get("installActionId") is None
    assert await instructions(db) == []

    await controller.tick(db, now=NOW + timedelta(seconds=30))                # a second tick decides nothing new
    assert len(await rows(db)) == 1


async def test_approving_the_held_canary_line_sends_it_stores_its_ids_and_the_result_settles_the_host(mongo_db):
    db = mongo_db
    await base(db, level="suggest")
    await host(db, "a1", canary=True)
    rollout_id = await begin(db)
    await controller.tick(db, now=NOW)
    held = (await rows(db))[0]

    answer = await lines.approve_line(db, T, rollout_id, 0, "install", approver=APPROVER, now=NOW)
    assert (answer["status"], answer["when"], answer["approved"]) == ("approved", "now", 1)
    sent = await instructions(db)
    assert len(sent) == 1 and sent[0]["type"] == "install_patches"
    sent_row = (await rows(db))[0]
    assert sent_row["state"] == "dispatching"
    doc = await host_doc(db, "a1")
    assert doc["state"] == "installing"
    assert doc["installJobId"] == held["params"]["job_id"] and doc["installInstructionId"] == sent[0]["id"]
    assert doc.get("installActionId") is None

    await post_result(db, held["params"]["job_id"], "a1", success_result(["openssl"]))
    await controller.tick(db, now=NOW + timedelta(minutes=2))
    assert (await host_doc(db, "a1"))["state"] == "installed"
    assert (await rows(db))[0]["state"] == "executed"


async def test_a_canary_row_the_gate_escalated_to_awaiting_approval_is_the_same_install_line(mongo_db, monkeypatch):
    db = mongo_db
    await base(db)
    await host(db, "a1", canary=True)
    await begin(db)
    escalate_canary(monkeypatch)
    await controller.tick(db, now=NOW)

    found = await rows(db)
    assert [(r["state"], r["reason"]["ruleId"]) for r in found] == [("awaiting_approval", "rollout:canary_install")]
    doc = await host_doc(db, "a1")
    assert doc["lineActionIds"]["install"] == [found[0]["id"]] and doc["linePatchIds"] == ["openssl"]
    assert (doc["state"], doc["waitReason"]) == ("waiting", "approval") and doc.get("installActionId") is None
    assert await instructions(db) == []


# ---------------------------------------------------------------- Task 2: cards, halts, refusals

async def test_at_suggest_level_a_later_ring_raises_its_install_line_and_the_card_offers_approve_and_deny(mongo_db):
    db = mongo_db
    await base(db)
    await host(db, "a1", canary=True)
    await host(db, "b1")
    rollout_id = await begin(db)
    later = await pass_the_canary(db, rollout_id, level_before_last="suggest")

    found = await rows(db, **{"reason.inputs.ring": 1})
    assert [(r["state"], r["targets"]) for r in found] == [("suggested", ["b1"])]
    assert (await host_doc(db, "b1"))["lineActionIds"]["install"] == [found[0]["id"]]
    shown = await cards.list_cards(db, T, caller(), offset=0, limit=10, now=later)
    assert shown["total"] == 1
    line = shown["items"][0]["lines"][0]
    assert (line["line"], line["state"], line["canApprove"], line["canDeny"]) == ("install", "pending", True, True)
    assert line["computers"] == ["host-b1"]


async def test_denying_the_held_canary_line_halts_the_rollout_with_install_denied(mongo_db):
    db = mongo_db
    await base(db, level="suggest")
    await host(db, "a1", canary=True)
    rollout_id = await begin(db)
    await controller.tick(db, now=NOW)
    shown = await cards.list_cards(db, T, caller(), offset=0, limit=10, now=NOW)
    assert shown["total"] == 1 and shown["items"][0]["lines"][0]["canDeny"] is True

    assert (await lines.deny_line(db, T, rollout_id, 0, "install", approver=APPROVER))["status"] == "denied"
    await controller.tick(db, now=NOW + timedelta(minutes=1))
    rollout = await db.patch_rollouts.find_one({"id": rollout_id})
    assert rollout["status"] == "halted" and rollout["haltReason"]["code"] == "install_denied"
    assert await instructions(db) == []          # nothing was installed (the host reading "installed" is WR-04, plan 84-27)


async def test_a_held_canary_line_nobody_answers_in_24_hours_halts_with_approval_expired(mongo_db):
    db = mongo_db
    await base(db, level="suggest")
    await host(db, "a1", canary=True)
    rollout_id = await begin(db)
    await controller.tick(db, now=NOW)

    after = NOW + timedelta(hours=25)
    assert await approvals.expire_due(db, now=after, tenant_id=T) == 1
    await online_at(db, after)
    await controller.tick(db, now=after)
    rollout = await db.patch_rollouts.find_one({"id": rollout_id})
    assert rollout["status"] == "halted" and rollout["haltReason"]["code"] == "approval_expired"
    assert await instructions(db) == []          # nothing was installed (the host reading "installed" is WR-04, plan 84-27)


async def test_a_refused_canary_row_never_parks_the_host_it_is_retried_and_then_fails_with_a_reason(mongo_db, monkeypatch):
    db = mongo_db
    await base(db)
    await host(db, "a1", canary=True)
    await begin(db)
    refuse_canary(monkeypatch)

    await controller.tick(db, now=NOW)
    doc = await host_doc(db, "a1")
    assert (doc["state"], doc["attempt"]) == ("waiting", 1) and doc.get("installActionId") is None
    await controller.tick(db, now=NOW + timedelta(minutes=1))
    doc = await host_doc(db, "a1")
    assert (doc["state"], doc["attempt"]) == ("waiting", 2) and doc.get("installActionId") is None
    await controller.tick(db, now=NOW + timedelta(minutes=2))
    doc = await host_doc(db, "a1")
    assert doc["state"] == "failed" and doc["failureMessage"] and doc["attempt"] == 3
    assert doc.get("installActionId") is None and await instructions(db) == []


async def test_a_held_canary_row_and_a_deferred_patch_on_one_host_share_one_install_line(mongo_db):
    db = mongo_db
    await base(db, level="suggest")
    await host(db, "a1", canary=True, pending=("openssl", "linux-image-6.8"))
    await begin(db, ["openssl", "linux-image-6.8"])
    await controller.tick(db, now=NOW)

    assert sorted(r["params"]["patch_ids"][0] for r in await rows(db)) == ["linux-image-6.8", "openssl"]
    doc = await host_doc(db, "a1")
    assert len(doc["lineActionIds"]["install"]) == 2 and sorted(doc["linePatchIds"]) == ["linux-image-6.8", "openssl"]
    assert doc.get("installActionId") is None and await instructions(db) == []        # nothing installs until approved
    shown = await cards.list_cards(db, T, caller(), offset=0, limit=10, now=NOW)
    assert shown["total"] == 1 and len(shown["items"][0]["lines"]) == 1
    line = shown["items"][0]["lines"][0]
    assert line["line"] == "install" and line["computerTotal"] == 1 and line["computers"] == ["host-a1"]


# ---------------------------------------------------------------- Task 3: the circuit breaker

async def test_three_not_delivered_rollout_rows_do_not_lower_the_tenants_level(mongo_db):
    db = mongo_db
    await base(db)
    for n in range(3):
        at = NOW - timedelta(minutes=n + 1)
        await db.autonomy_actions.insert_one({
            "id": f"AO-nd-{n}", "tenantId": T, "kind": "patching", "dispatcher": "patch_rollout", "state": "failed",
            "autoDispatched": True, "createdAt": at, "updatedAt": at, "finishedAt": at, "command": "install_patches",
            "targets": ["a1"], "reasonCode": "rollout_not_delivered"})
    assert await ledger.recent_finished_auto(db, T, 3) == []
    assert await breaker.evaluate(db, T, now=NOW) is False
    assert (await db.autonomy_settings.find_one({"tenantId": T}))["level"] == "undoable_auto"
