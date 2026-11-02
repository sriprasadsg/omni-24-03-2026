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


class MoveBody(BaseModel):
    """The target is required on purpose: ``null`` means direct, so an empty body must not mean it."""
    targetPartnerId: Optional[str] = Field(..., max_length=64)


def _require_super_admin(user) -> None:
    if not is_super_admin(getattr(user, "role", "")):
        raise HTTPException(status_code=403, detail="Only the Super Admin manages partners")


@router.get("")
async def list_partners(current_user=Depends(get_current_user)):
    """Every partner with its pool used and free."""
    _require_super_admin(current_user)
    return {"partners": await service.list_partners(mongodb.db)}


@router.get("/direct-customers")
async def get_direct_customers(current_user=Depends(get_current_user)):
    """Organizations with no partner, for the Add existing customer picker."""
    _require_super_admin(current_user)
    return {"customers": await service.direct_customers(mongodb.db)}


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


@router.post("/{partner_id}/suspend")
async def suspend_partner(partner_id: str, current_user=Depends(get_current_user)):
    """Lock a partner and sign out its people; its customers keep running."""
    _require_super_admin(current_user)
    try:
        return {"partner": await service.suspend(mongodb.db, partner_id, current_user)}
    except PartnerError as err:
        return error_response(err)


@router.post("/{partner_id}/reinstate")
async def reinstate_partner(partner_id: str, current_user=Depends(get_current_user)):
    """Lift a suspension."""
    _require_super_admin(current_user)
    try:
        return {"partner": await service.reinstate(mongodb.db, partner_id, current_user)}
    except PartnerError as err:
        return error_response(err)


@router.get("/{partner_id}/customers")
async def get_partner_customers(partner_id: str, current_user=Depends(get_current_user)):
    """One partner's customers: the same rows the partner sees."""
    _require_super_admin(current_user)
    try:
        return {"customers": await service.partner_customers(mongodb.db, partner_id)}
    except PartnerError as err:
        return error_response(err)


@router.post("/customers/{customer_id}/move")
async def move_customer(customer_id: str, data: MoveBody, current_user=Depends(get_current_user)):
    """Move a customer, with its seats, to another partner or to direct (null target)."""
    _require_super_admin(current_user)
    try:
        return {"customer": await service.move(mongodb.db, customer_id, data.targetPartnerId, current_user)}
    except PartnerError as err:
        return error_response(err)
