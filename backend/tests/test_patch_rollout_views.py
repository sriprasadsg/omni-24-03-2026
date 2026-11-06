"""Staged patch rollouts, plan 84-09 task 1: the card and page payloads the Rollouts tab reads.

Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py; time is frozen by
passing ``now``. Rollouts and their computers are written straight into the collections the controller owns, so
each state is built exactly, never reached through a long run of ticks.

Value: protects=PTCH-01 / PTCH-04 / PTCH-05: the server writes what every ring and computer is doing in the words
the UI-SPEC fixed, orders the list so what needs a person comes first, never claims a revert the computers did not
report, and decides every control (the browser infers nothing); fails_when=a state reads wrongly, a halt block
claims more reverts than were recorded, a finished rollout stays listed for over 30 days, or a view-only person is
offered a control; no_claim=the HTTP routes (tests/test_patch_rollout_endpoints.py) and the screens (84-12/14).
"""
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rbac_utils
from auth_types import TokenData
from autonomous_ops import PLATFORM_TENANT_ID, protected, settings
from autonomous_ops.rollout import messages, views
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.rollout_support import seed_group, seed_rings, seed_rollout_tenant, seed_window

T = "t1"
NOW = datetime(2026, 11, 6, 12, 0, 0, tzinfo=timezone.utc)
TYPES_TS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                        "services", "patchRollouts", "types.ts")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()


def keys_of(interface):
    """The field names of one interface in services/patchRollouts/types.ts."""
    with open(TYPES_TS, encoding="utf-8") as handle:
        body = re.search(r"export interface %s \{(.*?)\n\}" % interface, handle.read(), re.S).group(1)
    return set(re.findall(r"^\s{4}(\w+)\??:", body, re.M))


def ring(index, name, state, **extra):
    base = {"index": index, "key": name.lower(), "name": name, "groupIds": [f"G{index}"], "soakHours": 24,
            "failPct": 10, "minSample": 10, "isCanary": index == 0, "state": state}
    base.update(extra)
    return base


def host(agent, ring_index, state, **extra):
    base = {"agentId": agent, "ring": ring_index, "state": state, "os": "linux", "hostname": f"host-{agent}",
            "patchIds": ["openssl"], "active": True, "waitReason": None}
    base.update(extra)
    return base


async def seed(db, rollout_id="r1", *, status="running", rings=None, hosts=(), created=None, name="November",
               shadow=False, tenant=T, current=0, **extra):
    rings = rings if rings is not None else [ring(0, "Canary", "installing"), ring(1, "Pilot", "not_started"),
                                            ring(2, "Rest", "not_started")]
    doc = {"id": rollout_id, "tenantId": tenant, "name": name, "patchIds": ["openssl"], "status": status,
           "shadow": shadow, "currentRing": current, "rings": rings, "leftOut": [],
           "createdAt": created or NOW - timedelta(hours=2), "createdBy": {"id": "u1", "name": "Ann"}}
    doc.update(extra)
    await db.patch_rollouts.insert_one(doc)
    for h in hosts:
        await db.patch_rollout_hosts.insert_one({"tenantId": tenant, "rolloutId": rollout_id, **h})
    return doc


async def prepare(db):
    await seed_rollout_tenant(db, T)
    await seed_window(db, T, start="03:00", end="05:00")        # closed at 12:00
    for i in range(3):
        await seed_group(db, T, f"G{i}", [])


class Who:
    """A caller built the way the routes build one."""

    def __init__(self, can_manage=False, can_open=False, interactive=True, platform=False):
        self.can_manage_patches = can_manage
        self.can_open_decisions = can_open
        self.interactive = interactive
        self.platform_tenant = platform


MANAGER = Who(can_manage=True, can_open=True)
VIEWER = Who()


async def card(db, rollout_id="r1", caller=MANAGER, now=NOW):
    rollout = await db.patch_rollouts.find_one({"id": rollout_id}, {"_id": 0})
    return await views.rollout_card(db, T, rollout, caller, now)


