"""
Cloud Remediation API Endpoints
"""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict
from authentication_service import get_current_user
from cloud_remediation_service import cloud_remediation
from database import get_database

router = APIRouter(prefix="/api/cloud/remediation", tags=["Cloud Remediation"])


def _tenant_id(user):
    if isinstance(user, dict):
        return user.get("tenant_id") or user.get("tenantId") or None
    return getattr(user, "tenant_id", None) or None


@router.get("/capabilities")
async def get_remediation_capabilities(
    _current_user: dict = Depends(get_current_user)
) -> Dict:
    """Get available cloud remediation capabilities"""
    return cloud_remediation.get_capabilities()


@router.post("/execute/{finding_id}")
async def execute_remediation(
    finding_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict:
    """Execute auto-remediation for a security finding"""
    db = get_database()
    finding = await db.cloud_findings.find_one({"id": finding_id})

    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    user_tid = _tenant_id(current_user)
    if finding.get("tenantId") != user_tid and finding.get("tenant_id") != user_tid:
        raise HTTPException(status_code=403, detail="Access denied")

    result = await cloud_remediation.execute_remediation(finding)

    actor = getattr(current_user, "username", None) or (current_user.get("email", "") if isinstance(current_user, dict) else "")
    job = {
        "finding_id": finding_id,
        "tenant_id": user_tid,
        "user": actor,
        "action": finding.get("remediationType"),
        "cloud_provider": finding.get("cloudProvider"),
        "result": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
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

    if job.get("tenant_id") != _tenant_id(current_user):
        raise HTTPException(status_code=403, detail="Access denied")

    return job


@router.get("/history")
async def get_remediation_history(
    limit: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """Get remediation history for tenant"""
    db = get_database()
    try:
        history = await db.remediation_jobs.find(
            {"tenant_id": _tenant_id(current_user)}
        ).sort("timestamp", -1).limit(limit).to_list(length=limit)
    except Exception:
        history = []
    return history
