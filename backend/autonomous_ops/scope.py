"""Database handle and tenant-context helpers for Autonomous Ops.

The package works on the raw Mongo handle with an explicit tenantId on every filter and
document. It never uses the ambient tenant ContextVar: under ``platform-admin`` the
tenant-isolating wrapper injects no filter and stamps no tenantId, and with no context it
stamps an orphan marker. ``tenant_scope`` exists only for the rare call into a tenant-wrapped
helper elsewhere in the backend.
"""
from contextlib import contextmanager


def raw(db):
    """The raw Motor database behind the tenant wrapper; anything else (a raw Motor
    database, a MagicMock) is returned unchanged."""
    from database import TenantIsolatedDatabase
    return db._db if isinstance(db, TenantIsolatedDatabase) else db


@contextmanager
def tenant_scope(tenant_id):
    """Set the tenant ContextVar for the block and always reset it, even on error (SEC-03)."""
    import tenant_context
    token = tenant_context.set_tenant_id(tenant_id)
    try:
        yield
    finally:
        tenant_context.reset_tenant_id(token)
