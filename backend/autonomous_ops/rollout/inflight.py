"""Work in flight must end (Phase 84, gap plan 84-27: WR-02, WR-03, WR-06).

An instruction a rollout sent can be answered, refused, left unread past its expiry, answered FAILURE, or never
answered at all. ``instruction_outcome`` reads one instruction document and says which, so settle (installs) and
revert (undo) end the work the same way instead of waiting for ever:

* ``not_delivered``: refused or cancelled, or still ``pending`` (nobody fetched it) after its own ``expiresAt``. The
  computer never had the step; it is tried again (not a failure of the computer, D-04). A ``sent`` instruction was
  fetched, so it is never "not delivered": the agent may be running it, and only ``RESULT_DEADLINE`` ends the wait.
* ``failed``: the agent answered FAILURE or error.
* ``no_result``: fetched (``sent``) or accepted, no result, and ``RESULT_DEADLINE`` has passed since the poll route
  stamped ``sent_at`` (or since the agent's accept, when there is one). The clock never runs for a ``pending``
  instruction: an undo has no ``expiresAt``, and a computer that is offline has not been asked yet (WR-27).
* ``done``: the agent answered SUCCESS; the result itself is read from the host's job, so this still waits.
* ``pending``: anything else; keep waiting.

A row left ``dispatching`` with no instruction for ``DISPATCH_CLAIM_BOUND`` was claimed by a process that died or raised
before it wrote the instruction; ``settle.recover_unsent`` ends it. ``close_job`` ends a patch job nobody will answer, so the
computer does not read busy for ever (``start._busy_agents`` and the dispatcher's busy check skip jobs that are not
In Progress).

Raw Mongo handle with an explicit tenantId only. Reads the queue; its one write is ``cancel_unfetched``, which only
ever turns a ``pending`` instruction into ``cancelled``.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from ..scope import raw
from . import store

logger = logging.getLogger(__name__)

# Claude's discretion (plan 84-27): Linux installs run up to 30 minutes per package, so a delivered install that has
# not answered after 6 hours is gone; a rollout row claimed for dispatch that has no instruction after 10 minutes is
# a crashed claim.
RESULT_DEADLINE = timedelta(hours=6)
DISPATCH_CLAIM_BOUND = timedelta(minutes=10)

NOT_DELIVERED_STATES = ("refused", "cancelled_by_stop", "cancelled")
_FAILED_STATES = ("failure", "error")
_TASK_FIELDS = {"_id": 0, "status": 1, "expiresAt": 1, "sent_at": 1, "updated_at": 1, "created_at": 1, "result": 1}


async def load_instruction(db, tenant_id: str, instruction_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """The fields of one instruction that decide its outcome, or None when there is none."""
    if not instruction_id:
        return None
    return await raw(db).agent_instructions.find_one({"id": instruction_id, "tenantId": tenant_id}, _TASK_FIELDS)


def status_of(task: Optional[Dict[str, Any]]) -> str:
    status = (task or {}).get("status")
    return status.strip().lower() if isinstance(status, str) else ""


def instruction_outcome(task: Optional[Dict[str, Any]], now: datetime, dispatched: Any = None) -> str:
    """``pending`` | ``not_delivered`` | ``failed`` | ``no_result`` | ``done`` for one instruction document (or
    None). ``dispatched`` is when the row was sent, used when the instruction records no fetch time."""
    task = task if isinstance(task, dict) else {}
    status = status_of(task)
    now = store.aware(now)
    if status in NOT_DELIVERED_STATES:
        return "not_delivered"
    if status in _FAILED_STATES:
        return "failed"
    if status == "pending":
        expires = store.parse_time(task.get("expiresAt"))
        return "not_delivered" if expires is not None and expires <= now else "pending"      # delivery refuses it after the expiry
    # The poll route stamps ``sent_at`` when the agent fetches; an accepted instruction's ``updated_at`` is its accept time.
    accepted = store.parse_time(task.get("updated_at")) if status == "accepted" else None
    began = (accepted or store.parse_time(task.get("sent_at")) or store.parse_time(dispatched)
             or store.parse_time(task.get("created_at")))
    if began is not None and began + RESULT_DEADLINE <= now:
        return "no_result"
    return "done" if status == "success" else "pending"


def failure_words(task: Optional[Dict[str, Any]], fallback: str) -> str:
    """What the agent said when it answered FAILURE (bounded), else ``fallback``."""
    result = (task or {}).get("result")
    result = result if isinstance(result, dict) else {}
    for key in ("error", "message"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:500]
    return fallback


async def close_job(db, tenant_id: str, job_id: Optional[str], now: datetime, reason: str) -> bool:
    """End a patch job nobody will answer: In Progress becomes Failed with one status line, so the computer never
    reads busy afterwards (WR-02). A job that already has a final status is left alone. Never raises."""
    if not job_id:
        return False
    stamp = store.aware(now).isoformat()
    try:
        done = await raw(db).patch_deployment_jobs.update_one(
            {"id": job_id, "tenantId": tenant_id, "status": "In Progress"},
            {"$set": {"status": "Failed", "progress": 100, "completedAt": stamp},
             "$push": {"statusLog": {"timestamp": stamp, "message": reason, "level": "error"}}})
    except Exception as exc:
        logger.error("autonomous_ops: job %s was not closed: %s", job_id, exc)
        return False
    return done.modified_count > 0


async def cancel_unfetched(db, tenant_id: str, instruction_id: Optional[str], now: datetime) -> bool:
    """Abandon an instruction nobody fetched: ``pending`` becomes ``cancelled``, so a computer that comes back later
    can not run a step the platform has already given up on (WR-27). One compare-and-set on the status: an instruction
    the agent fetched in the meantime is left alone. Never raises."""
    if not instruction_id:
        return False
    try:
        done = await raw(db).agent_instructions.update_one(
            {"id": instruction_id, "tenantId": tenant_id, "status": "pending"},
            {"$set": {"status": "cancelled", "error": "rollout_abandoned", "cancelled_at": store.aware(now).isoformat()}})
    except Exception as exc:
        logger.error("autonomous_ops: instruction %s was not cancelled: %s", instruction_id, exc)
        return False
    return done.modified_count > 0
