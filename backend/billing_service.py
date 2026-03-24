from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta
from database import get_database
import logging

logger = logging.getLogger(__name__)


class BillingService:
    """Service for managing billing, usage tracking, and invoice generation"""
    
    # Pricing configuration (in cents)
    SUBSCRIPTION_PRICES = {
        "Free": 0,
        "Pro": 9900,  # $99/month
        "Enterprise": 49900,  # $499/month
        "Custom": 0  # Custom pricing
    }
    
    # Usage pricing (per unit)
    USAGE_PRICES = {
        "data_ingestion_gb": 100,  # $1 per GB
        "api_calls_1000": 10,  # $0.10 per 1000 calls
        "ai_compute_vcpu_hour": 500  # $5 per vCPU hour
    }
    
    # Subscription limits
    SUBSCRIPTION_LIMITS = {
        "Free": {
            "data_ingestion_gb": 10,
            "api_calls_millions": 0.1,
            "ai_compute_vcpu_hours": 1
        },
        "Pro": {
            "data_ingestion_gb": 100,
            "api_calls_millions": 1,
            "ai_compute_vcpu_hours": 10
        },
        "Enterprise": {
            "data_ingestion_gb": 1000,
            "api_calls_millions": 10,
            "ai_compute_vcpu_hours": 100
        },
        "Custom": {
            "data_ingestion_gb": float('inf'),
            "api_calls_millions": float('inf'),
            "ai_compute_vcpu_hours": float('inf')
        }
    }
    
    @staticmethod
    async def track_usage(
        tenant_id: str,
        metric: str,
        quantity: float,
        metadata: Optional[Dict] = None
    ):
        """Track usage for a tenant"""
        db = get_database()
        
        # Get current billing period (month)
        now = datetime.now(timezone.utc)
        billing_period = now.strftime("%Y-%m")
        
        usage_record = {
            "tenantId": tenant_id,
            "metric": metric,
            "quantity": quantity,
            "billingPeriod": billing_period,
            "timestamp": now.isoformat(),
            "metadata": metadata or {}
        }
        
        await db.usage_records.insert_one(usage_record)
        logger.info(f"Tracked usage for {tenant_id}: {metric}={quantity}")
    
    @staticmethod
    async def get_usage_summary(tenant_id: str, billing_period: Optional[str] = None) -> Dict:
        """Get usage summary for a tenant in a billing period"""
        db = get_database()
        
        if not billing_period:
            billing_period = datetime.now(timezone.utc).strftime("%Y-%m")
        
        # Aggregate usage by metric
        pipeline = [
            {
                "$match": {
                    "tenantId": tenant_id,
                    "billingPeriod": billing_period
                }
            },
            {
                "$group": {
                    "_id": "$metric",
                    "total": {"$sum": "$quantity"}
                }
            }
        ]
        
        results = await db.usage_records.aggregate(pipeline).to_list(length=100)
        
        usage_summary = {}
        for result in results:
            usage_summary[result["_id"]] = result["total"]
        
        return usage_summary
    
    @staticmethod
    async def calculate_usage_charges(tenant_id: str, billing_period: Optional[str] = None) -> Dict:
        """Calculate usage charges for a tenant"""
        usage_summary = await BillingService.get_usage_summary(tenant_id, billing_period)
        
        # Get tenant subscription tier
        db = get_database()
        tenant = await db.tenants.find_one({"id": tenant_id})
        subscription_tier = tenant.get("subscriptionTier", "Free")
        
        limits = BillingService.SUBSCRIPTION_LIMITS.get(subscription_tier, {})
        
        charges = []
        total_amount = 0
        
        # Calculate data ingestion charges
        data_ingestion = usage_summary.get("data_ingestion_gb", 0)
        data_limit = limits.get("data_ingestion_gb", 0)
        if data_ingestion > data_limit:
            overage = data_ingestion - data_limit
            charge = overage * BillingService.USAGE_PRICES["data_ingestion_gb"]
            charges.append({
                "description": f"Data Ingestion Overage ({overage:.2f} GB)",
                "quantity": overage,
                "unit_price": BillingService.USAGE_PRICES["data_ingestion_gb"] / 100,
                "amount": charge / 100
            })
            total_amount += charge
        
        # Calculate API calls charges
        api_calls_millions = usage_summary.get("api_calls_millions", 0)
        api_limit = limits.get("api_calls_millions", 0)
        if api_calls_millions > api_limit:
            overage = api_calls_millions - api_limit
            charge = (overage * 1000) * BillingService.USAGE_PRICES["api_calls_1000"]
            charges.append({
                "description": f"API Calls Overage ({overage:.2f}M calls)",
                "quantity": overage,
                "unit_price": BillingService.USAGE_PRICES["api_calls_1000"] / 100,
                "amount": charge / 100
            })
            total_amount += charge
        
        # Calculate AI compute charges
        ai_compute = usage_summary.get("ai_compute_vcpu_hours", 0)
        ai_limit = limits.get("ai_compute_vcpu_hours", 0)
        if ai_compute > ai_limit:
            overage = ai_compute - ai_limit
            charge = overage * BillingService.USAGE_PRICES["ai_compute_vcpu_hour"]
            charges.append({
                "description": f"AI Compute Overage ({overage:.2f} vCPU hours)",
                "quantity": overage,
                "unit_price": BillingService.USAGE_PRICES["ai_compute_vcpu_hour"] / 100,
                "amount": charge / 100
            })
            total_amount += charge
        
        return {
            "charges": charges,
            "total_amount": total_amount / 100,  # Convert to dollars
            "currency": "USD"
        }
    
    @staticmethod
    async def generate_invoice(tenant_id: str, billing_period: Optional[str] = None) -> Dict:
        """Generate an invoice for a tenant"""
        db = get_database()
        
        if not billing_period:
            billing_period = datetime.now(timezone.utc).strftime("%Y-%m")
        
        # Get tenant info
        tenant = await db.tenants.find_one({"id": tenant_id})
        subscription_tier = tenant.get("subscriptionTier", "Free")
        
        # Get subscription charge
        subscription_amount = BillingService.SUBSCRIPTION_PRICES.get(subscription_tier, 0) / 100
        
        # Get usage charges
        usage_charges = await BillingService.calculate_usage_charges(tenant_id, billing_period)
        
        # Build line items
        line_items = []
        
        if subscription_amount > 0:
            line_items.append({
                "description": f"{subscription_tier} Subscription",
                "amount": subscription_amount
            })
        
        line_items.extend(usage_charges["charges"])
        
        # Calculate total
        total_amount = subscription_amount + usage_charges["total_amount"]
        
        # Calculate tax (simplified logic)
        tax_rate = 0.0825 if tenant.get("location") == "US" else 0.05
        tax_amount = total_amount * tax_rate
        
        # Generate invoice number
        invoice_count = await db.invoices.count_documents({"tenantId": tenant_id})
        invoice_number = f"INV-{tenant_id[:8].upper()}-{billing_period}-{invoice_count + 1:04d}"
        
        # Create invoice document
        invoice = {
            "tenantId": tenant_id,
            "invoiceNumber": invoice_number,
            "billingPeriod": billing_period,
            "subscriptionTier": subscription_tier,
            "lineItems": line_items,
            "subtotal": round(total_amount, 2),
            "tax": round(tax_amount, 2),
            "total": round(total_amount + tax_amount, 2),
            "currency": "USD",
            "status": "draft",
            "createdAt": datetime.now(timezone.utc).isoformat()
        }
        
        result = await db.invoices.insert_one(invoice)
        invoice["_id"] = str(result.inserted_id)
        
        logger.info(f"Generated invoice {invoice_number} for {tenant_id}: ${total_amount:.2f}")
        
        return invoice
    
    @staticmethod
    async def check_usage_limits(tenant_id: str) -> Dict:
        """Check if tenant is within usage limits"""
        db = get_database()
        tenant = await db.tenants.find_one({"id": tenant_id})
        if not tenant:
            subscription_tier = "Free"
        else:
            subscription_tier = tenant.get("subscriptionTier", "Free")
        
        limits = BillingService.SUBSCRIPTION_LIMITS.get(subscription_tier, {})
        usage_summary = await BillingService.get_usage_summary(tenant_id)
        
        warnings = []
        
        # Check data ingestion
        data_usage = usage_summary.get("data_ingestion_gb", 0)
        data_limit = limits.get("data_ingestion_gb", 0)
        if data_limit != float('inf'):
            usage_percent = (data_usage / data_limit * 100) if data_limit > 0 else 0
            if usage_percent >= 90:
                warnings.append({
                    "metric": "data_ingestion_gb",
                    "usage": data_usage,
                    "limit": data_limit,
                    "percent": usage_percent,
                    "message": f"Data ingestion at {usage_percent:.1f}% of limit"
                })
        
        # Check API calls
        api_usage = usage_summary.get("api_calls_millions", 0)
        api_limit = limits.get("api_calls_millions", 0)
        if api_limit != float('inf'):
            usage_percent = (api_usage / api_limit * 100) if api_limit > 0 else 0
            if usage_percent >= 90:
                warnings.append({
                    "metric": "api_calls_millions",
                    "usage": api_usage,
                    "limit": api_limit,
                    "percent": usage_percent,
                    "message": f"API calls at {usage_percent:.1f}% of limit"
                })
        
        # Check AI compute
        ai_usage = usage_summary.get("ai_compute_vcpu_hours", 0)
        ai_limit = limits.get("ai_compute_vcpu_hours", 0)
        if ai_limit != float('inf'):
            usage_percent = (ai_usage / ai_limit * 100) if ai_limit > 0 else 0
            if usage_percent >= 90:
                warnings.append({
                    "metric": "ai_compute_vcpu_hours",
                    "usage": ai_usage,
                    "limit": ai_limit,
                    "percent": usage_percent,
                    "message": f"AI compute at {usage_percent:.1f}% of limit"
                })
        
        return {
            "within_limits": len(warnings) == 0,
            "warnings": warnings,
            "usage": usage_summary,
            "limits": limits
        }
