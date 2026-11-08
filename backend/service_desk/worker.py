"""The desk's worker: one attempt on the oldest waiting ticket (DESK-05).

``run_once`` claims the single oldest pending job and runs it to its end; the job finishes ``done``
with the outcome as its reason, or ``dropped`` with reason ``error`` when something unexpected
happened. 85-17 adds the lock, the loop, the deadline and the queue caps.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from pymongo import ReturnDocument

from . import pipeline, store
from .model import OllamaClient

logger = logging.getLogger(__name__)


async def _finish(db, job_id: str, state: str, reason: Optional[str]) -> None:
    await store.jobs(db).update_one({"id": job_id},
                                    {"$set": {"state": state, "reason": reason, "finishedAt": datetime.now(timezone.utc)}})


async def run_once(db, *, client: Optional[OllamaClient] = None, now: Optional[datetime] = None) -> Optional[str]:
    """Run the oldest pending job. Returns its id, or None when nothing is waiting."""
    now = now or datetime.now(timezone.utc)
    job = await store.jobs(db).find_one_and_update(
        {"state": "pending"}, {"$set": {"state": "running", "startedAt": now}},
        sort=[("createdAt", 1), ("id", 1)], return_document=ReturnDocument.AFTER, projection={"_id": 0})
    if job is None:
        return None
    try:
        prepared, reason = await pipeline.prepare(db, job, now=now)
        if prepared is not None:
            reason = await pipeline.answer(db, prepared, client or OllamaClient(), now=now)
        await _finish(db, job["id"], "done", reason)
    except Exception as exc:
        logger.error("service_desk: job %s failed: %s", job["id"], exc)
        try:
            await _finish(db, job["id"], "dropped", "error")
        except Exception as finish_exc:
            logger.error("service_desk: job %s could not be closed: %s", job["id"], finish_exc)
    return job["id"]
