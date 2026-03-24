"""
Threat Intelligence API Endpoints

Provides real-time threat intelligence scanning using VirusTotal integration.
Supports scanning of IPs, domains, URLs, and file hashes.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase

from database import get_database
from virustotal_client import get_virustotal_client
from rbac_utils import require_permission
from auth_types import TokenData

router = APIRouter(prefix="/api/threat-intel", tags=["Threat Intelligence"])

def _get_role(user):
    return getattr(user, 'role', None) or (user.get('role') if isinstance(user, dict) else None)

def _get_tenant(user):
    return getattr(user, 'tenant_id', None) or (user.get('tenantId') if isinstance(user, dict) else None)



# Request/Response Models
class ScanRequest(BaseModel):
    artifact: str = Field(..., description="IP, domain, URL, or file hash to scan")
    artifact_type: str = Field(..., description="Type: ip, domain, url, or hash")
    tenant_id: str = Field(..., description="Tenant ID")


class ThreatIntelScan(BaseModel):
    id: str
    tenant_id: str
    artifact: str
    artifact_type: str
    verdict: str
    detection_ratio: str
    malicious: Optional[int] = 0
    suspicious: Optional[int] = 0
    harmless: Optional[int] = 0
    undetected: Optional[int] = 0
    scan_date: str
    reputation: Optional[int] = 0
    created_at: str
    created_by: str


# Endpoints
@router.post("/scan", response_model=ThreatIntelScan)
async def scan_artifact(
    request: ScanRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: TokenData = Depends(require_permission("view:threat_intel"))
):
    """
    Scan an artifact (IP, domain, URL, or hash) using VirusTotal
    
    Returns real-time threat intelligence verdict
    """
    vt_client = get_virustotal_client()
    
    # Perform scan based on type
    if request.artifact_type == "ip":
        result = vt_client.scan_ip(request.artifact)
    elif request.artifact_type == "domain":
        result = vt_client.scan_domain(request.artifact)
    elif request.artifact_type == "url":
        result = vt_client.scan_url(request.artifact)
    elif request.artifact_type == "hash":
        result = vt_client.scan_file_hash(request.artifact)
    else:
        raise HTTPException(status_code=400, detail=f"Invalid artifact type: {request.artifact_type}")
    
    # Check for errors
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    
    scan_date = result.get("scanDate")
    if isinstance(scan_date, (int, float)):
        scan_date = datetime.fromtimestamp(scan_date, tz=timezone.utc).isoformat()
    elif not scan_date:
        scan_date = datetime.now(timezone.utc).isoformat()

    # Store scan in database
    scan_doc = {
        "tenant_id": request.tenant_id,
        "artifact": request.artifact,
        "artifact_type": request.artifact_type,
        "verdict": result.get("verdict", "Unknown"),
        "detection_ratio": result.get("detectionRatio", "0/0"),
        "malicious": result.get("malicious", 0),
        "suspicious": result.get("suspicious", 0),
        "harmless": result.get("harmless", 0),
        "undetected": result.get("undetected", 0),
        "scan_date": scan_date,
        "reputation": result.get("reputation", 0),
        "raw_result": result.get("details", {}),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user.username or "system"
    }
    
    insert_result = await db.threat_intel_scans.insert_one(scan_doc)
    scan_doc["id"] = str(insert_result.inserted_id)
    
    return ThreatIntelScan(**scan_doc)


@router.get("/feed", response_model=List[ThreatIntelScan])
async def get_threat_feed(
    tenant_id: Optional[str] = None,
    limit: int = 50,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: TokenData = Depends(require_permission("view:threat_intel"))
):
    """
    Get recent threat intelligence scans
    
    Returns feed of recent scans with verdicts
    """
    query = {}
    if tenant_id:
        query["tenant_id"] = tenant_id
    elif _get_role(current_user) != "Super Admin":
        query["tenant_id"] = _get_tenant(current_user)
    
    scans = []
    try:
        cursor = db.threat_intel_scans.find(query).sort("created_at", -1).limit(limit)
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            # Fill missing required fields with defaults
            doc.setdefault("tenant_id", query.get("tenant_id", "default"))
            doc.setdefault("artifact", "")
            doc.setdefault("artifact_type", "unknown")
            doc.setdefault("verdict", "Unknown")
            doc.setdefault("detection_ratio", "0/0")
            doc.setdefault("scan_date", doc.get("created_at", ""))
            doc.setdefault("created_at", "")
            doc.setdefault("created_by", "system")
            try:
                scans.append(ThreatIntelScan(**doc))
            except Exception:
                pass
    except Exception:
        pass
    
    return scans


@router.get("/history/{artifact}", response_model=List[ThreatIntelScan])
async def get_artifact_history(
    artifact: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: TokenData = Depends(require_permission("view:threat_intel"))
):
    """
    Get scan history for a specific artifact
    
    Returns all historical scans for the artifact
    """
    query = {"artifact": artifact}
    
    if current_user.role != "Super Admin":
        query["tenant_id"] = current_user.tenant_id
    
    cursor = db.threat_intel_scans.find(query).sort("created_at", -1)
    scans = []
    
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        scans.append(ThreatIntelScan(**doc))
    
    return scans


@router.post("/enrich-security-event")
async def enrich_security_event(
    event_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: TokenData = Depends(require_permission("manage:security"))
):
    """
    Automatically enrich a security event with threat intelligence
    
    Scans all IPs and domains in the event and adds TI context
    """
    # Get the security event
    event = await db.security_events.find_one({"_id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Security event not found")
    
    vt_client = get_virustotal_client()
    enrichments = []
    
    # Extract and scan IPs
    if "source_ip" in event:
        result = vt_client.scan_ip(event["source_ip"])
        if "error" not in result:
            enrichments.append({
                "type": "ip",
                "artifact": event["source_ip"],
                "verdict": result.get("verdict"),
                "detection_ratio": result.get("detectionRatio")
            })
    
    if "destination_ip" in event:
        result = vt_client.scan_ip(event["destination_ip"])
        if "error" not in result:
            enrichments.append({
                "type": "ip",
                "artifact": event["destination_ip"],
                "verdict": result.get("verdict"),
                "detection_ratio": result.get("detectionRatio")
            })
    
    # Extract and scan domains
    if "domain" in event:
        result = vt_client.scan_domain(event["domain"])
        if "error" not in result:
            enrichments.append({
                "type": "domain",
                "artifact": event["domain"],
                "verdict": result.get("verdict"),
                "detection_ratio": result.get("detectionRatio")
            })
    
    # Update event with enrichments
    await db.security_events.update_one(
        {"_id": event_id},
        {
            "$set": {
                "threat_intel_enrichments": enrichments,
                "enriched_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    return {
        "event_id": event_id,
        "enrichments": enrichments,
        "message": f"Added {len(enrichments)} threat intelligence enrichments"
    }


@router.get("/stats")
async def get_threat_intel_stats(
    tenant_id: Optional[str] = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: TokenData = Depends(require_permission("view:threat_intel"))
):
    """
    Get threat intelligence statistics
    
    Returns aggregated stats on scans and verdicts
    """
    query = {}
    if tenant_id:
        query["tenant_id"] = tenant_id
    elif current_user.role != "Super Admin":
        query["tenant_id"] = current_user.tenant_id
    
    # Aggregate stats
    pipeline = [
        {"$match": query},
        {
            "$group": {
                "_id": "$verdict",
                "count": {"$sum": 1}
            }
        }
    ]
    
    cursor = db.threat_intel_scans.aggregate(pipeline)
    verdict_counts = {}
    total_scans = 0
    
    async for doc in cursor:
        verdict_counts[doc["_id"]] = doc["count"]
        total_scans += doc["count"]
    
    return {
        "total_scans": total_scans,
        "verdict_breakdown": verdict_counts,
        "malicious_count": verdict_counts.get("Malicious", 0),
        "suspicious_count": verdict_counts.get("Suspicious", 0),
        "harmless_count": verdict_counts.get("Harmless", 0),
        "unknown_count": verdict_counts.get("Unknown", 0)
    }
