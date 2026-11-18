"""One-click response from a SOC alert (Security Operations Center).

An analyst picks an action the alert's own evidence supports: isolate the host (it reconnects by itself
after 4 hours unless someone keeps it isolated), quarantine the file the alert names (path and SHA-256,
never a protected system file), block the IP it names for 1 hour, 24 hours or 7 days, or end the process
when the alert carries its id, start time and program (the agent then ends only that program).
Parameters come only from the stored alert, never from the request.

Each request goes through the Autonomous Ops gate with origin "analyst" (gate.ANALYST_ORIGIN): the
tenant's Autonomous Ops switch and level do not apply, every protective check does (stops, the Platform
tenant, protected targets, agent capability/online/support, dedupe), and the person's click is the
approval (approvals.approve). So it reaches the agent through the same dispatcher as every response,
is undone the same way (approvals.undo) and is kept isolated the same way (isolation.confirm). The
ledger row names the alert; ``options`` lists those rows on the alert.
"""
import ipaddress
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import audit_ledger
from autonomous_ops import agent_support, approvals, gate, isolation, messages, protected_paths, registry
from autonomous_ops import response_dispatch  # noqa: F401  (registers the security_response dispatcher)
from autonomous_ops.scope import raw
from database import get_database
from soc_service import scope_filter

logger = logging.getLogger(__name__)

ACTIONS = ("isolate_host", "quarantine_file", "block_ip", "kill_process")
BLOCK_TTLS = {"1h": 3600, "24h": 86400, "7d": 604800}
TTL_WORDS = {"1h": "1 hour", "24h": "24 hours", "7d": "7 days"}
NO_FILE_ACTIONS = ("pii_detected", "ueba_anomaly", "ueba_data_exfil", "shadow_ai_process")
LABELS = {"isolate_host": "Isolate host", "quarantine_file": "Quarantine file", "block_ip": "Block IP",
          "kill_process": "End process"}
SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
QUOTED_PATH = re.compile(r"'((?:/|[A-Za-z]:\\)[^']+)'")
STATE_WORDS = {
    "awaiting_approval": "Waiting", "approved": "Sending", "dispatching": "Sent to the agent",
    "executed": "Done", "verified": "Done and checked", "failed": "Failed", "refused": "Refused",
    "undone": "Undone", "rolled_back": "Ended by itself", "expired": "Expired", "cancelled_by_stop": "Stopped",
}
UNDOABLE = ("executed", "verified")
AGENT_FIELDS = {"_id": 0, "id": 1, "tenantId": 1, "hostname": 1, "status": 1, "lastSeen": 1, "platform": 1,
                "meta.response_actions": 1, "meta.response_state": 1}


class ResponseError(ValueError):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def _meta(doc: Dict[str, Any]) -> Dict[str, Any]:
    return doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}


def _first(doc: Dict[str, Any], *keys: str) -> Any:
    meta = _meta(doc)
    for key in keys:
        for source in (doc, meta):
            value = source.get(key)
            if isinstance(value, (str, int)) and not isinstance(value, bool) and str(value).strip():
                return value
    return None


def _int(value: Any, floor: int) -> Optional[int]:
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return None
    return number if number > floor else None


def evidence(doc: Dict[str, Any]) -> Dict[str, Any]:
    """What the alert names that an action can use: file path and hash, a public IP, a process."""
    path = _first(doc, "path", "file_path", "target", "exe", "executable")
    if not path:
        quoted = QUOTED_PATH.search(" ".join(str(v) for v in (doc.get("description"), _meta(doc).get("description")) if v))
        path = quoted.group(1) if quoted else None
    sha = _first(doc, "sha256", "current_checksum", "hash")
    ip = _first(doc, "remote_ip", "ip_address", "ip", "source_ip", "dest_ip", "destination_ip")
    try:
        ip = str(ipaddress.ip_address(str(ip).strip())) if ip and ipaddress.ip_address(str(ip).strip()).is_global else None
    except ValueError:
        ip = None
    return {
        "path": str(path) if path else None,
        "sha256": str(sha).lower() if sha and SHA256.match(str(sha)) else None,
        "ip": ip,
        "pid": _int(_first(doc, "pid"), 1),
        "start_time": _int(_first(doc, "start_time", "process_start_time"), 0),
        "exe": _first(doc, "expected_exe", "exe", "executable"),
    }


def _params(action: str, ev: Dict[str, Any], ttl: Optional[str]) -> Optional[Dict[str, Any]]:
    """The agent parameters for an action, or None when the alert does not name enough for it."""
    if action == "isolate_host":
        return {}
    if action == "quarantine_file":
        return {"path": ev["path"], "sha256": ev["sha256"]} if ev["path"] and ev["sha256"] else None
    if action == "block_ip":
        return {"ip_address": ev["ip"], "ttl_seconds": BLOCK_TTLS[ttl or "24h"]} if ev["ip"] else None
    if action == "kill_process":
        if not (ev["pid"] and ev["start_time"] and ev["exe"]):
            return None
        return {"target": str(ev["pid"]), "expected_exe": str(ev["exe"]),
                "processes": [{"pid": ev["pid"], "start_time": ev["start_time"]}]}
    return None


