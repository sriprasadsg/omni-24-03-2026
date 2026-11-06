"""Starting a rollout: check everything, snapshot the rings, then claim every computer atomically.

``preflight`` is the check the Start dialog shows (UI-SPEC section 3 and DEV-3): one row per check, each OK or a
blocker, in a fixed order (window, rings, canary per operating system, left out, offline, then Autonomous Ops,
stop, size and patches). ``start_rollout`` is called by a person, never the controller. It runs the same check
and refuses with ``PreflightBlocked`` (carrying the rows) when anything blocks, so nothing is claimed on a guess.

A computer is in the rollout when it is enrolled in this organization, has one of the chosen patches pending
and can take a rollout: Windows or Linux, a recent enough agent (it reports it can restart and its boot time),
patch installs switched on, not on the never-touch list, not busy with another patch job and not in another
active rollout. Every other computer with a chosen patch pending is LEFT OUT and listed with one reason, never
dropped silently (DEV-3, D-13). The platform's own computers are never offered: only this organization's own
agents are read, and the never-touch list holds the platform server (PTCH-07).

Claims are made one computer at a time in a fixed (agent id) order, so two Starts that overlap can never both
lose: the one that finds a computer held releases what it took, removes its rollout and raises
``AlreadyInRollout``. The unique partial index is the final guarantee (store.py).

Raw Mongo handle with an explicit tenantId only.
"""
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from .. import PLATFORM_TENANT_ID, agent_support, protected, settings
from ..scope import raw
from . import CAPABILITY, MAX_HOSTS_PER_ROLLOUT, MIN_RINGS, TOKEN_REBOOT, messages, rings as rings_mod, store
from . import windows as windows_mod

logger = logging.getLogger(__name__)

_KB = re.compile(r"^KB\d+$")
_AGENT_FIELDS = {"_id": 0, "id": 1, "tenantId": 1, "hostname": 1, "ipAddress": 1, "status": 1, "platform": 1,
                 "lastSeen": 1, "meta.response_actions": 1, "meta.response_state": 1,
                 "meta.system_patching": 1, "meta.os_patches": 1}
SHOWN_HOSTS = 10                      # computer names a row carries for its "Show hosts" list
OS_LABEL = {"windows": "Windows", "linux": "Linux"}
IN_ROLLOUT = "in_rollout"             # the reason code of a computer held by another rollout
FALLBACK_NAME = "another rollout"


class PreflightBlocked(Exception):
    """Start was refused by the check; ``rows`` are the preflight rows (the route answers 422 with them)."""

    def __init__(self, rows: List[Dict[str, Any]]):
        self.rows = rows
        first = next((r["detail"] for r in rows if r.get("blocker")), "")
        super().__init__(first)


class AlreadyInRollout(Exception):
    """Another Start took a computer first. Nothing of this Start is left claimed (the route answers 409)."""

    def __init__(self, left_out: List[str]):
        self.left_out = left_out
        super().__init__(messages.API_DETAIL["already_in_rollout"])


def refused(code: str, **extra: Any) -> Dict[str, Any]:
    return {"status": "refused", "reason": code, **extra}


def os_of(agent: Dict[str, Any]) -> Optional[str]:
    """"windows" or "linux" from the agent's platform text, else None."""
    text = str(agent.get("platform") or "").casefold()
    if "windows" in text:
        return "windows"
    return "linux" if "linux" in text else None


def pending_ids(agent: Dict[str, Any]) -> List[str]:
    """The installable ids the agent reports as pending (system patching scan and OS patch scan)."""
    from patch_core_endpoints import pending_entry_id
    meta = agent.get("meta") if isinstance(agent.get("meta"), dict) else {}
    found: List[str] = []
    for section, key in (("system_patching", "pending_updates"), ("os_patches", "items")):
        block = meta.get(section) if isinstance(meta.get(section), dict) else {}
        for entry in block.get(key) if isinstance(block.get(key), list) else []:
            patch_id = pending_entry_id(entry)
            if patch_id and patch_id not in found:
                found.append(patch_id)
    return found


