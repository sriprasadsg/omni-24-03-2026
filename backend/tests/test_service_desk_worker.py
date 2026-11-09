"""The desk worker (Phase 85, plan 85-17, DESK-05, D-21). Real MongoDB (skips without one) through the throwaway
database of tests/_mongo_test_db.py; the local model is a stand-in (httpx.MockTransport) and the time is an
injected clock, so nothing waits and no real model is called.

Value: protects=one generation at a time across the deployment, cheap rules before the slow call, nothing that
cannot finish inside 10 minutes of the ticket's arrival is started and nothing that finishes late is posted,
a flood from one tenant or a crash cannot block the queue; fails_when=two passes both generate, a security or
fulfilment ticket waits behind a generation, a generation starts after the deadline or past it, a late answer
is posted, the 11th ticket of a tenant or the 31st overall waits, a crashed job stays running forever, a desk
that is off or stopped notifies anyone, or a missing model leaves tickets queued; no_claim=the real speed of a
CPU (an operator step) and the live database.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import distributed_lock
from service_desk import CALL_TIMEOUT_MAX, QUEUE_DEADLINE, pipeline, runtime, store, worker
from service_desk.model import OllamaClient
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.service_desk_worker_support import (NOW, Clock, _desk_env, add_tenant, generates, job, kinds, queue,  # noqa: F401
                                               rows, stand_in, stored, world)


async def run(db, clock=None, **stand):
    stand_up, calls = stand_in(**stand)
    counts = await worker.run_once(db, client=OllamaClient(transport=stand_up), clock=clock or Clock())
    return counts, calls


async def measure(db, *, gen_tps, load=20):
    """The operator's measurement with a prefill so fast that the estimate is 220 / gen_tps + load seconds."""
    await runtime.save_measurement(db, {"prefillTps": 1e9, "genTps": gen_tps, "loadSeconds": load})


# ---------------------------------------------------------------- one runner, cheap stages first

async def test_a_second_runner_gets_none_and_only_one_generation_is_made(world):
    ticket, job_id = await queue(world, 1)

    async def slow():
        await asyncio.sleep(0.3)
    stand_up, calls = stand_in(on_generate=slow)
    first, second = await asyncio.gather(
        worker.run_once(world, client=OllamaClient(transport=stand_up), clock=Clock()),
        worker.run_once(world, client=OllamaClient(transport=stand_up), clock=Clock()))
    assert sorted(r is None for r in (first, second)) == [False, True]
    assert len(generates(calls)) == 1
    assert (await job(world, job_id))["state"] == "done"


async def test_cheap_stages_run_for_every_job_before_the_one_generation(world):
    a, job_a = await queue(world, 1, arrived=NOW - timedelta(minutes=3), title="I think I clicked a phishing link")
    b, job_b = await queue(world, 2, arrived=NOW - timedelta(minutes=2), title="VPN will not connect",
                           description="My company's VPN app says the connection failed and keeps dropping")
    c, job_c = await queue(world, 3, arrived=NOW - timedelta(minutes=1), type="feature")
    counts, calls = await run(world)
    assert len(generates(calls)) == 1
    assert (await job(world, job_a))["reason"] == "security_topic"
    assert (await job(world, job_c))["reason"] == "fulfilment_request"
    assert (await job(world, job_b))["reason"] in ("posted", "drafted")
    assert (await stored(world, a))["desk"]["phase"] == "handed_off"
    assert (await stored(world, c))["desk"]["phase"] == "handed_off"
    assert counts["jobs"] == [job_a, job_b, job_c] or counts["jobs"] == [job_a, job_c, job_b]


async def test_jobs_are_taken_in_arrival_order_and_only_the_oldest_ready_one_is_generated(world):
    _, newer = await queue(world, 1, arrived=NOW - timedelta(minutes=1))
    _, older = await queue(world, 2, arrived=NOW - timedelta(minutes=4))
    _, calls = await run(world)
    assert len(generates(calls)) == 1
    assert (await job(world, older))["state"] == "done" and (await job(world, newer))["state"] == "ready"
    _, calls = await run(world)                        # the next pass answers the one that was waiting
    assert len(generates(calls)) == 1 and (await job(world, newer))["state"] == "done"


# ---------------------------------------------------------------- D-21: the 10-minute limit

