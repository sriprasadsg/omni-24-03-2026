
import os
import shutil
from pathlib import Path
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from datetime import datetime

router = APIRouter(prefix="/api/software", tags=["Software Repository"])

UPLOAD_DIR = Path("uploads/repo")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

class SoftwareFile(BaseModel):
    filename: str
    size: int
    upload_date: str
    url: str

@router.post("/upload")
async def upload_software(file: UploadFile = File(...)):
    """
    Upload a software installer to the repository.
    """
    try:
        file_path = UPLOAD_DIR / file.filename
        
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        return {
            "success": True, 
            "filename": file.filename, 
            "message": f"Successfully uploaded {file.filename}",
            "url": f"/api/software/download/{file.filename}"
        }
    except Exception as e:
        print(f"Upload error: {e}")
        return {"success": False, "error": str(e)}

@router.get("/repository")
async def list_repository_files():
    """
    List all files in the software repository.
    """
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
                    "url": f"/api/software/download/{path.name}"
                })
        return files
    except Exception as e:
        print(f"List repo error: {e}")
        return []

@router.get("/download/{filename}")
async def download_software(filename: str):
    """
    Download a file from the repository (Agent usage).
    """
    file_path = UPLOAD_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
        
    return FileResponse(path=file_path, filename=filename, media_type='application/octet-stream')

# ===== SOFTWARE DEPLOY / UNINSTALL ENDPOINT =====
from datetime import timezone
import uuid


class DeployRequest(BaseModel):
    agentIds: List[str]
    packageId: str
    action: str = "install"  # install | upgrade | uninstall | install_from_repo
    installArgs: str = None


@router.post("/deploy")
async def deploy_software(payload: DeployRequest):
    """
    Dispatch a software action (install / upgrade / uninstall / install_from_repo)
    to one or more agents via Celery tasks.

    Returns a list of task IDs the frontend can poll at
    GET /api/tasks/<task_id>
    """
    valid_actions = {"install", "upgrade", "uninstall", "install_from_repo"}
    if payload.action not in valid_actions:
        return {"success": False, "error": f"Invalid action '{payload.action}'. Must be one of: {valid_actions}"}

    if not payload.agentIds:
        return {"success": False, "error": "No agents specified."}

    if not payload.packageId:
        return {"success": False, "error": "packageId is required."}

    try:
        from app import get_database
        from datetime import datetime, timezone
        import uuid
        db = get_database()

        task_ids = []
        for agent_id in payload.agentIds:
            tenant_id = "global"
            agent = await db.agents.find_one({"id": agent_id})
            if agent:
                tenant_id = agent.get("tenantId", "global")

            instruction_type = f"{payload.action}_{payload.packageId}"
            agent_payload = {
                "package": payload.packageId,
            }

            if payload.action == "install":
                task_description = f"install_software: {payload.packageId}"
            elif payload.action == "upgrade":
                task_description = f"upgrade_software: {payload.packageId}"
            elif payload.action == "uninstall":
                task_description = f"uninstall_software: {payload.packageId}"
            elif payload.action == "install_from_repo":
                # Check for the local package
                repo_pkg = await db.local_repo.find_one({
                    "tenantId": tenant_id, "filename": payload.packageId
                })
                # If found, set download url. Ensure the type matches our agent handler 
                task_description = f"install_software: {payload.packageId}"
                if repo_pkg:
                    agent_payload["package"] = repo_pkg["pkg_name"]
                    agent_payload["pkg_type"] = repo_pkg["pkg_type"]
                    agent_payload["download_url"] = f"/api/repo/download/{repo_pkg['filename']}?tenantId={tenant_id}"
                if payload.installArgs:
                    agent_payload["install_args"] = payload.installArgs
            else:
                task_description = f"{payload.action}: {payload.packageId}"
                
            instruction = {
                "agent_id": agent_id,
                "instruction": task_description,
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "type": instruction_type,
                "payload": agent_payload
            }
            res = await db.agent_instructions.insert_one(instruction)
            task_ids.append(str(res.inserted_id))

        return {
            "success": True,
            "message": f"{payload.action.capitalize()} dispatched to {len(payload.agentIds)} agent(s).",
            "taskIds": task_ids
        }

    except Exception as e:
        print(f"[deploy_software] Error: {e}")
        return {"success": False, "error": str(e)}

import asyncio

