"""Staged patch rollouts, plan 84-08: restarts, the boot baseline and the new-boot check on a real database.

Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py. Time is frozen by
passing ``now`` to the real controller tick and to ``approve_line``; the dispatcher's own clock (the approvals
path hands it none) is frozen with a fixture. The stand-in agent posts a 2.1.16-shaped install result through
the real ``record_agent_patch_result`` path and comes back from a restart by changing its heartbeat fields.

Value: protects=PTCH-02 / D-07 / D-08 / D-17 / T-84-26: only a computer whose result says a restart is needed
gets a Reboot row, an approved restart is sent inside the window with a 5 minute warning and a stored boot
baseline, a heartbeat from before the restart never counts as the new boot, and a computer with no new boot
30 minutes after the restart was due halts the ring and is named; fails_when=a computer that needs no restart
is listed, the baseline is not stored, an old boot_time or a heartbeat sent before the restart is accepted as
the new boot, the 30 minute clock starts at dispatch, an undelivered restart is mistaken for a computer that
never came back, or a halt does not name the computer; no_claim=a real agent, a real restart, or the live
database.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import protected
from autonomous_ops.rollout import controller, dispatcher, lines, reboots
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.rollout_support import post_result, success_result
from tests.test_patch_rollout_lines import APPROVER, NOW, T, aware, base, begin, host, host_doc, instructions, \
    online_at, rows

PARAMS = {"delay_seconds": 300, "reason": "Restarting in 5 minutes for updates"}
BOOT = 1_700_000_000
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()


@pytest.fixture
def clock(monkeypatch):
    """The dispatcher's own clock (``approvals.approve`` hands it none): set ``clock["now"]`` to freeze it."""
    state = {"now": None}
    real = dispatcher._now

    def fake(now=None):
        return real(state["now"] if now is None and state["now"] is not None else now)

    monkeypatch.setattr(dispatcher, "_now", fake)
    return state


def at(seconds):
    return EPOCH + timedelta(seconds=seconds)


def agent_of(boot, seen):
    return {"id": "a1", "lastSeen": seen.isoformat(), "meta": {"response_state": {"boot_time": boot}}}


def baseline_host():
    """A host whose restart was sent 500 s after it booted: restart due 300 s later."""
    dispatched = at(BOOT + 500)
    return {"agentId": "a1", "baselineBootTime": BOOT, "dispatchedRebootAt": dispatched,
            "scheduledRestartAt": dispatched + timedelta(seconds=300)}


# ---------------------------------------------------------------- the pure checks

def test_a_boot_time_that_did_not_move_or_moved_inside_the_tolerance_is_not_a_new_boot():
    due = baseline_host()["scheduledRestartAt"]
    assert reboots.is_new_boot(agent_of(BOOT, due + timedelta(minutes=5)), baseline_host()) is False
    assert reboots.is_new_boot(agent_of(BOOT + 60, due + timedelta(minutes=5)), baseline_host()) is False


def test_a_later_boot_seen_after_the_restart_was_due_is_the_new_boot():
    due = baseline_host()["scheduledRestartAt"]
    assert reboots.is_new_boot(agent_of(BOOT + 600, due + timedelta(minutes=1)), baseline_host()) is True


def test_a_heartbeat_sent_before_the_restart_was_due_is_never_the_new_boot():
    due = baseline_host()["scheduledRestartAt"]
    assert reboots.is_new_boot(agent_of(BOOT + 600, due - timedelta(seconds=10)), baseline_host()) is False
    assert reboots.is_new_boot(agent_of(BOOT + 600, due), baseline_host()) is False       # later than, not equal


def test_a_boot_time_from_before_the_restart_was_sent_is_not_the_new_boot():
    due = baseline_host()["scheduledRestartAt"]
    # moved by 300 s (more than the tolerance) but still 200 s before the restart was sent, minus the tolerance
    assert reboots.is_new_boot(agent_of(BOOT + 300, due + timedelta(minutes=5)), baseline_host()) is False


def test_an_agent_with_no_readable_boot_time_gives_no_answer():
    due = baseline_host()["scheduledRestartAt"]
    seen = due + timedelta(minutes=5)
    assert reboots.is_new_boot({"id": "a1", "lastSeen": seen.isoformat(), "meta": {}}, baseline_host()) is None
    assert reboots.is_new_boot(agent_of("1700000600", seen), baseline_host()) is None
    assert reboots.is_new_boot(agent_of(True, seen), baseline_host()) is None
    assert reboots.is_new_boot(agent_of(BOOT + 600, seen) | {"lastSeen": None}, baseline_host()) is None
    assert reboots.is_new_boot(None, baseline_host()) is None
    assert reboots.is_new_boot(agent_of(BOOT + 600, seen), {"agentId": "a1"}) is None      # no baseline stored


