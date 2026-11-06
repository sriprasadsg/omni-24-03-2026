"""Staged patch rollouts, plan 84-16 task 3: the Activity list says, in plain words, what each rollout step did.

Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py. The rows are made by
the real controller, the real halt and revert, and the real restart settle; they are read back through the real
Activity presenter (``views.present_row``) and list (``views.list_page``). Every sentence is compared with
``messages.ACTIVITY`` (UI-SPEC section 7), never with a copy of the words.

Value: protects=ACTV-01 / ACTV-02 / PTCH-04 / PROH-84-02: a canary install row says why it ran and, once the
agent answered, what happened; a patch that cannot be reversed says it needs a person; a revert says which ring
halted and why, and a computer that could not be put back never reads as reverted; a restart says when the
computer came back; fails_when=a Why or Result text is missing, written outside messages.py, shows the wrong
patch, computer or time, or a Not reverted row starts with the word Reverted; no_claim=the browser rendering.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import ledger, protected, views
from autonomous_ops.rollout import controller, lifecycle, lines, messages as rm, store
from autonomous_ops.rollout import windows as windows_mod
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.rollout_support import failure_result, post_result, success_result
from tests.test_patch_rollout_boot import approved_restart, clock  # noqa: F401  (clock is a fixture)
from tests.test_patch_rollout_lines import NOW, T, base, begin, host, host_doc, online_at, rows
from tests.test_patch_rollout_revert import NO_TOKEN, WITH_TOKEN, add, answer, example, halt, world as revert_world

A = rm.ACTIVITY


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()


async def shown(db, action_id, name=None):
    """The row as the Activity list presents it."""
    return views.present_row(await ledger.get(db, T, action_id), viewer_is_platform_staff=False,
                             host=name or "host-a1")


async def canary_row(db, patch_ids=("openssl",), **host_kwargs):
    await base(db)
    await host(db, "a1", canary=True, pending=patch_ids, **host_kwargs)
    rollout_id = await begin(db, patch_ids)
    await controller.tick(db, now=NOW)
    found = await rows(db)
    assert len(found) == 1, found
    return rollout_id, found[0]


# ---------------------------------------------------------------- the canary install

async def test_a_canary_install_says_why_it_ran_and_what_the_agent_confirmed(mongo_db):
    """fails_when=the Why lacks the rollout name or the patch, or the Result is the generic word Done."""
    db = mongo_db
    rollout_id, row = await canary_row(db)
    why = rm.fill(A["canary_why"], rollout="Nov", patch="openssl")
    assert row["reasonText"] == why and why == "Nov: canary ring, reversible patch (openssl)."

    sending = await shown(db, row["id"])
    assert sending["reasonText"] == why and sending["resultText"] == "Sent to the host. Waiting for the result."

    job = await db.patch_deployment_jobs.find_one({"rolloutId": rollout_id})
    await post_result(db, job["id"], "a1", success_result(["openssl"]))
    await controller.tick(db, now=NOW + timedelta(minutes=2))

    done = await shown(db, row["id"])
    assert done["state"] == "executed" and done["reasonText"] == why
    assert done["resultText"] == rm.fill(A["canary_done"], patch="openssl")
    assert done["resultText"] == "Installed openssl. Verified: it is no longer pending."


async def test_a_canary_install_the_computer_did_not_confirm_says_it_is_marked_failed(mongo_db):
    db = mongo_db
    rollout_id, row = await canary_row(db)
    job = await db.patch_deployment_jobs.find_one({"rolloutId": rollout_id})
    await post_result(db, job["id"], "a1", failure_result(["openssl"]))
    await controller.tick(db, now=NOW + timedelta(minutes=2))
    failed = await shown(db, row["id"])
    assert failed["state"] == "failed" and failed["resultText"] == A["canary_failed"]
    assert failed["reasonText"] == rm.fill(A["canary_why"], rollout="Nov", patch="openssl")


async def test_several_patches_are_listed_in_the_why_and_the_result(mongo_db):
    db = mongo_db
    rollout_id, row = await canary_row(db, patch_ids=("openssl", "curl"))
    assert row["reasonText"] == rm.fill(A["canary_why"], rollout="Nov", patch="openssl, curl")
    job = await db.patch_deployment_jobs.find_one({"rolloutId": rollout_id})
    await post_result(db, job["id"], "a1", success_result(["openssl", "curl"]))
    await controller.tick(db, now=NOW + timedelta(minutes=2))
    assert (await shown(db, row["id"]))["resultText"] == rm.fill(A["canary_done"], patch="openssl, curl")


async def test_a_patch_that_cannot_be_reversed_says_it_needs_your_approval(mongo_db):
    """fails_when=the approval row for a non-reversible patch has the generic reason."""
    db = mongo_db
    await base(db)
    await host(db, "a1", canary=True, tokens=("reboot_host",))          # the agent cannot check reversibility
    await begin(db)
    await controller.tick(db, now=NOW)
    found = await rows(db)
    assert len(found) == 1 and found[0]["state"] == "awaiting_approval"
    row = await shown(db, found[0]["id"])
    assert row["reasonText"] == rm.fill(A["not_reversible_why"], patch="openssl", host="host-a1")
    assert row["reasonText"] == "openssl can't be reversed on host-a1, so it needs your approval."
    assert row["resultText"] == A["not_reversible_result"] == "Waiting for your approval."


# ---------------------------------------------------------------- the revert

async def settled_revert(db):
    """Pilot halts; l1 (Linux package), w1 (Windows KB), x1 (cannot be uninstalled) and l2 (agent too old)."""
    await revert_world(db)
    await add(db, "w1", os_name="windows", tokens=NO_TOKEN, ids=("KB5034441",))
    await add(db, "l1", ids=("openssl",))
    await add(db, "x1", ids=("curl",))
    await add(db, "l2", tokens=NO_TOKEN)
    await halt(db)
    await answer(db, "l1", example("revert_ok", patch_id="openssl"))
    await answer(db, "w1", example("revert_ok", patch_id="KB5034441"))
    await answer(db, "x1", example("revert_not_uninstallable", patch_id="curl"))
    await controller.tick(db, now=NOW + timedelta(minutes=1))


async def test_a_revert_names_the_ring_that_halted_and_what_the_computer_confirmed(mongo_db):
    """protects=PROH-84-02c; fails_when=a computer that could not be put back reads as reverted, or the Why drops the
    ring or the reason."""
    db = mongo_db
    await settled_revert(db)
    why = rm.fill(A["revert_why"], ring="Pilot", reason="host-x1 failed its health check")
    assert why == "Pilot halted: host-x1 failed its health check."

    linux = await shown(db, "AO-l1", "host-l1")
    assert linux["state"] == "undone" and linux["reasonText"] == why
    assert linux["resultText"] == rm.fill(A["revert_done_package"], patch="openssl", host="host-l1")
    windows = await shown(db, "AO-w1", "host-w1")
    assert windows["reasonText"] == why and windows["resultText"] == rm.fill(A["revert_done_update"], patch="KB5034441")
    assert windows["resultText"] == "Uninstalled KB5034441. Verified: it is no longer listed."

    stuck = await shown(db, "AO-x1", "host-x1")
    assert stuck["reasonText"] == why and stuck["resultText"] == rm.NOT_REVERTED["not_uninstallable"]
    assert not stuck["resultText"].startswith("Reverted") and stuck["resultText"].startswith("Not reverted")

    old = await shown(db, "AO-l2", "host-l2")           # never sent anything: the install row says why
    assert old["state"] == "executed" and old["resultText"] == rm.NOT_REVERTED["agent_unsupported"]
    assert old["reasonText"] == why


async def test_a_reason_the_screen_has_no_words_for_still_reads_not_reverted(mongo_db):
    db = mongo_db
    await revert_world(db)
    await add(db, "l1", ids=("openssl",))
    await halt(db)
    await answer(db, "l1", {"status": "failed", "successful": 0, "failed": 1, "total": 1,
                            "results": [{"patch_id": "openssl", "status": "failed", "code": "something_new"}]})
    await controller.tick(db, now=NOW + timedelta(minutes=1))
    got = await shown(db, "AO-l1", "host-l1")
    assert got["resultText"] == rm.NOT_REVERTED_OTHER and got["resultText"].startswith("Not reverted")


# ---------------------------------------------------------------- the restart

async def test_a_restart_that_saw_the_new_boot_says_when_the_computer_came_back(mongo_db, clock):
    """fails_when=the time is shown in UTC instead of the organization's zone, or is the dispatch time."""
    db = mongo_db
    rollout_id, _ = await approved_restart(db, clock)
    await db.maintenance_settings.update_one({"tenantId": T}, {"$set": {"timeZone": "Asia/Kolkata"}}, upsert=True)
    due = (await host_doc(db, "a1"))["scheduledRestartAt"].replace(tzinfo=timezone.utc)
    booted = due + timedelta(minutes=2)
    back = due + timedelta(minutes=10)
    await online_at(db, back)
    await db.agents.update_one({"id": "a1"}, {"$set": {"meta.response_state.boot_time": int(booted.timestamp())}})
    await controller.tick(db, now=back)
    row = (await rows(db, command="reboot_host"))[0]
    got = await shown(db, row["id"])
    at = windows_mod.clock_text(booted, "Asia/Kolkata")
    assert got["state"] == "executed" and got["resultText"] == rm.fill(A["restart_done"], at=at)
    assert got["resultText"].startswith("Restarted. Warned 5 minutes before. Back online at ")
    assert got["reasonText"] == rm.fill(A["restart_why"], rollout="Nov", ring="Canary")


