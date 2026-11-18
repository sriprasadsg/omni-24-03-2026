"""Across-endpoint correlation: the same file hash, public IP, MITRE technique or detection seen on two or
more endpoints of a tenant in the last days, grouped as one campaign (incidents stay per endpoint).

Computed when asked, from active and recent alerts; a detection is keyed by its type and its title with
agent ids and numbers removed, so "Unusual Login Time" on three hosts is one campaign.
"""
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from soc_alerts import SEVERITIES
from soc_service import TECHNIQUE_NAMES, scope_filter, view

_NOISE = re.compile(r"agent-[0-9a-f]{8,}|\b[0-9a-f]{12,}\b|\d+")
RANK = {s: i for i, s in enumerate(SEVERITIES)}


def keys_of(alert: Dict[str, Any]) -> List[tuple]:
    import soc_response
    ev = soc_response.evidence(alert.get("_doc") or {})
    out = []
    if ev.get("sha256"):
        out.append(("hash", ev["sha256"], f"File {ev['sha256'][:12]}…"))
    if ev.get("ip"):
        out.append(("ip", ev["ip"], f"IP {ev['ip']}"))
    for t in alert.get("mitre") or []:
        out.append(("technique", t, f"{t} {TECHNIQUE_NAMES.get(t, ('', ''))[0]}".strip()))
    title = " ".join(_NOISE.sub(" ", str(alert.get("title") or "")).split())
    out.append(("detection", f"{alert.get('type')}|{title.lower()}", title or alert.get("typeLabel")))
    return out


async def campaigns(db, scope: Optional[str], days: int = 7) -> List[Dict[str, Any]]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    docs = await db.security_alerts.find({**scope_filter(scope), "status": {"$nin": ["merged", "archived"]},
                                          "$or": [{"status": {"$in": ["open", "new", "acknowledged"]}}, {"created_at": {"$gte": since}}]},
                                         {"_id": 0}).to_list(5000)
    groups: Dict[tuple, Dict[str, Any]] = defaultdict(lambda: {"agents": set(), "alerts": []})
    for d in docs:
        v = {**view(d), "_doc": d}
        if not v.get("agentId"):
            continue
        for kind, key, label in keys_of(v):
            g = groups[(v.get("tenantId"), kind, key)]
            g.update(kind=kind, key=key, label=label, tenantId=v.get("tenantId"))
            g["agents"].add(v["agentId"])
            g["alerts"].append(v)
    hosts = {a["id"]: a.get("hostname") for a in await db.agents.find(scope_filter(scope), {"_id": 0, "id": 1, "hostname": 1}).to_list(5000)}
    out = []
    for g in groups.values():
        if len(g["agents"]) < 2:
            continue
        alerts = sorted(g["alerts"], key=lambda a: str(a.get("createdAt") or ""))
        out.append({"kind": g["kind"], "key": g["key"], "label": g["label"], "tenantId": g["tenantId"],
                    "endpoints": [{"agentId": a, "hostname": hosts.get(a) or a} for a in sorted(g["agents"])],
                    "alertCount": len(alerts), "severity": min((a["severity"] for a in alerts), key=lambda s: RANK.get(s, 9)),
                    "active": sum(1 for a in alerts if a["status"] != "closed"),
                    "firstAt": alerts[0].get("createdAt"), "lastAt": alerts[-1].get("lastSeenAt") or alerts[-1].get("createdAt"),
                    "alertIds": [a["id"] for a in alerts][:50]})
    order = {"hash": 0, "ip": 1, "technique": 2, "detection": 3}
    out.sort(key=lambda c: (-len(c["endpoints"]), RANK.get(c["severity"], 9), order[c["kind"]], -c["alertCount"]))
    return out[:50]
