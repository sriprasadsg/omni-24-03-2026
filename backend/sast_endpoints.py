"""
SAST API Endpoints

Provides API for static application security testing.
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

from database import get_database
from sast_service import get_sast_service
from rbac_utils import require_permission

router = APIRouter(prefix="/api/sast", tags=["SAST"])


# Request/Response Models
class TriggerScanRequest(BaseModel):
    project_name: str
    repository_url: str
    branch: str = "main"
    scan_type: str = "full"  # full, incremental, quick


class MarkFalsePositiveRequest(BaseModel):
    vulnerability_id: str
    reason: str


# Endpoints

@router.post("/scan")
async def trigger_scan(
    request: TriggerScanRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:devsecops"))
):
    """
    Trigger a SAST scan
    
    Scan types:
    - full: Complete codebase scan
    - incremental: Only changed files since last scan
    - quick: Fast scan with essential checks only
    """
    sast_service = get_sast_service(db)
    tenant_id = current_user.tenant_id

    try:
        scan = await sast_service.trigger_scan(
            project_name=request.project_name,
            repository_url=request.repository_url,
            branch=request.branch,
            scan_type=request.scan_type,
            tenant_id=tenant_id
        )
        
        return scan
    
    except Exception as e:
        logger.error("Failed to trigger scan: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/scans/{scan_id}")
async def get_scan_results(
    scan_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:devsecops"))
):
    """Get scan results by ID"""
    sast_service = get_sast_service(db)
    
    tenant_id = getattr(current_user, "tenant_id", None) or ""
    try:
        results = await sast_service.get_scan_results(scan_id, tenant_id=tenant_id)
        return results

    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        logger.error("Failed to get scan results: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/vulnerabilities")
async def list_vulnerabilities(
    scan_id: Optional[str] = None,
    severity: Optional[str] = None,
    status: str = "open",
    limit: int = 100,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:devsecops"))
):
    """
    List vulnerabilities
    
    Filter by:
    - scan_id: Specific scan
    - severity: critical, high, medium, low, info
    - status: open, fixed, false_positive
    """
    sast_service = get_sast_service(db)
    
    tenant_id = getattr(current_user, "tenant_id", None) or ""
    try:
        vulnerabilities = await sast_service.list_vulnerabilities(
            scan_id=scan_id,
            severity=severity,
            status=status,
            limit=limit,
            tenant_id=tenant_id,
        )
        
        return vulnerabilities
    
    except Exception as e:
        logger.error("Failed to list vulnerabilities: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/vulnerabilities/false-positive")
async def mark_false_positive(
    request: MarkFalsePositiveRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:devsecops"))
):
    """Mark a vulnerability as false positive"""
    sast_service = get_sast_service(db)
    user = current_user.username or "unknown"
    
    try:
        result = await sast_service.mark_false_positive(
            vulnerability_id=request.vulnerability_id,
            reason=request.reason,
            user=user
        )
        
        return result
    
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        logger.error("Failed to mark false positive: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/quality/{scan_id}")
async def get_code_quality_metrics(
    scan_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:devsecops"))
):
    """Get code quality metrics for a scan"""
    sast_service = get_sast_service(db)
    
    tenant_id = getattr(current_user, "tenant_id", None) or ""
    try:
        metrics = await sast_service.get_code_quality_metrics(scan_id, tenant_id=tenant_id)
        return metrics

    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        logger.error("Failed to get metrics: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/history")
async def get_scan_history(
    project_name: Optional[str] = None,
    limit: int = 50,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:devsecops"))
):
    """Get scan history"""
    sast_service = get_sast_service(db)
    
    tenant_id = getattr(current_user, "tenant_id", None) or ""
    try:
        history = await sast_service.get_scan_history(
            project_name=project_name,
            limit=limit,
            tenant_id=tenant_id,
        )
        
        return history
    
    except Exception as e:
        logger.error("Failed to get scan history: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/projects")
async def list_projects(
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:devsecops"))
):
    """List distinct code repositories/projects that have been scanned."""
    tenant_id = current_user.tenant_id
    try:
        # Aggregate distinct projects from scan history
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Tenant context required")
        pipeline = [
            {"$match": {"tenantId": tenant_id}},
            {"$group": {
                "_id": "$project_name",
                "repositoryUrl": {"$first": "$repository_url"},
                "lastScanned": {"$max": "$start_time"},
                "totalScans": {"$sum": 1},
                "branch": {"$first": "$branch"},
            }},
            {"$project": {
                "_id": 0,
                "name": "$_id",
                "repositoryUrl": 1,
                "lastScanned": 1,
                "totalScans": 1,
                "branch": 1,
            }},
            {"$sort": {"lastScanned": -1}},
        ]
        cursor = db.sast_scans.aggregate(pipeline)
        projects = await cursor.to_list(length=200)
        return projects
    except Exception as e:
        logger.error("Failed to list projects: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/statistics")
async def get_statistics(
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:devsecops"))
):
    """Get SAST statistics"""
    sast_service = get_sast_service(db)
    tenant_id = current_user.tenant_id
    
    try:
        stats = await sast_service.get_statistics(tenant_id)
        return stats
    
    except Exception as e:
        logger.error("Failed to get statistics: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
