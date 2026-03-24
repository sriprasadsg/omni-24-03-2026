from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import List, Dict, Any, Optional
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])

@router.get("")
async def list_jobs(
    status: Optional[str] = None,
    limit: int = 50,
    current_user: TokenData = Depends(get_current_user)
):
    """List background jobs"""
    db = get_database()
    query = {}
    
    # Filter by status if provided
    if status and status != "all":
        query["status"] = status
        
    # Standard tenant isolation is handled by get_database wrapper
    # but for platform admins we might want to see all or filter by tenant_id query param
    # (Leaving simple for now)
    
    jobs = await db.jobs.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(length=limit)
    return jobs

@router.get("/{job_id}")
async def get_job(job_id: str, current_user: TokenData = Depends(get_current_user)):
    """Get specific job details"""
    db = get_database()
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    return job

@router.post("")
async def create_job(job_data: Dict[str, Any], current_user: TokenData = Depends(get_current_user)):
    # Extract username safely (handles TokenData object or dict)
    username = "unknown"
    if hasattr(current_user, "username"):
        username = current_user.username
    elif isinstance(current_user, dict):
        username = current_user.get("sub") or current_user.get("username")
    
    db = get_database()
    task_id = f"task-{uuid.uuid4().hex[:12]}"
    new_job = {
        "id": job_id,
        "task_id": task_id,
        "type": job_data.get("type", "generic_task"),
        "status": "pending",
        "progress": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": username,
        "details": job_data.get("details", {}),
        "result": None
    }
    
    await db.jobs.insert_one(new_job)
    new_job.pop("_id", None) # Remove ObjectId which is not serializable
    return new_job

@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str, current_user: TokenData = Depends(get_current_user)):
    """Cancel a pending or running job"""
    db = get_database()
    
    result = await db.jobs.update_one(
        {"id": job_id},
        {"$set": {
            "status": "cancelled",
            "cancelled_at": datetime.now(timezone.utc).isoformat(),
            "cancelled_by": current_user.username
        }}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Job not found")
        
    return {"success": True, "message": "Job cancelled"}