def test_the_thirty_minute_clock_starts_at_the_scheduled_restart_not_at_dispatch():
    host_doc_ = baseline_host()
    due = host_doc_["scheduledRestartAt"]
    assert reboots.overdue(host_doc_, due + timedelta(minutes=30)) is False
    assert reboots.overdue(host_doc_, due + timedelta(minutes=30, seconds=1)) is True
    assert reboots.overdue(host_doc_, host_doc_["dispatchedRebootAt"] + timedelta(minutes=31)) is False
    assert reboots.overdue({"agentId": "a1"}, due + timedelta(days=2)) is False             # nothing was sent


# ---------------------------------------------------------------- the Reboot line

async def installed_ring(db, *, restart=("a1",), agents=("a1", "b1")):
    """Two canary computers installed; the ones in ``restart`` report that a restart is needed. Returns
    (rollout id, the time of the tick that settled them)."""
    await base(db)
    for agent in agents:
        await host(db, agent, canary=True)
    rollout_id = await begin(db)
    await controller.tick(db, now=NOW)
    for agent in agents:
        job = await db.patch_deployment_jobs.find_one({"rolloutId": rollout_id, "dispatchedAgents": agent})
        await post_result(db, job["id"], agent, success_result(["openssl"], reboot=agent in restart))
    settled = NOW + timedelta(minutes=2)
    await online_at(db, settled)
    await controller.tick(db, now=settled)
    return rollout_id, settled


async def restart_instructions(db):
    return [i for i in await instructions(db) if i["type"] == "reboot_host"]


async def ring_zero(db, rollout_id):
    return (await db.patch_rollouts.find_one({"id": rollout_id}))["rings"][0]


async def test_only_the_computer_whose_result_says_a_restart_is_needed_gets_a_reboot_row(mongo_db):
    db = mongo_db
    rollout_id, _ = await installed_ring(db)
    found = await rows(db, command="reboot_host")
    assert len(found) == 1
    assert (found[0]["state"], found[0]["targets"], found[0]["params"]) == ("awaiting_approval", ["a1"], PARAMS)
    assert found[0]["reason"]["inputs"]["line"] == "reboot" and found[0]["reason"]["inputs"]["ring"] == 0
    assert await restart_instructions(db) == []                                       # nothing is sent before approval
    assert (await host_doc(db, "b1"))["state"] == "installed" and (await host_doc(db, "a1"))["state"] == "installed"
    ring = await ring_zero(db, rollout_id)
    assert ring["state"] == "waiting_for_approval" and ring.get("soakEndsAt") is None   # no soak until it is back up


async def test_a_second_tick_raises_no_second_reboot_row(mongo_db):
    db = mongo_db
    _, settled = await installed_ring(db)
    await online_at(db, settled + timedelta(minutes=1))
    await controller.tick(db, now=settled + timedelta(minutes=1))
    assert len(await rows(db, command="reboot_host")) == 1


async def test_no_computer_needing_a_restart_means_no_reboot_row_and_the_soak_starts(mongo_db):
    db = mongo_db
    rollout_id, settled = await installed_ring(db, restart=())
    assert await rows(db, command="reboot_host") == []
    ring = await ring_zero(db, rollout_id)
    assert ring["state"] == "soaking"
    last = max([aware((await host_doc(db, a))["installReportedAt"]) for a in ("a1", "b1")])
    assert aware(ring["soakEndsAt"]) == last + timedelta(hours=1)


# ---------------------------------------------------------------- approval, dispatch and the baseline

async def approved_restart(db, clock):
    rollout_id, settled = await installed_ring(db)
    sent_at = settled + timedelta(minutes=1)
    clock["now"] = sent_at
    await online_at(db, sent_at)
    result = await lines.approve_line(db, T, rollout_id, 0, "reboot", approver=APPROVER, now=sent_at)
    assert (result["status"], result["when"], result["approved"]) == ("approved", "now", 1), result
    return rollout_id, sent_at


