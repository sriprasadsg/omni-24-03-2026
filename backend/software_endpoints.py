
import os
import shutil
import logging
from pathlib import Path
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from datetime import datetime
from authentication_service import get_current_user
from rate_limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/software", tags=["Software Repository"])

UPLOAD_DIR = Path("uploads/repo")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_SUPER_ADMIN_ROLES = {"Super Admin", "superadmin", "super_admin", "platform-admin"}

class SoftwareFile(BaseModel):
    filename: str
    size: int
    upload_date: str
    url: str


def _safe_filename(raw: str) -> str:
    """Strip directory components and reject names with unsafe characters."""
    name = os.path.basename(raw).strip()
    if not name or name.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    return name


@router.post("/upload")
@limiter.limit("20/hour")
async def upload_software(
    request: Request,
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
):
    """Upload a software installer to the repository."""
    try:
        safe_name = _safe_filename(file.filename or "")
        file_path = UPLOAD_DIR / safe_name
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {
            "success": True,
            "filename": safe_name,
            "message": f"Successfully uploaded {safe_name}",
            "url": f"/api/software/download/{safe_name}",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Upload error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/repository")
async def list_repository_files(current_user=Depends(get_current_user)):
    """List all files in the software repository."""
    files = []
    try:
        if not UPLOAD_DIR.exists():
            return []
        for path in UPLOAD_DIR.iterdir():
            if path.is_file():
                stat = path.stat()
                files.append({
                    "filename": path.name,
                    "size": stat.st_size,
                    "upload_date": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "url": f"/api/software/download/{path.name}",
                })
        return files
    except Exception as e:
        logger.error("List repo error: %s", e)
        return []


@router.get("/download/{filename}")
async def download_software(filename: str, current_user=Depends(get_current_user)):
    """Download a file from the repository."""
    safe_name = _safe_filename(filename)
    file_path = UPLOAD_DIR / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=file_path, filename=safe_name, media_type="application/octet-stream")


# ===== SOFTWARE DEPLOY / UNINSTALL ENDPOINT =====
from datetime import timezone
import uuid
import asyncio


class DeployRequest(BaseModel):
    agentIds: List[str] = Field(..., max_items=500)
    packageId: str = Field(..., max_length=255)
    action: str = Field("install", max_length=50)
    installArgs: str = Field(None, max_length=500)


