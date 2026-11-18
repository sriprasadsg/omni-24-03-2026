"""SIEM pipeline: what agents log becomes normalized events, executable rules run over them, and hits become SOC alerts.

Intake (``run_once``, every 60 s from ``intake_loop``):
* Linux: the syslog and auth.log lines agents ship (``logs``, service syslog/auth). sshd sign-ins, sudo, account
  creation and admin-group changes are recognised (``parse_linux``); other lines stay in ``logs`` only.
* Windows: the Security-log events each heartbeat carries (``agents.meta.log_collection.security_events``, agent
  2.1.21+: event data fields and the record number), or from older agents the recent System/Application events
  (``recent_events``, message text), whose event id a rule can use (``WINDOWS_EVENTS``), each once (unique ``key``).
Events go to ``soc_log_events`` (tenant, agent, host, source, time, action, user, source IP, process, message).

Rules (``siem_rules``, the organization's and the platform library's): one with ``logic`` runs on events of its
``logSource``: ``match`` (field equal to a value, or {"in": [...]}) and ``threshold`` {count, windowSeconds,
groupBy, distinct?}. One without logic, or whose source sent nothing for 7 days, waits (``rule_states``). Library
rules record hits for 7 days (``mode`` "record" until ``alertAfter``) so a noisy one is tuned before it alerts.
A hit is stored in ``siem_hits`` (once per rule, group and window) and, when alerting, raised through
soc_alerts.record_alert (type ``siem_rule``), repeats counted on one alert per rule and group.
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)

LINE = re.compile(r"^(\S+)\s+(\S+)\s+([\w\-./]+?)(?:\[(\d+)\])?:\s*(.*)$")
IP = r"([0-9a-fA-F.:]{3,45})"
LINUX_PATTERNS = (
    ("sshd", re.compile(rf"Failed \S+ for (?:invalid user )?(\S*) from {IP}"), "login_failed", "failure"),
    ("sshd", re.compile(rf"Invalid user (\S*)\s*from {IP}"), "login_failed", "failure"),
    ("sshd", re.compile(rf"Accepted \S+ for (\S+) from {IP}"), "login_success", "success"),
    ("sudo", re.compile(r"authentication failure;.*\buser=(\S+)"), "sudo_failed", "failure"),
    ("sudo", re.compile(r"^\s*(\S+) : .*COMMAND=(.*)$"), "sudo_command", "success"),
    ("useradd", re.compile(r"new user: name=([^,\s]+)"), "account_created", "success"),
    ("usermod", re.compile(r"add '([^']+)' to (?:shadow )?group '(sudo|admin|wheel|root)'"), "admin_group_add", "success"),
    ("gpasswd", re.compile(r"user (\S+) added by \S+ to group (sudo|admin|wheel|root)"), "admin_group_add", "success"),
)
WINDOWS_EVENTS = {4625: "login_failed", 4624: "login_success", 4720: "account_created", 4732: "admin_group_add",
                  4728: "admin_group_add", 4756: "admin_group_add", 1102: "log_cleared", 7045: "service_installed",
                  4740: "account_locked"}
WIN_USER = re.compile(r"Account Name:\s+([^\s\r\n]+)")
WIN_IP = re.compile(r"Source Network Address:\s+([0-9a-fA-F.:]{3,45})")
ADMINISTRATORS_SID = "S-1-5-32-544"  # the same in every Windows language
LOCAL_ADDRESSES = ("-", "::1", "127.0.0.1")
BATCH = 5000
SOURCE_IDLE = timedelta(days=7)


def _raw(db):
    return getattr(db, "_db", db)


def parse_linux(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """A normalized event for a syslog/auth line a rule can use, else None."""
    m = LINE.match(str(doc.get("message") or ""))
    if not m:
        return None
    ts, host, prog, _pid, text = m.groups()
    for name, pattern, action, outcome in LINUX_PATTERNS:
        if prog != name:
            continue
        hit = pattern.search(text)
        if not hit:
            continue
        groups = hit.groups()
        event = {"action": action, "outcome": outcome, "user": groups[0] or None, "process": prog}
        if name == "sshd":
            event["srcIp"] = groups[1]
        elif action == "sudo_command":
            event["command"] = groups[1][:300]
        elif action == "admin_group_add":
            event["group"] = groups[1]
        return {**event, "timestamp": ts, "host": host, "source": "linux_auth", "message": text[:500]}
    return None


def parse_windows(agent: Dict[str, Any], e: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        eid = int(e.get("event_id"))
    except (TypeError, ValueError):
        return None
    action = WINDOWS_EVENTS.get(eid)
    if not action:
        return None
    if isinstance(e.get("data"), dict):
        return _windows_fields(agent, e, eid, action, e["data"])
    text = str(e.get("message") or "")
    user, ip = WIN_USER.findall(text), WIN_IP.search(text)
    return {"action": action, "outcome": "failure" if eid in (4625, 4740) else "success", "eventId": eid,
            "user": user[-1] if user else None, "srcIp": ip.group(1) if ip and ip.group(1) not in ("-", "::1") else None,
            "timestamp": e.get("time"), "host": agent.get("hostname"), "source": "windows_security",
            "group": "Administrators" if action == "admin_group_add" and "Administrators" in text else None,
            "message": text[:500], "key": f"{agent['id']}|{e.get('source')}|{eid}|{e.get('time')}"}


def _windows_fields(agent: Dict[str, Any], e: Dict[str, Any], eid: int, action: str,
                    data: Dict[str, Any]) -> Dict[str, Any]:
    """An event from the Security log's event data (agent 2.1.21+), keyed by its record number."""
    def field(name: str) -> Optional[str]:
        value = str(data.get(name) or "").strip()
        return value if value and value != "-" else None

    group = None
    if action == "admin_group_add":
        user = field("MemberName") or field("MemberSid")
        group = "Administrators" if field("TargetSid") == ADMINISTRATORS_SID else field("TargetUserName")
    elif eid == 1102:
        user = field("SubjectUserName")
    elif eid == 7045:
        user = field("AccountName")
    else:
        user = field("TargetUserName")
    ip = field("IpAddress")
    detail = " ".join(f"{k}={v}" for k, v in sorted(data.items()) if str(v or "").strip() not in ("", "-"))
    record = e.get("record_id")
    return {"action": action, "outcome": "failure" if eid in (4625, 4740) else "success", "eventId": eid,
            "user": user, "srcIp": ip if ip not in LOCAL_ADDRESSES else None, "logonType": field("LogonType"),
            "process": field("ServiceName"), "timestamp": e.get("time"), "host": agent.get("hostname"),
            "source": "windows_security", "group": group, "message": f"Event {eid}: {detail}"[:500],
            "key": f"{agent['id']}|{e.get('log') or e.get('source')}|{record}" if record is not None
            else f"{agent['id']}|{e.get('source')}|{eid}|{e.get('time')}"}


