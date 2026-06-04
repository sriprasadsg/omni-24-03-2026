"""
Billing Invoice Endpoints — Phase 7
Provides invoice CRUD and PDF download functionality.
Integrates with Stripe for live invoice data and invoice_generator.py for PDFs.
"""
import os
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends

logger = logging.getLogger(__name__)
from fastapi.responses import Response
from pydantic import BaseModel, Field
from typing import Optional, List
from database import get_database
from authentication_service import get_current_user
from tenant_context import get_tenant_id

router = APIRouter(prefix="/api/billing", tags=["Billing"])

_BILLING_ADMIN_ROLES = {"Super Admin", "super_admin", "platform-admin", "admin", "Tenant Admin"}


def _tid(user) -> str:
    """Extract tenant_id from the authenticated JWT user — never from the ContextVar."""
    if isinstance(user, dict):
        return user.get("tenant_id") or user.get("tenantId") or ""
    return getattr(user, "tenant_id", None) or getattr(user, "tenantId", None) or ""


class InvoiceLineItem(BaseModel):
    description: str = Field(..., max_length=500)
    amount: float
    quantity: int = Field(1, ge=1, le=10_000)


class InvoiceRequest(BaseModel):
    period_start: Optional[str] = Field(None, max_length=32)
    period_end: Optional[str] = Field(None, max_length=32)
    plan: Optional[str] = Field(None, max_length=100)
    custom_items: Optional[List[InvoiceLineItem]] = None


@router.get("/invoices")
async def list_invoices(current_user=Depends(get_current_user)):
    """List all invoices for the current tenant."""
    db = get_database()
    tenant_id = _tid(current_user)

    # Try Stripe first if configured
    stripe_key = os.getenv("STRIPE_SECRET_KEY")
    if stripe_key and stripe_key.startswith("sk_"):
        try:
            from payment_gateways.stripe_gateway import stripe_gateway
            tenant = await db.tenants.find_one({"id": tenant_id}, {"_id": 0})
            stripe_customer_id = (tenant or {}).get("stripe_customer_id")
            if stripe_customer_id:
                invoices = stripe_gateway.list_invoices(stripe_customer_id)
                return {"invoices": invoices, "source": "stripe"}
        except Exception:
            pass  # Fall through to database

    # Fallback: MongoDB invoices
    invoices = await db.invoices.find(
        {"tenantId": tenant_id}, {"_id": 0}
    ).sort("generated_at", -1).to_list(length=50)
    return {"invoices": invoices, "source": "database"}


@router.post("/invoice")
async def generate_invoice_alias(
    tenant_id: str = "",
    req: InvoiceRequest = None,
    current_user=Depends(get_current_user),
):
    """Generate invoice — query-param alias for /invoices/generate (test-compatible)."""
    from tenant_context import set_tenant_id as _stid
    if tenant_id:
        caller_role = getattr(current_user, "role", "") if not isinstance(current_user, dict) else current_user.get("role", "")
        caller_tenant = getattr(current_user, "tenant_id", None) if not isinstance(current_user, dict) else (current_user.get("tenant_id") or current_user.get("tenantId"))
        _SUPER = {"Super Admin", "super_admin", "platform-admin"}
        if caller_role not in _SUPER and caller_tenant != tenant_id:
            raise HTTPException(status_code=403, detail="Not authorized to generate invoices for this tenant")
        _stid(tenant_id)
    return await generate_invoice(req or InvoiceRequest(), current_user)


@router.post("/invoices/generate")
async def generate_invoice(req: InvoiceRequest, current_user=Depends(get_current_user)):
    """Generate a new invoice for the current period."""
    caller_role = getattr(current_user, "role", "") if not isinstance(current_user, dict) else current_user.get("role", "")
    if caller_role not in _BILLING_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Billing admin role required to generate invoices")
    db = get_database()
    tenant_id = _tid(current_user)
    tenant = await db.tenants.find_one({"id": tenant_id}, {"_id": 0}) or {}

    # Build invoice
    plan = req.plan or tenant.get("subscriptionPlan", "Standard")
    plan_pricing = {"Starter": 99, "Standard": 299, "Professional": 799, "Enterprise": 1999}
    amount = plan_pricing.get(plan, 299)

    # Apply location-based tax
    location = tenant.get("location", "")
    tax_rate = 8.25 if "US" in location or "United States" in location else 5.0
    tax = round(amount * tax_rate / 100, 2)
    total = round(amount + tax, 2)

    invoice = {
        "id": f"INV-{uuid.uuid4().hex[:8].upper()}",
        "tenantId": tenant_id,
        "plan": plan,
        "amount": amount,
        "subtotal": amount,
        "tax": tax,
        "tax_rate": tax_rate,
        "total": total,
        "currency": "USD",
        "status": "pending",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": [{"description": f"{plan} Plan — Monthly Subscription", "qty": 1, "unit_price": amount, "total": amount}],
    }

    await db.invoices.insert_one({**invoice, "_id": invoice["id"]})
    return invoice


@router.get("/invoices/{invoice_id}/pdf")
async def download_invoice_pdf(invoice_id: str, current_user=Depends(get_current_user)):
    """Download an invoice as a PDF."""
    from invoice_generator import generate_invoice_pdf
    db = get_database()
    tenant_id = _tid(current_user)

    invoice = await db.invoices.find_one({"id": invoice_id, "tenantId": tenant_id}, {"_id": 0})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    tenant = await db.tenants.find_one({"id": tenant_id}, {"_id": 0}) or {"name": "Tenant"}

    try:
        pdf_bytes = generate_invoice_pdf(invoice, tenant)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=invoice-{invoice_id}.pdf"}
        )
    except Exception as e:
        logger.error("PDF generation failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/invoices/{invoice_id}/pay")
