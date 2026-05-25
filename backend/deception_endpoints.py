"""
Deception Technology Endpoints
"""

import re
from fastapi import APIRouter, Depends, HTTPException, Body, Request, Query
from typing import Any, Dict
import logging

from authentication_service import get_current_user
from auth_types import TokenData
from rate_limiter import limiter
import deception_service as svc

_TOKEN_ID_RE = re.compile(r'^[a-zA-Z0-9_-]{8,64}$')

router = APIRouter(prefix="/api/deception", tags=["Deception Technology"])
logger = logging.getLogger(__name__)


@router.get("/summary")
async def get_summary(current_user: TokenData = Depends(get_current_user)):
    return await svc.get_deception_summary(current_user.tenant_id or "", current_user.role or "")


@router.get("/honeytokens")
async def list_honeytokens(current_user: TokenData = Depends(get_current_user)):
    tokens = await svc.list_honeytokens(current_user.tenant_id or "", current_user.role or "")
    return {"honeytokens": tokens, "total": len(tokens)}


@router.post("/honeytokens")
async def create_honeytoken(
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    token_type = payload.get("type", "api_key")
    if token_type not in svc.HONEYTOKEN_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid type. Choose from: {list(svc.HONEYTOKEN_TYPES.keys())}")

    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    token = await svc.create_honeytoken(
        current_user.tenant_id,
        current_user.username or "",
        payload,
    )
    token.pop("_id", None)
    return {"honeytoken": token, "message": "Honeytoken created — deploy it in a sensitive location to detect unauthorized access"}


@router.delete("/honeytokens/{token_id}")
async def delete_honeytoken(token_id: str, current_user: TokenData = Depends(get_current_user)):
    success = await svc.delete_honeytoken(token_id, current_user.tenant_id or "", current_user.role or "")
    if not success:
        raise HTTPException(status_code=404, detail="Honeytoken not found")
    return {"message": "Honeytoken deleted"}


@router.post("/honeytokens/{token_id}/deactivate")
async def deactivate_honeytoken(token_id: str, current_user: TokenData = Depends(get_current_user)):
    success = await svc.deactivate_honeytoken(token_id, current_user.tenant_id or "", current_user.role or "")
    if not success:
        raise HTTPException(status_code=404, detail="Honeytoken not found")
    return {"message": "Honeytoken deactivated"}


@router.get("/alerts")
async def list_alerts(
    limit: int = Query(100, ge=1, le=500),
    current_user: TokenData = Depends(get_current_user),
):
    alerts = await svc.list_deception_alerts(current_user.tenant_id or "", current_user.role or "", limit=limit)
    return {"alerts": alerts, "total": len(alerts)}


@router.get("/honeytoken-types")
async def honeytoken_types(current_user: TokenData = Depends(get_current_user)):
    return {"types": [
        {"id": k, **v} for k, v in svc.HONEYTOKEN_TYPES.items()
    ]}


# ── Webhook endpoint for external canarytoken.org-style callbacks ─────────────

@router.post("/webhook/trigger/{token_id}")
@limiter.limit("10/minute")
async def webhook_trigger(request: Request, token_id: str):
    """
    Publicly accessible webhook for external honeytoken callbacks.
    No auth required — this is called by attacker infrastructure.
    """
    if not _TOKEN_ID_RE.match(token_id):
        return {"status": "ok"}

    source_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")
    try:
        body = await request.json()
    except Exception:
        body = {}

    triggered = await svc.record_trigger(token_id, source_ip, user_agent, body)
    # Always return 200 to not reveal detection
    return {"status": "ok"}
