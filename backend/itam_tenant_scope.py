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

A tenant the Owner names in the header must exist (IN-01): an unknown id is a 400, so a typo
cannot read empty figures or have an export or a saved report written under a tenant that does not
exist. The database is reached only for that header case, through the caller's own get_database.

This is a plain function awaited from the handler body, never a FastAPI dependency: a dependency
runs in a copy of the context, so its set_tenant_id would not reach the handler. TenantMiddleware
restores the context after the request.
"""
from typing import Any, Callable

from fastapi import HTTPException, Request, status

import rbac_defaults
import tenant_context
from auth_types import TokenData

TENANT_REQUIRED_DETAIL = "Select a tenant: ITAM figures cover one organization at a time."
UNKNOWN_TENANT_DETAIL = "Unknown tenant: the selected organization does not exist."


async def resolve_itam_tenant(request: Request, current_user: TokenData, get_db: Callable[[], Any]) -> str:
    """The one tenant this request's ITAM figures cover; 400 when there is none or it does not exist.

    get_db is the calling module's own get_database, called only when an Owner's header names the tenant.
    """
    tenant_id = current_user.tenant_id
    header = (request.headers.get("X-Tenant-ID") or "").strip()
    from_header = bool(
        header
        and current_user.auth_source == "session"
        and rbac_defaults.platform_tier(current_user.role) == "owner"
    )
    if from_header:
        tenant_id = header
    if not tenant_id or tenant_id == rbac_defaults.PLATFORM_TENANT_ID:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=TENANT_REQUIRED_DETAIL)
    if from_header and await get_db().tenants.find_one({"id": tenant_id}, {"_id": 1}) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=UNKNOWN_TENANT_DETAIL)
    tenant_context.set_tenant_id(tenant_id)
    return tenant_id