async def mark_invoice_paid(invoice_id: str, current_user=Depends(get_current_user)):
    """Mark an invoice as paid (admin action)."""
    if getattr(current_user, "role", None) not in _BILLING_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required")
    db = get_database()
    tenant_id = _tid(current_user)
    result = await db.invoices.update_one(
        {"id": invoice_id, "tenantId": tenant_id},
        {"$set": {"status": "paid", "paid_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {"success": True, "invoice_id": invoice_id, "status": "paid"}


@router.get("/payment-methods")
async def get_payment_methods(current_user=Depends(get_current_user)):
    """List saved payment methods for the tenant."""
    db = get_database()
    tenant_id = _tid(current_user)
    tenant = await db.tenants.find_one({"id": tenant_id}, {"_id": 0}) or {}

    stripe_key = os.getenv("STRIPE_SECRET_KEY")
    stripe_customer_id = tenant.get("stripe_customer_id")
    if stripe_key and stripe_customer_id:
        try:
            import stripe
            stripe.api_key = stripe_key
            methods = stripe.PaymentMethod.list(customer=stripe_customer_id, type="card")
            cards = [
                {
                    "id": m.id,
                    "brand": m.card.brand,
                    "last4": m.card.last4,
                    "exp_month": m.card.exp_month,
                    "exp_year": m.card.exp_year,
                }
                for m in methods.data
            ]
            return {"payment_methods": cards, "source": "stripe"}
        except Exception as e:
            logger.warning("Stripe payment method fetch failed: %s", e)

    # PayPal fallback: check if PayPal credentials are configured
    paypal_client = os.getenv("PAYPAL_CLIENT_ID")
    if paypal_client:
        try:
            saved = await db.billing_payment_methods.find(
                {"tenantId": tenant_id}, {"_id": 0}
            ).to_list(length=20)
            if saved:
                return {"payment_methods": saved, "source": "paypal"}
        except Exception as e:
            logger.warning("PayPal payment method fetch failed: %s", e)

    return {"payment_methods": [], "source": "none", "note": "Configure Stripe or PayPal to manage payment methods"}


@router.get("/stripe-config")
async def get_stripe_config(current_user=Depends(get_current_user)):
    """Return Stripe publishable key so the frontend can load Stripe.js. Empty string when unconfigured."""
    publishable_key = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
    return {"publishable_key": publishable_key, "configured": bool(publishable_key)}


@router.get("/paypal-config")
async def get_paypal_config(current_user=Depends(get_current_user)):
    """Return PayPal client ID for frontend SDK. Empty when unconfigured."""
    client_id = os.getenv("PAYPAL_CLIENT_ID", "")
    mode = os.getenv("PAYPAL_MODE", "sandbox")
    return {"client_id": client_id, "mode": mode, "configured": bool(client_id)}


@router.post("/paypal/order")
async def create_paypal_order(
    plan: str,
    current_user=Depends(get_current_user)
):
    """Create a PayPal order for a plan upgrade. Returns approval URL for redirect."""
    client_id = os.getenv("PAYPAL_CLIENT_ID", "")
    client_secret = os.getenv("PAYPAL_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="PayPal is not configured. Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET.")

    plan_pricing = {"Starter": 99, "Standard": 299, "Professional": 799, "Enterprise": 1999}
    if plan not in plan_pricing:
        raise HTTPException(status_code=400, detail="Invalid plan")
    amount = plan_pricing[plan]
    mode = os.getenv("PAYPAL_MODE", "sandbox")
    base = "https://api-m.sandbox.paypal.com" if mode == "sandbox" else "https://api-m.paypal.com"

    import aiohttp as _aiohttp
    try:
        async with _aiohttp.ClientSession() as session:
            # Get access token
            async with session.post(f"{base}/v1/oauth2/token",
                                    auth=_aiohttp.BasicAuth(client_id, client_secret),
                                    data="grant_type=client_credentials") as tr:
                token_data = await tr.json()
                access_token = token_data.get("access_token", "")

            from urllib.parse import urlparse as _urlparse
            frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
            _parsed = _urlparse(frontend_url)
            if _parsed.scheme not in ("http", "https") or not _parsed.netloc:
                frontend_url = "http://localhost:3000"
            # Create order
            async with session.post(f"{base}/v2/checkout/orders",
                                    headers={"Authorization": f"Bearer {access_token}",
                                             "Content-Type": "application/json"},
                                    json={
                                        "intent": "CAPTURE",
                                        "purchase_units": [{"amount": {"currency_code": "USD",
                                                                        "value": str(amount)}}],
                                        "application_context": {
                                            "return_url": f"{frontend_url}/billing?paypal=success&plan={plan}",
                                            "cancel_url": f"{frontend_url}/billing?paypal=cancel",
                                        }
                                    }) as or_:
                order = await or_.json()
                approval_url = next(
                    (link["href"] for link in order.get("links", []) if link.get("rel") == "approve"), ""
                )
                return {"order_id": order.get("id"), "approval_url": approval_url, "amount": amount, "plan": plan}
    except Exception as exc:
        logger.error("PayPal order creation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Payment order creation failed")


@router.post("/stripe/checkout")
async def create_stripe_checkout(
    price_id: str,
    current_user=Depends(get_current_user)
):
    """Create a Stripe Checkout session for subscription upgrade."""
    from payment_gateways.stripe_gateway import stripe_gateway
    if not stripe_gateway.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Stripe is not configured. Set STRIPE_SECRET_KEY in .env"
        )

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    db = get_database()
    tenant_id = _tid(current_user)
    tenant = await db.tenants.find_one({"id": tenant_id}, {"_id": 0}) or {}

    session = stripe_gateway.create_checkout_session(
        price_id=price_id,
        customer_email=current_user.username,
        tenant_id=tenant_id,
        success_url=f"{frontend_url}/billing?success=true",
        cancel_url=f"{frontend_url}/billing?cancelled=true",
    )
    return session
