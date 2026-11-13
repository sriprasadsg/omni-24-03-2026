"""Go-live checks for the Super Admin (Phase 86, plan 86-07, GATE-09, D-14, D-15).

GET  /api/platform/autonomous-ops/golive                   the five checks, every ticked organization and
                                                            whether its shadow mode can be lifted
POST /api/platform/autonomous-ops/golive/checks/{check_id}  record one live check with a note

Both routes need control:platform_autonomous_ops (held by the platform owner, never by Platform Support, a
tenant role or an API key) and an interactive sign-in. A record is added, never changed: recording a check
again keeps the earlier record and the newest one is shown. Each record is written to the platform audit
chain. The lift itself is PUT /tenants/{id}/shadow, which refuses until the checks and the observation
period are met.
"""
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StringConstraints

import audit_ledger
from autonomous_ops import PLATFORM_TENANT_ID, views
from autonomous_ops.reporting import GOLIVE_CHECK_IDS, NOTE_MAX, NOTE_MIN, golive
from autonomous_ops_endpoints import _require_interactive_session, _unavailable
from autonomous_ops_platform_endpoints import _require_platform_autonomy_control
from database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/platform/autonomous-ops/golive", tags=["Autonomous Ops (platform)"])

CheckId = Literal[GOLIVE_CHECK_IDS]


class CheckNote(BaseModel):
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=NOTE_MIN, max_length=NOTE_MAX)]


@router.get("", summary="Go-live checks and shadow observation for every organization")
async def get_golive(
    user=Depends(_require_platform_autonomy_control),
    _session=Depends(_require_interactive_session),
):
    """The five go-live checks (the newest record of each), how many are recorded, every organization with
    the Autonomous Ops screen ticked (its shadow flag, whole days observed, simulated actions, whether it can
    be lifted and why not), and the deployment-wide shadow switch. Super Admin only, interactive session."""
    try:
        return await golive.overview(get_database(), golive.clock())
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.post("/checks/{check_id}", status_code=201, summary="Record a go-live check")
async def post_check(
    check_id: CheckId,
    body: CheckNote,
    user=Depends(_require_platform_autonomy_control),
    _session=Depends(_require_interactive_session),
):
    """Records that a live check was done, with a note of 10 to 500 characters saying what was seen. The
    earlier record of the same check stays. Answers 422 for another check id or a note outside that range.
    Super Admin only, interactive session."""
    try:
        db = get_database()
        actor = await views.actor_for(db, await views.build_caller(user))
        record = await golive.record_check(db, check_id, body.note, actor, golive.clock())
        try:
            await audit_ledger.event(
                "autonomous_ops.golive_check_recorded", PLATFORM_TENANT_ID,
                actor={"email": getattr(user, "username", None), "role": getattr(user, "role", None),
                       "tenantId": getattr(user, "tenant_id", None)},
                checkId=check_id, note=record["note"], recordId=record["id"])
        except Exception as exc:        # the record is stored; the audit event is the second copy
            logger.error("autonomous_ops: go-live check %s was not written to the audit ledger: %s", check_id, exc)
        return record
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise _unavailable(exc) from exc