async def test_an_approved_restart_is_sent_once_with_the_warning_and_stores_the_boot_baseline(mongo_db, clock):
    db = mongo_db
    _, sent_at = await approved_restart(db, clock)
    sent = await restart_instructions(db)
    assert len(sent) == 1 and sent[0]["agent_id"] == "a1" and sent[0]["payload"] == PARAMS
    assert sent[0]["autonomy"]["kind"] == "action"
    host_ = await host_doc(db, "a1")
    assert host_["state"] == "restarting"
    assert aware(host_["dispatchedRebootAt"]) == sent_at
    assert aware(host_["scheduledRestartAt"]) == sent_at + timedelta(seconds=300)
    assert host_["baselineBootTime"] == BOOT and aware(host_["baselineLastSeen"]) == sent_at
    assert (await host_doc(db, "b1"))["state"] == "installed"                          # the other computer is left alone
    await controller.tick(db, now=sent_at + timedelta(minutes=1))
    assert len(await restart_instructions(db)) == 1                                   # a tick never sends it twice


async def test_a_computer_back_on_a_new_boot_is_healthy_and_the_soak_starts_from_the_restart(mongo_db, clock):
    db = mongo_db
    rollout_id, _ = await approved_restart(db, clock)
    due = aware((await host_doc(db, "a1"))["scheduledRestartAt"])
    booted = due + timedelta(minutes=2)
    back = due + timedelta(minutes=10)
    await online_at(db, back)
    await db.agents.update_one({"id": "a1"}, {"$set": {"meta.response_state.boot_time": int(booted.timestamp())}})
    await controller.tick(db, now=back)
    host_ = await host_doc(db, "a1")
    assert host_["state"] == "healthy" and aware(host_["newBootAt"]) == booted
    ring = await ring_zero(db, rollout_id)
    assert ring["state"] == "soaking" and aware(ring["soakEndsAt"]) == booted + timedelta(hours=1)
    row = (await rows(db, command="reboot_host"))[0]
    assert (row["state"], row["reasonCode"]) == ("executed", "rollout_restarted")


async def test_a_heartbeat_from_before_the_restart_is_never_the_new_boot_and_the_ring_halts_after_thirty_minutes(
        mongo_db, clock):
    db = mongo_db
    rollout_id, _ = await approved_restart(db, clock)
    due = aware((await host_doc(db, "a1"))["scheduledRestartAt"])
    for minutes in (10, 29):                       # alive after the restart was due, but the boot_time never moved
        moment = due + timedelta(minutes=minutes)
        await online_at(db, moment)
        await controller.tick(db, now=moment)
        rollout = await db.patch_rollouts.find_one({"id": rollout_id})
        assert rollout["status"] == "running" and rollout["rings"][0]["state"] == "restarting", minutes
        assert (await host_doc(db, "a1"))["state"] == "restarting"
    late = due + timedelta(minutes=31)
    await online_at(db, late)
    await controller.tick(db, now=late)
    rollout = await db.patch_rollouts.find_one({"id": rollout_id})
    reason = rollout["haltReason"]
    assert rollout["status"] == "halted" and rollout["rings"][0]["state"] == "halted"
    assert (reason["code"], reason["ring"], reason["host"]) == ("no_new_boot", 0, "a1")
    assert "host-a1" in reason["text"] and "30 minutes" in reason["text"]
    host_ = await host_doc(db, "a1")
    assert host_["state"] == "failed" and host_["active"] is True
    row = (await rows(db, command="reboot_host"))[0]
    assert (row["state"], row["reasonCode"]) == ("failed", "rollout_no_new_boot")


async def test_a_restart_the_computer_never_received_is_asked_for_again_not_taken_for_a_missing_boot(mongo_db, clock):
    db = mongo_db
    rollout_id, sent_at = await approved_restart(db, clock)
    await db.agent_instructions.update_many({"type": "reboot_host"}, {"$set": {"status": "refused"}})
    await online_at(db, sent_at + timedelta(minutes=1))
    await controller.tick(db, now=sent_at + timedelta(minutes=1))
    found = await rows(db, command="reboot_host")
    assert sorted(r["state"] for r in found) == ["awaiting_approval", "failed"]
    assert [r["reasonCode"] for r in found if r["state"] == "failed"] == ["rollout_not_delivered"]
    assert (await host_doc(db, "a1"))["state"] == "installed"
    assert (await db.patch_rollouts.find_one({"id": rollout_id}))["status"] == "running"
