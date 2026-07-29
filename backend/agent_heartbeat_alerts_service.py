"""
Persistence-detection and PII-scanner telemetry handlers, extracted from
agent_heartbeat_endpoints.py (CLAUDE.md-driven adjustment, Phase 46 Plan 05,
Rule 2) — the endpoint file was already over the CLAUDE.md 500-line cap
before this plan's ASN/location-history wiring landed, and this plan's own
acceptance criteria requires it stay under 500 afterward. Both blocks were
self-contained (only need db, agent_id, tenant_id, and the relevant `meta`
sub-payload), making this a clean, behavior-preserving extraction.
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger("agent_heartbeat_alerts_service")


async def persist_persistence_detection(db, agent_id: str, tenant_id, p_data) -> None:
    if not (isinstance(p_data, dict) and p_data.get("findings")):
        return
    import uuid as _uuid
    await db.persistence_results.insert_one({
        "id": _uuid.uuid4().hex, "tenantId": tenant_id,
        "agentId": agent_id, "findings": p_data.get("findings", []),
        "count": p_data.get("count", 0), "platform": p_data.get("platform"),
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


async def persist_pii_scanner(db, agent_id: str, tenant_id, pii_data, background_tasks) -> None:
    if not (isinstance(pii_data, dict) and pii_data.get("pii_found")):
        return
    try:
        from ueba_service import persist_security_alert
        background_tasks.add_task(
            persist_security_alert, db, alert_type="pii_detected", severity="high",
            title=f"PII Detected on Agent {agent_id}",
            description=f"{pii_data.get('findings_count', 0)} file(s) contain PII patterns.",
            metadata={**pii_data, "agent_id": agent_id, "tenantId": tenant_id},
        )
    except ImportError:
        pass
    _allowed_pii = {"findings_count", "pii_found", "files_scanned", "categories"}
    await db.pii_findings.update_one(
        {"agent_id": agent_id},
        {"$set": {k: pii_data[k] for k in _allowed_pii if k in pii_data} | {
            "agent_id": agent_id,
            "tenantId": tenant_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
