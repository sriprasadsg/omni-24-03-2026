"""Shared tenant resolver for the ITAM cost, KPI and report routes, pre-built and custom (Phase 78, D-13; custom report routes added 2026-11-17).

Why the header is read here: TenantMiddleware applies a Platform Owner's X-Tenant-ID, but the
authentication dependencies (verify_token and verify_token_async) reset the ambient tenant to
the token's own tenant afterwards, so a handler cannot see the switcher's choice through
tenant_context. The resolver therefore reads the header itself and writes the ambient tenant
back, so the tenant-isolating database wrapper scopes reads to the resolved tenant.

Only the Owner tier, on a session (never an API key), may choose a tenant (D-15, amended
2026-11-16: no role is widened). A caller whose role lacks the route's permission is refused
by the route guard with 403 before this resolver runs; Platform Support and an Owner with no
choice get 400 here, before any database read.

This is a plain synchronous function called from the handler body, never a FastAPI dependency:
a synchronous dependency runs in a threadpool copy of the context, so its set_tenant_id would
not reach the handler. TenantMiddleware restores the context after the request.
"""
from fastapi import HTTPException, Request, status

import rbac_defaults
import tenant_context
from auth_types import TokenData

TENANT_REQUIRED_DETAIL = "Select a tenant: ITAM figures cover one organization at a time."


def resolve_itam_tenant(request: Request, current_user: TokenData) -> str:
    """The one tenant this request's ITAM figures cover; 400 when there is none."""
    tenant_id = current_user.tenant_id
    header = (request.headers.get("X-Tenant-ID") or "").strip()
    if (
        header
        and current_user.auth_source == "session"
        and rbac_defaults.platform_tier(current_user.role) == "owner"
    ):
        tenant_id = header
    if not tenant_id or tenant_id == rbac_defaults.PLATFORM_TENANT_ID:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=TENANT_REQUIRED_DETAIL)
    tenant_context.set_tenant_id(tenant_id)
    return tenant_id
