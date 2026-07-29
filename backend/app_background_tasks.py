"""Background coroutines started during the application lifespan."""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# New imports for autonomous remediation
from autonomous_remediation_service import AutonomousRemediationService, AUTONOMOUS_REMEDIATION_INTERVAL_SEC
from tenant_context import set_tenant_id, reset_tenant_id # Import set_tenant_id, reset_tenant_id


async def autonomous_remediation_loop():
    """Continuous loop to run autonomous remediation across tenants."""
    logger = logging.getLogger(__name__ + ".auto_remediation")
    logger.info("Autonomous remediation loop started (interval=%ds)", AUTONOMOUS_REMEDIATION_INTERVAL_SEC)

    service = AutonomousRemediationService()

    while True:
        _tenant_ctx_token = None
        try:
            db = get_database() # Ensure get_database is imported or globally available
            # Scan all tenants
            tenants = await db._db.tenants.find({}, {"id": 1}).to_list(length=500)
            for tenant in tenants:
                tid = tenant.get("id")
                if tid:
                    _tenant_ctx_token = set_tenant_id(tid) # Set tenant context before running cycle
                    await service.run_cycle(tid)
        except Exception as e:
            logger.error("Autonomous remediation loop error for tenant %s: %s", tid, e)
        finally:
            if _tenant_ctx_token is not None:
                reset_tenant_id(_tenant_ctx_token) # Ensure context is reset

        await asyncio.sleep(AUTONOMOUS_REMEDIATION_INTERVAL_SEC)


async def monitor_agent_status():
    """Background task to mark agents as Offline if inactive > 5 min (10× missed 30 s heartbeat)."""
    import websocket_manager
    from database import get_database
    from tenant_context import set_tenant_id, reset_tenant_id

    while True:
        _tenant_ctx_token = None
        try:
            await asyncio.sleep(30)
            _tenant_ctx_token = set_tenant_id("platform-admin")
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
        finally:
            if _tenant_ctx_token is not None:
                reset_tenant_id(_tenant_ctx_token)


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
    from tenant_context import set_tenant_id, reset_tenant_id
    from compliance_score_endpoints import (
        _weighted_score, _score_status, _CATEGORY_SEVERITY, SEVERITY_WEIGHTS,
        _VULN_WEIGHTS, _VULN_BURDEN_BASELINE, _ASSET_WEIGHTS,
    )

    _log = logging.getLogger(__name__ + ".score_snapshot")
    _log.info("Compliance score snapshot loop started (interval=86400s)")

    while True:
        await asyncio.sleep(86400)  # run once per day
        _tenant_ctx_token = None
        try:
            db = get_database()
            _tenant_ctx_token = set_tenant_id("platform-admin")

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
                        upsert=True
                    )
                    _log.info("Compliance score snapshot recorded for tenant %s: %s", tid, threat_score)

                except Exception as _te:
                    _log.error("Compliance score snapshot error for tenant %s: %s", tid, _te)
        except Exception as _e:
            _log.error("Compliance score snapshot cycle error: %s", _e)
        finally:
            if _tenant_ctx_token is not None:
                reset_tenant_id(_tenant_ctx_token)

