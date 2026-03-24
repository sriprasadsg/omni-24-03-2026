"""
High Availability & Disaster Recovery API Endpoints

Provides API for backup management, disaster recovery, and HA monitoring.
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime

from database import get_database
from hadr_service import get_hadr_service, BackupType
from rbac_utils import require_permission

router = APIRouter(prefix="/api/hadr", tags=["HA/DR"])


# Request/Response Models
class BackupRequest(BaseModel):
    backup_type: str = BackupType.FULL
    collections: Optional[List[str]] = None
    tenant_id: Optional[str] = None


class RestoreRequest(BaseModel):
    backup_id: str
    collections: Optional[List[str]] = None
    dry_run: bool = False


class HealthCheckResponse(BaseModel):
    status: str
    database_connected: bool
    backup_system_healthy: bool
    rpo_compliant: bool
    rto_achievable: bool
    last_backup: Optional[str]
    issues: List[str] = []


# Endpoints

@router.post("/backup")
async def create_backup(
    request: BackupRequest,
    background_tasks: BackgroundTasks,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:backups"))
):
    """
    Create a database backup
    
    Backup types:
    - full: Complete backup of all data
    - incremental: Only changes since last backup
    - differential: Changes since last full backup
    """
    hadr_service = get_hadr_service(db)
    
    try:
        # Create backup in background
        background_tasks.add_task(
            hadr_service.create_backup,
            backup_type=request.backup_type,
            collections=request.collections,
            tenant_id=request.tenant_id
        )
        
        return {
            "message": "Backup initiated",
            "backup_type": request.backup_type
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initiate backup: {str(e)}")


@router.get("/backups")
async def list_backups(
    status: Optional[str] = None,
    limit: int = 50,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:backups"))
):
    """
    List all backups
    
    Filter by status: pending, in_progress, completed, failed, verified
    """
    query = {}
    if status:
        query["status"] = status
    
    cursor = db.backup_metadata.find(query).sort("started_at", -1).limit(limit)
    
    backups = []
    async for backup in cursor:
        backup["id"] = str(backup.pop("_id"))
        backups.append(backup)
    
    return backups


@router.get("/backups/{backup_id}")
async def get_backup_details(
    backup_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:backups"))
):
    """
    Get detailed backup information
    """
    backup = await db.backup_metadata.find_one({"backup_id": backup_id})
    
    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")
    
    backup["id"] = str(backup.pop("_id"))
    return backup


@router.post("/backups/{backup_id}/verify")
async def verify_backup(
    backup_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:backups"))
):
    """
    Verify backup integrity
    
    Checks:
    - File exists
    - Checksum matches
    - Data can be read
    - Encryption is valid
    """
    hadr_service = get_hadr_service(db)
    
    try:
        result = await hadr_service.verify_backup(backup_id)
        return result
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")


@router.post("/restore")
async def restore_from_backup(
    request: RestoreRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:backups"))
):
    """
    Restore from backup
    
    WARNING: This will overwrite existing data!
    Use dry_run=true to test without actually restoring.
    """
    hadr_service = get_hadr_service(db)
    
    try:
        result = await hadr_service.restore_backup(
            backup_id=request.backup_id,
            collections=request.collections,
            dry_run=request.dry_run
        )
        
        return result
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restoration failed: {str(e)}")


@router.get("/status")
async def get_backup_status(
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:backups"))
):
    """
    Get overall backup system status
    
    Returns:
    - Backup counts by status
    - Total storage used
    - Latest backup information
    - RPO compliance
    - RTO target
    """
    hadr_service = get_hadr_service(db)
    
    try:
        status = await hadr_service.get_backup_status()
        return status
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


@router.post("/test-dr")
async def test_disaster_recovery(
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:backups"))
):
    """
    Test disaster recovery procedures
    
    Validates:
    - Latest backup can be restored
    - RTO is achievable (< 15 minutes)
    - Data integrity after restore
    
    This is a dry-run test that doesn't modify production data.
    """
    hadr_service = get_hadr_service(db)
    
    try:
        result = await hadr_service.test_disaster_recovery()
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DR test failed: {str(e)}")


@router.get("/test-history")
async def get_dr_test_history(
    limit: int = 20,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:backups"))
):
    """
    Get disaster recovery test history
    """
    cursor = db.dr_test_log.find().sort("started_at", -1).limit(limit)
    
    tests = []
    async for test in cursor:
        test["id"] = str(test.pop("_id"))
        tests.append(test)
    
    return tests


@router.post("/cleanup")
async def cleanup_old_backups(
    background_tasks: BackgroundTasks,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:backups"))
):
    """
    Clean up backups older than retention period (30 days)
    """
    hadr_service = get_hadr_service(db)
    
    try:
        # Run cleanup in background
        background_tasks.add_task(hadr_service.cleanup_old_backups)
        
        return {
            "message": "Cleanup initiated",
            "retention_days": hadr_service.backup_retention_days
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")


@router.get("/health")
async def health_check(
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:system"))
):
    """
    Comprehensive health check for HA/DR system
    
    Returns:
    - Overall health status
    - Database connectivity
    - Backup system health
    - RPO compliance
    - RTO achievability
    """
    hadr_service = get_hadr_service(db)
    issues = []
    
    # Check database connection
    try:
        await db.command("ping")
        database_connected = True
    except Exception as e:
        database_connected = False
        issues.append(f"Database connection failed: {str(e)}")
    
    # Check backup system
    try:
        backup_status = await hadr_service.get_backup_status()
        backup_system_healthy = True
        rpo_compliant = backup_status["rpo_compliant"]
        last_backup = backup_status["latest_backup_time"]
        
        if not rpo_compliant:
            issues.append(f"RPO not compliant - last backup: {last_backup}")
    except Exception as e:
        backup_system_healthy = False
        rpo_compliant = False
        last_backup = None
        issues.append(f"Backup system check failed: {str(e)}")
    
    # Check RTO achievability (based on last DR test)
    try:
        latest_test = await db.dr_test_log.find_one(sort=[("started_at", -1)])
        rto_achievable = latest_test["rto_achieved"] if latest_test else False
        
        if not rto_achievable and latest_test:
            issues.append(f"RTO not achievable - last test took {latest_test['duration_minutes']} minutes")
    except Exception:
        rto_achievable = False
        issues.append("No DR test results available")
    
    # Determine overall status
    if database_connected and backup_system_healthy and rpo_compliant and rto_achievable:
        status = "healthy"
    elif database_connected and backup_system_healthy:
        status = "degraded"
    else:
        status = "critical"
    
    return {
        "status": status,
        "database_connected": database_connected,
        "backup_system_healthy": backup_system_healthy,
        "rpo_compliant": rpo_compliant,
        "rto_achievable": rto_achievable,
        "last_backup": last_backup,
        "issues": issues
    }


@router.get("/schedule")
async def get_backup_schedule(
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:backups"))
):
    """
    Get automated backup schedule
    """
    schedule = await db.backup_schedule.find_one({"_id": "default"})
    
    if not schedule:
        return {
            "message": "No schedule configured",
            "default_schedule": {
                "full_backup": "Daily at 2 AM",
                "incremental_backup": "Every hour"
            }
        }
    
    schedule["id"] = str(schedule.pop("_id"))
    return schedule


@router.post("/schedule")
async def setup_backup_schedule(
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:backups"))
):
    """
    Set up automated backup schedule
    """
    hadr_service = get_hadr_service(db)
    
    try:
        schedule = await hadr_service.schedule_backups()
        return {
            "message": "Backup schedule configured",
            "schedule": schedule
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to configure schedule: {str(e)}")


@router.get("/restoration-log")
async def get_restoration_history(
    limit: int = 20,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:backups"))
):
    """
    Get restoration history
    """
    cursor = db.restoration_log.find().sort("started_at", -1).limit(limit)
    
    restorations = []
    async for restoration in cursor:
        restoration["id"] = str(restoration.pop("_id"))
        restorations.append(restoration)
    
    return restorations
