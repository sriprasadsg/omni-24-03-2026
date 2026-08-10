from fastapi import APIRouter, HTTPException, Depends, Request, Response
from typing import List, Any, Dict, Optional
from pydantic import BaseModel
from database import get_database, mongodb
from authentication_service import get_current_user
from rbac_utils import is_super_admin
from rate_limiter import limiter
from datetime import datetime, timezone
import hashlib
import uuid
import secrets

router = APIRouter(prefix="/api/tenants", tags=["Tenant Management"])

_TENANT_ADMIN_ROLES = {"Admin", "Tenant Admin", "tenant_admin"}


def _assert_tenant_access(current_user, tenant_id: str) -> None:
    """Raise 403 unless caller is a super-admin or owns the tenant."""
    if is_super_admin(getattr(current_user, "role", "")):
        return
    caller_tenant = getattr(current_user, "tenant_id", None) or getattr(current_user, "tenantId", None)
    if caller_tenant != tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this tenant")

class TenantCreate(BaseModel):
    name: str
    subscriptionTier: str = "Free"
    enabledFeatures: List[str] = [
        "view:dashboard", "view:cxo_dashboard", "view:profile", "view:insights", 
        "view:tracing", "view:logs", "view:network", "view:agents", "view:assets", 
        "view:patching", "view:security", "view:cloud_security", "view:threat_hunting", 
        "view:dspm", "view:attack_path", "view:sbom", "view:persistence", 
        "view:vulnerabilities", "view:devsecops", "view:dora_metrics", "view:service_catalog", 
        "view:chaos", "view:compliance", "view:ai_governance", "view:security_audit", 
        "view:audit_log", "view:reporting", "view:automation", "view:finops", 
        "view:developer_hub", "view:advanced_bi", "view:llmops", "view:unified_ops",
        "view:swarm", "manage:settings", "manage:tenants", "view:itam", "manage:itam"
    ]
    notificationPreferences: Dict[str, Any] = {}

@router.get("")
async def get_tenants(current_user = Depends(get_current_user)):
    """List all tenants. Super Admin only."""
    if not is_super_admin(getattr(current_user, "role", "")):
        raise HTTPException(status_code=403, detail="Super Admin access required")
    tenants = await mongodb.db.tenants.find({}, {"_id": 0}).to_list(length=1000)

    # Batch agent counts via a single aggregation instead of one query per tenant
    pipeline = [{"$group": {"_id": "$tenantId", "count": {"$sum": 1}}}]
    count_cursor = mongodb.db.agents.aggregate(pipeline)
    agent_counts = {doc["_id"]: doc["count"] async for doc in count_cursor}

    for tenant in tenants:
        tenant["agentCount"] = agent_counts.get(tenant.get("id"), 0)

    return tenants

@router.post("")
async def create_tenant(data: TenantCreate, current_user = Depends(get_current_user)):
    """Create a new tenant"""
    # Authorization Check
    if not is_super_admin(getattr(current_user, "role", "")):
        raise HTTPException(status_code=403, detail="Only Super Admin can create tenants")
    
    # Use raw mongodb.db
    
    # Check duplicate
    existing = await mongodb.db.tenants.find_one({"name": data.name})
    if existing:
        raise HTTPException(status_code=400, detail="Tenant already exists")
        
    tenant_id = f"tenant_{uuid.uuid4().hex[:12]}"
    registration_key = f"reg_{uuid.uuid4().hex}"
    
    tenant_doc = {
        "id": tenant_id,
        "name": data.name,
        "subscriptionTier": data.subscriptionTier,
        "registrationKey": registration_key,
        "enabledFeatures": data.enabledFeatures,
        "notificationPreferences": data.notificationPreferences,
        "emailConfig": {},
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "updatedAt": datetime.now(timezone.utc).isoformat()
    }
    
    await mongodb.db.tenants.insert_one(tenant_doc)
    
    # Remove _id
    if "_id" in tenant_doc:
        del tenant_doc["_id"]
        
    return tenant_doc

