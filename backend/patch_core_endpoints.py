from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import List, Optional
import logging
import re
import uuid
from datetime import datetime, timezone
from database import get_database
from authentication_service import get_current_user
from rbac_utils import require_permission
from auth_types import TokenData
from auth_roles import platform_scope_roles

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/patches", tags=["Patch Management"])

_PATCH_ADMIN_ROLES = platform_scope_roles()


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
    query: dict = {} if (is_admin and not tenant_id) else {"tenantId": effective_tenant}
    patches = await db.patches.find(query, {"_id": 0}).to_list(length=100)
    return patches


_KB_RE = re.compile(r"^KB\d{4,8}$", re.IGNORECASE)
# Advisory ids (CVE-…) and KB-shaped ids of the wrong length are never treated as package names.
_NOT_PKG_RE = re.compile(r"^(CVE-\d{4}-\d+|KB\d+)$", re.IGNORECASE)
# Debian/RPM package names, optionally with an apt ":arch" suffix. No spaces, quotes,
# shell metacharacters or a leading "-", so an id can never become an option or a command.
_PKG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_:-]{0,127}$")


def installable_patch_id(value) -> Optional[str]:
    """The id an agent can actually install: a Windows KB number (normalised to
    "KB1234567") or a Linux package name. CVE ids are advisories, not installable
    updates, so they are rejected along with anything that is not a plain name."""
    if not isinstance(value, str):
        return None
    v = value.strip()
    if _KB_RE.match(v):
        return v.upper()
    if _NOT_PKG_RE.match(v) or not _PKG_RE.match(v):
        return None
    return v


def pending_entry_id(entry) -> Optional[str]:
    """The installable id of one reported pending update: a plain id string (Python
    agent os_patches.items) or an {id|kb|package, title, ...} object (system_patching)."""
    if isinstance(entry, dict):
        kb = str(entry.get("kb") or "").strip()
        entry = entry.get("id") or (f"KB{kb}" if kb.isdigit() else None) or entry.get("package")
    return installable_patch_id(entry)


def new_patch_job(job_id: str, tenant_id: str, patch_ids: List[str], target_assets: List[str],
                  agent_ids: List[str], created_by: str, deployment_type: str,
                  scheduled_at: Optional[str], now: str, status: str) -> dict:
    """A patch_deployment_jobs document. Progress and the final status come only from
    agent reports (deployment_result_endpoints.record_agent_patch_result)."""
    return {
        "id": job_id,
        "tenantId": tenant_id,
        "patchIds": patch_ids,
        "targetAssets": target_assets,
        "dispatchedAgents": agent_ids,
        "agentResults": {},
        "instructionsQueued": len(agent_ids),
        "status": status,
        "progress": 0,
        "startTime": scheduled_at or now,
        "scheduledAt": scheduled_at or now,
        "createdAt": now,
        "createdBy": created_by,
        "type": "Patch Deployment",
        "deploymentType": deployment_type,
        "statusLog": [{
            "timestamp": now,
            "message": (f"Queued {len(patch_ids)} patch(es) for {len(agent_ids)} agent(s)"
                        + (f", starting {scheduled_at}" if status == "Scheduled" else "")),
            "level": "info",
        }],
    }


def patch_instruction(job_id: str, agent: dict, patch_ids: List[str], now: str,
                      scheduled_at: Optional[str] = None, rollback: bool = False) -> dict:
    """The agent_instructions document that tells one agent to install (or roll back)
    patches. It is filed under the agent's own tenant, which its poll is scoped to."""
    doc = {
        "id":          uuid.uuid4().hex,
        "agent_id":    agent["id"],
        "tenantId":    agent.get("tenantId"),
        "instruction": "rollback_patches" if rollback else "install_patches",
        "payload":     {"patch_ids": patch_ids, "job_id": job_id},
        "status":      "pending",
        "created_at":  now,
        "type":        "os_patch_rollback" if rollback else "os_patch_install",
        "job_id":      job_id,
        "metadata":    {"patches": patch_ids, "job_id": job_id},
    }
    if scheduled_at:
        doc["scheduledAt"] = scheduled_at
        doc["status"] = "scheduled"
    return doc


