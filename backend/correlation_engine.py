"""
SIEM Correlation Engine

Detects attack patterns and correlates security events using time-based,
entity-based, and MITRE ATT&CK pattern matching.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
from collections import defaultdict
import asyncio

class CorrelationEngine:
    """SIEM Correlation Engine for detecting attack patterns"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        
        # MITRE ATT&CK patterns (simplified for MVP)
        self.attack_patterns = {
            "credential_access": {
                "name": "Credential Access Attempt",
                "events": ["failed_login", "brute_force", "password_spray"],
                "threshold": 5,
                "time_window_minutes": 10
            },
            "lateral_movement": {
                "name": "Lateral Movement",
                "events": ["smb_connection", "rdp_connection", "ssh_connection"],
                "threshold": 3,
                "time_window_minutes": 15
            },
            "data_exfiltration": {
                "name": "Data Exfiltration",
                "events": ["large_upload", "unusual_traffic", "external_connection"],
                "threshold": 2,
                "time_window_minutes": 20
            },
            "privilege_escalation": {
                "name": "Privilege Escalation",
                "events": ["sudo_attempt", "admin_access", "service_creation"],
                "threshold": 3,
                "time_window_minutes": 10
            }
        }
    
    async def correlate_events(
        self,
        tenant_id: str,
        time_window_minutes: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Correlate security events to detect attack patterns
        
        Returns list of detected correlations with confidence scores
        """
        threshold_time = datetime.now(timezone.utc) - timedelta(minutes=time_window_minutes)
        
        # Fetch recent events
        events = await self.db.security_events.find({
            "tenant_id": tenant_id,
            "timestamp": {"$gte": threshold_time.isoformat()}
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
        
        # Store correlations
        for correlation in correlations:
            correlation["tenant_id"] = tenant_id
            correlation["detected_at"] = datetime.now(timezone.utc).isoformat()
            await self.db.correlations.insert_one(correlation)
        
        return correlations
    
    async def _correlate_by_time(self, events: List[Dict]) -> List[Dict]:
        """Correlate events that occur within a short time window"""
        correlations = []
        time_window = timedelta(minutes=5)
        
        # Group events by time buckets
        time_buckets = defaultdict(list)
        for event in events:
            timestamp = datetime.fromisoformat(event["timestamp"].replace('Z', '+00:00'))
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
            # Find events matching this pattern
            matching_events = []
            for event in events:
                event_type = event.get("event_type", "")
                if event_type in pattern["events"]:
                    matching_events.append(event)
            
            # Check if threshold is met
            if len(matching_events) >= pattern["threshold"]:
                # Check time window
                if matching_events:
                    timestamps = [datetime.fromisoformat(e["timestamp"].replace('Z', '+00:00')) for e in matching_events]
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


# Singleton instance
_correlation_engine: Optional[CorrelationEngine] = None

def get_correlation_engine(db: AsyncIOMotorDatabase) -> CorrelationEngine:
    """Get or create correlation engine singleton"""
    global _correlation_engine
    if _correlation_engine is None:
        _correlation_engine = CorrelationEngine(db)
    return _correlation_engine
