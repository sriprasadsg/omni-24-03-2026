"""
MFA Endpoints — /api/mfa/*
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from authentication_service import get_current_user, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from database import get_database
from datetime import timedelta
import mfa_service

router = APIRouter(prefix="/api/mfa", tags=["MFA"])


# ─── Request / Response Models ────────────────────────────────────────────────

class MFAVerifySetupRequest(BaseModel):
    totp_code: str

class MFAVerifyLoginRequest(BaseModel):
    session_token: str
    code: str
    use_backup_code: bool = False

class MFADisableRequest(BaseModel):
    totp_code: str


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/setup")
async def setup_mfa(current_user=Depends(get_current_user)):
    """
    Generate a TOTP secret and return it alongside a QR code for enrollment.
    Does NOT enable MFA yet — call /mfa/verify-setup with the first code to activate.
    """
    db = get_database()
    user = await db.users.find_one({"email": current_user.username})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Generate and persist pending secret (not active until confirmed)
    secret = mfa_service.generate_totp_secret()
    encrypted = mfa_service._encrypt_secret(secret)

    await db.users.update_one(
        {"email": current_user.username},
        {"$set": {"mfa.pending_secret": encrypted}}
    )

    uri = mfa_service.get_totp_provisioning_uri(current_user.username, secret)
    qr_base64 = mfa_service.generate_qr_base64(uri)

    return {
        "secret": secret,           # Show to user for manual entry
        "qr_uri": uri,             # otpauth:// URI
        "qr_base64": qr_base64,    # data:image/png;base64,... for <img> tag
        "app_name": mfa_service.APP_NAME,
    }


@router.post("/verify-setup")
async def verify_mfa_setup(req: MFAVerifySetupRequest, current_user=Depends(get_current_user)):
    """
    Confirm the first TOTP code from the authenticator app.
    Activates MFA on the account and returns 8 one-time backup codes.
    """
    result = await mfa_service.enroll_mfa(current_user.username, req.totp_code)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/verify")
async def verify_mfa_at_login(req: MFAVerifyLoginRequest):
    """
    Called during the second step of login (after password succeeds).
    Accepts the MFA session token from /auth/login plus a TOTP code (or backup code).
    Returns a full JWT access token on success.
    """
    if req.use_backup_code:
        email = mfa_service.validate_mfa_session(req.session_token)
        if not email:
            raise HTTPException(status_code=401, detail="MFA session expired or invalid")
        ok = await mfa_service.use_backup_code(email, req.code)
        if not ok:
            raise HTTPException(status_code=401, detail="Invalid or already-used backup code")
        mfa_service.consume_mfa_session(req.session_token)
    else:
        result = await mfa_service.verify_mfa_token(req.session_token, req.code)
        if not result["success"]:
            raise HTTPException(status_code=401, detail=result["error"])
        email = result["email"]

    # Fetch user and issue full JWT
    db = get_database()
    user = await db.users.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    role = user.get("role", "user")
    tenant_id = user.get("tenantId", "default")
    access_token = create_access_token(
        data={"sub": email, "role": role, "tenant_id": tenant_id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    user_data = {k: v for k, v in user.items() if k not in ("password", "_id", "mfa")}
    user_data["id"] = str(user.get("_id", ""))

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "success": True,
        "user": user_data,
    }


@router.post("/disable")
async def disable_mfa(req: MFADisableRequest, current_user=Depends(get_current_user)):
    """Disable MFA on the current user's account (requires valid TOTP code as confirmation)."""
    result = await mfa_service.disable_mfa(current_user.username, req.totp_code)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/status")
async def get_mfa_status(current_user=Depends(get_current_user)):
    """Return MFA enrollment status for the current user."""
    return await mfa_service.get_mfa_status(current_user.username)
