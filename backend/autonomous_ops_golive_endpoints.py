"""Go-live checks for the Super Admin (Phase 86, plan 86-07, GATE-09, D-14, D-15).

GET  /api/platform/autonomous-ops/golive                   the five checks, every ticked organization and
                                                            whether its shadow mode can be lifted
POST /api/platform/autonomous-ops/golive/checks/{check_id}  record one live check with a note
POST   /api/platform/autonomous-ops/golive/test-organization  mark the one go-live test organization (D-23)
DELETE /api/platform/autonomous-ops/golive/test-organization  clear that mark

All routes need control:platform_autonomous_ops (held by the platform owner, never by Platform Support, a
tenant role or an API key) and an interactive sign-in. A record is added, never changed: recording a check
again keeps the earlier record and the newest one is shown. Each record is written to the platform audit
chain. The lift itself is PUT /tenants/{id}/shadow, which refuses until the checks and the observation
period are met, except for the go-live test organization: one ticked organization, named by typing its
name, may leave shadow mode without them so the live checks can be walked. Only one can be marked, never the
platform organization, and the mark cannot be cleared while that organization is out of shadow mode. Marking
and clearing are written to the platform audit chain.
"""
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, StringConstraints

import audit_ledger
from autonomous_ops import PLATFORM_TENANT_ID, settings as ao_settings, sweep, views
from autonomous_ops.reporting import GOLIVE_CHECK_IDS, NOTE_MAX, NOTE_MIN, golive, golive_test_org
from autonomous_ops.scope import raw
from autonomous_ops_endpoints import _require_interactive_session, _unavailable
from autonomous_ops_platform_endpoints import _require_platform_autonomy_control
from database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/platform/autonomous-ops/golive", tags=["Autonomous Ops (platform)"])

CheckId = Literal[GOLIVE_CHECK_IDS]


class CheckNote(BaseModel):
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=NOTE_MIN, max_length=NOTE_MAX)]


class TestOrganization(BaseModel):
    tenantId: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=views.TENANT_ID_MAX)]
    confirmName: Annotated[str, StringConstraints(max_length=200)]


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


def _actor(user) -> dict:
    return {"email": getattr(user, "username", None), "role": getattr(user, "role", None),
            "tenantId": getattr(user, "tenant_id", None)}


async def _audit_test_org(action: str, user, tenant_id: str, name: str) -> None:
    """The platform-chain event for a mark or a clear. The stored change stands when the event fails."""
    try:
        await audit_ledger.event(action, PLATFORM_TENANT_ID, actor=_actor(user),
                                 organization=tenant_id, organizationName=name)
    except Exception as exc:
        logger.error("autonomous_ops: the go-live test organization change %s for %s was not written to the "
                     "audit ledger: %s", action, tenant_id, exc)


def _mark_payload(mark) -> dict:
    return {"id": mark.get("tenantId"), "name": mark.get("tenantName"),
            "markedBy": mark.get("markedBy"), "markedAt": mark.get("markedAt")}


@router.post("/test-organization", status_code=201, summary="Mark the go-live test organization")
async def post_test_organization(
    body: TestOrganization,
    user=Depends(_require_platform_autonomy_control),
    _session=Depends(_require_interactive_session),
):
    """Marks one ticked organization as the go-live test organization, which may leave shadow mode before
    the five checks are recorded and without the seven days. The caller types the organization's name as
    confirmation (422 when it differs after trimming). The platform organization answers 409, an unticked
    or unknown one 404, and marking while another organization is marked answers 409 naming it. Super Admin
    only, interactive session."""
    try:
        db = get_database()
        tenant_id = body.tenantId
        if tenant_id == PLATFORM_TENANT_ID:
            raise HTTPException(status_code=409, detail="The platform organization can't be the test organization.")
        tenant = await raw(db).tenants.find_one({"id": tenant_id}, {"_id": 0, "name": 1})
        if tenant is None or tenant_id not in await sweep._ticked_tenants(db):
            raise HTTPException(status_code=404, detail="Organization not found")
        name = str(tenant.get("name") or tenant_id)
        if body.confirmName.strip() != name:
            raise HTTPException(status_code=422, detail="Type the organization's name exactly to confirm.")
        actor = await views.actor_for(db, await views.build_caller(user))
        try:
            mark = await golive_test_org.mark(db, tenant_id, name, actor, golive.clock())
        except golive_test_org.AlreadyMarked as exc:
            current = (exc.current or {}).get("tenantName") or "Another organization"
            raise HTTPException(status_code=409, detail=f"{current} is already the test organization. "
                                                        "Clear that mark first.") from exc
        await _audit_test_org("autonomous_ops.golive_test_org_marked", user, tenant_id, name)
        return {"testOrganization": _mark_payload(mark)}
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.delete("/test-organization", summary="Clear the go-live test organization")
async def delete_test_organization(
    tenantId: Annotated[str, Query(min_length=1, max_length=views.TENANT_ID_MAX)],
    user=Depends(_require_platform_autonomy_control),
    _session=Depends(_require_interactive_session),
):
    """Clears the mark. Answers 404 when this organization is not the test organization and 409 while its
    own shadow mode is off, changing nothing. Super Admin only, interactive session."""
    try:
        db = get_database()
        mark = await golive_test_org.current(db)
        if not mark or mark.get("tenantId") != tenantId:
            raise HTTPException(status_code=404, detail="That organization is not the test organization.")
        name = str(mark.get("tenantName") or tenantId)
        if (await ao_settings.load(db, tenantId)).shadow is not True:
            raise HTTPException(status_code=409, detail=f"Turn shadow mode back on for {name} first.")
        if await golive_test_org.clear(db, tenantId):
            await _audit_test_org("autonomous_ops.golive_test_org_cleared", user, tenantId, name)
        return {"testOrganization": None}
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc
