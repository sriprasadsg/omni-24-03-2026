"""A tenant's rings: the ordered groups of computers a rollout moves through (PTCH-02 groundwork).

A ring is a name, the agent groups that make it up, and its checks: how long it soaks, what share of
computers may fail, and how many must have reported before that share counts. The first ring is the
canary. Computers join a ring through the agent groups the tenant already has: a computer in the groups
of two rings joins the earlier one, and a computer in no ring's group joins the last ring (D-09).
Plan 84-06 adds validation and saving.

Raw Mongo handle with an explicit tenantId only.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from ..scope import raw
from . import DEFAULT_FAIL_PCT, DEFAULT_MIN_SAMPLE, DEFAULT_SOAK_HOURS, MAX_RINGS

logger = logging.getLogger(__name__)


@dataclass
class RingSetting:
    key: str
    name: str
    groupIds: List[str] = field(default_factory=list)
    soakHours: float = DEFAULT_SOAK_HOURS
    failPct: int = DEFAULT_FAIL_PCT
    minSample: int = DEFAULT_MIN_SAMPLE

    def snapshot(self, index: int) -> Dict[str, Any]:
        """The ring as a rollout stores it at Start."""
        return {"index": index, "key": self.key, "name": self.name, "groupIds": list(self.groupIds),
                "soakHours": self.soakHours, "failPct": self.failPct, "minSample": self.minSample,
                "isCanary": index == 0, "state": "not_started"}


@dataclass
class RolloutRings:
    rings: List[RingSetting] = field(default_factory=list)
    readable: bool = True


def _number(value: Any) -> Optional[float]:
    return None if isinstance(value, bool) or not isinstance(value, (int, float)) else value


def _parse(item: Any) -> Optional[RingSetting]:
    if not isinstance(item, dict) or not isinstance(item.get("key"), str) or not item["key"]:
        return None
    groups = item.get("groupIds", [])
    if not isinstance(groups, list) or any(not isinstance(g, str) or not g for g in groups):
        return None
    soak = _number(item.get("soakHours", DEFAULT_SOAK_HOURS))
    fail = _number(item.get("failPct", DEFAULT_FAIL_PCT))
    sample = _number(item.get("minSample", DEFAULT_MIN_SAMPLE))
    if soak is None or soak < 0 or fail is None or not 0 <= fail <= 100 or sample is None or sample < 1:
        return None
    return RingSetting(key=item["key"], name=str(item.get("name") or item["key"]), groupIds=list(groups),
                       soakHours=soak, failPct=int(fail), minSample=int(sample))


async def load(db, tenant_id: str) -> RolloutRings:
    """The tenant's saved rings. Nothing saved reads as no rings (readable); a setting this module cannot
    understand reads as unreadable, so a rollout is refused rather than started on a guess."""
    try:
        doc = await raw(db).patch_rollout_settings.find_one({"tenantId": tenant_id}, {"_id": 0, "rings": 1})
    except Exception as exc:
        logger.error("autonomous_ops: ring settings of %s unreadable: %s", tenant_id, exc)
        return RolloutRings(readable=False)
    if doc is None or doc.get("rings") is None:
        return RolloutRings()
    items = doc["rings"]
    if not isinstance(items, list) or len(items) > MAX_RINGS:
        return RolloutRings(readable=False)
    parsed = [_parse(i) for i in items]
    if any(p is None for p in parsed) or len({p.key for p in parsed}) != len(parsed):
        return RolloutRings(readable=False)
    return RolloutRings(rings=parsed)


async def membership(db, tenant_id: str, rings: List[RingSetting],
                     agent_ids: Optional[Iterable[str]] = None) -> Dict[str, int]:
    """{agent id: ring index}. A computer in the groups of two rings joins the earlier ring. With
    ``agent_ids``, a computer in no ring's group is placed in the last ring (D-09); without it, only
    grouped computers appear."""
    result: Dict[str, int] = {}
    for index in range(len(rings) - 1, -1, -1):          # later rings first, so the earlier ring wins
        if not rings[index].groupIds:
            continue
        found = raw(db).agent_group_members.find(
            {"tenantId": tenant_id, "group_id": {"$in": rings[index].groupIds}}, {"_id": 0, "agent_id": 1})
        async for row in found:
            if isinstance(row.get("agent_id"), str):
                result[row["agent_id"]] = index
    if agent_ids is not None and rings:
        for agent_id in agent_ids:
            result.setdefault(agent_id, len(rings) - 1)
    return result
