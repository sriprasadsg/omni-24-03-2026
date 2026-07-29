"""
UEBA (User and Entity Behavior Analytics) Service
Detects behavioral anomalies through multi-rule analysis.
"""
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
import logging
from database import get_database
from authentication_service import get_current_user

router = APIRouter(prefix="/api/ueba", tags=["UEBA"])
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

# ── Helper ─────────────────────────────────────────────────────────────────────

async def _persist_alert(db, alert_type: str, severity: str, title: str, description: str, metadata: Dict[str, Any]):
    now = datetime.now(timezone.utc).isoformat()
    alert = {
        "type": alert_type,
        "severity": severity,
        "title": title,
        "description": description,
        "metadata": metadata,
        "created_at": now,
        "status": "new",
        "timestamp": now,
    }
    await db.security_alerts.insert_one(alert)

    # Publish to streaming broker so the Streaming Dashboard receives live events
    try:
        from streaming_service import broker as _broker
        _alert_copy = {k: v for k, v in alert.items() if k != "_id"}
        import asyncio as _asyncio
        _asyncio.create_task(_broker.publish("security_events", _alert_copy))
    except Exception as e:
        logger.debug("Security event streaming publish failed (non-fatal): %s", e)

    # Append an immutable blockchain audit block for this security event
    try:
        import hashlib as _hl
        import json as _json
        last_block = await db.blockchain_audit.find_one(
            {}, {"_id": 0, "blockNumber": 1, "hash": 1}, sort=[("blockNumber", -1)]
        )
        prev_num = last_block["blockNumber"] if last_block else 0
        prev_hash = last_block["hash"] if last_block else "0" * 64
        block_data = {
            "blockNumber": prev_num + 1,
            "previousHash": prev_hash,
            "timestamp": now,
            "eventType": alert_type,
            "severity": severity,
            "title": title,
        }
        block_data["hash"] = _hl.sha256(
            _json.dumps(block_data, sort_keys=True).encode()
        ).hexdigest()
        await db.blockchain_audit.insert_one(block_data)
    except Exception as e:
        logger.debug("Blockchain audit block write failed (non-fatal): %s", e)


# Public alias — five existing heartbeat call sites (shadow_ai, ueba_anomaly,
# fim_violation, pii_detected, runtime_security in agent_heartbeat_endpoints.py
# / agent_heartbeat_alerts_service.py) already do
# `from ueba_service import persist_security_alert` wrapped in
# `try/except ImportError: pass`. That name never existed until now, so all
# five silently no-op'd (47-RESEARCH.md Pitfall 1). Do NOT rename
# `_persist_alert` — its 4 internal call sites (above, and in analyze_login/
# report_shadow_ai/analyze_data_access) reference the private name directly.
# This is the ONLY alert-persistence path; never add a second one.
persist_security_alert = _persist_alert


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


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/shadow-ai")
async def report_shadow_ai(event: ShadowAIEvent, background_tasks: BackgroundTasks, db=Depends(get_database)):
    """Ingest Shadow AI detection events from agents."""
    logger.warning("Shadow AI Detected: %s -> %s on %s", event.process, event.remote_host, event.agent_id)
    await db.shadow_ai_events.insert_one(event.dict())
    background_tasks.add_task(
        _persist_alert, db, "shadow_ai", "medium",
        f"Shadow AI Usage Detected: {event.remote_host}",
        f"Process '{event.process}' on agent {event.agent_id} connected to {event.remote_host}.",
        event.dict(),
    )
    return {"status": "recorded"}


