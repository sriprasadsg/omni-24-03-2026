"""Staged patch rollouts, plan 84-03: the window-deferred dispatcher and line approve and deny.

Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py. Time is frozen by
passing ``now`` to the real controller tick and to ``approve_line``; the dispatcher's own clock (the approvals
path hands it no time) is frozen with a fixture. Approvals go through the real ``approvals.approve`` / ``deny``.

Value: protects=PTCH-06 / PTCH-05 / D-07 / T-84-08 / T-84-09: one click approves one line (one compare-and-set per
row), approved work is sent inside the window and only once, a computer that cannot take it at dispatch time is
never sent anything, and no approval reaches another line; fails_when=an instruction is written with the window
closed or for a released, unticked, offline, busy or unsupported computer, a second click or a click that meets a
tick writes a second instruction, a deny sends anything, or the dispatcher is missing in a process that approves;
no_claim=a real agent, a real restart, or the live database.
"""
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import approvals, protected
from autonomous_ops.rollout import controller, dispatcher, lines, store
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.rollout_support import seed_window
from tests.test_patch_rollout_lines import (APPROVER, NOW, T, aware, base, begin, hhmm, host, host_doc, instructions,
                                            online_at, pass_the_canary, rows)

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINDOW_END = NOW + timedelta(hours=3)


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


async def ring_one(db, agents=("b1", "b2", "b3"), *, short_window=False):
    """A rollout whose canary passed and whose ring one holds ``agents``. With ``short_window`` the daily window
    closes 30 minutes after NOW, so ring one waits for the next day's window. Returns (rollout id, time)."""
    await base(db)
    if short_window:
        await db.maintenance_windows.delete_many({})
        await seed_window(db, T, start=hhmm(NOW - timedelta(hours=1)), end=hhmm(NOW + timedelta(minutes=30)))
    await host(db, "a1", canary=True)
    for agent in agents:
        await host(db, agent)
    rollout_id = await begin(db)
    return rollout_id, await pass_the_canary(db, rollout_id)


async def closed_window_world(db, clock, agents=("b1", "b2", "b3")):
    """Ring one's cards raised in the second day's window and approved after it closed: every row is approved
    and nothing is sent. Returns (rollout id, the time of the next open window, a time inside it)."""
    rollout_id, _ = await ring_one(db, agents, short_window=True)
    raised = NOW + timedelta(hours=23, minutes=10)
    await online_at(db, raised)
    await controller.tick(db, now=raised)
    assert len(await rows(db, **{"reason.inputs.ring": 1})) == len(agents)
    closed = NOW + timedelta(hours=25)
    clock["now"] = closed
    result = await lines.approve_line(db, T, rollout_id, 1, "install", approver=APPROVER, now=closed)
    assert result["status"] == "approved" and result["when"] == "window", result
    opens = NOW + timedelta(hours=47)
    assert datetime.fromisoformat(result["windowOpensAt"]) == opens
    return rollout_id, opens, opens + timedelta(minutes=5)


def ring_one_rows(db, **extra):
    return rows(db, **{"reason.inputs.ring": 1, **extra})


# ---------------------------------------------------------------- one click, window open

async def test_one_click_approves_the_whole_line_and_each_row_is_sent_once_inside_the_window(mongo_db, clock):
    db = mongo_db
    rollout_id, later = await ring_one(db)
    clock["now"] = later
    before = len(await instructions(db))

    result = await lines.approve_line(db, T, rollout_id, 1, "install", approver=APPROVER, now=later)
    assert (result["status"], result["when"], result["approved"], result["refused"]) == ("approved", "now", 3, [])
    assert result["windowOpensAt"] is None and result["message"].startswith("Approved. Installing now")

    found = await ring_one_rows(db)
    assert [r["state"] for r in found] == ["dispatching"] * 3
    assert all(r["approval"]["approver"] == APPROVER for r in found)
    sent = [i for i in await instructions(db) if i["type"] == "install_patches" and i["agent_id"] != "a1"]
    assert sorted(i["agent_id"] for i in sent) == ["b1", "b2", "b3"] and len(await instructions(db)) == before + 3
    for item in sent:
        assert aware(item["expiresAt"]) == WINDOW_END                    # the instruction dies with the window
        assert item["autonomy"]["kind"] == "action" and item["payload"]["patch_ids"] == ["openssl"]
        assert "require_reversible" not in item["payload"]
    jobs = [j async for j in db.patch_deployment_jobs.find({"rolloutId": rollout_id, "dispatchedAgents": {"$in": ["b1", "b2", "b3"]}})]
    assert len(jobs) == 3 and all(j["status"] == "In Progress" for j in jobs)
    assert (await host_doc(db, "b1"))["state"] == "installing"

    again = await lines.approve_line(db, T, rollout_id, 1, "install", approver=APPROVER, now=later)
    assert again["status"] == "already_handled" and again["approved"] == 0
    assert len(await instructions(db)) == before + 3                    # a second click writes nothing


