from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import List, Dict, Any, Optional
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])

_JOBS_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}


@router.get("")
async def list_jobs(
    status: Optional[str] = None,
    limit: int = 50,
    current_user: TokenData = Depends(get_current_user),
):
    """List background jobs"""
    db = get_database()
    caller_role = getattr(current_user, "role", "")
    caller_tenant = getattr(current_user, "tenant_id", None)
    query: dict = {} if caller_role in _JOBS_SUPER_ROLES else {"tenantId": caller_tenant}
    if status and status != "all":
        query["status"] = status
    jobs = await db.jobs.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(length=limit)
    return jobs


@router.get("/{job_id}")
async def get_job(job_id: str, current_user: TokenData = Depends(get_current_user)):
    """Get specific job details"""
    db = get_database()
    caller_role = getattr(current_user, "role", "")
    caller_tenant = getattr(current_user, "tenant_id", None)
    job_filter: dict = {"id": job_id}
    if caller_role not in _JOBS_SUPER_ROLES:
        job_filter["tenantId"] = caller_tenant
    job = await db.jobs.find_one(job_filter, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("")
async def create_job(job_data: Dict[str, Any], current_user: TokenData = Depends(get_current_user)):
    username = "unknown"
    if hasattr(current_user, "username"):
        username = current_user.username
    elif isinstance(current_user, dict):
        username = current_user.get("sub") or current_user.get("username")
    tenant_id = getattr(current_user, "tenant_id", None)

    db = get_database()
    job_id = f"job-{uuid.uuid4().hex[:12]}"
    task_id = f"task-{uuid.uuid4().hex[:12]}"
    new_job = {
        "id": job_id,
        "task_id": task_id,
        "type": job_data.get("type", "generic_task"),
        "status": "pending",
        "progress": 0,
        "tenantId": tenant_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": username,
        "details": job_data.get("details", {}),
        "result": None,
    }
    await db.jobs.insert_one(new_job)
    new_job.pop("_id", None)
    return new_job


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str, current_user: TokenData = Depends(get_current_user)):
    """Cancel a pending or running job"""
    db = get_database()
    caller_role = getattr(current_user, "role", "")
    caller_tenant = getattr(current_user, "tenant_id", None)
    job_filter: dict = {"id": job_id}
    if caller_role not in _JOBS_SUPER_ROLES:
        job_filter["tenantId"] = caller_tenant
    result = await db.jobs.update_one(
        job_filter,
        {"$set": {
            "status": "cancelled",
            "cancelled_at": datetime.now(timezone.utc).isoformat(),
            "cancelled_by": getattr(current_user, "username", "unknown"),
        }}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"success": True, "message": "Job cancelled"}
