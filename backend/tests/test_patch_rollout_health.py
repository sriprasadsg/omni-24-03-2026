"""Staged patch rollouts, plan 84-08: the signals of the health gate and the computers that were never reached.

Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py for the controller
cases; the signal reader and the ring verdict are checked on plain dictionaries. Time is frozen by passing ``now``
to the real controller tick; the stand-in agent posts a 2.1.16-shaped install result through the real
``record_agent_patch_result`` path.

Value: protects=PTCH-02 / PTCH-03 / D-10 / D-18 / T-84-27 / T-84-28: every signal is read from data newer than the
change it judges (a scan more than 5 minutes after the install, a heartbeat after the restart, a service state
newer than the new boot), a missing signal is no data and never a pass, a computer that cannot report services
reads Not checked, and a computer that was offline for the whole install window is Not reached, left out of the
counts, and tried again when the canary still lacks an operating system; fails_when=an old scan, old heartbeat or
old service block counts, a stopped service passes, a missing signal passes, an agent-only host fakes a pass for
watched services, a not-reached computer is judged or the canary passes without every operating system;
no_claim=a real agent, a real restart, or the live database.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import protected
from autonomous_ops.rollout import controller, signals, store
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.rollout_support import fresh_scan, post_result, seed_rollout_agent, success_result
from tests.test_patch_rollout_lines import NOW, T, TOKENS, base, begin, host, host_doc, instructions, online_at
from tests.test_patch_rollout_tracer import installed_world, rollout_of

INSTALL = datetime(2026, 11, 10, 3, 0, tzinfo=timezone.utc)
BOOT_AT = INSTALL + timedelta(minutes=20)
CAPS = frozenset({"patch_installer", "remediation_executor"})
SERVICE_TOKENS = ("reboot_host", "service_state")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()


def minutes(n, base_=INSTALL):
    return base_ + timedelta(minutes=n)


def a_host(**over):
    return {"agentId": "a1", "hostname": "host-a1", "os": "linux", "state": "installed", "patchIds": ["openssl"],
            "installedIds": ["openssl"], "installReportedAt": INSTALL, **over}


def an_agent(*, seen=None, scan_at=None, pending=(), boot=None, tokens=(), block=None, failures=None):
    meta = {"response_actions": {"tokens": list(tokens)}}
    if scan_at is not None:
        meta["system_patching"] = {"timestamp": scan_at.isoformat(), "pending_updates": [{"id": p, "title": p} for p in pending]}
    if boot is not None:
        meta["response_state"] = {"boot_time": boot}
    if block is not None:
        meta["service_state"] = block
    if failures is not None:
        meta["service_failures"] = [{"name": n} for n in failures]
    return {"id": "a1", "lastSeen": (seen or minutes(1)).isoformat(), "meta": meta}


async def read(host, agent, watched=(), caps=CAPS):
    return await signals.host_signals(None, T, {"id": "r1"}, host, agent, watched, caps, minutes(120))


def state_block(at, **states):
    return {"v": 1, "at": int(at.timestamp()), "services": [{"name": n, "state": s} for n, s in states.items()]}


# ---------------------------------------------------------------- inventory

async def test_inventory_needs_a_scan_more_than_five_minutes_after_the_install():
    assert (await read(a_host(), an_agent(scan_at=minutes(4))))["inventory"] is None
    assert (await read(a_host(), an_agent(scan_at=minutes(5))))["inventory"] is None             # more than, not equal
    assert (await read(a_host(), an_agent(scan_at=minutes(6))))["inventory"] is True
    assert (await read(a_host(), an_agent()))["inventory"] is None                               # never scanned


async def test_a_fresh_scan_that_still_lists_the_patch_fails_the_computer():
    got = await read(a_host(), an_agent(scan_at=minutes(6), pending=["openssl"]))
    assert got["inventory"] is False and got["failed"] is True and got["reported"] is True
    other = await read(a_host(), an_agent(scan_at=minutes(6), pending=["curl"]))
    assert other["inventory"] is True and other["failed"] is False


# ---------------------------------------------------------------- heartbeat

async def test_without_a_restart_any_heartbeat_after_the_install_report_counts():
    assert (await read(a_host(), an_agent(seen=minutes(1))))["heartbeat"] is True
    assert (await read(a_host(), an_agent(seen=minutes(-1))))["heartbeat"] is None
    assert (await read(a_host(), an_agent(seen=INSTALL)))["heartbeat"] is None


def restarted_host(**over):
    due = minutes(5)
    return a_host(rebootNeeded=True, state="healthy", baselineBootTime=1_000, dispatchedRebootAt=minutes(0),
                  scheduledRestartAt=due, **over)


async def test_with_a_restart_only_a_heartbeat_from_the_new_boot_counts():
    host_ = restarted_host()
    new_boot = int(minutes(7).timestamp())
    assert (await read(host_, an_agent(seen=minutes(30), boot=new_boot)))["heartbeat"] is True
    assert (await read(host_, an_agent(seen=minutes(30), boot=1_000)))["heartbeat"] is None       # an old boot
    assert (await read(host_, an_agent(seen=minutes(3), boot=new_boot)))["heartbeat"] is None     # sent before it was due
    assert (await read(host_, an_agent(seen=minutes(30))))["heartbeat"] is None                   # a 2.1.14 agent
    recorded = restarted_host(newBootAt=minutes(7))
    assert (await read(recorded, an_agent(seen=minutes(30), boot=1_000)))["heartbeat"] is True    # proven when it was seen


async def test_a_failed_or_waiting_install_has_its_own_install_value():
    assert (await read(a_host(state="failed"), an_agent()))["install"] is False
    assert (await read(a_host(state="waiting"), an_agent()))["install"] is None
    assert (await read(a_host(state="restarting"), an_agent()))["install"] is True


# ---------------------------------------------------------------- services

async def test_an_empty_watched_list_checks_only_the_agent_and_that_is_not_no_data():
    got = await read(a_host(), an_agent(), watched=[])
    assert got["services"] == "agent_only" and got["failed"] is False


async def test_an_unreadable_watched_list_is_no_data_not_a_pass():
    assert (await read(a_host(), an_agent(), watched=None))["services"] is None


async def test_a_host_that_reports_service_state_must_show_every_watched_service_running_after_the_new_boot():
    host_ = restarted_host(newBootAt=BOOT_AT)
    fresh = BOOT_AT + timedelta(seconds=130)
    watched = ["sshd", "nginx"]
    ok = await read(host_, an_agent(tokens=SERVICE_TOKENS, block=state_block(fresh, sshd="running", NGINX="running")),
                    watched)
    assert ok["services"] is True and ok["failed"] is False
    stopped = await read(host_, an_agent(tokens=SERVICE_TOKENS, block=state_block(fresh, sshd="running", nginx="stopped")),
                         watched)
    assert stopped["services"] is False and stopped["failed"] is True
    broken = await read(host_, an_agent(tokens=SERVICE_TOKENS, block=state_block(fresh, sshd="failed", nginx="running")),
                        watched)
    assert broken["services"] is False


async def test_a_stale_missing_or_unclear_service_block_is_no_data():
    host_ = restarted_host(newBootAt=BOOT_AT)
    watched = ["sshd", "nginx"]
    early = BOOT_AT + timedelta(seconds=120)                                              # not newer than boot + 120 s
    assert (await read(host_, an_agent(tokens=SERVICE_TOKENS, block=state_block(early, sshd="running", nginx="running")),
                       watched))["services"] is None
    assert (await read(host_, an_agent(tokens=SERVICE_TOKENS), watched))["services"] is None
    fresh = BOOT_AT + timedelta(seconds=130)
    assert (await read(host_, an_agent(tokens=SERVICE_TOKENS, block=state_block(fresh, sshd="running")),
                       watched))["services"] is None                                      # nginx is missing from the block
    assert (await read(host_, an_agent(tokens=SERVICE_TOKENS, block=state_block(fresh, sshd="running", nginx="unknown")),
                       watched))["services"] is None
    old_stop = await read(host_, an_agent(tokens=SERVICE_TOKENS, block=state_block(early, sshd="stopped", nginx="running")),
                          watched)
    assert old_stop["services"] is None                                                   # a stop before the boot proves nothing


async def test_without_a_restart_the_service_block_must_be_newer_than_the_install_report():
    fresh = INSTALL + timedelta(seconds=130)
    got = await read(a_host(), an_agent(tokens=SERVICE_TOKENS, block=state_block(fresh, sshd="running")), ["sshd"])
    assert got["services"] is True
    stale = await read(a_host(), an_agent(tokens=SERVICE_TOKENS, block=state_block(INSTALL + timedelta(seconds=60), sshd="running")),
                       ["sshd"])
    assert stale["services"] is None


async def test_a_host_without_the_service_state_token_is_not_checked_unless_it_reports_a_watched_failure():
    watched = ["sshd"]
    assert (await read(a_host(), an_agent(failures=[]), watched))["services"] == "not_checked"
    assert (await read(a_host(), an_agent(), watched))["services"] == "not_checked"
    named = await read(a_host(), an_agent(failures=["SSHD"]), watched)
    assert named["services"] is False and named["failed"] is True
    assert (await read(a_host(), an_agent(failures=["cron"]), watched))["services"] == "not_checked"
    unticked = await read(a_host(), an_agent(failures=["sshd"]), watched, caps=frozenset({"patch_installer"}))
    assert unticked["services"] == "not_checked"


# ---------------------------------------------------------------- the ring's health rows

async def test_the_ring_keeps_its_health_rows_for_the_views(mongo_db):
    db = mongo_db
    rollout_id, installed = await installed_world(db)
    await controller.tick(db, now=installed + timedelta(minutes=30))
    rows_ = (await rollout_of(db, rollout_id))["rings"][0]["health"]
    assert [r["signal"] for r in rows_] == ["install", "inventory", "heartbeat", "services"]
    by_signal = {r["signal"]: r for r in rows_}
    assert (by_signal["install"]["state"], by_signal["install"]["k"], by_signal["install"]["n"]) == ("passed", 1, 1)
    assert by_signal["inventory"]["state"] == "waiting" and by_signal["inventory"]["k"] == 0
    assert by_signal["services"]["state"] == "agent_only"


# ---------------------------------------------------------------- computers that were never reached

async def two_hosts(db, other_platform="Linux", other_patch="openssl"):
    """A canary ring of a1 (online) and a second computer that never comes online during the day's window."""
    await base(db)
    await host(db, "a1", canary=True)
    offline_at = NOW - timedelta(hours=2)
    await seed_rollout_agent(db, T, "b1", hostname="host-b1", platform=other_platform, tokens=TOKENS,
                             pending=[other_patch], boot_time=1_700_000_000, last_seen=offline_at)
    await db.agent_group_members.replace_one({"group_id": "G1", "agent_id": "b1"},
                                             {"group_id": "G1", "agent_id": "b1", "tenantId": T}, upsert=True)
    return await begin(db, ("openssl", other_patch) if other_patch != "openssl" else ("openssl",))


