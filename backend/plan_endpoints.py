"""Super Admin Plans routes (Phase 88, D-14): /api/platform/plans.

The mounted ``tenantManagement`` catalogue guard checks ``manage:tenants``; each handler also checks the
Super Admin role itself, so the routes stay closed if the guard is ever unmounted. Raw database handle only;
no tenant context is switched. A seats edit is applied at once to the direct tenants on that plan; screens and
trial-days edits only shape what comes next (plan_service.update_plan).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt

import licensing
import plan_service
from authentication_service import get_current_user
from database import mongodb
from rbac_utils import is_super_admin

router = APIRouter(prefix="/api/platform/plans", tags=["Plans"])


class PlanUpdate(BaseModel):
    """Only the fields sent are changed. Strict integers: a float, a boolean or a string is refused."""
    model_config = ConfigDict(extra="forbid")

    seats: Optional[StrictInt] = Field(None, ge=0, le=licensing.MAX_AGENTS_CEILING)
    trialDays: Optional[StrictInt] = Field(None, ge=1, le=365)
    screens: Optional[List[str]] = Field(None, max_length=plan_service.MAX_PLAN_SCREENS)


def _require_super_admin(user) -> None:
    if not is_super_admin(getattr(user, "role", "")):
        raise HTTPException(status_code=403, detail="Only the Super Admin edits plans")


@router.get("")
async def get_plans(current_user=Depends(get_current_user)):
    """The four plans in order, with seats, trial days, screens and how many tenants are on each."""
    _require_super_admin(current_user)
    return {"plans": await plan_service.list_plans(mongodb.db)}


@router.put("/{plan_key}")
async def put_plan(plan_key: str, data: PlanUpdate, current_user=Depends(get_current_user)):
    """Edit one plan's seats, trial days (Free) or screens; a seats edit reaches tenants without an override at once."""
    _require_super_admin(current_user)
    try:
        return await plan_service.update_plan(
            mongodb.db, plan_key, data.model_dump(exclude_unset=True), actor=current_user)
    except plan_service.PlanError as err:
        return JSONResponse(status_code=err.status,
                            content={"error": str(err), "code": err.code, "status_code": err.status})
