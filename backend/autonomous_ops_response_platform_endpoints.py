"""Autonomous Ops response settings, platform routes (Phase 83, plan 83-07, RESP-08, D-04, D-13).

GET /api/platform/autonomous-ops/response-settings        how the organizations are set
PUT /api/platform/autonomous-ops/.../bulk                 write twoSignal and/or blockHours to each one

Both routes need control:platform_autonomous_ops (the platform owner) and a signed-in session; an API key
and Platform Support are refused. "Every organization" is a write to each organization's own setting, so
an organization's administrator can change it back and there is only one value to read. Each write leaves
that organization its own control row and audit event naming the person. The platform organization is
never written. Watched services are per organization and are not accepted here (UI-SPEC R10).

A write that fails for one organization does not stop the others: the answer lists `failures`, and the
caller retries with `onlyTenants` naming only those.

This router sits outside every catalogue prefix and has no mount guard of its own.
"""
import logging
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StrictBool, StrictInt, StringConstraints

from autonomous_ops import PLATFORM_TENANT_ID, messages, response_settings, views
from autonomous_ops.scope import raw
from autonomous_ops_endpoints import _require_interactive_session, _unavailable
from autonomous_ops_platform_endpoints import _require_platform_autonomy_control
from database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/platform/autonomous-ops", tags=["Autonomous Ops (platform)"])

MAX_ONLY_TENANTS = 1000
TenantId = Annotated[str, StringConstraints(min_length=1, max_length=views.TENANT_ID_MAX)]


class BulkBody(BaseModel):
    """Which settings to write, and optionally which organizations. Watched services are not accepted."""
    model_config = {"extra": "forbid"}

    twoSignal: Optional[StrictBool] = None
    blockHours: Optional[StrictInt] = None
    onlyTenants: Optional[List[TenantId]] = None


async def _tenants(db) -> List[Dict[str, str]]:
    """Every organization except the platform one, in id order."""
    rows = []
    async for doc in raw(db).tenants.find({}, {"_id": 0, "id": 1, "name": 1}):
        if doc.get("id") and doc["id"] != PLATFORM_TENANT_ID:
            rows.append({"id": str(doc["id"]), "name": str(doc.get("name") or doc["id"])})
    return sorted(rows, key=lambda t: t["id"])


@router.get("/response-settings", summary="How the organizations' response settings are set")
async def get_response_settings(
    user=Depends(_require_platform_autonomy_control),
    _session=Depends(_require_interactive_session),
):
    """The number of organizations (not counting the platform organization) with the two-source rule on
    and off, and how many have each block length in hours. An organization whose stored settings cannot be
    read counts at the safe defaults and in `unreadable`."""
    try:
        db = get_database()
        on = off = unreadable = 0
        lengths: Dict[str, int] = {}
        tenants = await _tenants(db)
        for tenant in tenants:
            s = await response_settings.load(db, tenant["id"])
            on, off = (on + 1, off) if s.two_signal else (on, off + 1)
            lengths[str(s.block_hours)] = lengths.get(str(s.block_hours), 0) + 1
            unreadable += 0 if s.readable else 1
        return {"organizations": len(tenants), "twoSignal": {"on": on, "off": off}, "blockHours": lengths,
                "unreadable": unreadable}
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.put("/response-settings/bulk", summary="Apply response settings to every organization")
async def put_response_settings_bulk(
    body: BulkBody,
    user=Depends(_require_platform_autonomy_control),
    _session=Depends(_require_interactive_session),
):
    """Writes twoSignal and/or blockHours (1 to 168) to each organization's own setting, in id order.
    Answers 200 with `changed` (organizations written, including those already at the value) and
    `failures` ({tenantId, name, detail} for each one that could not be written; the others still
    changed). `onlyTenants` limits the write to those organizations, for a retry; naming the platform
    organization answers 409, and an unknown one is listed in `failures`. An empty body is 422."""
    values = body.model_dump(exclude_none=True, exclude={"onlyTenants"})
    try:
        cleaned = response_settings.validate_changes(values)
    except response_settings.SettingsError as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc
    try:
        db = get_database()
        tenants = await _tenants(db)
        if body.onlyTenants is not None:
            wanted = set(body.onlyTenants)
            if PLATFORM_TENANT_ID in wanted:
                raise HTTPException(status_code=409, detail=messages.API_DETAIL["platform_tenant"])
            known = {t["id"] for t in tenants}
            unknown = sorted(wanted - known)         # e.g. deleted since the first attempt: reported, not fatal
            tenants = [t for t in tenants if t["id"] in wanted]
        caller = await views.build_caller(user)
        actor = await views.actor_for(db, caller)
        changed: List[str] = []
        failures: List[Dict[str, Any]] = [
            {"tenantId": t, "name": t, "detail": messages.API_DETAIL["organization_missing"]}
            for t in (unknown if body.onlyTenants is not None else [])]
        for tenant in tenants:
            try:
                await response_settings.save(db, tenant["id"], cleaned, actor=actor, scope="platform")
                changed.append(tenant["id"])
            except Exception as exc:               # one organization failing must not stop the rest
                logger.error("autonomous_ops: bulk response settings for %s failed: %s", tenant["id"], exc)
                failures.append({"tenantId": tenant["id"], "name": tenant["name"],
                                 "detail": messages.API_DETAIL["bulk_failed"]})
        return {"changed": changed, "failures": failures}
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc
