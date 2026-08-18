"""
SSO Endpoints — Google OAuth2 + SAML / OIDC
Phase 4: Real SSO integration using authlib
"""
import os
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field
from database import get_database
from authentication_service import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from rate_limiter import limiter
import httpx

from auth_types import TokenData
# Deliberately excluded from the D-02 API-key swap (Phase 73): SAML/SSO
# configuration is a materially different risk from reading/writing ITAM
# assets — this surface stays session-auth-only.
from itam_asset_endpoints import _require_itam_admin_session_only as _require_itam_admin
from rbac_utils import is_super_admin
from tenant_context import get_tenant_id

from saml_service import (
    SAMLConfigError,
    SAMLProvisionError,
    SAMLValidationError,
    SAMLAuthenticator,
    authenticate_saml,
    build_saml_request_data,
    get_saml_config,
)
from saml_mapping import SAMLGroupMapper, SAMLMappingError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sso", tags=["SSO"])

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("SSO_REDIRECT_URI", "http://localhost:5000/api/sso/google/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

_env = os.getenv("ENVIRONMENT", "development").lower()
_dev_envs = {"development", "dev", "local", "test"}
if _env not in _dev_envs and GOOGLE_REDIRECT_URI.startswith("http://"):
    logger.warning(
        "SSO_REDIRECT_URI is set to a plain HTTP URL (%r). "
        "OAuth authorisation codes must be delivered over HTTPS in production. "
        "Set SSO_REDIRECT_URI to an https:// URL before enabling Google SSO.",
        GOOGLE_REDIRECT_URI,
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


class SSOExchangeRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=256)


@router.post("/exchange")
@limiter.limit("10/minute")
async def exchange_sso_code(request: Request, body: SSOExchangeRequest):
    """Redeem a one-time SSO exchange code for a JWT access token."""
    token = await _consume_sso_state(f"tok:{body.code}")
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
    if os.getenv("SAML_IDP_METADATA_URL") or os.getenv("SAML_ENTITY_ID"):
        providers.append({
            "id": "saml",
            "name": "Enterprise SSO (SAML)",
            "icon": "shield",
            "login_url": "/api/auth/saml/login"
        })
    return {"providers": providers}


# ═══════════════════════════════════════════════════════════════════════════
# SAML 2.0 SSO (ITAM-USR-04)
# ═══════════════════════════════════════════════════════════════════════════
# The full SP implementation (metadata, login, ACS validation, SLO, user
# provisioning, group->role mapping) lives in saml_service.py / saml_mapping.py
# (see plan 64-04 <module_budget>) — this section only wires HTTP endpoints.
#
# Registered as a SEPARATE router (`saml_router`, no /api/sso prefix) because
# /api/auth/saml/* and /api/admin/sso/saml/* don't share this file's existing
# `router` prefix. router_registry.py must load both `router` and
# `saml_router` from this module — see 64-04 SUMMARY.md deviations.

saml_router = APIRouter(tags=["SAML SSO"])


def _saml_config_scope(current_user: TokenData) -> Optional[str]:
    """Mirrors ldap_endpoints._config_scope: Super Admins manage the
    platform-wide default SAML config (tenant_id=None, the one the
    unauthenticated /api/auth/saml/* routes resolve to); everyone else who
    reaches _require_itam_admin manages their own tenant's config."""
    return None if is_super_admin(current_user.role) else get_tenant_id()


class SAMLConfigIn(BaseModel):
    entity_id: str
    acs_url: str
    slo_url: Optional[str] = ""
    idp_entity_id: str
    idp_sso_url: str
    idp_slo_url: Optional[str] = ""
    idp_x509_cert: Optional[str] = ""
    sp_x509_cert: Optional[str] = ""
    sp_private_key: Optional[str] = ""
    attribute_email: Optional[str] = "email"
    attribute_name: Optional[str] = "name"
    attribute_groups: Optional[str] = "groups"


class SAMLAttributeMappingIn(BaseModel):
    group_value: str
    role: str
    priority: Optional[int] = 100


# ─── Admin: config management ──────────────────────────────────────────────

@saml_router.post("/api/admin/sso/saml/config")
async def save_saml_config(config: SAMLConfigIn, current_user: TokenData = Depends(_require_itam_admin)):
    """Persist SAML configuration. The SP private key is encrypted at rest
    via encryption_service (T-64-14) — never stored in plaintext."""
    from encryption_service import get_encryption_service

    db = get_database()
    tenant_id = _saml_config_scope(current_user)
    doc = config.model_dump()
    enc = get_encryption_service()
    doc["sp_private_key_encrypted"] = enc.encrypt(doc.pop("sp_private_key") or "")
    doc["tenant_id"] = tenant_id
    doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    doc["updated_by"] = getattr(current_user, "username", "unknown")

    await db.saml_configs.update_one({"tenant_id": tenant_id}, {"$set": doc}, upsert=True)
    return {"success": True}


@saml_router.get("/api/admin/sso/saml/config")
async def read_saml_config(current_user: TokenData = Depends(_require_itam_admin)):
    """Return the saved SAML config with the SP private key masked."""
    db = get_database()
    tenant_id = _saml_config_scope(current_user)
    doc = await db.saml_configs.find_one({"tenant_id": tenant_id})
    if not doc:
        raise HTTPException(status_code=404, detail="SAML is not configured for this scope")
    doc["_id"] = str(doc["_id"])
    doc.pop("sp_private_key_encrypted", None)
    doc["sp_private_key"] = "***masked***"
    return doc


@saml_router.get("/api/admin/sso/saml/metadata")
async def admin_saml_metadata(current_user: TokenData = Depends(_require_itam_admin)):
    """Admin preview of the SP metadata XML for the caller's configured scope
    (same content the public /api/auth/saml/metadata serves, gated here for
    operators setting up the IdP side before going live)."""
    tenant_id = _saml_config_scope(current_user)
    try:
        config = await get_saml_config(tenant_id)
    except SAMLConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    metadata_xml, _errors = SAMLAuthenticator(config).metadata()
    return Response(content=metadata_xml, media_type="application/xml")


@saml_router.post("/api/admin/sso/saml/test")
async def test_saml_config(current_user: TokenData = Depends(_require_itam_admin)):
    """Validate the caller's SAML configuration is complete and produces
    valid SP metadata (catches config typos — required fields, cert
    formatting — before going live). Does not perform a live IdP round
    trip; no test IdP is available to verify against in this environment,
    same accepted gap as 64-03's LDAP test-connection endpoint."""
    tenant_id = _saml_config_scope(current_user)
    try:
        config = await get_saml_config(tenant_id)
    except SAMLConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _metadata_xml, errors = SAMLAuthenticator(config).metadata()
    if errors:
        raise HTTPException(status_code=400, detail=f"SAML settings invalid: {errors}")
    return {"success": True, "message": "SAML configuration is valid"}


# ─── Admin: attribute (group) -> role mapping ──────────────────────────────

@saml_router.get("/api/admin/sso/saml/attribute-mapping")
async def list_attribute_mappings(current_user: TokenData = Depends(_require_itam_admin)):
    tenant_id = _saml_config_scope(current_user)
    return await SAMLGroupMapper.list_mappings(tenant_id)


@saml_router.post("/api/admin/sso/saml/attribute-mapping")
async def upsert_attribute_mapping(mapping: SAMLAttributeMappingIn, current_user: TokenData = Depends(_require_itam_admin)):
    tenant_id = _saml_config_scope(current_user)
    try:
        return await SAMLGroupMapper.upsert_mapping(
            mapping.group_value, mapping.role, tenant_id=tenant_id, priority=mapping.priority or 100,
        )
    except SAMLMappingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@saml_router.delete("/api/admin/sso/saml/attribute-mapping/{mapping_id}")
async def delete_attribute_mapping(mapping_id: str, current_user: TokenData = Depends(_require_itam_admin)):
    try:
        deleted = await SAMLGroupMapper.delete_mapping(mapping_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid mapping ID")
    if not deleted:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return {"success": True}


# ─── Public: metadata / SP-initiated login / ACS / SLO ─────────────────────
# Never gated by _require_itam_admin or get_current_user — an IdP (and a
# not-yet-authenticated browser) must be able to reach these.

@saml_router.get("/api/auth/saml/metadata")
async def public_saml_metadata():
    """Public SP metadata XML — paste this into the IdP's SAML app config."""
    try:
        config = await get_saml_config(None)
    except SAMLConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    metadata_xml, _errors = SAMLAuthenticator(config).metadata()
    return Response(content=metadata_xml, media_type="application/xml")


@saml_router.get("/api/auth/saml/login")
@limiter.limit("10/minute")
async def saml_login(request: Request):
    """SP-initiated SSO: redirect the browser to the IdP's SSO URL with a
    freshly built AuthnRequest."""
    try:
        config = await get_saml_config(None)
    except SAMLConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    request_data = await build_saml_request_data(request)
    url = await SAMLAuthenticator(config).build_login_url(request_data)
    return RedirectResponse(url=url)


@saml_router.post("/api/auth/saml/acs")
@limiter.limit("10/minute")
async def saml_acs(request: Request):
    """Assertion Consumer Service — the IdP POSTs the SAMLResponse here.
    Validates the assertion (signature/audience/timestamp/replay —
    T-64-13), provisions/updates the user, then redirects to the frontend
    via the same one-time exchange-code pattern the Google OIDC flow above
    already uses (_store_sso_state/_consume_sso_state), rather than putting
    a JWT directly in a browser-visible response.

    MFA follow-up: if SAML login must also honor two-phase MFA, that needs
    to be reconciled with 64-06's rewrite of the local login handler in the
    same wave — deliberately not attempted here (see plan Task 2, item 11).
    """
    request_data = await build_saml_request_data(request)
    try:
        result = await authenticate_saml(request_data, tenant_id=None)
    except SAMLValidationError as exc:
        logger.warning("SAML ACS validation failed: %s", exc)
        return RedirectResponse(url=_safe_frontend_url("/login?error=saml_failed"))
    except SAMLProvisionError as exc:
        logger.warning("SAML ACS provisioning failed: %s", exc)
        return RedirectResponse(url=_safe_frontend_url("/login?error=saml_not_registered"))

    exchange_code = secrets.token_urlsafe(32)
    await _store_sso_state(f"tok:{exchange_code}", result["access_token"], ttl_seconds=30)
    return RedirectResponse(url=_safe_frontend_url(f"/sso-callback?code={exchange_code}&provider=saml"))


@saml_router.get("/api/auth/saml/slo")
async def saml_slo(request: Request):
    """Single Logout — handles both an IdP-sent LogoutRequest and a
    LogoutResponse to an SP-initiated logout (HTTP-Redirect binding)."""
    try:
        config = await get_saml_config(None)
    except SAMLConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    request_data = await build_saml_request_data(request)
    try:
        redirect_url = SAMLAuthenticator(config).process_slo(request_data)
    except SAMLValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if redirect_url:
        return RedirectResponse(url=redirect_url)
    return {"success": True}
