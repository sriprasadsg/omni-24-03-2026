"""
CorrelationEngine threat mixin: AI playbook selection, case creation, false-positive
feedback, IoC broadcast, threat hunting, and kill-chain pre-staging.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone
import logging

logger = logging.getLogger(__name__)


class CorrelationEngineThreatMixin:
    """AI-driven response, threat intelligence, and kill-chain prediction."""

    # Maps detected stage → next likely stage + recommended pre-staging action
    KILL_CHAIN_NEXT_STAGE: Dict[str, Dict[str, Any]] = {
        "credential_access": {
            "next_stage": "lateral_movement",
            "instruction": "enable_enhanced_auth_logging",
            "description": (
                "Credential access detected — pre-staging enhanced auth logging "
                "to catch lateral movement attempts early."
            ),
        },
        "lateral_movement": {
            "next_stage": "privilege_escalation",
            "instruction": "enable_privilege_monitoring",
            "description": "Lateral movement detected — pre-staging privilege escalation monitoring.",
        },
        "privilege_escalation": {
            "next_stage": "data_exfiltration",
            "instruction": "enable_data_loss_monitoring",
            "description": "Privilege escalation detected — enabling DLP monitoring to catch exfiltration.",
        },
        "data_exfiltration": {
            "next_stage": "ransomware",
            "instruction": "create_vss_snapshot",
            "description": "Exfiltration detected — triggering VSS snapshot as ransomware pre-staging.",
        },
        "ransomware": {
            "next_stage": "impact",
            "instruction": "run_vss_rollback_check",
            "description": "Ransomware detected — verifying VSS snapshots are intact for recovery.",
        },
    }

    async def _ai_select_playbook(
        self, tenant_id: str, correlation: Dict[str, Any]
    ) -> None:
        """Ask the AI service to suggest the best playbook for a correlation."""
        try:
            from ai_service import IncidentAnalyzer
            from enhanced_playbook_engine import get_playbook_engine

            analyzer = IncidentAnalyzer()
            await analyzer.initialize()
            if not analyzer.is_configured:
                return

            prompt = (
                f"A security correlation was detected: pattern={correlation.get('pattern')}, "
                f"severity={correlation.get('severity')}, type={correlation.get('type')}. "
                f"What is the single best incident response action? "
                f"Respond with one word: isolate, block, quarantine, or notify."
            )
            suggestion = (
                await analyzer.generate_text(prompt, source="correlation")
            ).strip().lower()
            action_map = {
                "isolate": "isolate_endpoint",
                "block": "block_ip",
                "quarantine": "quarantine_file",
                "notify": "send_notification",
            }
            action = next((v for k, v in action_map.items() if k in suggestion), None)
            if not action:
                return

            playbook = await self.db.playbooks.find_one({
                "tenant_id": {"$in": [tenant_id, "platform"]},
                "steps.action": action,
                "enabled": True,
            })
            if playbook:
                engine = get_playbook_engine(self.db)
                context = {"auto_approved": True, "confidence": correlation.get("confidence", 0.9)}
                await engine.execute_playbook(
                    playbook_id=str(playbook["_id"]),
                    trigger_data={**correlation, **context},
                    tenant_id=tenant_id,
                    executed_by="ai-selector",
                )
                logger.info(
                    "AI selected playbook '%s' (action=%s) for correlation pattern '%s'",
                    playbook.get("name"), action, correlation.get("pattern_id"),
                )
        except Exception as exc:
            logger.warning("AI playbook selection failed: %s — using rule-based fallback", exc)
            await self._fallback_select_playbook(tenant_id, correlation)

    async def _fallback_select_playbook(
        self, tenant_id: str, correlation: Dict[str, Any]
    ) -> None:
        """Select the first enabled playbook matching the correlation severity when AI is unavailable."""
        try:
            from enhanced_playbook_engine import get_playbook_engine
            severity = correlation.get("severity", "Medium")
            playbook = await self.db.playbooks.find_one({
                "tenant_id": {"$in": [tenant_id, "platform"]},
                "enabled": True,
                "$or": [
                    {"trigger_severity": severity},
                    {"trigger_severity": {"$exists": False}},
                ],
            }, sort=[("priority", -1)])
            if playbook:
                engine = get_playbook_engine(self.db)
                await engine.execute_playbook(
                    playbook_id=str(playbook.get("id", playbook["_id"])),
                    trigger_data={**correlation, "auto_approved": True},
                    tenant_id=tenant_id,
                    executed_by="fallback-selector",
                )
                logger.info(
                    "Fallback selected playbook '%s' for correlation pattern '%s'",
                    playbook.get("name"), correlation.get("pattern_id"),
                )
        except Exception as fb_exc:
            logger.error("Fallback playbook selection also failed: %s", fb_exc)

    async def _auto_create_security_case(
        self, tenant_id: str, correlation: Dict[str, Any]
    ) -> None:
        """Open a security case for critical/high-severity correlations."""
        severity = correlation.get("severity", "")
        if severity not in ("critical", "high"):
            return

        pattern_id = correlation.get("pattern_id", "unknown")
        now = datetime.now(timezone.utc).isoformat()
        one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        existing = await self.db.security_cases.find_one({
            "tenant_id": tenant_id,
            "correlation_pattern": pattern_id,
            "created_at": {"$gte": one_hour_ago},
        })
        if existing:
            return

        case = {
            "id": f"CASE-AUTO-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "tenant_id": tenant_id,
            "title": f"[AUTO] {correlation.get('pattern', pattern_id)}",
            "description": (
                f"Automatically generated from XDR correlation.\n"
                f"Pattern: {correlation.get('pattern')}\n"
                f"Severity: {severity}\n"
                f"Events correlated: {correlation.get('event_count', 0)}\n"
                f"Confidence: {correlation.get('confidence', 0):.0%}"
            ),
            "severity": severity,
            "status": "open",
            "source": "xdr_auto",
            "correlation_pattern": pattern_id,
            "correlation_id": str(correlation.get("_id", "")),
            "created_at": now,
            "updated_at": now,
        }
        await self.db.security_cases.insert_one(case)
        logger.info(
            "AUTO-CASE created for pattern '%s' severity='%s' in tenant %s",
            pattern_id, severity, tenant_id,
        )

    async def record_false_positive(self, pattern_id: str, tenant_id: str) -> None:
        """
        Increment the false-positive counter for a pattern.
        When FP rate over the last 7 days exceeds 20%, raise the pattern threshold by 1.
        """
        now = datetime.now(timezone.utc)
        await self.db.pattern_stats.update_one(
            {"pattern_id": pattern_id, "tenant_id": tenant_id},
            {
                "$inc": {"fp_count": 1, "total_count": 1},
                "$set": {"last_updated": now.isoformat()},
                "$setOnInsert": {"created_at": now.isoformat()},
            },
            upsert=True,
        )

        stats = await self.db.pattern_stats.find_one(
            {"pattern_id": pattern_id, "tenant_id": tenant_id}
        )
        if stats:
            fp_rate = stats.get("fp_count", 0) / max(stats.get("total_count", 1), 1)
            if fp_rate > 0.20 and pattern_id in self.attack_patterns:
                old = self.attack_patterns[pattern_id]["threshold"]
                self.attack_patterns[pattern_id]["threshold"] = old + 1
                logger.warning(
                    "AUTO-TUNE: raised threshold for pattern '%s' from %d → %d (FP rate=%.0f%%)",
                    pattern_id, old, old + 1, fp_rate * 100,
                )
                await self.db.pattern_stats.update_one(
                    {"pattern_id": pattern_id, "tenant_id": tenant_id},
                    {"$set": {"auto_tuned_threshold": old + 1, "tuned_at": now.isoformat()}},
                )

    async def broadcast_ioc(self, tenant_id: str, correlation: Dict[str, Any]) -> None:
        """Broadcast IoCs to all tenant agents after a confirmed attack pattern."""
        pattern_id = correlation.get("pattern_id", "unknown")
        event_ids = correlation.get("event_ids", [])
        broadcast = {
            "tenant_id": tenant_id,
            "pattern_id": pattern_id,
            "severity": correlation.get("severity", "high"),
            "iocs": {
                "source_ip": correlation.get("source_ip"),
                "pattern": correlation.get("pattern"),
                "event_ids": [str(e) for e in event_ids],
            },
            "broadcast_at": datetime.now(timezone.utc).isoformat(),
            "status": "active",
        }
        await self.db.threat_intel_broadcast.insert_one(broadcast)
        logger.info("IOC broadcast created for pattern '%s' in tenant %s", pattern_id, tenant_id)

    async def trigger_threat_hunt(
        self, tenant_id: str, pattern_id: str, correlation: Dict[str, Any]
    ) -> None:
        """Dispatch a threat-hunt scan to every online agent in the tenant."""
        agents = await self.db.agents.find(
            {"tenantId": tenant_id, "status": "Online"}, {"id": 1}
        ).to_list(length=500)
        if not agents:
            return

        now = datetime.now(timezone.utc).isoformat()
        instructions = [
            {
                "agent_id": a["id"],
                "instruction": "run_threat_hunt",
                "payload": {
                    "pattern_id": pattern_id,
                    "iocs": correlation.get("iocs", {}),
                    "source_correlation": str(correlation.get("_id", "")),
                    "triggered_by": "autonomous_threat_hunt",
                },
                "status": "pending",
                "created_at": now,
                "source": "correlation_engine",
            }
            for a in agents
        ]
        if instructions:
            await self.db.agent_instructions.insert_many(instructions)
            logger.info(
                "Threat hunt dispatched to %d agents for pattern '%s'",
                len(instructions), pattern_id,
            )

    async def prestage_kill_chain_defenses(
        self,
        tenant_id: str,
        detected_pattern_id: str,
        agent_id: Optional[str] = None,
    ) -> None:
        """When stage N is confirmed, pre-stage defenses for stage N+1."""
        next_stage_info = self.KILL_CHAIN_NEXT_STAGE.get(detected_pattern_id)
        if not next_stage_info:
            return

        instruction = next_stage_info["instruction"]
        description = next_stage_info["description"]
        next_stage = next_stage_info["next_stage"]

        logger.info(
            "KILL-CHAIN PRE-STAGE: detected '%s' → pre-staging for '%s' (%s)",
            detected_pattern_id, next_stage, instruction,
        )

        if agent_id:
            target_agents = [{"id": agent_id}]
        else:
            target_agents = await self.db.agents.find(
                {"tenantId": tenant_id, "status": "Online"}, {"id": 1}
            ).to_list(length=500)

        now = datetime.now(timezone.utc).isoformat()
        instructions = [
            {
                "agent_id": a["id"],
                "instruction": instruction,
                "payload": {
                    "detected_stage": detected_pattern_id,
                    "next_stage": next_stage,
                    "description": description,
                    "triggered_by": "kill_chain_predictor",
                },
                "status": "pending",
                "created_at": now,
                "source": "correlation_engine",
            }
            for a in target_agents
        ]
        if instructions:
            await self.db.agent_instructions.insert_many(instructions)
            logger.info(
                "Pre-staged %d kill-chain defense instructions for stage '%s'",
                len(instructions), next_stage,
            )

        await self.db.kill_chain_predictions.insert_one({
            "tenant_id": tenant_id,
            "detected_stage": detected_pattern_id,
            "predicted_next_stage": next_stage,
            "instruction_dispatched": instruction,
            "agent_count": len(instructions),
            "predicted_at": now,
        })
