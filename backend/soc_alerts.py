"""Security alerts: the one record every detection writes, read by the SOC console and Alert Management.

``record_alert`` gives each alert an id, its tenant and endpoint at the top level, a status the
console understands and a live push to the tenant's open consoles. Repeats of the same finding
(``group``) update one active alert (``occurrences``, ``lastSeenAt``) instead of adding a row each
scan. AI processes a tenant approved (``approved_ai_processes``) raise no alert at all.

Stored statuses: ``open``, ``acknowledged``, ``closed`` (with a ``resolution``), and two that the
console hides: ``merged`` (a repeat folded into another alert) and ``archived``. Older rows say
``new`` for open, and the legacy ``alerts`` collection uses ``resolved``/``false_positive``;
``status_of`` reads them all.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from pymongo import ReturnDocument

logger = logging.getLogger(__name__)

ACTIVE = ("open", "acknowledged")
HIDDEN = ("merged", "archived")
RESOLUTIONS = ("resolved", "false_positive", "benign", "approved")
SEVERITIES = ("critical", "high", "medium", "low", "info")

TYPE_LABELS = {
    "shadow_ai_process": "Unapproved AI process",
    "ueba_anomaly": "Unusual user behaviour",
    "ueba_data_exfil": "Possible data exfiltration",
    "pii_detected": "Personal data found",
    "fim_violation": "File integrity",
    "runtime_security": "Runtime threat",
    "malware_detected": "Malware",
    "persistence_mechanism": "Suspicious persistence",
    "etw_behavioral_detection": "Windows behaviour rule",
    "siem_rule": "SIEM rule",
    "paging_test": "Paging test",
    "ids_alert": "Network IDS",
}


def type_label(alert_type: Any) -> str:
    key = str(alert_type or "").strip()
    return TYPE_LABELS.get(key) or (key.replace("_", " ").capitalize() if key else "Other")


def severity_of(value: Any) -> str:
    s = str(value or "").strip().lower()
    if s in SEVERITIES:
        return s
    return "info" if s in ("informational", "information") else "medium"


def status_of(doc: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """(status, resolution) in the console's words, for any stored alert."""
    s = str(doc.get("status") or "").strip().lower()
    if s in HIDDEN:
        return s, None
    if s == "closed":
        return "closed", doc.get("resolution") or "resolved"
    if s in ("resolved", "false_positive", "benign", "approved", "dismissed"):
        return "closed", "benign" if s == "dismissed" else s
    if s == "acknowledged" or doc.get("acknowledged") is True:
        return "acknowledged", None
    return "open", None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def is_approved_ai(db, tenant_id: Optional[str], agent_id: Optional[str], process: Optional[str]) -> bool:
    """True when the tenant approved this AI process on this endpoint, or on all its endpoints."""
    if not process:
        return False
    found = await db.approved_ai_processes.find_one(
        {"tenantId": tenant_id, "process": process.strip().lower(), "agentId": {"$in": [agent_id, None]}},
        {"_id": 1},
    )
    return found is not None


async def record_alert(db, alert: Dict[str, Any], group: Optional[str] = None) -> Dict[str, Any]:
    """Store one security alert (or count a repeat of an active one) and push it to open consoles.

    ``alert`` is the writer's document; tenant and endpoint come from ``metadata`` when the writer
    only put them there. Returns the stored alert, without ``_id``.
    """
    meta = alert.get("metadata") if isinstance(alert.get("metadata"), dict) else {}
    if not alert.get("tenantId") and meta.get("tenantId"):
        alert["tenantId"] = meta["tenantId"]
    if not alert.get("agent_id") and (meta.get("agent_id") or alert.get("agentId")):
        alert["agent_id"] = meta.get("agent_id") or alert.get("agentId")
    alert["severity"] = severity_of(alert.get("severity"))
    alert["created_at"] = alert.get("created_at") or alert.get("timestamp") or _now()
    alert["status"] = status_of(alert)[0] if alert.get("status") else "open"
    alert["lastSeenAt"] = alert["created_at"]
    alert["occurrences"] = 1

    if group:
        alert["group"] = group
        repeat = await db.security_alerts.find_one_and_update(
            {"tenantId": alert.get("tenantId"), "group": group, "status": {"$in": list(ACTIVE)}},
            {"$inc": {"occurrences": 1},
             "$set": {"lastSeenAt": alert["created_at"], "description": alert.get("description", "")}},
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )
        if repeat:
            await _push(repeat, repeat=True)
            return repeat

    alert["id"] = alert.get("id") or str(uuid.uuid4())
    await db.security_alerts.insert_one(alert)
    alert.pop("_id", None)
    try:  # the tenant's automation rules (soc_rules) first: they may raise, assign or close it
        import soc_rules
        await soc_rules.apply(db, alert)
    except Exception as e:
        logger.warning("SOC rules not applied to %s: %s", alert["id"], e)
    try:  # threat-intel feeds listing one of its hashes or IPs (soc_context)
        import soc_context
        await soc_context.match_alert(db, alert)
    except Exception as e:
        logger.debug("SOC threat-intel match for %s skipped: %s", alert["id"], e)
    if alert.get("status") != "closed":
        try:  # the endpoint's incident (soc_incidents); a failure never loses the alert
            import soc_incidents
            alert["incidentId"] = await soc_incidents.attach(db, alert)
        except Exception as e:
            logger.warning("SOC alert %s not put on an incident: %s", alert["id"], e)
    await _push(alert)
    if alert.get("status") != "closed":
        try:  # a new critical alert gets an AI triage in the background (soc_triage)
            import soc_triage
            soc_triage.schedule_auto(alert)
        except Exception as e:
            logger.debug("SOC auto-triage not scheduled: %s", e)
        try:  # the organization's on-call page, when it has paging set up (soc_paging)
            import soc_paging
            soc_paging.schedule_new(alert)
        except Exception as e:
            logger.debug("SOC paging not scheduled: %s", e)
    return alert


async def _push(alert: Dict[str, Any], repeat: bool = False) -> None:
    """Tell the tenant's open consoles (and the platform view) that an alert arrived; never raises."""
    try:
        from websocket_manager import broadcast_security_alert
        payload = {
            "id": alert.get("id"), "type": alert.get("type"), "severity": alert.get("severity"),
            "title": alert.get("title"), "agentId": alert.get("agent_id"),
            "createdAt": alert.get("lastSeenAt") or alert.get("created_at"), "repeat": repeat,
        }
        tenant = alert.get("tenantId")
        for room in {tenant, "platform-admin"} - {None, ""}:
            await broadcast_security_alert(room, payload)
    except Exception as e:  # a closed socket must never lose the alert itself
        logger.debug("security alert push failed (non-fatal): %s", e)
