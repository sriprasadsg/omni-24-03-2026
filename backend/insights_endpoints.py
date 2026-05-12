"""
Proactive Insights Endpoint
Generates actionable security insights by querying existing collections.
No simulation — derived purely from real operational data.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from authentication_service import get_current_user
from auth_types import TokenData
from database import get_database
from tenant_context import set_tenant_id

router = APIRouter(prefix="/api/insights", tags=["Proactive Insights"])

logger = logging.getLogger(__name__)

_ADMIN_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}


@router.get("/proactive")
async def get_proactive_insights(
    tenantId: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Derive proactive security insights from live operational data.
    Each insight has: id, category, severity, title, description, count, action.
    """
    if getattr(current_user, "role", "") in _ADMIN_ROLES:
        set_tenant_id("platform-admin")

    db = get_database()
    now = datetime.now(timezone.utc)
    day_ago = (now - timedelta(hours=24)).isoformat()
    week_ago = (now - timedelta(days=7)).isoformat()

    insights = []
    base_query = {"tenantId": tenantId} if tenantId else {}

    # 1. Unacknowledged critical/high alerts older than 24h
    try:
        stale_alerts = await db.alerts.count_documents({
            **base_query,
            "severity": {"$in": ["Critical", "High", "critical", "high"]},
            "status": {"$in": ["open", "Open", "new", "New"]},
            "timestamp": {"$lt": day_ago},
        })
        if stale_alerts > 0:
            insights.append({
                "id": "stale-critical-alerts",
                "category": "Alerting",
                "severity": "High",
                "title": f"{stale_alerts} Critical/High Alert{'s' if stale_alerts > 1 else ''} Unresolved >24h",
                "description": "High-severity alerts left open for more than 24 hours increase dwell time risk.",
                "count": stale_alerts,
                "action": "Review and triage open critical alerts",
            })
    except Exception as exc:
        logger.warning("insights: stale-alerts query failed: %s", exc)

    # 2. Offline agents
    try:
        offline_agents = await db.agents.count_documents({
            **base_query,
            "status": {"$in": ["Offline", "offline", "Unknown"]},
        })
        if offline_agents > 0:
            insights.append({
                "id": "offline-agents",
                "category": "Agent Health",
                "severity": "Medium",
                "title": f"{offline_agents} Agent{'s' if offline_agents > 1 else ''} Currently Offline",
                "description": "Offline agents create blind spots in your security coverage.",
                "count": offline_agents,
                "action": "Investigate and reconnect offline agents",
            })
    except Exception as exc:
        logger.warning("insights: offline-agents query failed: %s", exc)

    # 3. Unpatched critical CVEs
    try:
        unpatched_critical = await db.patches.count_documents({
            **base_query,
            "severity": {"$in": ["Critical", "critical"]},
            "status": {"$in": ["pending", "Pending", "missing", "Missing"]},
        })
        if unpatched_critical > 0:
            insights.append({
                "id": "unpatched-critical-cves",
                "category": "Vulnerability Management",
                "severity": "Critical",
                "title": f"{unpatched_critical} Critical CVE{'s' if unpatched_critical > 1 else ''} Unpatched",
                "description": "Critical vulnerabilities with known exploits remain unpatched in your environment.",
                "count": unpatched_critical,
                "action": "Schedule emergency patching for critical CVEs",
            })
    except Exception as exc:
        logger.warning("insights: unpatched-cves query failed: %s", exc)

    # 4. Failed compliance controls
    try:
        failed_controls = await db.compliance_evidence.count_documents({
            **base_query,
            "status": {"$in": ["fail", "Fail", "failed", "Failed", "non_compliant"]},
        })
        if failed_controls > 0:
            insights.append({
                "id": "failed-compliance-controls",
                "category": "Compliance",
                "severity": "High",
                "title": f"{failed_controls} Compliance Control{'s' if failed_controls > 1 else ''} Failing",
                "description": "Compliance controls in a failed state may result in audit findings.",
                "count": failed_controls,
                "action": "Review failing compliance controls and apply remediations",
            })
    except Exception as exc:
        logger.warning("insights: compliance-controls query failed: %s", exc)

    # 5. High-risk UEBA users
    try:
        high_risk_users = await db.ueba_risk_scores.count_documents({
            **base_query,
            "score": {"$gte": 80},
        })
        if high_risk_users > 0:
            insights.append({
                "id": "high-risk-ueba-users",
                "category": "UEBA",
                "severity": "High",
                "title": f"{high_risk_users} User{'s' if high_risk_users > 1 else ''} with High Behavioral Risk Score",
                "description": "Users with risk scores ≥ 80 exhibit anomalous behavior patterns.",
                "count": high_risk_users,
                "action": "Review high-risk user activity and consider step-up authentication",
            })
    except Exception as exc:
        logger.warning("insights: ueba-risk query failed: %s", exc)

    # 6. Recent DLP incidents
    try:
        dlp_incidents = await db.dlp_incidents.count_documents({
            **base_query,
            "status": {"$in": ["open", "Open", "active", "Active"]},
            "createdAt": {"$gte": week_ago},
        })
        if dlp_incidents > 0:
            insights.append({
                "id": "active-dlp-incidents",
                "category": "Data Loss Prevention",
                "severity": "Medium",
                "title": f"{dlp_incidents} Active DLP Incident{'s' if dlp_incidents > 1 else ''} in Last 7 Days",
                "description": "Potential data exfiltration events require investigation.",
                "count": dlp_incidents,
                "action": "Review DLP incidents and assess data exposure",
            })
    except Exception as exc:
        logger.warning("insights: dlp-incidents query failed: %s", exc)

    # 7. Agents with stale heartbeat (online but not seen in 7 days)
    try:
        stale_agents = await db.agents.count_documents({
            **base_query,
            "status": "Online",
            "lastSeen": {"$lt": week_ago},
        })
        if stale_agents > 0:
            insights.append({
                "id": "stale-heartbeat-agents",
                "category": "Agent Health",
                "severity": "Low",
                "title": f"{stale_agents} Online Agent{'s' if stale_agents > 1 else ''} with Stale Heartbeat",
                "description": "Agents reporting Online but not seen in 7+ days may have connectivity issues.",
                "count": stale_agents,
                "action": "Verify agent connectivity and restart if needed",
            })
    except Exception as exc:
        logger.warning("insights: stale-heartbeat query failed: %s", exc)

    if not insights:
        insights.append({
            "id": "all-clear",
            "category": "Summary",
            "severity": "Info",
            "title": "No Proactive Insights at This Time",
            "description": "All monitored metrics are within normal thresholds.",
            "count": 0,
            "action": None,
        })

    return insights
