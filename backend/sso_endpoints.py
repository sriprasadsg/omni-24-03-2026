"""
SSO Endpoints — Google OAuth2 + SAML / OIDC
Phase 4: Real SSO integration using authlib
"""
import os
import hmac
import logging
import secrets
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from authlib.integrations.httpx_client import AsyncOAuth2Client
from database import get_database
from authentication_service import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from datetime import timedelta, timezone
import httpx
import uuid

# Short-lived in-process state store for CSRF protection {state: expires_at_epoch}
_oauth_states: dict = {}

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sso", tags=["SSO"])

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("SSO_REDIRECT_URI", "http://localhost:5000/api/sso/google/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Reject plain-HTTP redirect URIs outside local development to prevent auth-code interception
_env = os.getenv("ENVIRONMENT", "development").lower()
if _env != "development" and GOOGLE_REDIRECT_URI.startswith("http://"):
    raise RuntimeError(
        f"SSO_REDIRECT_URI is set to a plain HTTP URL ({GOOGLE_REDIRECT_URI!r}). "
        "OAuth authorisation codes must be delivered over HTTPS in non-development environments. "
        "Set SSO_REDIRECT_URI to an https:// URL."
    )
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# Allowlist of trusted redirect origins derived from FRONTEND_URL and SSO_REDIRECT_URI
def _safe_frontend_url(path: str) -> str:
    """Return FRONTEND_URL + path, validated to prevent open redirect."""
    from urllib.parse import urlparse
    parsed = urlparse(FRONTEND_URL)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"FRONTEND_URL is invalid: {FRONTEND_URL!r}")
    # Reconstruct to drop any query/fragment that could smuggle a redirect
    safe_base = f"{parsed.scheme}://{parsed.netloc}"
    return f"{safe_base}{path}"


@router.get("/google/login")
async def google_login():
    """Initiate Google OAuth2 login flow."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=503,
            detail="Google SSO not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env"
        )

    import time
    # Generate and store CSRF state token (60-second TTL)
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = time.time() + 60
    # Purge expired states
    now = time.time()
    for k in [k for k, v in _oauth_states.items() if v < now]:
        del _oauth_states[k]

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "state": state,
    }
    auth_url = GOOGLE_AUTH_URL + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url=auth_url)


@router.get("/google/callback")
async def google_callback(code: str, state: str = ""):
    """Handle Google OAuth2 callback, exchange code for tokens, create session."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Google SSO not configured")

    import time
    # Validate CSRF state
    expected_expiry = _oauth_states.pop(state, None)
    if not expected_expiry or time.time() > expected_expiry:
        return RedirectResponse(url=_safe_frontend_url("/login?error=invalid_state"))

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
        logger.error("Google OAuth callback error: %s", e)
        return RedirectResponse(url=_safe_frontend_url("/login?error=sso_failed"))

    email = userinfo.get("email")
    name = userinfo.get("name", email)

    if not email:
        return RedirectResponse(url=_safe_frontend_url("/login?error=no_email"))

    # Find or create user in DB
    db = get_database()
    user = await db.users.find_one({"email": email})

    if not user:
        # Do not auto-provision unknown users — they must register first via the
        # signup flow which creates a properly isolated tenant for their organisation.
        logger.warning("SSO login rejected for unregistered email: %s", email)
        return RedirectResponse(
            url=_safe_frontend_url("/login?error=sso_not_registered")
        )

    # Issue JWT
    jwt_token = create_access_token(
        data={"sub": email, "role": user.get("role", "Viewer"), "tenant_id": user.get("tenantId", "default")},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    # Pass token via short-lived exchange code (not in URL) to avoid token in browser history/logs
    exchange_code = secrets.token_urlsafe(32)
    _oauth_states[f"tok:{exchange_code}"] = (jwt_token, __import__("time").time() + 30)
    return RedirectResponse(url=_safe_frontend_url(f"/sso-callback?code={exchange_code}&provider=google"))


@router.post("/exchange")
async def exchange_sso_code(body: dict):
    """Redeem a one-time SSO exchange code for a JWT access token."""
    import time
    code = body.get("code", "")
    key = f"tok:{code}"
    entry = _oauth_states.pop(key, None)
    if not entry or time.time() > entry[1]:
        raise HTTPException(status_code=401, detail="Invalid or expired SSO exchange code")
    return {"access_token": entry[0], "token_type": "bearer"}


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
