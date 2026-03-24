
import razorpay
from typing import Dict, List, Optional, Any
from payment_gateway_service import PaymentGatewayInterface
import logging

logger = logging.getLogger(__name__)

class RazorpayGateway(PaymentGatewayInterface):
    def __init__(self, credentials: Dict[str, str]):
        super().__init__(credentials)
        self.client = razorpay.Client(auth=(
            credentials.get("key_id"),
            credentials.get("key_secret")
        ))

    async def create_customer(self, email: str, name: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        try:
            customer = self.client.customer.create({
                "name": name,
                "email": email,
                "notes": metadata
            })
            return customer
        except Exception as e:
            logger.error(f"Razorpay customer creation failed: {e}")
            raise

    async def create_subscription(
        self,
        customer_id: str,
        price_id: str, # Plan ID
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        try:
            subscription = self.client.subscription.create({
                "plan_id": price_id,
                "customer_notify": 1,
                "total_count": 12, # recurring
                "notes": metadata
            })
            return {
                "id": subscription["id"],
                "status": subscription["status"], # created, authenticated, active
                "plan": {
                    "id": price_id,
                    "currency": "INR" # Razorpay default usually
                },
                "current_period_start": subscription.get("current_start"),
                "current_period_end": subscription.get("current_end"),
                "short_url": subscription.get("short_url")
            }
        except Exception as e:
            logger.error(f"Razorpay subscription failed: {e}")
            raise

    async def cancel_subscription(self, subscription_id: str) -> Dict[str, Any]:
        try:
            self.client.subscription.cancel(subscription_id)
            return {"status": "canceled"}
        except Exception as e:
            logger.error(f"Razorpay cancel failed: {e}")
            raise

    async def create_charge(
        self,
        customer_id: str,
        amount: int,
        currency: str,
        description: str,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        try:
            # Razorpay order creation
            order = self.client.order.create({
                "amount": amount, # paise
                "currency": currency,
                "receipt": metadata.get("order_id", "receipt#1"),
                "notes": metadata
            })
            return {
                "id": order["id"],
                "amount": order["amount"],
                "currency": order["currency"],
                "status": order["status"],
                "paid": False, # Orders are created first, then paid
                "created": order["created_at"]
            }
        except Exception as e:
            logger.error(f"Razorpay charge failed: {e}")
            raise

    async def create_refund(self, charge_id: str, amount: Optional[int] = None) -> Dict[str, Any]:
        # charge_id here refers to payment_id for Razorpay? Or order_id? 
        # Usually refund is on payment_id. Assuming charge_id = payment_id
        try:
            data = {"amount": amount} if amount else {}
            refund = self.client.payment.refund(charge_id, data)
            return {"id": refund["id"], "status": "processed"}
        except Exception as e:
            logger.error(f"Razorpay refund failed: {e}")
            raise

    async def get_invoices(self, customer_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        return []

    async def verify_webhook(self, payload: bytes, signature: str, secret: str) -> bool:
        try:
            self.client.utility.verify_webhook_signature(payload.decode(), signature, secret)
            return True
        except Exception:
            return False

    async def construct_webhook_event(self, payload: bytes, signature: str, secret: str) -> Dict[str, Any]:
        import json
        event = json.loads(payload)
        return {
            "id": event.get("entity", {}).get("id"),
            "type": event.get("event"),
            "data": event.get("payload")
        }
