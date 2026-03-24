from fastapi import APIRouter, HTTPException, Depends
from typing import List, Any, Dict, Optional
from pydantic import BaseModel
from database import get_database, mongodb
from authentication_service import get_current_user
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/api/tenants", tags=["Tenant Management"])

class TenantCreate(BaseModel):
    name: str
    subscriptionTier: str = "Enterprise"
    enabledFeatures: List[str] = [
        "view:dashboard", "view:cxo_dashboard", "view:profile", "view:insights", 
        "view:tracing", "view:logs", "view:network", "view:agents", "view:assets", 
        "view:patching", "view:security", "view:cloud_security", "view:threat_hunting", 
        "view:dspm", "view:attack_path", "view:sbom", "view:persistence", 
        "view:vulnerabilities", "view:devsecops", "view:dora_metrics", "view:service_catalog", 
        "view:chaos", "view:compliance", "view:ai_governance", "view:security_audit", 
        "view:audit_log", "view:reporting", "view:automation", "view:finops", 
        "view:developer_hub", "view:advanced_bi", "view:llmops", "view:unified_ops", 
        "view:swarm", "manage:settings", "manage:tenants"
    ]
    notificationPreferences: Dict[str, Any] = {}

@router.get("")
async def get_tenants(current_user = Depends(get_current_user)):
    """
    List all tenants (Super Admin only usually, but open for now for debugging).
    """
    # Use raw mongodb.db to bypass tenant isolation
    tenants = await mongodb.db.tenants.find({}, {"_id": 0}).to_list(length=1000)
    
    # Attach agent count for each tenant
    for tenant in tenants:
        tenant_id = tenant.get("id")
        if tenant_id:
            agent_count = await mongodb.db.agents.count_documents({"tenantId": tenant_id})
            tenant["agentCount"] = agent_count
        else:
            tenant["agentCount"] = 0
            
    return tenants

@router.post("")
async def create_tenant(data: TenantCreate, current_user = Depends(get_current_user)):
    """Create a new tenant"""
    # Authorization Check
    if current_user.role != "Super Admin":
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
async def lookup_tenant_key(payload: dict):
    """
    Lookup tenant ID by registration key.
    Public endpoint for agents/installers.
    """
    key = payload.get("registrationKey")
    if not key:
        raise HTTPException(status_code=400, detail="Registration key required")
        
    # Public endpoint, no context issues usually, but safer to use raw
    tenant = await mongodb.db.tenants.find_one({"registrationKey": key})
    
    if not tenant:
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
    # Debug logging
    print(f"[DEBUG] Updating tenant {tenant_id}")
    print(f"[DEBUG] Received data: {data.model_dump()}")
    print(f"[DEBUG] User role: {current_user.role}")
    
    # Check permissions
    if current_user.role != "Super Admin":
        # Tenant Admins can only update their own tenant's voiceBotSettings
        if current_user.tenantId != tenant_id or current_user.role != "Admin":
            raise HTTPException(status_code=403, detail="Not authorized to update this tenant")
        
        # Ensure they are not trying to update restricted fields
        if data.enabledFeatures is not None or data.subscriptionTier is not None:
             raise HTTPException(status_code=403, detail="Only Super Admin can update features and subscription tier")
             
    
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
    
    print(f"[DEBUG] Update data: {update_data}")
    
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
    if current_user.role != "Super Admin":
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
async def get_tenant_branding(tenant_id: str):
    """
    Get branding configuration for a specific tenant.
    Public endpoint logic (or minimal auth) to allow login page to fetch it?
    For now, authenticated.
    """
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
    if current_user.role != "Super Admin":
        # Check if user belongs to this tenant and is Admin
        if current_user.tenantId != tenant_id or current_user.role != "Admin":
             raise HTTPException(status_code=403, detail="Not authorized to update branding for this tenant")

    # Update
    result = await mongodb.db.tenants.update_one(
        {"id": tenant_id},
        {"$set": {"branding": branding.dict(exclude_unset=True), "updatedAt": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Tenant not found")
        
    return {"success": True, "message": "Branding updated"}
