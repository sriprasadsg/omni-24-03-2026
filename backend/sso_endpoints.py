"""
SSO Endpoints — Google OAuth2 + SAML / OIDC
Phase 4: Real SSO integration using authlib
"""
import os
import logging
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from authlib.integrations.httpx_client import AsyncOAuth2Client
from database import get_database
from authentication_service import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from datetime import timedelta
import httpx
import uuid

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sso", tags=["SSO"])

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("SSO_REDIRECT_URI", "http://localhost:5000/api/sso/google/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


@router.get("/google/login")
async def google_login():
    """Initiate Google OAuth2 login flow."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=503,
            detail="Google SSO not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env"
        )

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "state": str(uuid.uuid4()),
    }
    auth_url = GOOGLE_AUTH_URL + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url=auth_url)


@router.get("/google/callback")
async def google_callback(code: str, state: str = None):
    """Handle Google OAuth2 callback, exchange code for tokens, create session."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Google SSO not configured")

    try:
        # Exchange code for access token
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                }
            )
            token_resp.raise_for_status()
            tokens = token_resp.json()
            access_token = tokens.get("access_token")

            # Get user info
            userinfo_resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            userinfo_resp.raise_for_status()
            userinfo = userinfo_resp.json()

    except Exception as e:
        logger.error(f"Google OAuth callback error: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=sso_failed")

    email = userinfo.get("email")
    name = userinfo.get("name", email)

    if not email:
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=no_email")

    # Find or create user in DB
    db = get_database()
    user = await db.users.find_one({"email": email})

    if not user:
        # Auto-provision user (assign to default tenant or based on email domain)
        new_user = {
            "id": str(uuid.uuid4()),
            "email": email,
            "name": name,
            "role": "Viewer",
            "tenantId": "default",
            "sso_provider": "google",
            "google_sub": userinfo.get("sub"),
            "created_at": __import__("datetime").datetime.utcnow().isoformat(),
        }
        await db.users.insert_one(new_user)
        user = new_user

    # Issue JWT
    jwt_token = create_access_token(
        data={"sub": email, "role": user.get("role", "Viewer"), "tenant_id": user.get("tenantId", "default")},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    # Redirect to frontend with token
    return RedirectResponse(url=f"{FRONTEND_URL}/sso-callback?token={jwt_token}&provider=google")


@router.get("/status")
async def sso_status():
    """Return SSO provider configuration status."""
    return {
        "google": {
            "configured": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
            "client_id": GOOGLE_CLIENT_ID[:8] + "..." if GOOGLE_CLIENT_ID else None,
        },
        "saml": {
            "configured": bool(os.getenv("SAML_IDP_METADATA_URL")),
            "metadata_url": os.getenv("SAML_IDP_METADATA_URL"),
        }
    }


@router.get("/providers")
async def list_sso_providers():
    """List available SSO providers for the login page."""
    providers = []
    if GOOGLE_CLIENT_ID:
        providers.append({
            "id": "google",
            "name": "Google",
            "icon": "google",
            "login_url": "/api/sso/google/login"
        })
    if os.getenv("SAML_IDP_METADATA_URL"):
        providers.append({
            "id": "saml",
            "name": "Enterprise SSO (SAML)",
            "icon": "shield",
            "login_url": "/api/sso/saml/login"
        })
    return {"providers": providers}
