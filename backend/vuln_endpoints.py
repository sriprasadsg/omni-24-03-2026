from fastapi import APIRouter, HTTPException, Query, Depends, Body
from typing import List, Dict, Any, Optional
from vuln_service import vuln_service
from datetime import datetime, timezone
import re
from database import get_database

_ID_RE = re.compile(r'^[a-zA-Z0-9_\-]+$')

router = APIRouter(
    prefix="/api/vulnerabilities",
    tags=["Vulnerability Management"]
)

from auth_types import TokenData
from tenant_context import get_tenant_id
from rbac_service import rbac_service

@router.get("", response_model=Dict[str, Any])
async def get_vulnerabilities(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    severity: Optional[str] = Query(None),
    current_user: TokenData = Depends(rbac_service.has_permission("view:security")),
):
    """
    List vulnerabilities with pagination.
    """
    import logging as _log
    tenant_id = get_tenant_id()
    try:
        return await vuln_service.get_vulnerabilities(tenant_id, page=page, page_size=page_size, severity=severity)
    except Exception as e:
        _log.getLogger(__name__).error("get_vulnerabilities failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/stats", response_model=Dict[str, Any])
async def get_vulnerability_stats(current_user: TokenData = Depends(rbac_service.has_permission("view:security"))):
    """
    Get vulnerability statistics.
    """
    tenant_id = get_tenant_id()
    return await vuln_service.get_vulnerability_stats(tenant_id)

@router.post("/scan")
async def schedule_scan(
    scan_type: str = Body(..., embed=True, max_length=100),
    assets: List[str] = Body(..., embed=True, max_items=500),
    current_user: TokenData = Depends(rbac_service.has_permission("view:security")),
):
    """
    Schedule a vulnerability scan.
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)
    try:
        db = get_database()
        tenant_id = getattr(current_user, "tenant_id", None) or get_tenant_id()

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

        if "_id" in job:
            del job["_id"]

        return job
    except Exception as e:
        _log.error("Error scheduling scan: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{vuln_id}/apply-patch")
async def apply_patch(
    vuln_id: str,
    data: Dict[str, Any] = Body(default={}),
    current_user: TokenData = Depends(rbac_service.has_permission("manage:patches")),
):
    """Queue a patch deployment job for a specific vulnerability."""
    if not _ID_RE.match(vuln_id):
        raise HTTPException(status_code=400, detail="Invalid vulnerability ID format")
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
        {"id": vuln_id, "tenantId": tenant_id},
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


@router.get("/{vuln_id}")
async def get_vulnerability_by_id(
    vuln_id: str,
    current_user: TokenData = Depends(rbac_service.has_permission("view:security")),
):
    """Fetch a single vulnerability record by its id field."""
    if not _ID_RE.match(vuln_id):
        raise HTTPException(status_code=400, detail="Invalid vulnerability ID")
    tenant_id = get_tenant_id()
    db = get_database()
    doc = await db.vulnerabilities.find_one({"id": vuln_id, "tenantId": tenant_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Vulnerability not found")
    return doc