# ---------------------------------------------------------------- the shape

async def test_a_card_carries_every_key_of_the_card_type_and_every_ring_key_of_the_ring_type(mongo_db):
    """protects=PTCH-01 (payload names match services/patchRollouts/types.ts); fails_when=a key of RolloutCard,
    RingView, HostRow or HaltBlock is missing from the payload."""
    await prepare(mongo_db)
    await seed(mongo_db, status="halted", rings=[ring(0, "Canary", "halted"), ring(1, "Pilot", "not_started")],
               hosts=[host("a1", 0, "failed", failureMessage="boom")],
               haltReason={"code": "canary_failed", "ring": 0, "text": "a computer failed its health check."})
    got = await card(mongo_db)
    assert keys_of("RolloutCard") <= set(got)
    assert keys_of("RingView") <= set(got["rings"][0])
    assert keys_of("HostRow") <= set(got["rings"][0]["hosts"][0])
    assert keys_of("HaltBlock") <= set(got["halt"])
    page = await views.rollout_page(mongo_db, T, MANAGER, 0, 10, NOW)
    assert keys_of("RolloutPage") <= set(page) and keys_of("RolloutFlags") <= set(page["flags"])
    assert keys_of("WindowStrip") <= set(page["window"])


async def test_the_header_facts_are_written_from_the_stored_rollout(mongo_db):
    await prepare(mongo_db)
    await seed(mongo_db, hosts=[host("a1", 0, "waiting"), host("a2", 1, "waiting")])
    got = await card(mongo_db)
    assert (got["id"], got["name"], got["status"], got["simulation"]) == ("r1", "November", "running", False)
    assert (got["patchCount"], got["computerCount"], got["startedBy"], got["currentRing"]) == (1, 2, "Ann", 0)
    assert got["startedAt"] == (NOW - timedelta(hours=2)).isoformat()


# ---------------------------------------------------------------- ring chips and detail lines (UI-SPEC section 4)

RING_CASES = [
    ("not_started", {}, [], "Starts after Canary passes."),
    ("waiting_for_window", {}, [host("a1", 1, "waiting")], "Opens Sat 7 Nov, 03:00 (UTC)."),
    ("installing", {}, [host("a1", 1, "installed"), host("a2", 1, "installing"), host("a3", 1, "waiting")],
     "1 of 3 installed."),
    ("restarting", {}, [host("a1", 1, "healthy", newBootAt=NOW), host("a2", 1, "restarting", rebootNeeded=True)],
     "1 of 2 back up."),
    ("soaking", {"soakEndsAt": NOW + timedelta(hours=5, minutes=10)}, [host("a1", 1, "healthy")],
     "Soak: 6 h left. Ends Fri 6 Nov, 17:10."),
    ("passed", {}, [host("a1", 1, "healthy"), host("a2", 1, "healthy")], "2 computers healthy."),
    ("passed", {}, [host("a1", 1, "healthy"), host("a2", 1, "not_reached")], "1 computer healthy. 1 not reached."),
    ("reverted", {}, [host("a1", 1, "reverted"), host("a2", 1, "reverted")], "Reverted on 2 computers."),
    ("reverted", {}, [host("a1", 1, "reverted"), host("a2", 1, "not_reverted", notRevertedReason="not_uninstallable")],
     "Reverted on 1 computer. 1 could not be reverted."),
]


@pytest.mark.parametrize("state,extra,hosts,detail", RING_CASES)
async def test_each_ring_state_reads_the_way_the_ui_spec_table_says(mongo_db, state, extra, hosts, detail):
    """protects=PTCH-01 / UI-SPEC section 4; fails_when=a chip state or its server-written detail line differs."""
    await prepare(mongo_db)
    await seed(mongo_db, current=1, rings=[ring(0, "Canary", "passed"), ring(1, "Pilot", state, **extra),
                                           ring(2, "Rest", "not_started")], hosts=hosts)
    got = (await card(mongo_db))["rings"][1]
    assert got["state"] == state and got["detail"] == detail


