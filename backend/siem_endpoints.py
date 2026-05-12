from fastapi import APIRouter, Depends, HTTPException, Query
from ingest_service import ingest_service
from tenant_context import get_tenant_id
from authentication_service import get_current_user
from auth_types import TokenData
from database import get_database
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
import re

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

# ── SIEM Integration Config Management ───────────────────────────────────────

@router.get("/configs")
async def list_siem_configs(
    _current_user: TokenData = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id),
):
    """List all SIEM integration configurations for the current tenant."""
    try:
        db = get_database()
        configs = await db.siem_configs.find(
            {"tenant_id": tenant_id}, {"_id": 0, "aws_secret_key": 0, "api_token": 0}
        ).to_list(length=100)
        return {"configs": configs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/configs/{provider}")
async def upsert_siem_config(
    provider: str,
    data: Dict[str, Any],
    current_user: TokenData = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id),
):
    """
    Create or update a SIEM integration config.
    Providers: aws_cloudtrail, okta, syslog.
    Body fields vary by provider — see inline docs.
    """
    allowed = {"aws_cloudtrail", "okta", "syslog"}
    if provider not in allowed:
        raise HTTPException(status_code=400, detail=f"Unknown provider. Must be one of: {allowed}")
    try:
        db = get_database()
        update = {**data, "provider": provider, "tenant_id": tenant_id,
                  "updated_at": datetime.now(timezone.utc).isoformat(),
                  "updated_by": getattr(current_user, "username", str(current_user))}
        await db.siem_configs.update_one(
            {"provider": provider, "tenant_id": tenant_id},
            {"$set": update},
            upsert=True,
        )
        safe = {k: v for k, v in update.items() if k not in ("aws_secret_key", "api_token")}
        return {"success": True, "config": safe}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/configs/{provider}")
