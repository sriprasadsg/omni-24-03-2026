from fastapi import APIRouter, HTTPException, Depends, Body
import logging
from typing import Dict, Any
from database import get_database
from email_service import email_service
from authentication_service import get_current_user
from auth_types import TokenData
from datetime import datetime, timezone

router = APIRouter(prefix="/api/email", tags=["Email Service"])
logger = logging.getLogger(__name__)

_ADMIN_ROLES = {"Admin", "admin", "Super Admin", "superadmin", "super_admin", "platform-admin"}


@router.get("/config")
async def get_smtp_config(current_user: TokenData = Depends(get_current_user)):
    """Get SMTP configuration (password masked). Admin only."""
    if getattr(current_user, "role", "") not in _ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    tenant_id = getattr(current_user, "tenant_id", None) or None
    db = get_database()
    config = await db.smtp_config.find_one({"tenant_id": tenant_id}, {"_id": 0})
    if config:
        config["smtpPassword"] = "********"
        config.pop("smtpPasswordEncrypted", None)
    return config or {}


@router.post("/config")
async def save_smtp_config(
    config: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user)
):
    """Save SMTP configuration. Admin only."""
    if getattr(current_user, "role", "") not in _ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None) or None
    config["tenant_id"] = tenant_id  # always use token-derived tenant

    if "smtpPassword" in config and config["smtpPassword"] != "********":
        config["smtpPasswordEncrypted"] = email_service.encrypt_password(config["smtpPassword"])
        del config["smtpPassword"]
    elif "smtpPassword" in config and config["smtpPassword"] == "********":
        existing = await db.smtp_config.find_one({"tenant_id": tenant_id})
        if existing:
            config["smtpPasswordEncrypted"] = existing.get("smtpPasswordEncrypted")
        del config["smtpPassword"]

    config["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.smtp_config.update_one({"tenant_id": tenant_id}, {"$set": config}, upsert=True)
    return {"success": True}


@router.post("/test")
async def test_smtp_config(
    config: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user)
):
    """Test SMTP configuration. Admin only."""
    if getattr(current_user, "role", "") not in _ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    tenant_id = getattr(current_user, "tenant_id", None) or None
    if config.get("smtpPassword") == "********":
        db = get_database()
        existing = await db.smtp_config.find_one({"tenant_id": tenant_id})
        if existing:
            config["smtpPasswordEncrypted"] = existing.get("smtpPasswordEncrypted")
        else:
            raise HTTPException(status_code=400, detail="Password required for new config")
    elif "smtpPassword" in config:
        config["smtpPasswordEncrypted"] = email_service.encrypt_password(config["smtpPassword"])
    result = email_service.verify_smtp_config(config)
    if not result["success"]:
        raise HTTPException(status_code=400, detail="SMTP configuration test failed")
    return result


@router.post("/send")
async def send_email(
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user)
):
    """Send a generic email. Admin only."""
    if getattr(current_user, "role", "") not in _ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None) or None
    config = await db.smtp_config.find_one({"tenant_id": tenant_id})
    if not config:
        raise HTTPException(status_code=400, detail="SMTP configuration not found")
    result = email_service.send_email(
        smtp_config=config,
        to_email=payload.get("to", ""),
        subject=payload.get("subject", ""),
        body_text=payload.get("body", ""),
        body_html=payload.get("html"),
    )
    if not result["success"]:
        logger.error("Email send failed for tenant %s: %s", tenant_id, result.get("message"))
        raise HTTPException(status_code=500, detail="Failed to send email")
    return result
