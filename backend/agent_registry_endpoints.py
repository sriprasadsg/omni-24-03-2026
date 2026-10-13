from fastapi import APIRouter, Depends, HTTPException, Body, BackgroundTasks, Request, Response
from catalogue_mounts_agents import AGENTS_GUARD
from typing import Dict, Any
from database import get_database
from authentication_service import get_current_user, create_access_token, SECRET_KEY, ALGORITHM, is_agent_payload
from rbac_utils import require_permission
from datetime import datetime, timezone, timedelta
import asyncio
import contextlib
import hashlib
import hmac
import secrets
import uuid
import jwt
from cache_service import invalidate_cache
from rate_limiter import limiter
import geoip_service
import agent_asn_service
import logging
from agent_location_history_service import record_location_change, get_track_agent_location

router = APIRouter(prefix="/api/agents", tags=["Agents"])
logger = logging.getLogger("agent_registry_endpoints")


def _hash_agent_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


async def _proves_agent_identity(db, existing_agent: dict, tenant_id: str, data: dict, request: Request) -> bool:
    """Whether a re-registration for an already-enrolled hostname comes from
    that agent. The tenant registration key ships in every installer, so it
    alone must never hand out a token for an existing agent id.

    Agents enrolled with a per-agent secret must present it. Agents enrolled
    before secrets existed may upgrade once by presenting a token the server
    issued to that exact agent (expiry ignored, revocation honoured).
    """
    stored = existing_agent.get("agentSecretHash")
    if stored:
        supplied = data.get("agentSecret")
        return isinstance(supplied, str) and hmac.compare_digest(_hash_agent_secret(supplied), stored)

    token = data.get("previousToken")
    if not token:
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
    if not token:
        return False
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})
    except jwt.PyJWTError:
        return False
    if not is_agent_payload(payload) or payload.get("sub") != existing_agent.get("id") or payload.get("tenant_id") != tenant_id:
        return False
    jti = payload.get("jti")
    raw = getattr(db, "_db", db)  # revoked_tokens is not tenant-scoped
    if jti and await raw.revoked_tokens.find_one({"jti": jti}, {"_id": 1}):
        return False
    return True


_ENROLLMENT_LOCK_TTL = timedelta(seconds=10)
_ENROLLMENT_LOCK_ATTEMPTS = 60
_ENROLLMENT_LOCK_RETRY_S = 0.05


@contextlib.asynccontextmanager
async def _tenant_enrollment_lock(db, tenant_id: str):
    """Serialize a tenant's seat-limit check and agent insert across requests and
    workers, so concurrent first enrollments cannot all pass the count (QA
    ISSUE-001). A lease, not a mutex: a crashed holder's lock expires after the
    TTL. Interim until an atomic seat counter replaces the count check.
    """
    locks = getattr(db, "_db", db).enrollment_locks  # platform-internal, not tenant-scoped
    key = f"enroll:{tenant_id}"
    owner = uuid.uuid4().hex
    for _ in range(_ENROLLMENT_LOCK_ATTEMPTS):
        now = datetime.now(timezone.utc)
        try:
            # Matches only an expired lease; otherwise the upsert collides on _id.
            await locks.update_one(
                {"_id": key, "lockedUntil": {"$lt": now}},
                {"$set": {"lockedUntil": now + _ENROLLMENT_LOCK_TTL, "owner": owner}},
                upsert=True,
            )
            break
        except Exception as e:
            if "E11000 duplicate key error" not in str(e):
                raise
            await asyncio.sleep(_ENROLLMENT_LOCK_RETRY_S)
    else:
        raise HTTPException(status_code=503, detail="Agent enrollment is busy for this tenant; retry")
    try:
        yield
    finally:
        await locks.delete_one({"_id": key, "owner": owner})