async def test_a_ring_waiting_for_approval_links_to_decisions_only_when_the_viewer_can_open_them(mongo_db):
    await prepare(mongo_db)
    await seed(mongo_db, rings=[ring(0, "Canary", "waiting_for_approval"), ring(1, "Pilot", "not_started")],
               hosts=[host("a1", 0, "waiting", waitReason="approval")])
    seen = (await card(mongo_db, caller=MANAGER))["rings"][0]
    assert seen["detail"] == messages.RING_DETAIL["waiting_for_approval"]
    assert seen["decisionsLink"] is True and seen["waitingText"] is None
    blind = (await card(mongo_db, caller=VIEWER))["rings"][0]
    assert blind["decisionsLink"] is False
    assert blind["waitingText"] == "Waiting for someone with access to Autonomous Ops."


async def test_the_card_status_derives_the_two_waiting_states_from_the_current_ring(mongo_db):
    await prepare(mongo_db)
    await seed(mongo_db, "ra", rings=[ring(0, "Canary", "waiting_for_approval"), ring(1, "P", "not_started")])
    await seed(mongo_db, "rw", rings=[ring(0, "Canary", "waiting_for_window"), ring(1, "P", "not_started")])
    await seed(mongo_db, "rr", rings=[ring(0, "Canary", "soaking"), ring(1, "P", "not_started")])
    assert [(await card(mongo_db, r))["status"] for r in ("ra", "rw", "rr")] == \
        ["waiting_for_approval", "waiting_for_window", "running"]


async def test_a_simulation_reads_in_the_conditional(mongo_db):
    """protects=shadow mode (UI-SPEC section 4); fails_when=a simulated ring says it installed something."""
    await prepare(mongo_db)
    await seed(mongo_db, shadow=True, rings=[ring(0, "Canary", "installing"), ring(1, "P", "not_started")],
               hosts=[host("a1", 0, "would_install"), host("a2", 0, "would_install")])
    got = await card(mongo_db)
    assert got["simulation"] is True
    assert got["rings"][0]["detail"] == "Would install on 2 computers."
    assert got["rings"][0]["hosts"][0]["result"] == "Would install openssl. Nothing was carried out."


async def test_the_failure_rate_soak_and_health_lines_come_from_the_ring_and_its_stored_checks(mongo_db):
    await prepare(mongo_db)
    health = [{"signal": "install", "state": "passed", "k": 11, "n": 12, "notChecked": 0},
              {"signal": "inventory", "state": "waiting", "k": 0, "n": 12, "notChecked": 0},
              {"signal": "heartbeat", "state": "no_data", "k": 0, "n": 12, "notChecked": 0},
              {"signal": "services", "state": "agent_only", "k": 12, "n": 12, "notChecked": 0}]
    await seed(mongo_db, current=1, rings=[ring(0, "Canary", "passed"),
                                           ring(1, "Pilot", "soaking", health=health,
                                                healthCounts={"reported": 12, "failed": 2})])
    got = (await card(mongo_db))["rings"][1]
    assert got["failureRateText"] == ("2 of 12 computers failed (17%). The ring halts above 10% once 10 computers "
                                      "have reported. Below 10 computers, any failure halts.")
    assert got["soakText"] == "Soaks 24 hours after the last install or restart."
    by_signal = {row["signal"]: row for row in got["health"]}
    assert by_signal["install"] == {"signal": "install", "state": "passed",
                                    "text": "11 of 12 computers installed without an error."}
    assert by_signal["inventory"]["text"] == "Waiting for the inventory after the install."
    assert by_signal["heartbeat"]["text"] == "No data for the heartbeat after the restart counts as a failure, so the ring halts."
    assert by_signal["services"]["text"] == "Only the agent service is checked."