@router.post("/analyze")
async def analyze_event(
    body: Dict[str, Any],
    background_tasks: BackgroundTasks,
    db=Depends(get_database),
    current_user=Depends(get_current_user),
):
    """
    Unified UEBA analyze endpoint.
    Routes to analyze_login or analyze_data_access based on event_type.
    Returns { risk_score, flags, recommendations, is_anomalous }.
    Requires authentication — unauthenticated callers cannot trigger auto-ban.
    """
    now = datetime.now(timezone.utc).isoformat()
    event_type = body.get("event_type", "login")

    if event_type == "api_call":
        # Check for Shadow AI — calls to known AI provider endpoints/IPs
        _SHADOW_AI_PROVIDERS = {
            "openai.com", "api.openai.com",
            "generativelanguage.googleapis.com", "gemini.google.com",
            "anthropic.com", "api.anthropic.com",
            "huggingface.co", "api-inference.huggingface.co",
            "cohere.ai", "api.cohere.ai",
            "api.mistral.ai",
        }
        endpoint = body.get("endpoint", "") or body.get("ip_address", "")
        is_shadow_ai = any(provider in str(endpoint).lower() for provider in _SHADOW_AI_PROVIDERS)

        base_event = LoginEvent(
            user_id=body.get("user_id", "unknown"),
            ip_address=body.get("ip_address", "0.0.0.0"),
            user_agent=body.get("user_agent", ""),
            timestamp=body.get("timestamp", now),
        )
        result = await analyze_login(db, base_event)

        if is_shadow_ai:
            result["triggered_rules"] = list(result.get("triggered_rules", [])) + ["shadow_ai_detected"]
            result["risk_score"] = min(100, result.get("risk_score", 0) + 60)
            result["is_anomalous"] = True
            result.setdefault("recommendations", []).append(
                "Unauthorized AI service access detected. Review and enforce AI usage policy."
            )

    elif event_type == "login":
        event = LoginEvent(
            user_id=body.get("user_id", "unknown"),
            ip_address=body.get("ip_address", "0.0.0.0"),
            user_agent=body.get("user_agent", ""),
            timestamp=body.get("timestamp", now),
            country=body.get("country"),
            source_host=body.get("source_host"),
            login_success=body.get("login_success", True),
        )
        result = await analyze_login(db, event)
    elif event_type == "data_access":
        event = DataAccessEvent(
            user_id=body.get("user_id", "unknown"),
            resource=body.get("resource", "unknown"),
            bytes_accessed=int(body.get("bytes_accessed", 0)),
            timestamp=body.get("timestamp", now),
            sensitivity=body.get("sensitivity", "public"),
        )
        result = await analyze_data_access(db, event)
    else:
        # Generic risk scoring for unknown event types
        risk_score = 10
        flags: list[str] = []
        if body.get("ip_address"):
            ioc = await db.edr_ioc.find_one(
                {"$or": [{"value": body["ip_address"]}, {"source_ip": body["ip_address"]}]}
            )
            if ioc:
                flags.append("ioc_match")
                risk_score += 50
        result = {
            "risk_score": risk_score,
            "flags": flags,
            "recommendations": ["Monitor this user's activity" if risk_score > 30 else "No action required"],
            "is_anomalous": risk_score >= 50,
            "triggered_rules": flags,
        }

    # Normalise to the expected response shape
    return {
        "risk_score": result.get("risk_score", 0),
        "flags": result.get("triggered_rules", result.get("flags", [])),
        "recommendations": result.get("recommendations", []),
        "is_anomalous": result.get("is_anomalous", False),
    }


@router.post("/analyze-login")
async def analyze_login_behavior(event: LoginEvent, background_tasks: BackgroundTasks, db=Depends(get_database)):
    """Multi-rule behavioral analysis of a login event."""
    result = await analyze_login(db, event)

    # Persist the event for future baseline analysis
    await db.login_events.insert_one({**event.dict(), "analysis": result})

    if result["is_anomalous"]:
        logger.warning("Anomalous login: user=%s score=%s rules=%s", event.user_id, result["risk_score"], result["triggered_rules"])
        background_tasks.add_task(
            _persist_alert, db, "ueba_anomaly",
            "critical" if result["risk_score"] >= 80 else "high" if result["risk_score"] >= 60 else "medium",
            f"Anomalous Login: {event.user_id}",
            f"Risk score {result['risk_score']}/100. Triggered: {', '.join(result['triggered_rules'])}",
            {**event.dict(), "analysis": result},
        )

    return result


@router.post("/analyze-data-access")
async def analyze_data_access_endpoint(event: DataAccessEvent, background_tasks: BackgroundTasks, db=Depends(get_database)):
    """Analyze a data access event for exfiltration patterns."""
    result = await analyze_data_access(db, event)

    await db.data_access_events.insert_one({**event.dict(), "analysis": result})

    if result["is_anomalous"]:
        background_tasks.add_task(
            _persist_alert, db, "ueba_data_exfil",
            result["risk_level"],
            f"Suspected Data Exfiltration: {event.user_id}",
            "; ".join(result["reasons"]),
            {**event.dict(), "analysis": result},
        )

    return result


