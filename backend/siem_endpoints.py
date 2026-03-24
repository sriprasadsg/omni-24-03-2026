from fastapi import APIRouter, Depends, HTTPException, Query
from ingest_service import ingest_service
from tenant_context import get_tenant_id
from typing import List, Dict, Any, Optional

router = APIRouter(prefix="/api/siem", tags=["SIEM"])

@router.post("/ingest")
async def ingest_log(source: str, payload: Dict[str, Any], tenant_id: str = Depends(get_tenant_id)):
    """
    Ingests a raw log from a security source and normalizes it to OCSF.
    """
    try:
        event_id = await ingest_service.ingest_raw_log(tenant_id, source, payload)
        return {"status": "Success", "event_id": event_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/events")
async def get_events(
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0),
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Retrieves normalized security events for the current tenant.
    """
    try:
        events = await ingest_service.get_security_events(tenant_id, limit, skip)
        return {"events": events}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/summary")
async def get_siem_summary(tenant_id: str = Depends(get_tenant_id)):
    """
    Provides a high-level summary of security event distribution.
    """
    try:
        events: List[Dict[str, Any]] = await ingest_service.get_security_events(tenant_id, limit=500)
        summary: Dict[str, Any] = {
            "total_events": len(events),
            "severity_counts": {
                "Critical": 0, "High": 0, "Medium": 0, "Low": 0
            },
            "source_counts": {}
        }
        for e in events:
            sev = e.get("severity", "Low")
            if sev in summary["severity_counts"]:
                summary["severity_counts"][sev] += 1
            src = e.get("metadata", {}).get("product", "Unknown")
            summary["source_counts"][src] = summary["source_counts"].get(src, 0) + 1
            
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