# ---------------------------------------------------------------- the list

async def test_the_activity_list_returns_the_why_and_result_of_a_rollout_row(mongo_db):
    """protects=ACTV-02; fails_when=the endpoint's page drops the texts."""
    db = mongo_db
    rollout_id, row = await canary_row(db)
    job = await db.patch_deployment_jobs.find_one({"rolloutId": rollout_id})
    await post_result(db, job["id"], "a1", success_result(["openssl"]))
    await controller.tick(db, now=NOW + timedelta(minutes=2))
    page = await views.list_page(db, T, bucket="all", limit=25, cursor=None, viewer_is_platform_staff=False)
    item = next(i for i in page["items"] if i["id"] == row["id"])
    assert item["reasonText"] == rm.fill(A["canary_why"], rollout="Nov", patch="openssl")
    assert item["resultText"] == rm.fill(A["canary_done"], patch="openssl")
    assert item["canUndo"] is False


def test_no_rollout_module_writes_an_activity_sentence_of_its_own():
    """protects=PTCH-04 (every text comes from messages.py); fails_when=a Why or Result is typed into a module."""
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "autonomous_ops", "rollout")
    for name in ("installs.py", "settle.py", "revert.py", "reboots.py"):
        text = open(os.path.join(root, name), encoding="utf-8").read()
        assert "ACTIVITY" in text or name == "installs.py", name
        for phrase in ("Verified: it is no longer", "Uninstalled ", "Back online at", "halted: "):
            assert phrase not in text, (name, phrase)
