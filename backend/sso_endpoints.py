"""
SSO Endpoints — Google OAuth2 + SAML / OIDC
Phase 4: Real SSO integration using authlib
"""
import os
import logging
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from database import get_database
from authentication_service import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
import httpx

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sso", tags=["SSO"])

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("SSO_REDIRECT_URI", "http://localhost:5000/api/sso/google/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

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

_sso_index_created = False


def _safe_frontend_url(path: str) -> str:
    """Return FRONTEND_URL + path, validated to prevent open redirect."""
    from urllib.parse import urlparse
    parsed = urlparse(FRONTEND_URL)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"FRONTEND_URL is invalid: {FRONTEND_URL!r}")
    safe_base = f"{parsed.scheme}://{parsed.netloc}"
    return f"{safe_base}{path}"


async def _sso_col():
    """Return the sso_state collection, ensuring TTL index exists."""
    global _sso_index_created
    db = get_database()
    col = db._db.sso_state
    if not _sso_index_created:
        await col.create_index("expires_at", expireAfterSeconds=0)
        _sso_index_created = True
    return col


async def _store_sso_state(key: str, value, ttl_seconds: int) -> None:
    """Upsert a short-lived SSO state entry (CSRF token or exchange code)."""
    col = await _sso_col()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    await col.replace_one(
        {"_id": key},
        {"_id": key, "value": value, "expires_at": expires_at},
        upsert=True,
    )


async def _consume_sso_state(key: str):
    """Atomically delete and return the value for key; returns None if missing or expired."""
    col = await _sso_col()
    doc = await col.find_one_and_delete({"_id": key})
    if not doc:
        return None
    if doc["expires_at"] < datetime.now(timezone.utc):
        return None  # document expired but TTL index hasn't cleaned it yet
    return doc.get("value")


@router.get("/google/login")
async def google_login():
    """Initiate Google OAuth2 login flow."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=503,
            detail="Google SSO not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env"
        )

    state = secrets.token_urlsafe(32)
    await _store_sso_state(state, True, ttl_seconds=60)

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

    valid = await _consume_sso_state(state)
    if not valid:
        return RedirectResponse(url=_safe_frontend_url("/login?error=invalid_state"))

    try:
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

    # Reject unverified email addresses — an attacker with an unverified email matching
    # an existing user's address would otherwise receive a valid JWT for that account.
    if not userinfo.get("email_verified", False):
        logger.warning("SSO login rejected for unverified email: %s", email)
        return RedirectResponse(url=_safe_frontend_url("/login?error=email_not_verified"))

    db = get_database()
    user = await db.users.find_one({"email": email})

    if not user:
        logger.warning("SSO login rejected for unregistered email: %s", email)
        return RedirectResponse(url=_safe_frontend_url("/login?error=sso_not_registered"))

    jwt_token = create_access_token(
        data={"sub": email, "role": user.get("role", "Viewer"), "tenant_id": user.get("tenantId") or None},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    exchange_code = secrets.token_urlsafe(32)
    await _store_sso_state(f"tok:{exchange_code}", jwt_token, ttl_seconds=30)
    return RedirectResponse(url=_safe_frontend_url(f"/sso-callback?code={exchange_code}&provider=google"))


@router.post("/exchange")
async def exchange_sso_code(body: dict):
    """Redeem a one-time SSO exchange code for a JWT access token."""
    code = body.get("code", "")
    token = await _consume_sso_state(f"tok:{code}")
    if not token:
        raise HTTPException(status_code=401, detail="Invalid or expired SSO exchange code")
    return {"access_token": token, "token_type": "bearer"}


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