@router.post("/deploy")
async def deploy_software(
    payload: DeployRequest,
    current_user=Depends(get_current_user),
):
    """Dispatch a software action to one or more agents."""
    valid_actions = {"install", "upgrade", "uninstall", "install_from_repo"}
    if payload.action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Invalid action. Must be one of: {sorted(valid_actions)}")

    if not payload.agentIds:
        raise HTTPException(status_code=400, detail="No agents specified")

    try:
        from app import get_database
        db = get_database()
        caller_tenant = getattr(current_user, "tenant_id", None)
        is_super_admin = getattr(current_user, "role", "") in _SUPER_ADMIN_ROLES

        task_ids = []
        for agent_id in payload.agentIds[:100]:
            _agent_q: dict = {"id": agent_id}
            if not is_super_admin and caller_tenant:
                _agent_q["tenantId"] = caller_tenant
            agent = await db.agents.find_one(_agent_q)
            if not agent:
                continue
            tenant_id = agent.get("tenantId") or None
            if not tenant_id:
                continue

            instruction_type = f"{payload.action}_{payload.packageId}"
            agent_payload: dict = {"package": payload.packageId}

            if payload.action == "install":
                task_description = f"install_software: {payload.packageId}"
            elif payload.action == "upgrade":
                task_description = f"upgrade_software: {payload.packageId}"
            elif payload.action == "uninstall":
                task_description = f"uninstall_software: {payload.packageId}"
            elif payload.action == "install_from_repo":
                task_description = f"install_software: {payload.packageId}"
                repo_pkg = await db.local_repo.find_one(
                    {"tenantId": tenant_id, "filename": payload.packageId}
                ) or await db.local_repo.find_one(
                    {"tenantId": "global", "filename": payload.packageId}
                )
                if repo_pkg:
                    effective_tid = repo_pkg.get("tenantId", tenant_id)
                    agent_payload["package"] = repo_pkg["pkg_name"]
                    agent_payload["pkg_type"] = repo_pkg["pkg_type"]
                    agent_payload["download_url"] = f"/api/repo/download/{repo_pkg['filename']}?tenantId={effective_tid}"
                else:
                    disk_path = UPLOAD_DIR / _safe_filename(payload.packageId)
                    if disk_path.exists():
                        agent_payload["download_url"] = f"/api/software/download/{payload.packageId}"
                if payload.installArgs:
                    agent_payload["install_args"] = payload.installArgs
            else:
                task_description = f"{payload.action}: {payload.packageId}"

            task_id = str(uuid.uuid4().hex)
            instruction = {
                "id": task_id,
                "agent_id": agent_id,
                "tenantId": tenant_id,
                "instruction": task_description,
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "type": instruction_type,
                "payload": agent_payload,
            }
            await db.agent_instructions.insert_one(instruction)
            task_ids.append(task_id)

        return {
            "success": True,
            "message": f"{payload.action.capitalize()} dispatched to {len(task_ids)} agent(s).",
            "taskIds": task_ids,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("deploy_software error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/updates/deploy")
async def deploy_software_updates(
    data: dict,
    current_user=Depends(get_current_user),
):
    """Schedule deployment of software updates across multiple assets."""
    try:
        from app import get_database
        from tenant_context import set_tenant_id, get_tenant_id

        software_updates = data.get("softwareUpdates", [])
        deployment_type = data.get("deploymentType", "Immediate")
        schedule_time = data.get("scheduleTime")

        if not software_updates:
            raise HTTPException(status_code=400, detail="softwareUpdates array is required")

        db = get_database()
        old_tenant_id = get_tenant_id()

        set_tenant_id("platform-admin")
        try:
            tenant_id = old_tenant_id
            if not tenant_id or tenant_id == "platform-admin":
                if software_updates:
                    first_asset_id = software_updates[0].get("assetId")
                    if first_asset_id:
                        asset = await db.assets.find_one({"id": first_asset_id})
                        tenant_id = asset.get("tenantId") if asset else None
            effective_tenant_id = tenant_id if tenant_id else "global"
        finally:
            set_tenant_id(old_tenant_id)

        if effective_tenant_id and effective_tenant_id != "global":
            set_tenant_id(effective_tenant_id)

        try:
            job_id = f"sw-update-{uuid.uuid4().hex[:12]}"
            current_time = datetime.now(timezone.utc).isoformat()

            job = {
                "id": job_id,
                "tenantId": effective_tenant_id,
                "scheduledAt": schedule_time or current_time,
                "startedAt": current_time if deployment_type == "Immediate" else None,
                "completedAt": None,
                "softwareUpdates": software_updates,
                "targetAssetIds": list(set([sw["assetId"] for sw in software_updates])),
                "status": "In Progress" if deployment_type == "Immediate" else "Scheduled",
                "progress": 0,
                "statusLog": [{
                    "timestamp": current_time,
                    "message": f"Deployment job created ({len(software_updates)} update(s) targeting {len(set([sw['assetId'] for sw in software_updates]))} asset(s))",
                }],
                "deploymentType": deployment_type,
                "createdAt": current_time,
            }

            await db.software_deployment_jobs.insert_one(job)

            if deployment_type == "Immediate":
                for update in software_updates:
                    asset_id = update["assetId"]
                    software_name = update["name"]
                    target_version = update["latestVersion"]
                    agent = await db.agents.find_one({"assetId": asset_id})
                    if agent:
                        instruction = {
                            "agent_id": agent["id"],
                            "tenantId": effective_tenant_id,
                            "instruction": f"upgrade_software: {software_name}",
                            "status": "pending",
                            "created_at": current_time,
                            "type": f"upgrade_software: {software_name}",
                            "payload": {"package": software_name, "target_version": target_version},
                            "deployment_job_id": job_id,
                        }
                        await db.agent_instructions.insert_one(instruction)

                instructions_queued = 0
                for u in software_updates:
                    if await db.agents.find_one({"assetId": u["assetId"]}):
                        instructions_queued += 1

                await db.software_deployment_jobs.update_one(
                    {"id": job_id}, {"$set": {"instructionsQueued": instructions_queued}}
                )
                asyncio.create_task(simulate_software_deployment(job_id, len(software_updates)))

            if "_id" in job:
                del job["_id"]

            return {
                "success": True,
                "job": job,
                "message": f"Software update deployment {deployment_type.lower()} started",
            }
        finally:
            set_tenant_id(old_tenant_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("deploy_software_updates error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


async def simulate_software_deployment(job_id: str, update_count: int):
    """Animate deployment progress while real agents execute updates."""
    try:
        db = get_database()
        job = await db.software_deployment_jobs.find_one({"id": job_id}, {"instructionsQueued": 1})
        has_real_agents = job and job.get("instructionsQueued", 0) > 0
        total = max(update_count, 1)

        for i in range(1, total + 1):
            await asyncio.sleep(2)
            current = await db.software_deployment_jobs.find_one({"id": job_id}, {"status": 1})
            if current and current.get("status") in ("Completed", "Failed", "Partially Completed"):
                return
            progress = int((i / total) * 99)
            await db.software_deployment_jobs.update_one(
                {"id": job_id},
                {
                    "$set": {"progress": progress},
                    "$push": {"statusLog": {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "message": f"Waiting for agent: update {i}/{total}",
                        "level": "info",
                    }},
                },
            )

        if not has_real_agents:
            await db.software_deployment_jobs.update_one(
                {"id": job_id},
                {
                    "$set": {
                        "status": "Completed",
                        "progress": 100,
                        "completedAt": datetime.now(timezone.utc).isoformat(),
                    },
                    "$push": {"statusLog": {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "message": f"[Demo] {total} software updates complete (no agents registered)",
                        "level": "warn",
                    }},
                },
            )
    except Exception as e:
        logger.error("simulate_software_deployment error: %s", e)


def _get_database():
    from app import get_database as _gd
    return _gd()


@router.get("/deployment-jobs")
async def get_software_deployment_jobs(current_user=Depends(get_current_user)):
    """Get software deployment jobs scoped to the caller's tenant."""
    try:
        db = _get_database()
        role = getattr(current_user, "role", "")
        query: dict = {}
        if role not in _SUPER_ADMIN_ROLES:
            tid = getattr(current_user, "tenant_id", None)
            query["tenantId"] = tid
        jobs = await db.software_deployment_jobs.find(query, {"_id": 0}).sort("createdAt", -1).limit(50).to_list(length=50)
        return jobs
    except Exception as e:
        logger.error("Error fetching deployment jobs: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/tasks")
async def get_software_tasks(current_user=Depends(get_current_user)):
    """Return recent software deployment tasks scoped to the caller's tenant."""
    try:
        db = _get_database()
        role = getattr(current_user, "role", "")
        base_filter: dict = {
            "instruction": {"$regex": "install_software|upgrade_software|uninstall_software", "$options": "i"}
        }
        if role not in _SUPER_ADMIN_ROLES:
            tid = getattr(current_user, "tenant_id", None)
            base_filter["tenantId"] = tid

        instrs = await db.agent_instructions.find(
            base_filter, {"_id": 0}
        ).sort("created_at", -1).limit(100).to_list(length=100)

        agent_ids = list({i.get("agent_id") for i in instrs if i.get("agent_id")})
        agents_map: dict = {}
        if agent_ids:
            agent_lookup: dict = {"id": {"$in": agent_ids}}
            if role not in _SUPER_ADMIN_ROLES:
                agent_lookup["tenantId"] = getattr(current_user, "tenant_id", None)
            async for agent in db.agents.find(agent_lookup, {"_id": 0, "id": 1, "hostname": 1}):
                agents_map[agent["id"]] = agent.get("hostname", agent["id"])

        for instr in instrs:
            instr["hostname"] = agents_map.get(instr.get("agent_id"), instr.get("agent_id", "Unknown"))

        return instrs
    except Exception as e:
        logger.error("Error fetching software tasks: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
