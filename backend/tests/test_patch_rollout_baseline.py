"""Staged patch rollouts, gap plan 84-25: the pre-change services baseline is recorded when an install is queued.

Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py. Time is frozen by
passing ``now`` to the real controller tick; the agent's last ``meta.service_state`` block stands for what the
computer looked like before the change.

Value: protects=PTCH-02 / PTCH-04 / CR-03 / T-84-70: a queued install (automatic canary or approved line) keeps the
computer's services as it was (``servicesPresentBefore`` / ``servicesAbsentBefore`` on its rollout host row) so the
health gate can tell a service the computer never had from one the patch removed; the lists merge across attempts;
no block or no queue means no baseline (fail closed, absent then reads as no data);
fails_when=a queued install leaves no baseline, a retry overwrites an earlier present name, a refused or failed send
writes a baseline, a baseline write error ends the send; no_claim=a real agent, a real install or the live database.
"""
import os
import sys
from datetime import timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import gate
from autonomous_ops.rollout import controller, lines, signals
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.test_patch_rollout_gap_inflight import APPROVER, NOW, T, base, begin, host, host_doc, _env  # noqa: F401


def block(**states):
    return {"v": 1, "at": int(NOW.timestamp()), "services": [{"name": n, "state": s} for n, s in states.items()]}


async def set_block(db, value):
    await db.agents.update_one({"id": "a1", "tenantId": T}, {"$set": {"meta.service_state": value}})


async def queue_the_install(db, path):
    """Drive a canary computer a1 to a queued install by the automatic path or by an approved line."""
    await base(db, level="undoable_auto" if path == "automatic" else "suggest")
    await host(db, "a1", canary=True)
    await set_block(db, block(sshd="running", nginx="absent"))
    rollout_id = await begin(db)
    await controller.tick(db, now=NOW)
    if path == "approved":
        await lines.approve_line(db, T, rollout_id, 0, "install", approver=APPROVER, now=NOW)
        await controller.tick(db, now=NOW + timedelta(seconds=30))
    return rollout_id


@pytest.mark.parametrize("path", ["automatic", "approved"])
async def test_a_queued_install_records_the_services_the_computer_had_before(mongo_db, path):
    db = mongo_db
    await queue_the_install(db, path)
    doc = await host_doc(db, "a1")
    assert doc["state"] == "installing"
    assert doc["servicesPresentBefore"] == ["sshd"] and doc["servicesAbsentBefore"] == ["nginx"]


async def test_a_later_attempt_never_hides_an_earlier_presence(mongo_db):
    db = mongo_db
    await queue_the_install(db, "automatic")
    later = signals.service_baseline({"meta": {"service_state": block(sshd="absent", nginx="absent", cron="running")}})
    await signals.record_service_baseline(db, T, (await host_doc(db, "a1"))["rolloutId"], "a1", later)
    doc = await host_doc(db, "a1")
    assert sorted(doc["servicesPresentBefore"]) == ["cron", "sshd"]          # sshd stays present: merged, not set
    assert sorted(doc["servicesAbsentBefore"]) == ["nginx", "sshd"]
    after = {"meta": {"response_actions": {"tokens": ["service_state"]},
                      "service_state": {"v": 1, "at": int((NOW + timedelta(hours=1)).timestamp()),
                                        "services": [{"name": "sshd", "state": "absent"}]}}}
    host_ = {**doc, "agentId": "a1", "state": "installed", "installReportedAt": NOW}
    assert signals.read(after, host_, ["sshd"], [])["services"] is False      # present before, absent after: fails


@pytest.mark.parametrize("path", ["automatic", "approved"])
async def test_an_agent_with_no_service_block_gets_no_baseline(mongo_db, path):
    db = mongo_db
    await base(db, level="undoable_auto" if path == "automatic" else "suggest")
    await host(db, "a1", canary=True)
    rollout_id = await begin(db)
    await controller.tick(db, now=NOW)
    if path == "approved":
        await lines.approve_line(db, T, rollout_id, 0, "install", approver=APPROVER, now=NOW)
        await controller.tick(db, now=NOW + timedelta(seconds=30))
    doc = await host_doc(db, "a1")
    assert doc["state"] == "installing"
    assert "servicesPresentBefore" not in doc and "servicesAbsentBefore" not in doc


@pytest.mark.parametrize("path", ["automatic", "approved"])
async def test_a_send_that_is_not_queued_writes_no_baseline(mongo_db, monkeypatch, path):
    db = mongo_db
    await base(db, level="undoable_auto" if path == "automatic" else "suggest")
    await host(db, "a1", canary=True)
    await set_block(db, block(sshd="running", nginx="absent"))
    rollout_id = await begin(db)

    async def refused(*args, **kwargs):
        return {"status": "refused", "reason": "nope"}

    if path == "automatic":
        monkeypatch.setattr(gate, "execute", refused)
        await controller.tick(db, now=NOW)
    else:
        await controller.tick(db, now=NOW)
        monkeypatch.setattr(gate, "execute", refused)
        await lines.approve_line(db, T, rollout_id, 0, "install", approver=APPROVER, now=NOW)
        await controller.tick(db, now=NOW + timedelta(seconds=30))
    doc = await host_doc(db, "a1")
    assert doc["state"] != "installing"
    assert "servicesPresentBefore" not in doc and "servicesAbsentBefore" not in doc


class BrokenDb:
    """A database whose every collection raises, for the baseline helpers (they must never raise)."""

    def __getattr__(self, name):
        raise RuntimeError("database unavailable")


async def test_a_baseline_that_cannot_be_read_or_written_is_logged_and_never_raises():
    assert await signals.record_service_baseline(BrokenDb(), T, "r1", "a1", (["sshd"], [])) is None
    assert await signals.read_service_baseline(BrokenDb(), T, "a1") is None


async def test_a_baseline_that_cannot_be_read_never_ends_the_send(mongo_db, monkeypatch):
    def broken(agent):
        raise RuntimeError("unreadable")

    monkeypatch.setattr(signals, "service_baseline", broken)
    await queue_the_install(mongo_db, "automatic")
    doc = await host_doc(mongo_db, "a1")
    assert doc["state"] == "installing" and "servicesPresentBefore" not in doc


def test_the_baseline_of_a_block_splits_present_from_absent_and_ignores_a_missing_or_malformed_block():
    got = signals.service_baseline({"meta": {"service_state": block(SSHD="running", nginx="absent", cron="unknown",
                                                                    db="stopped")}})
    assert got == (["cron", "db", "sshd"], ["nginx"])
    assert signals.service_baseline(None) is None and signals.service_baseline({"meta": {}}) is None
    assert signals.service_baseline({"meta": {"service_state": {"services": "x"}}}) is None