async def _run_agent_uptime_rollup_once(db) -> int:
    """
    Single-pass body of `agent_uptime_rollup_loop()`, factored out so tests
    can drive one sweep iteration directly rather than the infinite
    `while True` loop.

    Reuses `agent_uptime_service.compute_uptime` for the daily % (D-01b) —
    NEVER re-implements the uptime math here. Iterates ALL tenants via raw
    `db._db` (Pattern 1 — this is a legitimate cross-tenant background
    sweep), writing one upserted row per agent per day into
    `agent_uptime_rollups` keyed on `{agent_id, date}`. Every row carries an
    explicit `tenant_id` (T-48-04).

    Returns the number of rollup rows upserted this pass.
    """
    from agent_uptime_service import compute_uptime

    _log = logging.getLogger(__name__ + ".uptime_rollup")
    _tenant_ctx_token = None
    written = 0
    try:
        _tenant_ctx_token = set_tenant_id("platform-admin")
        tenants = await db._db.tenants.find({}, {"id": 1}).to_list(length=500)
        now = datetime.now(timezone.utc)
        date_key = now.strftime("%Y-%m-%d")
        window_start_iso = (now - timedelta(hours=24)).isoformat()

        for tenant in tenants:
            tid = tenant.get("id")
            if not tid:
                continue
            try:
                set_tenant_id(tid)
                agents = await db._db.agents.find(
                    {"tenantId": tid}, {"id": 1}
                ).to_list(length=5000)

                for agent in agents:
                    aid = agent.get("id")
                    if not aid:
                        continue

                    rows = await db._db.agent_metrics.find(
                        {"agent_id": aid, "timestamp": {"$gte": window_start_iso}},
                        {"_id": 0, "timestamp": 1},
                    ).to_list(length=5760)  # 24h ceiling at 30s cadence

                    result = compute_uptime(rows, 24)

                    await db._db.agent_uptime_rollups.update_one(
                        {"agent_id": aid, "date": date_key},
                        {
                            "$set": {
                                "tenant_id": tid,
                                "uptime_percent": result["uptime_percent"],
                                # Native BSON Date — NEVER .isoformat() here
                                # (Pattern 3 / T-48-06): retention_service
                                # compares this field with a datetime $lt.
                                "timestamp": datetime.now(timezone.utc),
                            }
                        },
                        upsert=True,
                    )
                    written += 1
            except Exception as _te:
                _log.error("Agent uptime rollup error for tenant %s: %s", tid, _te)
    except Exception as _e:
        _log.error("Agent uptime rollup cycle error: %s", _e)
    finally:
        if _tenant_ctx_token is not None:
            reset_tenant_id(_tenant_ctx_token)
    return written


async def agent_uptime_rollup_loop():
    """
    Daily background sweep (FOBS-02, D-01b): writes one row per agent per
    day into `agent_uptime_rollups`, so aggregate/long-range uptime is cheap
    and a future longer-range UI is a switch-on, not a rebuild.

    D-08: this performs NO historical backfill. Each run writes ONLY the
    current day's row — an empty `agent_uptime_rollups` collection right
    after first deploy is expected (it fills in one row per agent per day
    going forward), not a bug.
    """
    from database import get_database

    _log = logging.getLogger(__name__ + ".uptime_rollup")
    _log.info("Agent uptime rollup loop started (interval=86400s)")

    while True:
        await asyncio.sleep(86400)  # run once per day; no backfill (D-08)
        try:
            db = get_database()
            written = await _run_agent_uptime_rollup_once(db)
            _log.info("Agent uptime rollup sweep wrote %d row(s)", written)
        except Exception as _e:
            _log.error("Agent uptime rollup loop error: %s", _e)


async def refresh_mitre_heatmap_loop():
    """Nightly rebuild of the MITRE ATT&CK heatmap cache."""
    from mitre_heatmap_service import MitreHeatmapService
    from database import get_database
    from tenant_context import set_tenant_id, reset_tenant_id

    _log = logging.getLogger(__name__ + ".mitre_heatmap")
    _log.info("MITRE heatmap refresh loop started (interval=86400s)")

    while True:
        await asyncio.sleep(86400)  # run once per day
        _tenant_ctx_token = None
        try:
            db = get_database()
            _tenant_ctx_token = set_tenant_id("platform-admin") # Admin context for tenant enumeration

            tenants = await db._db.tenants.find({}, {"id": 1}).to_list(length=500)
            heatmap_service = MitreHeatmapService(db)

            for tenant in tenants:
                tid = tenant.get("id")
                if tid:
                    try:
                        set_tenant_id(tid) # Switch to tenant context for heatmap generation
                        await heatmap_service.rebuild_heatmap_cache(tid)
                        _log.info("MITRE heatmap refreshed for tenant %s", tid)
                    except Exception as _te:
                        _log.error("MITRE heatmap refresh error for tenant %s: %s", tid, _te)
        except Exception as _e:
            _log.error("MITRE heatmap refresh cycle error: %s", _e)
        finally:
            if _tenant_ctx_token is not None:
                reset_tenant_id(_tenant_ctx_token)
