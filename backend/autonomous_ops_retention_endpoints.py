"""Retention review and confirmation for the Super Admin (Phase 82, plan 82-10, HEAL-06, D-18, D-19, D-20).

GET  /api/platform/autonomous-ops/retention/review   what the nightly job counted and is waiting to delete
POST /api/platform/autonomous-ops/retention/confirm  confirm every countable waiting row at once

Both routes need control:platform_autonomous_ops (held by the platform owner, never by Platform
Support or a tenant role) and an interactive sign-in. The confirm route carries the review token of the
rows the person looked at; if the waiting rows changed since (a recount, a new period) it answers 409
and changes nothing. Confirming deletes nothing itself: the next nightly run does.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import retention_gate
import retention_job
from autonomous_ops import ledger, views
from autonomous_ops.scope import raw
from autonomous_ops_endpoints import _require_interactive_session, _unavailable
from autonomous_ops_platform_endpoints import _require_platform_autonomy_control
from database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/platform/autonomous-ops/retention", tags=["Autonomous Ops (platform)"])

RUN_IN_PROGRESS = "A retention run is in progress. Confirm after it finishes."
NOTHING_TO_CONFIRM = "There are no counted rows to confirm yet."
REVIEW_INCOMPLETE = "Not every organization has been counted yet. Confirm after the next run."
STALE_REVIEW = ("The counts changed since you opened this review. Reload the review and check the new "
                "counts before confirming.")


class ConfirmBody(BaseModel):
    reviewToken: str = Field(..., min_length=1, max_length=128)


def _when(value) -> Any:
    return retention_gate.aware(value).isoformat() if isinstance(value, datetime) else value


def _item(row: Dict[str, Any]) -> Dict[str, Any]:
    return {**row, "countedAt": _when(row.get("countedAt"))}


async def _last_run(db):
    """The newest finished nightly run, for the card's Last run cell."""
    doc = await raw(db)[retention_gate.RUNS].find_one(
        {"trigger": "scheduled", "finishedAt": {"$exists": True}}, {"_id": 0}, sort=[("startedAt", -1)])
    if not doc:
        return None
    return {"at": _when(doc.get("finishedAt") or doc.get("startedAt")), "trigger": doc.get("trigger"),
            "counted": doc.get("counted", 0), "deleted": doc.get("deleted", 0), "tenants": doc.get("tenants", 0),
            "error": doc.get("error"), "stoppedEarly": bool(doc.get("stoppedEarly"))}


@router.get("/review", summary="Retention counts waiting for confirmation")
async def get_review(
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    user=Depends(_require_platform_autonomy_control),
    _session=Depends(_require_interactive_session),
):
    """The rows the nightly job only counted so far, largest count first (25 per page), the totals over
    every waiting row, and the token that confirms them. The token covers all rows, not only the page."""
    try:
        db = get_database()
        rows = await retention_gate.review_rows(db)
        countable = [r for r in rows if r["count"] is not None and not r["countError"]]
        running = await retention_job.run_in_progress(db)
        counted_yet = bool(await raw(db)[retention_gate.COUNTS].count_documents({}, limit=1)) \
            or await retention_gate.global_confirmed_at(db) is not None
        stamps = [retention_gate.aware(r["countedAt"]) for r in rows if isinstance(r.get("countedAt"), datetime)]
        page = rows[offset:offset + limit]
        return {
            "mode": "running" if running else "counting_only" if rows or not counted_yet else "deleting_nightly",
            "notCountedYet": not counted_yet,
            "nextRun": retention_job.next_scheduled(datetime.now(timezone.utc)).isoformat(),
            "lastRun": await _last_run(db),
            "incomplete": await retention_gate.incomplete_review(db),
            "countedAt": _when(max(stamps)) if stamps else None,
            "reviewToken": retention_gate.review_token(rows),
            "totals": {"records": sum(r["count"] for r in countable),
                       "tenants": len({r["tenantId"] for r in countable}),
                       "rows": len(rows), "uncountable": len(rows) - len(countable)},
            "items": [_item(r) for r in page],
            "total": len(rows),
            "nextOffset": offset + limit if offset + limit < len(rows) else None,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.post("/confirm", summary="Confirm deletion of the counted retention rows")
async def post_confirm(
    body: ConfirmBody,
    user=Depends(_require_platform_autonomy_control),
    _session=Depends(_require_interactive_session),
):
    """Confirm every countable waiting row the person reviewed; the next nightly run deletes them."""
    try:
        db = get_database()
        if await retention_job.run_in_progress(db):
            raise HTTPException(status_code=409, detail=RUN_IN_PROGRESS)
        actor = await views.actor_for(db, await views.build_caller(user))
        now = datetime.now(timezone.utc)
        try:
            confirmed = await retention_gate.confirm(db, body.reviewToken, actor["username"], now)
        except retention_gate.StaleReview as exc:
            raise HTTPException(status_code=409, detail=STALE_REVIEW) from exc
        except retention_gate.ReviewIncomplete as exc:
            raise HTTPException(status_code=409, detail=REVIEW_INCOMPLETE) from exc
        if not confirmed["rows"]:
            raise HTTPException(status_code=422, detail=NOTHING_TO_CONFIRM)
        try:
            await ledger.record_platform_health(
                db, uuid.uuid4().hex, "retention_confirmed",
                {"by": actor["display"], "records": confirmed["records"], "tenants": confirmed["tenants"],
                 "rows": confirmed["rows"]}, at=now, host=None, actor=actor)
        except Exception as exc:        # the confirmation is already stored in the gate; the row is the log
            logger.error("retention: confirmation row not recorded in Activity: %s", exc)
        return {"confirmed": confirmed}
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc
