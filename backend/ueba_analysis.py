"""
UEBA (User and Entity Behavior Analytics) rule-based analysis engine,
extracted from ueba_service.py (CLAUDE.md 500-line cap — file was 690
lines). Pure detection logic (rules, event models, analyze_login/
analyze_data_access) with no FastAPI router coupling — ueba_service.py
imports and re-exports these names so every existing external import
(`from ueba_service import analyze_login, LoginEvent`,
`from ueba_service import _haversine_km`) keeps working unchanged.
"""
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging

from ueba_alert_persistence_service import _persist_alert

logger = logging.getLogger(__name__)

# ── Risk scoring weights ───────────────────────────────────────────────────────
_RULES = {
    "off_hours_login":           {"weight": 30, "severity": "medium", "desc": "Login outside business hours (00:00–05:00)"},
    "known_malicious_ip":        {"weight": 60, "severity": "high",   "desc": "Login from IP in threat intel feed"},
    "impossible_travel":         {"weight": 80, "severity": "high",   "desc": "Login from two distant locations within 4 hours"},
    "new_country":               {"weight": 40, "severity": "medium", "desc": "Login from a country not seen in last 30 days"},
    "brute_force":               {"weight": 70, "severity": "high",   "desc": "≥5 failed logins in 10 minutes before successful auth"},
    "privilege_escalation":      {"weight": 75, "severity": "high",   "desc": "User accessed resources beyond historical role baseline"},
    "lateral_movement":          {"weight": 65, "severity": "high",   "desc": "Login from a source host not in user's usual set"},
    "mass_download":             {"weight": 55, "severity": "medium", "desc": "Data volume request >10× user's 30-day median"},
    "after_hours_data_access":   {"weight": 45, "severity": "medium", "desc": "Sensitive data accessed outside working hours"},
    "dormant_account":           {"weight": 35, "severity": "low",    "desc": "Account inactive >30 days suddenly active"},
}

# ── Pydantic models ────────────────────────────────────────────────────────────

class LoginEvent(BaseModel):
    user_id: str
    ip_address: str
    user_agent: str = ""
    timestamp: str
    country: Optional[str] = None
    source_host: Optional[str] = None
    login_success: bool = True

class DataAccessEvent(BaseModel):
    user_id: str
    resource: str
    bytes_accessed: int
    timestamp: str
    sensitivity: str = "public"

class ShadowAIEvent(BaseModel):
    agent_id: str
    process: str
    remote_ip: str
    remote_host: str
    timestamp: str

# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_dt(val: str) -> datetime:
    return datetime.fromisoformat(val.replace("Z", "+00:00"))


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Quick approximate distance between two lat/lon points."""
    import math
    R = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── Analysis engine ────────────────────────────────────────────────────────────

async def analyze_login(db, event: LoginEvent) -> Dict[str, Any]:
    """Multi-rule behavioral analysis of a login event."""
    risk_score = 0
    reasons: List[str] = []
    triggered_rules: List[str] = []

    try:
        dt = _parse_dt(event.timestamp)

        # ── Rule 1: Off-hours login ────────────────────────────────────────────
        if 0 <= dt.hour < 5:
            risk_score += _RULES["off_hours_login"]["weight"]
            reasons.append(_RULES["off_hours_login"]["desc"])
            triggered_rules.append("off_hours_login")

        # ── Rule 2: Known malicious IP ─────────────────────────────────────────
        ioc = await db.threat_intel_broadcast.find_one({
            "$or": [
                {"source_ip": event.ip_address},
                {"ioc_type": "ip", "ioc_value": event.ip_address},
            ]
        }, {"severity": 1})
        if ioc:
            risk_score += _RULES["known_malicious_ip"]["weight"]
            reasons.append(f"IP {event.ip_address} is in threat intel feed (severity={ioc.get('severity', '?')})")
            triggered_rules.append("known_malicious_ip")

        # ── Rule 3: Brute force — failed logins before this success ───────────
        if event.login_success:
            ten_min_ago = (dt - timedelta(minutes=10)).isoformat()
            failed_count = await db.login_events.count_documents({
                "user_id": event.user_id,
                "login_success": False,
                "timestamp": {"$gte": ten_min_ago, "$lte": event.timestamp},
            })
            if failed_count >= 5:
                risk_score += _RULES["brute_force"]["weight"]
                reasons.append(f"{failed_count} failed logins in 10 min before success")
                triggered_rules.append("brute_force")

        # ── Rule 4: Impossible travel ──────────────────────────────────────────
        if event.country:
            four_hrs_ago = (dt - timedelta(hours=4)).isoformat()
            recent_login = await db.login_events.find_one(
                {
                    "user_id": event.user_id,
                    "login_success": True,
                    "timestamp": {"$gte": four_hrs_ago, "$lte": event.timestamp},
                    "country": {"$exists": True, "$ne": event.country},
                },
                sort=[("timestamp", -1)],
            )
            if recent_login:
                prev_country = recent_login.get("country", "?")
                # Approximate: any country change within 4h = impossible
                risk_score += _RULES["impossible_travel"]["weight"]
                reasons.append(f"Impossible travel: {prev_country} → {event.country} within 4h")
                triggered_rules.append("impossible_travel")

            # ── Rule 5: New country (not impossible travel, just novel) ────────
            elif not await db.login_events.find_one(
                {"user_id": event.user_id, "country": event.country,
                 "timestamp": {"$gte": (dt - timedelta(days=30)).isoformat()}},
            ):
                risk_score += _RULES["new_country"]["weight"]
                reasons.append(f"Login from new country: {event.country} (no prior 30-day history)")
                triggered_rules.append("new_country")

        # ── Rule 6: Lateral movement — unusual source host ─────────────────────
        if event.source_host:
            known_hosts = await db.login_events.distinct(
                "source_host",
                {"user_id": event.user_id, "timestamp": {"$gte": (dt - timedelta(days=30)).isoformat()}},
            )
            if event.source_host not in (known_hosts or []):
                risk_score += _RULES["lateral_movement"]["weight"]
                reasons.append(f"Login from new source host: {event.source_host}")
                triggered_rules.append("lateral_movement")

        # ── Rule 7: Dormant account ────────────────────────────────────────────
        thirty_days_ago = (dt - timedelta(days=30)).isoformat()
        recent = await db.login_events.find_one(
            {"user_id": event.user_id, "timestamp": {"$gte": thirty_days_ago}},
            sort=[("timestamp", -1)],
        )
        if not recent:
            risk_score += _RULES["dormant_account"]["weight"]
            reasons.append("Account inactive for >30 days")
            triggered_rules.append("dormant_account")

    except Exception as e:
        logger.error("UEBA login analysis error: %s", e)

    # Cap at 100
    risk_score = min(risk_score, 100)

    # ── Auto-ban IP on critical risk from brute force or known malicious IP ──
    _AUTO_BAN_RULES = {"brute_force", "known_malicious_ip"}
    if risk_score >= 80 and _AUTO_BAN_RULES.intersection(triggered_rules):
        try:
            from ip_ban_service import is_banned as _is_banned, ban_ip as _ban_ip
            if not await _is_banned(event.ip_address):
                ban_reason = f"Auto-banned by UEBA: risk_score={risk_score}, rules={triggered_rules}"
                await _ban_ip(
                    ip=event.ip_address,
                    reason=ban_reason,
                    banned_by="ueba_auto",
                    auto=True,
                    expires_hours=24,
                )
                await _persist_alert(
                    db, "ip_auto_ban", "critical",
                    f"IP Auto-Banned: {event.ip_address}",
                    ban_reason,
                    {"ip": event.ip_address, "user_id": event.user_id, "risk_score": risk_score},
                )
        except Exception as _ban_err:
            logger.error("UEBA auto-ban failed (non-fatal): %s", _ban_err)

    result = {
        "user_id": event.user_id,
        "ip_address": event.ip_address,
        "timestamp": event.timestamp,
        "risk_score": risk_score,
        "risk_level": "critical" if risk_score >= 80 else "high" if risk_score >= 60 else "medium" if risk_score >= 30 else "low",
        "reasons": reasons,
        "triggered_rules": triggered_rules,
        "is_anomalous": risk_score >= 30,
        "ip_auto_banned": risk_score >= 80 and bool(_AUTO_BAN_RULES.intersection(triggered_rules)),
    }
    return result


async def analyze_data_access(db, event: DataAccessEvent) -> Dict[str, Any]:
    """Detect mass download and after-hours sensitive data access."""
    risk_score = 0
    reasons: List[str] = []
    triggered_rules: List[str] = []

    try:
        dt = _parse_dt(event.timestamp)

        # ── Rule 8: Mass download — compare to 30-day median ──────────────────
        thirty_ago = (dt - timedelta(days=30)).isoformat()
        history = await db.data_access_events.find(
            {"user_id": event.user_id, "timestamp": {"$gte": thirty_ago}},
            {"bytes_accessed": 1},
        ).to_list(length=500)
        if history:
            volumes = sorted([h["bytes_accessed"] for h in history])
            median = volumes[len(volumes) // 2]
            if median > 0 and event.bytes_accessed > median * 10:
                risk_score += _RULES["mass_download"]["weight"]
                reasons.append(f"Downloaded {event.bytes_accessed:,} bytes — {round(event.bytes_accessed/median)}× over 30-day median ({median:,})")
                triggered_rules.append("mass_download")

        # ── Rule 9: After-hours sensitive data access ──────────────────────────
        if event.sensitivity in ("confidential", "restricted", "top_secret") and not (8 <= dt.hour <= 18):
            risk_score += _RULES["after_hours_data_access"]["weight"]
            reasons.append(f"Sensitive ({event.sensitivity}) resource accessed outside working hours")
            triggered_rules.append("after_hours_data_access")

    except Exception as e:
        logger.error("UEBA data access analysis error: %s", e)

    risk_score = min(risk_score, 100)
    return {
        "user_id": event.user_id,
        "resource": event.resource,
        "timestamp": event.timestamp,
        "risk_score": risk_score,
        "risk_level": "high" if risk_score >= 60 else "medium" if risk_score >= 30 else "low",
        "reasons": reasons,
        "triggered_rules": triggered_rules,
        "is_anomalous": risk_score >= 30,
    }
