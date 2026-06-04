from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from enum import Enum


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
    """Credential store for custom / third-party gateways with no built-in API client.

    IMPORTANT — KNOWN GAP: All billing operations below are no-ops that return
    stub/placeholder responses. The `SubscriptionManagement` and `InvoiceList` frontend
    components will render empty data for any tenant configured with a Custom gateway.

    To integrate a real gateway, subclass this and override the relevant methods,
    then register the subclass in PaymentGatewayFactory below.
    """

    _warn_logged: set[str] = set()

    def _warn_noop(self, method: str) -> None:
        import logging as _log
        if method not in self._warn_logged:
            _log.getLogger(__name__).warning(
                "GenericGateway.%s called — this is a no-op stub. "
                "Integrate a real payment gateway to enable this operation.", method
            )
            self._warn_logged.add(method)

    async def create_customer(self, email, name, metadata=None):
        return {"id": f"cust_{email}", "email": email}

    async def create_subscription(self, customer_id, price_id, metadata=None):
        return {"id": f"sub_{customer_id}", "status": "active",
                "current_period_start": 0, "current_period_end": 0,
                "plan": {"amount": 0, "currency": "usd", "interval": "month"}}

    async def cancel_subscription(self, subscription_id):
        return {"id": subscription_id, "canceled_at": 0}

    async def create_charge(self, customer_id, amount, currency, description, metadata=None):
        return {"id": f"ch_{customer_id}", "amount": amount, "currency": currency,
                "description": description, "status": "succeeded", "paid": True, "created": 0}

    async def create_refund(self, charge_id, amount=None):
        return {"id": f"re_{charge_id}", "amount": amount}

    async def get_invoices(self, customer_id, limit=10):
        self._warn_noop("get_invoices")
        return []  # ← always empty; SubscriptionManagement/InvoiceList will show nothing

    async def verify_webhook(self, payload, signature, secret):
        return False

    async def construct_webhook_event(self, payload, signature, secret):
        raise NotImplementedError("Webhooks not supported for custom gateways")

    async def list_payment_methods(self, customer_id):
        self._warn_noop("list_payment_methods")
        return []  # ← always empty; Payment Settings page will show no saved cards

    async def add_payment_method(self, customer_id, payment_method_id):
        return {"id": payment_method_id}

    async def delete_payment_method(self, payment_method_id):
        return True


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
