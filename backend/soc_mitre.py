"""ATT&CK coverage for the SOC console: for every technique, what can detect it on the organization's endpoints,
which SIEM rules name it, and how many alerts named it in the range.

* Endpoint detection: a built-in detection (mitre_service.DETECTION_COVERAGE) covers a technique on the endpoints
  whose agent reports the check that runs it (``availableCapabilities``). Only this counts as covered.
* SIEM rule: a rule names the technique in its ``mitre_technique`` text (the organization's own rules and the
  platform library). A rule that runs on a log source that sent events in the last 7 days (siem_pipeline.rule_states)
  covers it like a detection; a rule that waits for its source is "rule written", never covered. ``siemLogs``
  counts the organization's normalized events of the last 7 days.
* Seen: alerts in the range whose techniques (soc_service.techniques_of) include it.

A technique the matrix does not list rolls up to its parent; one with no parent there either (named in an
alert's own text) goes under "Other". Computed when asked; nothing is stored.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from mitre_service import ATTACK_MATRIX, DETECTION_COVERAGE
from network_topology_service import HIDDEN_AGENT_STATUSES
from soc_alerts import HIDDEN
from soc_service import RANGES, STATUS_QUERY, TECHNIQUE, TECHNIQUE_NAMES, scope_filter, techniques_of

# Enterprise ATT&CK's column order (the embedded matrix lists its tactics in another order).
TACTIC_ORDER = ("TA0043", "TA0042", "TA0001", "TA0002", "TA0003", "TA0004", "TA0005", "TA0006", "TA0007",
                "TA0008", "TA0009", "TA0011", "TA0010", "TA0040")
SIEM_LOG_DAYS = 7
MAX_ALERTS = 20000


def cell_of(technique: str) -> str:
    """The matrix entry a technique counts under: itself, else its parent, else itself under Other."""
    if technique in TECHNIQUE_NAMES:
        return technique
    parent = technique.split(".")[0]
    return parent if parent in TECHNIQUE_NAMES else technique


def _raw(db):
    return getattr(db, "_db", db)


async def _rules(db, scope: Optional[str]) -> List[Dict[str, Any]]:
    owners = {"tenant_id": {"$in": [scope, "platform-admin"]}} if scope else {}
    rows = await _raw(db).siem_rules.find({**owners, "enabled": {"$ne": False}},
                                          {"_id": 0, "id": 1, "name": 1, "severity": 1, "mitre_technique": 1, "tenant_id": 1}).to_list(2000)
    return [{**r, "techniques": list(dict.fromkeys(TECHNIQUE.findall(str(r.get("mitre_technique") or ""))))} for r in rows]


async def _siem_logs(db, scope: Optional[str], now: datetime) -> int:
    return await _raw(db).soc_log_events.count_documents({**({"tenantId": scope} if scope else {}),
                                                          "at": {"$gte": now - timedelta(days=SIEM_LOG_DAYS)}})


async def coverage(db, scope: Optional[str], range_key: str = "30d", now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(seconds=RANGES[range_key][0])).isoformat()
    agents = [g for g in await db.agents.find(scope_filter(scope), {"_id": 0, "id": 1, "status": 1, "availableCapabilities": 1}).to_list(5000)
              if g.get("status") not in HIDDEN_AGENT_STATUSES]
    running = {d["check"]: sum(1 for g in agents if d["check"] in (g.get("availableCapabilities") or [])) for d in DETECTION_COVERAGE}

    cells: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"detections": [], "rules": [], "seen": 0, "active": 0, "named": set()})
    for d in DETECTION_COVERAGE:
        for tech, what in d["techniques"].items():
            cell = cells[cell_of(tech)]
            cell["named"].add(tech)
            cell["detections"].append({"type": d["type"], "label": d["label"], "check": d["check"], "technique": tech,
                                       "what": what, "endpoints": running[d["check"]]})
    import siem_pipeline
    states = await siem_pipeline.rule_states(db, scope, now)
    for r in await _rules(db, scope):
        for tech in r["techniques"]:
            cell = cells[cell_of(tech)]
            cell["named"].add(tech)
            cell["rules"].append({"name": r.get("name") or "SIEM rule", "severity": str(r.get("severity") or "").lower() or None,
                                  "technique": tech, "library": r.get("tenant_id") == "platform-admin",
                                  "state": states.get(r.get("id"), "no logic yet")})
    filt = {**scope_filter(scope), "status": {"$nin": list(HIDDEN)}, "$or": [{"created_at": {"$gte": since}}, {"lastSeenAt": {"$gte": since}}]}
    for d in await db.security_alerts.find(filt, {"_id": 0}).to_list(MAX_ALERTS):
        active = str(d.get("status") or "open").lower() in STATUS_QUERY["active"]
        for cid in {cell_of(t) for t in techniques_of(d)}:
            cells[cid]["seen"] += 1
            cells[cid]["active"] += active

    def entry(tid: str, name: str) -> Dict[str, Any]:
        c = cells.get(tid) or {"detections": [], "rules": [], "seen": 0, "active": 0, "named": set()}
        live = any(x["endpoints"] > 0 for x in c["detections"]) or any(r["state"] == "running" for r in c["rules"])
        level = "detected" if live else "rule" if c["rules"] else "none"
        return {"id": tid, "name": name, "level": level, "detections": c["detections"], "rules": c["rules"][:20],
                "ruleCount": len(c["rules"]), "seen": c["seen"], "active": c["active"],
                "subTechniques": sorted(t for t in c["named"] if t != tid)}

    by_id = {t["id"]: t for t in ATTACK_MATRIX["tactics"]}
    tactics = [{"id": tid, "name": by_id[tid]["name"], "techniques": [entry(t["id"], t["name"]) for t in by_id[tid]["techniques"]]}
               for tid in TACTIC_ORDER if tid in by_id]
    other = sorted(t for t in cells if t not in TECHNIQUE_NAMES)
    if other:
        tactics.append({"id": "other", "name": "Other", "techniques": [entry(t, t) for t in other]})
    flat = [t for tac in tactics for t in tac["techniques"]]
    return {
        "generatedAt": now.isoformat(), "range": range_key, "endpoints": len(agents), "siemLogs": await _siem_logs(db, scope, now),
        "siemLogDays": SIEM_LOG_DAYS, "tactics": tactics,
        "totals": {"techniques": len(flat), "detected": sum(t["level"] == "detected" for t in flat),
                   "ruleOnly": sum(t["level"] == "rule" for t in flat), "none": sum(t["level"] == "none" for t in flat),
                   "seen": sum(1 for t in flat if t["seen"])},
        "checks": [{"type": d["type"], "label": d["label"], "check": d["check"], "endpoints": running[d["check"]],
                    "techniques": sorted(d["techniques"])} for d in DETECTION_COVERAGE],
    }
