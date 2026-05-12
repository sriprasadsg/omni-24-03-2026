"""
Deception Technology Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Body, Request
from typing import Any, Dict
import logging

from auth_utils import get_current_user
import deception_service as svc

router = APIRouter(prefix="/api/deception", tags=["Deception Technology"])
logger = logging.getLogger(__name__)


@router.get("/summary")
async def get_summary(current_user: dict = Depends(get_current_user)):
    tenant_id = current_user.get("tenant_id", "")
    role = current_user.get("role", "")
    return await svc.get_deception_summary(tenant_id, role)


@router.get("/honeytokens")
async def list_honeytokens(current_user: dict = Depends(get_current_user)):
    tenant_id = current_user.get("tenant_id", "")
    role = current_user.get("role", "")
    tokens = await svc.list_honeytokens(tenant_id, role)
    return {"honeytokens": tokens, "total": len(tokens)}


@router.post("/honeytokens")
async def create_honeytoken(
    payload: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user),
):
    token_type = payload.get("type", "api_key")
    if token_type not in svc.HONEYTOKEN_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid type. Choose from: {list(svc.HONEYTOKEN_TYPES.keys())}")

    tenant_id = current_user.get("tenant_id", "platform-admin")
    created_by = current_user.get("email", current_user.get("username", ""))
    token = await svc.create_honeytoken(tenant_id, created_by, payload)
    token.pop("_id", None)
    return {"honeytoken": token, "message": "Honeytoken created — deploy it in a sensitive location to detect unauthorized access"}


@router.delete("/honeytokens/{token_id}")
async def delete_honeytoken(token_id: str, current_user: dict = Depends(get_current_user)):
    tenant_id = current_user.get("tenant_id", "")
    role = current_user.get("role", "")
    success = await svc.delete_honeytoken(token_id, tenant_id, role)
    if not success:
        raise HTTPException(status_code=404, detail="Honeytoken not found")
    return {"message": "Honeytoken deleted"}


@router.post("/honeytokens/{token_id}/deactivate")
async def deactivate_honeytoken(token_id: str, current_user: dict = Depends(get_current_user)):
    tenant_id = current_user.get("tenant_id", "")
    role = current_user.get("role", "")
    success = await svc.deactivate_honeytoken(token_id, tenant_id, role)
    if not success:
        raise HTTPException(status_code=404, detail="Honeytoken not found")
    return {"message": "Honeytoken deactivated"}


@router.get("/alerts")
async def list_alerts(
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
):
    tenant_id = current_user.get("tenant_id", "")
    role = current_user.get("role", "")
    alerts = await svc.list_deception_alerts(tenant_id, role, limit=limit)
    return {"alerts": alerts, "total": len(alerts)}


@router.get("/honeytoken-types")
async def honeytoken_types(current_user: dict = Depends(get_current_user)):
    return {"types": [
        {"id": k, **v} for k, v in svc.HONEYTOKEN_TYPES.items()
    ]}


# ── Webhook endpoint for external canarytoken.org-style callbacks ─────────────

@router.post("/webhook/trigger/{token_id}")
async def webhook_trigger(token_id: str, request: Request):
    """
    Publicly accessible webhook for external honeytoken callbacks.
    No auth required — this is called by attacker infrastructure.
    """
    source_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")
    try:
        body = await request.json()
    except Exception:
        body = {}

    triggered = await svc.record_trigger(token_id, source_ip, user_agent, body)
    # Always return 200 to not reveal detection
    return {"status": "ok"}
