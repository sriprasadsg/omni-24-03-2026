"""What the Start dialog and the Rollout rings card read (plan 84-09, PTCH-01, D-11).

* ``pending_patches``: patches waiting on at least one computer that can take a rollout, with the OS and a computer
  count, filtered by a search text and paged by 50 (UI-SPEC section 3).
* ``draft``: a vulnerability suggestion of the caller's organization turned into a name and a patch list. It reads
  and stores nothing: only a person pressing Start creates a rollout (PROH-84-01). A suggested patch that is no
  longer pending on its computer is dropped and counted.
* ``rings_settings``: the saved rings and the organization's groups with the ring each belongs to.

Raw Mongo handle with an explicit tenantId only; reads only.
"""
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from .. import PLATFORM_TENANT_ID, ledger
from ..scope import raw
from . import messages as rm, rings as rings_mod, start

PAGE = 50
NAME_MAX = 60
TITLE_CAP = 200
SUGGESTION_RULE = "sweep:suggest_vulnerability"
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def _text(value: Any, cap: int = TITLE_CAP) -> str:
    return _CONTROL.sub(" ", value).strip()[:cap] if isinstance(value, str) else ""


def _titles(agent: Dict[str, Any]) -> Dict[str, str]:
    """{patch id: title} for the updates an agent reports as pending (a plain id is its own title)."""
    from patch_core_endpoints import pending_entry_id
    meta = agent.get("meta") if isinstance(agent.get("meta"), dict) else {}
    found: Dict[str, str] = {}
    for section, key in (("system_patching", "pending_updates"), ("os_patches", "items")):
        block = meta.get(section) if isinstance(meta.get(section), dict) else {}
        for entry in block.get(key) if isinstance(block.get(key), list) else []:
            patch_id = pending_entry_id(entry)
            if patch_id and patch_id not in found:
                title = _text(entry.get("title") or entry.get("name")) if isinstance(entry, dict) else ""
                found[patch_id] = title or patch_id
    return found


async def _tenant_agents(db, tenant_id: str) -> List[Dict[str, Any]]:
    found = raw(db).agents.find({"tenantId": tenant_id}, start._AGENT_FIELDS)
    return [a async for a in found if a.get("tenantId") == tenant_id and a.get("id")]


async def pending_patches(db, tenant_id: str, *, search: str = "", offset: int = 0, limit: int = PAGE,
                          now: datetime) -> Dict[str, Any]:
    page = {"items": [], "total": 0, "offset": offset, "limit": limit}
    if tenant_id == PLATFORM_TENANT_ID:
        return page
    agents = await _tenant_agents(db, tenant_id)
    wanted = sorted({p for a in agents for p in start.pending_ids(a)})
    if not wanted:
        return page
    classified = await start.classify_hosts(db, tenant_id, wanted, now=now)
    by_id = {a["id"]: a for a in agents}
    patches: Dict[str, Dict[str, Any]] = {}
    for entry in classified.eligible:
        titles = _titles(by_id[entry["agent"]["id"]])
        for patch_id in entry["patchIds"]:
            row = patches.setdefault(patch_id, {"patchId": patch_id, "title": titles.get(patch_id, patch_id),
                                                "os": entry["os"], "computers": 0})
            row["computers"] += 1
    needle = _text(search, 100).casefold()
    rows = sorted((r for r in patches.values() if not needle or needle in r["patchId"].casefold()
                   or needle in r["title"].casefold()), key=lambda r: (-r["computers"], r["patchId"].casefold()))
    page.update(items=rows[offset:offset + limit], total=len(rows))
    return page


async def draft(db, tenant_id: str, suggestion_id: str) -> Optional[Dict[str, Any]]:
    """The draft for a vulnerability suggestion of this organization, or None when there is no such suggestion
    (another organization's id reads the same). Nothing is written."""
    from patch_core_endpoints import installable_patch_id
    row = await ledger.get(db, tenant_id, suggestion_id)
    reason = (row or {}).get("reason") if isinstance((row or {}).get("reason"), dict) else {}
    inputs = reason.get("inputs") if isinstance(reason.get("inputs"), dict) else {}
    found = inputs.get("suggestion") if isinstance(inputs.get("suggestion"), dict) else {}
    targets = (row or {}).get("targets") or []
    if row is None or reason.get("ruleId") != SUGGESTION_RULE or found.get("kind") != "vulnerability" or not targets:
        return None
    agent = await raw(db).agents.find_one({"id": targets[0], "tenantId": tenant_id}, start._AGENT_FIELDS)
    if agent is None:
        return None
    items = [i for i in found.get("items") or [] if isinstance(i, dict)]
    packages = list(dict.fromkeys(_text(i.get("package"), 200) for i in items if _text(i.get("package"), 200)))
    pending = set(start.pending_ids(agent))
    kept = [p for p in dict.fromkeys(installable_patch_id(p) for p in packages) if p and p in pending]
    cves = list(dict.fromkeys(_text(i.get("cve"), 64) for i in items if _text(i.get("cve"), 64)))
    host = _text(agent.get("hostname")) or agent["id"]
    name = (rm.fill(rm.DRAFT_NAME["cve"], cve=cves[0], host=host) if len(cves) == 1
            else rm.fill(rm.DRAFT_NAME["many"], host=host))[:NAME_MAX]
    return {"name": name, "patchIds": kept, "removedCount": len(packages) - len(kept), "host": host, "cves": cves}


async def rings_settings(db, tenant_id: str) -> Dict[str, Any]:
    """The saved rings, whether they could be read, and the organization's groups with their computer count and the
    ring each one is in (null for a group no ring uses)."""
    if tenant_id == PLATFORM_TENANT_ID:
        return {"rings": [], "readable": True, "groups": []}
    saved = await rings_mod.load(db, tenant_id)
    ring_of = {g: ring.name for ring in saved.rings for g in ring.groupIds}
    members = {m["_id"]: m["n"] async for m in raw(db).agent_group_members.aggregate(
        [{"$match": {"tenantId": tenant_id}}, {"$group": {"_id": "$group_id", "n": {"$sum": 1}}}])}
    groups = [{"id": g["id"], "name": str(g.get("name") or g["id"]), "computers": int(members.get(g["id"], 0)),
               "ring": ring_of.get(g["id"])}
              async for g in raw(db).agent_groups.find({"tenantId": tenant_id}, {"_id": 0, "id": 1, "name": 1})]
    return {"rings": [{"key": r.key, "name": r.name, "groupIds": list(r.groupIds), "soakHours": r.soakHours,
                       "failPct": r.failPct, "minSample": r.minSample} for r in saved.rings],
            "readable": saved.readable, "groups": sorted(groups, key=lambda g: (g["name"].casefold(), g["id"]))}