async def test_the_canary_failure_line_and_the_small_sample_line(mongo_db):
    await prepare(mongo_db)
    await seed(mongo_db, current=1, rings=[ring(0, "Canary", "passed"),
                                           ring(1, "Pilot", "installing", healthCounts={"reported": 4, "failed": 1})])
    rings_ = (await card(mongo_db))["rings"]
    assert rings_[0]["failureRateText"] == "Any failure halts the rollout."
    assert rings_[1]["failureRateText"] == ("1 of 4 computers failed. Fewer than 10 computers have reported, so "
                                            "any failure halts.")


# ---------------------------------------------------------------- computers

async def test_computer_rows_put_problems_first_then_waiting_then_the_rest_by_name(mongo_db):
    """protects=UI-SPEC section 4 ordering; fails_when=a healthy computer sits above a failed one."""
    await prepare(mongo_db)
    await seed(mongo_db, rings=[ring(0, "Canary", "installing"), ring(1, "P", "not_started")], hosts=[
        host("h", 0, "healthy", hostname="alpha"), host("w", 0, "waiting", hostname="beta"),
        host("f", 0, "failed", hostname="zulu", failureMessage="disk full"),
        host("n", 0, "not_reverted", hostname="yankee", notRevertedReason="version_not_offered"),
        host("i", 0, "installed", hostname="Charlie")])
    rows = (await card(mongo_db))["rings"][0]["hosts"]
    assert [r["hostname"] for r in rows] == ["yankee", "zulu", "beta", "alpha", "Charlie"]
    assert (await card(mongo_db))["rings"][0]["hostTotal"] == 5


async def test_each_computer_state_has_its_result_sentence(mongo_db):
    await prepare(mongo_db)
    when = NOW - timedelta(minutes=30)
    hosts = [
        host("1", 0, "waiting", waitReason="approval", hostname="c01"),
        host("2", 0, "waiting", hostname="c02"),
        host("3", 0, "installing", hostname="c03", patchIds=["a", "b"]),
        host("4", 0, "installed", hostname="c04", installedIds=["a", "b"], installReportedAt=when),
        host("5", 0, "restarting", hostname="c05"),
        host("6", 0, "healthy", hostname="c06", newBootAt=when),
        host("7", 0, "failed", hostname="c07", failureMessage="disk full", patchIds=["openssl"]),
        host("8", 0, "failed", hostname="c08", failureCode="no_new_boot", failureMessage="x"),
        host("9", 0, "reverted", hostname="c09", installedIds=["openssl"], revertedAt=when),
        host("10", 0, "not_reverted", hostname="c10", notRevertedReason="not_uninstallable"),
        host("11", 0, "not_reverted", hostname="c11", notRevertedReason="agent_unsupported"),
        host("12", 0, "not_reached", hostname="c12"),
        host("13", 0, "reverting", hostname="c13", installedIds=["openssl"])]
    await seed(mongo_db, rings=[ring(0, "Canary", "installing"), ring(1, "P", "not_started")], hosts=hosts)
    result = {r["hostname"]: r["result"] for r in (await card(mongo_db))["rings"][0]["hosts"]}
    assert result["c01"] == "Waiting for approval."
    assert result["c02"] == "Waiting for the next window."
    assert result["c03"] == "Installing 2 patches."
    assert result["c04"] == "Installed 2 patches. Verified: no longer pending."
    assert result["c05"] == "Restarting. Waiting for a heartbeat from the new start."
    assert result["c06"] == "Passed every check at 11:30."
    assert result["c07"] == "openssl failed to install: disk full."
    assert result["c08"] == "No heartbeat from this computer within 30 minutes of the restart, so the ring halts."
    assert result["c09"] == "Reverted 1 patch at 11:30."
    assert result["c10"] == ("Not reverted: Windows doesn't allow this update to be uninstalled. "
                             "The patch is still installed.")
    assert result["c11"] == "Not reverted: this computer's agent doesn't support it yet. The patch is still installed."
    assert result["c12"].startswith("Offline for the whole ring")
    assert result["c13"] == "Reverting 1 patch."


