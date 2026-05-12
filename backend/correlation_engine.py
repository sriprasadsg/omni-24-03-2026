"""
SIEM Correlation Engine

Detects attack patterns and correlates security events using time-based,
entity-based, and MITRE ATT&CK pattern matching.

After each correlation is stored, the engine automatically searches for
playbooks whose `trigger_type == "correlation"` and whose trigger conditions
match the detected correlation's severity / pattern, then fires those playbooks
in the background — completing the XDR detection-to-response loop.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
from collections import defaultdict
import asyncio
import logging

logger = logging.getLogger(__name__)

_BUILTIN_ATTACK_PATTERNS = {
    "credential_access": {
        "name": "Credential Access Attempt",
        "events": ["failed_login", "brute_force", "password_spray"],
        "threshold": 5,
        "time_window_minutes": 10,
        "mitre": "TA0006",
        "severity": "high",
    },
    "lateral_movement": {
        "name": "Lateral Movement",
        "events": ["smb_connection", "rdp_connection", "ssh_connection"],
        "threshold": 3,
        "time_window_minutes": 15,
        "mitre": "TA0008",
        "severity": "high",
    },
    "data_exfiltration": {
        "name": "Data Exfiltration",
        "events": ["large_upload", "unusual_traffic", "external_connection"],
        "threshold": 2,
        "time_window_minutes": 20,
        "mitre": "TA0010",
        "severity": "critical",
    },
    "privilege_escalation": {
        "name": "Privilege Escalation",
        "events": ["sudo_attempt", "admin_access", "service_creation"],
        "threshold": 3,
        "time_window_minutes": 10,
        "mitre": "TA0004",
        "severity": "high",
    },
    "ransomware": {
        "name": "Ransomware Activity",
        "events": ["file_encryption", "ransomware_detected", "mass_file_rename", "shadow_copy_deletion"],
        "threshold": 1,
        "time_window_minutes": 5,
        "mitre": "T1486",
        "severity": "critical",
    },
    "defense_evasion": {
        "name": "Defense Evasion",
        "events": ["log_cleared", "av_disabled", "firewall_disabled", "process_injection"],
        "threshold": 2,
        "time_window_minutes": 10,
        "mitre": "TA0005",
        "severity": "high",
    },
    "command_and_control": {
        "name": "Command and Control Beacon",
        "events": ["c2_beacon", "dns_tunneling", "periodic_outbound", "unusual_port"],
        "threshold": 3,
        "time_window_minutes": 30,
        "mitre": "TA0011",
        "severity": "critical",
    },
}


class CorrelationEngine:
    """SIEM Correlation Engine for detecting attack patterns."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        # Start with builtins; _load_attack_patterns_from_db() merges DB overrides
        self.attack_patterns: Dict[str, Any] = dict(_BUILTIN_ATTACK_PATTERNS)
        self._patterns_loaded = False
    
    async def _load_attack_patterns_from_db(self) -> None:
        """
        Load / refresh attack pattern definitions from the `signature_library`
        collection.  DB records override the builtin defaults for matching
        pattern_ids; new pattern_ids are added as custom patterns.
        Runs once per process lifetime (self._patterns_loaded guard).
        """
        try:
            cursor = self.db.signature_library.find(
                {"version_type": "attack_pattern", "enabled": {"$ne": False}}
            )
            count = 0
            async for doc in cursor:
                pid = doc.get("pattern_id")
                if not pid:
                    continue
                merged = dict(_BUILTIN_ATTACK_PATTERNS.get(pid, {}))
                for field in ("name", "events", "threshold", "time_window_minutes",
                              "mitre", "severity"):
                    if field in doc:
                        merged[field] = doc[field]
                self.attack_patterns[pid] = merged
                count += 1
            if count:
                logger.info("[CorrelationEngine] Loaded %d attack pattern(s) from DB", count)
            self._patterns_loaded = True
        except Exception as exc:
            logger.warning("[CorrelationEngine] Could not load patterns from DB: %s — using builtins", exc)
            self._patterns_loaded = True  # don't retry every cycle on DB error

    async def correlate_events(
        self,
        tenant_id: str,
        time_window_minutes: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Correlate security events to detect attack patterns.
        Returns list of detected correlations with confidence scores.
        """
        if not self._patterns_loaded:
            await self._load_attack_patterns_from_db()
        threshold_time = datetime.now(timezone.utc) - timedelta(minutes=time_window_minutes)
        
        # Fetch recent events — support both snake_case and camelCase tenant fields
        events = await self.db.security_events.find({
            "$or": [
                {"tenant_id": tenant_id, "$or": [
                    {"timestamp": {"$gte": threshold_time.isoformat()}},
                    {"time": {"$gte": threshold_time.isoformat()}},
                ]},
                {"tenantId": tenant_id, "$or": [
                    {"timestamp": {"$gte": threshold_time.isoformat()}},
                    {"time": {"$gte": threshold_time.isoformat()}},
                ]},
            ]
        }).to_list(length=1000)
        
        correlations = []
        
        # Time-based correlation
        time_correlations = await self._correlate_by_time(events)
        correlations.extend(time_correlations)
        
        # Entity-based correlation (same IP, user, asset)
        entity_correlations = await self._correlate_by_entity(events)
        correlations.extend(entity_correlations)
        
        # MITRE ATT&CK pattern matching
        attack_correlations = await self._detect_attack_patterns(events)
        correlations.extend(attack_correlations)
        
        # Store correlations and trigger matching playbooks
        for correlation in correlations:
            correlation["tenant_id"] = tenant_id
            correlation["detected_at"] = datetime.now(timezone.utc).isoformat()
            await self.db.correlations.insert_one(correlation)
            asyncio.create_task(self._trigger_playbooks(correlation, tenant_id))

        return correlations
    
    async def _correlate_by_time(self, events: List[Dict]) -> List[Dict]:
        """Correlate events that occur within a short time window"""
        correlations = []

        # Group events by time buckets
        time_buckets = defaultdict(list)
        for event in events:
            ts_raw = event.get("timestamp") or event.get("time") or datetime.now(timezone.utc).isoformat()
            try:
                timestamp = datetime.fromisoformat(ts_raw.replace('Z', '+00:00'))
            except Exception:
                continue
            bucket_key = timestamp.replace(minute=timestamp.minute // 5 * 5, second=0, microsecond=0)
            time_buckets[bucket_key].append(event)
        
        # Find buckets with multiple events
        for bucket_time, bucket_events in time_buckets.items():
            if len(bucket_events) >= 3:
                correlations.append({
                    "type": "time_based",
                    "pattern": "Multiple events in short timeframe",
                    "event_count": len(bucket_events),
                    "event_ids": [e.get("_id") for e in bucket_events],
                    "time_window": bucket_time.isoformat(),
                    "confidence": min(len(bucket_events) * 0.2, 1.0),
                    "severity": "medium" if len(bucket_events) < 5 else "high"
                })
        
        return correlations
    
    async def _correlate_by_entity(self, events: List[Dict]) -> List[Dict]:
        """Correlate events by common entities (IP, user, asset)"""
        correlations = []
        
        # Group by source IP
        ip_events = defaultdict(list)
        for event in events:
            if "source_ip" in event:
                ip_events[event["source_ip"]].append(event)
        
        for ip, ip_event_list in ip_events.items():
            if len(ip_event_list) >= 5:
                # Check for diverse event types
                event_types = set(e.get("event_type", "unknown") for e in ip_event_list)
                if len(event_types) >= 3:
                    correlations.append({
                        "type": "entity_based",
                        "entity_type": "ip",
                        "entity_value": ip,
                        "pattern": f"Multiple diverse events from same IP",
                        "event_count": len(ip_event_list),
                        "event_types": list(event_types),
                        "event_ids": [e.get("_id") for e in ip_event_list],
                        "confidence": min(len(event_types) * 0.25, 1.0),
                        "severity": "high"
                    })
        
        # Group by user
        user_events = defaultdict(list)
        for event in events:
            if "user" in event:
                user_events[event["user"]].append(event)
        
        for user, user_event_list in user_events.items():
            if len(user_event_list) >= 4:
                correlations.append({
                    "type": "entity_based",
                    "entity_type": "user",
                    "entity_value": user,
                    "pattern": f"Multiple events from same user",
                    "event_count": len(user_event_list),
                    "event_ids": [e.get("_id") for e in user_event_list],
                    "confidence": min(len(user_event_list) * 0.15, 1.0),
                    "severity": "medium"
                })
        
        return correlations
    
    async def _detect_attack_patterns(self, events: List[Dict]) -> List[Dict]:
        """Detect MITRE ATT&CK patterns in events"""
        correlations = []
        
        for pattern_id, pattern in self.attack_patterns.items():
            # Find events matching this pattern — check multiple possible field names
            matching_events = []
            for event in events:
                event_type = (
                    event.get("event_type")
                    or event.get("activity_name")
                    or event.get("category_name")
                    or event.get("class_name")
                    or event.get("type")
                    or ""
                ).lower().replace(" ", "_")
                if event_type in pattern["events"] or any(p in event_type for p in pattern["events"]):
                    matching_events.append(event)
            
            # Check if threshold is met
            if len(matching_events) >= pattern["threshold"]:
                # Check time window
                if matching_events:
                    timestamps = []
                    for e in matching_events:
                        ts_raw = e.get("timestamp") or e.get("time") or datetime.now(timezone.utc).isoformat()
                        try:
                            timestamps.append(datetime.fromisoformat(ts_raw.replace('Z', '+00:00')))
                        except Exception:
                            pass
                    if not timestamps:
                        continue
                    time_span = max(timestamps) - min(timestamps)
                    
                    if time_span <= timedelta(minutes=pattern["time_window_minutes"]):
                        correlations.append({
                            "type": "attack_pattern",
                            "pattern_id": pattern_id,
                            "pattern": pattern["name"],
                            "event_count": len(matching_events),
                            "event_ids": [e.get("_id") for e in matching_events],
                            "time_span_minutes": time_span.total_seconds() / 60,
                            "confidence": min((len(matching_events) / pattern["threshold"]) * 0.8, 1.0),
                            "severity": "critical",
                            "mitre_attack": pattern_id
                        })
        
        return correlations
    
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
            playbooks = await self.db.playbooks.find(query, {"id": 1, "name": 1,
                                                              "trigger_conditions": 1}).to_list(length=50)

            severity = correlation.get("severity", "")
            pattern_id = correlation.get("pattern_id", "")

            for pb in playbooks:
                tc = pb.get("trigger_conditions") or {}

                # Severity filter (empty list = match all)
                allowed_severities = tc.get("severity", [])
                if allowed_severities and severity not in allowed_severities:
                    continue

                # Pattern filter (empty list = match all)
                allowed_patterns = tc.get("pattern_ids", [])
                if allowed_patterns and pattern_id not in allowed_patterns:
                    continue

                # Lazy import to avoid circular dependencies at module load
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
            # Phase 3-1: AI-driven playbook selection (runs in background, non-blocking)
            asyncio.create_task(self._ai_select_playbook(tenant_id, correlation))

            # Phase 4-1: Broadcast IoCs to all tenant agents
            asyncio.create_task(self.broadcast_ioc(tenant_id, correlation))

            # Phase 4-2: Autonomous threat hunt across all online agents
            asyncio.create_task(
                self.trigger_threat_hunt(tenant_id, pattern_id, correlation)
            )

            # Phase 4-3: Pre-stage kill-chain defenses for next likely stage
            agent_id = correlation.get("agent_id")
            asyncio.create_task(
                self.prestage_kill_chain_defenses(tenant_id, pattern_id, agent_id)
            )

            # Phase 3-2: Auto-create a security case for critical/high correlations
            asyncio.create_task(
                self._auto_create_security_case(tenant_id, correlation)
            )

        except Exception as exc:
            logger.error("Playbook trigger failed for correlation %s: %s",
                         correlation.get("pattern_id"), exc)

    async def run_periodic_correlation(
        self,
        tenant_id: str,
        interval_seconds: int = 300,
        time_window_minutes: int = 60,
    ) -> None:
        """
        Background loop: run correlate_events() every `interval_seconds`.
        Launched from app.py lifespan for each active tenant.
        """
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
        severity: Optional[str] = None
    ) -> List[Dict]:
        """Get recent correlations for a tenant"""
        query = {"tenant_id": tenant_id}
        if severity:
            query["severity"] = severity
        
        cursor = self.db.correlations.find(query).sort("detected_at", -1).limit(limit)
        correlations = []
        
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            correlations.append(doc)
        
        return correlations
    
    async def get_correlation_stats(self, tenant_id: str) -> Dict[str, Any]:
        """Get correlation statistics"""
        pipeline = [
            {"$match": {"tenant_id": tenant_id}},
            {
                "$group": {
                    "_id": "$severity",
                    "count": {"$sum": 1}
                }
            }
        ]
        
        cursor = self.db.correlations.aggregate(pipeline)
        severity_counts = {}
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
            "low_count": severity_counts.get("low", 0)
        }

    # ------------------------------------------------------------------
    # Phase 3-1: AI-driven playbook selection after correlation
    # ------------------------------------------------------------------

    async def _ai_select_playbook(
        self, tenant_id: str, correlation: Dict[str, Any]
    ) -> None:
        """
        Ask the AI service to suggest the best matching playbook for a
        correlation, then trigger it. Falls back silently if AI unavailable.
        """
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
            suggestion = (await analyzer.generate_text(prompt, source="correlation")).strip().lower()
            action_map = {
                "isolate": "isolate_endpoint",
                "block": "block_ip",
                "quarantine": "quarantine_file",
                "notify": "send_notification",
            }
            action = next((v for k, v in action_map.items() if k in suggestion), None)
            if not action:
                return

            # Find a playbook that executes this action
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

    # ------------------------------------------------------------------
    # Phase 3-2: Auto-create security case for critical/high correlations
    # ------------------------------------------------------------------

    async def _auto_create_security_case(
        self, tenant_id: str, correlation: Dict[str, Any]
    ) -> None:
        """
        Automatically open a security case when a critical or high-severity
        correlation is confirmed, so the SOC has a trackable record.
        """
        severity = correlation.get("severity", "")
        if severity not in ("critical", "high"):
            return

        pattern_id = correlation.get("pattern_id", "unknown")
        now = datetime.now(timezone.utc).isoformat()

        # Avoid duplicate cases for the same pattern within 1 hour
        one_hour_ago = (
            datetime.now(timezone.utc) - timedelta(hours=1)
        ).isoformat()
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

    # ------------------------------------------------------------------
    # Phase 2-2: Self-tuning thresholds via false-positive feedback
    # ------------------------------------------------------------------

    async def record_false_positive(
        self, pattern_id: str, tenant_id: str
    ) -> None:
        """
        Increment the false-positive counter for a pattern.
        When the FP rate over the last 7 days exceeds 20 %, the threshold
        for that pattern is raised by 1 to reduce noise.
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
                    "AUTO-TUNE: raised threshold for pattern '%s' from %d → %d "
                    "(FP rate=%.0f%%)",
                    pattern_id, old, old + 1, fp_rate * 100,
                )
                await self.db.pattern_stats.update_one(
                    {"pattern_id": pattern_id, "tenant_id": tenant_id},
                    {"$set": {"auto_tuned_threshold": old + 1, "tuned_at": now.isoformat()}},
                )

    # ------------------------------------------------------------------
    # Phase 4-1: Cross-agent IoC broadcast
    # ------------------------------------------------------------------

    async def broadcast_ioc(
        self, tenant_id: str, correlation: Dict[str, Any]
    ) -> None:
        """
        After a confirmed attack pattern, broadcast IoCs (IPs, hashes,
        behaviours) to all agents in the tenant via threat_intel_broadcast
        so each agent can pre-screen for the same indicators.
        """
        source_ip = correlation.get("source_ip")
        pattern_id = correlation.get("pattern_id", "unknown")
        event_ids = correlation.get("event_ids", [])

        broadcast = {
            "tenant_id": tenant_id,
            "pattern_id": pattern_id,
            "severity": correlation.get("severity", "high"),
            "iocs": {
                "source_ip": source_ip,
                "pattern": correlation.get("pattern"),
                "event_ids": [str(e) for e in event_ids],
            },
            "broadcast_at": datetime.now(timezone.utc).isoformat(),
            "status": "active",
        }
        await self.db.threat_intel_broadcast.insert_one(broadcast)
        logger.info(
            "IOC broadcast created for pattern '%s' in tenant %s", pattern_id, tenant_id
        )

    # ------------------------------------------------------------------
    # Phase 4-2: Autonomous threat hunting across all tenant agents
    # ------------------------------------------------------------------

    async def trigger_threat_hunt(
        self, tenant_id: str, pattern_id: str, correlation: Dict[str, Any]
    ) -> None:
        """
        Dispatch a threat-hunt scan instruction to every online agent
        in the tenant, targeting the confirmed attack pattern's IoCs.
        """
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

    # ------------------------------------------------------------------
    # Phase 4-3: Predictive kill-chain pre-staging (MITRE ATT&CK)
    # ------------------------------------------------------------------

    # Maps detected stage → next likely stage + recommended pre-staging action
    KILL_CHAIN_NEXT_STAGE: Dict[str, Dict[str, Any]] = {
        "credential_access": {
            "next_stage": "lateral_movement",
            "instruction": "enable_enhanced_auth_logging",
            "description": "Credential access detected — pre-staging enhanced auth logging "
                           "to catch lateral movement attempts early.",
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

    async def prestage_kill_chain_defenses(
        self, tenant_id: str, detected_pattern_id: str, agent_id: Optional[str] = None
    ) -> None:
        """
        When stage N is confirmed, pre-stage defenses for stage N+1
        by dispatching the appropriate instruction to affected agents.
        """
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

        # Target the specific agent if known, otherwise all online agents
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

        # Record the prediction for observability
        await self.db.kill_chain_predictions.insert_one({
            "tenant_id": tenant_id,
            "detected_stage": detected_pattern_id,
            "predicted_next_stage": next_stage,
            "instruction_dispatched": instruction,
            "agent_count": len(instructions),
            "predicted_at": now,
        })


# Singleton instance
_correlation_engine: Optional[CorrelationEngine] = None

def get_correlation_engine(db: AsyncIOMotorDatabase) -> CorrelationEngine:
    """Get or create correlation engine singleton"""
    global _correlation_engine
    if _correlation_engine is None:
        _correlation_engine = CorrelationEngine(db)
    return _correlation_engine