async def install_a1(db, rollout_id):
    await controller.tick(db, now=NOW)
    job = await db.patch_deployment_jobs.find_one({"rolloutId": rollout_id, "dispatchedAgents": "a1"})
    await post_result(db, job["id"], "a1", success_result(["openssl"]))
    await controller.tick(db, now=NOW + timedelta(minutes=2))
    return store.aware((await host_doc(db, "a1"))["installReportedAt"])


async def test_a_computer_offline_for_the_whole_window_is_not_reached_and_the_canary_is_judged_without_it(mongo_db):
    db = mongo_db
    rollout_id = await two_hosts(db)
    installed = await install_a1(db, rollout_id)
    assert (await host_doc(db, "b1"))["state"] == "waiting"                  # the window is still open: it may yet come
    closing = NOW + timedelta(hours=3, minutes=1)
    await fresh_scan(db, "a1", [], installed + timedelta(minutes=10))
    await db.agents.update_one({"id": "a1"}, {"$set": {"lastSeen": closing.isoformat()}})
    await db.agents.update_one({"id": "b1"}, {"$set": {"lastSeen": closing.isoformat()}})   # back, but the window is over
    await controller.tick(db, now=closing)
    b1 = await host_doc(db, "b1")
    assert b1["state"] == "not_reached"
    ring = (await rollout_of(db, rollout_id))["rings"][0]
    assert ring["state"] == "passed"                                          # judged on the computer that installed
    assert [i for i in await instructions(db) if i["agent_id"] == "b1"] == []


