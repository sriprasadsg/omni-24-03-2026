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
import itertools
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import protected
from autonomous_ops.rollout import controller, health, settle, signals, store
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


# ---------------------------------------------------------------- the ring verdict: every edge of PTCH-02 and PTCH-03

PAST = INSTALL - timedelta(hours=1)          # a soak that has ended at ``NOW_V``
NOW_V = INSTALL


def sig(agent_id, *, hostname=None, failed=False, state="installed", os="linux", **over):
    """One computer's plain signal dict, everything good unless said otherwise."""
    base_ = {"agentId": agent_id, "hostname": hostname or agent_id, "os": os, "state": state, "failed": failed,
             "reported": state not in ("waiting", "installing"), "install": not failed, "inventory": True,
             "heartbeat": True, "services": True}
    return {**base_, **over}


def ring_of(**over):
    return {"isCanary": False, "failPct": 10, "minSample": 10, "soakEndsAt": PAST, **over}


def ring_hosts(reported, failed):
    """``reported`` computers in all, ``failed`` of them failed."""
    return [sig(f"h{i:03d}", failed=i < failed) for i in range(reported)]


@pytest.mark.parametrize("reported,failed,outcome", [
    (9, 0, ("green", None)),
    (9, 1, ("halt", "host_failed")),          # below the minimum any failure halts
    (1, 1, ("halt", "host_failed")),
    (10, 0, ("green", None)),
    (10, 1, ("green", None)),                 # 10 % is not more than 10 %
    (10, 2, ("halt", "failure_share")),
    (11, 1, ("green", None)),
    (11, 2, ("halt", "failure_share")),       # 18.2 %
    (20, 2, ("green", None)),
    (20, 3, ("halt", "failure_share")),
])
def test_the_failure_share_is_judged_at_every_threshold_with_minimum_10_and_limit_10_percent(reported, failed, outcome):
    verdict = health.ring_verdict(ring_hosts(reported, failed), ring_of(), NOW_V)
    assert (verdict.kind, verdict.code) == outcome


@pytest.mark.parametrize("reported,failed,pct,halts", [
    (100, 29, 29, False),          # 0.29 * 100 is 28.999999999999996 as a float: 29 would wrongly be over it
    (100, 57, 57, False),
    (100, 30, 29, True),
    (3, 1, 33, True),              # 100 > 99
    (200, 20, 10, False),
    (200, 21, 10, True),
])
def test_the_share_is_compared_in_whole_numbers_so_no_rounding_decides_a_halt(reported, failed, pct, halts):
    ring = ring_of(failPct=pct, minSample=3)
    assert (health.ring_verdict(ring_hosts(reported, failed), ring, NOW_V).kind == "halt") is halts


def test_with_no_computer_reported_there_is_no_failure_share_and_the_ring_keeps_waiting():
    waiting_hosts = [sig("a", state="waiting", install=None, reported=False),
                     sig("b", state="installing", install=None, reported=False)]
    verdict = health.ring_verdict(waiting_hosts, ring_of(), NOW_V)
    assert (verdict.kind, verdict.code) == ("waiting", "no_reports")
    assert health.ring_verdict([], ring_of(), NOW_V).kind == "green"          # nothing at all to judge


def test_the_verdict_and_the_named_computer_do_not_depend_on_the_order_of_the_list():
    hosts = [sig("id3", hostname="Zed", failed=True), sig("id1", hostname="alpha", failed=True),
             sig("id2", hostname="Beta"), sig("id0", hostname="beta", inventory=None)]
    ring = ring_of(minSample=10)
    seen = {(v.kind, v.code, v.host) for v in (health.ring_verdict(list(p), ring, NOW_V)
                                                for p in itertools.permutations(hosts))}
    assert seen == {("halt", "host_failed", "id1")}                           # alpha before Beta before Zed (casefold)
    twin = [sig("b", hostname="same", failed=True), sig("a", hostname="same", failed=True)]
    assert health.ring_verdict(twin, ring_of(isCanary=True), NOW_V).host == "a"        # then the agent id


def test_a_canary_ring_halts_on_any_single_failure_even_in_the_middle_of_the_soak():
    ring = ring_of(isCanary=True, soakEndsAt=NOW_V + timedelta(hours=20))
    verdict = health.ring_verdict([sig("a"), sig("b", failed=True)] + ring_hosts(30, 0), ring, NOW_V)
    assert (verdict.kind, verdict.code, verdict.host) == ("halt", "canary_failed", "b")


def test_a_failure_above_the_limit_halts_at_once_without_waiting_for_the_soak():
    ring = ring_of(soakEndsAt=NOW_V + timedelta(hours=20))
    assert health.ring_verdict(ring_hosts(10, 2), ring, NOW_V).code == "failure_share"
    assert health.ring_verdict(ring_hosts(10, 1), ring, NOW_V).kind == "waiting"       # within the limit: just soak


