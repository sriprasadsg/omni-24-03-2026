"""One origin suggests, a second one within 24 hours acts, and the tenant's switch is honoured
(Phase 83, plan 83-05, RESP-08 / D-03 / D-04 / D-14). Real MongoDB (skips without one) through the
throwaway database of tests/_mongo_test_db.py. The full sweep tick is the system under test.

Value: protects=a single source only ever records a suggestion, the second different source inside 24 hours
turns it into the automatic action and ends the suggestion as superseded, later than that it stays a
suggestion, the tenant's switch lets one source act while every other limit stays, and after a block has
run out the address needs two fresh origins again;
fails_when=one source acts, the 24 hour edge moves, the order the sources arrive in changes the result, a
dormant computer gets a row, or expiry is treated as an undo;
no_claim=a real agent or firewall (the instruction is only written, never sent anywhere).
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import agent_support, ledger, protected, signals, sweep
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import (seed_feed_ioc, seed_native_verdict, seed_response_agent, seed_telemetry,
                                    seed_tenant)

IP = "45.33.32.156"
SHA = "d" * 64
NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)
SUGGEST_KEY = f"t1|sweep-suggest|block_ip|a1|{IP}"
ACT_KEY = f"t1|sweep|block_ip|a1|{IP}"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()


async def _world(db, *, shadow=False, tokens=("block_ip_ttl", "quarantine_file"), two_signal=None):
    await ledger.ensure_indexes(db)
    await signals.ensure_indexes(db)
    await seed_tenant(db, "t1", shadow=shadow)
    await seed_response_agent(db, "t1", "a1", hostname="host-a1", tokens=list(tokens), last_seen=NOW)
    if two_signal is not None:
        await db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"response": {"twoSignal": two_signal}}})


async def _native(db, at, target=IP):
    await seed_native_verdict(db, "t1", "host-a1", kind="ip", target=target, created_at=at - timedelta(minutes=5))


async def _feed(db, at):
    await seed_feed_ioc(db, ioc_type="url", value=f"http://{IP}/x", source_ip=IP, feed="urlhaus", updated_at=at)


async def _tick(db, at):
    await db.agents.update_one({"id": "a1"}, {"$set": {"lastSeen": at.isoformat()}})
    return await sweep.tick(db, now=at)


async def _rows(db, key=None):
    flt = {"tenantId": "t1", "kind": {"$ne": "control"}}
    if key:
        flt["dedupeKey"] = key
    return [r async for r in db.autonomy_actions.find(flt, {"_id": 0}).sort("createdAt", 1)]


async def _instructions(db):
    return [d async for d in db.agent_instructions.find({"tenantId": "t1"}, {"_id": 0})]


# ------------------------------------------------------------------ one origin suggests

async def test_one_origin_records_one_suggestion_and_sends_nothing(mongo_db):
    await _world(mongo_db)
    await _native(mongo_db, NOW)
    counts = await _tick(mongo_db, NOW)
    (row,) = await _rows(mongo_db)
    assert counts["blocked"] == 0 and row["state"] == "suggested" and row["dedupeKey"] == SUGGEST_KEY
    inputs = row["reason"]["inputs"]
    assert inputs["suggestionOnly"] is True and inputs["suggestion"] == {"kind": "single_signal"}
    assert inputs["origins"] == ["native"] and inputs["indicator"] == IP and inputs["twoSignal"] is True
    assert row["command"] == "block_ip" and row["dispatcher"] == "security_response"
    assert row["reasonText"].startswith("Only one source flagged this: agent verdict.")
    assert await _instructions(mongo_db) == []


async def test_ten_ticks_over_one_suggestion_change_nothing(mongo_db):
    await _world(mongo_db)
    await _native(mongo_db, NOW)
    await _tick(mongo_db, NOW)
    first = await _rows(mongo_db)
    for _ in range(9):
        await _tick(mongo_db, NOW)
    assert await _rows(mongo_db) == first


async def test_a_suggestion_is_kept_alive_while_the_source_is_still_seen(mongo_db):
    await _world(mongo_db)
    await _native(mongo_db, NOW)
    await _tick(mongo_db, NOW)
    (row,) = await _rows(mongo_db)
    later = NOW + 13 * HOUR
    await _native(mongo_db, later)
    await _tick(mongo_db, later)
    (again,) = await _rows(mongo_db)
    assert again["id"] == row["id"] and again["state"] == "suggested"
    assert again["approval"]["expiresAt"].replace(tzinfo=timezone.utc) == later + 24 * HOUR


# ------------------------------------------------------------------ a second origin inside 24 hours acts

@pytest.mark.parametrize("first", ["native", "feed"])
@pytest.mark.parametrize("gap, acts", [(timedelta(hours=23), True), (timedelta(hours=24), True),
                                       (timedelta(hours=24, seconds=1), False), (timedelta(hours=25), False)])
async def test_the_second_origin_promotes_inside_24_hours_in_either_order_and_not_after(mongo_db, first, gap, acts):
    await _world(mongo_db)
    arrive = NOW + gap
    if first == "feed":          # the computer already talks to the address, so the feed row names a host
        await seed_telemetry(mongo_db, "a1", connections=[{"remote_address": f"{IP}:443"}])
        await _feed(mongo_db, NOW)
        await _tick(mongo_db, NOW)
        await _native(mongo_db, arrive)
        await _tick(mongo_db, arrive)
    else:
        await _native(mongo_db, NOW)
        await _tick(mongo_db, NOW)
        await _feed(mongo_db, arrive)
        await _tick(mongo_db, arrive)
    suggestion = (await _rows(mongo_db, SUGGEST_KEY))
    acting = await _rows(mongo_db, ACT_KEY)
    assert len(suggestion) == 1
    if acts:
        (act,) = acting
        assert act["state"] == "dispatching" and act["reason"]["inputs"]["origins"] == ["feed:urlhaus", "native"]
        assert act["reason"]["inputs"]["twoSignal"] is True and act["reasonText"].startswith("Two sources agree:")
        assert len(await _instructions(mongo_db)) == 1
        assert suggestion[0]["state"] == "expired" and suggestion[0]["reasonCode"] == "superseded"
    else:
        assert acting == [] and await _instructions(mongo_db) == []
        assert suggestion[0]["state"] == "suggested" and suggestion[0]["reason"]["inputs"]["origins"] == [first_origin(first)]


def first_origin(first):
    return "native" if first == "native" else "feed:urlhaus"


async def test_one_event_seen_through_its_mirrored_alert_is_still_one_origin(mongo_db):
    """PROH-83-03: a native verdict and the alert it writes never satisfy the two-source rule."""
    from tests.autonomy_support import seed_alert
    await _world(mongo_db)
    await seed_native_verdict(mongo_db, "t1", "host-a1", kind="file", target="/tmp/evil", sha256=SHA,
                              created_at=NOW - timedelta(minutes=5))
    await seed_alert(mongo_db, "t1", "host-a1", sha256=SHA, source="native", created_at=NOW - timedelta(minutes=5))
    await _tick(mongo_db, NOW)
    (row,) = await _rows(mongo_db)
    assert row["state"] == "suggested" and row["reason"]["inputs"]["origins"] == ["native"]
    assert row["command"] == "quarantine_file" and row["params"] == {"path": "/tmp/evil", "sha256": SHA}


async def test_a_file_that_two_origins_name_is_left_for_the_quarantine_plan(mongo_db):
    """File candidates are observed and suggested here; the automatic quarantine decision is plan 83-11."""
    from tests.autonomy_support import seed_alert
    await _world(mongo_db)
    await seed_native_verdict(mongo_db, "t1", "host-a1", kind="file", target="/tmp/evil", sha256=SHA,
                              created_at=NOW - timedelta(minutes=5))
    await seed_alert(mongo_db, "t1", "host-a1", sha256=SHA, vt_ratio="9/70", created_at=NOW - timedelta(minutes=5))
    await _tick(mongo_db, NOW)
    assert await _rows(mongo_db) == [] and await _instructions(mongo_db) == []
    assert await mongo_db.autonomy_signals.count_documents({"kind": "file"}) == 1


# ------------------------------------------------------------------ the tenant's switch (D-04)

async def test_with_the_rule_off_one_origin_acts_and_says_so(mongo_db):
    await _world(mongo_db, two_signal=False)
    await _native(mongo_db, NOW)
    counts = await _tick(mongo_db, NOW)
    (row,) = await _rows(mongo_db)
    assert counts["blocked"] == 1 and row["dedupeKey"] == ACT_KEY and row["state"] == "dispatching"
    assert row["reason"]["inputs"]["twoSignal"] is False and row["reason"]["inputs"]["origins"] == ["native"]
    assert row["reasonText"].startswith("This organization's two-source rule is off")
    assert len(await _instructions(mongo_db)) == 1


async def test_with_the_rule_off_every_other_limit_still_applies(mongo_db):
    await _world(mongo_db, shadow=True, two_signal=False)
    await _native(mongo_db, NOW)
    await _tick(mongo_db, NOW)
    (row,) = await _rows(mongo_db)
    assert row["state"] == "shadow" and row["wouldHave"] == "allow_auto" and await _instructions(mongo_db) == []


async def test_in_shadow_a_suggestion_is_a_simulation_that_would_have_suggested(mongo_db):
    await _world(mongo_db, shadow=True)
    await _native(mongo_db, NOW)
    await _tick(mongo_db, NOW)
    (row,) = await _rows(mongo_db)
    assert row["state"] == "shadow" and row["wouldHave"] == "suggest" and row["dedupeKey"] == SUGGEST_KEY


# ------------------------------------------------------------------ dormant computers stay silent

@pytest.mark.parametrize("both", [False, True])
async def test_a_computer_that_cannot_carry_the_action_gets_neither_a_suggestion_nor_an_action(mongo_db, both):
    await _world(mongo_db, tokens=[])
    await _native(mongo_db, NOW)
    if both:
        await _feed(mongo_db, NOW)
    await _tick(mongo_db, NOW)
    assert await _rows(mongo_db) == [] and await _instructions(mongo_db) == []


# ------------------------------------------------------------------ after a block has run out (D-14)

async def _block_then_let_it_run_out(db):
    await _native(db, NOW)
    await _feed(db, NOW)
    await _tick(db, NOW)
    (row,) = await _rows(db)
    await db.autonomy_actions.update_one(
        {"id": row["id"]}, {"$set": {"state": "verified", "blockedFrom": NOW, "blockedUntil": NOW + 24 * HOUR,
                                      "finishedAt": NOW}})
    return row["id"]


async def test_after_a_block_expires_old_evidence_does_not_count_and_fresh_evidence_from_two_origins_does(mongo_db):
    await _world(mongo_db)
    first_id = await _block_then_let_it_run_out(mongo_db)
    after = NOW + 25 * HOUR
    await _tick(mongo_db, after)                      # same old evidence: nothing new
    assert [r["id"] for r in await _rows(mongo_db)] == [first_id]
    await _native(mongo_db, after)                    # fresh evidence from two origins
    await mongo_db.edr_ioc.update_one({}, {"$set": {"updated_at": after.isoformat()}})
    await _tick(mongo_db, after)
    rows = await _rows(mongo_db)
    assert len(rows) == 2 and rows[1]["state"] == "dispatching" and rows[1]["id"] != first_id
    assert rows[0]["state"] == "verified"             # expiry is never an undo
    assert [d["type"] for d in await _instructions(mongo_db)] == ["block_ip", "block_ip"]     # never an unblock


async def test_after_a_block_expires_one_fresh_origin_is_only_a_suggestion(mongo_db):
    await _world(mongo_db)
    await _block_then_let_it_run_out(mongo_db)
    after = NOW + 25 * HOUR
    await _native(mongo_db, after)
    await _tick(mongo_db, after)
    rows = await _rows(mongo_db)
    assert [r["state"] for r in rows] == ["verified", "suggested"] and rows[1]["dedupeKey"] == SUGGEST_KEY
    assert rows[1]["reason"]["inputs"]["origins"] == ["native"]


def test_the_agent_token_for_quarantine_is_what_the_file_test_seeds():
    assert agent_support.token_for("quarantine_file") == "quarantine_file"