@router.post("/deploy")
async def create_deployment_job(
    request: PatchDeploymentRequest,
    current_user: TokenData = Depends(require_permission("manage:patches")),
):
    """Queue a patch deployment on the agents behind the selected assets.

    Only Windows KB numbers and Linux package names are sent to agents. A request
    that resolves to nothing installable, or to no registered agent, is refused
    instead of producing a job that can never run."""
    try:
        db = get_database()

        is_immediate = request.deployment_type != "Scheduled"
        if not is_immediate and not request.schedule_time:
            raise HTTPException(status_code=400, detail="A scheduled deployment needs schedule_time")
        is_admin_caller = getattr(current_user, "role", "") in _PATCH_ADMIN_ROLES
        caller_tenant = getattr(current_user, "tenant_id", None) or None
        if not caller_tenant and not is_admin_caller:
            raise HTTPException(status_code=403, detail="Tenant context required")
        now = datetime.now(timezone.utc).isoformat()

        patch_cursor = db.patches.find(
            {"$or": [
                {"id": {"$in": request.patch_ids}},
                {"_id": {"$in": request.patch_ids}},
                {"cve_id": {"$in": request.patch_ids}},
            ]},
            {"_id": 0},
        )
        fetched_patches = {doc.get("id") or doc.get("cve_id"): doc async for doc in patch_cursor}
        patch_identifiers: List[str] = []
        not_installable: List[str] = []
        for pid in request.patch_ids:
            doc = fetched_patches.get(pid)
            candidates = [doc.get("kb_number"), doc.get("package_name")] if doc else [pid]
            ident = next((i for i in map(installable_patch_id, candidates) if i), None)
            if ident and ident not in patch_identifiers:
                patch_identifiers.append(ident)
            elif not ident:
                not_installable.append(pid)
        if not patch_identifiers:
            raise HTTPException(status_code=400, detail=(
                "None of the selected patches is an installable Windows KB or Linux package "
                f"(CVE records have no KB/package mapped yet): {', '.join(not_installable[:10])}"))

        hostnames = [a[len("asset-"):] for a in request.asset_ids if a.startswith("asset-")]
        agent_query: dict = {"$or": [
            {"id": {"$in": request.asset_ids}},
            {"hostname": {"$in": request.asset_ids + hostnames}},
            {"assetId": {"$in": request.asset_ids}},
        ]}
        if not is_admin_caller:
            agent_query["tenantId"] = caller_tenant
        agents: dict = {}
        async for a in db.agents.find(agent_query, {"id": 1, "tenantId": 1, "hostname": 1, "assetId": 1, "status": 1}):
            # An uninstalled agent never polls again, so its instruction would wait forever.
            if a.get("id") and str(a.get("status", "")).lower() != "uninstalled":
                agents[a["id"]] = a
        if not agents:
            raise HTTPException(status_code=400, detail="None of the selected assets has an installed, registered agent")

        # Agents only see (and report on) jobs of their own tenant, so a job never spans tenants.
        agent_tenants = {a.get("tenantId") for a in agents.values()}
        if len(agent_tenants) > 1:
            raise HTTPException(status_code=400, detail="Select assets from one tenant per patch deployment")
        tenant_id = agent_tenants.pop()
        if not tenant_id:
            raise HTTPException(status_code=409, detail="The selected agent has no tenant")

        job_id = f"job-{int(datetime.now(timezone.utc).timestamp())}-{uuid.uuid4().hex[:6]}"
        scheduled_at = None if is_immediate else request.schedule_time
        job = new_patch_job(
            job_id, tenant_id, patch_identifiers, request.asset_ids, list(agents),
            getattr(current_user, "username", str(current_user)), request.deployment_type,
            scheduled_at, now, "In Progress" if is_immediate else "Scheduled",
        )
        if not_installable:
            job["skippedPatchIds"] = not_installable
            job["statusLog"].append({
                "timestamp": now, "level": "warn",
                "message": f"Skipped {len(not_installable)} patch(es) with no KB/package: {', '.join(not_installable[:10])}",
            })
        await db.patch_deployment_jobs.insert_one(job.copy())
        job.pop("_id", None)

        # Insert in chunks of 1 000 to stay under MongoDB's 16 MiB batch limit at scale.
        instr_docs = [patch_instruction(job_id, a, patch_identifiers, now, scheduled_at) for a in agents.values()]
        _CHUNK = 1_000
        for i in range(0, len(instr_docs), _CHUNK):
            await db.agent_instructions.insert_many(instr_docs[i : i + _CHUNK], ordered=False)

        return {"success": True, "job_id": job_id, "job": job}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating deployment job: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/deployment-jobs/{job_id}/rollback")