async def test_a_ticket_that_arrived_ten_minutes_ago_is_never_generated_for(world):
    """protects=PROH-85-09: exactly at the deadline counts as passed; fails_when=a generate request is sent."""
    ticket, job_id = await queue(world, 1, arrived=NOW - QUEUE_DEADLINE)
    _, calls = await run(world)
    assert generates(calls) == []
    done = await job(world, job_id)
    assert (done["state"], done["reason"]) == ("done", "service_desk_busy")
    assert (await stored(world, ticket))["desk"]["lastReason"] == "service_desk_busy"
    assert "ai_answer" not in kinds(await stored(world, ticket))


async def test_a_ticket_one_second_inside_the_limit_is_still_answered(world):
    _, job_id = await queue(world, 1, arrived=NOW - QUEUE_DEADLINE + timedelta(seconds=300))
    await measure(world, gen_tps=22)
    _, calls = await run(world)
    assert len(generates(calls)) == 1 and (await job(world, job_id))["reason"] in ("posted", "drafted")


async def test_no_generation_starts_that_cannot_finish_in_time(world):
    """protects=D-21: 9 minutes in, an expected 120 s call would end after the limit; 30 s would not."""
    await measure(world, gen_tps=2.2, load=20)                       # 100 s + 20 s
    ticket, slow = await queue(world, 1, arrived=NOW - timedelta(minutes=9))
    _, calls = await run(world)
    assert generates(calls) == [] and (await job(world, slow))["reason"] == "service_desk_busy"
    await measure(world, gen_tps=22, load=20)                        # 10 s + 20 s
    _, quick = await queue(world, 2, arrived=NOW - timedelta(minutes=9))
    _, calls = await run(world)
    [sent] = generates(calls)
    assert sent["read"] <= 60 and (await job(world, quick))["reason"] in ("posted", "drafted")


async def test_the_call_timeout_is_cut_to_the_time_left(world):
    await measure(world, gen_tps=22, load=5)
    await queue(world, 1, arrived=NOW - QUEUE_DEADLINE + timedelta(seconds=30))
    _, calls = await run(world)
    [sent] = generates(calls)
    assert sent["read"] == pytest.approx(30.0, abs=0.01)


async def test_an_answer_that_comes_back_after_the_limit_is_never_posted(world):
    """protects=T-85-66 / PROH-85-09: fails_when=a late reply becomes a comment or a draft."""
    clock = Clock()
    ticket, job_id = await queue(world, 1, arrived=NOW - timedelta(minutes=5))

    async def slow():
        clock.at = NOW + timedelta(minutes=5)                          # the reply lands exactly at the limit
    _, calls = await run(world, clock, on_generate=slow)
    assert len(generates(calls)) == 1
    after = await stored(world, ticket)
    assert not {"ai_answer", "ai_draft"} & set(kinds(after)) and after["status"] == "open"
    assert (await job(world, job_id))["reason"] == "service_desk_busy"
    assert [r["command"] for r in await rows(world)] == ["ticket_handoff"]


# ---------------------------------------------------------------- caps, crashes, off, offline

async def test_the_eleventh_ticket_of_a_tenant_is_handed_off_at_once(world):
    ids = [(await queue(world, n, arrived=NOW - timedelta(minutes=2, seconds=-n)))[1] for n in range(1, 12)]
    _, calls = await run(world)
    assert len(generates(calls)) == 1
    assert (await job(world, ids[10]))["reason"] == "service_desk_busy"
    assert (await job(world, ids[10]))["state"] == "done"
    assert "service_desk_busy" not in [(await job(world, i))["reason"] for i in ids[:10]]


async def test_the_thirty_first_ticket_of_the_deployment_is_handed_off_at_once(world):
    ids = []
    for t, tenant in enumerate(("t1", "t2", "t3", "t4")):
        if tenant != "t1":
            await add_tenant(world, tenant)
        for k in range(8):
            n = t * 8 + k + 1
            ids.append((await queue(world, n, tenant=tenant, arrived=NOW - timedelta(minutes=2, seconds=-n)))[1])
    await run(world)
    busy = [i for i in ids if (await job(world, i))["reason"] == "service_desk_busy"]
    assert busy == ids[30:]