@pytest.mark.parametrize("signal", ["install", "inventory", "heartbeat", "services"])
def test_a_signal_with_no_data_after_the_soak_halts_the_ring_and_names_the_computer(signal):
    hosts = [sig("ok"), sig("later", hostname="zz", **{signal: None}), sig("first", hostname="aa", **{signal: None})]
    verdict = health.ring_verdict(hosts, ring_of(), NOW_V)
    assert (verdict.kind, verdict.code, verdict.host) == ("halt", f"no_data:{signal}", "first")
    soaking = ring_of(soakEndsAt=NOW_V + timedelta(minutes=1))
    assert health.ring_verdict(hosts, soaking, NOW_V).kind == "waiting"                # no data waits out the soak


def test_services_that_are_not_checked_or_agent_only_are_neither_a_pass_nor_no_data():
    hosts = [sig("a", services="not_checked"), sig("b", services="agent_only"), sig("c")]
    assert health.ring_verdict(hosts, ring_of(), NOW_V).kind == "green"


def test_a_ring_with_a_soak_that_was_never_set_waits_rather_than_passes():
    assert health.ring_verdict([sig("a")], ring_of(soakEndsAt=None), NOW_V).kind == "waiting"


def test_computers_that_were_not_reached_count_in_neither_the_reported_nor_the_failed_numbers():
    hosts = ring_hosts(9, 1) + [sig(f"n{i}", state="not_reached", reported=False, install=None, inventory=None,
                                    heartbeat=None, services=None) for i in range(5)]
    verdict = health.ring_verdict(hosts, ring_of(), NOW_V)
    assert (verdict.kind, verdict.code) == ("halt", "host_failed")       # 9 reported is below the minimum of 10
    gone = [sig("x", state="left_out", reported=False, install=None, inventory=None, heartbeat=None, services=None)]
    assert health.ring_verdict(ring_hosts(10, 1) + gone, ring_of(), NOW_V).kind == "green"


def test_the_canary_needs_an_installed_computer_for_every_operating_system_of_the_rollout():
    both = [sig("w1", os="windows"), sig("l1", os="linux")]
    ring = ring_of(isCanary=True)
    assert health.ring_verdict(both, ring, NOW_V, ["linux", "windows"]).kind == "green"
    only_linux = [sig("l1", os="linux"), sig("w1", os="windows", state="not_reached", reported=False, install=None,
                                             inventory=None, heartbeat=None, services=None)]
    verdict = health.ring_verdict(only_linux, ring, NOW_V, ["linux", "windows"])
    assert (verdict.kind, verdict.code) == ("waiting", "canary_os")
    assert health.ring_verdict(only_linux, ring, NOW_V, ["linux"]).kind == "green"
    assert health.ring_verdict(only_linux, ring_of(), NOW_V, ["linux", "windows"]).kind == "green"   # a later ring


def test_skipped_and_deferred_results_are_never_counted_as_installed():
    skipped = settle.verdict_of({"results": [{"patch_id": "p", "status": "skipped"}]}, ["p"])
    assert skipped["ok"] is False and skipped["installed"] == []
    deferred = settle.verdict_of({"results": [{"patch_id": "p", "status": "deferred", "code": "not_reversible"}]}, ["p"])
    assert deferred["installed"] == [] and deferred["deferred"] == ["p"]
    mixed = settle.verdict_of({"results": [{"patch_id": "p", "status": "success"},
                                           {"patch_id": "q", "status": "skipped"}]}, ["p", "q"])
    assert mixed["ok"] is False and mixed["installed"] == ["p"]
    assert signals.read(an_agent(), a_host(state="waiting"), [], CAPS)["install"] is None


def test_the_health_rows_say_failed_no_data_waiting_not_checked_agent_only_or_passed():
    ring = ring_of()
    rows_ = {r["signal"]: r for r in health.health_rows(
        [sig("a", inventory=False, failed=True), sig("b", heartbeat=None, services="not_checked"), sig("c")], ring, NOW_V)}
    assert rows_["inventory"]["state"] == "failed" and rows_["inventory"]["k"] == 2 and rows_["inventory"]["n"] == 3
    assert rows_["heartbeat"]["state"] == "no_data"
    assert rows_["services"]["state"] == "not_checked" and rows_["services"]["notChecked"] == 1
    assert rows_["install"]["state"] == "failed" or rows_["install"]["state"] == "passed"
    early = {r["signal"]: r for r in health.health_rows([sig("b", heartbeat=None)], ring_of(soakEndsAt=NOW_V + timedelta(hours=1)), NOW_V)}
    assert early["heartbeat"]["state"] == "waiting"
    only_agent = {r["signal"]: r for r in health.health_rows([sig("a", services="agent_only")], ring, NOW_V)}
    assert only_agent["services"]["state"] == "agent_only" and only_agent["install"]["state"] == "passed"
