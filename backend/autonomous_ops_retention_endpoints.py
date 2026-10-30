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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import retention_gate
from autonomous_ops import ledger, views
from autonomous_ops_endpoints import _require_interactive_session, _unavailable
from autonomous_ops_platform_endpoints import _require_platform_autonomy_control
from database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/platform/autonomous-ops/retention", tags=["Autonomous Ops (platform)"])

STALE_REVIEW = ("The counts changed since you opened this review. Reload the review and check the new "
                "counts before confirming.")


class ConfirmBody(BaseModel):
    reviewToken: str = Field(..., min_length=1, max_length=128)


def _when(value) -> Any:
    return retention_gate.aware(value).isoformat() if isinstance(value, datetime) else value


def _item(row: Dict[str, Any]) -> Dict[str, Any]:
    return {**row, "countedAt": _when(row.get("countedAt"))}


@router.get("/review", summary="Retention counts waiting for confirmation")
async def get_review(
    user=Depends(_require_platform_autonomy_control),
    _session=Depends(_require_interactive_session),
):
    """The rows the nightly job only counted so far, largest count first, and the token that confirms them."""
    try:
        db = get_database()
        rows = await retention_gate.review_rows(db)
        countable = [r for r in rows if r["count"] is not None and not r["countError"]]
        return {
            "mode": "counting_only" if rows else "deleting_nightly",
            "reviewToken": retention_gate.review_token(rows),
            "totals": {"records": sum(r["count"] for r in countable),
                       "tenants": len({r["tenantId"] for r in countable}),
                       "rows": len(rows), "uncountable": len(rows) - len(countable)},
            "items": [_item(r) for r in rows],
            "total": len(rows),
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
        actor = await views.actor_for(db, await views.build_caller(user))
        now = datetime.now(timezone.utc)
        try:
            confirmed = await retention_gate.confirm(db, body.reviewToken, actor["username"], now)
        except retention_gate.StaleReview as exc:
            raise HTTPException(status_code=409, detail=STALE_REVIEW) from exc
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