async def test_a_click_and_a_tick_that_meet_on_one_row_write_one_instruction(mongo_db, clock):
    db = mongo_db
    rollout_id, opens, inside = await closed_window_world(db, clock, ("b1",))
    clock["now"] = inside
    await online_at(db, inside)
    row = (await ring_one_rows(db))[0]
    first = await dispatcher.send(db, row, inside)
    second = await dispatcher.send(db, row, inside)                      # the same stale row, as a racing caller holds it
    assert first["status"] == "queued" and second["status"] == "deferred" and second["reason"] == "already_sent"
    assert len([i for i in await instructions(db) if i["agent_id"] == "b1"]) == 1


# ---------------------------------------------------------------- window closed

async def ring_one_instructions(db):
    return [i for i in await instructions(db) if i["agent_id"] != "a1"]


async def test_with_the_window_closed_the_rows_stay_approved_and_the_first_open_tick_sends_them_once(mongo_db, clock):
    db = mongo_db
    rollout_id, opens, inside = await closed_window_world(db, clock)
    assert [r["state"] for r in await ring_one_rows(db)] == ["approved"] * 3
    assert len(await ring_one_instructions(db)) == 0                       # approved, but nothing is sent
    await controller.tick(db, now=NOW + timedelta(hours=26))               # still closed: the ring says what it waits for
    rollout = await db.patch_rollouts.find_one({"id": rollout_id})
    assert rollout["rings"][1]["state"] == "waiting_for_window"
    assert len(await ring_one_instructions(db)) == 0

    await online_at(db, inside)
    await controller.tick(db, now=inside)
    assert len(await ring_one_instructions(db)) == 3
    assert [r["state"] for r in await ring_one_rows(db)] == ["dispatching"] * 3
    await controller.tick(db, now=inside + timedelta(minutes=1))
    assert len(await ring_one_instructions(db)) == 3                       # a second tick sends nothing more


# ---------------------------------------------------------------- the computer at dispatch time

async def break_it(db, kind):
    if kind == "claim_released":
        await store.release(db, T, (await db.patch_rollouts.find_one({}))["id"], ["b1"])
    elif kind == "capability_off":
        await db.tenants.update_one({"id": T}, {"$set": {"agentCapabilities": []}})
    elif kind == "offline":
        await db.agents.update_one({"id": "b1"}, {"$set": {"lastSeen": (NOW - timedelta(days=3)).isoformat()}})
    elif kind == "busy":
        await db.patch_deployment_jobs.insert_one({"id": "other-job", "tenantId": T, "status": "In Progress",
                                                   "dispatchedAgents": ["b1"], "agentResults": {}})


async def fix_it(db, kind, when):
    if kind == "claim_released":
        await db.patch_rollout_hosts.update_one({"agentId": "b1"}, {"$set": {"active": True}})
    elif kind == "capability_off":
        await db.tenants.update_one({"id": T}, {"$set": {"agentCapabilities": ["all"]}})
    elif kind == "offline":
        await db.agents.update_one({"id": "b1"}, {"$set": {"lastSeen": when.isoformat()}})
    elif kind == "busy":
        await db.patch_deployment_jobs.update_one({"id": "other-job"}, {"$set": {"status": "Completed"}})


@pytest.mark.real_agent_capabilities          # the suite otherwise turns every capability on (tests/conftest.py)
@pytest.mark.parametrize("kind", ["claim_released", "capability_off", "offline", "busy"])
async def test_a_computer_that_cannot_take_an_approved_row_at_dispatch_time_is_never_sent_anything(mongo_db, clock, kind):
    db = mongo_db
    rollout_id, opens, inside = await closed_window_world(db, clock, ("b1",))
    clock["now"] = inside
    await online_at(db, inside)
    await break_it(db, kind)
    await controller.tick(db, now=inside)
    assert [i for i in await instructions(db) if i["agent_id"] == "b1"] == []
    assert [r["state"] for r in await ring_one_rows(db)] == ["approved"]

    await fix_it(db, kind, inside)
    await controller.tick(db, now=inside + timedelta(minutes=1))
    assert len([i for i in await instructions(db) if i["agent_id"] == "b1"]) == 1
    assert [r["state"] for r in await ring_one_rows(db)] == ["dispatching"]


