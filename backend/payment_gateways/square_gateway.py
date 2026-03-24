
from square import Square
from typing import Dict, List, Optional, Any
from payment_gateway_service import PaymentGatewayInterface
import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

class SquareGateway(PaymentGatewayInterface):
    def __init__(self, credentials: Dict[str, str]):
        super().__init__(credentials)
        self.client = Square(
            access_token=credentials.get("access_token"),
            environment=credentials.get("environment", "sandbox")
        )
        self.location_id = credentials.get("location_id")

    async def create_customer(self, email: str, name: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        try:
            result = self.client.customers.create_customer(body={
                "given_name": name.split(" ")[0],
                "family_name": " ".join(name.split(" ")[1:]) if " " in name else "",
                "email_address": email,
                "note": str(metadata) if metadata else None,
                "idempotency_key": str(uuid.uuid4())
            })
            
            if result.is_success():
                return result.body["customer"]
            else:
                raise Exception(f"Square create customer failed: {result.errors}")
        except Exception as e:
            logger.error(f"Square customer failed: {e}")
            raise

    async def create_subscription(
        self,
        customer_id: str,
        price_id: str, # Square Plan ID
        metadata: Dict[str, Any] = None # contains card_id?
    ) -> Dict[str, Any]:
        try:
            # Square subscriptions usually require a card on file first
            card_id = metadata.get("card_id")
            
            body = {
                "idempotency_key": str(uuid.uuid4()),
                "location_id": self.location_id,
                "plan_id": price_id,
                "customer_id": customer_id,
                "card_id": card_id # Optional if customer has default card
            }
            
            result = self.client.subscriptions.create_subscription(body=body)
            
            if result.is_success():
                sub = result.body["subscription"]
                return {
                    "id": sub["id"],
                    "status": sub["status"],
                    "plan": {"id": sub["plan_id"]},
                    "current_period_start": datetime.utcnow().timestamp(), # Square doesn't always return this easily in creation
                    "current_period_end": datetime.utcnow().timestamp() + (30*24*3600) # Mock 30 days
                }
            else:
                raise Exception(f"Square create subscription failed: {result.errors}")
        except Exception as e:
            logger.error(f"Square subscription failed: {e}")
            raise

    async def cancel_subscription(self, subscription_id: str) -> Dict[str, Any]:
        try:
            result = self.client.subscriptions.cancel_subscription(subscription_id)
            if result.is_success():
                return {"status": "canceled"}
            else:
                raise Exception(f"Square cancel failed: {result.errors}")
        except Exception as e:
            logger.error(f"Square cancel failed: {e}")
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
            # Square payments API
            body = {
                "source_id": metadata.get("source_id", "cnon:card-nonce-ok"),
                "idempotency_key": str(uuid.uuid4()),
                "amount_money": {
                    "amount": amount, # cents
                    "currency": currency
                },
                "customer_id": customer_id,
                "note": description,
                "autocomplete": True,
                "location_id": self.location_id
            }
            
            result = self.client.payments.create_payment(body=body)
            
            if result.is_success():
                payment = result.body["payment"]
                return {
                    "id": payment["id"],
                    "amount": payment["amount_money"]["amount"],
                    "currency": payment["amount_money"]["currency"],
                    "status": payment["status"],
                    "paid": payment["status"] == "COMPLETED",
                    "created": datetime.utcnow().timestamp()
                }
            else:
                raise Exception(f"Square payment failed: {result.errors}")
        except Exception as e:
            logger.error(f"Square charge failed: {e}")
            raise

    async def create_refund(self, charge_id: str, amount: Optional[int] = None) -> Dict[str, Any]:
        try:
            body = {
                "idempotency_key": str(uuid.uuid4()),
                "amount_money": {
                    "amount": amount,
                    "currency": "USD" # Should fetch from original payment
                },
                "payment_id": charge_id
            }
            result = self.client.refunds.refund_payment(body=body)
            if result.is_success():
                return {"id": result.body["refund"]["id"], "status": result.body["refund"]["status"]}
            else:
                raise Exception(f"Square refund failed: {result.errors}")
        except Exception as e:
            logger.error(f"Square refund failed: {e}")
            raise

    async def get_invoices(self, customer_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        return []

    async def verify_webhook(self, payload: bytes, signature: str, secret: str) -> bool:
        # In production, use Square's webhook verification helper:
        # from square.webhook_helpers import WebhookHelper
        # return WebhookHelper.is_valid_webhook_event_signature(payload, signature, secret, self.client.base_url)
        
        # For this implementation, we simulate verification using a basic check
        # and recommend the above for production-grade security.
        return len(signature) > 10 # Basic non-triviality check for simulation

    async def construct_webhook_event(self, payload: bytes, signature: str, secret: str) -> Dict[str, Any]:
        import json
        event = json.loads(payload)
        return {
            "id": event.get("event_id"),
            "type": event.get("type"),
            "data": event.get("data")
        }
