"""
Cloud Remediation API Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict
from authentication_service import get_current_user
from cloud_remediation_service import cloud_remediation
from database import get_database

router = APIRouter(prefix="/api/cloud/remediation", tags=["Cloud Remediation"])

@router.get("/capabilities")
async def get_remediation_capabilities(
    current_user: dict = Depends(get_current_user)
) -> Dict:
    """Get available cloud remediation capabilities"""
    return cloud_remediation.get_capabilities()

@router.post("/execute/{finding_id}")
async def execute_remediation(
    finding_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict:
    """Execute auto-remediation for a security finding"""
    # Get finding from database
    db = get_database()
    finding = await db.cloud_findings.find_one({"id": finding_id})
    
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    
    # Check tenant ownership
    user_tid = current_user.get("tenant_id") or current_user.get("tenantId", "")
    if finding.get("tenantId") != user_tid and finding.get("tenant_id") != user_tid:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Execute remediation
    result = await cloud_remediation.execute_remediation(finding)
    
    # Log remediation job
    user_tid = current_user.get("tenant_id") or current_user.get("tenantId", "")
    job = {
        "finding_id": finding_id,
        "tenant_id": user_tid,
        "user": current_user.get("email", ""),
        "action": finding.get("remediationType"),
        "cloud_provider": finding.get("cloudProvider"),
        "result": result,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    await db.remediation_jobs.insert_one(job)
    
    return result

@router.get("/status/{job_id}")
async def get_remediation_status(
    job_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict:
    """Get status of a remediation job"""
    db = get_database()
    job = await db.remediation_jobs.find_one({"_id": job_id})
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    user_tid = current_user.get("tenant_id") or current_user.get("tenantId", "")
    if job.get("tenant_id") != user_tid:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return job

@router.get("/history")
async def get_remediation_history(
    limit: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """Get remediation history for tenant"""
    db = get_database()
    user_tid = current_user.get("tenant_id") or current_user.get("tenantId", "")
    try:
        history = await db.remediation_jobs.find({
            "tenant_id": user_tid
        }).sort("timestamp", -1).limit(limit).to_list(length=limit)
    except Exception:
        history = []
    return history

# Import for timestamp
from datetime import datetime