async def test_a_running_job_older_than_a_crashed_call_could_last_is_dropped_to_a_person(world):
    stale_ticket, stale = await queue(world, 1, arrived=NOW - timedelta(minutes=8))
    fresh_ticket, fresh = await queue(world, 2, arrived=NOW - timedelta(minutes=8))
    await store.jobs(world).update_one({"id": stale}, {"$set": {
        "state": "running", "startedAt": NOW - timedelta(seconds=CALL_TIMEOUT_MAX + 61)}})
    await store.jobs(world).update_one({"id": fresh}, {"$set": {
        "state": "running", "startedAt": NOW - timedelta(seconds=CALL_TIMEOUT_MAX - 100)}})
    counts, calls = await run(world)
    assert generates(calls) == []
    gone = await job(world, stale)
    assert (gone["state"], gone["reason"]) == ("dropped", "stale_running")
    assert gone["finishedAt"] is not None
    assert (await stored(world, stale_ticket))["desk"]["lastReason"] == "service_desk_busy"
    assert (await job(world, fresh))["state"] == "running" and "desk" in await stored(world, fresh_ticket)
    assert (await stored(world, fresh_ticket))["desk"]["phase"] == "queued"


async def test_a_stale_job_whose_ticket_was_already_answered_is_dropped_without_a_hand_off(world):
    ticket, stale = await queue(world, 1, arrived=NOW - timedelta(minutes=8))
    await store.jobs(world).update_one({"id": stale}, {"$set": {
        "state": "running", "startedAt": NOW - timedelta(seconds=CALL_TIMEOUT_MAX + 61)}})
    await world.tickets.update_one({"id": ticket["id"]}, {"$set": {"desk.phase": "posted"}})
    await run(world)
    assert (await job(world, stale))["state"] == "dropped" and await rows(world) == []
    assert kinds(await stored(world, ticket)) == []


async def test_a_job_picked_up_after_the_desk_was_switched_off_is_dropped_silently(world):
    ticket, job_id = await queue(world, 1)
    await world.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"serviceDesk": {"mode": "off"}}})
    _, calls = await run(world)
    gone = await job(world, job_id)
    assert (gone["state"], gone["reason"]) == ("dropped", "desk_off")
    assert calls == [] and await rows(world) == [] and (await stored(world, ticket))["comments"] == []


async def test_a_ticket_over_the_cap_of_a_tenant_whose_desk_is_off_is_dropped_silently(world):
    ids = [(await queue(world, n, arrived=NOW - timedelta(minutes=2, seconds=-n)))[1] for n in range(1, 12)]
    await world.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"serviceDesk": {"mode": "off"}}})
    await run(world)
    assert (await job(world, ids[10]))["reason"] == "desk_off" and await rows(world) == []


async def test_a_job_picked_up_during_a_stop_is_handed_off_without_a_notice(world):
    ticket, job_id = await queue(world, 1)
    await world.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"stop": {"active": True}}})
    _, calls = await run(world)
    assert calls == [] and (await job(world, job_id))["reason"] == "desk_stopped"
    assert "handoff_notice" not in kinds(await stored(world, ticket))


async def test_with_no_model_every_waiting_ticket_is_handed_off_in_one_pass(world):
    ids = [(await queue(world, n, arrived=NOW - timedelta(minutes=2, seconds=-n)))[1] for n in range(1, 5)]
    counts, calls = await run(world, fail_tags=True)
    assert generates(calls) == []
    assert [(await job(world, i))["reason"] for i in ids] == ["service_desk_offline"] * 4
    assert [(await job(world, i))["state"] for i in ids] == ["done"] * 4
    assert counts["handed_off"] == 4


async def test_a_pass_stops_when_the_lock_is_lost(world, monkeypatch):
    ids = [(await queue(world, n, arrived=NOW - timedelta(minutes=2, seconds=-n)))[1] for n in range(1, 4)]
    monkeypatch.setattr(worker, "LOCK_RENEW_EVERY", 0.01)

    async def refuse(*args, **kwargs):
        return False
    monkeypatch.setattr(distributed_lock, "renew_lock", refuse)
    real = pipeline.prepare

    async def slow_prepare(*args, **kwargs):
        await asyncio.sleep(0.1)
        return await real(*args, **kwargs)
    monkeypatch.setattr(pipeline, "prepare", slow_prepare)
    _, calls = await run(world)
    assert generates(calls) == []
    assert [(await job(world, i))["state"] for i in ids[1:]] == ["pending", "pending"]


# ---------------------------------------------------------------- timing and the finished state

async def test_a_finished_job_keeps_its_times_and_a_datetime_for_the_ttl(world):
    clock = Clock()
    _, job_id = await queue(world, 1, arrived=NOW - timedelta(minutes=5))

    async def slow():
        clock.advance(20)
    await run(world, clock, on_generate=slow)
    done = await job(world, job_id)
    assert isinstance(done["finishedAt"], datetime) and done["state"] == "done"
    assert done["waitSeconds"] == pytest.approx(300, abs=1) and done["runSeconds"] == pytest.approx(20, abs=1)


