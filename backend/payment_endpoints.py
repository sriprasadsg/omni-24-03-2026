from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import BaseModel, EmailStr
from typing import Dict, List, Optional, Any
from authentication_service import get_current_user
from auth_types import TokenData
from database import get_database
from payment_gateway_service import PaymentGatewayFactory, PaymentGatewayType
from encryption_service import get_encryption_service
from datetime import datetime, timezone
import logging

router = APIRouter(prefix="/api/payments", tags=["Payments"])
logger = logging.getLogger(__name__)


# --- Request/Response Models ---

class PaymentGatewaySetup(BaseModel):
    gateway: PaymentGatewayType
    credentials: Dict[str, str]  # e.g., {"secret_key": "sk_...", "publishable_key": "pk_..."}


class SubscriptionCreate(BaseModel):
    plan: str  # "Pro", "Enterprise", "Custom"
    price_id: str  # Gateway-specific price ID


class ChargeCreate(BaseModel):
    amount: int  # Amount in cents
    currency: str = "USD"
    description: str


class RefundCreate(BaseModel):
    charge_id: str
    amount: Optional[int] = None  # Partial refund if specified


class PaymentMethodCreate(BaseModel):
    payment_method_id: str


# --- Helper Functions ---

async def get_tenant_gateway(db, tenant_id: str):
    """Get the active payment gateway for a tenant"""
    gateway_config = await db.payment_gateways.find_one({
        "tenantId": tenant_id,
        "isActive": True
    })
    
    if not gateway_config:
        raise HTTPException(status_code=404, detail="No payment gateway configured for this tenant")
    
    # Decrypt credentials
    encryption = get_encryption_service()
    decrypted_credentials = {}
    for key, value in gateway_config["credentials"].items():
        decrypted_credentials[key] = encryption.decrypt(value)
    
    # Create gateway instance
    gateway = PaymentGatewayFactory.create_gateway(
        PaymentGatewayType(gateway_config["gateway"]),
        decrypted_credentials
    )
    
    return gateway, gateway_config


# --- Endpoints ---

@router.post("/setup")
async def setup_payment_gateway(
    setup: PaymentGatewaySetup,
    current_user: TokenData = Depends(get_current_user)
):
    """Configure payment gateway for tenant"""
    db = get_database()
    tenant_id = current_user.tenant_id
    
    # Encrypt credentials
    encryption = get_encryption_service()
    encrypted_credentials = {}
    for key, value in setup.credentials.items():
        encrypted_credentials[key] = encryption.encrypt(value)
    
    # Deactivate existing gateways
    await db.payment_gateways.update_many(
        {"tenantId": tenant_id},
        {"$set": {"isActive": False}}
    )
    
    # Insert new gateway configuration
    gateway_doc = {
        "tenantId": tenant_id,
        "gateway": setup.gateway.value,
        "isActive": True,
        "credentials": encrypted_credentials,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "createdBy": current_user.username
    }
    
    result = await db.payment_gateways.insert_one(gateway_doc)
    

    return {
        "success": True,
        "message": f"{setup.gateway.value.capitalize()} gateway configured successfully",
        "gatewayId": str(result.inserted_id)
    }


@router.get("/configured-gateways")
async def get_configured_gateways(
    current_user: TokenData = Depends(get_current_user)
):
    """Get list of configured and active payment gateways"""
    db = get_database()
    tenant_id = current_user.tenant_id
    
    cursor = db.payment_gateways.find({
        "tenantId": tenant_id,
        "isActive": True
    })
    
    gateways = []
    async for doc in cursor:
        gateways.append({
            "gateway": doc["gateway"],
            "createdAt": doc["createdAt"]
        })
        
    return {
        "success": True,
        "gateways": gateways
    }


