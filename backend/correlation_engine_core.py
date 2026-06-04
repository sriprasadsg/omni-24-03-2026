"""
CorrelationEngine core: initialization, event loading, and pattern detection.
"""

from typing import List, Dict, Any
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


class CorrelationEngineCoreMixin:
    """Core event correlation and pattern detection."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.attack_patterns: Dict[str, Any] = dict(_BUILTIN_ATTACK_PATTERNS)
        self._patterns_loaded = False

    async def _load_attack_patterns_from_db(self) -> None:
        """Load / refresh attack pattern definitions from the signature_library collection."""
        try:
            # Only load platform-level patterns (no tenantId or tenantId=platform-admin).
            # Tenant-scoped patterns would allow a malicious tenant to inject signatures
            # that fire against every other tenant's events.
            cursor = self.db.signature_library.find(
                {
                    "version_type": "attack_pattern",
                    "enabled": {"$ne": False},
                    "$or": [
                        {"tenantId": {"$exists": False}},
                        {"tenantId": None},
                        {"tenantId": "platform-admin"},
                    ],
                }
            )
            count = 0
            async for doc in cursor:
                pid = doc.get("pattern_id")
                if not pid:
                    continue
                merged = dict(_BUILTIN_ATTACK_PATTERNS.get(pid, {}))
                for field in ("name", "events", "threshold", "time_window_minutes", "mitre", "severity"):
                    if field in doc:
                        merged[field] = doc[field]
                self.attack_patterns[pid] = merged
                count += 1
            if count:
                logger.info("[CorrelationEngine] Loaded %d attack pattern(s) from DB", count)
            self._patterns_loaded = True
        except Exception as exc:
            logger.warning("[CorrelationEngine] Could not load patterns from DB: %s — using builtins", exc)
            self._patterns_loaded = True

    async def correlate_events(
        self,
        tenant_id: str,
        time_window_minutes: int = 60,
    ) -> List[Dict[str, Any]]:
        """Correlate security events to detect attack patterns."""
        if not self._patterns_loaded:
            await self._load_attack_patterns_from_db()
        threshold_time = datetime.now(timezone.utc) - timedelta(minutes=time_window_minutes)

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
        }).to_list(length=5000)
        if len(events) == 5000:
            logger.warning(
                "[CorrelationEngine] Event query for tenant %s hit the 5000-event cap — "
                "some events may have been excluded from this correlation cycle.",
                tenant_id,
            )

        correlations = []
        correlations.extend(await self._correlate_by_time(events))
        correlations.extend(await self._correlate_by_entity(events))
        correlations.extend(await self._detect_attack_patterns(events))

        for correlation in correlations:
            correlation["tenant_id"] = tenant_id
            correlation["detected_at"] = datetime.now(timezone.utc).isoformat()
            await self.db.correlations.insert_one(correlation)
            asyncio.create_task(self._trigger_playbooks(correlation, tenant_id))

        return correlations

    async def _correlate_by_time(self, events: List[Dict]) -> List[Dict]:
        """Correlate events that occur within a short time window."""
        correlations = []
        time_buckets: Dict = defaultdict(list)
        for event in events:
            ts_raw = event.get("timestamp") or event.get("time") or datetime.now(timezone.utc).isoformat()
            try:
                timestamp = datetime.fromisoformat(ts_raw.replace('Z', '+00:00'))
            except Exception as e:
                logger.debug("Unparseable event timestamp, skipping: %s", e)
                continue
            bucket_key = timestamp.replace(minute=timestamp.minute // 5 * 5, second=0, microsecond=0)
            time_buckets[bucket_key].append(event)

        for bucket_time, bucket_events in time_buckets.items():
            if len(bucket_events) >= 3:
                correlations.append({
                    "type": "time_based",
                    "pattern": "Multiple events in short timeframe",
                    "event_count": len(bucket_events),
                    "event_ids": [e.get("_id") for e in bucket_events],
                    "time_window": bucket_time.isoformat(),
                    "confidence": min(len(bucket_events) * 0.2, 1.0),
                    "severity": "medium" if len(bucket_events) < 5 else "high",
                })
        return correlations

    async def _correlate_by_entity(self, events: List[Dict]) -> List[Dict]:
        """Correlate events by common entities (IP, user, asset)."""
        correlations = []
        ip_events: Dict = defaultdict(list)
        for event in events:
            if "source_ip" in event:
                ip_events[event["source_ip"]].append(event)

        for ip, ip_event_list in ip_events.items():
            if len(ip_event_list) >= 5:
                event_types = set(e.get("event_type", "unknown") for e in ip_event_list)
                if len(event_types) >= 3:
                    correlations.append({
                        "type": "entity_based", "entity_type": "ip", "entity_value": ip,
                        "pattern": "Multiple diverse events from same IP",
                        "event_count": len(ip_event_list), "event_types": list(event_types),
                        "event_ids": [e.get("_id") for e in ip_event_list],
                        "confidence": min(len(event_types) * 0.25, 1.0), "severity": "high",
                    })

        user_events: Dict = defaultdict(list)
        for event in events:
            if "user" in event:
                user_events[event["user"]].append(event)

        for user, user_event_list in user_events.items():
            if len(user_event_list) >= 4:
                correlations.append({
                    "type": "entity_based", "entity_type": "user", "entity_value": user,
                    "pattern": "Multiple events from same user",
                    "event_count": len(user_event_list),
                    "event_ids": [e.get("_id") for e in user_event_list],
                    "confidence": min(len(user_event_list) * 0.15, 1.0), "severity": "medium",
                })
        return correlations

    async def _detect_attack_patterns(self, events: List[Dict]) -> List[Dict]:
        """Detect MITRE ATT&CK patterns in events."""
        correlations = []
        for pattern_id, pattern in self.attack_patterns.items():
            matching_events = []
            for event in events:
                event_type = (
                    event.get("event_type") or event.get("activity_name")
                    or event.get("category_name") or event.get("class_name")
                    or event.get("type") or ""
                ).lower().replace(" ", "_")
                if event_type in pattern["events"] or any(p in event_type for p in pattern["events"]):
                    matching_events.append(event)

            if len(matching_events) >= pattern["threshold"] and matching_events:
                timestamps = []
                for e in matching_events:
                    ts_raw = e.get("timestamp") or e.get("time") or datetime.now(timezone.utc).isoformat()
                    try:
                        timestamps.append(datetime.fromisoformat(ts_raw.replace('Z', '+00:00')))
                    except Exception as e:
                        logger.debug("Unparseable pattern-match timestamp: %s", e)
                if not timestamps:
                    continue
                time_span = max(timestamps) - min(timestamps)
                if time_span <= timedelta(minutes=pattern["time_window_minutes"]):
                    correlations.append({
                        "type": "attack_pattern", "pattern_id": pattern_id,
                        "pattern": pattern["name"],
                        "event_count": len(matching_events),
                        "event_ids": [e.get("_id") for e in matching_events],
                        "time_span_minutes": time_span.total_seconds() / 60,
                        "confidence": min((len(matching_events) / pattern["threshold"]) * 0.8, 1.0),
                        "severity": "critical", "mitre_attack": pattern_id,
                    })
        return correlations