@router.get("/shadow-ai/events")
async def get_shadow_ai_events(limit: int = 50, db=Depends(get_database)):
    cursor = db.shadow_ai_events.find().sort("timestamp", -1).limit(limit)
    events = await cursor.to_list(length=limit)
    for e in events:
        e["id"] = str(e.pop("_id"))
    return events


@router.get("/anomalies")
async def list_anomalies(limit: int = 100, user_id: Optional[str] = None, db=Depends(get_database)):
    """Return recent UEBA anomalies from login and data access events."""
    query: Dict[str, Any] = {"analysis.is_anomalous": True}
    if user_id:
        query["user_id"] = user_id

    login_cursor = db.login_events.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit // 2)
    data_cursor  = db.data_access_events.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit // 2)

    login_anom = await login_cursor.to_list(length=limit // 2)
    data_anom  = await data_cursor.to_list(length=limit // 2)

    combined = sorted(login_anom + data_anom, key=lambda x: x.get("timestamp", ""), reverse=True)[:limit]
    return {"anomalies": combined, "total": len(combined)}


@router.get("/stats")
async def get_ueba_stats(db=Depends(get_database)):
    shadow_count  = await db.shadow_ai_events.count_documents({})
    anomaly_count = await db.security_alerts.count_documents({"type": {"$in": ["ueba_anomaly", "ueba_data_exfil"]}})
    high_risk     = await db.login_events.count_documents({"analysis.risk_level": "critical"})
    total_logins  = await db.login_events.count_documents({})
    return {
        "shadow_ai_detections": shadow_count,
        "login_anomalies": anomaly_count,
        "critical_risk_logins": high_risk,
        "total_login_events_analyzed": total_logins,
        "rules_active": len(_RULES),
    }


_UEBA_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}


@router.get("/risk-scores")
async def get_user_risk_scores(
    tenant_id: Optional[str] = None,
    limit: int = 50,
    db=Depends(get_database),
    current_user=Depends(get_current_user),
):
    """
    Aggregate risk scores per user from recent login events.
    Returns a sorted list (highest risk first).
    """
    caller_role = getattr(current_user, "role", "") or ""
    caller_tenant = getattr(current_user, "tenant_id", None)
    # Non-admins are always scoped to their own tenant; admins may cross-scope
    effective_tenant = (tenant_id if caller_role in _UEBA_SUPER_ROLES else caller_tenant) or caller_tenant
    query: Dict[str, Any] = {}
    if effective_tenant:
        query["tenantId"] = effective_tenant

    pipeline = [
        {"$match": {**query, "analysis.risk_score": {"$exists": True}}},
        {"$group": {
            "_id": "$user_id",
            "max_risk_score": {"$max": "$analysis.risk_score"},
            "avg_risk_score": {"$avg": "$analysis.risk_score"},
            "event_count": {"$sum": 1},
            "last_seen": {"$max": "$timestamp"},
            "triggered_rules": {"$push": "$analysis.triggered_rules"},
        }},
        {"$sort": {"max_risk_score": -1}},
        {"$limit": limit},
    ]

    results = await db.login_events.aggregate(pipeline).to_list(length=limit)
    return [
        {
            "user_id": r["_id"],
            "risk_score": round(r["max_risk_score"], 1),
            "avg_risk_score": round(r["avg_risk_score"], 1),
            "event_count": r["event_count"],
            "last_seen": r["last_seen"],
        }
        for r in results
    ]


@router.get("/alerts")
async def get_ueba_alerts(
    tenant_id: Optional[str] = None,
    limit: int = 100,
    db=Depends(get_database),
    current_user=Depends(get_current_user),
):
    """Return tenant-scoped UEBA anomaly alerts sorted by recency."""
    caller_role = getattr(current_user, "role", "") or ""
    caller_tenant = getattr(current_user, "tenant_id", None)
    effective_tenant = (tenant_id if caller_role in _UEBA_SUPER_ROLES else caller_tenant) or caller_tenant
    query: Dict[str, Any] = {"type": {"$regex": "^ueba_", "$options": "i"}}
    if effective_tenant:
        query["tenantId"] = effective_tenant

    alerts = await (
        db.alerts
        .find(query, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
        .to_list(length=limit)
    )
    return alerts


@router.get("/rules")
async def list_rules():
    """Return active UEBA rule definitions and weights."""
    return {
        "rules": [
            {"id": k, "weight": v["weight"], "severity": v["severity"], "description": v["desc"]}
            for k, v in _RULES.items()
        ],
        "total": len(_RULES),
    }
