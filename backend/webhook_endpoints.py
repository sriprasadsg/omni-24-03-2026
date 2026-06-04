import ipaddress
import socket
from urllib.parse import urlparse as _wh_urlparse
from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Dict, Any
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from datetime import datetime, timezone
import uuid
import hmac
import hashlib
import httpx
from intent_parser_service import intent_parser_service
from integration_service import get_integration_service


def _is_safe_webhook_url(url: str) -> bool:
    """Reject webhook URLs that resolve to private/internal addresses (SSRF guard)."""
    if not url or not url.startswith(("http://", "https://")):
        return False
    try:
        hostname = _wh_urlparse(url).hostname
        if not hostname:
            return False
        for info in socket.getaddrinfo(hostname, None):
            addr = ipaddress.ip_address(info[4][0])
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                return False
        return True
    except Exception:
        return False

router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])

_WEBHOOK_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}


async def _verify_inbound_signature(request: Request, provider: str, db) -> bool:
    """Validate HMAC-SHA256 signature on inbound webhook. Fail-closed when secret is configured."""
    cfg = await db.integration_config.find_one({"type": provider}, {"_id": 0}) or {}
    secret = cfg.get("webhook_secret") or cfg.get("webhookSecret", "")
    if not secret:
        import logging as _l
        _l.getLogger(__name__).warning(
            "No webhook_secret configured for %s inbound webhooks — accepting unauthenticated", provider
        )
        return True
    body = await request.body()
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    sig_header = (
        request.headers.get("X-Hub-Signature-256")
        or request.headers.get("X-Hub-Signature")
        or request.headers.get("X-Zoho-Signature")
        or ""
    )
    if not sig_header:
        return False
    return hmac.compare_digest(expected, sig_header)

@router.post("/jira/inbound")
async def handle_jira_webhook(request: Request, payload: Dict[str, Any]):
    """
    Handle inbound Jira webhook events.
    Parses 'issue_created' or 'issue_updated' and dispatches tasks.
    """
    db = get_database()
    if not await _verify_inbound_signature(request, "jira", db):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    integration_svc = get_integration_service(db)
    
    result = await intent_parser_service.parse_and_dispatch(payload, "jira")
    
    if result.get("success") and result.get("task_id"):
        # Post a comment back to Jira (optional/configurable)
        ticket_id = result.get("ticket_id")
        comment = f"Omni-Agent: Intent detected as '{result['intent']['action']}'. Automated task dispatched (ID: {result['task_id']})."
        await integration_svc.comment_on_ticket(ticket_id, comment, "jira")
    
    return result

@router.post("/zoho/inbound")
async def handle_zoho_webhook(request: Request, payload: Dict[str, Any]):
    """
    Handle inbound Zoho Desk webhook events.
    """
    db = get_database()
    if not await _verify_inbound_signature(request, "zohodesk", db):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    integration_svc = get_integration_service(db)
    
    result = await intent_parser_service.parse_and_dispatch(payload, "zohodesk")
    
    if result.get("success") and result.get("task_id"):
        ticket_id = result.get("ticket_id")
        comment = f"Omni-Agent: Automated task dispatched for '{result['intent']['action']}'."
        await integration_svc.comment_on_ticket(ticket_id, comment, "zohodesk")
        
    return result

@router.get("")
async def get_webhooks(current_user: TokenData = Depends(get_current_user)):
    """Get all configured webhooks"""
    db = get_database()
    caller_role = getattr(current_user, "role", "")
    caller_tenant = getattr(current_user, "tenant_id", None)
    query = {} if caller_role in _WEBHOOK_SUPER_ROLES else {"tenantId": caller_tenant}
    cursor = db.webhooks.find(query, {"_id": 0})
    return await cursor.to_list(length=100)

@router.post("")
async def create_webhook(
    webhook_data: Dict[str, Any],
    current_user: TokenData = Depends(get_current_user)
):
    """Create a new webhook"""
    db = get_database()
    
    webhook_id = f"wh-{uuid.uuid4().hex[:12]}"
    
    url = webhook_data.get("url", "")
    if not _is_safe_webhook_url(url):
        raise HTTPException(status_code=400, detail="Invalid or disallowed webhook URL")

    new_webhook = {
        "id": webhook_id,
        "name": webhook_data.get("name"),
        "url": url,
        "events": webhook_data.get("events", []),
        "status": "Active",
        "secret": f"whsec_{uuid.uuid4().hex[:24]}", # Auto-generated secret
        "tenantId": current_user.tenant_id,
        "createdBy": current_user.username,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "failureCount": 0,
        "lastResult": None
    }
    
    await db.webhooks.insert_one(new_webhook)
    return new_webhook

@router.delete("/{webhook_id}")
async def delete_webhook(webhook_id: str, current_user: TokenData = Depends(get_current_user)):
    """Delete a webhook"""
    db = get_database()
    query: dict = {"id": webhook_id}
    if getattr(current_user, "role", "") not in _WEBHOOK_SUPER_ROLES:
        query["tenantId"] = getattr(current_user, "tenant_id", None)
    result = await db.webhooks.delete_one(query)
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"success": True}

