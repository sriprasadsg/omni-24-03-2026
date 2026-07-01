"""
Payment gateway configuration and payment method endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional
from authentication_service import get_current_user
from auth_types import TokenData
from database import get_database
from payment_gateway_service import PaymentGatewayFactory, PaymentGatewayType
from encryption_service import get_encryption_service
from datetime import datetime, timezone
import logging

router = APIRouter(prefix="/api/payments", tags=["Payments"])
logger = logging.getLogger(__name__)


class PaymentGatewaySetup(BaseModel):
    gateway: PaymentGatewayType
    credentials: Dict[str, str]
    gateway_name: Optional[str] = None
    webhook_url: Optional[str] = None


class PaymentMethodCreate(BaseModel):
    payment_method_id: str


async def get_tenant_gateway(db, tenant_id: str):
    """Get the active payment gateway for a tenant."""
    gateway_config = await db.payment_gateways.find_one({"tenantId": tenant_id, "isActive": True})
    if not gateway_config:
        raise HTTPException(status_code=404, detail="No payment gateway configured for this tenant")
    encryption = get_encryption_service()
    decrypted_credentials = {k: encryption.decrypt(v) for k, v in gateway_config["credentials"].items()}
    gateway = PaymentGatewayFactory.create_gateway(
        PaymentGatewayType(gateway_config["gateway"]), decrypted_credentials
    )
    return gateway, gateway_config


@router.post("/setup")
async def setup_payment_gateway(
    setup: PaymentGatewaySetup,
    current_user: TokenData = Depends(get_current_user),
):
    """Configure payment gateway for tenant."""
    db = get_database()
    tenant_id = current_user.tenant_id
    encryption = get_encryption_service()
    encrypted_credentials = {k: encryption.encrypt(v) for k, v in setup.credentials.items()}

    existing = await db.payment_gateways.find_one({"tenantId": tenant_id, "gateway": setup.gateway.value})
    if existing:
        await db.payment_gateways.update_one(
            {"tenantId": tenant_id, "gateway": setup.gateway.value},
            {"$set": {"credentials": encrypted_credentials,
                      "updatedAt": datetime.now(timezone.utc).isoformat()}},
        )
        result_id = str(existing["_id"])
    else:
        existing_count = await db.payment_gateways.count_documents({"tenantId": tenant_id})
        gateway_doc = {
            "tenantId": tenant_id,
            "gateway": setup.gateway.value,
            "gatewayName": setup.gateway_name or setup.gateway.value.capitalize(),
            "isActive": existing_count == 0,
            "isCustom": setup.gateway == PaymentGatewayType.CUSTOM,
            "webhookUrl": setup.webhook_url,
            "credentials": encrypted_credentials,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "createdBy": current_user.username,
        }
        result = await db.payment_gateways.insert_one(gateway_doc)
        result_id = str(result.inserted_id)

    return {
        "success": True,
        "message": f"{setup.gateway.value.capitalize()} gateway configured successfully",
        "gatewayId": result_id,
    }


@router.get("/configured-gateways")
async def get_configured_gateways(current_user: TokenData = Depends(get_current_user)):
    """Get all configured payment gateways for this tenant."""
    db = get_database()
    tenant_id = current_user.tenant_id
    cursor = db.payment_gateways.find({"tenantId": tenant_id}, {"_id": 0, "credentials": 0})
    gateways = []
    async for doc in cursor:
        gateways.append({
            "gateway":     doc.get("gateway"),
            "gatewayName": doc.get("gatewayName") or doc.get("gateway", "").capitalize(),
            "isActive":    doc.get("isActive", False),
            "isCustom":    doc.get("isCustom", False),
            "webhookUrl":  doc.get("webhookUrl"),
            "createdAt":   doc.get("createdAt"),
            "createdBy":   doc.get("createdBy"),
        })
    return {"success": True, "gateways": gateways}


@router.post("/gateways/{gateway_type}/activate")
async def activate_gateway(
    gateway_type: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Set a specific gateway as the active one."""
    db = get_database()
    tenant_id = current_user.tenant_id
    existing = await db.payment_gateways.find_one({"tenantId": tenant_id, "gateway": gateway_type})
    if not existing:
        raise HTTPException(status_code=404, detail="Gateway not found")
    await db.payment_gateways.update_many({"tenantId": tenant_id}, {"$set": {"isActive": False}})
    await db.payment_gateways.update_one(
        {"tenantId": tenant_id, "gateway": gateway_type}, {"$set": {"isActive": True}}
    )
    return {"success": True, "message": f"{gateway_type.capitalize()} set as active gateway"}


@router.delete("/gateways/{gateway_type}")
async def delete_gateway(
    gateway_type: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Remove a payment gateway configuration."""
    db = get_database()
    tenant_id = current_user.tenant_id
    result = await db.payment_gateways.delete_one({"tenantId": tenant_id, "gateway": gateway_type})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Gateway not found")
    return {"success": True, "message": f"{gateway_type.capitalize()} gateway removed"}


@router.get("/methods")
async def get_payment_methods(current_user: TokenData = Depends(get_current_user)):
    """List payment methods."""
    db = get_database()
    tenant_id = current_user.tenant_id
    try:
        gateway, _ = await get_tenant_gateway(db, tenant_id)
    except HTTPException:
        return {"success": True, "methods": []}
    customer_doc = await db.payment_customers.find_one({"tenantId": tenant_id})
    if not customer_doc:
        return {"success": True, "methods": []}
    methods = await gateway.list_payment_methods(customer_doc["gatewayCustomerId"])
    return {"success": True, "methods": methods}


@router.post("/methods")
async def add_payment_method(
    method: PaymentMethodCreate,
    current_user: TokenData = Depends(get_current_user),
):
    """Add a payment method."""
    db = get_database()
    tenant_id = current_user.tenant_id
    gateway, gateway_config = await get_tenant_gateway(db, tenant_id)
    customer_doc = await db.payment_customers.find_one({"tenantId": tenant_id})
    if not customer_doc:
        user_doc = await db.users.find_one({"email": current_user.username})
        user_name = user_doc.get("name") if user_doc else current_user.username
        customer = await gateway.create_customer(
            email=current_user.username, name=user_name, metadata={"tenantId": tenant_id}
        )
        customer_doc = {
            "tenantId": tenant_id, "gateway": gateway_config["gateway"],
            "gatewayCustomerId": customer["id"], "email": current_user.username,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        await db.payment_customers.insert_one(customer_doc)
    result = await gateway.add_payment_method(customer_doc["gatewayCustomerId"], method.payment_method_id)
    return {"success": True, "method": result}


@router.delete("/methods/{method_id}")
async def delete_payment_method(
    method_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Delete a payment method."""
    db = get_database()
    tenant_id = current_user.tenant_id
    gateway, _ = await get_tenant_gateway(db, tenant_id)
    success = await gateway.delete_payment_method(method_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to remove payment method")
    return {"success": True}
