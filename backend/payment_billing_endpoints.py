"""
Payment billing endpoints: subscriptions, charges, invoices, webhooks, and usage.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import BaseModel
from typing import Optional
from authentication_service import get_current_user
from auth_types import TokenData
from database import get_database
from encryption_service import get_encryption_service
from datetime import datetime, timezone
from rate_limiter import limiter
import logging

from payment_gateway_endpoints import get_tenant_gateway
from billing_service import BillingService

router = APIRouter(prefix="/api/payments", tags=["Payments"])
logger = logging.getLogger(__name__)


class SubscriptionCreate(BaseModel):
    plan: str
    price_id: str


class ChargeCreate(BaseModel):
    amount: int
    currency: str = "USD"
    description: str


@router.post("/subscribe")
async def create_subscription(
    subscription: SubscriptionCreate,
    current_user: TokenData = Depends(get_current_user),
):
    """Create a subscription for the tenant."""
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

    sub = await gateway.create_subscription(
        customer_id=customer_doc["gatewayCustomerId"],
        price_id=subscription.price_id,
        metadata={"tenantId": tenant_id, "plan": subscription.plan},
    )
    subscription_doc = {
        "tenantId": tenant_id, "gateway": gateway_config["gateway"],
        "gatewaySubscriptionId": sub["id"], "plan": subscription.plan,
        "status": sub["status"],
        "currentPeriodStart": datetime.fromtimestamp(sub["current_period_start"], tz=timezone.utc).isoformat(),
        "currentPeriodEnd": datetime.fromtimestamp(sub["current_period_end"], tz=timezone.utc).isoformat(),
        "amount": sub["plan"]["amount"] / 100,
        "currency": sub["plan"]["currency"],
        "interval": sub["plan"]["interval"],
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    await db.subscriptions.insert_one(subscription_doc)
    await db.tenants.update_one({"id": tenant_id}, {"$set": {"subscriptionTier": subscription.plan}})
    return {"success": True, "subscription": subscription_doc}


@router.post("/charge")
async def create_charge(
    charge: ChargeCreate,
    current_user: TokenData = Depends(get_current_user),
):
    """Create a one-time charge."""
    db = get_database()
    tenant_id = current_user.tenant_id
    gateway, gateway_config = await get_tenant_gateway(db, tenant_id)
    customer_doc = await db.payment_customers.find_one({"tenantId": tenant_id})
    if not customer_doc:
        raise HTTPException(status_code=404, detail="No payment customer found. Please set up payment method first.")
    charge_result = await gateway.create_charge(
        customer_id=customer_doc["gatewayCustomerId"],
        amount=charge.amount, currency=charge.currency,
        description=charge.description, metadata={"tenantId": tenant_id},
    )
    charge_doc = {
        "tenantId": tenant_id, "gateway": gateway_config["gateway"],
        "gatewayChargeId": charge_result["id"],
        "amount": charge_result["amount"] / 100,
        "currency": charge_result["currency"], "description": charge.description,
        "status": charge_result["status"], "paid": charge_result["paid"],
        "createdAt": datetime.fromtimestamp(charge_result["created"], tz=timezone.utc).isoformat(),
    }
    await db.charges.insert_one(charge_doc)
    return {"success": True, "charge": charge_doc}


@router.get("/invoices")
async def get_invoices(
    limit: int = 10,
    current_user: TokenData = Depends(get_current_user),
):
    """Get invoices for the tenant."""
    db = get_database()
    tenant_id = current_user.tenant_id
    invoices = await db.invoices.find({"tenantId": tenant_id}).sort("createdAt", -1).limit(limit).to_list(length=limit)
    for invoice in invoices:
        invoice.pop("_id", None)
    return {"success": True, "invoices": invoices}


@router.get("/invoices/{invoice_id}/pdf")
async def download_invoice_pdf(
    invoice_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Generate and download invoice PDF."""
    db = get_database()
    tenant_id = current_user.tenant_id
    invoice = await db.invoices.find_one({"invoiceNumber": invoice_id, "tenantId": tenant_id})
    if not invoice:
        invoice = await db.invoices.find_one({"gatewayInvoiceId": invoice_id, "tenantId": tenant_id})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    tenant = await db.tenants.find_one({"id": tenant_id}) or {"name": "Valued Customer", "id": tenant_id}
    from invoice_generator import InvoiceGenerator
    from fastapi.responses import StreamingResponse

    pdf_buffer = InvoiceGenerator.generate_pdf(invoice, tenant)
    filename = f"invoice_{invoice.get('invoiceNumber', 'draft')}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/cancel-subscription")
async def cancel_subscription(current_user: TokenData = Depends(get_current_user)):
    """Cancel active subscription."""
    db = get_database()
    tenant_id = current_user.tenant_id
    subscription_doc = await db.subscriptions.find_one({"tenantId": tenant_id, "status": "active"})
    if not subscription_doc:
        raise HTTPException(status_code=404, detail="No active subscription found")
    gateway, _ = await get_tenant_gateway(db, tenant_id)
    result = await gateway.cancel_subscription(subscription_doc["gatewaySubscriptionId"])
    await db.subscriptions.update_one(
        {"_id": subscription_doc["_id"]},
        {"$set": {
            "status": "canceled",
            "canceledAt": datetime.fromtimestamp(result["canceled_at"], tz=timezone.utc).isoformat(),
        }},
    )
    await db.tenants.update_one({"id": tenant_id}, {"$set": {"subscriptionTier": "Free"}})
    return {"success": True, "message": "Subscription canceled successfully"}