async def rollback_patch_job(
    job_id: str,
    current_user: TokenData = Depends(require_permission("manage:patches")),
):
    """Roll back a finished patch job: each agent uninstalls (Windows) or downgrades
    (Linux) exactly the patches it reported as installed. Runs as a new job."""
    db = get_database()
    is_admin = getattr(current_user, "role", "") in _PATCH_ADMIN_ROLES
    caller_tenant = getattr(current_user, "tenant_id", None) or None
    job = await db.patch_deployment_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job or (not is_admin and job.get("tenantId") != caller_tenant):
        raise HTTPException(status_code=404, detail="Patch deployment job not found")
    if job.get("status") not in ("Completed", "Partially Completed", "Failed"):
        raise HTTPException(status_code=409, detail="Only a finished patch job can be rolled back")

    installed: dict = {}
    for agent_id in job.get("dispatchedAgents") or []:
        res = (job.get("agentResults") or {}).get(agent_id.replace(".", "_").replace("$", "_")) or {}
        ids = [r.get("patch_id") for r in res.get("results", [])
               if isinstance(r, dict) and r.get("status") == "success" and installable_patch_id(r.get("patch_id"))]
        if ids:
            installed[agent_id] = ids
    if not installed:
        raise HTTPException(status_code=400, detail="This job installed nothing, so there is nothing to roll back")

    agents = {a["id"]: a async for a in db.agents.find({"id": {"$in": list(installed)}},
                                                       {"id": 1, "tenantId": 1, "status": 1})}
    agents = {k: a for k, a in agents.items() if str(a.get("status", "")).lower() != "uninstalled"}
    if not agents:
        raise HTTPException(status_code=409, detail="None of the job's agents is still installed")

    now = datetime.now(timezone.utc).isoformat()
    rb_id = f"rollback-{int(datetime.now(timezone.utc).timestamp())}-{uuid.uuid4().hex[:6]}"
    all_ids = sorted({p for a in agents for p in installed[a]})
    rb_job = new_patch_job(rb_id, job.get("tenantId"), all_ids, job.get("targetAssets") or [], list(agents),
                           getattr(current_user, "username", "unknown"), "Immediate", None, now, "In Progress")
    rb_job.update({"type": "Patch Rollback", "rollbackOf": job_id})
    await db.patch_deployment_jobs.insert_one(rb_job.copy())
    rb_job.pop("_id", None)
    await db.agent_instructions.insert_many(
        [patch_instruction(rb_id, a, installed[a["id"]], now, rollback=True) for a in agents.values()],
        ordered=False)
    await db.patch_deployment_jobs.update_one({"id": job_id}, {"$push": {"statusLog": {
        "timestamp": now, "level": "warn", "message": f"Rollback started as {rb_id}"}}})
    return {"success": True, "job_id": rb_id, "job": rb_job}


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