_MISSING = {
    "quarantine_file": "The alert does not name both the file and its SHA-256 hash, so the agent could not check it moves the right file.",
    "block_ip": "The alert does not name a public IP address.",
    "kill_process": "The alert does not name the process id, start time and program, so the agent could not be sure it ends the right process.",
}


async def _alert(db, scope: Optional[str], alert_id: str) -> Dict[str, Any]:
    doc = await db.security_alerts.find_one({"id": alert_id, **scope_filter(scope)}, {"_id": 0})
    if not doc:
        raise ResponseError("Alert not found", 404)
    return doc


def _row_view(row: Dict[str, Any]) -> Dict[str, Any]:
    spec = registry.resolve(row.get("command"))
    until = row.get("blockedUntil")
    expired = isinstance(until, datetime) and until.replace(tzinfo=until.tzinfo or timezone.utc) <= datetime.now(timezone.utc)
    iso = row.get("isolation") if isinstance(row.get("isolation"), dict) else {}
    when = lambda v: v.isoformat() if isinstance(v, datetime) else v  # noqa: E731
    return {
        "actionId": row.get("id"), "action": row.get("command"), "label": LABELS.get(row.get("command"), row.get("command")),
        "state": row.get("state"), "stateText": STATE_WORDS.get(row.get("state"), row.get("state")),
        "reason": messages.REASON_TEXT.get(row.get("reasonCode")) if row.get("state") in ("failed", "refused") else None,
        "requestedBy": ((row.get("approval") or {}).get("approver") or {}).get("display")
        or ((row.get("approval") or {}).get("approver") or {}).get("username"),
        "createdAt": when(row.get("createdAt")), "blockedUntil": when(until),
        "revertsAt": when(iso.get("revertsAt")), "keptIsolated": bool(iso.get("confirmedAt")),
        "canUndo": row.get("state") in UNDOABLE and bool(spec and spec.undo) and not expired,
        "canKeepIsolated": row.get("command") == "isolate_host" and row.get("state") in UNDOABLE and not iso.get("confirmedAt"),
    }


async def options(scope: Optional[str], alert_id: str, now: Optional[datetime] = None) -> Dict[str, Any]:
    """The actions this alert supports, whether its endpoint can carry each out now, and what was done."""
    db = get_database()
    now = now or datetime.now(timezone.utc)
    doc = await _alert(db, scope, alert_id)
    tenant, agent_id = doc.get("tenantId"), doc.get("agent_id")
    agent = await raw(db).agents.find_one({"id": agent_id, "tenantId": tenant}, AGENT_FIELDS) if agent_id and tenant else None
    host = (agent or {}).get("hostname") or agent_id or "this endpoint"
    ev = evidence(doc)
    out = []
    for action in ACTIONS:
        params = _params(action, ev, None)
        why = None
        if tenant == gate.PLATFORM_TENANT_ID:
            why = "Response actions are not available on the platform's own computers."
        elif not agent:
            why = "The endpoint is no longer enrolled."
        elif action == "quarantine_file" and doc.get("type") in NO_FILE_ACTIONS:
            why = "This kind of alert does not point at a harmful file."
        elif params is None:
            why = _MISSING.get(action)
        elif action == "quarantine_file" and protected_paths.is_protected(params["path"], (agent or {}).get("platform")):
            why = "This is a protected system file; it can only be quarantined from Autonomous Ops with approval."
        else:
            code = await agent_support.check(db, tenant, agent, action, params=params or {}, now=now)
            why = messages.REASON_TEXT.get(code) if code else None
        out.append({"action": action, "label": LABELS[action], "available": why is None, "reason": why,
                    "target": {"host": host, "path": ev["path"], "ip": ev["ip"], "pid": ev["pid"], "exe": ev["exe"]}})
    rows = await raw(db).autonomy_actions.find(
        {"tenantId": tenant, "origin": gate.ANALYST_ORIGIN, "reason.inputs.alertId": alert_id}, {"_id": 0},
    ).sort("createdAt", -1).to_list(20)
    state = ((agent or {}).get("meta") or {}).get("response_state") if agent else None
    return {"options": out, "history": [_row_view(r) for r in rows], "host": host,
            "isolated": bool(isinstance(state, dict) and state.get("isolation")), "blockTtls": list(BLOCK_TTLS)}