@router.post("/webhook/stripe")
@limiter.limit("60/minute")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
):
    """Handle Stripe webhooks."""
    db = get_database()
    payload = await request.body()
    # Verify idempotency: reject replayed webhook events before decrypting any secret
    raw_event_id = None
    try:
        import json as _json
        raw_event_id = _json.loads(await request.body()).get("id")
    except Exception:
        pass
    if raw_event_id:
        already = await db.webhook_events.find_one({"eventId": raw_event_id}, {"_id": 1})
        if already:
            return {"received": True, "duplicate": True}

    # Resolve webhook secret scoped to the Stripe account that owns this event.
    # Using the platform-admin gateway config is incorrect in multi-tenant deployments;
    # use the tenantId embedded in the event metadata to look up the right config.
    gateway_config = await db.payment_gateways.find_one(
        {"gateway": "stripe", "tenantId": {"$in": [None, "platform-admin"]}}
    )
    if not gateway_config or "webhookSecret" not in gateway_config:
        raise HTTPException(status_code=400, detail="Webhook secret not configured")
    encryption = get_encryption_service()
    webhook_secret = encryption.decrypt(gateway_config["webhookSecret"])
    from payment_gateways.stripe_gateway import StripeGateway
    gateway = StripeGateway({"secret_key": ""})
    try:
        event = await gateway.construct_webhook_event(payload, stripe_signature, webhook_secret)
    except Exception as e:
        logger.error("Webhook verification failed: %s", e)
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event["type"]
    if event_type == "invoice.payment_succeeded":
        invoice_data = event["data"]
        # Never trust tenantId from the webhook payload — verify the Stripe customer
        # belongs to a real tenant by resolving it from our own DB.
        gateway_customer_id = invoice_data.get("customer")
        customer_doc = await db.payment_customers.find_one(
            {"gatewayCustomerId": gateway_customer_id}, {"tenantId": 1}
        ) if gateway_customer_id else None
        verified_tenant_id = (customer_doc or {}).get("tenantId") or ""
        if not verified_tenant_id:
            logger.warning("Webhook invoice.payment_succeeded: unknown customer %s — skipping", gateway_customer_id)
        else:
            await db.invoices.insert_one({
                "tenantId": verified_tenant_id,
                "gateway": "stripe", "gatewayInvoiceId": invoice_data["id"],
                "invoiceNumber": invoice_data.get("number"),
                "amount": invoice_data["amount_paid"] / 100,
                "currency": invoice_data["currency"], "status": "paid",
                "paidAt": datetime.fromtimestamp(
                    invoice_data["status_transitions"]["paid_at"], tz=timezone.utc
                ).isoformat(),
                "createdAt": datetime.now(timezone.utc).isoformat(),
            })
    elif event_type == "customer.subscription.deleted":
        sub_data = event["data"]
        await db.subscriptions.update_one(
            {"gatewaySubscriptionId": sub_data["id"]}, {"$set": {"status": "canceled"}}
        )

    await db.webhook_events.insert_one({
        "gateway": "stripe", "eventId": event["id"], "eventType": event_type,
        "processed": True, "createdAt": datetime.now(timezone.utc).isoformat(),
    })
    return {"success": True}


@router.get("/usage")
async def get_usage(
    billing_period: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Get usage summary for current billing period."""
    tenant_id = current_user.tenant_id
    usage_summary = await BillingService.get_usage_summary(tenant_id, billing_period)
    usage_charges = await BillingService.calculate_usage_charges(tenant_id, billing_period)
    limits_check = await BillingService.check_usage_limits(tenant_id)
    return {
        "success": True,
        "billingPeriod": billing_period or datetime.now(timezone.utc).strftime("%Y-%m"),
        "usage": usage_summary, "charges": usage_charges, "limits": limits_check,
    }


@router.post("/generate-invoice")
async def generate_invoice(
    billing_period: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Generate invoice for a billing period."""
    tenant_id = current_user.tenant_id
    invoice = await BillingService.generate_invoice(tenant_id, billing_period)
    invoice.pop("_id", None)
    return {"success": True, "invoice": invoice}


@router.get("/subscription-info")
async def get_subscription_info(current_user: TokenData = Depends(get_current_user)):
    """Get current subscription information."""
    db = get_database()
    tenant_id = current_user.tenant_id
    tenant = await db.tenants.find_one({"id": tenant_id})
    if not tenant:
        limits_check = await BillingService.check_usage_limits(tenant_id)
        return {"success": True, "subscriptionTier": "Free", "subscription": None, "limits": limits_check}
    subscription = await db.subscriptions.find_one({"tenantId": tenant_id, "status": "active"})
    limits_check = await BillingService.check_usage_limits(tenant_id)
    return {
        "success": True,
        "subscriptionTier": tenant.get("subscriptionTier", "Free"),
        "subscription": subscription, "limits": limits_check,
    }
