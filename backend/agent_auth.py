from fastapi import Depends, HTTPException, Header, Request
from typing import Optional, Dict, Any
from database import get_database
import logging
import jwt
from authentication_service import SECRET_KEY, ALGORITHM, is_agent_payload

logger = logging.getLogger("agent_auth")

# Path parameters through which agent routes name the agent they act for.
AGENT_PATH_PARAMS = ("agent_id", "hostname")

# Key verify_agent_key adds to the tenant it returns when the caller used an
# agent token (the registration key proves the tenant only).
CALLER_AGENT_KEY = "authenticated_agent_id"

_NEEDS_AGENT_TOKEN = "This endpoint requires the agent's own token"


def caller_agent_id(tenant: Optional[Dict[str, Any]]) -> Optional[str]:
    """The agent verify_agent_key authenticated, or None for the registration key."""
    return (tenant or {}).get(CALLER_AGENT_KEY)


async def agent_answers_to(agent_id: Optional[str], tenant_id: Optional[str], name: Optional[str], db) -> bool:
    """Whether `name` (an agent id or hostname, as agents put them in URLs and
    request bodies) names agent `agent_id` of `tenant_id`."""
    if not agent_id or not name:
        return False
    if name == agent_id:
        return True
    raw = getattr(db, "_db", db)  # may run before the tenant context is set
    return bool(await raw.agents.find_one(
        {"id": agent_id, "tenantId": tenant_id, "hostname": name}, {"_id": 1}
    ))


async def require_agent_named(agent_id: Optional[str], tenant_id: Optional[str], name: Optional[str], db) -> None:
    """403 unless the caller, authenticated as agent `agent_id`, is the agent `name`."""
    if not agent_id:
        raise HTTPException(status_code=403, detail=_NEEDS_AGENT_TOKEN)
    if not await agent_answers_to(agent_id, tenant_id, name, db):
        logger.warning("Agent %s (tenant %s) tried to act as agent %r; refused", agent_id, tenant_id, name)
        raise HTTPException(status_code=403, detail="Agent token does not belong to this agent")


async def bind_path_agent(request: Optional[Request], agent_id: Optional[str], tenant_id: Optional[str], db) -> None:
    """An agent may only act for itself: any agent the URL path names must be the caller."""
    if request is None:
        return
    for param in AGENT_PATH_PARAMS:
        name = request.path_params.get(param)
        if name is not None:
            await require_agent_named(agent_id, tenant_id, name, db)


async def verify_agent_key(
    request: Request = None,
    x_tenant_key: Optional[str] = Header(None, alias="X-Tenant-Key"),
    authorization: Optional[str] = Header(None),
    db=Depends(get_database),
) -> Dict[str, Any]:
    """Authenticate an endpoint agent; returns its tenant.

    With the agent's own token (Authorization: Bearer, issued at registration)
    the tenant carries the agent's id (caller_agent_id), and an agent named in
    the URL path must be that agent. The tenant registration key (X-Tenant-Key)
    ships in every installer and proves only the tenant, so it is refused on
    routes that act for a named agent. User sessions are not agent credentials.
    """
    from tenant_context import set_tenant_id

    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except jwt.PyJWTError:
            raise HTTPException(status_code=403, detail="Invalid Agent Token")
        if is_agent_payload(payload):
            tenant_id = payload.get("tenant_id")
            agent_id = payload.get("sub")
            if not tenant_id or not agent_id:
                raise HTTPException(status_code=403, detail="Invalid Agent Token")

            jti = payload.get("jti")
            raw = getattr(db, "_db", db)  # revoked_tokens is not tenant-scoped
            if jti and await raw.revoked_tokens.find_one({"jti": jti}, {"_id": 1}):
                raise HTTPException(status_code=403, detail="Agent token has been revoked")

            tenant = await db.tenants.find_one({"id": tenant_id})
            if not tenant:
                logger.warning("Agent token references unknown tenant_id: %s", tenant_id)
                raise HTTPException(status_code=403, detail="Invalid Agent Token")
            await bind_path_agent(request, agent_id, tenant["id"], db)
            set_tenant_id(tenant["id"])
            return {**tenant, CALLER_AGENT_KEY: agent_id}
        if not x_tenant_key:
            raise HTTPException(status_code=403, detail="Agent credentials required; user sessions are not accepted here")

    if x_tenant_key:
        tenant = await db.tenants.find_one({"registrationKey": x_tenant_key})
        if not tenant:
            raise HTTPException(status_code=403, detail="Invalid Tenant Key")
        if request is not None and any(p in request.path_params for p in AGENT_PATH_PARAMS):
            raise HTTPException(status_code=403, detail=_NEEDS_AGENT_TOKEN)
        set_tenant_id(tenant["id"])
        return tenant

    raise HTTPException(status_code=401, detail="Authentication required (X-Tenant-Key or Bearer Token)")
