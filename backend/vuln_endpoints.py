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
