"""
FinOps Usage Tracker
Records API-level usage events into the usage_records collection so that
FinOpsService.calculate_current_spend() has real data to aggregate.

Usage events are written by the record_usage() helper called from key endpoints,
and by the background aggregation loop that counts DB activity every 5 minutes.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from database import get_database

logger = logging.getLogger(__name__)

# Maps internal service names to pricing IDs used by FinOpsService
SERVICE_ID_MAP = {
    "edr_telemetry":       "price-edr",
    "mdr_response":        "price-mdr",
    "xdr_correlation":     "price-xdr",
    "agent_management":    "price-agent-fleet",
    "security_operations": "price-sec-ops",
    "ai_services":         "price-ai-gov",
    "compliance_monitoring": "price-compliance",
    "finops_analytics":    "price-finops",
    "patch_management":    "price-patch-mgmt",
    "log_ingestion":       "price-view-logs",
    "distributed_tracing": "price-dist-trace",
    "software_deployment": "price-soft-hub",
}


async def record_usage(
    service_id: str,
    tenant_id: str,
    amount: float = 1.0,
    metadata: Optional[dict] = None,
) -> None:
    """
    Write a single usage event to usage_records.
    Call this from endpoint handlers to record billable activity.
    """
    try:
        db = get_database()
        await db.usage_records.insert_one({
            "serviceId": service_id,
            "tenantId": tenant_id,
            "amount": amount,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        })
    except Exception as exc:
        logger.debug("[UsageTracker] Failed to record usage for %s: %s", service_id, exc)


async def _aggregate_period(db) -> None:
    """
    Count DB activity in the last 5 minutes and write usage records for each
    active service/tenant combination.
    """
    now = datetime.now(timezone.utc)
    window_start = (now.timestamp() - 300)
    window_iso = datetime.fromtimestamp(window_start, tz=timezone.utc).isoformat()

    # EDR: count telemetry events
    try:
        pipeline = [
            {"$match": {"timestamp": {"$gte": window_iso}}},
            {"$group": {"_id": "$tenantId", "count": {"$sum": 1}}},
        ]
        async for row in db.edr_alerts.aggregate(pipeline):
            if row["_id"] and row["count"]:
                await record_usage("edr_telemetry", row["_id"], float(row["count"]))
    except Exception as exc:
        logger.debug("[UsageTracker] EDR aggregation error: %s", exc)

    # XDR: count correlation events
    try:
        async for row in db.correlation_events.aggregate([
            {"$match": {"timestamp": {"$gte": window_iso}}},
            {"$group": {"_id": "$tenantId", "count": {"$sum": 1}}},
        ]):
            if row["_id"] and row["count"]:
                await record_usage("xdr_correlation", row["_id"], float(row["count"]))
    except Exception as exc:
        logger.debug("[UsageTracker] XDR aggregation error: %s", exc)

    # Agents: count heartbeats (online agents = active usage)
    try:
        async for row in db.agents.aggregate([
            {"$match": {"status": "Online"}},
            {"$group": {"_id": "$tenantId", "count": {"$sum": 1}}},
        ]):
            if row["_id"] and row["count"]:
                # Charge per agent per 5-minute interval (1/12 of hourly rate)
                await record_usage("agent_management", row["_id"], float(row["count"]) / 12.0)
    except Exception as exc:
        logger.debug("[UsageTracker] Agent aggregation error: %s", exc)

    # Patch deployments
    try:
        async for row in db.patch_deployment_jobs.aggregate([
            {"$match": {"createdAt": {"$gte": window_iso}}},
            {"$group": {"_id": "$tenantId", "count": {"$sum": 1}}},
        ]):
            if row["_id"] and row["count"]:
                await record_usage("patch_management", row["_id"], float(row["count"]))
    except Exception as exc:
        logger.debug("[UsageTracker] Patch aggregation error: %s", exc)

    # AI / LLM calls
    try:
        async for row in db.ai_usage_logs.aggregate([
            {"$match": {"timestamp": {"$gte": window_iso}}},
            {"$group": {"_id": "$tenantId", "tokens": {"$sum": "$tokens_used"}}},
        ]):
            if row["_id"] and row["tokens"]:
                await record_usage("ai_services", row["_id"], float(row["tokens"]) / 1000.0)
    except Exception as exc:
        logger.debug("[UsageTracker] AI usage aggregation error: %s", exc)


async def start_usage_tracking_loop() -> None:
    """Run usage aggregation every 5 minutes."""
    while True:
        try:
            db = get_database()
            await _aggregate_period(db._db if hasattr(db, "_db") else db)
        except Exception as exc:
            logger.error("[UsageTracker] Loop error: %s", exc)
        await asyncio.sleep(300)
