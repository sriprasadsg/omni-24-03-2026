from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class PaymentGatewayType(str, Enum):
    STRIPE = "stripe"
    PAYPAL = "paypal"
    RAZORPAY = "razorpay"
    SQUARE = "square"


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


class PaymentGatewayFactory:
    """Factory to create payment gateway instances"""
    
    @staticmethod
    def create_gateway(gateway_type: PaymentGatewayType, credentials: Dict[str, str]) -> PaymentGatewayInterface:
        """Create a payment gateway instance based on type"""
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
            raise ValueError(f"Unsupported payment gateway type: {gateway_type}")