@router.post("/register")
@limiter.limit("10/minute")
async def register_agent(request: Request, response: Response, data: Dict[str, Any] = Body(...), background_tasks: BackgroundTasks = None):
    """
    Register a new agent or update an existing one.
    Public endpoint, requires registrationKey.
    """
    db = get_database()
    registration_key = data.get("registrationKey")

    if not registration_key:
        raise HTTPException(status_code=400, detail="Registration key required")

    tenant = await db.tenants.find_one({"registrationKey": registration_key})
    if not tenant:
        raise HTTPException(status_code=404, detail="Invalid registration key")

    from tenant_context import set_tenant_id
    set_tenant_id(tenant["id"])

    hostname = data.get("hostname")
    if not hostname:
        raise HTTPException(status_code=400, detail="Hostname required")

    agent_id = f"agent-{uuid.uuid4().hex}"
    existing_agent = await db.agents.find_one({"hostname": hostname, "tenantId": tenant["id"]})
    agent_secret = None  # issued to new agents and to legacy agents upgrading
    if existing_agent:
        if not await _proves_agent_identity(db, existing_agent, tenant["id"], data, request):
            logger.warning(
                "Rejected re-registration of enrolled agent %s (hostname %s) without proof of identity",
                existing_agent.get("id"), hostname,
            )
            raise HTTPException(
                status_code=409,
                detail="This hostname is already enrolled. Re-enrollment requires the agent's secret; "
                       "an administrator can delete the agent to enroll it again.",
            )
        agent_id = existing_agent["id"]
        if not existing_agent.get("agentSecretHash"):
            agent_secret = secrets.token_urlsafe(32)
    else:
        agent_secret = secrets.token_urlsafe(32)

    agent_limit = tenant.get("maxAgents", 5)

    agent_data = {
        "id": agent_id,
        "tenantId": tenant["id"],
        "hostname": hostname,
        "platform": data.get("platform", "Unknown"),
        "version": data.get("version", "1.0.0"),
        "ipAddress": data.get("ipAddress", "0.0.0.0"),
        "deviceId": data.get("device_id") or data.get("deviceId"),
        "status": "Online",
        "lastSeen": datetime.now(timezone.utc).isoformat(),
        "registeredAt": existing_agent.get("registeredAt") if existing_agent else datetime.now(timezone.utc).isoformat(),
        "health": {
            "overallStatus": "Healthy",
            "checks": [
                {"name": "Connectivity", "status": "Pass", "message": "Agent connected to server"},
                {"name": "Service Status", "status": "Pass", "message": "Service is running"},
                {"name": "Cache Write Access", "status": "Pass", "message": "Cache is writable"}
            ]
        }
    }

    if agent_secret:
        agent_data["agentSecretHash"] = _hash_agent_secret(agent_secret)

    reg_meta = data.get("meta", {})
    available_caps = reg_meta.get("availableCapabilities") or reg_meta.get("capabilities") or []
    if available_caps:
        agent_data["availableCapabilities"] = available_caps

    # WAN / ISP-assigned public IP, when the agent resolved it before registering.
    public_ip = data.get("publicIp") or reg_meta.get("public_ip")
    geo = None
    if public_ip:
        agent_data["publicIp"] = public_ip
        geo = geoip_service.lookup(public_ip)
        if geo:
            agent_data["geo"] = geo

    # ASN + VPN heuristic enrichment + location-history (Phase 46, GAUD-01/02).
    # Both are gated on the per-tenant track_agent_location toggle (D-02) —
    # when OFF, neither runs, but the geoip_service city/country enrichment
    # above stays unconditional (scope boundary, T-46-05-B).
    asn_enrichment = None
    track_location = False
    if public_ip:
        track_location = await get_track_agent_location(db, tenant["id"])
        if track_location:
            asn_enrichment = agent_asn_service.lookup(public_ip)
            if asn_enrichment:
                geo = {**(geo or {}), "asn": asn_enrichment.get("asn"), "vpn_heuristic": asn_enrichment.get("vpn_heuristic")}
                agent_data["geo"] = geo

    # D9: the (tenantId, hostname) compound unique index is the authoritative
    # backstop for the find_one-then-upsert registration race below — when two
    # concurrent /register calls for the same hostname both miss the check,
    # the second upsert hits E11000 and we degrade to a non-upsert update on
    # the winner's id instead of minting a duplicate agent doc.
    # A new agent takes a seat, so its limit check and insert run under the
    # tenant's enrollment lock; re-enrolling an existing agent takes no seat.
    async with (_tenant_enrollment_lock(db, tenant["id"]) if not existing_agent else contextlib.nullcontext()):
        if not existing_agent:
            current_agent_count = await db.agents.count_documents({"tenantId": tenant["id"]})
            if current_agent_count >= agent_limit:
                raise HTTPException(
                    status_code=403,
                    detail=f"Agent limit reached ({agent_limit}). Please upgrade your plan for more capacity."
                )
        try:
            await db.agents.update_one({"id": agent_id}, {"$set": agent_data}, upsert=True)
        except Exception as e:
            if "E11000 duplicate key error" in str(e):
                if not existing_agent:
                    # Lost a concurrent first-enrollment race for this hostname: the
                    # winner owns the agent record, so this caller gets no token.
                    raise HTTPException(status_code=409, detail="Concurrent enrollment for this hostname; retry")
                await db.agents.update_one({"id": agent_id}, {"$set": agent_data})
            else:
                raise e

    # Record location history (Phase 46, GAUD-01) — reuses the existing_agent
    # doc already fetched above (D-05, zero extra reads); None on first-ever
    # registration lets record_location_change's first-ever branch fire.
    if public_ip and track_location:
        try:
            await record_location_change(
                db, existing_agent, agent_id, tenant["id"], public_ip, geo, asn_enrichment
            )
        except Exception as loc_err:
            logger.warning("Failed to record location history for agent %s: %s", agent_id, loc_err)

    metrics = data.get("meta", {})
    os_info = metrics.get("os_info", {})
    asset_id = f"asset-{hostname}"
    existing_asset = await db.assets.find_one({"id": asset_id})

    asset_data = {
        "id": asset_id,
        "tenantId": tenant["id"],
        "hostname": hostname,
        "osName": data.get("platform", "Unknown"),
        "osVersion": data.get("osVersion", os_info.get("version", "Unknown")),
        "kernel": data.get("kernel", "Unknown"),
        "serialNumber": data.get("serialNumber", "Not Available"),
        "osEdition": data.get("osEdition") or (existing_asset.get("osEdition") if existing_asset else ""),
        "osDisplayVersion": data.get("osDisplayVersion") or (existing_asset.get("osDisplayVersion") if existing_asset else ""),
        "osInstalledOn": data.get("osInstalledOn") or (existing_asset.get("osInstalledOn") if existing_asset else ""),
        "osBuild": data.get("osBuild") or (existing_asset.get("osBuild") if existing_asset else ""),
        "osExperience": data.get("osExperience") or (existing_asset.get("osExperience") if existing_asset else ""),
        "ipAddress": data.get("ipAddress", "0.0.0.0"),
        "macAddress": data.get("macAddress", "00:00:00:00:00:00"),
        "lastScanned": datetime.now(timezone.utc).isoformat(),
        "cpuModel": data.get("cpuModel", "Unknown"),
        "cpuCores": data.get("cpuCores", 0),
        "ram": data.get("ram", "Unknown"),
        "totalMemoryGB": data.get("totalMemoryGB", 0),
        "disks": data.get("disks", []),
        "installedSoftware": data.get("installedSoftware", []),
        "criticalFiles": existing_asset.get("criticalFiles", []) if existing_asset else [],
        "vulnerabilities": existing_asset.get("vulnerabilities", []) if existing_asset else [],
        "status": "active",
        "type": "server"
    }
    if public_ip:
        asset_data["publicIp"] = public_ip
    if geo:
        asset_data["geo"] = geo

    try:
        await db.assets.update_one({"id": asset_id}, {"$set": asset_data}, upsert=True)
    except Exception as e:
        if "E11000 duplicate key error" in str(e):
            await db.assets.update_one({"id": asset_id}, {"$set": asset_data})
        else:
            raise e

    await db.agents.update_one({"id": agent_id}, {"$set": {"assetId": asset_id}})

    # D9: /register writes new agent state but never invalidated the agents
    # cache — matching delete/move/update which all call invalidate_cache.
    # A stale cached get_agent_instructions response can point at a pre-race
    # doc id. Invalidate so the next poll resolves fresh.
    invalidate_cache("agents:*")

    try:
        from finops_service import finops_service
        await finops_service.recalculate_tenant_costs(tenant["id"])
    except Exception as e:
        logger.warning("FinOps cost recalculation failed for tenant %s: %s", tenant["id"], e)

    try:
        from admin_evidence_service import run_evidence_collection_for_asset
        if background_tasks is not None:
            background_tasks.add_task(run_evidence_collection_for_asset, hostname, db)
        else:
            import asyncio
            asyncio.create_task(run_evidence_collection_for_asset(hostname, db))
    except Exception as e:
        logger.warning("Evidence collection dispatch failed for host %s: %s", hostname, e)

    token_data = {"sub": agent_id, "role": "agent", "typ": "agent", "tenant_id": tenant["id"], "jti": str(uuid.uuid4())}
    access_token = create_access_token(data=token_data, expires_delta=timedelta(days=90))
    result = {"success": True, "agentId": agent_id, "token": access_token}
    if agent_secret:
        # Returned once; the agent stores it and presents it to re-enroll.
        result["agentSecret"] = agent_secret
    return result


