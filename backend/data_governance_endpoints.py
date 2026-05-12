from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List
from datetime import datetime, timezone
from data_quality_service import quality_service
from data_governance_service import governance_service
from pii_service import PIIService
from rbac_utils import require_permission

router = APIRouter(prefix="/api", tags=["Data Governance & Quality"])

# --- Governance Endpoints ---

@router.post("/governance/scan")
async def scan_data(
    data: Dict[str, Any],
    current_user: dict = Depends(require_permission("view:system"))
):
    """On-demand scan of a data record for PII and classification using expanded PIIService."""
    text = str(data)
    result = PIIService.scan(text)

    return {
        "pii_detected": result["pii_types_found"],
        "classification": result["overall_classification"].upper(),
        "detection_count": result["detection_count"],
        "detections": result["detections"],
        "max_severity": result["max_severity"],
        "redacted_preview": result["redacted_text"][:500],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/governance/pii-patterns")
async def get_pii_patterns(current_user: dict = Depends(require_permission("view:reporting"))):
    """Return catalog of all PII detection pattern types."""
    return {"patterns": PIIService.get_pattern_catalog(), "total": len(PIIService.get_pattern_catalog())}

@router.get("/governance/catalog")
async def get_catalog(
    current_user: dict = Depends(require_permission("view:reporting"))
):
    """
    Get the Data Governance Catalog.
    """
    return governance_service.get_data_catalog()

# --- Quality Endpoints ---

@router.get("/quality/report")
async def get_quality_report(
    current_user: dict = Depends(require_permission("view:reporting"))
):
    """Get a data quality report based on real record counts from the database."""
    from database import get_database
    db = get_database()

    # Count real records across key collections
    asset_count = await db.assets.count_documents({})
    agent_count = await db.agents.count_documents({})
    event_count = await db.security_events.count_documents({})
    alert_count = await db.alerts.count_documents({})
    total_records = asset_count + agent_count + event_count + alert_count

    # Sample assets for quality scoring (up to 50)
    sample_docs = await db.assets.find({}, {"_id": 0, "hostname": 1, "ipAddress": 1, "osType": 1}).to_list(length=50)
    sample_dataset = [
        {"id": doc.get("hostname", ""), "name": doc.get("hostname"), "ip": doc.get("ipAddress", "")}
        for doc in sample_docs
    ]
    if not sample_dataset:
        sample_dataset = [{"id": "no-data", "name": "No assets ingested", "ip": ""}]

    score = quality_service.calculate_quality_score(sample_dataset)
    quarantined = await quality_service.get_quarantined_items()

    # Derive common issues from the sample
    issues = []
    missing_ip = sum(1 for d in sample_dataset if not d.get("ip"))
    if missing_ip:
        issues.append(f"{missing_ip} assets missing IP address")
    if agent_count == 0:
        issues.append("No agents registered")
    if not issues:
        issues.append("No data quality issues detected")

    return {
        "overall_quality_score": round(score, 2),
        "total_records_scanned": total_records,
        "quarantined_count": len(quarantined),
        "common_issues": issues,
        "status": "Healthy" if score > 80 else "Needs Attention"
    }

@router.post("/quality/validate")
async def validate_record(
    record: Dict[str, Any],
    current_user: dict = Depends(require_permission("manage:system"))
):
    """
    Validate a single record against standard rules.
    """
    # Simple rule: must have 'id' and 'timestamp'
    required = ["id", "timestamp"]
    is_valid = quality_service.validate_schema(record, required)
    
    completeness = quality_service.check_completeness(record)
    
    if not is_valid:
        await quality_service.quarantine_data(record, "Missing required fields")
        
    return {
        "valid": is_valid,
        "completeness_score": round(completeness * 100, 2),
        "quarantined": not is_valid
    }