async def delete_siem_config(
    provider: str,
    _current_user: TokenData = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id),
):
    """Remove a SIEM integration config."""
    try:
        db = get_database()
        result = await db.siem_configs.delete_one({"provider": provider, "tenant_id": tenant_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Config not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Log Explorer endpoints ─────────────────────────────────────────────────────

@router.get("/logs")
async def search_logs(
    q: str = Query("", description="Full-text / keyword search on log message"),
    source: str = Query("", description="Filter by source (metadata.product)"),
    limit: int = Query(200, ge=1, le=2000),
    _current_user: TokenData = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id),
):
    """
    Full-text log search for the Log Explorer dashboard.
    Queries security_events with optional keyword and source filters.
    Returns flat records shaped for the frontend table.
    """
    try:
        db = get_database()
        query: Dict[str, Any] = {"tenantId": tenant_id} if tenant_id != "platform-admin" else {}
        if source:
            query["metadata.product"] = source
        if q:
            try:
                query["message"] = {"$regex": re.escape(q), "$options": "i"}
            except Exception:
                pass

        cursor = db.security_events.find(query, {"_id": 0}).sort("time", -1).limit(limit)
        raw_events = await cursor.to_list(length=limit)

        logs = [
            {
                "id": e.get("id", ""),
                "timestamp": e.get("time") or e.get("ingestedAt", ""),
                "log_type": e.get("metadata", {}).get("product", "unknown"),
                "severity": e.get("severity", "Low"),
                "raw_message": e.get("message") or e.get("activity_name") or e.get("class_name") or "",
                "category": e.get("category_name", ""),
            }
            for e in raw_events
        ]
        return {"logs": logs, "total": len(logs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/aggregations")
async def get_log_aggregations(
    _current_user: TokenData = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id),
):
    """
    Returns aggregated stats for the Log Explorer: source counts and hourly histogram.
    """
    try:
        db = get_database()
        match_filter: Dict[str, Any] = {"tenantId": tenant_id} if tenant_id != "platform-admin" else {}

        # Source distribution
        source_pipeline = [
            {"$match": match_filter},
            {"$group": {"_id": "$metadata.product", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 20},
        ]
        source_docs = await db.security_events.aggregate(source_pipeline).to_list(length=20)
        sources = {(d["_id"] or "unknown"): d["count"] for d in source_docs}

        # Hourly histogram for the past 24 hours (24 buckets)
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        since_iso = since.isoformat()

        histogram_pipeline = [
            {"$match": {**match_filter, "time": {"$gte": since_iso}}},
            {
                "$group": {
                    "_id": {
                        "$substr": ["$time", 0, 13]  # "YYYY-MM-DDTHH" bucket
                    },
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"_id": 1}},
        ]
        hist_docs = await db.security_events.aggregate(histogram_pipeline).to_list(length=48)
        histogram = [{"time": d["_id"], "count": d["count"]} for d in hist_docs]

        # Severity breakdown
        sev_pipeline = [
            {"$match": match_filter},
            {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
        ]
        sev_docs = await db.security_events.aggregate(sev_pipeline).to_list(length=10)
        severity_counts = {d["_id"]: d["count"] for d in sev_docs}

        total = await db.security_events.count_documents(match_filter)

        return {
            "sources": sources,
            "histogram": histogram,
            "severity_counts": severity_counts,
            "total": total,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Summary ───────────────────────────────────────────────────────────────────

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


# ── SIEM Correlation Rules ─────────────────────────────────────────────────────

@router.get("/rules")
async def list_siem_rules(
    tenant_id_param: Optional[str] = Query(None, alias="tenant_id"),
    _current_user: TokenData = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id),
):
    """List SIEM correlation rules for the current tenant."""
    try:
        db = get_database()
        effective_tenant = tenant_id_param or tenant_id
        rules = await db.siem_rules.find(
            {"tenant_id": effective_tenant}, {"_id": 0}
        ).sort("created_at", -1).to_list(length=500)
        return rules
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rules")
async def create_siem_rule(
    data: Dict[str, Any],
    tenant_id_param: Optional[str] = Query(None, alias="tenant_id"),
    current_user: TokenData = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id),
):
    """Create a new SIEM correlation rule."""
    try:
        import uuid
        db = get_database()
        effective_tenant = tenant_id_param or tenant_id
        rule = {
            "id": f"rule-{uuid.uuid4().hex[:10]}",
            "name": data.get("name", ""),
            "description": data.get("description", ""),
            "severity": data.get("severity", "Medium"),
            "enabled": data.get("enabled", True),
            "conditions": data.get("conditions", {}),
            "remediation": data.get("remediation", ""),
            "tenant_id": effective_tenant,
            "created_by": getattr(current_user, "username", "system"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "match_count": 0,
        }
        await db.siem_rules.insert_one(rule)
        rule.pop("_id", None)
        return rule
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/rules/{rule_id}")
async def update_siem_rule(
    rule_id: str,
    data: Dict[str, Any],
    tenant_id_param: Optional[str] = Query(None, alias="tenant_id"),
    current_user: TokenData = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id),
):
    """Update an existing SIEM correlation rule."""
    try:
        db = get_database()
        effective_tenant = tenant_id_param or tenant_id
        allowed = {"name", "description", "severity", "enabled", "conditions", "remediation"}
        update = {k: v for k, v in data.items() if k in allowed}
        update["updated_at"] = datetime.now(timezone.utc).isoformat()
        result = await db.siem_rules.update_one(
            {"id": rule_id, "tenant_id": effective_tenant},
            {"$set": update},
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Rule not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/rules/{rule_id}")
async def delete_siem_rule(
    rule_id: str,
    tenant_id_param: Optional[str] = Query(None, alias="tenant_id"),
    current_user: TokenData = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id),
):
    """Delete a SIEM correlation rule."""
    try:
        db = get_database()
        effective_tenant = tenant_id_param or tenant_id
        result = await db.siem_rules.delete_one({"id": rule_id, "tenant_id": effective_tenant})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Rule not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
