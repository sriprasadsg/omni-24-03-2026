from fastapi import APIRouter, HTTPException, Depends, Body
from typing import Dict, Any
from database import get_database
from email_service import email_service
from datetime import datetime, timezone

router = APIRouter(prefix="/api/email", tags=["Email Service"])

@router.get("/config")
async def get_smtp_config(tenant_id: str = "default"):
    """Get SMTP configuration (password masked)"""
    db = get_database()
    config = await db.smtp_config.find_one({"tenant_id": tenant_id}, {"_id": 0})
    
    if config:
        # Mask password
        config["smtpPassword"] = "********"
        if "smtpPasswordEncrypted" in config:
            del config["smtpPasswordEncrypted"]
            
    return config or {}

@router.post("/config")
async def save_smtp_config(config: Dict[str, Any] = Body(...)):
    """Save SMTP configuration"""
    db = get_database()
    tenant_id = config.get("tenant_id", "default")
    
    # Encrypt password if provided
    if "smtpPassword" in config and config["smtpPassword"] != "********":
        config["smtpPasswordEncrypted"] = email_service.encrypt_password(config["smtpPassword"])
        del config["smtpPassword"] # Don't store plain text
    elif "smtpPassword" in config and config["smtpPassword"] == "********":
        # Keep existing encrypted password
        existing = await db.smtp_config.find_one({"tenant_id": tenant_id})
        if existing:
            config["smtpPasswordEncrypted"] = existing.get("smtpPasswordEncrypted")
        del config["smtpPassword"]
        
    config["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.smtp_config.update_one(
        {"tenant_id": tenant_id},
        {"$set": config},
        upsert=True
    )
    return {"success": True}

@router.post("/test")
async def test_smtp_config(config: Dict[str, Any] = Body(...)):
    """Test SMTP configuration"""
    # If password is masked, fetch from DB
    if config.get("smtpPassword") == "********":
        db = get_database()
        existing = await db.smtp_config.find_one({"tenant_id": config.get("tenant_id", "default")})
        if existing:
            config["smtpPasswordEncrypted"] = existing.get("smtpPasswordEncrypted")
        else:
            raise HTTPException(status_code=400, detail="Password required for new config")
    elif "smtpPassword" in config:
        config["smtpPasswordEncrypted"] = email_service.encrypt_password(config["smtpPassword"])
    
    result = email_service.verify_smtp_config(config)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
        
    return result

@router.post("/send")
async def send_email(payload: Dict[str, Any] = Body(...)):
    """Send a generic email (Admin only)"""
    # Fetch config
    db = get_database()
    tenant_id = payload.get("tenant_id", "default")
    config = await db.smtp_config.find_one({"tenant_id": tenant_id})
    
    if not config:
        raise HTTPException(status_code=400, detail="SMTP configuration not found")
        
    result = email_service.send_email(
        smtp_config=config,
        to_email=payload["to"],
        subject=payload["subject"],
        body_text=payload["body"],
        body_html=payload.get("html")
    )
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
        
    return result
