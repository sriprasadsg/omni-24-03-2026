"""
Payment endpoints aggregator.
Gateway management: payment_gateway_endpoints
Billing/subscriptions: payment_billing_endpoints
"""

from fastapi import APIRouter
from payment_gateway_endpoints import router as _gateway
from payment_billing_endpoints import router as _billing

router = APIRouter()
router.include_router(_gateway)
router.include_router(_billing)
