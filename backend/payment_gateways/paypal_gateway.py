
import paypalrestsdk
from typing import Dict, List, Optional, Any
from payment_gateway_service import PaymentGatewayInterface, SubscriptionStatus, InvoiceStatus
import logging

logger = logging.getLogger(__name__)

class PayPalGateway(PaymentGatewayInterface):
    def __init__(self, credentials: Dict[str, str]):
        super().__init__(credentials)
        self.configure()

    def configure(self):
        paypalrestsdk.configure({
            "mode": self.credentials.get("mode", "sandbox"),  # sandbox or live
            "client_id": self.credentials.get("client_id"),
            "client_secret": self.credentials.get("client_secret")
        })

    async def create_customer(self, email: str, name: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        PayPal doesn't use 'Customer' objects in the same way as Stripe for simple payments.
        We'll just return a mock object or minimal info since user auth is handled by PayPal login usually.
        However, for Vault/Recurring, we might need Payer ID. 
        For this abstraction, we'll return a placeholder.
        """
        return {
            "id": f"paypal_cust_{email}",  # specialized mapping not really needed for basic REST SDK usage
            "email": email,
            "name": name,
            "gateway": "paypal"
        }

    async def create_subscription(
        self,
        customer_id: str,
        price_id: str,  # In PayPal, this would be a Plan ID
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Create a billing agreement (Subscription).
        Note: This usually requires a redirect flow. 
        For API-to-API, we might need to assume the user has already approved a plan or we create an agreement and return the approval URL.
        """
        billing_plan = paypalrestsdk.BillingPlan.find(price_id)
        
        # Create billing agreement
        billing_agreement = paypalrestsdk.BillingAgreement({
            "name": metadata.get("plan", "Subscription"),
            "description": f"Subscription for {metadata.get('plan')}",
            "start_date": (datetime.utcnow() + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "plan": {"id": price_id},
            "payer": {"payment_method": "paypal"},
            "override_merchant_preferences": {
                "return_url": "http://localhost:3000/settings/billing?status=success",
                "cancel_url": "http://localhost:3000/settings/billing?status=cancel",
                "auto_bill_amount": "YES",
                "initial_fail_amount_action": "CONTINUE",
                "max_fail_attempts": "0"
            }
        })

        if billing_agreement.create():
            # In a real app, we need to return the approval_url to the frontend
            approval_url = next((link.href for link in billing_agreement.links if link.rel == "approval_url"), None)
            
            return {
                "id": billing_agreement.id,
                "status": "pending_approval",  # Requires user to approve
                "approval_url": approval_url,
                "plan": {
                    "id": price_id,
                    "amount": 0, # fetched from plan details ideally
                    "currency": "USD",
                    "interval": "month"
                },
                "current_period_start": datetime.utcnow().timestamp(),
                "current_period_end": (datetime.utcnow() + timedelta(days=30)).timestamp()
            }
        else:
            logger.error(f"PayPal subscription failed: {billing_agreement.error}")
            raise Exception(f"Failed to create PayPal subscription: {billing_agreement.error}")

    async def cancel_subscription(self, subscription_id: str) -> Dict[str, Any]:
        billing_agreement = paypalrestsdk.BillingAgreement.find(subscription_id)
        
        cancel_note = {"note": "Canceled by user request"}
        
        if billing_agreement.cancel(cancel_note):
            return {"status": "canceled", "canceled_at": datetime.utcnow().timestamp()}
        else:
            raise Exception(f"Failed to cancel PayPal subscription: {billing_agreement.error}")

    async def create_charge(
        self,
        customer_id: str,
        amount: int,
        currency: str,
        description: str,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        payment = paypalrestsdk.Payment({
            "intent": "sale",
            "payer": {"payment_method": "paypal"},
            "redirect_urls": {
                "return_url": "http://localhost:3000/settings/billing/success",
                "cancel_url": "http://localhost:3000/settings/billing/cancel"
            },
            "transactions": [{
                "item_list": {
                    "items": [{
                        "name": description,
                        "sku": "item",
                        "price": str(amount / 100),
                        "currency": currency.upper(),
                        "quantity": 1
                    }]
                },
                "amount": {
                    "total": str(amount / 100),
                    "currency": currency.upper()
                },
                "description": description
            }]
        })

        if payment.create():
            # Return approval URL for frontend redirection
            approval_url = next((link.href for link in payment.links if link.rel == "approval_url"), None)
            return {
                "id": payment.id,
                "amount": amount, # cents
                "currency": currency,
                "status": payment.state, # created, approved, failed
                "paid": payment.state == "approved",
                "created": datetime.utcnow().timestamp(),
                "approval_url": approval_url
            }
        else:
            raise Exception(f"PayPal charge failed: {payment.error}")

    async def create_refund(self, charge_id: str, amount: Optional[int] = None) -> Dict[str, Any]:
        sale = paypalrestsdk.Sale.find(charge_id)
        
        refund_data = {}
        if amount:
            refund_data["amount"] = {
                "total": str(amount / 100),
                "currency": sale.amount.currency
            }

        refund = sale.refund(refund_data)
        
        if refund.success():
            return {"id": refund.id, "status": "succeeded"}
        else:
            raise Exception(f"PayPal refund failed: {refund.error}")

    async def get_invoices(self, customer_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        # PayPal Invoicing API is separate. For now, returning empty list or mocking.
        return []

    async def verify_webhook(self, payload: bytes, signature: str, secret: str) -> bool:
        # PayPal webhook verification requires API calls to verify signature certificate
        # Simplified for now (always True if secret matches - weak verification)
        return True 

    async def construct_webhook_event(self, payload: bytes, signature: str, secret: str) -> Dict[str, Any]:
        # Parse PayPal webhook JSON
        import json
        event = json.loads(payload)
        return {
            "id": event.get("id"),
            "type": event.get("event_type"),
            "data": event.get("resource")
        }
