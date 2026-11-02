"""Super Admin Partners screen routes (Phase 87): /api/platform/partners.

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
    adminName: str = Field(..., min_length=1, max_length=100)
    adminEmail: str = Field(..., min_length=1, max_length=254)

    @field_validator("name", "adminName")
    @classmethod
    def _stripped(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class PartnerUpdate(BaseModel):
    """Only the fields sent are changed; an explicit null expiresAt clears the pool expiry."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    poolSize: Optional[int] = Field(None, ge=1, le=licensing.MAX_AGENTS_CEILING)
    expiresAt: Optional[datetime] = None
    screenCeiling: Optional[List[str]] = Field(None, max_length=300)


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
    """Appoint a partner with a seat pool, an optional expiry and a screen ceiling, and invite its first admin."""
    _require_super_admin(current_user)
    try:
        return await service.appoint(
            mongodb.db, name=data.name, pool_size=data.poolSize, expires_at=data.expiresAt,
            screen_ceiling=data.screenCeiling, admin_name=data.adminName, admin_email=data.adminEmail,
            actor=current_user,
        )
    except PartnerError as err:
        return error_response(err)


@router.patch("/{partner_id}")
async def update_partner(partner_id: str, data: PartnerUpdate, current_user=Depends(get_current_user)):
    """Change a partner's name, pool size, pool expiry or screen ceiling."""
    _require_super_admin(current_user)
    changes = {key: getattr(data, key) for key in data.model_fields_set
               if key == "expiresAt" or getattr(data, key) is not None}
    if not changes:
        raise HTTPException(status_code=400, detail="Nothing to update")
    try:
        return {"partner": await service.update_partner(mongodb.db, partner_id, changes=changes, actor=current_user)}
    except PartnerError as err:
        return error_response(err)
