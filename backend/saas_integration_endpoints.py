"""SaaS OAuth Integration Endpoints.

Routes:
  GET    /api/saas/connections                        — list all tenant connections
  GET    /api/saas/connect/{provider}                 — OAuth authorize redirect
  GET    /api/saas/callback/{provider}                — OAuth token exchange callback
  POST   /api/saas/connections/{id}/pull-evidence     — trigger async evidence collection
  DELETE /api/saas/connections/{id}                   — revoke and remove connection
"""
from __future__ import annotations

import logging
import os
import urllib.parse
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from authentication_service import get_current_user
from database import get_db
from saas_integration_service import (
    OAUTH_CONFIGS,
    OAuthProvider,
    _decrypt,
    saas_integration_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/saas", tags=["SaaS Integration"])

_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8000")
_GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
_GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")
_JIRA_CLIENT_ID = os.environ.get("JIRA_CLIENT_ID", "")
_JIRA_CLIENT_SECRET = os.environ.get("JIRA_CLIENT_SECRET", "")
_GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
_GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
_SLACK_CLIENT_ID = os.environ.get("SLACK_CLIENT_ID", "")
_SLACK_CLIENT_SECRET = os.environ.get("SLACK_CLIENT_SECRET", "")
_OKTA_CLIENT_ID = os.environ.get("OKTA_CLIENT_ID", "")
_OKTA_CLIENT_SECRET = os.environ.get("OKTA_CLIENT_SECRET", "")

_CLIENT_IDS = {
    "github": _GITHUB_CLIENT_ID,
    "jira": _JIRA_CLIENT_ID,
    "google_workspace": _GOOGLE_CLIENT_ID,
    "slack": _SLACK_CLIENT_ID,
    "okta": _OKTA_CLIENT_ID,
}


def _tenant_filter(user) -> dict:
    """Return a MongoDB filter scoped to the current user's tenant."""
    role = getattr(user, "role", None)
    if role in ("super_admin", "platform_admin"):
        return {}
    tenant_id = getattr(user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return {"tenant_id": tenant_id}


# ---------------------------------------------------------------------------
# GET /api/saas/connections
# ---------------------------------------------------------------------------

@router.get("/connections")
async def list_connections(
    current_user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Return all SaaS connections for the current tenant."""
    flt = _tenant_filter(current_user)
    docs = []
    async for doc in db.saas_connections.find(flt):
        docs.append({
            "id": doc.get("id"),
            "provider": doc.get("provider"),
            "status": doc.get("status", "active"),
            "last_synced": doc.get("last_synced"),
            "evidence_count": doc.get("evidence_count", 0),
            "tenant_id": doc.get("tenant_id"),
        })
    return {"connections": docs}


# ---------------------------------------------------------------------------
# GET /api/saas/connect/{provider} — OAuth authorize redirect
# ---------------------------------------------------------------------------

@router.get("/connect/{provider}")
async def oauth_authorize(
    provider: str,
    current_user=Depends(get_current_user),
):
    """Start the OAuth authorization code flow for the given provider."""
    if provider not in OAUTH_CONFIGS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    config = OAUTH_CONFIGS[provider]
    client_id = _CLIENT_IDS.get(provider, "")
    if not client_id:
        raise HTTPException(status_code=503, detail=f"{provider} OAuth client ID not configured")

    callback_url = f"{_BASE_URL}/api/saas/callback/{provider}"
    tenant_id = getattr(current_user, "tenant_id", "")
    state = urllib.parse.quote(tenant_id)

    params = {
        "client_id": client_id,
        "redirect_uri": callback_url,
        "scope": config["scopes"],
        "state": state,
        "response_type": "code",
    }
    auth_url = config["auth_url"].replace("{domain}", os.environ.get("OKTA_DOMAIN", ""))
    redirect_target = f"{auth_url}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url=redirect_target)


# ---------------------------------------------------------------------------
# GET /api/saas/callback/{provider} — OAuth token exchange
# ---------------------------------------------------------------------------

@router.get("/callback/{provider}")
async def oauth_callback(
    provider: str,
    code: str,
    state: Optional[str] = None,
    db=Depends(get_db),
):
    """Exchange the OAuth authorization code for access/refresh tokens."""
    if provider not in OAUTH_CONFIGS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    tenant_id = urllib.parse.unquote(state or "")
    config = OAUTH_CONFIGS[provider]
    client_id = _CLIENT_IDS.get(provider, "")
    client_secret = {
        "github": _GITHUB_CLIENT_SECRET,
        "jira": _JIRA_CLIENT_SECRET,
        "google_workspace": _GOOGLE_CLIENT_SECRET,
        "slack": _SLACK_CLIENT_SECRET,
        "okta": _OKTA_CLIENT_SECRET,
    }.get(provider, "")

    import httpx as _httpx
    token_url = config["token_url"].replace("{domain}", os.environ.get("OKTA_DOMAIN", ""))
    try:
        async with _httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": f"{_BASE_URL}/api/saas/callback/{provider}",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            token_data = resp.json()
    except Exception as exc:
        logger.warning("OAuth token exchange failed for %s: %s", provider, exc)
        raise HTTPException(status_code=502, detail="Token exchange failed")

    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")

    if not access_token:
        raise HTTPException(status_code=502, detail="No access_token in OAuth response")

    connection_id = await saas_integration_service.store_connection(
        db=db,
        provider=provider,
        tenant_id=tenant_id,
        access_token=access_token,
        refresh_token=refresh_token,
    )
    return {"message": "Connection established", "connection_id": connection_id, "provider": provider}


# ---------------------------------------------------------------------------
# POST /api/saas/connections/{id}/pull-evidence
# ---------------------------------------------------------------------------

@router.post("/connections/{connection_id}/pull-evidence")
async def pull_evidence(
    connection_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Trigger evidence collection for a SaaS connection (SAAS-02)."""
    connection = await db.saas_connections.find_one({"id": connection_id})
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    # Tenant isolation — super_admin can pull any connection
    role = getattr(current_user, "role", None)
    user_tenant = getattr(current_user, "tenant_id", None)
    if role not in ("super_admin", "platform_admin"):
        if connection.get("tenant_id") != user_tenant:
            raise HTTPException(status_code=403, detail="Access denied: cross-tenant pull not allowed")

    evidence = await saas_integration_service.pull_all_evidence(connection=connection, db=db)
    return {"message": "Evidence collected", "count": len(evidence), "connection_id": connection_id}


# ---------------------------------------------------------------------------
# DELETE /api/saas/connections/{id}
# ---------------------------------------------------------------------------

@router.delete("/connections/{connection_id}")
async def delete_connection(
    connection_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Revoke and remove a SaaS connection (SAAS-03)."""
    connection = await db.saas_connections.find_one({"id": connection_id})
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    role = getattr(current_user, "role", None)
    user_tenant = getattr(current_user, "tenant_id", None)
    if role not in ("super_admin", "platform_admin"):
        if connection.get("tenant_id") != user_tenant:
            raise HTTPException(status_code=403, detail="Access denied")

    result = await db.saas_connections.delete_one({"id": connection_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=500, detail="Failed to delete connection")

    return {"message": "Connection removed", "connection_id": connection_id}