def boot_time_of(agent: Dict[str, Any]) -> Optional[int]:
    meta = agent.get("meta") if isinstance(agent.get("meta"), dict) else {}
    state = meta.get("response_state") if isinstance(meta.get("response_state"), dict) else {}
    boot = state.get("boot_time")
    return boot if isinstance(boot, int) and not isinstance(boot, bool) else None


def _name(agent: Dict[str, Any]) -> str:
    return str(agent.get("hostname") or agent.get("id") or "")


# ---------------------------------------------------------------- which computers can take a rollout

@dataclass
class Classified:
    """Every computer of the tenant with a chosen patch pending, sorted into where it goes."""
    eligible: List[Dict[str, Any]] = field(default_factory=list)       # {"agent", "patchIds", "os"}
    cannot_take: List[Tuple[Dict[str, Any], str]] = field(default_factory=list)       # (agent, reason code)
    in_rollout: List[Tuple[Dict[str, Any], str, str]] = field(default_factory=list)   # (agent, rollout id, name)
    offline: List[Dict[str, Any]] = field(default_factory=list)
    known_ids: List[str] = field(default_factory=list)                 # every enrolled computer of the tenant


async def _busy_agents(db, tenant_id: str) -> set:
    """Computers with a patch job still waiting on them (the same rule the patch screen uses)."""
    busy: set = set()
    jobs = raw(db).patch_deployment_jobs.find({"tenantId": tenant_id, "status": "In Progress"},
                                              {"_id": 0, "dispatchedAgents": 1, "agentResults": 1})
    async for job in jobs:
        reported = job.get("agentResults") if isinstance(job.get("agentResults"), dict) else {}
        for agent_id in job.get("dispatchedAgents") or []:
            if isinstance(agent_id, str) and agent_id.replace(".", "_").replace("$", "_") not in reported:
                busy.add(agent_id)
    return busy


async def _held_elsewhere(db, tenant_id: str) -> Dict[str, Tuple[str, str]]:
    """{agent id: (rollout id, rollout name)} for computers an active rollout holds."""
    held: Dict[str, str] = {}
    async for claim in store.hosts(db).find({"tenantId": tenant_id, "active": True},
                                            {"_id": 0, "agentId": 1, "rolloutId": 1}):
        held[claim["agentId"]] = claim["rolloutId"]
    if not held:
        return {}
    names: Dict[str, str] = {}
    async for doc in store.rollouts(db).find({"tenantId": tenant_id, "id": {"$in": sorted(set(held.values()))}},
                                             {"_id": 0, "id": 1, "name": 1}):
        names[doc["id"]] = str(doc.get("name") or "").strip() or FALLBACK_NAME
    return {a: (r, names.get(r, FALLBACK_NAME)) for a, r in held.items()}


async def classify_hosts(db, tenant_id: str, patch_ids: List[str], *, now: datetime) -> Classified:
    """Sort the tenant's computers that have one of ``patch_ids`` pending. Only this organization's own agents are
    read, so a computer of the platform (or of any other organization) is never offered even when a group lists
    it. A reason is decided in a fixed order: unsupported system, never-touch, agent too old, patch installs off,
    held by another rollout, busy. The never-touch list failing to read propagates: nothing starts on a guess."""
    from agent_capabilities import allowed_for
    result = Classified()
    wanted = set(patch_ids)
    permitted = await allowed_for(db, tenant_id)
    busy = await _busy_agents(db, tenant_id)
    held = await _held_elsewhere(db, tenant_id)
    found = raw(db).agents.find({"tenantId": tenant_id}, _AGENT_FIELDS)
    agents = sorted([a async for a in found if a.get("tenantId") == tenant_id and a.get("id")
                     and str(a.get("status") or "").casefold() != "uninstalled"],
                    key=lambda a: (_name(a).casefold(), a["id"]))
    for agent in agents:
        result.known_ids.append(agent["id"])
        applicable = [p for p in pending_ids(agent) if p in wanted]
        if not applicable:
            continue
        if os_of(agent) is None:
            result.cannot_take.append((agent, "unsupported_os"))
        elif await protected.check(db, tenant_id, agent=agent):
            result.cannot_take.append((agent, "never_touch"))
        elif TOKEN_REBOOT not in agent_support.tokens_of(agent) or boot_time_of(agent) is None:
            result.cannot_take.append((agent, "agent_too_old"))
        elif CAPABILITY not in permitted:
            result.cannot_take.append((agent, "capability_off"))
        elif agent["id"] in held:
            result.in_rollout.append((agent, *held[agent["id"]]))
        elif agent["id"] in busy:
            result.cannot_take.append((agent, "busy"))
        else:
            result.eligible.append({"agent": agent, "patchIds": applicable, "os": os_of(agent)})
            if not agent_support.online(agent, now):
                result.offline.append(agent)
    return result