@router.put("/{agent_id}/link", dependencies=[Depends(AGENTS_GUARD)])
async def link_agent_to_asset(
    agent_id: str,
    asset_data: Dict[str, str] = Body(...),
    db=Depends(get_database),
    current_user=Depends(require_permission("manage:agents"))
):
    """Manually link an Agent to a specific Asset. Expects body: {"assetId": "asset-123"}"""
    asset_id = asset_data.get("assetId")
    if not asset_id:
        raise HTTPException(status_code=400, detail="assetId is required")

    agent_query = {"id": agent_id}
    if current_user.role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        agent_query["tenantId"] = current_user.tenant_id

    agent = await db.agents.find_one(agent_query)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    asset_query = {"id": asset_id}
    if current_user.role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        asset_query["tenantId"] = current_user.tenant_id

    asset = await db.assets.find_one(asset_query)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    await db.agents.update_one(agent_query, {"$set": {"assetId": asset_id}})
    await db.assets.update_one(
        asset_query,
        {"$set": {
            "agentStatus": agent.get("status", "Online"),
            "agentVersion": agent.get("version", "1.0.0"),
            "agentCapabilities": agent.get("capabilities", [])
        }}
    )
    return {"success": True, "message": f"Agent {agent_id} successfully linked to Asset {asset_id}"}


