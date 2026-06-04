"""
CorrelationEngine response mixin: playbook triggering, periodic loop, and query helpers.
"""

from typing import List, Dict, Any, Optional
import asyncio
import logging

logger = logging.getLogger(__name__)


class CorrelationEngineResponseMixin:
    """Playbook triggering, periodic correlation loop, and correlation query helpers."""

    async def _trigger_playbooks(self, correlation: Dict[str, Any], tenant_id: str) -> None:
        """
        Find playbooks with trigger_type='correlation' whose severity / pattern
        conditions match this correlation, and fire them.
        A playbook opts-in by setting:
            trigger_type: "correlation"
            trigger_conditions:
              severity: ["high", "critical"]   # optional filter
              pattern_ids: ["credential_access", ...]  # optional filter
        """
        try:
            query = {
                "tenant_id": {"$in": [tenant_id, "platform"]},
                "trigger_type": "correlation",
                "enabled": True,
            }
            playbooks = await self.db.playbooks.find(
                query, {"id": 1, "name": 1, "trigger_conditions": 1}
            ).to_list(length=50)

            severity = correlation.get("severity", "")
            pattern_id = correlation.get("pattern_id", "")

            for pb in playbooks:
                tc = pb.get("trigger_conditions") or {}

                allowed_severities = tc.get("severity", [])
                if allowed_severities and severity not in allowed_severities:
                    continue

                allowed_patterns = tc.get("pattern_ids", [])
                if allowed_patterns and pattern_id not in allowed_patterns:
                    continue

                from enhanced_playbook_engine import get_playbook_engine
                engine = get_playbook_engine(self.db)
                exec_result = await engine.execute_playbook(
                    playbook_id=str(pb["_id"]),
                    trigger_data=correlation,
                    tenant_id=tenant_id,
                    executed_by="xdr-auto",
                )
                logger.info(
                    "XDR auto-triggered playbook '%s' for correlation pattern '%s': %s",
                    pb.get("name"), pattern_id, exec_result.get("status"),
                )

            asyncio.create_task(self._ai_select_playbook(tenant_id, correlation))
            asyncio.create_task(self.broadcast_ioc(tenant_id, correlation))
            asyncio.create_task(self.trigger_threat_hunt(tenant_id, pattern_id, correlation))

            agent_id = correlation.get("agent_id")
            asyncio.create_task(self.prestage_kill_chain_defenses(tenant_id, pattern_id, agent_id))
            asyncio.create_task(self._auto_create_security_case(tenant_id, correlation))

        except Exception as exc:
            logger.error(
                "Playbook trigger failed for correlation %s: %s",
                correlation.get("pattern_id"), exc,
            )
            # Surface the failure as an alert so the SOC team is not left in the dark
            try:
                import uuid as _uuid
                from datetime import datetime as _dt, timezone as _tz
                await self.db.alerts.insert_one({
                    "id": str(_uuid.uuid4()),
                    "tenantId": tenant_id,
                    "severity": "High",
                    "type": "playbook_trigger_failure",
                    "source": "correlation_engine",
                    "message": (
                        f"Automated playbook trigger failed for pattern "
                        f"'{correlation.get('pattern_id', 'unknown')}': {exc}"
                    ),
                    "status": "Open",
                    "acknowledged": False,
                    "timestamp": _dt.now(_tz.utc).isoformat(),
                })
            except Exception as _alert_err:
                logger.error("Failed to raise playbook-failure alert: %s", _alert_err)

    async def run_periodic_correlation(
        self,
        tenant_id: str,
        interval_seconds: int = 300,
        time_window_minutes: int = 60,
    ) -> None:
        """Background loop: run correlate_events() every interval_seconds."""
        logger.info(
            "XDR periodic correlation started for tenant %s (interval=%ds, window=%dm)",
            tenant_id, interval_seconds, time_window_minutes,
        )
        while True:
            try:
                found = await self.correlate_events(tenant_id, time_window_minutes)
                if found:
                    logger.info(
                        "XDR periodic scan: %d correlation(s) detected for tenant %s",
                        len(found), tenant_id,
                    )
            except Exception as exc:
                logger.error("Periodic correlation error for tenant %s: %s", tenant_id, exc)
            await asyncio.sleep(interval_seconds)

    async def get_correlations(
        self,
        tenant_id: str,
        limit: int = 50,
        severity: Optional[str] = None,
    ) -> List[Dict]:
        """Get recent correlations for a tenant."""
        query: Dict[str, Any] = {"tenant_id": tenant_id}
        if severity:
            query["severity"] = severity
        cursor = self.db.correlations.find(query).sort("detected_at", -1).limit(limit)
        correlations = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            correlations.append(doc)
        return correlations

    async def get_correlation_stats(self, tenant_id: str) -> Dict[str, Any]:
        """Get correlation statistics aggregated by severity."""
        pipeline = [
            {"$match": {"tenant_id": tenant_id}},
            {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
        ]
        cursor = self.db.correlations.aggregate(pipeline)
        severity_counts: Dict[str, int] = {}
        total = 0
        async for doc in cursor:
            severity_counts[doc["_id"]] = doc["count"]
            total += doc["count"]
        return {
            "total_correlations": total,
            "by_severity": severity_counts,
            "critical_count": severity_counts.get("critical", 0),
            "high_count": severity_counts.get("high", 0),
            "medium_count": severity_counts.get("medium", 0),
            "low_count": severity_counts.get("low", 0),
        }