async def test_a_not_reverted_computer_with_an_unknown_reason_still_never_claims_a_revert(mongo_db):
    """protects=PROH-84-02; fails_when=an unknown reason code raises or reads as reverted."""
    await prepare(mongo_db)
    await seed(mongo_db, hosts=[host("a1", 0, "not_reverted", notRevertedReason="dispatch_failed")])
    row = (await card(mongo_db))["rings"][0]["hosts"][0]
    assert row["state"] == "not_reverted"
    assert row["result"].startswith("Not reverted") and "still installed" in row["result"]


# ---------------------------------------------------------------- the halt block

async def test_the_halt_block_counts_only_the_reverts_the_computers_recorded(mongo_db):
    """protects=PTCH-04 / PROH-84-02; fails_when=the block says more computers were reverted than recorded."""
    await prepare(mongo_db)
    hosts = [host(f"r{i}", 0, "reverted", installedIds=["openssl"]) for i in range(3)]
    hosts += [host("x1", 0, "not_reverted", notRevertedReason="not_uninstallable"),
              host("ok", 0, "failed", failureMessage="no")]
    await seed(mongo_db, status="halted", rings=[ring(0, "Canary", "halted"), ring(1, "Pilot", "not_started")],
               hosts=hosts, haltReason={"code": "canary_failed", "ring": 0,
                                        "text": "a computer failed its health check."})
    halt = (await card(mongo_db))["halt"]
    assert halt["ringName"] == "Canary" and halt["reason"] == "a computer failed its health check."
    assert halt["reverts"] == [
        "Reverted on 3 computers.",
        "1 computer could not be reverted: Windows doesn't allow this update to be uninstalled. "
        "The patch is still installed on it."]


async def test_a_revert_still_running_says_so_and_blocks_resume(mongo_db):
    await prepare(mongo_db)
    await seed(mongo_db, status="halted", rings=[ring(0, "Canary", "halted"), ring(1, "Pilot", "not_started")],
               hosts=[host("a1", 0, "reverting", installedIds=["x"]), host("a2", 0, "reverted", installedIds=["x"])],
               haltReason={"code": "canary_failed", "ring": 0, "text": "t"})
    got = await card(mongo_db)
    assert got["halt"]["reverts"][0] == "Reverting 1 computer now."
    assert got["revertRunning"] is True
    assert got["canResume"] is False and got["resumeBlockedReason"] == "Wait for the revert to finish."
    assert got["canCancel"] is True


async def test_a_halted_rollout_without_a_revert_has_no_revert_lines_and_can_be_resumed(mongo_db):
    await prepare(mongo_db)
    await seed(mongo_db, status="halted", rings=[ring(0, "Canary", "passed"), ring(1, "Pilot", "halted")], current=1,
               hosts=[host("a1", 1, "failed", failureMessage="m")],
               haltReason={"code": "no_data:heartbeat", "ring": 1, "text": "no data for the heartbeat after the restart."})
    got = await card(mongo_db)
    assert got["halt"]["ringName"] == "Pilot" and got["halt"]["reverts"] == []
    assert got["canResume"] is True and got["resumeBlockedReason"] is None and got["revertRunning"] is False


async def test_only_a_halted_rollout_has_a_halt_block_or_resume_and_cancel(mongo_db):
    await prepare(mongo_db)
    await seed(mongo_db)
    got = await card(mongo_db)
    assert got["halt"] is None and got["canResume"] is False and got["canCancel"] is False


async def test_a_viewer_is_offered_neither_resume_nor_cancel(mongo_db):
    await prepare(mongo_db)
    await seed(mongo_db, status="halted", haltReason={"code": "canary_failed", "ring": 0, "text": "t"})
    got = await card(mongo_db, caller=VIEWER)
    assert got["canResume"] is False and got["canCancel"] is False and got["halt"] is not None


