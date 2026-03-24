from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List
from data_quality_service import quality_service
from data_governance_service import governance_service
from rbac_utils import require_permission

router = APIRouter(prefix="/api", tags=["Data Governance & Quality"])

# --- Governance Endpoints ---

@router.post("/governance/scan")
async def scan_data(
    data: Dict[str, Any],
    current_user: dict = Depends(require_permission("view:system"))
):
    """
    On-demand scan of a data record for PII and classification.
    """
    pii_types = governance_service.scan_for_pii(str(data))
    classification = governance_service.classify_data(data)
    
    return {
        "pii_detected": pii_types,
        "classification": classification,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

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
    """
    Get a simulated data quality report.
    """
    # Simulate a dataset check
    sample_dataset = [
        {"id": 1, "name": "Valid Record", "email": "test@example.com"},
        {"id": 2, "name": "Incomplete", "email": ""}, # Missing email
        {"id": 3, "name": None, "email": "no-name@example.com"} # Missing name
    ]
    
    score = quality_service.calculate_quality_score(sample_dataset)
    quarantined = quality_service.get_quarantined_items()
    
    return {
        "overall_quality_score": round(score, 2),
        "total_records_scanned": 15420, # Simulated total
        "quarantined_count": len(quarantined),
        "common_issues": ["Missing 'email' field", "Invalid timestamp format"],
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
        quality_service.quarantine_data(record, "Missing required fields")
        
    return {
        "valid": is_valid,
        "completeness_score": round(completeness * 100, 2),
        "quarantined": not is_valid
    }
