from contextvars import ContextVar
from typing import Optional

# Context variable to store the tenant_id for the current request
_tenant_id_ctx: ContextVar[Optional[str]] = ContextVar("tenant_id", default=None)

def set_tenant_id(tenant_id: str):
    """Set the tenant_id for the current context"""
    _tenant_id_ctx.set(tenant_id)

def get_tenant_id() -> Optional[str]:
    """Get the tenant_id for the current context"""
    return _tenant_id_ctx.get()
