"""SCIM 2.0 routes (scim_service, scim_groups).

* /api/admin/sso/scim/tokens: an organization's admins (User Management catalogue, plus manage:users) create,
  list and revoke the bearer tokens their identity provider uses. A token belongs to one real organization, so
  the platform scope (a Super Admin not viewing a tenant) is refused.
* /api/scim/v2: the identity provider's API (Users, Groups, ServiceProviderConfig, ResourceTypes, Schemas). It has
  no session: the bearer token, checked on every request, names the tenant, and nothing outside that tenant is
  read or written. Answers are application/scim+json with SCIM error bodies.
"""
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

import rbac_defaults
import scim_groups
import scim_service
from auth_types import TokenData
from authentication_service import get_current_user
from catalogue_mounts_billing_identity import USER_MANAGEMENT_GUARD
from database import get_database
from rbac_utils import require_permission
from scim_service import GROUP_SCHEMA, USER_SCHEMA, ScimError
from tenant_context import get_tenant_id

MEDIA = "application/scim+json"
MAX_BODY = 1_000_000

admin_router = APIRouter(prefix="/api/admin/sso/scim", tags=["SCIM"],
                         dependencies=[Depends(USER_MANAGEMENT_GUARD), Depends(require_permission("manage:users"))])
router = APIRouter(prefix="/api/scim/v2", tags=["SCIM"])


class TokenIn(BaseModel):
    label: Optional[str] = Field(None, max_length=80)

    model_config = {"extra": "forbid"}


def _admin_tenant() -> str:
    tenant = get_tenant_id()
    if not tenant or tenant == rbac_defaults.PLATFORM_TENANT_ID:
        raise HTTPException(status_code=400, detail="Select a tenant: a SCIM token belongs to one organization")
    return tenant


async def _admin(fn: Callable, *args: Any):
    try:
        return await fn(get_database(), *args)
    except ScimError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)


@admin_router.get("/tokens")
async def list_scim_tokens(current_user: TokenData = Depends(get_current_user)):
    """The organization's SCIM tokens (never the token values) and the API path to give the identity provider."""
    tenant = _admin_tenant()
    return {"items": await _admin(scim_service.list_tokens, tenant), "basePath": router.prefix}


@admin_router.post("/tokens")
async def create_scim_token(body: TokenIn, current_user: TokenData = Depends(get_current_user)):
    """A new token, shown once."""
    tenant = _admin_tenant()
    out = await _admin(scim_service.create_token, tenant, current_user.username, body.label)
    await scim_service.audit(get_database(), "scim.token.create", tenant, current_user.username, resourceId=out["id"])
    return {**out, "basePath": router.prefix}


@admin_router.delete("/tokens/{token_id}")
async def revoke_scim_token(token_id: str, current_user: TokenData = Depends(get_current_user)):
    tenant = _admin_tenant()
    await _admin(scim_service.revoke_token, tenant, token_id[:64], current_user.username)
    await scim_service.audit(get_database(), "scim.token.revoke", tenant, current_user.username, resourceId=token_id[:64])
    return {"success": True}


# ── The identity provider's API ─────────────────────────────────────────────


async def scim_caller(request: Request) -> Dict[str, Any]:
    """The token record (tenant, prefix) of the presented bearer token; 401 for anything else."""
    header = request.headers.get("authorization") or ""
    record = None
    if header[:7].lower() == "bearer ":
        record = await scim_service.token_record(get_database(), header[7:].strip())
    if not record:
        raise HTTPException(status_code=401, detail="A valid SCIM bearer token is required",
                            headers={"WWW-Authenticate": "Bearer"})
    return record


