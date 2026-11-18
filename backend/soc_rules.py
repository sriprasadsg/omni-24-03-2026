"""SOC automation rules: when a new alert matches, assign it, raise its severity, close it, notify people,
open a case, or mark a response as suggested. A rule never sends a response to an endpoint: automatic
responses stay with Autonomous Ops and its approvals.

A rule's conditions are ANDed (each list is "any of"): detection types, severities, endpoints, text in
the title or details, MITRE techniques; at least one is required so a rule cannot match everything by
accident. Rules run in their order on each new alert (not on repeats); the first rule that assigns or
closes wins those fields, a raise only ever raises. The alert records which rules touched it; a rule
counts its matches. Rule closures are ``autoClosed`` so they stay out of the response times.

Notifications go to the tenant's admins in the app and to the tenant's own webhooks subscribed to
``soc.rule_match`` (selected by tenantId explicitly, never through the ambient tenant context).
"""
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from soc_alerts import SEVERITIES, severity_of
from soc_service import techniques_of

logger = logging.getLogger(__name__)

MAX_RULES = 50
CLOSE_AS = ("resolved", "false_positive", "benign")
NOTIFY = ("in_app", "webhook")
RESPONSES = ("isolate_host", "quarantine_file", "block_ip", "kill_process")
RANK = {s: i for i, s in enumerate(SEVERITIES)}
TECHNIQUE = re.compile(r"^T\d{4}(\.\d{3})?$")
WEBHOOK_EVENT = "soc.rule_match"
PLATFORM = "platform-admin"


class RuleError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _strings(value: Any, limit: int, size: int = 100) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > limit:
        raise RuleError(f"A list of at most {limit} values is expected")
    out = [str(v).strip()[:size] for v in value if str(v).strip()]
    return list(dict.fromkeys(out))


def clean(body: Dict[str, Any]) -> Dict[str, Any]:
    """A rule as stored: checked names, conditions and actions (raises RuleError on anything else)."""
    name = str(body.get("name") or "").strip()[:120]
    if not name:
        raise RuleError("A rule needs a name")
    cond_in, act_in = body.get("conditions") or {}, body.get("actions") or {}
    if not isinstance(cond_in, dict) or not isinstance(act_in, dict):
        raise RuleError("conditions and actions must be objects")
    severities = _strings(cond_in.get("severities"), 5)
    techniques = [t.upper() for t in _strings(cond_in.get("techniques"), 20, 9)]
    if any(s not in SEVERITIES for s in severities) or any(not TECHNIQUE.match(t) for t in techniques):
        raise RuleError("Unknown severity or MITRE technique id")
    conditions = {"types": _strings(cond_in.get("types"), 20), "severities": severities,
                  "agentIds": _strings(cond_in.get("agentIds"), 50, 128), "techniques": techniques,
                  "text": str(cond_in.get("text") or "").strip()[:100]}
    if not any(conditions.values()):
        raise RuleError("A rule needs at least one condition")
    notify = _strings(act_in.get("notify"), 2)
    actions = {"assignTo": str(act_in.get("assignTo") or "").strip()[:120] or None,
               "raiseTo": act_in.get("raiseTo") or None, "close": act_in.get("close") or None, "notify": notify,
               "openCase": bool(act_in.get("openCase")), "suggestResponse": act_in.get("suggestResponse") or None}
    if actions["raiseTo"] not in (None, *SEVERITIES) or actions["close"] not in (None, *CLOSE_AS) \
            or any(n not in NOTIFY for n in notify) or actions["suggestResponse"] not in (None, *RESPONSES):
        raise RuleError("Unknown action value")
    if not (actions["assignTo"] or actions["raiseTo"] or actions["close"] or notify or actions["openCase"] or actions["suggestResponse"]):
        raise RuleError("A rule needs at least one action")
    if actions["close"] and actions["openCase"]:
        raise RuleError("A rule cannot both close the alert and open a case for it")
    return {"name": name, "enabled": bool(body.get("enabled", True)), "conditions": conditions, "actions": actions}


