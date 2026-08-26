"""
UEBA (User and Entity Behavior Analytics) Service
Detects behavioral anomalies through multi-rule analysis.

CLAUDE.md 500-line cap: the rule-based analysis engine (event models, _RULES,
analyze_login/analyze_data_access, _parse_dt/_haversine_km) now lives in
ueba_analysis.py, and the alert-persistence helper lives in
ueba_alert_persistence_service.py (mirrors the agent_heartbeat_alerts_service.py
split, Phase 46 Plan 05). Both are re-exported below via plain module-level
imports so every existing external import path keeps working unchanged:
`from ueba_service import persist_security_alert` (agent_heartbeat_endpoints.py,
agent_heartbeat_alerts_service.py), `from ueba_service import _haversine_km`
(geo_security_service.py), `from ueba_service import analyze_login, LoginEvent`
(authentication_endpoints.py), and module-qualified test references
(`ueba_service._persist_alert`, `ueba_service.persist_security_alert`, etc.)
all still resolve to the same objects — re-exporting via `from X import Y`
does not create a copy, `ueba_service.Y is ueba_analysis.Y` stays true.
"""
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, status
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import logging
from database import get_database
from authentication_service import get_current_user

from ueba_analysis import (  # noqa: F401 — re-exported for external/test imports
    _RULES,
    LoginEvent,
    DataAccessEvent,
    ShadowAIEvent,
    _parse_dt,
    _haversine_km,
    analyze_login,
    analyze_data_access,
)
from ueba_alert_persistence_service import _persist_alert, persist_security_alert  # noqa: F401

router = APIRouter(prefix="/api/ueba", tags=["UEBA"])
logger = logging.getLogger(__name__)


# ── Endpoints ──────────────────────────────────────────────────────────────────

# ── AUT-03: predictive containment trigger ─────────────────────────────────────
#
# First production call site of the Phase 53 autonomous_remediation_service.
# remediate() engine (RESEARCH Pitfall 1). Per the checkpoint:decision in
# Plan 55-03 (option-a): only the shadow_ai_detected anomaly rule — the one
# UEBA signal that carries a real agent_id — is eligible for automated,
# approval-gated containment (kill_process, via 55-02's select_playbook()
# anomaly branch). Every other anomaly rule / a missing agent_id or tenant
# fails closed here (T-55-09) and is still recorded/correlated/SIEM-pushed by
# the existing alert path above — it simply never reaches remediate().


def _dispatch_anomaly_containment_if_eligible(
    background_tasks: BackgroundTasks,
    tenant_id: Optional[str],
    agent_id: Optional[str],
    resource_id: Optional[str],
    anomaly_rule: str,
    risk_score: int = 100,
) -> bool:
    """Fail-closed eligibility gate + fire-and-forget scheduler.

    Returns False (no dispatch) unless `anomaly_rule == "shadow_ai_detected"`
    AND a truthy `agent_id` AND a resolved `tenant_id` are all present.
    Otherwise schedules `_dispatch_anomaly_remediation` via
    `background_tasks.add_task` — NEVER awaited inline (T-55-08, RESEARCH
    anti-pattern: _dispatch_and_verify can block up to ~120s) — and returns
    True.
    """
    if anomaly_rule != "shadow_ai_detected" or not agent_id or not tenant_id:
        return False
    background_tasks.add_task(
        _dispatch_anomaly_remediation, tenant_id, agent_id, resource_id, anomaly_rule, risk_score,
    )
    return True


async def _dispatch_anomaly_remediation(
    tenant_id: str,
    agent_id: str,
    resource_id: Optional[str],
    anomaly_rule: str,
    risk_score: int,
) -> None:
    """Runs inside `background_tasks` (never inline). Dedupes BEFORE
    dispatch (Pitfall 2 / T-55-07 — is_duplicate_task must be called before
    remediate() so a repeated anomaly does not trigger repeated destructive
    dispatch), then builds a RemediationFinding(finding_type="anomaly") and
    calls the existing Phase 53 `remediate()` engine unchanged — the
    identical approval-gate/dry-run/DB-lease/audit path as every other
    finding_type (D-02/D-04). No second dispatch engine is introduced."""
    from response_orchestrator import ResponseOrchestrator
    from autonomous_remediation_service import AutonomousRemediationService, RemediationFinding

    orchestrator = ResponseOrchestrator()
    is_dup = await orchestrator.is_duplicate_task(
        agent_id=agent_id,
        action="remediate_anomaly",
        dedup_window_minutes=5,
        tenant_id=tenant_id,
        alert_type="anomaly",
    )
    if is_dup:
        logger.info("UEBA anomaly containment skipped — duplicate task for agent %s", agent_id)
        return

    severity = "critical" if risk_score >= 80 else "high" if risk_score >= 60 else "medium"
    finding = RemediationFinding(
        finding_id=f"UEBA-{agent_id}-{anomaly_rule}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        finding_type="anomaly",
        severity=severity,
        tenant_id=tenant_id,
        agent_id=agent_id,
        resource_id=resource_id,
        details={"anomaly_rule": anomaly_rule, "risk_score": risk_score},
    )
    await AutonomousRemediationService().remediate(finding)


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

    # AUT-03: first production trigger of the Phase 53 remediate() engine.
    # Every ShadowAIEvent here already carries a real agent_id (required
    # field) and is definitionally shadow_ai_detected — resolve its tenant
    # from the agents collection (the same lookup used elsewhere in the
    # codebase, e.g. agent_approval_endpoints.py) and let the eligibility
    # gate above decide.
    agent_doc = await db.agents.find_one({"id": event.agent_id}, {"tenantId": 1})
    tenant_id = (agent_doc or {}).get("tenantId")
    _dispatch_anomaly_containment_if_eligible(
        background_tasks,
        tenant_id=tenant_id,
        agent_id=event.agent_id,
        resource_id=event.remote_host or event.process,
        anomaly_rule="shadow_ai_detected",
        risk_score=100,
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