def _base(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return f"{proto}://{request.headers.get('host') or request.url.netloc}{router.prefix}"


def _actor(caller: Dict[str, Any]) -> str:
    return f"scim:{caller.get('prefix')}"


async def _json(request: Request) -> Dict[str, Any]:
    if int(request.headers.get("content-length") or 0) > MAX_BODY:
        raise ScimError(413, "The request body is too large")
    try:
        data = await request.json()
    except ValueError:
        raise ScimError(400, "The body is not JSON", "invalidSyntax")
    if not isinstance(data, dict):
        raise ScimError(400, "The body must be a JSON object", "invalidSyntax")
    return data


async def _answer(coro, status: int = 200):
    try:
        out = await coro
    except ScimError as e:
        return JSONResponse(e.body(), status_code=e.status, media_type=MEDIA)
    if out is None:
        return Response(status_code=204)
    return JSONResponse(out, status_code=status, media_type=MEDIA)


@router.get("/ServiceProviderConfig")
async def service_provider_config(caller: Dict[str, Any] = Depends(scim_caller)):
    return JSONResponse({
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
        "patch": {"supported": True}, "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
        "filter": {"supported": True, "maxResults": scim_service.MAX_COUNT}, "changePassword": {"supported": False},
        "sort": {"supported": False}, "etag": {"supported": False},
        "authenticationSchemes": [{"type": "oauthbearertoken", "name": "Bearer token", "primary": True,
                                   "description": "A per-organization token created under User Management"}],
    }, media_type=MEDIA)


@router.get("/ResourceTypes")
async def resource_types(request: Request, caller: Dict[str, Any] = Depends(scim_caller)):
    base = _base(request)
    types = [{"schemas": ["urn:ietf:params:scim:schemas:core:2.0:ResourceType"], "id": n, "name": n, "endpoint": f"/{n}s",
              "schema": s, "meta": {"resourceType": "ResourceType", "location": f"{base}/ResourceTypes/{n}"}}
             for n, s in (("User", USER_SCHEMA), ("Group", GROUP_SCHEMA))]
    return JSONResponse(scim_service.list_response(types, 2, 1), media_type=MEDIA)


@router.get("/Schemas")
async def schemas(caller: Dict[str, Any] = Depends(scim_caller)):
    items = [{"schemas": ["urn:ietf:params:scim:schemas:core:2.0:Schema"], "id": s, "name": n}
             for n, s in (("User", USER_SCHEMA), ("Group", GROUP_SCHEMA))]
    return JSONResponse(scim_service.list_response(items, 2, 1), media_type=MEDIA)


@router.get("/Users")
async def list_users(request: Request, filter: Optional[str] = Query(None, max_length=500),
                     startIndex: Optional[int] = Query(None, ge=1), count: Optional[int] = Query(None, ge=0),
                     caller: Dict[str, Any] = Depends(scim_caller)):
    return await _answer(scim_service.list_users(get_database(), caller["tenantId"], filter, startIndex, count, _base(request)))


@router.post("/Users")
async def create_user(request: Request, caller: Dict[str, Any] = Depends(scim_caller)):
    async def go():
        return await scim_service.create_user(get_database(), caller["tenantId"], await _json(request), _actor(caller), _base(request))
    return await _answer(go(), 201)


@router.get("/Users/{user_id}")
async def get_user(user_id: str, request: Request, caller: Dict[str, Any] = Depends(scim_caller)):
    return await _answer(scim_service.get_user(get_database(), caller["tenantId"], user_id[:80], _base(request)))


@router.put("/Users/{user_id}")
async def replace_user(user_id: str, request: Request, caller: Dict[str, Any] = Depends(scim_caller)):
    async def go():
        return await scim_service.replace_user(get_database(), caller["tenantId"], user_id[:80], await _json(request),
                                               _actor(caller), _base(request))
    return await _answer(go())


@router.patch("/Users/{user_id}")
async def patch_user(user_id: str, request: Request, caller: Dict[str, Any] = Depends(scim_caller)):
    async def go():
        return await scim_service.patch_user(get_database(), caller["tenantId"], user_id[:80], await _json(request),
                                             _actor(caller), _base(request))
    return await _answer(go())


@router.delete("/Users/{user_id}")
async def delete_user(user_id: str, caller: Dict[str, Any] = Depends(scim_caller)):
    return await _answer(scim_service.delete_user(get_database(), caller["tenantId"], user_id[:80], _actor(caller)))


@router.get("/Groups")
async def list_groups(request: Request, filter: Optional[str] = Query(None, max_length=500),
                      startIndex: Optional[int] = Query(None, ge=1), count: Optional[int] = Query(None, ge=0),
                      excludedAttributes: Optional[str] = Query(None, max_length=200),
                      caller: Dict[str, Any] = Depends(scim_caller)):
    members = "members" not in (excludedAttributes or "").lower()
    return await _answer(scim_groups.list_groups(get_database(), caller["tenantId"], filter, startIndex, count,
                                                 _base(request), members))


@router.post("/Groups")
async def create_group(request: Request, caller: Dict[str, Any] = Depends(scim_caller)):
    async def go():
        return await scim_groups.create_group(get_database(), caller["tenantId"], await _json(request), _actor(caller), _base(request))
    return await _answer(go(), 201)


@router.get("/Groups/{group_id}")
async def get_group(group_id: str, request: Request, excludedAttributes: Optional[str] = Query(None, max_length=200),
                    caller: Dict[str, Any] = Depends(scim_caller)):
    members = "members" not in (excludedAttributes or "").lower()
    return await _answer(scim_groups.get_group(get_database(), caller["tenantId"], group_id[:80], _base(request), members))


@router.put("/Groups/{group_id}")
async def replace_group(group_id: str, request: Request, caller: Dict[str, Any] = Depends(scim_caller)):
    async def go():
        return await scim_groups.replace_group(get_database(), caller["tenantId"], group_id[:80], await _json(request),
                                               _actor(caller), _base(request))
    return await _answer(go())


@router.patch("/Groups/{group_id}")
async def patch_group(group_id: str, request: Request, caller: Dict[str, Any] = Depends(scim_caller)):
    async def go():
        return await scim_groups.patch_group(get_database(), caller["tenantId"], group_id[:80], await _json(request),
                                             _actor(caller), _base(request))
    return await _answer(go())


@router.delete("/Groups/{group_id}")
async def delete_group(group_id: str, caller: Dict[str, Any] = Depends(scim_caller)):
    return await _answer(scim_groups.delete_group(get_database(), caller["tenantId"], group_id[:80], _actor(caller)))
