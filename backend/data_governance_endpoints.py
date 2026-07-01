from fastapi import APIRouter, Depends
from typing import Dict, Any
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
    return await governance_service.get_data_catalog()


@router.get("/governance/lineage")
async def get_data_lineage(
    current_user: dict = Depends(require_permission("view:reporting"))
):
    """
    Return data lineage graph (nodes + edges) derived from the catalog.
    Nodes have: id, label, type (source|process|destination), classification
    Edges have: source, target, label
    """
    from database import get_database
    db = get_database()

    # Fetch catalog entries to build lineage
    catalog = await governance_service.get_data_catalog()
    nodes = []
    edges = []

    # Also pull ETL pipeline definitions if they exist
    etl_pipelines = await db.etl_pipelines.find({}, {"_id": 0}).to_list(length=50)

    # Build source nodes from catalog (first half = sources, rest = destinations)
    source_layer = [e for e in catalog if e.get("type") in ("database", "api", "file", "stream", "source") or e.get("classification") in ("CONFIDENTIAL", "RESTRICTED")]
    dest_layer = [e for e in catalog if e not in source_layer]

    seen_ids: set = set()
    for entry in source_layer[:8]:
        nid = entry.get("id") or entry.get("name", "").lower().replace(" ", "_")
        if nid in seen_ids:
            continue
        seen_ids.add(nid)
        nodes.append({"id": nid, "label": entry.get("name", nid), "type": "source",
                      "classification": entry.get("classification", "INTERNAL"),
                      "owner": entry.get("owner", "")})

    # Processing nodes from ETL pipelines
    for pipe in etl_pipelines[:6]:
        nid = pipe.get("id") or pipe.get("name", "").lower().replace(" ", "_")
        if nid in seen_ids:
            continue
        seen_ids.add(nid)
        nodes.append({"id": nid, "label": pipe.get("name", nid), "type": "process",
                      "classification": "INTERNAL", "owner": pipe.get("owner", "")})
        # Connect to sources
        for src in source_layer[:2]:
            src_id = src.get("id") or src.get("name", "").lower().replace(" ", "_")
            edges.append({"source": src_id, "target": nid, "label": pipe.get("operation", "ETL")})

    # Destination nodes
    for entry in dest_layer[:6]:
        nid = (entry.get("id") or entry.get("name", "")).lower().replace(" ", "_") + "_dest"
        if nid in seen_ids:
            continue
        seen_ids.add(nid)
        nodes.append({"id": nid, "label": entry.get("name", nid), "type": "destination",
                      "classification": entry.get("classification", "INTERNAL"),
                      "owner": entry.get("owner", "")})
        # Connect last process → dest, or source → dest directly
        if etl_pipelines:
            last_proc = etl_pipelines[0].get("id") or etl_pipelines[0].get("name", "").lower().replace(" ", "_")
            if last_proc in seen_ids:
                edges.append({"source": last_proc, "target": nid, "label": "load"})
        elif source_layer:
            src_id = (source_layer[0].get("id") or source_layer[0].get("name", "")).lower().replace(" ", "_")
            edges.append({"source": src_id, "target": nid, "label": "direct"})

    # Seed with platform defaults if catalog is empty
    if not nodes:
        nodes = [
            {"id": "agents_db",    "label": "Agent Telemetry DB",   "type": "source",      "classification": "CONFIDENTIAL", "owner": "Platform"},
            {"id": "assets_db",    "label": "Asset Inventory",       "type": "source",      "classification": "INTERNAL",     "owner": "Platform"},
            {"id": "etl_normalize","label": "ETL Normalization",      "type": "process",     "classification": "INTERNAL",     "owner": "Data Eng"},
            {"id": "etl_enrich",   "label": "CVE Enrichment",         "type": "process",     "classification": "INTERNAL",     "owner": "Data Eng"},
            {"id": "data_lake",    "label": "Security Data Lake",     "type": "destination", "classification": "RESTRICTED",   "owner": "CISO"},
            {"id": "warehouse",    "label": "Analytics Warehouse",    "type": "destination", "classification": "INTERNAL",     "owner": "Analytics"},
        ]
        edges = [
            {"source": "agents_db",     "target": "etl_normalize", "label": "ingest"},
            {"source": "assets_db",     "target": "etl_normalize", "label": "ingest"},
            {"source": "etl_normalize", "target": "etl_enrich",    "label": "transform"},
            {"source": "etl_enrich",    "target": "data_lake",     "label": "load"},
            {"source": "etl_enrich",    "target": "warehouse",     "label": "load"},
        ]

    return {"nodes": nodes, "edges": edges}

# --- Quality Endpoints ---

@router.get("/quality/report")
async def get_quality_report(
    current_user: dict = Depends(require_permission("view:reporting"))
):
    """Get a data quality report based on real record counts from the database."""
    from database import get_database
    db = get_database()

    _DG_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}
    caller_role = (
        current_user.get("role") if isinstance(current_user, dict)
        else getattr(current_user, "role", None)
    )
    caller_tenant = (
        current_user.get("tenant_id") if isinstance(current_user, dict)
        else getattr(current_user, "tenant_id", None)
    )
    base = {} if caller_role in _DG_SUPER_ROLES else {"tenantId": caller_tenant}

    # Count real records across key collections
    asset_count = await db.assets.count_documents(base)
    agent_count = await db.agents.count_documents(base)
    event_count = await db.security_events.count_documents(base)
    alert_count = await db.alerts.count_documents(base)
    total_records = asset_count + agent_count + event_count + alert_count

    # Sample assets for quality scoring (up to 50)
    sample_docs = await db.assets.find(base, {"_id": 0, "hostname": 1, "ipAddress": 1, "osType": 1}).to_list(length=50)
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