@router.put("/{webhook_id}")
async def update_webhook(
    webhook_id: str, 
    data: Dict[str, Any], 
    current_user: TokenData = Depends(get_current_user)
):
    """Update webhook status or details"""
    db = get_database()
    
    update_fields = {}
    if "status" in data:
        update_fields["status"] = data["status"]
    if "name" in data:
        update_fields["name"] = data["name"]
    if "url" in data:
        update_fields["url"] = data["url"]
    if "events" in data:
        update_fields["events"] = data["events"]
        
    if not update_fields:
        return {"success": False, "message": "No fields to update"}

    query: dict = {"id": webhook_id}
    if getattr(current_user, "role", "") not in _WEBHOOK_SUPER_ROLES:
        query["tenantId"] = getattr(current_user, "tenant_id", None)
    result = await db.webhooks.update_one(query, {"$set": update_fields})

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Webhook not found")

    updated_webhook = await db.webhooks.find_one(query, {"_id": 0})
    return updated_webhook

@router.get("/{webhook_id}/deliveries")
async def get_webhook_deliveries(
    webhook_id: str,
    limit: int = 50,
    current_user: TokenData = Depends(get_current_user),
):
    """Get real delivery history for a webhook from the webhook_deliveries collection."""
    db = get_database()
    caller_role = getattr(current_user, "role", "")
    caller_tenant = getattr(current_user, "tenant_id", None)
    wh_filter: dict = {"id": webhook_id}
    if caller_role not in _WEBHOOK_SUPER_ROLES:
        wh_filter["tenantId"] = caller_tenant
    if not await db.webhooks.find_one(wh_filter, {"_id": 1}):
        raise HTTPException(status_code=404, detail="Webhook not found")
    cursor = db.webhook_deliveries.find(
        {"webhook_id": webhook_id}, {"_id": 0}
    ).sort("delivered_at", -1).limit(limit)
    return await cursor.to_list(length=limit)


async def _record_delivery(db, webhook_id: str, event: str, payload: dict,
                            success: bool, status_code: int = 0, error: str = ""):
    """Persist a delivery attempt to webhook_deliveries collection."""
    try:
        await db.webhook_deliveries.insert_one({
            "id": f"del-{uuid.uuid4().hex[:10]}",
            "webhook_id": webhook_id,
            "event": event,
            "payload_preview": str(payload)[:500],
            "success": success,
            "status_code": status_code,
            "error": error,
            "delivered_at": datetime.now(timezone.utc).isoformat(),
        })
        # Cap history to 200 entries per webhook
        count = await db.webhook_deliveries.count_documents({"webhook_id": webhook_id})
        if count > 200:
            oldest = await db.webhook_deliveries.find(
                {"webhook_id": webhook_id}, {"_id": 1}
            ).sort("delivered_at", 1).limit(count - 200).to_list(length=count - 200)
            ids = [d["_id"] for d in oldest]
            if ids:
                await db.webhook_deliveries.delete_many({"_id": {"$in": ids}})
    except Exception:
        pass  # delivery logging must never break the caller


@router.post("/{webhook_id}/test")
async def test_webhook(webhook_id: str, current_user: TokenData = Depends(get_current_user)):
    """Test a webhook by sending a ping event and recording the delivery."""
    db = get_database()
    caller_role = getattr(current_user, "role", "")
    caller_tenant = getattr(current_user, "tenant_id", None)
    wh_filter: dict = {"id": webhook_id}
    if caller_role not in _WEBHOOK_SUPER_ROLES:
        wh_filter["tenantId"] = caller_tenant
    webhook = await db.webhooks.find_one(wh_filter)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    payload = {
        "event": "ping",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {
            "message": "This is a test event from Omni Agent Platform",
            "triggeredBy": current_user.username,
        },
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                webhook["url"],
                json=payload,
                headers={"Content-Type": "application/json", "User-Agent": "Omni-Platform/1.0"},
                timeout=5.0,
            )

        success = 200 <= response.status_code < 300
        await _record_delivery(db, webhook_id, "ping", payload, success, response.status_code)

        await db.webhooks.update_one(
            wh_filter,
            {"$set": {"lastResult": "success" if success else "failure",
                      "lastTestedAt": datetime.now(timezone.utc).isoformat()}},
        )
        return {"success": success, "status": response.status_code, "response": response.text[:200]}
    except Exception as e:
        import logging as _l; _l.getLogger(__name__).error("Webhook test error: %s", e)
        await _record_delivery(db, webhook_id, "ping", payload, False, 0, "connection error")
        await db.webhooks.update_one(
            wh_filter,
            {"$set": {"lastResult": "failure", "failureCount": 1}},
        )
        return {"success": False, "error": "Webhook delivery failed"}
