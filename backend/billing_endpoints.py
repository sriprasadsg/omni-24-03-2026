"""
Billing Invoice Endpoints — Phase 7
Provides invoice CRUD and PDF download functionality.
Integrates with Stripe for live invoice data and invoice_generator.py for PDFs.
"""
import os
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional, Dict, Any
from database import get_database
from authentication_service import get_current_user
from tenant_context import get_tenant_id

router = APIRouter(prefix="/api/billing", tags=["Billing"])


class InvoiceRequest(BaseModel):
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    plan: Optional[str] = None
    custom_items: Optional[list] = None


@router.get("/invoices")
async def list_invoices(current_user=Depends(get_current_user)):
    """List all invoices for the current tenant."""
    db = get_database()
    tenant_id = get_tenant_id()

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
        except Exception as e:
            pass  # Fall through to database

    # Fallback: MongoDB invoices
    invoices = await db.invoices.find(
        {"tenantId": tenant_id}, {"_id": 0}
    ).sort("generated_at", -1).to_list(length=50)
    return {"invoices": invoices, "source": "database"}


@router.post("/invoices/generate")
async def generate_invoice(req: InvoiceRequest, current_user=Depends(get_current_user)):
    """Generate a new invoice for the current period."""
    db = get_database()
    tenant_id = get_tenant_id()
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
    tenant_id = get_tenant_id()

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
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")


@router.post("/invoices/{invoice_id}/pay")
async def mark_invoice_paid(invoice_id: str, current_user=Depends(get_current_user)):
    """Mark an invoice as paid (admin action)."""
    db = get_database()
    tenant_id = get_tenant_id()
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
    tenant_id = get_tenant_id()
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
        except Exception:
            pass

    return {"payment_methods": [], "source": "none", "note": "Configure Stripe to manage payment methods"}


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
    tenant_id = get_tenant_id()
    tenant = await db.tenants.find_one({"id": tenant_id}, {"_id": 0}) or {}

    session = stripe_gateway.create_checkout_session(
        price_id=price_id,
        customer_email=current_user.username,
        tenant_id=tenant_id,
        success_url=f"{frontend_url}/billing?success=true",
        cancel_url=f"{frontend_url}/billing?cancelled=true",
    )
    return session