async def respond(scope: Optional[str], alert_id: str, action: str, actor: Dict[str, Any], user: Any,
                  ttl: Optional[str] = None) -> Dict[str, Any]:
    """Carry out one action for the alert, with the person as its approver."""
    if action not in ACTIONS:
        raise ResponseError(f"action must be one of: {', '.join(ACTIONS)}", 400)
    if action == "block_ip" and ttl not in BLOCK_TTLS:
        raise ResponseError(f"A block needs a length: {', '.join(BLOCK_TTLS)}", 400)
    db = get_database()
    offered = {o["action"]: o for o in (await options(scope, alert_id))["options"]}
    if not offered[action]["available"]:
        raise ResponseError(offered[action]["reason"] or "This action is not available for this alert.")
    doc = await _alert(db, scope, alert_id)
    tenant, agent_id = doc["tenantId"], doc["agent_id"]
    params = _params(action, evidence(doc), ttl)
    indicator = params.get("sha256") or params.get("ip_address") or params.get("target") or ""
    who = actor.get("display") or actor.get("username") or "a person"
    decision = await gate.decide(db, gate.ActionRequest(
        tenant_id=tenant, kind="security", origin=gate.ANALYST_ORIGIN, actions=[action], targets=[agent_id],
        params=params, dedupe_key=f"{tenant}|analyst|{action}|{agent_id}|{indicator}",
        reason={"ruleId": "soc:analyst", "inputs": {"alertId": alert_id, "alertTitle": str(doc.get("title"))[:200]}},
        reason_text=f"{who} asked for this from the alert “{str(doc.get('title'))[:120]}”.",
        dispatcher=response_dispatch.DISPATCHER_NAME))
    if decision.outcome == "refuse":
        raise ResponseError(messages.REASON_TEXT.get(decision.reason) or "This action cannot be done now.")
    result = await approvals.approve(db, tenant, decision.action_id, approver=actor)
    await _audit(f"soc.response.{action}", tenant, user, alertId=alert_id, actionId=decision.action_id,
                 status=result.get("status"), reason=result.get("reason"))
    if result.get("status") != "dispatched":
        reason = result.get("reason") or result.get("status")
        raise ResponseError(messages.API_DETAIL.get(reason) or messages.REASON_TEXT.get(reason) or "The action was not sent.")
    await db.security_alerts.update_one({"id": alert_id, **scope_filter(scope)}, [{"$set": {
        "status": {"$cond": [{"$in": [{"$ifNull": ["$status", "open"]}, ["open", "new"]]}, "acknowledged", "$status"]},
        "acknowledgedAt": {"$ifNull": ["$acknowledgedAt", datetime.now(timezone.utc).isoformat()]},
        "acknowledgedBy": {"$ifNull": ["$acknowledgedBy", who]},
    }}])
    return {"actionId": decision.action_id, "status": "dispatched"}


async def _owned_row(db, scope: Optional[str], alert_id: str, action_id: str) -> Dict[str, Any]:
    doc = await _alert(db, scope, alert_id)
    row = await raw(db).autonomy_actions.find_one(
        {"id": action_id, "tenantId": doc.get("tenantId"), "origin": gate.ANALYST_ORIGIN, "reason.inputs.alertId": alert_id},
        {"_id": 0, "id": 1, "tenantId": 1})
    if not row:
        raise ResponseError("That action was not taken from this alert", 404)
    return row


async def undo(scope: Optional[str], alert_id: str, action_id: str, actor: Dict[str, Any], user: Any) -> Dict[str, Any]:
    db = get_database()
    row = await _owned_row(db, scope, alert_id, action_id)
    result = await approvals.undo(db, row["tenantId"], action_id, actor=actor)
    await _audit("soc.response.undo", row["tenantId"], user, alertId=alert_id, actionId=action_id, status=result.get("status"))
    if result.get("status") != "undone":
        reason = result.get("reason") or result.get("status")
        raise ResponseError(messages.API_DETAIL.get(reason) or messages.REASON_TEXT.get(reason) or "It could not be undone.")
    return {"status": "undone"}


async def keep_isolated(scope: Optional[str], alert_id: str, action_id: str, actor: Dict[str, Any], user: Any) -> Dict[str, Any]:
    db = get_database()
    row = await _owned_row(db, scope, alert_id, action_id)
    result = await isolation.confirm(db, row["tenantId"], action_id, actor)
    await _audit("soc.response.keep_isolated", row["tenantId"], user, alertId=alert_id, actionId=action_id,
                 status=result.get("status"))
    if result.get("status") != "confirmed":
        reason = result.get("reason") or result.get("status")
        raise ResponseError(messages.API_DETAIL.get(reason) or messages.REASON_TEXT.get(reason) or "The isolation was not kept.")
    return {"status": "confirmed"}


async def _audit(action: str, tenant_id: Optional[str], user: Any, **fields: Any) -> None:
    try:
        await audit_ledger.event(action, tenant_id or "platform-admin",
                                 actor={"email": getattr(user, "username", None), "role": getattr(user, "role", None),
                                        "tenantId": getattr(user, "tenant_id", None)}, **fields)
    except Exception as e:
        logger.warning("SOC response audit entry %s not recorded: %s", action, e)
