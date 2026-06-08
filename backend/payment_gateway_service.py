from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid
from datetime import datetime, timezone


class PaymentGatewayType(str, Enum):
    STRIPE = "stripe"
    PAYPAL = "paypal"
    RAZORPAY = "razorpay"
    SQUARE = "square"
    CUSTOM = "custom"


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    CANCELED = "canceled"
    PAST_DUE = "past_due"
    TRIALING = "trialing"
    INCOMPLETE = "incomplete"


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    OPEN = "open"
    PAID = "paid"
    VOID = "void"
    UNCOLLECTIBLE = "uncollectible"


class PaymentGatewayInterface(ABC):
    """Abstract base class for all payment gateway implementations"""
    
    def __init__(self, credentials: Dict[str, str]):
        self.credentials = credentials
    
    @abstractmethod
    async def create_customer(self, email: str, name: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Create a customer in the payment gateway"""
        pass
    
    @abstractmethod
    async def create_subscription(
        self,
        customer_id: str,
        price_id: str,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Create a subscription for a customer"""
        pass
    
    @abstractmethod
    async def cancel_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """Cancel a subscription"""
        pass
    
    @abstractmethod
    async def create_charge(
        self,
        customer_id: str,
        amount: int,
        currency: str,
        description: str,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Create a one-time charge"""
        pass
    
    @abstractmethod
    async def create_refund(self, charge_id: str, amount: Optional[int] = None) -> Dict[str, Any]:
        """Refund a charge"""
        pass
    
    @abstractmethod
    async def get_invoices(self, customer_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get invoices for a customer"""
        pass
    
    @abstractmethod
    async def verify_webhook(self, payload: bytes, signature: str, secret: str) -> bool:
        """Verify webhook signature"""
        pass
    
    @abstractmethod
    async def construct_webhook_event(self, payload: bytes, signature: str, secret: str) -> Dict[str, Any]:
        """Construct and verify webhook event"""
        pass

    @abstractmethod
    async def list_payment_methods(self, customer_id: str) -> List[Dict[str, Any]]:
        """List payment methods for a customer"""
        pass

    @abstractmethod
    async def add_payment_method(self, customer_id: str, payment_method_id: str) -> Dict[str, Any]:
        """Add a payment method to a customer"""
        pass

    @abstractmethod
    async def delete_payment_method(self, payment_method_id: str) -> bool:
        """Delete/Detach a payment method"""
        pass


class GenericGateway(PaymentGatewayInterface):
    """Manual / bank-transfer payment gateway for tenants without Stripe or PayPal.

    All operations are persisted to MongoDB using the same schema as the Stripe gateway,
    so InvoiceList, SubscriptionManagement, and PaymentSettings render real data.
    Records are tagged with ``gateway: "manual"`` for admin reconciliation.
    """

    _GATEWAY = "manual"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _ts(self) -> int:
        return int(datetime.now(timezone.utc).timestamp())

    async def _db(self):
        from database import get_database
        return get_database()

    async def create_customer(self, email: str, name: str, metadata=None):
        cust_id = f"cust_{uuid.uuid4().hex[:12]}"
        db = await self._db()
        doc = {
            "id": cust_id,
            "email": email,
            "name": name,
            "gateway": self._GATEWAY,
            "metadata": metadata or {},
            "created_at": self._now(),
        }
        await db.payment_customers.update_one({"email": email}, {"$set": doc}, upsert=True)
        return {"id": cust_id, "email": email, "name": name}

    async def create_subscription(self, customer_id: str, price_id: str, metadata=None):
        sub_id = f"sub_{uuid.uuid4().hex[:16]}"
        now_ts = self._ts()
        # One month from now
        period_end = now_ts + 30 * 24 * 3600
        db = await self._db()
        doc = {
            "id": sub_id,
            "customer_id": customer_id,
            "price_id": price_id,
            "status": "active",
            "gateway": self._GATEWAY,
            "current_period_start": now_ts,
            "current_period_end": period_end,
            "plan": {"amount": 0, "currency": "usd", "interval": "month"},
            "metadata": metadata or {},
            "created_at": self._now(),
        }
        await db.subscriptions.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def cancel_subscription(self, subscription_id: str):
        db = await self._db()
        now = self._now()
        await db.subscriptions.update_one(
            {"id": subscription_id},
            {"$set": {"status": "canceled", "canceled_at": now}},
        )
        return {"id": subscription_id, "status": "canceled", "canceled_at": now}

    async def create_charge(self, customer_id: str, amount: int, currency: str, description: str, metadata=None):
        charge_id = f"ch_{uuid.uuid4().hex[:16]}"
        db = await self._db()
        doc = {
            "id": charge_id,
            "customer_id": customer_id,
            "amount": amount,
            "currency": currency,
            "description": description,
            "status": "pending",
            "paid": False,
            "gateway": self._GATEWAY,
            "metadata": metadata or {},
            "created": self._ts(),
            "created_at": self._now(),
        }
        await db.charges.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def create_refund(self, charge_id: str, amount=None):
        refund_id = f"re_{uuid.uuid4().hex[:16]}"
        db = await self._db()
        doc = {
            "id": refund_id,
            "charge_id": charge_id,
            "amount": amount,
            "gateway": self._GATEWAY,
            "status": "pending",
            "created_at": self._now(),
        }
        await db.refunds.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def get_invoices(self, customer_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        db = await self._db()
        docs = await db.invoices.find(
            {"customer_id": customer_id, "gateway": self._GATEWAY},
            {"_id": 0},
        ).sort("created_at", -1).limit(limit).to_list(limit)
        return docs

    async def verify_webhook(self, payload, signature, secret) -> bool:
        # Manual gateway has no webhook signature to verify
        return True

    async def construct_webhook_event(self, payload, signature, secret) -> Dict[str, Any]:
        # Manual gateway: treat any incoming POST as a generic event
        import json as _json
        try:
            data = _json.loads(payload) if isinstance(payload, (bytes, str)) else payload
        except Exception:
            data = {}
        return {"type": "manual.event", "data": {"object": data}, "gateway": self._GATEWAY}

    async def list_payment_methods(self, customer_id: str) -> List[Dict[str, Any]]:
        # Always expose a single "Bank Transfer / Manual" entry so the UI is not empty
        db = await self._db()
        stored = await db.payment_methods.find(
            {"customer_id": customer_id, "gateway": self._GATEWAY},
            {"_id": 0},
        ).to_list(20)
        if stored:
            return stored
        return [{
            "id": f"pm_manual_{customer_id}",
            "type": "bank_transfer",
            "gateway": self._GATEWAY,
            "bank_transfer": {"bank_name": "Manual / Bank Transfer"},
            "created_at": self._now(),
        }]

    async def add_payment_method(self, customer_id: str, payment_method_id: str):
        db = await self._db()
        doc = {
            "id": payment_method_id,
            "customer_id": customer_id,
            "type": "bank_transfer",
            "gateway": self._GATEWAY,
            "created_at": self._now(),
        }
        await db.payment_methods.update_one(
            {"id": payment_method_id}, {"$set": doc}, upsert=True
        )
        return doc

    async def delete_payment_method(self, payment_method_id: str) -> bool:
        db = await self._db()
        result = await db.payment_methods.delete_one({"id": payment_method_id})
        return result.deleted_count > 0


class PaymentGatewayFactory:
    """Factory to create payment gateway instances"""

    @staticmethod
    def create_gateway(gateway_type: PaymentGatewayType, credentials: Dict[str, str]) -> PaymentGatewayInterface:
        if gateway_type == PaymentGatewayType.STRIPE:
            from payment_gateways.stripe_gateway import StripeGateway
            return StripeGateway(credentials)
        elif gateway_type == PaymentGatewayType.PAYPAL:
            from payment_gateways.paypal_gateway import PayPalGateway
            return PayPalGateway(credentials)
        elif gateway_type == PaymentGatewayType.RAZORPAY:
            from payment_gateways.razorpay_gateway import RazorpayGateway
            return RazorpayGateway(credentials)
        elif gateway_type == PaymentGatewayType.SQUARE:
            from payment_gateways.square_gateway import SquareGateway
            return SquareGateway(credentials)
        else:
            # CUSTOM or any future type — use the generic credential store
            return GenericGateway(credentials)
