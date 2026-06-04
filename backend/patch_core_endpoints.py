from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import List, Optional
import asyncio
import logging
from datetime import datetime, timezone
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/patches", tags=["Patch Management"])

_PATCH_ADMIN_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}


# ── Shared request models ─────────────────────────────────────────────────────

class PatchDeploymentRequest(BaseModel):
    patch_ids: List[str]
    asset_ids: List[str]
    deployment_type: str = "Immediate"
    schedule_time: Optional[str] = None
    tenantId: Optional[str] = None


class SoftwareUpdateRequest(BaseModel):
    agent_id: str
    package_name: str
    pkg_type: str
    tenant_id: Optional[str] = None


class OsPatchRequest(BaseModel):
    agent_id: str
    patch_ids: List[str]
    tenant_id: Optional[str] = None


class BulkSoftwareUpdateRequest(BaseModel):
    updates: List[SoftwareUpdateRequest]
    tenant_id: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_patches(
    tenant_id: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """List all patches"""
    db = get_database()
    is_admin = getattr(current_user, "role", "") in _PATCH_ADMIN_ROLES
    caller_tenant = getattr(current_user, "tenant_id", None) or None
    if not caller_tenant and not is_admin:
        raise HTTPException(status_code=403, detail="Tenant context required")
    if tenant_id and not is_admin and tenant_id != caller_tenant:
        raise HTTPException(status_code=403, detail="Not authorized to view patches for this tenant")
    effective_tenant = tenant_id if (tenant_id and is_admin) else caller_tenant
    patches = await db.patches.find({"tenantId": effective_tenant}, {"_id": 0}).to_list(length=100)
    return patches


@router.post("/deploy")
async def create_deployment_job(
    request: PatchDeploymentRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Schedule a patch deployment job."""
    try:
        from scheduler import simulate_patch_deployment
        db = get_database()

        job_id = f"job-{int(datetime.now(timezone.utc).timestamp())}"
        is_immediate = request.deployment_type != "Scheduled"
        is_admin_caller = getattr(current_user, "role", "") in _PATCH_ADMIN_ROLES
        caller_tenant = getattr(current_user, "tenant_id", None) or None
        tenant_id = (request.tenantId if is_admin_caller else None) or caller_tenant
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Tenant context required")
        now = datetime.now(timezone.utc).isoformat()

        job = {
            "id": job_id,
            "tenantId": tenant_id,
            "patchIds": request.patch_ids,
            "targetAssets": request.asset_ids,
            "status": "In Progress" if is_immediate else "Scheduled",
            "progress": 0,
            "startTime": request.schedule_time or now,
            "scheduledAt": request.schedule_time or now,
            "createdAt": now,
            "createdBy": getattr(current_user, "username", str(current_user)),
            "type": "Patch Deployment",
            "deploymentType": request.deployment_type,
        }

        await db.patch_deployment_jobs.insert_one(job.copy())
        job.pop("_id", None)

        patch_cursor = db.patches.find(
            {"$or": [
                {"id": {"$in": request.patch_ids}},
                {"_id": {"$in": request.patch_ids}},
                {"cve_id": {"$in": request.patch_ids}},
            ]},
            {"_id": 0},
        )
        fetched_patches = {doc.get("id") or doc.get("cve_id"): doc async for doc in patch_cursor}
        patch_docs = [fetched_patches.get(pid) or {"id": pid, "kb_number": pid, "name": pid} for pid in request.patch_ids]

        def _patch_identifier(doc: dict) -> str:
            return doc.get("kb_number") or doc.get("package_name") or doc.get("name") or doc.get("id", "")

        agent_cursor = db.agents.find(
            {"$or": [
                {"id": {"$in": request.asset_ids}},
                {"hostname": {"$in": request.asset_ids}},
                {"assetId": {"$in": request.asset_ids}},
            ]},
            {"id": 1, "tenantId": 1, "hostname": 1, "assetId": 1},
        )
        agent_map: dict = {}
        async for a in agent_cursor:
            for key in (a.get("id"), a.get("hostname"), a.get("assetId")):
                if key:
                    agent_map[key] = a

        instructions_queued = 0
        for asset_id in request.asset_ids:
            agent = agent_map.get(asset_id)
            if not agent:
                continue
            agent_id = agent["id"]
            patch_identifiers = [_patch_identifier(d) for d in patch_docs if _patch_identifier(d)]
            if not patch_identifiers:
                continue
            instruction_str = "Install Patches: " + " ".join(patch_identifiers) + f" Job: {job_id}"
            instr_doc: dict = {
                "agent_id":    agent_id,
                "instruction": instruction_str,
                "status":      "pending",
                "created_at":  now,
                "type":        "os_patch_install",
                "job_id":      job_id,
                "metadata":    {"patches": patch_identifiers, "job_id": job_id},
                "payload":     {},
            }
            if not is_immediate and request.schedule_time:
                instr_doc["scheduledAt"] = request.schedule_time
                instr_doc["status"] = "scheduled"
            await db.agent_instructions.insert_one(instr_doc)
            instructions_queued += 1

        job["instructionsQueued"] = instructions_queued

        if is_immediate:
            asyncio.create_task(
                simulate_patch_deployment(job_id, len(request.patch_ids), max(1, len(request.asset_ids)))
            )

        return job
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating deployment job: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/velocity")
async def get_patch_velocity(
    days: int = Query(30, ge=7, le=90),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Return daily patch deployment counts (deployed vs failed) for the last N days.
    Used to draw a remediation velocity trend chart.
    """
    from datetime import datetime, timezone, timedelta
    db = get_database()
    is_admin = getattr(current_user, "role", "") in _PATCH_ADMIN_ROLES
    caller_tenant = getattr(current_user, "tenant_id", None) or None
    if not caller_tenant and not is_admin:
        raise HTTPException(status_code=403, detail="Tenant context required")
    query: dict = {} if is_admin else {"tenantId": caller_tenant}

    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    query["$or"] = [
        {"completedAt": {"$gte": since}},
        {"createdAt": {"$gte": since}},
    ]

    jobs = await db.patch_deployment_jobs.find(
        query, {"_id": 0, "status": 1, "completedAt": 1, "createdAt": 1}
    ).to_list(length=5000)

    # Group by date string (first 10 chars of ISO timestamp)
    counts: dict = {}
    for job in jobs:
        ts = job.get("completedAt") or job.get("createdAt") or ""
        date = ts[:10]
        if not date:
            continue
        entry = counts.setdefault(date, {"date": date, "deployed": 0, "failed": 0})
        status = (job.get("status") or "").lower()
        if status in ("completed", "success", "deployed"):
            entry["deployed"] += 1
        elif status in ("failed", "error"):
            entry["failed"] += 1

    # Fill zero-value days and sort
    today = datetime.now(timezone.utc).date()
    result = []
    for i in range(days):
        d = (today - timedelta(days=days - 1 - i)).isoformat()
        result.append(counts.get(d, {"date": d, "deployed": 0, "failed": 0}))

    return result


@router.get("/deployment-jobs")
async def list_deployment_jobs(
    tenant_id: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """List patch deployment jobs"""
    db = get_database()
    is_admin = getattr(current_user, "role", "") in _PATCH_ADMIN_ROLES
    caller_tenant = getattr(current_user, "tenant_id", None) or None
    if not caller_tenant and not is_admin:
        raise HTTPException(status_code=403, detail="Tenant context required")
    if tenant_id and not is_admin and tenant_id != caller_tenant:
        raise HTTPException(status_code=403, detail="Not authorized to view jobs for this tenant")
    effective_tenant = tenant_id if (tenant_id and is_admin) else caller_tenant
    query: dict = {} if (is_admin and not tenant_id) else {"tenantId": effective_tenant}
    jobs = await db.patch_deployment_jobs.find(query, {"_id": 0}).to_list(length=100)
    return jobs
