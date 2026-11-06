"""A tenant's rings: the ordered groups of computers a rollout moves through (PTCH-02 groundwork).

A ring is a name, the agent groups that make it up, and its checks: how long it soaks, what share of
computers may fail, and how many must have reported before that share counts. The first ring is the
canary. Computers join a ring through the agent groups the tenant already has: a computer in the groups
of two rings joins the earlier one, and a computer in no ring's group joins the last ring (D-09).
``validate`` and ``save`` (plan 84-06) check a person's rings against the tenant's own groups and write
them with one ledger row and one audit event. A rollout stores a snapshot of the rings at Start, so a later
edit never moves a computer of a running rollout.

Raw Mongo handle with an explicit tenantId only.
"""
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from .. import PLATFORM_TENANT_ID, ledger
from ..response_settings import PlatformTenantError
from ..scope import raw
from . import DEFAULT_FAIL_PCT, DEFAULT_MIN_SAMPLE, DEFAULT_SOAK_HOURS, MAX_RINGS, MIN_RINGS, messages, store

CANARY_KEY = "canary"
CANARY_NAME = "Canary"
MAX_NAME = 40
MIN_SOAK, MAX_SOAK = 1, 168
MIN_FAIL, MAX_FAIL = 1, 50
MIN_SAMPLE, MAX_SAMPLE = 1, 100
CONTROL_EVENT = "rollout_rings_saved"
_KEY = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")

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


# ---------------------------------------------------------------- validation and saving (plan 84-06)

class RingsError(ValueError):
    """A refused ring setting. ``detail`` is the sentence shown to the person (the route answers 422 with it)."""

    def __init__(self, code: str):
        self.code = code
        self.detail = messages.VALIDATION[code]
        super().__init__(self.detail)


class PlatformRingsError(RingsError, PlatformTenantError):
    """The platform organization has no rollout rings (PTCH-07)."""

    def __init__(self):
        PlatformTenantError.__init__(self)


_ABSENT = object()


def _whole(value: Any, low: int, high: int, default: int) -> Optional[int]:
    """An integer in [low, high], the default when the key is absent, else None. A bool, a string, a null or a
    fraction is refused."""
    if value is _ABSENT:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value):
        return None
    return int(value) if low <= value <= high else None


def _soak(value: Any) -> Optional[float]:
    if value is _ABSENT:
        return DEFAULT_SOAK_HOURS
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if MIN_SOAK <= value <= MAX_SOAK else None


async def validate(db, tenant_id: str, items: Any) -> List[RingSetting]:
    """The rings a person asked to save, checked, with a stable key per ring. Raises ``RingsError`` with the
    sentence for the first problem: not 2 to 4 rings, a renamed Canary, a missing or repeated or long name, a
    check outside its range, a ring (the Canary and every middle ring) with no group, a group in two rings, or a
    group that is not one of this tenant's own (another tenant's id and a deleted group read the same)."""
    if tenant_id == PLATFORM_TENANT_ID:
        raise PlatformRingsError()
    if not isinstance(items, list) or not MIN_RINGS <= len(items) <= MAX_RINGS \
            or any(not isinstance(i, dict) for i in items):
        raise RingsError("ring_count")
    seen_names, seen_groups, parsed = set(), set(), []
    for index, item in enumerate(items):
        name = item.get("name")
        if index == 0 and (name is None or (isinstance(name, str) and not name.strip())):
            name = CANARY_NAME
        if not isinstance(name, str) or not name.strip():
            raise RingsError("ring_name")
        name = name.strip()
        if index == 0 and name != CANARY_NAME:
            raise RingsError("canary_name")
        if len(name) > MAX_NAME:
            raise RingsError("ring_name_long")
        if name.casefold() in seen_names:
            raise RingsError("ring_names_unique")
        seen_names.add(name.casefold())
        groups = item.get("groupIds", [])
        if not isinstance(groups, list) or any(not isinstance(g, str) or not g for g in groups):
            raise RingsError("group_unknown")
        if len(set(groups)) != len(groups) or seen_groups & set(groups):
            raise RingsError("group_twice")
        seen_groups.update(groups)
        if not groups:
            if index == 0:
                raise RingsError("canary_group")
            if index != len(items) - 1:
                raise RingsError("ring_group")
        soak = _soak(item.get("soakHours", _ABSENT))
        fail = _whole(item.get("failPct", _ABSENT), MIN_FAIL, MAX_FAIL, DEFAULT_FAIL_PCT)
        sample = _whole(item.get("minSample", _ABSENT), MIN_SAMPLE, MAX_SAMPLE, DEFAULT_MIN_SAMPLE)
        if soak is None:
            raise RingsError("soak_hours")
        if fail is None:
            raise RingsError("fail_pct")
        if sample is None:
            raise RingsError("min_sample")
        parsed.append(RingSetting(key=_key_for(item.get("key"), index, {p.key for p in parsed}), name=name,
                                  groupIds=list(groups), soakHours=soak, failPct=fail, minSample=sample))
    if seen_groups:
        own = {g["id"] async for g in raw(db).agent_groups.find(
            {"tenantId": tenant_id, "id": {"$in": sorted(seen_groups)}}, {"_id": 0, "id": 1})}
        if seen_groups - own:
            raise RingsError("group_unknown")
    return parsed


