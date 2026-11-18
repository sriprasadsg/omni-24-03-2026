"""SOC hunting routes (soc_hunt), under the Security Overview catalogue.

Running a hunt is a read (GET, view:security): the query travels as JSON in ``q``. Saving, changing and removing
hunts need what the catalogue's writes need (manage:security_cases or manage:settings); turning a hunt into a SIEM
rule changes what future events raise, so it also needs manage:automation, like the console's automation rules.
Every call works in the caller's scope (soc_endpoints.soc_scope).
"""
import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth_types import TokenData
from authentication_service import get_current_user
from catalogue_mounts_secops import SECURITY_GUARD
from database import get_database
from rbac_utils import require_permission, verify_permission
import soc_actions
import soc_hunt
from soc_endpoints import soc_scope

router = APIRouter(prefix="/api/security/soc/hunts", tags=["SOC"], dependencies=[Depends(SECURITY_GUARD)])
RULE_WRITE = [Depends(require_permission("manage:automation"))]


class HuntIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=500)
    query: Dict[str, Any]

    model_config = {"extra": "forbid"}


class RuleIn(BaseModel):
    name: Optional[str] = Field(None, max_length=120)
    severity: str = Field("Medium", max_length=10)
    count: int = Field(1, ge=1, le=1000)
    windowMinutes: int = Field(10, ge=1, le=1440)
    distinct: Optional[str] = Field(None, max_length=40)
    technique: Optional[str] = Field(None, max_length=80)
    alertNow: bool = False

    model_config = {"extra": "forbid"}


async def _run(coro):
    try:
        return await coro
    except soc_hunt.HuntError as e:
        raise HTTPException(status_code=e.status, detail=str(e))


@router.get("/fields")
async def hunt_fields(current_user: TokenData = Depends(get_current_user)):
    """What each source can be filtered and counted by, with its frequent values of the last 30 days."""
    return await soc_hunt.catalogue(get_database(), soc_scope(current_user))


@router.get("/run")
async def run_hunt(q: str = Query(..., max_length=8000), current_user: TokenData = Depends(get_current_user)):
    """Run an unsaved hunt: total, newest 100 rows, and the top groups when it counts by a field."""
    try:
        query = json.loads(q)
    except ValueError:
        raise HTTPException(status_code=400, detail="q must be a JSON hunt query")
    return await _run(soc_hunt.run(get_database(), soc_scope(current_user), query))


@router.get("")
async def list_hunts(current_user: TokenData = Depends(get_current_user)):
    return {"items": await soc_hunt.list_hunts(get_database(), soc_scope(current_user)),
            "canEdit": await verify_permission(current_user, "manage:security_cases")
            or await verify_permission(current_user, "manage:settings"),
            "canMakeRules": await verify_permission(current_user, "manage:automation")}


@router.post("")
async def save_hunt(body: HuntIn, current_user: TokenData = Depends(get_current_user)):
    scope = soc_scope(current_user)
    out = await _run(soc_hunt.save(get_database(), scope, body.model_dump(), current_user.username))
    await soc_actions._audit("soc.hunt.create", scope, current_user, huntId=out["id"], name=out["name"])
    return out


@router.put("/{hunt_id}")
async def update_hunt(hunt_id: str, body: HuntIn, current_user: TokenData = Depends(get_current_user)):
    scope = soc_scope(current_user)
    out = await _run(soc_hunt.save(get_database(), scope, body.model_dump(), current_user.username, hunt_id[:64]))
    await soc_actions._audit("soc.hunt.update", scope, current_user, huntId=out["id"], name=out["name"])
    return out


@router.delete("/{hunt_id}")
async def delete_hunt(hunt_id: str, current_user: TokenData = Depends(get_current_user)):
    scope = soc_scope(current_user)
    await _run(soc_hunt.delete(get_database(), scope, hunt_id[:64]))
    await soc_actions._audit("soc.hunt.delete", scope, current_user, huntId=hunt_id[:64])
    return {"success": True}


@router.get("/{hunt_id}/run")
async def rerun_hunt(hunt_id: str, current_user: TokenData = Depends(get_current_user)):
    """Run a saved hunt again; its last run time and count are kept with it."""
    return await _run(soc_hunt.rerun(get_database(), soc_scope(current_user), hunt_id[:64]))


@router.post("/{hunt_id}/rule", dependencies=RULE_WRITE)
async def hunt_to_rule(hunt_id: str, body: RuleIn = Body(...), current_user: TokenData = Depends(get_current_user)):
    """Make a SIEM rule from a saved hunt over SIEM events; it records hits for 7 days unless alertNow."""
    scope = soc_scope(current_user)
    out = await _run(soc_hunt.to_rule(get_database(), scope, hunt_id[:64], body.model_dump(), current_user.username))
    await soc_actions._audit("soc.hunt.rule", scope, current_user, huntId=hunt_id[:64], ruleId=out["id"],
                             mode=out["mode"], logSource=out["logSource"])
    return out