def matches(conditions: Dict[str, Any], alert: Dict[str, Any]) -> bool:
    if conditions.get("types") and str(alert.get("type") or "") not in conditions["types"]:
        return False
    if conditions.get("severities") and severity_of(alert.get("severity")) not in conditions["severities"]:
        return False
    if conditions.get("agentIds") and str(alert.get("agent_id") or "") not in conditions["agentIds"]:
        return False
    if conditions.get("techniques") and not set(conditions["techniques"]) & set(techniques_of(alert)):
        return False
    text = (conditions.get("text") or "").lower()
    if text and text not in f"{alert.get('title') or ''} {alert.get('description') or ''}".lower():
        return False
    return True


async def apply(db, alert: Dict[str, Any]) -> Dict[str, Any]:
    """Run the tenant's enabled rules on a new alert; returns the fields they set (also stored)."""
    tenant = alert.get("tenantId")
    rules = await db.soc_rules.find({"tenantId": tenant, "enabled": True}, {"_id": 0}).sort("order", 1).to_list(MAX_RULES)
    sets: Dict[str, Any] = {}
    applied, notices, cases = [], [], []
    now = datetime.now(timezone.utc).isoformat()
    for rule in rules:
        if not matches(rule.get("conditions") or {}, {**alert, **sets}):
            continue
        a, name = rule.get("actions") or {}, rule["name"]
        if a.get("assignTo") and "assignee" not in sets:
            sets["assignee"] = a["assignTo"]
        current = sets.get("severity") or severity_of(alert.get("severity"))
        if a.get("raiseTo") and RANK[a["raiseTo"]] < RANK[current]:
            sets["severity"] = a["raiseTo"]
        if a.get("close") and "status" not in sets:
            sets.update(status="closed", resolution=a["close"], closedAt=now, closedBy=f"rule: {name}",
                        closeNote=f"Closed by the rule “{name}”", acknowledged=True, autoClosed=True)
        if a.get("suggestResponse") and "suggestedResponse" not in sets:
            sets["suggestedResponse"] = {"action": a["suggestResponse"], "rule": name}
        if a.get("notify"):
            notices.append((name, a["notify"]))
        if a.get("openCase"):
            cases.append(name)
        applied.append({"id": rule["id"], "name": name})
        await db.soc_rules.update_one({"id": rule["id"], "tenantId": tenant},
                                      {"$inc": {"stats.matched": 1}, "$set": {"stats.lastMatchedAt": now}})
    if not applied:
        return {}
    sets["rules"] = applied
    await db.security_alerts.update_one({"id": alert["id"], "tenantId": tenant}, {"$set": sets})
    alert.update(sets)
    for name, channels in notices:
        await _notify(db, alert, name, channels)
    if cases and alert.get("status") != "closed":
        try:
            import soc_actions
            await soc_actions.open_case(tenant, alert["id"], SimpleNamespace(username=f"rule: {cases[0]}", role="system", tenant_id=tenant))
        except Exception as e:
            logger.warning("SOC rule case for %s not opened: %s", alert["id"], e)
    return sets


