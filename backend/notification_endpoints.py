from fastapi import APIRouter, HTTPException, Depends, Body, Query
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from database import get_database
import logging
import notification_service

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])
logger = logging.getLogger(__name__)

from auth_types import TokenData
from tenant_context import get_tenant_id
from rbac_service import rbac_service


def _validate_webhook_url(url: str) -> bool:
    """Reject private/loopback IPs and non-HTTP(S) schemes to block SSRF."""
    if not url:
        return False
    try:
        from urllib.parse import urlparse as _urlparse
        from ipaddress import ip_address as _ip_address
        parsed = _urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return False
        hostname = parsed.hostname or ""
        try:
            ip = _ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        except ValueError:
            pass  # hostname is a domain name — allow
        return True
    except Exception as e:
        logger.debug("Webhook URL validation failed: %s", e)
        return False


@router.get("")
async def get_notifications(
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
    limit: int = Query(50, ge=1, le=100),
):
    """Get recent notifications for a tenant"""
    db = get_database()
    tenant_id = get_tenant_id()
    notifications = await db.notifications.find(
        {"tenantId": tenant_id},
        {"_id": 0}
    ).sort("sent_at", -1).to_list(length=limit)
    return notifications

@router.put("/{notification_id}/read")
async def mark_as_read(notification_id: str, current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))):
    """Mark a notification as read"""
    db = get_database()
    tenant_id = get_tenant_id()
    result = await db.notifications.update_one(
        {"alert_id": notification_id, "tenantId": tenant_id},
        {"$set": {"read": True, "read_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"success": True}

@router.put("/read-all")
async def mark_all_as_read(
    notification_ids: Optional[List[str]] = Body(default=None),
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))
):
    """Mark all (or specific) notifications as read"""
    db = get_database()
    tenant_id = get_tenant_id()
    
    if notification_ids:
        query = {"alert_id": {"$in": notification_ids}, "tenantId": tenant_id}
    else:
        # Mark ALL notifications for tenant as read
        query = {"tenantId": tenant_id}
        
    result = await db.notifications.update_many(
        query,
        {"$set": {"read": True, "read_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"success": True, "modified_count": result.modified_count}

@router.delete("/{notification_id}")
async def delete_notification(notification_id: str, current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))):
    """Delete a notification"""
    db = get_database()
    tenant_id = get_tenant_id()
    result = await db.notifications.delete_one({"alert_id": notification_id, "tenantId": tenant_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"success": True}

_REDACTED_FIELDS = {"webhook_url", "auth_token", "routing_key", "account_sid", "secret"}

@router.get("/config")
async def get_notification_config(current_user: TokenData = Depends(rbac_service.has_permission("manage:settings"))):
    """Get notification configuration (Slack, etc.)"""
    db = get_database()
    tenant_id = get_tenant_id()
    configs = await db.notification_config.find(
        {"tenantId": tenant_id},
        {"_id": 0}
    ).to_list(length=100)
    # Redact sensitive credential fields — they are write-only
    for cfg in configs:
        for field in _REDACTED_FIELDS:
            if field in cfg:
                cfg[field] = "***"
    return configs

@router.post("/config")
async def update_notification_config(config: Dict[str, Any] = Body(...), current_user: TokenData = Depends(rbac_service.has_permission("manage:settings"))):
    """Update notification configuration"""
    db = get_database()
    tenant_id = get_tenant_id()
    config_type = config.get("type")

    if not config_type:
        raise HTTPException(status_code=400, detail="Config type is required")

    await db.notification_config.update_one(
        {"tenantId": tenant_id, "type": config_type},
        {"$set": {**config, "tenantId": tenant_id, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )
    return {"success": True}


@router.post("/test/{channel}")
async def test_notification_channel(
    channel: str,
    payload: Dict[str, Any] = Body(default={}),
    current_user: TokenData = Depends(rbac_service.has_permission("manage:settings")),
):
    """
    Test a notification channel by sending a real test message.
    channel: slack | teams | pagerduty | email | webhook | sms
    Supply the config in the body, or it will be loaded from the saved tenant config.
    """
    import aiohttp as _aiohttp
    db = get_database()
    tenant_id = get_tenant_id()

    # Load saved config and merge with any supplied override
    saved = await db.notification_config.find_one(
        {"tenantId": tenant_id, "type": channel}, {"_id": 0}
    ) or {}
    cfg = {**saved, **payload}

    test_msg = f"[OmniAgent] Notification test — channel '{channel}' — {datetime.now(timezone.utc).isoformat()}"

    try:
        if channel == "slack":
            webhook_url = cfg.get("webhook_url", "")
            if not webhook_url:
                return {"success": False, "message": "Slack webhook_url not configured"}
            if not _validate_webhook_url(webhook_url):
                return {"success": False, "message": "Invalid or unsafe Slack webhook URL"}
            async with _aiohttp.ClientSession() as s:
                async with s.post(webhook_url, json={"text": test_msg},
                                  timeout=_aiohttp.ClientTimeout(total=8)) as r:
                    ok = r.status == 200
                    return {"success": ok, "http_status": r.status,
                            "message": "Slack test sent" if ok else f"Slack returned HTTP {r.status}"}

        elif channel == "teams":
            webhook_url = cfg.get("webhook_url", "")
            if not webhook_url:
                return {"success": False, "message": "Teams webhook_url not configured"}
            if not _validate_webhook_url(webhook_url):
                return {"success": False, "message": "Invalid or unsafe Teams webhook URL"}
            async with _aiohttp.ClientSession() as s:
                payload_body = {"@type": "MessageCard", "@context": "http://schema.org/extensions",
                                "summary": "OmniAgent Test", "themeColor": "0078D4",
                                "sections": [{"activityTitle": "Notification Test",
                                              "activityText": test_msg}]}
                async with s.post(webhook_url, json=payload_body,
                                  timeout=_aiohttp.ClientTimeout(total=8)) as r:
                    ok = r.status in (200, 202)
                    return {"success": ok, "http_status": r.status,
                            "message": "Teams test sent" if ok else f"Teams returned HTTP {r.status}"}

        elif channel == "pagerduty":
            routing_key = cfg.get("routing_key", "")
            if not routing_key:
                return {"success": False, "message": "PagerDuty routing_key not configured"}
            pd_payload = {
                "routing_key": routing_key,
                "event_action": "trigger",
                "payload": {
                    "summary": "OmniAgent notification channel test",
                    "severity": "info",
                    "source": "omni-agent-platform",
                    "custom_details": {"message": test_msg},
                },
            }
            async with _aiohttp.ClientSession() as s:
                async with s.post("https://events.pagerduty.com/v2/enqueue",
                                  json=pd_payload, timeout=_aiohttp.ClientTimeout(total=10)) as r:
                    data = await r.json()
                    ok = r.status == 202
                    return {"success": ok, "http_status": r.status,
                            "dedup_key": data.get("dedup_key"),
                            "message": "PagerDuty event triggered" if ok else data.get("message", f"HTTP {r.status}")}

        elif channel == "email":
            recipient = cfg.get("test_recipient") or cfg.get("recipients", [None])[0]
            if not recipient:
                return {"success": False, "message": "No test_recipient configured for email channel"}
            from email_service import email_service
            result = await email_service.send_report(
                recipient=recipient,
                report_name="Notification Channel Test",
                report_data={"report_type": "test", "message": test_msg,
                             "generated_at": datetime.now(timezone.utc).isoformat()},
            )
            return result

        elif channel == "webhook":
            url = cfg.get("url", "") or cfg.get("webhook_url", "")
            if not url:
                return {"success": False, "message": "webhook url not configured"}
            if not _validate_webhook_url(url):
                return {"success": False, "message": "Invalid or unsafe webhook URL"}
            headers = {"Content-Type": "application/json"}
            if cfg.get("secret"):
                headers["X-OmniAgent-Secret"] = cfg["secret"]
            async with _aiohttp.ClientSession() as s:
                async with s.post(url, json={"event": "test", "message": test_msg},
                                  headers=headers, timeout=_aiohttp.ClientTimeout(total=8)) as r:
                    ok = r.status < 400
                    return {"success": ok, "http_status": r.status,
                            "message": "Webhook test delivered" if ok else f"Webhook returned HTTP {r.status}"}

        elif channel == "sms":
            account_sid = cfg.get("account_sid") or __import__("os").getenv("TWILIO_ACCOUNT_SID", "")
            auth_token = cfg.get("auth_token") or __import__("os").getenv("TWILIO_AUTH_TOKEN", "")
            from_number = cfg.get("from_number") or __import__("os").getenv("TWILIO_FROM", "")
            to_number = cfg.get("to_number") or cfg.get("test_number", "")
            if not all([account_sid, auth_token, from_number, to_number]):
                return {"success": False, "message": "Twilio credentials or phone numbers not configured"}
            async with _aiohttp.ClientSession() as s:
                async with s.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
                    auth=_aiohttp.BasicAuth(account_sid, auth_token),
                    data={"From": from_number, "To": to_number, "Body": test_msg},
                    timeout=_aiohttp.ClientTimeout(total=10),
                ) as r:
                    data = await r.json()
                    ok = r.status in (200, 201)
                    return {"success": ok, "sid": data.get("sid"),
                            "message": "SMS sent" if ok else data.get("message", f"HTTP {r.status}")}

        else:
            return {"success": False, "message": f"Unknown channel '{channel}'. Use: slack, teams, pagerduty, email, webhook, sms"}

    except Exception as exc:
        import logging as _l; _l.getLogger(__name__).error("Notification send error: %s", exc)
        return {"success": False, "message": "Notification delivery failed"}


# ─── Channels ─────────────────────────────────────────────────────────────────


@router.post("/channels")
async def create_notification_channel(payload: dict = Body(...), current_user: TokenData = Depends(rbac_service.has_permission("manage:settings"))):
    db = get_database()
    try:
        ch = await notification_service.create_channel(db, get_tenant_id(), payload)
        return {"channel": ch}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/channels")
async def list_notification_channels(current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))):
    db = get_database()
    items = await notification_service.list_channels(db, get_tenant_id())
    for item in items:
        cfg = item.get("config") or {}
        for field in _REDACTED_FIELDS:
            if field in cfg:
                cfg[field] = "***"
    return {"items": items, "count": len(items)}


# ─── Rules ────────────────────────────────────────────────────────────────────


@router.post("/rules")
async def create_notification_rule(payload: dict = Body(...), current_user: TokenData = Depends(rbac_service.has_permission("manage:settings"))):
    db = get_database()
    try:
        rule = await notification_service.create_rule(db, get_tenant_id(), payload)
        return {"rule": rule}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/rules")
async def list_notification_rules(current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))):
    db = get_database()
    items = await notification_service.list_rules(db, get_tenant_id())
    return {"items": items, "count": len(items)}
