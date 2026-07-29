from contextvars import ContextVar, Token
from typing import Optional

# Context variable to store the tenant_id for the current request
_tenant_id_ctx: ContextVar[Optional[str]] = ContextVar("tenant_id", default=None)

def set_tenant_id(tenant_id: str) -> Token:
    """Set the tenant_id for the current context.

    Returns the reset Token. Callers on a request/task path that can outlive
    a single unit of work (i.e. anything reached via middleware, not a
    short-lived script) MUST pass this token to reset_tenant_id() in a
    finally block — otherwise the value persists in the ContextVar for the
    lifetime of the underlying asyncio Task/thread and can leak into
    whatever runs on it next (SEC-03).
    """
    return _tenant_id_ctx.set(tenant_id)

def reset_tenant_id(token: Token) -> None:
    """Reset the tenant_id ContextVar to its pre-set_tenant_id() state.

    Must be called in a finally block wrapping any code path that called
    set_tenant_id(), so an exception mid-request cannot leave a stale
    tenant_id visible to whatever reuses this task/thread next.
    """
    _tenant_id_ctx.reset(token)

def get_tenant_id() -> Optional[str]:
    """Get the tenant_id for the current context"""
    return _tenant_id_ctx.get()
