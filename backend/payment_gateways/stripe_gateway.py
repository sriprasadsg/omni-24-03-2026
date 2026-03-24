"""
Stripe Payment Gateway — Phase 3
Wraps Stripe SDK for subscriptions, checkout sessions, and webhook handling.
"""
import stripe
import os
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


def get_stripe_client():
    api_key = os.getenv("STRIPE_SECRET_KEY")
    if not api_key:
        raise Exception("STRIPE_SECRET_KEY not configured in .env")
    stripe.api_key = api_key
    return stripe


class StripeGateway:
    def __init__(self):
        self.api_key = os.getenv("STRIPE_SECRET_KEY", "")
        self.webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
        self.publishable_key = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
        if self.api_key:
            stripe.api_key = self.api_key

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def create_customer(self, email: str, name: str, tenant_id: str) -> Dict[str, Any]:
        """Create a Stripe customer for a tenant."""
        try:
            customer = stripe.Customer.create(
                email=email,
                name=name,
                metadata={"tenant_id": tenant_id}
            )
            return {"id": customer.id, "email": customer.email, "name": customer.name}
        except stripe.error.StripeError as e:
            logger.error(f"Stripe create_customer error: {e}")
            raise Exception(f"Stripe error: {e.user_message}")

    def create_checkout_session(
        self,
        price_id: str,
        customer_email: str,
        tenant_id: str,
        success_url: str,
        cancel_url: str,
        mode: str = "subscription"
    ) -> Dict[str, Any]:
        """Create a Stripe Checkout session for subscription signup."""
        try:
            session = stripe.checkout.Session.create(
                customer_email=customer_email,
                payment_method_types=["card"],
                line_items=[{"price": price_id, "quantity": 1}],
                mode=mode,
                success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
                cancel_url=cancel_url,
                metadata={"tenant_id": tenant_id},
            )
            return {
                "session_id": session.id,
                "url": session.url,
                "publishable_key": self.publishable_key
            }
        except stripe.error.StripeError as e:
            logger.error(f"Stripe checkout session error: {e}")
            raise Exception(f"Stripe error: {e.user_message}")

    def create_billing_portal_session(self, customer_id: str, return_url: str) -> str:
        """Create a Stripe Customer Portal session for managing subscription."""
        try:
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url
            )
            return session.url
        except stripe.error.StripeError as e:
            logger.error(f"Stripe billing portal error: {e}")
            raise Exception(f"Stripe error: {e.user_message}")

    def cancel_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """Cancel a subscription at period end."""
        try:
            sub = stripe.Subscription.modify(
                subscription_id,
                cancel_at_period_end=True
            )
            return {"id": sub.id, "status": sub.status, "cancel_at_period_end": sub.cancel_at_period_end}
        except stripe.error.StripeError as e:
            raise Exception(f"Stripe error: {e.user_message}")

    def get_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """Retrieve subscription details."""
        try:
            sub = stripe.Subscription.retrieve(subscription_id)
            return {
                "id": sub.id,
                "status": sub.status,
                "current_period_end": sub.current_period_end,
                "plan": sub.plan.id if sub.plan else None,
            }
        except stripe.error.StripeError as e:
            raise Exception(f"Stripe error: {e.user_message}")

    def list_invoices(self, customer_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """List Stripe invoices for a customer."""
        try:
            invoices = stripe.Invoice.list(customer=customer_id, limit=limit)
            return [
                {
                    "id": inv.id,
                    "amount_due": inv.amount_due,
                    "amount_paid": inv.amount_paid,
                    "currency": inv.currency,
                    "status": inv.status,
                    "created": inv.created,
                    "invoice_pdf": inv.invoice_pdf,
                    "hosted_invoice_url": inv.hosted_invoice_url,
                }
                for inv in invoices.data
            ]
        except stripe.error.StripeError as e:
            raise Exception(f"Stripe error: {e.user_message}")

    def construct_webhook_event(self, payload: bytes, sig_header: str) -> Dict[str, Any]:
        """Construct and verify a Stripe webhook event."""
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, self.webhook_secret)
            return {"type": event.type, "data": event.data.object}
        except stripe.error.SignatureVerificationError:
            raise Exception("Invalid Stripe webhook signature")


# Global singleton
stripe_gateway = StripeGateway()