# ---------------------------------------------------------------- the check

def _row(check: str, ok: bool, detail: str, *, blocker: bool = False, link: Optional[str] = None,
         hosts: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    titles = messages.PREFLIGHT["titles"]
    names = sorted((_name(h) for h in hosts or []), key=str.casefold)
    return {"check": check, "ok": ok, "blocker": blocker,
            "title": titles.get(check, titles["autonomous_ops"]), "detail": detail, "link": link,
            "hosts": names[:SHOWN_HOSTS], "hostTotal": len(names)}


def _when(moment: datetime, zone: str) -> str:
    local = store.aware(moment).astimezone(ZoneInfo(zone))
    return f"{local:%a} {local.day} {local:%b}, {local:%H:%M}"


@dataclass
class Assessment:
    rows: List[Dict[str, Any]] = field(default_factory=list)
    claims: List[Dict[str, Any]] = field(default_factory=list)      # host documents to claim, sorted by agent id
    left_out: List[Dict[str, Any]] = field(default_factory=list)
    rings: List[rings_mod.RingSetting] = field(default_factory=list)
    next_window: Optional[str] = None
    shadow: bool = False

    @property
    def first_blocker(self) -> Optional[str]:
        return next((r["detail"] for r in self.rows if r["blocker"]), None)

    def as_dict(self) -> Dict[str, Any]:
        return {"rows": self.rows, "canStart": self.first_blocker is None, "firstBlocker": self.first_blocker,
                "nextWindowText": self.next_window}


def _left_out_entries(found: Classified) -> List[Dict[str, Any]]:
    entries = [{"agentId": a["id"], "hostname": a.get("hostname"), "reason": code, "rolloutName": None}
               for a, code in found.cannot_take]
    entries += [{"agentId": a["id"], "hostname": a.get("hostname"), "reason": IN_ROLLOUT, "rolloutName": name}
                for a, _, name in found.in_rollout]
    return sorted(entries, key=lambda e: e["agentId"])


async def _assess(db, tenant_id: str, ids: List[str], now: datetime) -> Assessment:
    """The check, row by row, and the hosts a Start would claim."""
    out = Assessment()
    tenant = await settings.load(db, tenant_id)
    out.shadow, _ = settings.shadow_state(tenant)
    # 1. Window (D-03): none, unreadable, or none coming up reads the same.
    tenant_windows = await windows_mod.load(db, tenant_id)
    upcoming = None
    if tenant_windows.readable and tenant_windows.windows:
        if tenant_windows.open_at(now) is not None:
            upcoming = now                                  # open now: the first install can run right away
        else:
            coming = windows_mod.next_open(tenant_windows.windows, tenant_windows.zone, now)
            upcoming = coming[0] if coming else None
    if upcoming is None:
        out.rows.append(_row("window", False, messages.PREFLIGHT["window_blocker"], blocker=True, link="maintenance"))
    else:
        out.next_window = f"{_when(upcoming, tenant_windows.zone)} ({tenant_windows.zone})"
        out.rows.append(_row("window", True, messages.fill(messages.PREFLIGHT["window_ok"], opens=_when(
            upcoming, tenant_windows.zone), zone=tenant_windows.zone)))
    found = await classify_hosts(db, tenant_id, ids, now=now)
    # 2. Rings (D-09) and the canary computers per operating system (D-12).
    configured = await rings_mod.load(db, tenant_id)
    placement: Dict[str, int] = {}
    if not configured.readable:
        out.rows.append(_row("rings", False, messages.API_DETAIL["rings_unreadable"], blocker=True, link="rings"))
    elif len(configured.rings) < MIN_RINGS:
        out.rows.append(_row("rings", False, messages.PREFLIGHT["rings_not_set"], blocker=True, link="rings"))
    else:
        out.rings = await rings_mod.resolve(db, tenant_id, configured.rings)
        enrolled = set(found.known_ids)
        explicit = await rings_mod.membership(db, tenant_id, out.rings)
        if not any(index == 0 and agent_id in enrolled for agent_id, index in explicit.items()):
            out.rings = []
            out.rows.append(_row("rings", False, messages.PREFLIGHT["canary_empty"], blocker=True, link="rings"))
        else:
            placement = await rings_mod.membership(db, tenant_id, out.rings, [e["agent"]["id"] for e in found.eligible])
            counts = [0] * len(out.rings)
            for entry in found.eligible:
                counts[placement[entry["agent"]["id"]]] += 1
            breakdown = ", ".join(f"{r.name} {n}" for r, n in zip(out.rings, counts))
            out.rows.append(_row("rings", True, messages.fill(
                messages.PREFLIGHT["rings_ok"], computers=messages.plural(len(found.eligible), "computer", "computers"),
                rings=messages.plural(len(out.rings), "ring", "rings"), breakdown=breakdown)))
            canary_groups = await _group_names(db, tenant_id, out.rings[0].groupIds)
            for os_name in ("windows", "linux"):
                covered = [e for e in found.eligible if e["os"] == os_name]
                if not covered:
                    continue
                if any(placement[e["agent"]["id"]] == 0 for e in covered):
                    out.rows.append(_row("canary", True, messages.fill(messages.PREFLIGHT["canary_ok"],
                                                                      os=OS_LABEL[os_name])))
                else:
                    out.rows.append(_row("canary", False, messages.canary_os_gap(OS_LABEL[os_name], canary_groups),
                                         blocker=True, link="agentGroups"))
    # 3. Left out: by rollout first (D-13), then the computers that cannot take one (DEV-3).
    by_rollout: Dict[str, List[Dict[str, Any]]] = {}
    for agent, _, name in found.in_rollout:
        by_rollout.setdefault(name, []).append(agent)
    for name in sorted(by_rollout, key=str.casefold):
        out.rows.append(_row("left_out", True, messages.left_out(len(by_rollout[name]), name), hosts=by_rollout[name]))
    by_reason: Dict[str, List[Dict[str, Any]]] = {}
    for agent, code in found.cannot_take:
        by_reason.setdefault(code, []).append(agent)
    for code in messages.CANNOT_TAKE:
        if code in by_reason:
            out.rows.append(_row("left_out", True, messages.CANNOT_TAKE[code], hosts=by_reason[code]))
    out.left_out = _left_out_entries(found)
    # 4. Offline now: still in the rollout; the controller waits for them.
    if found.offline:
        out.rows.append(_row("offline", True, messages.offline_now(len(found.offline)), hosts=found.offline))
    # 5. Blockers the dialog does not list as checks: Autonomous Ops off, a stop, size, patches.
    if tenant_id == PLATFORM_TENANT_ID:
        out.rows.append(_row("autonomous_ops", False, messages.API_DETAIL["platform_tenant"], blocker=True))
    elif settings.effective_level(tenant) == "off":
        out.rows.append(_row("autonomous_ops", False, messages.PREFLIGHT["autonomy_off"], blocker=True))
    if await _stopped(db, tenant):
        out.rows.append(_row("stopped", False, messages.PREFLIGHT["stopped"], blocker=True))
    if len(found.eligible) > MAX_HOSTS_PER_ROLLOUT:
        out.rows.append(_row("cap", False, messages.PREFLIGHT["cap"], blocker=True))
    if not ids:
        out.rows.append(_row("patches", False, messages.VALIDATION["patches"], blocker=True))
    elif not found.eligible:
        out.rows.append(_row("patches", False, messages.PREFLIGHT["nothing_pending"], blocker=True))
    if placement:
        out.claims = [{"agentId": e["agent"]["id"], "ring": placement[e["agent"]["id"]], "state": "waiting",
                       "os": e["os"], "hostname": e["agent"].get("hostname"), "patchIds": e["patchIds"],
                       "attempt": 0, "createdAt": now}
                      for e in sorted(found.eligible, key=lambda e: e["agent"]["id"])]
    return out


async def _group_names(db, tenant_id: str, group_ids: List[str]) -> List[str]:
    names = {g["id"]: g.get("name") or g["id"] async for g in raw(db).agent_groups.find(
        {"tenantId": tenant_id, "id": {"$in": list(group_ids)}}, {"_id": 0, "id": 1, "name": 1})}
    return [str(names[g]) for g in group_ids if g in names]


async def _stopped(db, tenant: settings.TenantSettings) -> bool:
    """A stop of the organization or of the whole platform. An unreadable platform stop counts as stopped."""
    if settings.stop_active(tenant.stop):
        return True
    try:
        return settings.stop_active(await settings.platform_stop(db))
    except Exception as exc:
        logger.error("autonomous_ops: the platform stop could not be read, treating it as on: %s", exc)
        return True


def _clean_ids(patch_ids: Any) -> Optional[List[str]]:
    """The chosen ids as installable ids (de-duplicated), or None when one of them is not installable."""
    from patch_core_endpoints import installable_patch_id
    ids = [installable_patch_id(p) for p in patch_ids] if isinstance(patch_ids, list) else []
    if any(i is None for i in ids):
        return None
    return list(dict.fromkeys(ids))


async def preflight(db, tenant_id: str, patch_ids: List[str], *, now: Optional[datetime] = None) -> Dict[str, Any]:
    """The check before Start: ``{"rows", "canStart", "firstBlocker", "nextWindowText"}``. Reads only; claims
    nothing. An id that is not an installable patch is a blocker on the patches row."""
    now = store.aware(now or datetime.now(timezone.utc))
    ids = _clean_ids(patch_ids)
    if ids is None:
        out = Assessment(rows=[_row("patches", False, messages.VALIDATION["patches"], blocker=True)])
        return out.as_dict()
    return (await _assess(db, tenant_id, ids, now)).as_dict()


# ---------------------------------------------------------------- Start

async def start_rollout(db, tenant_id: str, *, name: str, patch_ids: List[str], actor: Dict[str, Any],
                        now: Optional[datetime] = None) -> Dict[str, Any]:
    """Start a rollout. Returns ``{"status": "started", "rolloutId", "claimed", "leftOut"}`` or, for the platform
    organization and for ids that are not installable patches, ``{"status": "refused", "reason"}``. Raises
    ``PreflightBlocked`` when the check has a blocker and ``AlreadyInRollout`` when another Start took a computer
    first. Nothing is installed here: the controller does that, inside a window."""
    now = store.aware(now or datetime.now(timezone.utc))
    if not isinstance(tenant_id, str) or not tenant_id or tenant_id == PLATFORM_TENANT_ID:
        return refused("platform_tenant")
    ids = _clean_ids(patch_ids)
    if not ids:
        return refused("invalid_patch_ids")
    plan = await _assess(db, tenant_id, ids, now)
    if plan.first_blocker is not None:
        raise PreflightBlocked(plan.rows)
    rollout_id = uuid.uuid4().hex
    claimed: List[str] = []
    try:
        for doc in plan.claims:                           # one at a time, in agent id order: see the module note
            got, lost = await store.claim_hosts(db, tenant_id, rollout_id, [doc])
            if lost:
                await store.discard(db, tenant_id, rollout_id)
                raise AlreadyInRollout(lost)
            claimed += got
        await store.rollouts(db).insert_one({
            "id": rollout_id, "tenantId": tenant_id, "name": str(name or "").strip()[:120], "patchIds": ids,
            "patchesByOs": {"windows": [i for i in ids if _KB.match(i)], "linux": [i for i in ids if not _KB.match(i)]},
            "status": "running", "shadow": plan.shadow, "currentRing": 0,
            "rings": [r.snapshot(i) for i, r in enumerate(plan.rings)], "leftOut": plan.left_out,
            "createdAt": now, "createdBy": {"id": (actor or {}).get("id"), "name": (actor or {}).get("name")}})
    except AlreadyInRollout:
        raise
    except Exception:
        await store.discard(db, tenant_id, rollout_id)
        raise
    return {"status": "started", "rolloutId": rollout_id, "claimed": claimed, "leftOut": plan.left_out}
