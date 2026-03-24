from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
import random
import uuid

router = APIRouter(prefix="/api/dast", tags=["Dynamic Application Security Testing"])

# --- Models ---
class ScanTarget(BaseModel):
    url: str
    authType: Optional[str] = "None"

class DastFinding(BaseModel):
    id: str
    scanId: str
    title: str
    severity: str # Critical, High, Medium, Low
    description: str
    remediation: str
    url: str

class DastScan(BaseModel):
    id: str
    targetUrl: str
    status: str # Scheduled, Running, Completed, Failed
    riskScore: int
    startTime: str
    endTime: Optional[str]
    findingsCount: int
    findings: List[DastFinding] = []


# --- Database-backed DAST Scans ---
# No mock data - all scans stored in MongoDB

# --- Endpoints ---

@router.get("/scans", response_model=List[DastScan])
async def get_scans():
    """List all DAST scans from database."""
    from database import get_database
    db = get_database()
    scans = await db.dast_scans.find({}, {"_id": 0}).to_list(length=100)
    return [DastScan(**scan) for scan in scans] if scans else []

@router.post("/scans", response_model=DastScan)
async def start_scan(target: ScanTarget):
    """Start a new DAST scan and store in database."""
    from database import get_database
    db = get_database()
    
    new_scan = DastScan(
        id=f"scan-{uuid.uuid4().hex[:8]}",
        targetUrl=target.url,
        status="Running",
        riskScore=0,
        startTime=datetime.now().isoformat(),
        endTime=None,
        findingsCount=0,
        findings=[]
    )
    
    await db.dast_scans.insert_one(new_scan.dict())
    return new_scan

@router.get("/scans/{scan_id}", response_model=DastScan)
async def get_scan_details(scan_id: str):
    """Get details for a specific scan from database."""
    from database import get_database
    db = get_database()
    
    scan = await db.dast_scans.find_one({"id": scan_id}, {"_id": 0})
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return DastScan(**scan)

@router.get("/findings", response_model=List[DastFinding])
async def get_all_findings():
    """Get aggregated list of all findings from database."""
    from database import get_database
    db = get_database()
    
    scans = await db.dast_scans.find({}, {"_id": 0}).to_list(length=100)
    all_findings = []
    for scan in scans:
        all_findings.extend([DastFinding(**f) for f in scan.get("findings", [])])
    return all_findings