async def _notify(db, alert: Dict[str, Any], rule_name: str, channels: List[str]) -> None:
    tenant = alert.get("tenantId")
    title = f"SOC rule “{rule_name}” matched"
    message = f"{alert.get('title')} ({severity_of(alert.get('severity'))})"
    raw = getattr(db, "_db", db)
    if "in_app" in channels:
        try:
            import pending_agents
            await pending_agents.post_to_recipients(raw, {"id": tenant}, title, message,
                                                    "critical" if alert.get("severity") == "critical" else "warning",
                                                    {"source": "soc_rules", "alertId": alert.get("id")})
        except Exception as e:
            logger.warning("SOC rule notice for %s not posted: %s", alert.get("id"), e)
    if "webhook" in channels and tenant:
        try:
            import httpx
            from webhook_service import WebhookService
            hooks = await raw.webhooks.find({"tenantId": tenant, "status": "Active", "events": WEBHOOK_EVENT}).to_list(20)
            payload = {"event": WEBHOOK_EVENT, "timestamp": datetime.now(timezone.utc).isoformat(), "rule": rule_name,
                       "data": {k: alert.get(k) for k in ("id", "type", "severity", "title", "agent_id", "created_at", "status")}}
            async with httpx.AsyncClient() as client:
                for hook in hooks:
                    await WebhookService()._send_single_webhook(client, hook, payload, raw)
        except Exception as e:
            logger.warning("SOC rule webhook for %s not sent: %s", alert.get("id"), e)


def _tenant(scope: Optional[str]) -> str:
    return scope or PLATFORM


def _view(rule: Dict[str, Any]) -> Dict[str, Any]:
    return {k: rule.get(k) for k in ("id", "name", "enabled", "order", "conditions", "actions", "stats", "createdBy", "createdAt", "updatedAt")}


async def list_rules(db, scope: Optional[str]) -> List[Dict[str, Any]]:
    rows = await db.soc_rules.find({"tenantId": _tenant(scope)}, {"_id": 0}).sort("order", 1).to_list(MAX_RULES)
    return [_view(r) for r in rows]


async def save(db, scope: Optional[str], body: Dict[str, Any], who: str, rule_id: Optional[str] = None) -> Dict[str, Any]:
    tenant, rule, now = _tenant(scope), clean(body), datetime.now(timezone.utc).isoformat()
    if rule_id:
        res = await db.soc_rules.update_one({"id": rule_id, "tenantId": tenant}, {"$set": {**rule, "updatedAt": now, "updatedBy": who}})
        if res.matched_count == 0:
            raise RuleError("Rule not found", 404)
    else:
        if await db.soc_rules.count_documents({"tenantId": tenant}) >= MAX_RULES:
            raise RuleError(f"An organization can have at most {MAX_RULES} rules", 409)
        last = await db.soc_rules.find({"tenantId": tenant}, {"_id": 0, "order": 1}).sort("order", -1).to_list(1)
        rule_id = f"rule-{uuid.uuid4().hex[:12]}"
        await db.soc_rules.insert_one({**rule, "id": rule_id, "tenantId": tenant, "order": ((last[0].get("order") or 0) + 1) if last else 1,
                                       "stats": {"matched": 0, "lastMatchedAt": None}, "createdBy": who, "createdAt": now, "updatedAt": now})
    return _view(await db.soc_rules.find_one({"id": rule_id, "tenantId": tenant}, {"_id": 0}))


async def delete(db, scope: Optional[str], rule_id: str) -> None:
    res = await db.soc_rules.delete_one({"id": rule_id, "tenantId": _tenant(scope)})
    if res.deleted_count == 0:
        raise RuleError("Rule not found", 404)


async def preview(db, scope: Optional[str], body: Dict[str, Any], days: int = 7) -> Dict[str, Any]:
    """How many of the last ``days`` days' alerts the conditions would have matched, with a few examples."""
    conditions = clean({**body, "name": body.get("name") or "preview", "actions": body.get("actions") or {"notify": ["in_app"]}})["conditions"]
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = await db.security_alerts.find({"tenantId": _tenant(scope), "created_at": {"$gte": since}, "status": {"$nin": ["merged", "archived"]}},
                                         {"_id": 0}).sort("created_at", -1).to_list(5000)
    hits = [r for r in rows if matches(conditions, r)]
    return {"days": days, "checked": len(rows), "matched": len(hits),
            "examples": [{"id": r.get("id"), "title": r.get("title"), "severity": severity_of(r.get("severity")),
                          "createdAt": r.get("created_at")} for r in hits[:5]]}
