import os
import json
import secrets
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from pydantic import BaseModel
from webauthn import options_to_json
from auth_types import TokenData
from authentication_service import get_current_user, create_access_token, create_refresh_token
from passkey_service import (
    build_registration_options,
    verify_and_store_registration,
    build_authentication_options,
    verify_authentication,
)
from database import mongodb

router = APIRouter(prefix="/api/passkey", tags=["Passkey"])
limiter = Limiter(key_func=get_remote_address)

class RegisterOptionsRequest(BaseModel):
    pass

class RegisterVerifyRequest(BaseModel):
    credential: dict

class LoginOptionsRequest(BaseModel):
    pass

class LoginVerifyRequest(BaseModel):
    credential: dict
    challenge_key: str

@router.post("/register/options")
async def passkey_register_options(
    current_user: TokenData = Depends(get_current_user)
):
    """Generate registration options for a new passkey."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")

    options = await build_registration_options(
        user_id=current_user.tenant_id,
        username=current_user.username,
        display_name=current_user.username
    )
    # options_to_json handles bytes→base64url and snake→camelCase for the browser API
    return json.loads(options_to_json(options))

@router.post("/register/verify")
async def passkey_register_verify(
    data: RegisterVerifyRequest,
    current_user: TokenData = Depends(get_current_user)
):
    """Verify and store a new passkey registration."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")

    try:
        cred = await verify_and_store_registration(
            user_id=current_user.tenant_id,
            credential_response=data.credential,
            db=None,
            users_collection=None,
            tenant_id=current_user.tenant_id
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Passkey registration failed")
    return {"success": True, "credential": cred}

@router.post("/login/options")
@limiter.limit("10/minute")
async def passkey_login_options(
    request: Request
):
    """Generate authentication options for passkey login (usernameless flow).

    The challenge is stored under a random one-shot key the client must echo
    back at verify time — it cannot be keyed on a user because the user is
    unknown until the authenticator responds with a discoverable credential.
    """
    challenge_key = secrets.token_urlsafe(16)
    options = await build_authentication_options(f"login:{challenge_key}")
    return {
        "challenge_key": challenge_key,
        "options": json.loads(options_to_json(options)),
    }

@router.post("/login/verify")
@limiter.limit("10/minute")
async def passkey_login_verify(
    request: Request,
    data: LoginVerifyRequest
):
    """Verify passkey authentication and return JWT tokens."""
    # We need to look up the user by the credential ID (hex at rest, base64url from browsers)
    from passkey_service import credential_id_candidates
    cred_id_raw = data.credential.get("id") or data.credential.get("rawId")
    if not cred_id_raw:
        raise HTTPException(status_code=400, detail="Missing credential id")

    # Look up user by credential ID
    user_doc = await mongodb.db.users.find_one(
        {"webauthn_credentials.credential_id": {"$in": credential_id_candidates(cred_id_raw)}},
        {"id": 1, "webauthn_credentials": 1, "tenantId": 1, "username": 1, "role": 1}
    )
    if not user_doc:
        raise HTTPException(status_code=401, detail="Invalid credential")

    try:
        auth_result = await verify_authentication(
            user_key=f"login:{data.challenge_key}",
            credential_response=data.credential,
            db=None,
            users_collection=None
        )
    except ValueError:
        # expired/replayed challenge, unknown credential, or failed verification
        raise HTTPException(status_code=401, detail="Passkey authentication failed")

    # Create tokens
    access_token = create_access_token({
        "sub": user_doc["username"],
        "role": user_doc.get("role", "user"),
        "tenant_id": user_doc.get("tenantId")
    })
    refresh_token = create_refresh_token({
        "sub": user_doc["username"],
        "role": user_doc.get("role", "user"),
        "tenant_id": user_doc.get("tenantId")
    })

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

@router.get("/credentials")
async def list_passkeys(current_user: TokenData = Depends(get_current_user)):
    """List user's registered passkeys."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")

    user_doc = await mongodb.db.users.find_one(
        {"id": current_user.tenant_id},
        {"webauthn_credentials": 1, "_id": 0}
    )
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")

    credentials = user_doc.get("webauthn_credentials", [])
    # Return safe info (no private keys)
    return [{
        "credential_id": c.get("credential_id"),
        "transports": c.get("transports", []),
        "created_at": c.get("created_at"),
        "last_used_at": c.get("last_used_at"),
    } for c in credentials]

@router.delete("/credentials/{credential_id}")
async def delete_passkey(
    credential_id: str,
    current_user: TokenData = Depends(get_current_user)
):
    """Delete a registered passkey."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")

    from database import mongodb
    result = await mongodb.db.users.update_one(
        {"id": current_user.tenant_id},
        {"$pull": {"webauthn_credentials": {"credential_id": credential_id}}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Credential not found")
    return {"success": True}