# ---------------------------------------------------------------- completed rollouts

async def test_a_completed_rollout_with_offline_computers_says_when_it_closes_and_a_closed_one_says_never_reached(mongo_db):
    await prepare(mongo_db)
    closes = NOW + timedelta(days=6)
    await seed(mongo_db, "done", status="completed", completedAt=NOW - timedelta(days=1), closesAt=closes,
               rings=[ring(0, "Canary", "passed"), ring(1, "P", "passed")],
               hosts=[host("a1", 1, "healthy"), host("a2", 1, "not_reached"), host("a3", 1, "not_reached")])
    got = await card(mongo_db, "done")
    assert got["status"] == "completed" and got["currentRing"] is None
    assert got["notReachedCount"] == 2 and got["closesAt"] == closes.isoformat()
    assert got["closedText"] == ("2 computers were offline for the whole ring. They get the patches in a later window "
                                 "if they come back online. This rollout closes Thu 12 Nov.")
    await seed(mongo_db, "shut", status="completed", completedAt=NOW - timedelta(days=9), neverReachedCount=1,
               rings=[ring(0, "Canary", "passed"), ring(1, "P", "passed")])
    shut = await card(mongo_db, "shut")
    assert shut["neverReachedCount"] == 1 and shut["closedText"] == "1 computer was never reached."


# ---------------------------------------------------------------- the page

async def test_the_page_orders_halted_then_approval_then_running_then_window_then_finished_newest_first(mongo_db):
    """protects=PTCH-01 ordering; fails_when=a finished rollout sits above one that needs a person."""
    await prepare(mongo_db)
    day = lambda n: NOW - timedelta(days=n)  # noqa: E731
    await seed(mongo_db, "done-new", status="completed", created=day(5), completedAt=day(1))
    await seed(mongo_db, "done-old", status="completed", created=day(20), completedAt=day(10))
    await seed(mongo_db, "cancelled", status="cancelled", created=day(8), cancelledAt=day(3))
    await seed(mongo_db, "window", created=day(1), rings=[ring(0, "C", "waiting_for_window"), ring(1, "P", "not_started")])
    await seed(mongo_db, "running", created=day(2), rings=[ring(0, "C", "soaking"), ring(1, "P", "not_started")])
    await seed(mongo_db, "approval", created=day(3),
               rings=[ring(0, "C", "waiting_for_approval"), ring(1, "P", "not_started")])
    await seed(mongo_db, "halted", status="halted", created=day(4), haltReason={"code": "x", "ring": 0, "text": "t"})
    page = await views.rollout_page(mongo_db, T, MANAGER, 0, 10, NOW)
    assert [c["id"] for c in page["items"]] == ["halted", "approval", "running", "window", "done-new", "cancelled",
                                                "done-old"]
    assert page["total"] == 7 and page["attentionCount"] == 2
    assert (page["offset"], page["limit"]) == (0, 10)


async def test_a_finished_rollout_older_than_thirty_days_is_not_listed_and_the_page_pages(mongo_db):
    await prepare(mongo_db)
    await seed(mongo_db, "ancient", status="completed", created=NOW - timedelta(days=60),
               completedAt=NOW - timedelta(days=31))
    await seed(mongo_db, "recent", status="completed", created=NOW - timedelta(days=60),
               completedAt=NOW - timedelta(days=29))
    for i in range(3):
        await seed(mongo_db, f"live{i}", created=NOW - timedelta(minutes=i))
    page = await views.rollout_page(mongo_db, T, MANAGER, 0, 2, NOW)
    assert page["total"] == 4 and len(page["items"]) == 2
    second = await views.rollout_page(mongo_db, T, MANAGER, 2, 2, NOW)
    assert len(second["items"]) == 2 and second["offset"] == 2
    ids = {c["id"] for c in page["items"] + second["items"]}
    assert "ancient" not in ids and "recent" in ids


