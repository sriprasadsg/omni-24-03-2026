from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from typing import Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorDatabase
from database import get_database
from etl_service import get_etl_service
from rbac_utils import require_permission

router = APIRouter(prefix="/api/etl", tags=["Extract Transform Load"])

@router.post("/run")
async def run_etl_job(
    background_tasks: BackgroundTasks,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:system"))
):
    """
    Trigger an ETL job manually.
    """
    service = get_etl_service(db)
    tenant_id = current_user.tenant_id
    
    # Run in background to avoid timeout
    async def _run_job():
        await service.run_pipeline(tenant_id, job_id=f"manual-{tenant_id}")
    
    background_tasks.add_task(_run_job)
    
    return {"message": "ETL job initiated successfully."}

@router.get("/history")
async def get_etl_history(
    limit: int = 20,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:system"))
):
    """
    Get history of ETL jobs.
    """
    tenant_id = current_user.tenant_id
    cursor = db.etl_jobs.find({"tenant_id": tenant_id}).sort("start_time", -1).limit(limit)
    
    jobs = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        jobs.append(doc)
        
    return jobs
