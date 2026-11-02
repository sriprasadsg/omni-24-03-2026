"""Super Admin Partners screen routes (Phase 87): GET and POST /api/platform/partners.

The mounted ``partners`` catalogue guard checks ``manage:partners``; each handler also checks the
Super Admin role itself, so the routes stay closed if the guard is ever unmounted. Raw database
handle only; no tenant context is switched.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

import licensing
import partner_platform_service as service
from authentication_service import get_current_user
from database import mongodb
from partner_pool import PartnerError
from partner_store import error_response
from rbac_utils import is_super_admin

router = APIRouter(prefix="/api/platform/partners", tags=["Partners"])


class PartnerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    poolSize: int = Field(..., ge=1, le=licensing.MAX_AGENTS_CEILING)
    expiresAt: Optional[datetime] = None
    screenCeiling: List[str] = Field(default_factory=list, max_length=300)

    @field_validator("name")
    @classmethod
    def _stripped(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


def _require_super_admin(user) -> None:
    if not is_super_admin(getattr(user, "role", "")):
        raise HTTPException(status_code=403, detail="Only the Super Admin manages partners")


@router.get("")
async def list_partners(current_user=Depends(get_current_user)):
    """Every partner with its pool used and free."""
    _require_super_admin(current_user)
    return {"partners": await service.list_partners(mongodb.db)}


@router.post("", status_code=201)
async def create_partner(data: PartnerCreate, current_user=Depends(get_current_user)):
    """Appoint a partner with a seat pool, an optional expiry and a screen ceiling."""
    _require_super_admin(current_user)
    try:
        summary = await service.appoint(
            mongodb.db, name=data.name, pool_size=data.poolSize, expires_at=data.expiresAt,
            screen_ceiling=data.screenCeiling, actor=current_user,
        )
    except PartnerError as err:
        return error_response(err)
    return {"partner": summary}
