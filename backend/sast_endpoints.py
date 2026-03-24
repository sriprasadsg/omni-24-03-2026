"""
SAST API Endpoints

Provides API for static application security testing.
"""

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

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
    tenant_id = current_user.get("tenantId")
    
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
        raise HTTPException(status_code=500, detail=f"Failed to trigger scan: {str(e)}")


@router.get("/scans/{scan_id}")
async def get_scan_results(
    scan_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:devsecops"))
):
    """Get scan results by ID"""
    sast_service = get_sast_service(db)
    
    try:
        results = await sast_service.get_scan_results(scan_id)
        return results
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get scan results: {str(e)}")


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
    
    try:
        vulnerabilities = await sast_service.list_vulnerabilities(
            scan_id=scan_id,
            severity=severity,
            status=status,
            limit=limit
        )
        
        return vulnerabilities
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list vulnerabilities: {str(e)}")


@router.post("/vulnerabilities/false-positive")
async def mark_false_positive(
    request: MarkFalsePositiveRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:devsecops"))
):
    """Mark a vulnerability as false positive"""
    sast_service = get_sast_service(db)
    user = current_user.get("email", "unknown")
    
    try:
        result = await sast_service.mark_false_positive(
            vulnerability_id=request.vulnerability_id,
            reason=request.reason,
            user=user
        )
        
        return result
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to mark false positive: {str(e)}")


@router.get("/quality/{scan_id}")
async def get_code_quality_metrics(
    scan_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:devsecops"))
):
    """Get code quality metrics for a scan"""
    sast_service = get_sast_service(db)
    
    try:
        metrics = await sast_service.get_code_quality_metrics(scan_id)
        return metrics
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")


@router.get("/history")
async def get_scan_history(
    project_name: Optional[str] = None,
    limit: int = 50,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:devsecops"))
):
    """Get scan history"""
    sast_service = get_sast_service(db)
    
    try:
        history = await sast_service.get_scan_history(
            project_name=project_name,
            limit=limit
        )
        
        return history
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get history: {str(e)}")


@router.get("/statistics")
async def get_statistics(
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:devsecops"))
):
    """Get SAST statistics"""
    sast_service = get_sast_service(db)
    tenant_id = current_user.get("tenantId")
    
    try:
        stats = await sast_service.get_statistics(tenant_id)
        return stats
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {str(e)}")