def _ts(value: Any) -> datetime:
    try:
        t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
    return t.astimezone(timezone.utc) if t.tzinfo else t.replace(tzinfo=timezone.utc)


async def _store(db, event: Dict[str, Any]) -> bool:
    event["at"] = _ts(event.get("timestamp"))
    try:
        await _raw(db).soc_log_events.insert_one(dict(event))
        return True
    except DuplicateKeyError:
        return False


async def intake(db) -> List[Dict[str, Any]]:
    """New events since the last pass, stored; returns them."""
    raw, new = _raw(db), []
    cursor = await raw.siem_cursors.find_one({"id": "logs"}) or {}
    query = {"service": {"$in": ["syslog", "auth"]}, **({"_id": {"$gt": cursor["last"]}} if cursor.get("last") else {})}
    last = cursor.get("last")
    async for doc in raw.logs.find(query, {"message": 1, "tenantId": 1, "agentId": 1, "hostname": 1}).sort("_id", 1).limit(BATCH):
        last = doc["_id"]
        event = parse_linux(doc)
        if event:
            event.update(tenantId=doc.get("tenantId"), agentId=doc.get("agentId"), key=f"log|{doc['_id']}")
            if await _store(db, event):
                new.append(event)
    if last is not None:
        await raw.siem_cursors.update_one({"id": "logs"}, {"$set": {"last": last}}, upsert=True)
    async for agent in raw.agents.find({"$or": [{"meta.log_collection.security_events": {"$exists": True}},
                                                {"meta.log_collection.recent_events": {"$exists": True}}]},
                                       {"_id": 0, "id": 1, "tenantId": 1, "hostname": 1,
                                        "meta.log_collection.security_events": 1, "meta.log_collection.recent_events": 1}):
        logs = ((agent.get("meta") or {}).get("log_collection") or {})
        # an agent that reads the Security log sends 7045 there too, so its recent_events are not read twice
        listed = logs["security_events"] if isinstance(logs.get("security_events"), list) else logs.get("recent_events")
        for e in (listed or [])[:1000]:
            event = parse_windows(agent, e) if isinstance(e, dict) else None
            if event:
                event.update(tenantId=agent.get("tenantId"), agentId=agent["id"])
                if await _store(db, event):
                    new.append(event)
    return new


def _matches(event: Dict[str, Any], match: Dict[str, Any]) -> bool:
    for field, want in (match or {}).items():
        have = event.get(field)
        if isinstance(want, dict) and "in" in want:
            if have not in want["in"]:
                return False
        elif have != want:
            return False
    return True