async def test_an_error_in_one_job_drops_it_and_the_pass_goes_on(world, monkeypatch):
    _, first = await queue(world, 1, arrived=NOW - timedelta(minutes=3))
    _, second = await queue(world, 2, arrived=NOW - timedelta(minutes=2))
    real = pipeline.prepare

    async def broken(db, job_doc, **kwargs):
        if job_doc["ticketId"] == "k1":
            raise RuntimeError("boom")
        return await real(db, job_doc, **kwargs)
    monkeypatch.setattr(pipeline, "prepare", broken)
    _, calls = await run(world)
    assert (await job(world, first))["reason"] == "error" and (await job(world, first))["state"] == "dropped"
    assert len(generates(calls)) == 1 and (await job(world, second))["state"] == "done"


async def test_an_empty_queue_is_an_empty_pass(world):
    counts, calls = await run(world)
    assert counts["jobs"] == [] and calls == []


# ---------------------------------------------------------------- migration 032 and the startup task

DESK_INDEXES = {
    "service_desk_jobs": {"one_attempt_per_ticket", "state_created", "finished_ttl"},
    "service_desk_gaps": {"tenant_status_created", "created_ttl"},
    "knowledge_docs": {"tenant_helpdesk", "one_starter_copy"},
    "tickets": {"tray_list", "desk_return_due"},
}


async def _counts(db):
    return {name: await db[name].count_documents({}) for name in
            ("tickets", "knowledge_docs", "autonomy_settings", "service_desk_jobs", "service_desk_gaps")}


async def test_migration_032_creates_every_desk_index_twice_and_changes_no_document(mongo_db):  # noqa: F811
    """protects=D-03 / D-11 (nothing backfilled: a missing serviceDesk setting reads Drafts, a missing comment
    visibility reads staff); fails_when=a document is inserted or changed, an index is missing, a second run raises."""
    import importlib
    migration = importlib.import_module("migrations.032_service_desk")
    await mongo_db.tickets.insert_one({"id": "k1", "tenantId": "t1", "comments": [{"id": "c1", "text": "old"}]})
    await mongo_db.knowledge_docs.insert_one({"id": "d1", "tenantId": "t1", "title": "x", "content": "y"})
    await mongo_db.autonomy_settings.insert_one({"tenantId": "t1", "level": "suggest"})
    before = await _counts(mongo_db)
    snapshot = [await mongo_db[c].find({}, {"_id": 0}).to_list(10) for c in ("tickets", "knowledge_docs", "autonomy_settings")]
    await migration.up(mongo_db)
    await migration.up(mongo_db)
    assert await _counts(mongo_db) == before
    assert snapshot == [await mongo_db[c].find({}, {"_id": 0}).to_list(10)
                        for c in ("tickets", "knowledge_docs", "autonomy_settings")]
    for collection, names in DESK_INDEXES.items():
        assert names <= set(await mongo_db[collection].index_information()), collection
    unique = (await mongo_db.service_desk_jobs.index_information())["one_attempt_per_ticket"]
    assert unique["unique"] is True and (await mongo_db.knowledge_docs.index_information())["one_starter_copy"]["unique"]


async def test_the_fixtures_and_the_worker_leave_out_the_90_day_ttl_indexes(world):
    """protects=WR-301 (rows stamped from the fixed test clocks must not be removed by the TTL monitor);
    fails_when=a fixture or the worker's own index check leaves finished_ttl or created_ttl in place."""
    await run(world)
    jobs = set(await world.service_desk_jobs.index_information())
    assert {"one_attempt_per_ticket", "state_created"} <= jobs and "finished_ttl" not in jobs
    assert "created_ttl" not in set(await world.service_desk_gaps.index_information())


def test_the_runner_finds_migration_032_and_it_follows_031():
    from migrations import runner
    found = dict(runner._discover_pending(set()))
    assert found["032"] == "032_service_desk" and "031" in found


def test_the_backend_starts_one_service_desk_task_after_the_patch_rollout_controller():
    """The startup is read, not run: the real backend is the user's restart."""
    source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app_startup.py"),
                  encoding="utf-8").read()
    assert source.count('name="service_desk_worker"') == 1 and source.count("service_desk.worker import desk_loop") == 1
    assert source.index('name="patch_rollout_controller"') < source.index('name="service_desk_worker"')
    assert '_safe_bg_task(_service_desk_loop(), "service_desk_worker")' in source