@router.get("/methods")
async def get_payment_methods(
    current_user: TokenData = Depends(get_current_user)
):
    """List payment methods"""
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
    current_user: TokenData = Depends(get_current_user)
):
    """Add a payment method"""
    db = get_database()
    tenant_id = current_user.tenant_id
    
    gateway, gateway_config = await get_tenant_gateway(db, tenant_id)
    customer_doc = await db.payment_customers.find_one({"tenantId": tenant_id})
    
    if not customer_doc:
        # Create customer if not exists
        user_doc = await db.users.find_one({"email": current_user.username})
        user_name = user_doc.get("name") if user_doc else current_user.username
        
        customer = await gateway.create_customer(
            email=current_user.username,
            name=user_name,
            metadata={"tenantId": tenant_id}
        )
        
        customer_doc = {
            "tenantId": tenant_id,
            "gateway": gateway_config["gateway"],
            "gatewayCustomerId": customer["id"],
            "email": current_user.username,
            "createdAt": datetime.now(timezone.utc).isoformat()
        }
        await db.payment_customers.insert_one(customer_doc)
        
    result = await gateway.add_payment_method(
        customer_doc["gatewayCustomerId"], 
        method.payment_method_id
    )
    
    return {"success": True, "method": result}


@router.delete("/methods/{method_id}")
async def delete_payment_method(
    method_id: str,
    current_user: TokenData = Depends(get_current_user)
):
    """Delete a payment method"""
    db = get_database()
    tenant_id = current_user.tenant_id
    
    gateway, _ = await get_tenant_gateway(db, tenant_id)
    
    success = await gateway.delete_payment_method(method_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to remove payment method")
        
    return {"success": True}


@router.post("/subscribe")
async def create_subscription(
    subscription: SubscriptionCreate,
    current_user: TokenData = Depends(get_current_user)
):
    """Create a subscription for the tenant"""
    db = get_database()
    tenant_id = current_user.tenant_id
    
    # Get payment gateway
    gateway, gateway_config = await get_tenant_gateway(db, tenant_id)
    
    # Check if customer exists
    customer_doc = await db.payment_customers.find_one({"tenantId": tenant_id})
    
    if not customer_doc:
        # Fetch user name from DB since TokenData doesn't have it
        user_doc = await db.users.find_one({"email": current_user.username})
        user_name = user_doc.get("name") if user_doc else current_user.username
        
        # Create customer in payment gateway
        customer = await gateway.create_customer(
            email=current_user.username,
            name=user_name,
            metadata={"tenantId": tenant_id}
        )
        
        # Store customer ID
        customer_doc = {
            "tenantId": tenant_id,
            "gateway": gateway_config["gateway"],
            "gatewayCustomerId": customer["id"],
            "email": current_user.username,
            "createdAt": datetime.now(timezone.utc).isoformat()
        }
        await db.payment_customers.insert_one(customer_doc)
    
    # Create subscription
    sub = await gateway.create_subscription(
        customer_id=customer_doc["gatewayCustomerId"],
        price_id=subscription.price_id,
        metadata={"tenantId": tenant_id, "plan": subscription.plan}
    )
    
    # Store subscription
    subscription_doc = {
        "tenantId": tenant_id,
        "gateway": gateway_config["gateway"],
        "gatewaySubscriptionId": sub["id"],
        "plan": subscription.plan,
        "status": sub["status"],
        "currentPeriodStart": datetime.fromtimestamp(sub["current_period_start"], tz=timezone.utc).isoformat(),
        "currentPeriodEnd": datetime.fromtimestamp(sub["current_period_end"], tz=timezone.utc).isoformat(),
        "amount": sub["plan"]["amount"] / 100,  # Convert from cents
        "currency": sub["plan"]["currency"],
        "interval": sub["plan"]["interval"],
        "createdAt": datetime.now(timezone.utc).isoformat()
    }
    await db.subscriptions.insert_one(subscription_doc)
    
    # Update tenant subscription tier
    await db.tenants.update_one(
        {"id": tenant_id},
        {"$set": {"subscriptionTier": subscription.plan}}
    )
    
    return {
        "success": True,
        "subscription": subscription_doc
    }


@router.post("/charge")
async def create_charge(
    charge: ChargeCreate,
    current_user: TokenData = Depends(get_current_user)
):
    """Create a one-time charge"""
    db = get_database()
    tenant_id = current_user.tenant_id
    
    # Get payment gateway and customer
    gateway, gateway_config = await get_tenant_gateway(db, tenant_id)
    customer_doc = await db.payment_customers.find_one({"tenantId": tenant_id})
    
    if not customer_doc:
        raise HTTPException(status_code=404, detail="No payment customer found. Please set up payment method first.")
    
    # Create charge
    charge_result = await gateway.create_charge(
        customer_id=customer_doc["gatewayCustomerId"],
        amount=charge.amount,
        currency=charge.currency,
        description=charge.description,
        metadata={"tenantId": tenant_id}
    )
    
    # Store charge record
    charge_doc = {
        "tenantId": tenant_id,
        "gateway": gateway_config["gateway"],
        "gatewayChargeId": charge_result["id"],
        "amount": charge_result["amount"] / 100,
        "currency": charge_result["currency"],
        "description": charge.description,
        "status": charge_result["status"],
        "paid": charge_result["paid"],
        "createdAt": datetime.fromtimestamp(charge_result["created"], tz=timezone.utc).isoformat()
    }
    await db.charges.insert_one(charge_doc)
    
    return {
        "success": True,
        "charge": charge_doc
    }


@router.get("/invoices")
async def get_invoices(
    limit: int = 10,
    current_user: TokenData = Depends(get_current_user)
):
    """Get invoices for the tenant"""
    db = get_database()
    tenant_id = current_user.tenant_id
    
    # Get from database
    invoices = await db.invoices.find(
        {"tenantId": tenant_id}
    ).sort("createdAt", -1).limit(limit).to_list(length=limit)
    
    # Remove _id field
    for invoice in invoices:
        invoice.pop("_id", None)
    

    return {
        "success": True,
        "invoices": invoices
    }


@router.get("/invoices/{invoice_id}/pdf")
async def download_invoice_pdf(
    invoice_id: str,
    current_user: TokenData = Depends(get_current_user)
):
    """Generate and download invoice PDF"""
    db = get_database()
    tenant_id = current_user.tenant_id
    
    # Get invoice
    # Note: If invoice_id is not a valid ObjectId, we might need error handling
    # Assuming string ID for now, or match format in DB
    invoice = await db.invoices.find_one({
        "invoiceNumber": invoice_id, 
        "tenantId": tenant_id
    })
    
    if not invoice:
        # Try finding by gateway ID or internal ID if not found by number
        invoice = await db.invoices.find_one({
            "gatewayInvoiceId": invoice_id,
            "tenantId": tenant_id
        })
        
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    # Get tenant details for PDF
    tenant = await db.tenants.find_one({"id": tenant_id})
    if not tenant:
        tenant = {"name": "Valued Customer", "id": tenant_id}
        
    # Generate PDF
    from invoice_generator import InvoiceGenerator
    from fastapi.responses import StreamingResponse
    
    pdf_buffer = InvoiceGenerator.generate_pdf(invoice, tenant)
    
    filename = f"invoice_{invoice.get('invoiceNumber', 'draft')}.pdf"
    
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.post("/cancel-subscription")
async def cancel_subscription(
    current_user: TokenData = Depends(get_current_user)
):
    """Cancel active subscription"""
    db = get_database()
    tenant_id = current_user.tenant_id
    
    # Get active subscription
    subscription_doc = await db.subscriptions.find_one({
        "tenantId": tenant_id,
        "status": "active"
    })
    
    if not subscription_doc:
        raise HTTPException(status_code=404, detail="No active subscription found")
    
    # Get payment gateway
    gateway, _ = await get_tenant_gateway(db, tenant_id)
    
    # Cancel in gateway
    result = await gateway.cancel_subscription(subscription_doc["gatewaySubscriptionId"])
    
    # Update in database
    await db.subscriptions.update_one(
        {"_id": subscription_doc["_id"]},
        {"$set": {
            "status": "canceled",
            "canceledAt": datetime.fromtimestamp(result["canceled_at"], tz=timezone.utc).isoformat()
        }}
    )
    
    # Downgrade tenant to Free tier
    await db.tenants.update_one(
        {"id": tenant_id},
        {"$set": {"subscriptionTier": "Free"}}
    )
    
    return {
        "success": True,
        "message": "Subscription canceled successfully"
    }


@router.post("/webhook/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature")
):
    """Handle Stripe webhooks"""
    db = get_database()
    payload = await request.body()
    
    # Get webhook secret from first Stripe gateway config
    gateway_config = await db.payment_gateways.find_one({"gateway": "stripe"})
    if not gateway_config or "webhookSecret" not in gateway_config:
        raise HTTPException(status_code=400, detail="Webhook secret not configured")
    
    encryption = get_encryption_service()
    webhook_secret = encryption.decrypt(gateway_config["webhookSecret"])
    
    # Verify and construct event
    from payment_gateways.stripe_gateway import StripeGateway
    gateway = StripeGateway({"secret_key": ""})  # Just for webhook verification
    
    try:
        event = await gateway.construct_webhook_event(payload, stripe_signature, webhook_secret)
    except Exception as e:
        logger.error(f"Webhook verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    # Handle different event types
    event_type = event["type"]
    
    if event_type == "invoice.payment_succeeded":
        # Store invoice
        invoice_data = event["data"]
        await db.invoices.insert_one({
            "tenantId": invoice_data.get("metadata", {}).get("tenantId"),
            "gateway": "stripe",
            "gatewayInvoiceId": invoice_data["id"],
            "invoiceNumber": invoice_data.get("number"),
            "amount": invoice_data["amount_paid"] / 100,
            "currency": invoice_data["currency"],
            "status": "paid",
            "paidAt": datetime.fromtimestamp(invoice_data["status_transitions"]["paid_at"], tz=timezone.utc).isoformat(),
            "createdAt": datetime.now(timezone.utc).isoformat()
        })
    
    elif event_type == "customer.subscription.deleted":
        # Update subscription status
        sub_data = event["data"]
        await db.subscriptions.update_one(
            {"gatewaySubscriptionId": sub_data["id"]},
            {"$set": {"status": "canceled"}}
        )
    
    # Log webhook event
    await db.webhook_events.insert_one({
        "gateway": "stripe",
        "eventId": event["id"],
        "eventType": event_type,
        "processed": True,
        "createdAt": datetime.now(timezone.utc).isoformat()
    })
    
    return {"success": True}


# --- Billing Endpoints ---

from billing_service import BillingService


@router.get("/usage")
async def get_usage(
    billing_period: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user)
):
    """Get usage summary for current billing period"""
    tenant_id = current_user.tenant_id
    
    usage_summary = await BillingService.get_usage_summary(tenant_id, billing_period)
    usage_charges = await BillingService.calculate_usage_charges(tenant_id, billing_period)
    limits_check = await BillingService.check_usage_limits(tenant_id)
    
    return {
        "success": True,
        "billingPeriod": billing_period or datetime.now(timezone.utc).strftime("%Y-%m"),
        "usage": usage_summary,
        "charges": usage_charges,
        "limits": limits_check
    }