@router.post("/lookup-key")
@limiter.limit("5/minute")
async def lookup_tenant_key(request: Request, response: Response, payload: dict):
    """
    Lookup tenant ID by registration key.
    Public endpoint for agents/installers.
    Rate-limited to 5/minute per IP to limit key enumeration.
    Returns generic error on failure to prevent distinguishing invalid vs non-existent keys.
    """
    key = payload.get("registrationKey")
    if not key or len(key) < 16:
        raise HTTPException(status_code=400, detail="Registration key required")

    tenant = await mongodb.db.tenants.find_one({"registrationKey": key})
    if not tenant:
        # Generic message — do not reveal whether the key format was valid
        raise HTTPException(status_code=404, detail="Invalid registration key")

    return {
        "success": True,
        "tenantId": tenant["id"],
        "name": tenant["name"]
    }

class TenantUpdate(BaseModel):
    enabledFeatures: List[str] | None = None
    subscriptionTier: str | None = None
    voiceBotSettings: Dict[str, Any] | None = None


@router.patch("/{tenant_id}")
async def update_tenant(tenant_id: str, data: TenantUpdate, current_user =Depends(get_current_user)):
    """
    Update tenant's subscription tier and enabled features.
    Only Super Admin can update tenant configuration.
    """
    # Check permissions
    caller_role = getattr(current_user, "role", "")
    caller_tenant = getattr(current_user, "tenant_id", None)  # TokenData uses tenant_id (snake_case)

    if not is_super_admin(caller_role):
        # Non-super-admins may only update their own tenant
        if caller_tenant != tenant_id:
            raise HTTPException(status_code=403, detail="Not authorized to update this tenant")

        # Subscription tier and feature flags are billing-controlled — only super admin may change them
        if data.subscriptionTier is not None or data.enabledFeatures is not None:
            raise HTTPException(
                status_code=403,
                detail="Subscription tier and feature changes require Super Admin. Contact support to upgrade.",
            )
             
    
    # Use raw mongodb.db
    
    # Check if tenant exists
    tenant = await mongodb.db.tenants.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Build update data only with provided fields
    update_data = {"updatedAt": datetime.now(timezone.utc).isoformat()}
    
    if data.enabledFeatures is not None:
        update_data["enabledFeatures"] = data.enabledFeatures
    if data.subscriptionTier is not None:
        update_data["subscriptionTier"] = data.subscriptionTier
    if data.voiceBotSettings is not None:
        update_data["voiceBotSettings"] = data.voiceBotSettings
    
    result = await mongodb.db.tenants.update_one(
        {"id": tenant_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        # Tenant exists but no changes were made (same data)
        pass
    
    # Fetch and return updated tenant
    updated_tenant = await mongodb.db.tenants.find_one({"id": tenant_id}, {"_id": 0})
    return updated_tenant

@router.delete("/{tenant_id}")
async def delete_tenant(tenant_id: str, current_user = Depends(get_current_user)):
    """
    Delete a tenant and all associated users.
    Only Super Admin can delete tenants.
    """
    # Check if user is Super Admin
    if not is_super_admin(getattr(current_user, "role", "")):
        raise HTTPException(status_code=403, detail="Only Super Admin can delete tenants")
    
    db = get_database() # We need isolated DB for users/agents to delete correctly? 
    # Actually users/agents have tenantId, so isolation might help or hinder?
    # db.users.delete_many({"tenantId": tenant_id}) -> if context is super admin (no tenant), it inserts tenantId=None?
    # Wait, isolation injects filter `tenantId: current_user.tenantId`.
    # If Super Admin, tenantId might be "platform-admin" or None.
    # If "platform-admin", isolation is skipped.
    
    # So we can use db.users if isolation is skipped.
    # But for tenants collection, we MUST use raw.
    
    # Check if tenant exists
    tenant = await mongodb.db.tenants.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Delete all users associated with this tenant
    # Using raw db to be safe and explicit
    await mongodb.db.users.delete_many({"tenantId": tenant_id})
    
    # Delete all agents associated with this tenant
    await mongodb.db.agents.delete_many({"tenantId": tenant_id})
    
    # Delete the tenant
    result = await mongodb.db.tenants.delete_one({"id": tenant_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    return {
        "success": True,
        "message": f"Tenant {tenant['name']} and all associated data deleted successfully"
    }

class BrandingConfig(BaseModel):
    logoUrl: Optional[str] = None
    primaryColor: Optional[str] = None
    companyName: Optional[str] = None

@router.get("/{tenant_id}/branding")
async def get_tenant_branding(tenant_id: str, current_user=Depends(get_current_user)):
    is_admin = getattr(current_user, "role", "") in ("Super Admin", "super_admin", "admin", "platform-admin")
    caller_tenant = getattr(current_user, "tenant_id", None) or getattr(current_user, "tenantId", None)
    if not is_admin and caller_tenant != tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    tenant = await mongodb.db.tenants.find_one({"id": tenant_id}, {"branding": 1, "_id": 0})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
        
    return tenant.get("branding", {})

@router.post("/{tenant_id}/branding")
async def update_tenant_branding(
    tenant_id: str, 
    branding: BrandingConfig, 
    current_user = Depends(get_current_user)
):
    """
    Update tenant branding.
    Allowed for:
    - Super Admin
    - Tenant Admin of THAT tenant
    """
    # Authorization Check
    if not is_super_admin(getattr(current_user, "role", "")):
        # Tenant Admins may update branding for their own tenant
        _admin_roles = {"Admin", "Tenant Admin", "tenant_admin", "admin"}
        if current_user.tenantId != tenant_id or current_user.role not in _admin_roles:
            raise HTTPException(status_code=403, detail="Not authorized to update branding for this tenant")

    # Update
    result = await mongodb.db.tenants.update_one(
        {"id": tenant_id},
        {"$set": {"branding": branding.dict(exclude_unset=True), "updatedAt": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return {"success": True, "message": "Branding updated"}


# ── API Key Management ────────────────────────────────────────────────────────

@router.post("/{tenant_id}/api-keys")
async def generate_api_key(
    tenant_id: str,
    data: Dict[str, Any],
    current_user=Depends(get_current_user),
):
    """Generate a new API key for the tenant. Returns the plaintext key once — store it safely."""
    _is_super_admin = is_super_admin(getattr(current_user, "role", ""))
    is_own_admin = (
        getattr(current_user, "tenant_id", None) == tenant_id
        and getattr(current_user, "role", "") in ("Admin", "Tenant Admin", "tenant_admin")
    )
    if not _is_super_admin and not is_own_admin:
        raise HTTPException(status_code=403, detail="Not authorized to manage API keys for this tenant")

    tenant = await mongodb.db.tenants.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    plaintext = f"omni_sk_{secrets.token_urlsafe(32)}"
    key_id = f"key-{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc).isoformat()

    key_doc = {
        "id": key_id,
        "name": data.get("name", "API Key"),
        "key": plaintext[:12] + "••••••••••••",   # store only prefix for display
        "keyHash": hashlib.sha256(plaintext.encode()).hexdigest(),
        "createdAt": now,
        "userId": data.get("userId") or getattr(current_user, "username", ""),
    }
    await mongodb.db.tenants.update_one(
        {"id": tenant_id},
        {"$push": {"apiKeys": key_doc}},
    )
    return {"id": key_id, "name": key_doc["name"], "key": plaintext, "createdAt": now}


# ── Email Configuration ───────────────────────────────────────────────────────

@router.get("/{tenant_id}/email/config")
async def get_email_config(tenant_id: str, current_user=Depends(get_current_user)):
    _assert_tenant_access(current_user, tenant_id)
    tenant = await mongodb.db.tenants.find_one({"id": tenant_id}, {"emailConfig": 1, "_id": 0})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    config = dict(tenant.get("emailConfig", {}))
    smtp_password_set = bool(config.pop("smtpPassword", None))
    return {"success": True, "config": config, "smtpPasswordSet": smtp_password_set}


def _encrypt_smtp_password(plaintext: str) -> str:
    """Encrypt an SMTP password with Fernet; falls back to a tagged plaintext if key unset."""
    import os as _os
    key = _os.getenv("INTEGRATION_ENCRYPTION_KEY", "")
    if not key:
        return plaintext
    try:
        from cryptography.fernet import Fernet
        return "enc:" + Fernet(key.encode() if isinstance(key, str) else key).encrypt(plaintext.encode()).decode()
    except Exception:
        return plaintext


@router.post("/{tenant_id}/email/config")
async def save_email_config(tenant_id: str, data: Dict[str, Any], current_user=Depends(get_current_user)):
    _assert_tenant_access(current_user, tenant_id)
    tenant = await mongodb.db.tenants.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    existing = tenant.get("emailConfig", {})
    # Preserve existing (already encrypted) password if blank submitted
    if not data.get("smtpPassword"):
        data["smtpPassword"] = existing.get("smtpPassword", "")
    elif not data["smtpPassword"].startswith("enc:"):
        data["smtpPassword"] = _encrypt_smtp_password(data["smtpPassword"])
    await mongodb.db.tenants.update_one(
        {"id": tenant_id},
        {"$set": {"emailConfig": data, "updatedAt": datetime.now(timezone.utc).isoformat()}}
    )
    return {"success": True, "message": "Email configuration saved"}


@router.post("/{tenant_id}/email/test")
async def test_email_config(tenant_id: str, data: Dict[str, Any], current_user=Depends(get_current_user)):
    _assert_tenant_access(current_user, tenant_id)
    tenant = await mongodb.db.tenants.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    cfg = tenant.get("emailConfig", {})
    if not cfg.get("smtpHost"):
        return {"success": False, "message": "SMTP not configured — save a configuration first"}

    from email_service import email_service as _es
    smtp_cfg = {
        "smtpHost": cfg.get("smtpHost", ""),
        "smtpPort": int(cfg.get("smtpPort", 587)),
        "smtpUser": cfg.get("smtpUser", ""),
        "smtpPasswordEncrypted": cfg.get("smtpPassword", ""),
        "useTLS": cfg.get("useTLS", True),
    }
    result = await _es.verify_smtp_config(smtp_cfg)
    if not result.get("success"):
        return result

    # Optionally send a test message
    test_email = data.get("testEmail", "")
    if test_email:
        send_cfg = {**smtp_cfg, "from_email": cfg.get("fromEmail", smtp_cfg["smtpUser"])}
        await _es.send_email(
            to_email=test_email,
            subject="Omni-Agent SMTP Test",
            html_content="<p>SMTP connectivity test from Omni-Agent platform. Your email configuration is working correctly.</p>",
            smtp_config=send_cfg,
        )
    return {"success": True, "message": f"SMTP connection verified{' and test email sent to ' + test_email if test_email else ''} via {cfg['smtpHost']}"}


@router.get("/{tenant_id}/email/preferences")
async def get_email_preferences(tenant_id: str, current_user=Depends(get_current_user)):
    _assert_tenant_access(current_user, tenant_id)
    tenant = await mongodb.db.tenants.find_one({"id": tenant_id}, {"notificationPreferences": 1, "_id": 0})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    prefs = tenant.get("notificationPreferences", {})
    defaults = {
        "emailVerification": True, "alertNotifications": True,
        "reportDelivery": True, "weeklyDigest": False,
        "criticalAlertsOnly": False, "recipients": []
    }
    return {"success": True, "preferences": {**defaults, **prefs}}


@router.put("/{tenant_id}/email/preferences")
async def save_email_preferences(tenant_id: str, data: Dict[str, Any], current_user=Depends(get_current_user)):
    _assert_tenant_access(current_user, tenant_id)
    result = await mongodb.db.tenants.update_one(
        {"id": tenant_id},
        {"$set": {"notificationPreferences": data, "updatedAt": datetime.now(timezone.utc).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"success": True, "message": "Preferences saved"}


@router.delete("/{tenant_id}/api-keys/{key_id}")
async def revoke_api_key(
    tenant_id: str,
    key_id: str,
    current_user=Depends(get_current_user),
):
    """Revoke (delete) an API key for the tenant."""
    _is_super_admin = is_super_admin(getattr(current_user, "role", ""))
    is_own_admin = (
        getattr(current_user, "tenant_id", None) == tenant_id
        and getattr(current_user, "role", "") in ("Admin", "Tenant Admin", "tenant_admin")
    )
    if not _is_super_admin and not is_own_admin:
        raise HTTPException(status_code=403, detail="Not authorized to manage API keys for this tenant")

    result = await mongodb.db.tenants.update_one(
        {"id": tenant_id},
        {"$pull": {"apiKeys": {"id": key_id}}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"success": True}
