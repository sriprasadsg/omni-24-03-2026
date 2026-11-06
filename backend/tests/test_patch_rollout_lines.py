"""Staged patch rollouts, plan 84-03: approval lines on a real database.

Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py. Time is frozen by
passing ``now`` to the real controller tick; the stand-in agent posts a 2.1.16-shaped result through the real
``record_agent_patch_result`` path; approvals go through the real ``approvals.approve`` / ``deny``.

Value: protects=PTCH-06 / PTCH-05 / D-05 / D-06 / D-07 / R11: every install after the canary, and every canary
install that is not reversible or cannot be checked, waits for one person's decision per line; the hourly
limit never turns canary installs into cards; a denied or expired line halts the rollout and closes every
other open row; fails_when=an install is sent before approval, a kernel package installs on its own, a canary
host is decided out of order or past the hourly limit, a deferral produces no approval row, a halted rollout
keeps a row that could still be approved or delivered, or one line's approval reaches another line;
no_claim=a real agent, a real restart, or the live database.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import approvals, delivery, ledger, protected
from autonomous_ops.rollout import controller, lines, start, store
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.rollout_support import (failure_result, fresh_scan, post_result, seed_group, seed_rings,
                                   seed_rollout_agent, seed_rollout_tenant, seed_window, success_result)

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


async def base(db, *, shadow=False, window=True):
    """A ticked tenant, two rings (the canary ring is group G1) and a window that is open at NOW."""
    await ledger.ensure_indexes(db)
    await store.ensure_indexes(db)
    await seed_rollout_tenant(db, T, shadow=shadow)
    await seed_rings(db, T, RINGS)
    if window:
        await seed_window(db, T, start=hhmm(NOW - timedelta(hours=1)), end=hhmm(NOW + timedelta(hours=3)))
    else:
        await seed_window(db, T, start=hhmm(NOW + timedelta(hours=2)), end=hhmm(NOW + timedelta(hours=3)))


async def host(db, agent_id, *, hostname=None, canary=False, tokens=TOKENS, pending=("openssl",), at=None):
    await seed_rollout_agent(db, T, agent_id, hostname=hostname or f"host-{agent_id}", platform="Linux",
                             tokens=tokens, pending=list(pending), boot_time=BOOT, last_seen=at or NOW)
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


async def pass_the_canary(db, rollout_id, patch_ids=("openssl",), agent="a1"):
    """Tick the canary host through install, result, soak and a fresh scan, so ring 1 is current. Returns the
    time of the last tick (ring 0 passed, and ring 1 has had its first tick)."""
    await controller.tick(db, now=NOW)
    job = await db.patch_deployment_jobs.find_one({"rolloutId": rollout_id, "dispatchedAgents": agent})
    await post_result(db, job["id"], agent, success_result(list(patch_ids)))
    await controller.tick(db, now=NOW + timedelta(minutes=2))
    installed = aware((await host_doc(db, agent))["installReportedAt"])
    await fresh_scan(db, agent, [], installed + timedelta(minutes=10))
    later = installed + timedelta(minutes=61)
    await online_at(db, later)
    await controller.tick(db, now=later)
    return later


# ---------------------------------------------------------------- later rings

async def test_after_the_canary_passes_ring_one_gets_one_approval_row_per_computer_and_nothing_is_sent(mongo_db):
    db = mongo_db
    await base(db)
    await host(db, "a1", canary=True)
    await host(db, "b1")
    await host(db, "b2")
    rollout_id = await begin(db)
    later = await pass_the_canary(db, rollout_id)

    found = await rows(db, **{"reason.inputs.ring": 1})
    assert sorted(r["targets"][0] for r in found) == ["b1", "b2"]
    for row in found:
        assert (row["command"], row["state"], row["reasonCode"]) == ("install_patches", "awaiting_approval", "playbook_raised")
        assert row["reason"]["inputs"]["rolloutId"] == rollout_id
        assert row["reason"]["inputs"]["line"] == "install" and row["reason"]["inputs"]["patchIds"] == ["openssl"]
        assert "require_reversible" not in row["params"] and row["params"]["patch_ids"] == ["openssl"]
        assert row["params"]["job_id"] and "passed its health check" in row["reasonText"]
        assert row["approval"]["expiresAt"] is not None
    assert len(await instructions(db)) == 1                                    # only the canary instruction exists
    assert await db.patch_deployment_jobs.count_documents({"rolloutId": rollout_id}) == 1
    for agent in ("b1", "b2"):
        doc = await host_doc(db, agent)
        assert (doc["state"], doc["waitReason"]) == ("waiting", "approval")
        assert len(doc["lineActionIds"]["install"]) == 1
    rollout = await db.patch_rollouts.find_one({"id": rollout_id})
    assert rollout["currentRing"] == 1 and rollout["rings"][1]["state"] == "waiting_for_approval"

    await controller.tick(db, now=later + timedelta(minutes=1))                # a second tick raises nothing new
    assert len(await rows(db, **{"reason.inputs.ring": 1})) == 2 and len(await instructions(db)) == 1


async def test_a_later_ring_raises_nothing_while_the_window_is_closed_and_raises_when_it_opens(mongo_db):
    db = mongo_db
    await base(db)
    await db.maintenance_windows.delete_many({})
    await seed_window(db, T, start=hhmm(NOW - timedelta(hours=1)), end=hhmm(NOW + timedelta(minutes=30)))
    await host(db, "a1", canary=True)
    await host(db, "b1")
    rollout_id = await begin(db)
    later = await pass_the_canary(db, rollout_id)                                # the window closed at NOW + 30 min
    rollout = await db.patch_rollouts.find_one({"id": rollout_id})
    assert rollout["currentRing"] == 1 and rollout["rings"][1]["state"] == "waiting_for_window"
    assert await rows(db, **{"reason.inputs.ring": 1}) == []

    tomorrow = NOW + timedelta(hours=23, minutes=10)                                        # the daily window is open again
    await online_at(db, tomorrow)
    await controller.tick(db, now=tomorrow)
    assert len(await rows(db, **{"reason.inputs.ring": 1})) == 1


# ---------------------------------------------------------------- the canary split

async def test_a_canary_host_that_cannot_check_reversibility_gets_one_approval_row_for_all_its_patches(mongo_db):
    db = mongo_db
    await base(db)
    await host(db, "b", canary=True, tokens=("reboot_host",), pending=("openssl", "curl"))
    await begin(db, ["openssl", "curl"])
    await controller.tick(db, now=NOW)
    found = await rows(db)
    assert [(r["state"], r["targets"], r["params"]["patch_ids"]) for r in found] == [
        ("awaiting_approval", ["b"], ["openssl", "curl"])]
    assert "require_reversible" not in found[0]["params"]
    assert await instructions(db) == []
    doc = await host_doc(db, "b")
    assert (doc["state"], doc["waitReason"]) == ("waiting", "approval") and doc.get("installActionId") is None


async def test_a_canary_host_splits_into_one_automatic_row_and_one_approval_row(mongo_db):
    db = mongo_db
    await base(db)
    await host(db, "c", canary=True, pending=("openssl", "linux-image-6.8"))
    await begin(db, ["openssl", "linux-image-6.8"])
    await controller.tick(db, now=NOW)

    found = await rows(db)
    auto = [r for r in found if r["state"] == "dispatching"]
    cards = [r for r in found if r["state"] == "awaiting_approval"]
    assert len(auto) == 1 and auto[0]["params"]["patch_ids"] == ["openssl"] and auto[0]["params"]["require_reversible"] is True
    assert len(cards) == 1 and cards[0]["params"]["patch_ids"] == ["linux-image-6.8"]
    assert len(await instructions(db)) == 1
    doc = await host_doc(db, "c")
    assert doc["state"] == "installing" and doc["linePatchIds"] == ["linux-image-6.8"]

    await controller.tick(db, now=NOW + timedelta(seconds=30))
    assert len(await rows(db)) == 2 and len(await instructions(db)) == 1


async def test_a_host_whose_patches_are_all_restart_needing_gets_no_automatic_row(mongo_db):
    db = mongo_db
    await base(db)
    await host(db, "c", canary=True, pending=("linux-image-6.8",))
    await begin(db, ["linux-image-6.8"])
    await controller.tick(db, now=NOW)
    found = await rows(db)
    assert [(r["state"], r["params"]["patch_ids"]) for r in found] == [("awaiting_approval", ["linux-image-6.8"])]
    assert await instructions(db) == []


async def test_the_host_is_installed_only_when_the_automatic_and_the_approval_row_have_both_settled(mongo_db):
    db = mongo_db
    await base(db)
    await host(db, "c", canary=True, pending=("openssl", "linux-image-6.8"))
    rollout_id = await begin(db, ["openssl", "linux-image-6.8"])
    await controller.tick(db, now=NOW)
    job = await db.patch_deployment_jobs.find_one({"rolloutId": rollout_id})
    await post_result(db, job["id"], "c", success_result(["openssl"]))
    await controller.tick(db, now=NOW + timedelta(minutes=2))
    doc = await host_doc(db, "c")
    assert (doc["state"], doc["waitReason"]) == ("waiting", "approval")           # the kernel still waits for a person
    automatic = [r for r in await rows(db) if r["params"].get("require_reversible")]
    assert automatic[0]["state"] == "executed"
    assert (await db.patch_rollouts.find_one({"id": rollout_id}))["rings"][0]["state"] == "waiting_for_approval"


async def test_a_not_reversible_deferral_ends_the_automatic_row_and_raises_an_approval_row(mongo_db):
    db = mongo_db
    await base(db)
    await host(db, "a", canary=True)
    rollout_id = await begin(db)
    await controller.tick(db, now=NOW)
    job = await db.patch_deployment_jobs.find_one({"rolloutId": rollout_id})
    await post_result(db, job["id"], "a", {
        "status": "completed", "successful": 0, "failed": 0, "total": 1,
        "results": [{"patch_id": "openssl", "status": "deferred", "code": "not_reversible",
                     "message": "Not installed: this update cannot be reversed on this computer.",
                     "reboot_required": False}]})
    await controller.tick(db, now=NOW + timedelta(minutes=2))

    found = await rows(db)
    assert [r["state"] for r in found] == ["executed", "awaiting_approval"]
    assert found[0]["reasonCode"] == "rollout_not_reversible"
    card = found[1]
    assert card["params"]["patch_ids"] == ["openssl"] and "require_reversible" not in card["params"]
    assert card["reason"]["inputs"]["attempt"] == 2 and card["reason"]["inputs"]["patchIds"] == ["openssl"]
    assert "can't be reversed" in card["reasonText"]
    assert len(await instructions(db)) == 1
    doc = await host_doc(db, "a")
    assert (doc["state"], doc["waitReason"]) == ("waiting", "approval")


async def test_a_failed_install_result_still_fails_the_host(mongo_db):
    db = mongo_db
    await base(db)
    await host(db, "a", canary=True)
    rollout_id = await begin(db)
    await controller.tick(db, now=NOW)
    job = await db.patch_deployment_jobs.find_one({"rolloutId": rollout_id})
    await post_result(db, job["id"], "a", failure_result(["openssl"], "dpkg error"))
    await controller.tick(db, now=NOW + timedelta(minutes=2))
    assert (await host_doc(db, "a"))["state"] == "failed"
    assert (await db.patch_rollouts.find_one({"id": rollout_id}))["status"] == "halted"


# ---------------------------------------------------------------- the hourly limit

async def seed_recent_auto(db, n, at):
    for i in range(n):
        await db.autonomy_actions.insert_one({
            "id": f"AO-seed-{i}", "tenantId": T, "kind": "remediation", "dispatcher": "instruction", "state": "executed",
            "autoDispatched": True, "createdAt": at, "updatedAt": at, "command": "restart_service", "targets": ["x"]})


async def test_the_hourly_limit_decides_one_canary_install_and_never_makes_a_rate_limit_card(mongo_db):
    db = mongo_db
    await base(db)
    # Ids sort the opposite way to host names, so only the name order can pick alpha.
    await host(db, "z1", hostname="Charlie", canary=True)
    await host(db, "z2", hostname="alpha", canary=True)
    await host(db, "z3", hostname="Bravo", canary=True)
    await begin(db)
    await seed_recent_auto(db, 19, NOW)

    await controller.tick(db, now=NOW + timedelta(minutes=1))
    automatic = [r for r in await rows(db) if r["state"] == "dispatching"]
    assert [r["targets"] for r in automatic] == [["z2"]]                         # alpha, by hostname
    assert not [r for r in await rows(db) if r["reasonCode"] == "rate_limit"]
    assert await db.autonomy_actions.count_documents({"reasonCode": "rate_limit"}) == 0
    assert [(await host_doc(db, a))["state"] for a in ("z2", "z1", "z3")] == ["installing", "waiting", "waiting"]

    later = NOW + timedelta(minutes=62)
    await online_at(db, later)
    await controller.tick(db, now=later)
    sent = [r for r in await rows(db) if r["state"] == "dispatching"]
    assert sorted(r["targets"][0] for r in sent) == ["z1", "z2", "z3"]
    assert await db.autonomy_actions.count_documents({"reasonCode": "rate_limit"}) == 0


# ---------------------------------------------------------------- shadow

async def test_a_shadow_tenant_records_simulations_and_no_card(mongo_db):
    db = mongo_db
    await base(db, shadow=True)
    await host(db, "b", canary=True, tokens=("reboot_host",))
    await begin(db)
    await controller.tick(db, now=NOW)
    found = await rows(db)
    assert [r["state"] for r in found] == ["shadow"] and found[0]["wouldHave"] == "needs_approval"
    assert await db.autonomy_actions.count_documents({"tenantId": T, "state": "awaiting_approval"}) == 0
    assert await instructions(db) == []


# ---------------------------------------------------------------- a denied or expired line halts the rollout (R11)

async def ring_one_world(db, agents=("b1", "b2")):
    """The canary passed and ring one has an install card per computer. Returns (rollout id, time)."""
    await base(db)
    await host(db, "a1", canary=True)
    for agent in agents:
        await host(db, agent)
    rollout_id = await begin(db)
    later = await pass_the_canary(db, rollout_id)
    assert len(await rows(db, **{"reason.inputs.ring": 1, "state": "awaiting_approval"})) == len(agents)
    return rollout_id, later


async def add_reboot_card(db, rollout_id, agent, at):
    rollout = await db.patch_rollouts.find_one({"id": rollout_id}, {"_id": 0})
    made = await lines.raise_line(db, T, rollout, 1, "reboot",
                                  [(await host_doc(db, agent), "reboot_host", {"delay_seconds": 300, "reason": "x"})], at)
    assert made["raised"] == 1


async def test_a_denied_install_line_halts_the_rollout_at_that_ring_and_closes_every_other_open_row(mongo_db):
    db = mongo_db
    rollout_id, later = await ring_one_world(db)
    await add_reboot_card(db, rollout_id, "b1", later)
    result = await lines.deny_line(db, T, rollout_id, 1, "install", approver=APPROVER)
    assert result["status"] == "denied"
    await controller.tick(db, now=later + timedelta(minutes=1))

    rollout = await db.patch_rollouts.find_one({"id": rollout_id})
    assert rollout["status"] == "halted" and rollout["rings"][1]["state"] == "halted"
    reason = rollout["haltReason"]
    assert (reason["code"], reason["ring"]) == ("install_denied", 1) and reason["text"] == "the install was denied."
    installs_ = await rows(db, **{"reason.inputs.ring": 1, "reason.inputs.line": "install"})
    assert [(r["state"], r.get("reasonCode")) for r in installs_] == [("denied", "playbook_raised")] * 2
    reboot = (await rows(db, command="reboot_host"))[0]
    assert (reboot["state"], reboot["reasonCode"]) == ("expired", "rollout_closed")
    assert "closed before this step ran" in reboot["reasonText"]
    assert await db.patch_rollout_hosts.count_documents({"rolloutId": rollout_id, "active": True}) == 3   # claims stay for the revert

    await controller.tick(db, now=later + timedelta(minutes=2))                  # a halted rollout stays as it is
    assert (await db.patch_rollouts.find_one({"id": rollout_id}))["haltReason"]["at"] == rollout["haltReason"]["at"]


async def test_an_install_line_nobody_answers_in_24_hours_halts_with_approval_expired(mongo_db):
    db = mongo_db
    rollout_id, later = await ring_one_world(db)
    after = later + timedelta(hours=25)
    assert await approvals.expire_due(db, now=after, tenant_id=T) == 2
    await online_at(db, after)
    await controller.tick(db, now=after)
    rollout = await db.patch_rollouts.find_one({"id": rollout_id})
    assert rollout["status"] == "halted" and rollout["haltReason"]["code"] == "approval_expired"
    assert rollout["haltReason"]["text"] == "the approval expired."
    # Expired by the clock, not closed by the rollout: its reason code stays the one it was raised with.
    assert {(r["state"], r.get("reasonCode")) for r in await rows(db, **{"reason.inputs.ring": 1})} == {("expired", "playbook_raised")}


async def test_a_denied_restart_line_halts_with_restart_denied(mongo_db):
    db = mongo_db
    rollout_id, later = await ring_one_world(db, ("b1",))
    await add_reboot_card(db, rollout_id, "b1", later)
    await lines.deny_line(db, T, rollout_id, 1, "reboot", approver=APPROVER)
    await controller.tick(db, now=later + timedelta(minutes=1))
    rollout = await db.patch_rollouts.find_one({"id": rollout_id})
    assert rollout["status"] == "halted" and rollout["haltReason"]["code"] == "restart_denied"
    install = (await rows(db, **{"reason.inputs.line": "install", "reason.inputs.ring": 1}))[0]
    assert (install["state"], install["reasonCode"]) == ("expired", "rollout_closed")


async def test_a_halt_ends_a_row_whose_instruction_nobody_fetched_and_delivery_refuses_it(mongo_db):
    db = mongo_db
    rollout_id, later = await ring_one_world(db)
    approved = await lines.approve_line(db, T, rollout_id, 1, "install", approver=APPROVER, now=later)
    assert approved["status"] == "approved" and approved["approved"] == 2
    sent = [i async for i in db.agent_instructions.find({"tenantId": T, "agent_id": {"$in": ["b1", "b2"]}})]
    assert len(sent) == 2 and {i["status"] for i in sent} == {"pending"}
    # b2's agent fetched its instruction before the halt; b1's did not.
    await db.agent_instructions.update_one({"agent_id": "b2"}, {"$set": {"status": "sent"}})
    await add_reboot_card(db, rollout_id, "b1", later)
    await lines.deny_line(db, T, rollout_id, 1, "reboot", approver=APPROVER)
    await controller.tick(db, now=later + timedelta(minutes=1))

    assert (await db.patch_rollouts.find_one({"id": rollout_id}))["status"] == "halted"
    by_agent = {r["targets"][0]: r for r in await rows(db, command="install_patches", **{"reason.inputs.ring": 1})}
    assert (by_agent["b1"]["state"], by_agent["b1"]["reasonCode"]) == ("failed", "rollout_halted")
    assert by_agent["b2"]["state"] == "dispatching"                              # already sent: its row stays open
    assert (await host_doc(db, "b1"))["state"] == "not_reached"

    pending = [i async for i in db.agent_instructions.find({"agent_id": "b1"})]
    assert await delivery.hold_back_autonomous(db, T, pending) == []             # the poll refuses it
    assert (await db.agent_instructions.find_one({"agent_id": "b1"}))["status"] == "refused"

    job = await db.patch_deployment_jobs.find_one({"rolloutId": rollout_id, "dispatchedAgents": "b2"})
    await post_result(db, job["id"], "b2", success_result(["openssl"]))
    await controller.tick(db, now=later + timedelta(minutes=2))                  # the late result is still recorded
    # 84-13: the halted ring is put back where the computer can; this agent has no revert-by-job token, so it
    # reads Not reverted (never Reverted) and its install row stays executed.
    late = await host_doc(db, "b2")
    assert (late["state"], late["notRevertedReason"], late["installedIds"]) == ("not_reverted", "agent_unsupported", ["openssl"])
    assert (await rows(db, command="install_patches", **{"reason.inputs.ring": 1, "targets": "b2"}))[0]["state"] == "executed"


async def test_nothing_of_a_halted_rollout_can_be_approved_any_more(mongo_db):
    db = mongo_db
    rollout_id, later = await ring_one_world(db, ("b1",))
    await add_reboot_card(db, rollout_id, "b1", later)
    await lines.deny_line(db, T, rollout_id, 1, "reboot", approver=APPROVER)
    await controller.tick(db, now=later + timedelta(minutes=1))
    before = len(await instructions(db))
    refused = await lines.approve_line(db, T, rollout_id, 1, "install", approver=APPROVER, now=later)
    assert refused["status"] == "refused" and refused["message"] == "This rollout is not running, so nothing was decided."
    for row in await rows(db, **{"reason.inputs.ring": 1}):
        assert (await approvals.approve(db, T, row["id"], approver=APPROVER, now=later))["status"] == "already_handled"
    assert len(await instructions(db)) == before


async def test_a_halt_is_taken_once_when_two_passes_meet(mongo_db):
    from autonomous_ops.rollout import lifecycle
    db = mongo_db
    rollout_id, later = await ring_one_world(db, ("b1",))
    first = await db.patch_rollouts.find_one({"id": rollout_id}, {"_id": 0})
    second = dict(first)
    assert await lifecycle.halt(db, T, first, 1, code="install_denied", now=later) is True
    assert await lifecycle.halt(db, T, second, 1, code="approval_expired", now=later) is False
    assert (await db.patch_rollouts.find_one({"id": rollout_id}))["haltReason"]["code"] == "install_denied"
