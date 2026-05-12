from fastapi import APIRouter, HTTPException, Query, Depends, Body
from typing import List, Dict, Any, Optional
from vuln_service import vuln_service
from datetime import datetime, timezone
import asyncio
from database import get_database

router = APIRouter(
    prefix="/api/vulnerabilities",
    tags=["Vulnerability Management"]
)

from authentication_service import get_current_user
from auth_types import TokenData
from tenant_context import get_tenant_id
from rbac_service import rbac_service

@router.get("", response_model=List[Dict[str, Any]])
async def get_vulnerabilities(current_user: TokenData = Depends(rbac_service.has_permission("view:security"))):
    """
    List all vulnerabilities.
    """
    tenant_id = get_tenant_id()
    return await vuln_service.get_vulnerabilities(tenant_id)

@router.get("/stats", response_model=Dict[str, Any])
async def get_vulnerability_stats(current_user: TokenData = Depends(rbac_service.has_permission("view:security"))):
    """
    Get vulnerability statistics.
    """
    tenant_id = get_tenant_id()
    return await vuln_service.get_vulnerability_stats(tenant_id)

@router.post("/scan")
async def schedule_scan(
    scan_type: str = Body(..., embed=True),
    assets: List[str] = Body(..., embed=True),
    tenantId: Optional[str] = Body(None, embed=True) # Optional manual tenantId
):
    """
    Schedule a vulnerability scan.
    """
    try:
        db = get_database()
        # Use tenant_id from context if available, else from body (for testing/scripts)
        try:
            tenant_id = get_tenant_id()
        except:
            tenant_id = tenantId or "default"

        job_id = f"scan-{int(datetime.now(timezone.utc).timestamp())}"
        
        job = {
            "id": job_id,
            "tenantId": tenant_id,
            "assets": assets,
            "status": "In Progress",
            "progress": 0,
            "startTime": datetime.now(timezone.utc).isoformat(),
            "type": scan_type,
            "createdAt": datetime.now(timezone.utc).isoformat()
        }
        
        await db.vulnerability_scans.insert_one(job.copy())

        # Remove _id
        if "_id" in job:
            del job["_id"]

        return job
    except Exception as e:
        print(f"Error scheduling scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{vuln_id}/apply-patch")
async def apply_patch(
    vuln_id: str,
    data: Dict[str, Any] = Body(default={}),
    current_user: TokenData = Depends(rbac_service.has_permission("manage:patches")),
):
    """Queue a patch deployment job for a specific vulnerability."""
    import uuid
    db = get_database()
    tenant_id = get_tenant_id()
    now = datetime.now(timezone.utc).isoformat()

    vuln = await db.vulnerabilities.find_one({"id": vuln_id, "tenantId": tenant_id}, {"_id": 0})
    if not vuln:
        vuln = {"id": vuln_id}

    job_id = f"patch-{uuid.uuid4().hex[:10]}"
    job = {
        "id": job_id,
        "type": "patch_deployment",
        "vuln_id": vuln_id,
        "cve_id": vuln.get("cve_id") or vuln.get("cveId") or vuln_id,
        "asset_id": data.get("asset_id") or vuln.get("assetId"),
        "tenantId": tenant_id,
        "status": "scheduled",
        "created_at": now,
        "created_by": getattr(current_user, "username", "system"),
        "scheduled_for": data.get("scheduled_for", "next_maintenance_window"),
    }
    await db.patch_jobs.insert_one(job)
    await db.vulnerabilities.update_one(
        {"id": vuln_id},
        {"$set": {"patch_status": "scheduled", "patch_job_id": job_id, "updated_at": now}},
    )
    return {"task_id": job_id, "status": "scheduled", "message": "Patch queued for next maintenance window"}


@router.post("/{vuln_id}/resolve")
async def resolve_vulnerability(
    vuln_id: str,
    data: Dict[str, Any] = Body(default={}),
    current_user: TokenData = Depends(rbac_service.has_permission("manage:security_cases")),
):
    """Mark a vulnerability as resolved."""
    db = get_database()
    tenant_id = get_tenant_id()
    now = datetime.now(timezone.utc).isoformat()

    resolution = data.get("resolution", "manually_resolved")
    result = await db.vulnerabilities.update_one(
        {"id": vuln_id, "tenantId": tenant_id},
        {"$set": {
            "status": "resolved",
            "resolution": resolution,
            "resolved_at": now,
            "resolved_by": getattr(current_user, "username", "system"),
        }},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Vulnerability not found")
    return {"success": True, "status": "resolved"}