def _key_for(wanted: Any, index: int, taken: set) -> str:
    """The first ring is always ``canary``; another ring keeps a well-formed key it already had, else gets a new one."""
    if index == 0:
        return CANARY_KEY
    if isinstance(wanted, str) and _KEY.match(wanted) and wanted != CANARY_KEY and wanted not in taken:
        return wanted
    key = f"ring-{uuid.uuid4().hex[:8]}"
    return key if key not in taken else _key_for(None, index, taken)


def _document(rings: List[RingSetting]) -> List[Dict[str, Any]]:
    return [{"key": r.key, "name": r.name, "groupIds": list(r.groupIds), "soakHours": r.soakHours,
             "failPct": r.failPct, "minSample": r.minSample} for r in rings]


def _recorded_actor(actor: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The actor as the ledger and the audit chain read it: ``username`` and ``display``."""
    actor = dict(actor or {})
    name = actor.get("display") or actor.get("name") or actor.get("username") or "unknown"
    actor.setdefault("username", actor.get("username") or name)
    actor["display"] = name
    return actor


async def save(db, tenant_id: str, items: Any, *, actor: Optional[Dict[str, Any]]) -> List[RingSetting]:
    """Check and store the tenant's rings, then write one control row (mirrored to the audit chain) naming the
    person. Nothing is written when the rings are refused. If the control row cannot be written the previous
    rings are put back and the error is raised: a safeguard is never changed without a record (PROH-83-09)."""
    rings = await validate(db, tenant_id, items)
    who = _recorded_actor(actor)
    now = datetime.now(timezone.utc)
    coll = store.settings_coll(db)
    before = await coll.find_one({"tenantId": tenant_id}, {"_id": 0})
    await coll.update_one(
        {"tenantId": tenant_id},
        {"$set": {"rings": _document(rings), "updatedAt": now,
                  "updatedBy": {"id": who.get("id"), "name": who["display"], "username": who["username"]}}},
        upsert=True)
    try:
        await ledger.record_control(
            db, tenant_id, CONTROL_EVENT, scope="tenant", actor=who,
            reason=messages.RINGS_SAVED.replace("{rings}", messages.plural(len(rings), "ring", "rings"))
            .replace("{names}", ", ".join(r.name for r in rings)))
    except Exception:
        logger.error("autonomous_ops: rollout rings of %s not recorded; restoring the previous rings", tenant_id)
        if before is None:
            await coll.delete_one({"tenantId": tenant_id})
        else:
            await coll.replace_one({"tenantId": tenant_id}, before)
        raise
    return rings


async def ring_names_by_group(db, tenant_id: str) -> Dict[str, str]:
    """{group id: ring name} for the groups the tenant's saved rings use. Nothing saved, or unreadable, is empty."""
    configured = await load(db, tenant_id)
    return {g: ring.name for ring in configured.rings for g in ring.groupIds}


async def resolve(db, tenant_id: str, rings: List[RingSetting]) -> List[RingSetting]:
    """The rings with any group that no longer exists (deleted since the rings were saved) taken out, so a
    deleted group never places a computer. Members of a deleted group are removed with it."""
    wanted = {g for r in rings for g in r.groupIds}
    if not wanted:
        return list(rings)
    live = {g["id"] async for g in raw(db).agent_groups.find(
        {"tenantId": tenant_id, "id": {"$in": sorted(wanted)}}, {"_id": 0, "id": 1})}
    return [RingSetting(key=r.key, name=r.name, groupIds=[g for g in r.groupIds if g in live],
                        soakHours=r.soakHours, failPct=r.failPct, minSample=r.minSample) for r in rings]
