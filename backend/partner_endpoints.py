"""Partner portal routes (Phase 87): /api/partner.

Who the partner is: only the verified token's tenant, and only after that organization is confirmed
to be a partner (``type: "partner"``) and active. A partner id is never read from a path, a body or
a query string, and a Super Admin token gets 403 here (the portal is for partner accounts). The
mounted ``partnerPortal`` catalogue guard checks the permission; this module pins the partner.

``tenants`` is exempt from the tenant wrapper, so every read and write here uses the raw handle with
an explicit filter on the partner taken from the token, and answers with the D-01 allowlist only.
"""
from typing import List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

import licensing
import partner_portal_service as service
import rbac_defaults
from authentication_service import get_current_user
from database import mongodb
from partner_pool import PartnerError, _raw
from partner_store import error_response, find_partner

router = APIRouter(prefix="/api/partner", tags=["Partner portal"])

SUSPENDED_MESSAGE = "This partner account is suspended. Contact your platform administrator to restore access."


class CustomerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    seats: int = Field(..., ge=1, le=licensing.MAX_AGENTS_CEILING)
    enabledFeatures: Optional[List[str]] = Field(default=None, max_length=300)
    adminName: str = Field(..., min_length=1, max_length=100)
    adminEmail: str = Field(..., min_length=1, max_length=254)
    plan: Optional[str] = Field(None, max_length=32)

    @field_validator("name", "adminName")
    @classmethod
    def _stripped(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class SeatsBody(BaseModel):
    seats: int = Field(..., ge=0, le=licensing.MAX_AGENTS_CEILING)


class ColleagueInvite(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=1, max_length=254)
    role: Literal["partner_admin", "partner_viewer"]

    @field_validator("name")
    @classmethod
    def _stripped(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class FeaturesBody(BaseModel):
    enabledFeatures: List[str] = Field(..., max_length=300)


async def current_partner(current_user=Depends(get_current_user)) -> Tuple[object, dict]:
    """(user, partner organization) for a partner account, else 403."""
    if not rbac_defaults.is_partner_role(getattr(current_user, "role", None)):
        raise HTTPException(status_code=403, detail="The Partner portal is for partner accounts")
    partner = await find_partner(_raw(mongodb.db), getattr(current_user, "tenant_id", None))
    if partner is None or (partner.get("partner") or {}).get("status") != "active":
        raise HTTPException(status_code=403, detail=SUSPENDED_MESSAGE)
    return current_user, partner


def _is_partner_admin(user) -> bool:
    return rbac_defaults.canonical_key(rbac_defaults.normalize_role(getattr(user, "role", None))) \
        == rbac_defaults.PARTNER_ADMIN_KEY


def _require_partner_admin(user, what: str = "change the partner's customers") -> None:
    if not _is_partner_admin(user):
        raise HTTPException(status_code=403, detail=f"Only a partner admin can {what}")


@router.get("/overview")
async def get_overview(ctx=Depends(current_partner)):
    """The pool and, per customer, seats and usage only (D-01, D-16)."""
    user, partner = ctx
    return await service.overview(mongodb.db, partner, "admin" if _is_partner_admin(user) else "viewer")


@router.post("/customers", status_code=201)
async def post_customer(data: CustomerCreate, ctx=Depends(current_partner)):
    """Create a customer organization with seats drawn from the partner's pool."""
    user, partner = ctx
    _require_partner_admin(user)
    try:
        return await service.create_customer(
            mongodb.db, partner, name=data.name, seats=data.seats, enabled_features=data.enabledFeatures,
            admin_name=data.adminName, admin_email=data.adminEmail, actor=user, plan=data.plan or "Free",
        )
    except PartnerError as err:
        return error_response(err)


@router.put("/customers/{customer_id}/seats")
async def put_customer_seats(customer_id: str, data: SeatsBody, ctx=Depends(current_partner)):
    """Change one customer's seats within the seats in use and the pool's free seats (D-06)."""
    user, partner = ctx
    _require_partner_admin(user)
    try:
        return await service.change_seats(mongodb.db, partner, customer_id, data.seats, user)
    except PartnerError as err:
        return error_response(err)


@router.get("/customers/{customer_id}/features")
async def get_customer_features(customer_id: str, ctx=Depends(current_partner)):
    """The customer's screens, this partner's ceiling and the screens kept beyond it."""
    _, partner = ctx
    try:
        return await service.customer_features(mongodb.db, partner, customer_id)
    except PartnerError as err:
        return error_response(err)


@router.put("/customers/{customer_id}/features")
async def put_customer_features(customer_id: str, data: FeaturesBody, ctx=Depends(current_partner)):
    """Tick the customer's screens, only within the ceiling (D-10)."""
    user, partner = ctx
    _require_partner_admin(user)
    try:
        return await service.set_customer_features(mongodb.db, partner, customer_id, data.enabledFeatures, user)
    except PartnerError as err:
        return error_response(err)


@router.get("/team")
async def get_team(ctx=Depends(current_partner)):
    """The partner's own staff and whether each has set a password (partner admins only)."""
    user, partner = ctx
    _require_partner_admin(user, "see the partner's team")
    return await service.team(mongodb.db, partner)


@router.post("/team", status_code=201)
async def post_colleague(data: ColleagueInvite, ctx=Depends(current_partner)):
    """Invite a colleague into this partner as a partner admin or viewer."""
    user, partner = ctx
    _require_partner_admin(user, "invite colleagues")
    try:
        return await service.invite_colleague(mongodb.db, partner, name=data.name, email=data.email,
                                              role=data.role, actor=user)
    except PartnerError as err:
        return error_response(err)


@router.post("/team/{user_id}/resend")
async def post_resend_colleague(user_id: str, ctx=Depends(current_partner)):
    """Send a colleague who has not set a password a new link."""
    user, partner = ctx
    _require_partner_admin(user, "invite colleagues")
    try:
        return await service.resend_colleague(mongodb.db, partner, user_id, user)
    except PartnerError as err:
        return error_response(err)
