"""
Password reset endpoints: request and confirm flows.
Routes are mounted under /api/auth via the main authentication router.
"""

import datetime
import uuid
import logging
from datetime import timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from database import get_database
from auth_utils import hash_password, validate_password_complexity
from rate_limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


class PasswordResetRequest(BaseModel):
    email: str = Field(..., max_length=254)


class PasswordResetConfirm(BaseModel):
    token: str = Field(..., max_length=512)
    new_password: str = Field(..., max_length=1024)


# In-memory reset token store — replace with DB collection in production
_reset_tokens: dict[str, dict] = {}


@router.post("/reset-password/request")
@limiter.limit("3/minute")
async def request_password_reset(request: Request, response: Response, body: PasswordResetRequest):
    """Issue a password-reset token (send via email in production)."""
    db = get_database()
    user = await db._db.users.find_one({"email": body.email})
    # Always return 200 to prevent email enumeration
    if not user:
        return {"success": True, "message": "If that address is registered you will receive a reset link"}

    reset_token = uuid.uuid4().hex
    expires_at = datetime.datetime.now(timezone.utc) + timedelta(minutes=30)
    _reset_tokens[reset_token] = {"email": body.email, "expires_at": expires_at}

    # Persist to DB so token survives process restarts; fall back to in-memory dict
    try:
        await db._db.password_reset_tokens.insert_one({
            "token": reset_token,
            "email": body.email,
            "expires_at": expires_at.isoformat(),
        })
    except Exception as e:
        logger.warning("Failed to persist reset token to DB (using in-memory fallback): %s", e)

    logger.info("[PasswordReset] Token issued for %s", body.email)
    return {
        "success": True,
        "message": "If that address is registered you will receive a reset link",
    }


@router.post("/reset-password/confirm")
@limiter.limit("5/minute")
async def confirm_password_reset(request: Request, response: Response, body: PasswordResetConfirm):
    """Apply a new password using a valid reset token."""
    now = datetime.datetime.now(timezone.utc)
    entry = _reset_tokens.get(body.token)

    db = get_database()
    if not entry:
        try:
            db_token = await db._db.password_reset_tokens.find_one({"token": body.token})
            if db_token:
                expires_at = datetime.datetime.fromisoformat(db_token["expires_at"])
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                entry = {"email": db_token["email"], "expires_at": expires_at, "_from_db": True}
        except Exception as e:
            logger.warning("DB lookup for reset token failed (will reject as invalid): %s", e)

    if not entry:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    if now > entry["expires_at"]:
        _reset_tokens.pop(body.token, None)
        raise HTTPException(status_code=400, detail="Reset token has expired")

    complexity_error = validate_password_complexity(body.new_password)
    if complexity_error:
        raise HTTPException(status_code=400, detail=complexity_error)

    # ITAM-USR-03 Pitfall 4 / T-64-12: local password changes are blocked
    # for LDAP-sourced users — LDAP is the source of truth for their
    # credentials, so a self-service reset here would silently desync it.
    target_user = await db._db.users.find_one({"email": entry["email"]}, {"source": 1})
    if target_user and target_user.get("source") == "ldap":
        raise HTTPException(
            status_code=403,
            detail="Password resets for LDAP-sourced accounts must be performed in the directory, not via this form",
        )

    # Consume the token BEFORE updating the password so concurrent requests
    # cannot both pass validation and race to overwrite each other's new password.
    _reset_tokens.pop(body.token, None)
    try:
        deleted = await db._db.password_reset_tokens.find_one_and_delete({"token": body.token})
        if not deleted and entry.get("_from_db"):
            raise HTTPException(status_code=400, detail="Reset token has already been used")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete consumed reset token from DB: %s", e)

    hashed = hash_password(body.new_password)
    await db._db.users.update_one(
        {"email": entry["email"]},
        {"$set": {"password": hashed}},
    )
    return {"success": True, "message": "Password updated successfully"}