@router.post("/updates/deploy")
async def deploy_software_updates(data: dict):
    """
    Schedule deployment of software updates across multiple assets.
    Payload: {
        "softwareUpdates": [{"name": "...", "currentVersion": "...", "latestVersion": "...", "assetId": "..."}],
        "deploymentType": "Immediate"|"Scheduled",
        "scheduleTime": "ISO datetime" (optional)
    }
    """
    try:
        from app import get_database
        
        software_updates = data.get("softwareUpdates", [])
        deployment_type = data.get("deploymentType", "Immediate")
        schedule_time = data.get("scheduleTime")
        
        if not software_updates:
            return {"success": False, "error": "softwareUpdates array is required"}
        
        db = get_database()
        job_id = f"sw-update-{uuid.uuid4().hex[:12]}"
        current_time = datetime.now(timezone.utc).isoformat()
        
        # Create deployment job
        job = {
            "id": job_id,
            "scheduledAt": schedule_time or current_time,
            "startedAt": current_time if deployment_type == "Immediate" else None,
            "completedAt": None,
            "softwareUpdates": software_updates,
            "targetAssetIds": list(set([sw["assetId"] for sw in software_updates])),
            "status": "In Progress" if deployment_type == "Immediate" else "Scheduled",
            "progress": 0,
            "statusLog": [{
                "timestamp": current_time,
                "message": f"Deployment job created ({len(software_updates)} update(s) targeting {len(set([sw['assetId'] for sw in software_updates]))} asset(s))"
            }],
            "deploymentType": deployment_type,
            "createdAt": current_time
        }
        
        await db.software_deployment_jobs.insert_one(job)
        
        # If immediate, start processing
        if deployment_type == "Immediate":
            # Queue instructions for agents
            for update in software_updates:
                asset_id = update["assetId"]
                software_name = update["name"]
                target_version = update["latestVersion"]
                
                # Find corresponding agent
                agent = await db.agents.find_one({"assetId": asset_id})
                if agent:
                    agent_id = agent["id"]
                    
                    instruction = {
                        "agent_id": agent_id,
                        "instruction": f"upgrade_software: {software_name}",
                        "status": "pending",
                        "created_at": current_time,
                        "type": f"upgrade_software: {software_name}",
                        "payload": {
                            "package": software_name,
                            "target_version": target_version
                        },
                        "deployment_job_id": job_id
                    }
                    await db.agent_instructions.insert_one(instruction)
            
            # Simulate async job processing
            asyncio.create_task(simulate_software_deployment(job_id, len(software_updates)))
        
        # Remove MongoDB _id
        if "_id" in job:
            del job["_id"]
            
        return {
            "success": True,
            "job": job,
            "message": f"Software update deployment {deployment_type.lower()} started"
        }
        
    except Exception as e:
        print(f"Error deploying software updates: {e}")
        return {"success": False, "error": str(e)}

async def simulate_software_deployment(job_id: str, update_count: int):
    """Simulate software deployment progress"""
    try:
        from app import get_database
        db = get_database()
        await asyncio.sleep(2)
        
        # Update progress incrementally
        for i in range(1, update_count + 1):
            await asyncio.sleep(3)  # Simulate deployment time per package
            
            progress = int((i / update_count) * 100)
            status_message = f"Deployed {i}/{update_count} software update(s)"
            
            await db.software_deployment_jobs.update_one(
                {"id": job_id},
                {"$set": {
                    "progress": progress,
                    "status": "In Progress"
                },
                "$push": {
                    "statusLog": {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "message": status_message
                    }
                }}
            )
        
        # Mark as completed
        await db.software_deployment_jobs.update_one(
            {"id": job_id},
            {"$set": {
                "status": "Completed",
                "progress": 100,
                "completedAt": datetime.now(timezone.utc).isoformat()
            },
            "$push": {
                "statusLog": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "message": "All software updates deployed successfully"
                }
            }}
        )
        
    except Exception as e:
        print(f"Error in deployment simulation: {e}")

@router.get("/deployment-jobs")
async def get_software_deployment_jobs():
    """Get all software deployment jobs"""
    try:
        from app import get_database
        db = get_database()
        jobs = await db.software_deployment_jobs.find({}, {"_id": 0}).sort("createdAt", -1).limit(50).to_list(length=50)
        return jobs
    except Exception as e:
        print(f"Error fetching deployment jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))