async def evaluate(db, events: List[Dict[str, Any]], now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Run every rule with logic over the new events' groups; returns the hits made."""
    import soc_alerts
    raw, now, hits = _raw(db), now or datetime.now(timezone.utc), []
    tenants = {e.get("tenantId") for e in events}
    rules = await raw.siem_rules.find({"enabled": {"$ne": False}, "logic": {"$exists": True},
                                       "tenant_id": {"$in": [*tenants, "platform-admin"]}}, {"_id": 0}).to_list(500)
    for rule in rules:
        logic, th = rule["logic"], rule["logic"].get("threshold") or {}
        window = timedelta(seconds=int(th.get("windowSeconds") or 600))
        group_by, need = th.get("groupBy") or "agentId", int(th.get("count") or 1)
        fresh = [e for e in events if e.get("source") == rule.get("logSource") and _matches(e, logic.get("match"))
                 and (rule["tenant_id"] == "platform-admin" or e.get("tenantId") == rule["tenant_id"])]
        for (tenant, value) in {(e.get("tenantId"), e.get(group_by)) for e in fresh}:
            latest = max(e["at"] for e in fresh if (e.get("tenantId"), e.get(group_by)) == (tenant, value))
            q = {"tenantId": tenant, "source": rule["logSource"], group_by: value, "at": {"$gt": latest - window, "$lte": latest},
                 **{k: (v if not isinstance(v, dict) else {"$in": v["in"]}) for k, v in (logic.get("match") or {}).items()}}
            rows = await raw.soc_log_events.find(q, {"_id": 0}).sort("at", 1).to_list(5000)
            seen = {r.get(th["distinct"]) for r in rows} if th.get("distinct") else rows
            if len(seen) < need or await raw.siem_hits.find_one({"ruleId": rule["id"], "tenantId": tenant, "group": value,
                                                                  "windowEnd": {"$gt": latest - window}}):
                continue
            alerting = rule.get("mode") != "record" or (rule.get("alertAfter") and now >= _ts(rule["alertAfter"]))
            hit = {"ruleId": rule["id"], "rule": rule.get("name"), "tenantId": tenant, "group": value, "groupBy": group_by,
                   "count": len(seen), "windowStart": rows[0]["at"], "windowEnd": latest, "agentId": rows[-1].get("agentId"),
                   "host": rows[-1].get("host"), "alerted": bool(alerting), "at": now}
            await raw.siem_hits.insert_one(dict(hit))
            await raw.siem_rules.update_one({"id": rule["id"]}, {"$inc": {"match_count": 1}, "$set": {"lastMatchAt": now.isoformat()}})
            if alerting:
                await soc_alerts.record_alert(raw, {
                    "tenantId": tenant, "agent_id": hit["agentId"], "type": "siem_rule", "severity": rule.get("severity"),
                    "title": f"{rule.get('name')}: {value}" if value else rule.get("name"), "rule": rule.get("name"),
                    "description": f"{len(seen)} matching events from {group_by} {value} within {int(window.total_seconds() // 60)} minutes",
                    "mitre": rule.get("mitre_technique"), "metadata": {"user": rows[-1].get("user"), "remote_ip": rows[-1].get("srcIp")},
                    "created_at": now.isoformat(), "status": "open"}, group=f"siem:{rule['id']}:{tenant}:{value}")
            hits.append(hit)
    return hits


async def rule_states(db, scope: Optional[str], now: Optional[datetime] = None) -> Dict[str, str]:
    """rule id -> "running" | "waiting for <source>" | "no logic yet", for the rules a scope sees."""
    raw, now = _raw(db), now or datetime.now(timezone.utc)
    owners = {"tenant_id": {"$in": [scope, "platform-admin"]}} if scope else {}
    active = set(await raw.soc_log_events.distinct("source", {**({"tenantId": scope} if scope else {}), "at": {"$gte": now - SOURCE_IDLE}}))
    out = {}
    for r in await raw.siem_rules.find(owners, {"_id": 0, "id": 1, "logic": 1, "logSource": 1}).to_list(2000):
        out[r.get("id")] = ("running" if r.get("logSource") in active else f"waiting for {r.get('logSource')}") if r.get("logic") \
            else (f"waiting for {r['logSource']}" if r.get("logSource") else "no logic yet")
    return out


async def ensure_indexes(db) -> None:
    raw = _raw(db)
    await raw.soc_log_events.create_index("key", unique=True, name="soc_log_event_key")
    await raw.soc_log_events.create_index([("tenantId", 1), ("source", 1), ("at", -1)], name="soc_log_event_recent")
    await raw.soc_log_events.create_index("at", expireAfterSeconds=90 * 86400, name="soc_log_event_ttl")
    await raw.siem_hits.create_index([("ruleId", 1), ("tenantId", 1), ("group", 1), ("windowEnd", -1)], name="siem_hit_dedupe")


async def run_once(db) -> Dict[str, int]:
    events = await intake(db)
    hits = await evaluate(db, events) if events else []
    return {"events": len(events), "hits": len(hits)}


async def intake_loop() -> None:
    from database import get_database
    await asyncio.sleep(90)
    await ensure_indexes(get_database())
    while True:
        try:
            out = await run_once(get_database())
            if out["events"]:
                logger.info("SIEM pipeline: %s", out)
        except Exception as exc:  # the loop must survive a bad pass
            logger.warning("SIEM pipeline pass failed: %s", exc)
        await asyncio.sleep(60)