async def test_a_computer_that_was_online_during_the_window_is_not_marked_not_reached(mongo_db):
    db = mongo_db
    rollout_id = await two_hosts(db)
    await controller.tick(db, now=NOW)
    await db.agents.update_one({"id": "b1"}, {"$set": {"lastSeen": (NOW + timedelta(hours=1)).isoformat()}})
    await online_at(db, NOW + timedelta(hours=1, minutes=1))
    await controller.tick(db, now=NOW + timedelta(hours=1, minutes=1))
    closing = NOW + timedelta(hours=3, minutes=1)
    await controller.tick(db, now=closing)
    assert (await host_doc(db, "b1"))["state"] != "not_reached"


async def test_the_canary_waits_for_the_next_window_when_an_operating_system_was_never_reached(mongo_db):
    db = mongo_db
    await base(db)
    await host(db, "a1", canary=True)
    await seed_rollout_agent(db, T, "w1", hostname="host-w1", platform="Windows", tokens=TOKENS, pending=["KB5000001"],
                             boot_time=1_700_000_000, last_seen=NOW - timedelta(hours=2))
    await db.agent_group_members.replace_one({"group_id": "G1", "agent_id": "w1"},
                                             {"group_id": "G1", "agent_id": "w1", "tenantId": T}, upsert=True)
    rollout_id = await begin(db, ("openssl", "KB5000001"))
    installed = await install_a1(db, rollout_id)
    closing = NOW + timedelta(hours=3, minutes=1)
    await fresh_scan(db, "a1", [], installed + timedelta(minutes=10))
    await db.agents.update_one({"id": "a1"}, {"$set": {"lastSeen": closing.isoformat()}})
    await controller.tick(db, now=closing)
    assert (await host_doc(db, "w1"))["state"] == "not_reached"
    rollout = await rollout_of(db, rollout_id)
    assert rollout["status"] == "running" and rollout["currentRing"] == 0 and rollout["rings"][0]["state"] != "passed"

    next_day = NOW + timedelta(hours=24)                                      # the next window is open and w1 is back
    await db.agents.update_many({"id": {"$in": ["a1", "w1"]}}, {"$set": {"lastSeen": next_day.isoformat()}})
    await controller.tick(db, now=next_day)
    assert [i["type"] for i in await instructions(db) if i["agent_id"] == "w1"] == ["install_patches"]
    assert (await host_doc(db, "w1"))["state"] == "installing"