@router.post("/generate-invoice")
async def generate_invoice(
    billing_period: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user)
):
    """Generate invoice for a billing period"""
    tenant_id = current_user.tenant_id
    
    invoice = await BillingService.generate_invoice(tenant_id, billing_period)
    invoice.pop("_id", None)
    
    return {
        "success": True,
        "invoice": invoice
    }


@router.get("/subscription-info")
async def get_subscription_info(
    current_user: TokenData = Depends(get_current_user)
):
    """Get current subscription information"""
    db = get_database()
    tenant_id = current_user.tenant_id
    
    # Get tenant
    # Get tenant
    tenant = await db.tenants.find_one({"id": tenant_id})
    if not tenant:
        # If tenant not found, return default Free tier info instead of crashing
        limits_check = await BillingService.check_usage_limits(tenant_id)
        return {
            "success": True,
            "subscriptionTier": "Free",
            "subscription": None,
            "limits": limits_check
        }
    
    # Get active subscription
    subscription = await db.subscriptions.find_one({
        "tenantId": tenant_id,
        "status": "active"
    })
    
    # Get usage limits check
    limits_check = await BillingService.check_usage_limits(tenant_id)
    
    return {
        "success": True,
        "subscriptionTier": tenant.get("subscriptionTier", "Free"),
        "subscription": subscription,
        "limits": limits_check
    }