@router.delete("/{agent_id}", dependencies=[Depends(AGENTS_GUARD)])
async def delete_agent(
    agent_id: str,
    db=Depends(get_database),
    current_user=Depends(require_permission("manage:agents"))
):
    """Delete an agent and its linked asset. Requires Admin or Tenant Admin."""
    user_role = getattr(current_user, "role", None)
    tenant_id = getattr(current_user, "tenant_id", None)
    is_admin = user_role in ["Super Admin", "superadmin", "super_admin", "admin", "platform-admin"]

    query: dict = {"id": agent_id}
    if not is_admin:
        query["tenantId"] = tenant_id

    agent = await db.agents.find_one(query)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.get("assetId"):
        asset_del_filter: dict = {"id": agent["assetId"]}
        if not is_admin:
            asset_del_filter["tenantId"] = tenant_id
        await db.assets.delete_one(asset_del_filter)

    del_result = await db.agents.delete_one(query)
    if del_result.deleted_count == 0:
        raise HTTPException(status_code=500, detail="Failed to delete agent")

    await db.audit_logs.insert_one({
        "action": "DELETE_AGENT",
        "agent_id": agent_id,
        "performed_by": getattr(current_user, "username", str(current_user)),
        "tenant_id": getattr(current_user, "tenant_id", "unknown"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    invalidate_cache("agents:*")
    invalidate_cache("assets:*")
    return {"success": True, "message": f"Agent {agent_id} and its associated Asset successfully deleted"}


@router.put("/{agent_id}/move", dependencies=[Depends(AGENTS_GUARD)])
async def move_agent(
    agent_id: str,
    payload: Dict[str, str] = Body(...),
    current_user: Any = Depends(get_current_user)
):
    """Move an agent to a different tenant. Requires Super Admin privileges."""
    db = get_database()

    if getattr(current_user, "role", None) not in ["Super Admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Only Super Admin can move agents between tenants")

    target_tenant_id = payload.get("targetTenantId")
    if not target_tenant_id:
        raise HTTPException(status_code=400, detail="Target tenant ID required")

    target_tenant = await db.tenants.find_one({"id": target_tenant_id})
    if not target_tenant:
        raise HTTPException(status_code=404, detail="Target tenant not found")

    agent = await db.agents.find_one({"id": agent_id})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent["tenantId"] == target_tenant_id:
        return {"success": True, "message": "Agent is already in this tenant"}

    await db.agents.update_one(
        {"id": agent_id, "tenantId": agent["tenantId"]},
        {"$set": {"tenantId": target_tenant_id, "updatedAt": datetime.now(timezone.utc).isoformat()}}
    )
    if agent.get("assetId"):
        await db.assets.update_one(
            {"id": agent["assetId"], "tenantId": agent["tenantId"]},
            {"$set": {"tenantId": target_tenant_id}}
        )

    invalidate_cache("agents:*")
    invalidate_cache("assets:*")
    return {
        "success": True,
        "message": f"Agent {agent['hostname']} moved to tenant {target_tenant['name']}",
        "newTenantId": target_tenant_id
    }


@router.put("/{agent_id}", dependencies=[Depends(AGENTS_GUARD)])
async def update_agent(
    agent_id: str,
    update_data: Dict[str, Any] = Body(...),
    current_user: Any = Depends(require_permission("manage:agents"))
):
    """Update agent configuration (e.g. capabilities). Requires Admin privileges."""
    db = get_database()
    user_role = getattr(current_user, "role", None)
    tenant_id = getattr(current_user, "tenant_id", None)
    is_admin = user_role in ["Super Admin", "super_admin", "admin", "platform-admin"]

    query: dict = {"id": agent_id}
    if not is_admin:
        query["tenantId"] = tenant_id

    agent = await db.agents.find_one(query)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    def _normalise_caps(raw) -> list:
        if not isinstance(raw, list):
            return []
        return [
            c if isinstance(c, str) else c.get("id", "")
            for c in raw
            if (isinstance(c, str) and c) or (isinstance(c, dict) and c.get("id"))
        ]

    # Resolve capabilities: 'capabilities' takes precedence over 'agentCapabilities'.
    # Both are mirrors; process once to avoid the second field overwriting the first.
    set_data: Dict[str, Any] = {}
    if "capabilities" in update_data:
        cap_value = _normalise_caps(update_data["capabilities"])
        set_data["capabilities"] = cap_value
        set_data["agentCapabilities"] = cap_value
    elif "agentCapabilities" in update_data:
        cap_value = _normalise_caps(update_data["agentCapabilities"])
        set_data["capabilities"] = cap_value
        set_data["agentCapabilities"] = cap_value

    for field in ["status", "alias", "tags", "remediationAttempts"]:
        if field in update_data:
            set_data[field] = update_data[field]

    if not set_data:
        return agent

    set_data["updatedAt"] = datetime.now(timezone.utc).isoformat()
    await db.agents.update_one(query, {"$set": set_data})

    if agent.get("assetId"):
        asset_update_filter: dict = {"id": agent["assetId"]}
        if not is_admin:
            asset_update_filter["tenantId"] = tenant_id
        await db.assets.update_one(
            asset_update_filter,
            {"$set": {"agentCapabilities": set_data.get("capabilities", [])}}
        )

    invalidate_cache("agents:*")
    return await db.agents.find_one({"id": agent_id}, {"_id": 0})


@router.get("/version")
async def get_agent_version():
    """Return the current agent binary version and download URL. Polled by agent auto-update."""
    return {
        "version": "2.1.2-rust",
        "download_url": "/static/omni-agent.exe",
        "release_notes": "58 compliance checks, 175 control IDs, Collect Now runs all sources",
        "min_version": "1.0.0",
    }
