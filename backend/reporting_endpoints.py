"""
Reporting & Notification Endpoints
SLA compliance reports, vulnerability exposure, change management, and multi-channel notifications.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime, timezone

from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from reporting_service import get_reporting_service
from notification_service import get_notification_service
from tenant_context import set_tenant_id

router = APIRouter(tags=["Reporting & Notifications"])

_ADMIN_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}


def _elevate_if_admin(user: TokenData) -> None:
    """Allow admins to query across all tenants by bypassing tenant isolation."""
    if getattr(user, "role", "") in _ADMIN_ROLES:
        set_tenant_id("platform-admin")


def _resolve_tenant_id(user: TokenData, requested_tenant_id: str | None) -> str | None:
    """Return the effective tenant_id for a report query.

    Super-admins may pass any tenant_id (or None for all-tenants).
    Non-admins are always scoped to their own tenant regardless of what was requested.
    """
    caller_tenant = getattr(user, "tenant_id", None)
    if getattr(user, "role", "") in _ADMIN_ROLES:
        return requested_tenant_id
    return caller_tenant


_NOTIFICATION_CONFIG_FIELDS = {"type", "enabled", "webhook_url", "smtp_host", "smtp_port",
                                "smtp_user", "phone_number", "channel", "routing_key"}


# ── Reports ──────────────────────────────────────────────────────────────────

@router.get("/api/reports/sla-compliance")
async def get_sla_compliance_report(
    tenant_id: str = None,
    framework: str = "SOC2",
    start_date: str = None,
    end_date: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Generate SLA compliance report."""
    try:
        _elevate_if_admin(current_user)
        db = get_database()
        reporting_service = get_reporting_service(db)
        start = datetime.fromisoformat(start_date) if start_date else None
        end = datetime.fromisoformat(end_date) if end_date else None
        return await reporting_service.generate_sla_compliance_report(
            tenant_id=_resolve_tenant_id(current_user, tenant_id),
            framework=framework,
            start_date=start,
            end_date=end,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api/reports/vulnerability-exposure")
async def get_vulnerability_exposure_report(
    tenant_id: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Generate vulnerability exposure report with asset exposure, critical CVEs, and EPSS scores."""
    try:
        _elevate_if_admin(current_user)
        db = get_database()
        reporting_service = get_reporting_service(db)
        return await reporting_service.generate_vulnerability_exposure_report(
            tenant_id=_resolve_tenant_id(current_user, tenant_id)
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api/reports/change-management")
async def get_change_management_log(
    tenant_id: str = None,
    start_date: str = None,
    end_date: str = None,
    limit: int = Query(100, ge=1, le=500),
    current_user: TokenData = Depends(get_current_user),
):
    """Generate ITIL-compliant change management log for audit/compliance."""
    try:
        _elevate_if_admin(current_user)
        db = get_database()
        reporting_service = get_reporting_service(db)
        start = datetime.fromisoformat(start_date) if start_date else None
        end = datetime.fromisoformat(end_date) if end_date else None
        return await reporting_service.generate_change_management_log(
            tenant_id=_resolve_tenant_id(current_user, tenant_id),
            start_date=start,
            end_date=end,
            limit=limit,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api/reports/executive-summary")
async def get_executive_summary(
    tenant_id: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Generate executive-level KPI summary: security posture, compliance, patch velocity, risk exposure."""
    try:
        _elevate_if_admin(current_user)
        db = get_database()
        reporting_service = get_reporting_service(db)
        return await reporting_service.generate_executive_summary(
            tenant_id=_resolve_tenant_id(current_user, tenant_id)
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/reports/schedule")
async def schedule_report(
    data: dict,
    current_user: TokenData = Depends(get_current_user),
):
    """Schedule a recurring compliance report."""
    try:
        db = get_database()
        schedule = {
            "report_type": data.get("report_type"),
            "frequency": data.get("frequency", "weekly"), # daily, weekly, monthly
            "recipients": data.get("recipients", []),
            "tenant_id": getattr(current_user, "tenant_id", None) or None,
            "created_by": current_user.email,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_run": None,
            "next_run": data.get("next_run"), # ISO format
            "active": True
        }
        result = await db.report_schedules.insert_one(schedule)
        schedule["id"] = str(result.inserted_id)
        return schedule
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api/reports/schedules")
async def get_report_schedules(
    current_user: TokenData = Depends(get_current_user),
):
    """Get all active report schedules for the tenant."""
    try:
        db = get_database()
        _rep_role = getattr(current_user, "role", None)
        tenant_id = getattr(current_user, "tenant_id", None) or None
        if not tenant_id and _rep_role not in _ADMIN_ROLES:
            raise HTTPException(status_code=403, detail="Tenant context required")
        _rep_query: dict = {} if _rep_role in _ADMIN_ROLES else {"tenant_id": tenant_id}
        schedules = await db.report_schedules.find(_rep_query).to_list(length=100)
        for s in schedules:
            s["id"] = str(s.pop("_id"))
        return schedules
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")

# ── Notifications ─────────────────────────────────────────────────────────────

@router.post("/api/notifications/send")
async def send_notification(
    data: dict,
    _current_user: TokenData = Depends(get_current_user),
):
    """
    Send multi-channel notification.
    Body: { title, message, severity, recipients, channels, metadata }
    """
    try:
        db = get_database()
        notification_service = get_notification_service(db)
        return await notification_service.send_alert(
            title=data.get("title"),
            message=data.get("message"),
            severity=data.get("severity", "info"),
            recipients=data.get("recipients", []),
            channels=data.get("channels", ["email"]),
            metadata=data.get("metadata"),
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/notifications/config")
async def configure_notifications(
    data: dict,
    _current_user: TokenData = Depends(get_current_user),
):
    """
    Configure a notification channel.
    Body: { type, enabled, config: { webhook_url | smtp_host | phone_number, ... } }
    """
    try:
        db = get_database()
        tenant_id = getattr(_current_user, "tenant_id", None)
        raw_cfg = data.get("config", {})
        safe_cfg = {k: v for k, v in raw_cfg.items() if k in _NOTIFICATION_CONFIG_FIELDS}
        config = {
            "type": data.get("type"),
            "enabled": data.get("enabled", True),
            **safe_cfg,
            "tenant_id": tenant_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.notification_config.update_one(
            {"type": data.get("type"), "tenant_id": tenant_id},
            {"$set": config},
            upsert=True,
        )
        return {"success": True, "message": f"{data.get('type')} notifications configured"}
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api/notifications/config")
async def get_notification_configs(_current_user: TokenData = Depends(get_current_user)):
    """Get all notification channel configurations (sensitive fields redacted)."""
    try:
        db = get_database()
        tenant_id = getattr(_current_user, "tenant_id", None)
        query = {} if getattr(_current_user, "role", "") in _ADMIN_ROLES else {"tenant_id": tenant_id}
        configs = await db.notification_config.find(query, {"_id": 0}).to_list(length=500)
        for config in configs:
            if len(config.get("webhook_url", "")) > 30:
                config["webhook_url"] = config["webhook_url"][:30] + "..."
            if "smtp_password" in config:
                config["smtp_password"] = "***"
        return {"configs": configs}
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api/notifications/history")
async def get_notification_history(
    limit: int = Query(50, ge=1, le=500),
    severity: str = None,
    _current_user: TokenData = Depends(get_current_user),
):
    """Get notification history, optionally filtered by severity."""
    try:
        db = get_database()
        _NOTIF_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}
        user_role = getattr(_current_user, "role", "")
        tenant_id = getattr(_current_user, "tenant_id", None) or getattr(_current_user, "tenantId", None)
        query: dict = {} if user_role in _NOTIF_SUPER_ROLES else {"tenant_id": tenant_id}
        if severity:
            query["severity"] = severity
        notifications = await db.notifications.find(query, {"_id": 0}).sort("sent_at", -1).limit(limit).to_list(length=limit)
        return {"notifications": notifications, "count": len(notifications)}
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