async def test_a_restart_row_for_a_computer_without_the_restart_token_is_never_sent(mongo_db, clock):
    db = mongo_db
    rollout_id, _ = await ring_one(db, ("b1",))
    later = NOW + timedelta(hours=1, minutes=5)
    rollout = await db.patch_rollouts.find_one({"id": rollout_id}, {"_id": 0})
    doc = await host_doc(db, "b1")
    await online_at(db, later)
    made = await lines.raise_line(db, T, rollout, 1, "reboot", [(doc, "reboot_host", {"delay_seconds": 300, "reason": "x"})], later)
    assert made["raised"] == 1
    await db.agents.update_one({"id": "b1"}, {"$set": {"meta.response_actions.tokens": ["patch_reversible_check"]}})
    clock["now"] = later
    result = await lines.approve_line(db, T, rollout_id, 1, "reboot", approver=APPROVER, now=later)
    assert result["status"] == "approved" and result["when"] == "window"
    reboot = (await rows(db, command="reboot_host"))[0]
    assert reboot["state"] == "approved" and [i for i in await instructions(db) if i["type"] == "reboot_host"] == []
    await controller.tick(db, now=later + timedelta(minutes=1))
    assert [i for i in await instructions(db) if i["type"] == "reboot_host"] == []
    await db.agents.update_one({"id": "b1"}, {"$set": {"meta.response_actions.tokens": ["reboot_host"]}})
    await online_at(db, later + timedelta(minutes=2))
    await controller.tick(db, now=later + timedelta(minutes=2))
    assert len([i for i in await instructions(db) if i["type"] == "reboot_host"]) == 1


# ---------------------------------------------------------------- deny, stop, scope

async def test_deny_line_moves_every_awaiting_row_to_denied_and_writes_nothing(mongo_db, clock):
    db = mongo_db
    rollout_id, later = await ring_one(db)
    before = len(await instructions(db))
    result = await lines.deny_line(db, T, rollout_id, 1, "install", approver=APPROVER, reason="not today")
    assert result["status"] == "denied" and "Denied by Bo" in result["message"] and "Everyone else" in result["message"]
    assert [r["state"] for r in await ring_one_rows(db)] == ["denied"] * 3
    assert len(await instructions(db)) == before
    assert (await lines.deny_line(db, T, rollout_id, 1, "install", approver=APPROVER))["status"] == "already_handled"
    assert (await lines.approve_line(db, T, rollout_id, 1, "install", approver=APPROVER, now=later))["status"] == "already_handled"
    assert len(await instructions(db)) == before


async def test_a_stop_answers_stopped_and_changes_nothing(mongo_db, clock):
    db = mongo_db
    rollout_id, later = await ring_one(db)
    await db.autonomy_settings.update_one({"tenantId": T}, {"$set": {"stop": {"active": True}}})
    result = await lines.approve_line(db, T, rollout_id, 1, "install", approver=APPROVER, now=later)
    assert result["status"] == "stopped" and result["approved"] == 0
    assert [r["state"] for r in await ring_one_rows(db)] == ["awaiting_approval"] * 3


async def test_a_rollout_that_is_not_running_or_unknown_is_refused(mongo_db, clock):
    db = mongo_db
    rollout_id, later = await ring_one(db)
    unknown = await lines.approve_line(db, T, "nope", 1, "install", approver=APPROVER, now=later)
    assert unknown["status"] == "refused" and unknown["message"] == "This step was not found."
    await db.patch_rollouts.update_one({"id": rollout_id}, {"$set": {"status": "halted"}})
    for call in (lines.approve_line(db, T, rollout_id, 1, "install", approver=APPROVER, now=later),
                 lines.deny_line(db, T, rollout_id, 1, "install", approver=APPROVER)):
        result = await call
        assert result["status"] == "refused" and result["message"] == "This rollout is not running, so nothing was decided."
    assert [r["state"] for r in await ring_one_rows(db)] == ["awaiting_approval"] * 3


async def test_one_lines_approval_never_approves_another_line_or_another_tenants_row(mongo_db, clock):
    db = mongo_db
    rollout_id, later = await ring_one(db, ("b1",))
    rollout = await db.patch_rollouts.find_one({"id": rollout_id}, {"_id": 0})
    doc = await host_doc(db, "b1")
    await lines.raise_line(db, T, rollout, 1, "reboot", [(doc, "reboot_host", {"delay_seconds": 300, "reason": "x"})], later)
    clock["now"] = later
    assert (await lines.approve_line(db, T, rollout_id, 1, "install", approver=APPROVER, now=later))["approved"] == 1
    reboot = (await rows(db, command="reboot_host"))[0]
    assert reboot["state"] == "awaiting_approval"
    assert (await lines.approve_line(db, "other-tenant", rollout_id, 1, "reboot", approver=APPROVER, now=later))["status"] == "refused"
    assert (await rows(db, command="reboot_host"))[0]["state"] == "awaiting_approval"


# ---------------------------------------------------------------- registration

def test_importing_the_dispatcher_registers_it_with_approvals():
    assert approvals._DISPATCHERS["patch_rollout"] is dispatcher.dispatcher


def test_a_process_that_serves_approvals_has_the_dispatcher():
    code = ("import autonomous_ops_response_endpoints\n"
            "from autonomous_ops import approvals\n"
            "print('patch_rollout' in approvals._DISPATCHERS)\n")
    env = {**os.environ, "JWT_SECRET_KEY": "test-key-not-a-secret", "ENVIRONMENT": "development"}
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)
    assert out.stdout.strip().splitlines()[-1:] == ["True"], out.stderr[-800:]