async def test_another_organizations_rollouts_are_never_listed(mongo_db):
    await prepare(mongo_db)
    await seed(mongo_db, "mine")
    await seed(mongo_db, "theirs", tenant="t2")
    page = await views.rollout_page(mongo_db, T, MANAGER, 0, 10, NOW)
    assert [c["id"] for c in page["items"]] == ["mine"]


# ---------------------------------------------------------------- flags

def token(role):
    return TokenData(username=f"{role}@example.test", role=role, tenant_id=T)


async def flags_for(db, monkeypatch, role, tenant=T, **tenant_args):
    monkeypatch.setattr(rbac_utils, "get_database", lambda: db)
    tenant_settings = await settings.load(db, tenant)
    caller = await views.build_caller(token(role), tenant, tenant_settings)
    return (await views.rollout_page(db, tenant, caller, 0, 10, NOW))["flags"]


async def test_a_view_only_person_gets_every_flag_false(mongo_db, monkeypatch):
    """protects=T-84-32 (permissions are decided on the server); fails_when=a viewer is offered Start or rings."""
    await prepare(mongo_db)
    got = await flags_for(mongo_db, monkeypatch, "user")
    assert got["canStart"] is False and got["canManageRings"] is False and got["canOpenDecisions"] is False
    assert got["stopped"] is False and got["stopScope"] is None and got["platformTenant"] is False


async def test_a_manager_can_start_and_manage_rings_and_open_decisions(mongo_db, monkeypatch):
    await prepare(mongo_db)
    got = await flags_for(mongo_db, monkeypatch, "tenant_admin")
    assert got["canStart"] and got["canManageRings"] and got["canOpenDecisions"]


async def test_a_stop_turns_start_off_but_not_the_rings_and_names_its_scope(mongo_db, monkeypatch):
    await prepare(mongo_db)
    await mongo_db.autonomy_settings.update_one({"tenantId": T}, {"$set": {"stop": {"active": True}}})
    got = await flags_for(mongo_db, monkeypatch, "tenant_admin")
    assert got["canStart"] is False and got["canManageRings"] is True
    assert got["stopped"] is True and got["stopScope"] == "tenant"
    await mongo_db.autonomy_settings.update_one({"tenantId": T}, {"$set": {"stop": None}})
    await mongo_db.system_settings.insert_one({"type": "autonomous_ops", "stop": {"active": True, "scope": "platform"}})
    assert (await flags_for(mongo_db, monkeypatch, "tenant_admin"))["stopScope"] == "platform"


async def test_the_shadow_flag_follows_the_organization(mongo_db, monkeypatch):
    await prepare(mongo_db)
    assert (await flags_for(mongo_db, monkeypatch, "tenant_admin"))["shadow"] is False
    await mongo_db.autonomy_settings.update_one({"tenantId": T}, {"$set": {"shadow": True}})
    assert (await flags_for(mongo_db, monkeypatch, "tenant_admin"))["shadow"] is True


async def test_decisions_open_only_when_the_screen_is_enabled_for_the_organization(mongo_db, monkeypatch):
    await prepare(mongo_db)
    await mongo_db.tenants.update_one({"id": T}, {"$set": {"enabledFeatures": ["view:overview"]}})
    got = await flags_for(mongo_db, monkeypatch, "tenant_admin")
    assert got["canOpenDecisions"] is False


async def test_the_platform_organization_gets_an_empty_page_that_says_so(mongo_db, monkeypatch):
    await seed_rollout_tenant(mongo_db, PLATFORM_TENANT_ID)
    await seed(mongo_db, "p1", tenant=PLATFORM_TENANT_ID)
    monkeypatch.setattr(rbac_utils, "get_database", lambda: mongo_db)
    tenant_settings = await settings.load(mongo_db, PLATFORM_TENANT_ID)
    caller = await views.build_caller(token("tenant_admin"), PLATFORM_TENANT_ID, tenant_settings)
    page = await views.rollout_page(mongo_db, PLATFORM_TENANT_ID, caller, 0, 10, NOW)
    assert page["items"] == [] and page["total"] == 0
    assert page["flags"]["platformTenant"] is True and page["flags"]["canStart"] is False


