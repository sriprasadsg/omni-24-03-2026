"""Background coroutines started during the application lifespan."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


async def monitor_agent_status():
    """Background task to mark agents as Offline if inactive > 5 min (10× missed 30 s heartbeat)."""
    import websocket_manager
    from database import get_database
    from tenant_context import set_tenant_id

    while True:
        try:
            await asyncio.sleep(30)
            set_tenant_id("platform-admin")
            db = get_database()
            threshold = datetime.now(timezone.utc) - timedelta(minutes=5)

            result = await db.agents.update_many(
                {
                    "status": "Online",
                    "lastSeen": {"$lt": threshold.isoformat()},
                },
                {"$set": {"status": "Offline"}},
            )
            if result.modified_count > 0:
                logger.info("[Monitor] Marked %d stale agents as Offline", result.modified_count)

                affected_agents = await db.agents.find(
                    {"status": "Offline", "lastSeen": {"$lt": threshold.isoformat()}}
                ).to_list(length=result.modified_count)

                for agent in affected_agents:
                    tenant_id = agent.get("tenantId")
                    if tenant_id:
                        await websocket_manager.broadcast_agent_status_change(
                            tenant_id=tenant_id,
                            agent_id=agent.get("id"),
                            status="Offline",
                            details={"reason": "Heartbeat timeout"},
                        )

                from notification_manager import notification_manager
                await notification_manager.send_notification(
                    "agent.offline",
                    {"count": result.modified_count, "timestamp": datetime.now().isoformat()},
                    "platform-admin",
                )
        except Exception as e:
            logger.error("[Monitor] Error in stale agent check: %s", e)


async def _start_xdr_correlation_scanner() -> None:
    """
    Background task: fetch all active tenant IDs from MongoDB and run
    the XDR correlation engine against each one every 5 minutes.
    """
    _log = logging.getLogger("xdr_scanner")
    _log.info("XDR correlation scanner starting (interval=300s)")

    while True:
        try:
            from correlation_engine import get_correlation_engine
            from database import get_database
            db = get_database()
            # INTENTIONAL: platform-admin task — passes raw db to engine
            tenants = await db._db.tenants.find({}, {"id": 1}).to_list(length=500)
            engine = get_correlation_engine(db._db)
            for tenant in tenants:
                tid = tenant.get("id")
                if tid:
                    try:
                        found = await engine.correlate_events(tid, time_window_minutes=60)
                        if found:
                            _log.info("XDR: %d correlation(s) for tenant %s", len(found), tid)
                    except Exception as _te:
                        _log.error("XDR correlation error for tenant %s: %s", tid, _te)
        except Exception as _e:
            _log.error("XDR scanner cycle error: %s", _e)

        await asyncio.sleep(300)


async def compliance_evidence_sweep_loop():
    """Delegate to the dedicated compliance automation service."""
    from compliance_auto_evidence_service import compliance_evidence_sweep_loop as _loop
    await _loop()


async def snapshot_compliance_scores_loop():
    """Daily snapshot: write overall + ThreatScore to compliance_score_history for trend charts."""
    from database import get_database
    from tenant_context import set_tenant_id
    from compliance_score_endpoints import (
        _weighted_score, _score_status, _CATEGORY_SEVERITY, SEVERITY_WEIGHTS,
        _VULN_WEIGHTS, _VULN_BURDEN_BASELINE, _ASSET_WEIGHTS,
    )

    _log = logging.getLogger(__name__ + ".score_snapshot")
    _log.info("Compliance score snapshot loop started (interval=86400s)")

    while True:
        await asyncio.sleep(86400)  # run once per day
        try:
            db = get_database()
            set_tenant_id("platform-admin")

            # Enumerate all tenants
            tenants = await db._db.tenants.find({}, {"id": 1}).to_list(length=500)
            now = datetime.now(timezone.utc)
            date_key = now.strftime("%Y-%m-%d")

            for tenant in tenants:
                tid = tenant.get("id")
                if not tid:
                    continue
                try:
                    set_tenant_id(tid)

                    # Compliance score
                    frameworks = [fw async for fw in db._db.compliance_frameworks.find({})]
                    control_meta = {
                        c.get("id"): {"severity": _CATEGORY_SEVERITY.get(c.get("category", ""), "Low")}
                        for fw in frameworks for c in fw.get("controls", []) if c.get("id")
                    }
                    ac_by_control = {}
                    async for doc in db.asset_compliance.find({"controlId": {"$in": list(control_meta)}}):
                        if doc.get("controlId"):
                            ac_by_control[doc["controlId"]] = doc.get("status", "")

                    evaluated = [
                        {"severity": control_meta[cid]["severity"], "status_norm": _score_status(st)}
                        for cid, st in ac_by_control.items() if cid in control_meta
                    ]
                    compliance_pct = _weighted_score(evaluated)

                    # Vuln burden
                    vuln_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
                    async for doc in db.vulnerabilities.find({"status": {"$nin": ["closed", "resolved", "false_positive"]}}):
                        sev = (doc.get("severity") or "low").lower()
                        if sev in vuln_counts:
                            vuln_counts[sev] += 1
                    vuln_burden = sum(vuln_counts[s] * _VULN_WEIGHTS[s] for s in vuln_counts)
                    vuln_component = round((1.0 - min(1.0, vuln_burden / _VULN_BURDEN_BASELINE)) * 400, 1)

                    # Asset criticality
                    asset_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
                    total_assets = 0
                    async for doc in db.assets.find({}):
                        total_assets += 1
                        crit = (doc.get("criticality") or doc.get("risk_level") or "low").lower()
                        if crit in asset_counts:
                            asset_counts[crit] += 1
                    if total_assets > 0:
                        ab = sum(asset_counts[s] * _ASSET_WEIGHTS[s] for s in asset_counts)
                        asset_component = round((1.0 - ab / (total_assets * _ASSET_WEIGHTS["critical"])) * 200, 1)
                    else:
                        asset_component = 100.0

                    threat_score = round(compliance_pct / 100 * 400 + vuln_component + asset_component)

                    snapshot = {
                        "tenant_id": tid,
                        "date": date_key,
                        "compliance_pct": compliance_pct,
                        "threat_score": threat_score,
                        "vuln_counts": vuln_counts,
                        "asset_counts": asset_counts,
                        "recorded_at": now,
                    }
                    await db._db.compliance_score_history.update_one(
                        {"tenant_id": tid, "date": date_key},
                        {"$set": snapshot},
                        upsert=True,
                    )
                    _log.debug("Snapshot saved for tenant %s: score=%s threat=%s", tid, compliance_pct, threat_score)
                except Exception as _te:
                    _log.error("Snapshot failed for tenant %s: %s", tid, _te)

        except Exception as _e:
            _log.error("Score snapshot loop error: %s", _e)


async def refresh_mitre_heatmap_loop():
    """Recompute and broadcast MITRE ATT&CK heatmap to connected tenants every 60 seconds."""
    import websocket_manager
    from mitre_service import get_coverage_heatmap

    _log = logging.getLogger(__name__ + ".mitre_refresh")
    _log.info("MITRE heatmap auto-refresh loop started (interval=60s)")

    while True:
        await asyncio.sleep(60)
        try:
            tenant_ids = websocket_manager.get_connected_tenant_ids()
            for tenant_id in tenant_ids:
                if not tenant_id or tenant_id == "platform-admin":
                    continue
                try:
                    heatmap = await get_coverage_heatmap(tenant_id)
                    await websocket_manager.broadcast_mitre_heatmap(tenant_id, heatmap)
                except Exception as _te:
                    _log.debug("MITRE refresh failed for tenant %s: %s", tenant_id, _te)
        except Exception as _e:
            _log.error("MITRE heatmap refresh loop error: %s", _e)
