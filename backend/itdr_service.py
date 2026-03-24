"""
ITDR — Identity Threat Detection & Response Service
Detects:
  - Impossible travel (same user logging in from 2 countries in < 1hr)
  - Brute-force / credential stuffing (> 5 failed logins in 60s)
  - After-hours privilege escalation (role changed outside 08:00–20:00)
  - Concurrent session anomalies (same user from >3 IPs simultaneously)

Called from authentication_endpoints.py on each login and role-change event.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from database import get_database

logger = logging.getLogger(__name__)

# Thresholds
BRUTE_FORCE_WINDOW_SECONDS = 60
BRUTE_FORCE_THRESHOLD = 5
IMPOSSIBLE_TRAVEL_HOURS = 1
BUSINESS_HOURS_START = 8    # 08:00
BUSINESS_HOURS_END = 20     # 20:00
MAX_CONCURRENT_IPS = 3


class ITDRService:
    """
    Identity Threat Detection & Response.
    Each method returns a (threat_detected: bool, alert: dict | None) tuple.
    """

    async def on_login_failure(self, email: str, ip_address: str) -> Optional[Dict]:
        """Record a login failure and check for brute-force."""
        db = get_database()
        now = datetime.now(timezone.utc)
        doc = {
            "email": email,
            "ip": ip_address,
            "type": "login_failure",
            "timestamp": now.isoformat(),
        }
        await db.itdr_login_events.insert_one(doc)

        # Brute-force check
        since = (now - timedelta(seconds=BRUTE_FORCE_WINDOW_SECONDS)).isoformat()
        count = await db.itdr_login_events.count_documents({
            "email": email,
            "type": "login_failure",
            "timestamp": {"$gte": since},
        })

        if count >= BRUTE_FORCE_THRESHOLD:
            alert = await self._create_alert(
                alert_type="BRUTE_FORCE_DETECTED",
                description=f"Brute-force attack detected: {count} failed logins for '{email}' in {BRUTE_FORCE_WINDOW_SECONDS}s from {ip_address}",
                severity="critical",
                metadata={"email": email, "ip": ip_address, "attempts": count},
            )
            return alert
        return None

    async def on_login_success(self, email: str, ip_address: str, country: Optional[str] = None) -> Optional[Dict]:
        """Record a successful login and check for impossible travel."""
        db = get_database()
        now = datetime.now(timezone.utc)
        doc = {
            "email": email,
            "ip": ip_address,
            "country": country,
            "type": "login_success",
            "timestamp": now.isoformat(),
        }
        await db.itdr_login_events.insert_one(doc)

        # Impossible travel check
        if country:
            since = (now - timedelta(hours=IMPOSSIBLE_TRAVEL_HOURS)).isoformat()
            prev_logins = await db.itdr_login_events.find(
                {
                    "email": email,
                    "type": "login_success",
                    "timestamp": {"$gte": since},
                    "country": {"$ne": country, "$exists": True},
                },
                {"_id": 0, "country": 1, "ip": 1, "timestamp": 1}
            ).limit(1).to_list(length=1)

            if prev_logins:
                prev = prev_logins[0]
                alert = await self._create_alert(
                    alert_type="IMPOSSIBLE_TRAVEL",
                    description=f"Impossible travel: '{email}' logged in from {country} ({ip_address}) within {IMPOSSIBLE_TRAVEL_HOURS}h of login from {prev['country']} ({prev['ip']})",
                    severity="high",
                    metadata={"email": email, "new_country": country, "new_ip": ip_address,
                              "prev_country": prev["country"], "prev_ip": prev["ip"]},
                )
                return alert

        # Concurrent session anomaly
        since_10min = (now - timedelta(minutes=10)).isoformat()
        recent_ips = await db.itdr_login_events.distinct(
            "ip",
            {"email": email, "type": "login_success", "timestamp": {"$gte": since_10min}}
        )
        if len(recent_ips) > MAX_CONCURRENT_IPS:
            alert = await self._create_alert(
                alert_type="CONCURRENT_SESSION_ANOMALY",
                description=f"User '{email}' is actively logged in from {len(recent_ips)} different IPs simultaneously",
                severity="medium",
                metadata={"email": email, "ips": recent_ips},
            )
            return alert

        return None

    async def on_role_change(self, email: str, old_role: str, new_role: str,
                              changed_by: str) -> Optional[Dict]:
        """Check for after-hours privilege escalation."""
        now = datetime.now(timezone.utc)
        current_hour = now.hour

        # Check if elevated role
        elevated_roles = {"Super Admin", "superadmin", "admin", "Admin"}
        is_escalation = new_role in elevated_roles and old_role not in elevated_roles

        if is_escalation and not (BUSINESS_HOURS_START <= current_hour < BUSINESS_HOURS_END):
            alert = await self._create_alert(
                alert_type="AFTER_HOURS_PRIVILEGE_ESCALATION",
                description=f"Privilege escalation for '{email}' ({old_role} → {new_role}) detected outside business hours at {now.strftime('%H:%M UTC')}",
                severity="high",
                metadata={"email": email, "old_role": old_role, "new_role": new_role,
                          "changed_by": changed_by, "hour_utc": current_hour},
            )
            return alert
        return None

    async def get_alerts(self, limit: int = 100, unack_only: bool = False) -> List[Dict]:
        """Retrieve ITDR alerts."""
        db = get_database()
        query: Dict = {}
        if unack_only:
            query["acknowledged"] = False
        alerts = await db.itdr_alerts.find(
            query, {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(length=limit)
        return alerts

    async def acknowledge_alert(self, alert_id: str, by: str) -> bool:
        db = get_database()
        result = await db.itdr_alerts.update_one(
            {"alert_id": alert_id},
            {"$set": {"acknowledged": True, "acknowledged_by": by,
                      "acknowledged_at": datetime.now(timezone.utc).isoformat()}}
        )
        return result.matched_count > 0

    # ------------------------------------------------------------------

    async def _create_alert(self, alert_type: str, description: str,
                             severity: str, metadata: Dict) -> Dict:
        import uuid
        db = get_database()
        alert = {
            "alert_id": f"ITDR-{uuid.uuid4().hex[:12]}",
            "type": alert_type,
            "description": description,
            "severity": severity,
            "metadata": metadata,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "acknowledged": False,
        }
        await db.itdr_alerts.insert_one(alert)
        alert.pop("_id", None)
        logger.warning(f"[ITDR] {severity.upper()} — {alert_type}: {description}")
        return alert


# Module-level singleton
itdr_service = ITDRService()
