"""The desk's worker: one pass at a time, one generation at a time (DESK-05, D-21).

``run_once`` holds the single-runner lock (renewed while it works) and does four things in order:

1. A job left ``running`` by a crash (older than the longest call plus a minute) is dropped and its ticket goes
   to a person.
2. Every waiting job is prepared in arrival order, cheaply and without the model: the fixed rules, the stop, the
   English check and the article cut-off hand a sensitive, fulfilment or no-article ticket to a person at once,
   so it never waits behind a slow generation. A tenant's 11th waiting job and the deployment's 31st are handed
   to a person as "service desk busy" without being prepared.
3. A job whose arrival plus 10 minutes has passed, or for which now plus the expected call time would pass it,
   is handed off as busy. The model is never asked for an answer that cannot be ready in time.
4. The oldest job that can still finish is answered (``pipeline.answer``), with the call timeout cut to the time
   left. An answer that comes back at or after the limit is never posted: the ticket goes to a person.

With the model absent every waiting ticket is handed off as "service desk offline" in the same pass, so
nothing queues forever. Every read and write goes through the raw handle with an explicit tenantId.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional

from pymongo import ReturnDocument

import distributed_lock
from autonomous_ops.scope import raw

from . import (CALL_TIMEOUT_MAX, DEFAULT_CALL_TIMEOUT, GLOBAL_QUEUE_CAP, HANDOFF_REASONS, LOCK_RENEW_EVERY,
               LOCK_TTL_SECONDS, NUM_PREDICT, POLL_SECONDS, QUEUE_DEADLINE, TENANT_QUEUE_CAP, WORKER_LOCK, pipeline,
               runtime, settings, store)
from .model import ModelTimeout, OllamaClient
from .sanitize import build_prompt

logger = logging.getLogger(__name__)

STALE_RUNNING_SECONDS = CALL_TIMEOUT_MAX + 60
PASS_LIMIT = 200                          # waiting jobs looked at in one pass (the caps keep the real queue far smaller)
DROPPED_OUTCOMES = ("ticket_missing", "desk_off", "error", "stale_running")    # no answer and no hand-off to report
_REQUIRED_INDEXES = (("service_desk_jobs", "one_attempt_per_ticket"), ("knowledge_docs", "one_starter_copy"))


def _aware(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _deadline(job: Dict[str, Any], fallback: datetime) -> datetime:
    """The arrival of the ticket plus 10 minutes (a job with no readable arrival counts from now)."""
    return (_aware(job.get("createdAt")) or fallback) + QUEUE_DEADLINE


class _Bounded:
    """The model client as the pipeline sees it, with the queue limit enforced around the one call: the call
    never gets more time than is left, and a reply that arrives at or after the limit is refused as a timeout,
    which the pipeline turns into the busy hand-off (nothing late is ever posted)."""

    def __init__(self, client: OllamaClient, deadline: datetime, clock: Callable[[], datetime]):
        self._client, self._deadline, self._clock = client, deadline, clock

    @property
    def model(self) -> str:
        return self._client.model

    async def available(self) -> bool:
        return await self._client.available()

    async def generate(self, system: str, prompt: str, *, num_predict: int = NUM_PREDICT,
                       timeout: float = DEFAULT_CALL_TIMEOUT):
        left = (self._deadline - self._clock()).total_seconds()
        if left <= 0:
            raise ModelTimeout("the queue limit had already passed")
        reply = await self._client.generate(system, prompt, num_predict=num_predict, timeout=min(timeout, left))
        if self._clock() >= self._deadline:
            raise ModelTimeout("the answer came after the queue limit")
        return reply


async def _end(db, job: Dict[str, Any], outcome: str, now: datetime, counts: Dict[str, Any],
               started: Optional[datetime] = None) -> None:
    """Close the job: ``done`` with the outcome as its reason, or ``dropped`` when nothing was answered or handed
    off. Keeps how long it waited and how long it ran, and ``finishedAt`` as a datetime for the TTL."""
    created = _aware(job.get("createdAt"))
    fields: Dict[str, Any] = {"state": "dropped" if outcome in DROPPED_OUTCOMES else "done", "reason": outcome,
                              "finishedAt": now}
    if created:
        fields["waitSeconds"] = round(((started or now) - created).total_seconds(), 3)
    if started:
        fields["runSeconds"] = round((now - started).total_seconds(), 3)
    await store.jobs(db).update_one({"id": job["id"]}, {"$set": fields})
    counts["jobs"].append(job["id"])
    counts["dropped" if fields["state"] == "dropped" else "handed_off" if outcome in HANDOFF_REASONS
           else "answered"] += 1


async def _to_a_person(db, job: Dict[str, Any], now: datetime, *, only_if_unanswered: bool = False) -> str:
    """The ticket goes to a person because the desk cannot answer in time: ``service_desk_busy``. Nothing is
    written when the ticket is gone or the desk is Off; during a stop it is the quiet ``desk_stopped``. With
    ``only_if_unanswered`` a ticket the desk already answered or handed off is left as it is."""
    tenant = job["tenantId"]
    ticket = await raw(db).tickets.find_one({"id": job.get("ticketId"), "tenantId": tenant}, {"_id": 0})
    if ticket is None:
        return "ticket_missing"
    if only_if_unanswered and (ticket.get("desk") or {}).get("phase") not in (None, "queued"):
        return "already_handled"
    if (await settings.load(db, tenant)).mode == "off":
        return "desk_off"
    if await pipeline._stopped(db, tenant):
        return await pipeline._handoff(db, ticket, "desk_stopped", now=now, notify_requester=False)
    return await pipeline._handoff(db, ticket, "service_desk_busy", now=now)


async def _recover_stale(db, now: datetime, counts: Dict[str, Any]) -> None:
    """A job still ``running`` long after any call could last belongs to a crashed runner: drop it and give its
    ticket to a person (unless the desk had already answered it)."""
    cutoff = now - timedelta(seconds=STALE_RUNNING_SECONDS)
    stale = await store.jobs(db).find({"state": "running", "startedAt": {"$lt": cutoff}}, {"_id": 0}) \
        .sort([("startedAt", 1), ("id", 1)]).to_list(PASS_LIMIT)
    for job in stale:
        try:
            await _to_a_person(db, job, now, only_if_unanswered=True)
            await _end(db, job, "stale_running", now, counts, started=_aware(job.get("startedAt")))
            counts["recovered"] += 1
        except Exception as exc:
            logger.error("service_desk: stale job %s could not be recovered: %s", job.get("id"), exc)


async def _fail(db, job: Dict[str, Any], clock: Callable[[], datetime], counts: Dict[str, Any], exc: Exception,
                started: Optional[datetime] = None) -> None:
    """An unexpected error on one job: log it, give the ticket to a person if the desk had not answered it, and
    drop the job. The pass goes on with the next job."""
    logger.error("service_desk: job %s failed: %s", job.get("id"), exc)
    try:
        await _to_a_person(db, job, clock(), only_if_unanswered=True)
    except Exception as handoff_exc:
        logger.error("service_desk: the ticket of job %s could not be handed off: %s", job.get("id"), handoff_exc)
    try:
        await _end(db, job, "error", clock(), counts, started=started)
    except Exception as finish_exc:
        logger.error("service_desk: job %s could not be closed: %s", job.get("id"), finish_exc)


async def _prepare_waiting(db, clock: Callable[[], datetime], lost: Callable[[], bool],
                           counts: Dict[str, Any]) -> List[pipeline.Prepared]:
    """Prepare every waiting job in arrival order. Returns the ones that still need the model, oldest first."""
    waiting = await store.jobs(db).find({"state": {"$in": ["pending", "ready"]}}, {"_id": 0}) \
        .sort([("createdAt", 1), ("id", 1)]).to_list(PASS_LIMIT)
    ready: List[pipeline.Prepared] = []
    per_tenant: Dict[str, int] = {}
    total = 0
    for job in waiting:
        if lost():
            break
        now = clock()
        try:
            tenant = job["tenantId"]
            if per_tenant.get(tenant, 0) >= TENANT_QUEUE_CAP or total >= GLOBAL_QUEUE_CAP \
                    or now >= _deadline(job, now):
                await _end(db, job, await _to_a_person(db, job, now), now, counts)
                continue
            per_tenant[tenant] = per_tenant.get(tenant, 0) + 1
            total += 1
            prepared, outcome = await pipeline.prepare(db, job, now=now)
            if prepared is None:
                await _end(db, job, outcome, clock(), counts)
                continue
            await store.jobs(db).update_one({"id": job["id"], "state": {"$in": ["pending", "ready"]}},
                                            {"$set": {"state": "ready"}})
            ready.append(prepared)
        except Exception as exc:
            await _fail(db, job, clock, counts, exc)
    counts["prepared"] = len(ready)
    return ready


async def _answer_oldest(db, client: OllamaClient, clock: Callable[[], datetime], lost: Callable[[], bool],
                         ready: List[pipeline.Prepared], counts: Dict[str, Any]) -> None:
    """With the model offline every ready job is handed off now; otherwise the oldest one that can finish before
    its limit is answered (one generation per pass) and the ones that cannot are handed off busy."""
    if not ready:
        return
    offline = not await client.available()
    measurement = None if offline else await runtime.load_measurement(db)
    recent = None if offline else await runtime.recent_gen_ms(db)
    for prepared in ready:
        if lost():
            return
        job, now = prepared.job, clock()
        try:
            if offline:
                await _end(db, job, await pipeline.answer(db, prepared, client, now=now), clock(), counts)
                continue
            system, prompt = build_prompt(prepared.ticket.get("title"), prepared.ticket.get("description"),
                                          prepared.matches)
            expected = runtime.estimate_seconds(len(system) + len(prompt), NUM_PREDICT, measurement, recent)
            deadline = _deadline(job, now)
            if now + timedelta(seconds=expected) >= deadline:        # it cannot finish in time: never start it
                await _end(db, job, await _to_a_person(db, job, now), now, counts)
                continue
            claimed = await store.jobs(db).find_one_and_update(
                {"id": job["id"], "state": {"$in": ["pending", "ready"]}},
                {"$set": {"state": "running", "startedAt": now}}, return_document=ReturnDocument.AFTER,
                projection={"_id": 0})
            if claimed is None:
                continue
        except Exception as exc:
            await _fail(db, job, clock, counts, exc)
            continue
        try:
            outcome = await pipeline.answer(db, prepared, _Bounded(client, deadline, clock), now=now)
            await _end(db, claimed, outcome, clock(), counts, started=now)
            counts["generated"] += 1
        except Exception as exc:
            await _fail(db, claimed, clock, counts, exc, started=now)
        return


async def _indexes_ready(db) -> bool:
    """A missing required index is made again (what migration 032 does). When that fails the pass must not run
    unprotected: a second job for one ticket or a second starter copy would be possible."""
    try:
        for collection, name in _REQUIRED_INDEXES:
            if name not in await raw(db)[collection].index_information():
                await store.ensure_indexes(db)
                break
        return True
    except Exception as exc:
        logger.error("service_desk: the pass was skipped, the unique indexes it relies on are missing and could "
                     "not be made: %s", exc)
        return False


def _clock(now: Optional[datetime], clock: Optional[Callable[[], datetime]]) -> Callable[[], datetime]:
    if clock is not None:
        return clock
    if now is not None:
        fixed = _aware(now)
        return lambda: fixed
    return lambda: datetime.now(timezone.utc)


async def run_once(db, *, client: Optional[OllamaClient] = None, now: Optional[datetime] = None,
                   clock: Optional[Callable[[], datetime]] = None) -> Optional[Dict[str, Any]]:
    """One pass under the single-runner lock. None when another runner holds it; otherwise the counts of the
    pass (``jobs`` lists every job closed, in order). ``clock`` (a function returning the current time) is
    what tests move; ``now`` alone fixes the time."""
    clock = _clock(now, clock)
    counts: Dict[str, Any] = {"jobs": [], "prepared": 0, "generated": 0, "handed_off": 0, "answered": 0,
                              "dropped": 0, "recovered": 0}
    lock_db = SimpleNamespace(_db=raw(db))              # distributed_lock reads db._db
    async with distributed_lock.lock_with_renewal(lock_db, WORKER_LOCK, ttl_seconds=LOCK_TTL_SECONDS,
                                                  renew_every=LOCK_RENEW_EVERY) as handle:
        if not handle.acquired:
            return None
        if not await _indexes_ready(db):
            return counts
        lost = lambda: handle.lost                      # noqa: E731
        await _recover_stale(db, clock(), counts)
        ready = await _prepare_waiting(db, clock, lost, counts)
        await _answer_oldest(db, client or OllamaClient(), clock, lost, ready, counts)
    return counts


async def desk_loop(get_db: Optional[Callable[[], Any]] = None, sleep=asyncio.sleep) -> None:
    """Run a pass every POLL_SECONDS. A failing pass is logged and the loop goes on."""
    if get_db is None:
        from database import get_database as get_db
    while True:
        try:
            counts = await run_once(get_db())
            if counts and counts["jobs"]:
                logger.info("service_desk: pass %s", {k: v for k, v in counts.items() if k != "jobs"})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("service_desk: pass failed: %s", exc)
        await sleep(POLL_SECONDS)