# ---------------------------------------------------------------- the window strip and the rings summary

async def test_the_window_strip_says_open_closed_or_none_in_the_organizations_zone(mongo_db):
    await prepare(mongo_db)
    await mongo_db.maintenance_settings.update_one({"tenantId": T}, {"$set": {"timeZone": "Asia/Kolkata"}})
    closed = await views.window_strip(mongo_db, T, NOW)             # 17:30 in Kolkata, window 03:00-05:00 local
    assert closed["state"] == "closed" and closed["timeZone"] == "Asia/Kolkata"
    assert closed["text"] == "Next window opens Sat 7 Nov, 03:00 (Asia/Kolkata)."
    assert closed["nextOpensAt"] is not None and closed["closesAt"] is None
    opened = await views.window_strip(mongo_db, T, datetime(2026, 11, 6, 21, 40, tzinfo=timezone.utc))   # 03:10 local
    assert opened["state"] == "open" and opened["text"] == "Closes at 05:00 (Asia/Kolkata)."
    assert opened["closesAt"] is not None
    await mongo_db.maintenance_windows.delete_many({"tenantId": T})
    none = await views.window_strip(mongo_db, T, NOW)
    assert none["state"] == "none" and none["text"] == "Add a maintenance window first."
    assert none["closesAt"] is None and none["nextOpensAt"] is None


async def test_with_no_zone_set_the_strip_uses_utc_and_reports_no_zone(mongo_db):
    await seed_rollout_tenant(mongo_db, T)
    await mongo_db.maintenance_windows.insert_one({"id": "w", "tenantId": T, "name": "n", "recurrence": "daily",
                                                  "startTime": "03:00", "endTime": "05:00", "isActive": True})
    strip = await views.window_strip(mongo_db, T, NOW)
    assert strip["timeZone"] is None and strip["text"].endswith("(UTC).")


async def test_the_rings_summary_names_each_ring_its_groups_and_the_soak(mongo_db):
    await seed_rollout_tenant(mongo_db, T)
    assert await views.rings_summary(mongo_db, T) == (
        False, "No rings set up yet · Canary needs a group before a rollout can start")
    await seed_group(mongo_db, T, "G1", [])
    await seed_group(mongo_db, T, "G2", [])
    await mongo_db.agent_groups.update_one({"id": "G1"}, {"$set": {"name": "Canary"}})
    await mongo_db.agent_groups.update_one({"id": "G2"}, {"$set": {"name": "Servers"}})
    await seed_rings(mongo_db, T, [{"key": "canary", "name": "Canary", "groupIds": ["G1"], "soakHours": 24},
                                   {"key": "pilot", "name": "Pilot", "groupIds": ["G2"], "soakHours": 24},
                                   {"key": "rest", "name": "Rest", "groupIds": [], "soakHours": 24}])
    assert await views.rings_summary(mongo_db, T) == (
        True, "Canary (Canary) -> Pilot (Servers) -> Everyone else · 24-hour soak")


# ---------------------------------------------------------------- singular forms

async def test_one_of_a_thing_reads_in_the_singular(mongo_db):
    await prepare(mongo_db)
    await seed(mongo_db, current=1, rings=[ring(0, "Canary", "passed"), ring(1, "Pilot", "passed")],
               hosts=[host("a1", 1, "healthy"), host("a2", 1, "not_reached")],
               status="completed", completedAt=NOW, closesAt=NOW + timedelta(days=7))
    got = await card(mongo_db)
    assert got["patchCount"] == 1 and got["rings"][1]["detail"] == "1 computer healthy. 1 not reached."
    assert got["closedText"].startswith("1 computer was offline for the whole ring. It gets the patches")
    assert got["notReachedCount"] == 1
