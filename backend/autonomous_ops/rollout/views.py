"""Payload builders for the Rollouts tab (plan 84-09, PTCH-01, PTCH-04, PTCH-05).

Every field name matches services/patchRollouts/types.ts. The server writes every sentence a person reads (they come
from ``messages``; nothing is composed here beyond filling a template) and decides every control: ``canStart``,
``canResume`` and the rest are computed from the caller's permissions and the stored state, and the browser never
infers a permission (T-84-32). A halt block counts a revert only when a computer recorded it (PROH-84-02).

A page lists halted rollouts first, then those waiting for approval, running, waiting for a window, and finished
ones newest first; a finished rollout older than 30 days is not listed (R7). Raw Mongo handle with an explicit
tenantId only; reads only.
"""
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import rbac_defaults

from .. import PLATFORM_TENANT_ID, SCREEN_PERMISSION, response_settings, settings, views as ops_views
from ..scope import raw
from . import MIN_RINGS, RING_STATES, messages as rm, rings as rings_mod, store, windows as windows_mod

MANAGE_PERMISSION = "manage:patches"
HOST_PAGE = 25                         # computers a ring carries in its first page
LISTED_FOR = timedelta(days=30)        # a finished rollout is listed this long (R7)
EXCLUDED = ("not_reached", "left_out")
INSTALLED = ("installed", "restarting", "healthy")
PROBLEMS = ("failed", "not_reverted")
RANK = {"halted": 0, "waiting_for_approval": 1, "running": 2, "waiting_for_window": 3}
ATTENTION = ("halted", "waiting_for_approval")
_STATES = {"waiting", "installing", "installed", "restarting", "healthy", "failed", "reverting", "reverted",
           "not_reverted", "not_reached", "left_out", "would_install", "would_restart"}


@dataclass
class RolloutCaller:
    tenant_id: str
    interactive: bool
    can_manage_patches: bool
    can_open_decisions: bool
    platform_tenant: bool


async def build_caller(user, tenant_id: str, tenant: settings.TenantSettings) -> RolloutCaller:
    """What the caller may do with rollouts; permissions are the role's, narrowed by an API key's scopes."""
    support = rbac_defaults.platform_tier(getattr(user, "role", None)) == "support"
    platform = tenant_id == PLATFORM_TENANT_ID
    return RolloutCaller(
        tenant_id=tenant_id, interactive=ops_views.is_interactive(user), platform_tenant=platform,
        can_manage_patches=(not support) and await ops_views.holds(user, MANAGE_PERMISSION),
        can_open_decisions=(not platform) and bool(tenant.eligible) and await ops_views.holds(user, SCREEN_PERMISSION))


async def stop_state(db, tenant: settings.TenantSettings) -> Tuple[bool, Optional[str]]:
    """(stopped, scope). An unreadable platform stop counts as stopped, as the check before Start does."""
    try:
        if settings.stop_active(await settings.platform_stop(db)):
            return True, "platform"
    except Exception:
        return True, "platform"
    return (True, "tenant") if settings.stop_active(tenant.stop) else (False, None)


async def flags(db, caller, tenant: settings.TenantSettings) -> Dict[str, Any]:
    stopped, scope = await stop_state(db, tenant)
    can_act = bool(caller.can_manage_patches and caller.interactive and not caller.platform_tenant)
    return {"canStart": can_act and not stopped, "canManageRings": can_act,
            "canOpenDecisions": bool(caller.can_open_decisions), "shadow": settings.shadow_state(tenant)[0],
            "stopped": stopped, "stopScope": scope, "platformTenant": bool(caller.platform_tenant)}


# ---------------------------------------------------------------- small helpers

def _iso(value: Any) -> Optional[str]:
    moment = store.parse_time(value)
    return moment.isoformat() if moment else None


def _computers(n: int) -> str:
    return rm.plural(n, "computer", "computers")


def _patches(ids: Any) -> str:
    return rm.plural(len(ids) if isinstance(ids, list) else 0, "patch", "patches")


def _names(items: List[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _hours(value: Any) -> str:
    return str(int(value)) if float(value) == int(value) else str(value)


def _changed(host: Dict[str, Any]) -> Optional[Any]:
    times = [t for t in (store.parse_time(host.get(k)) for k in
                         ("changedAt", "revertedAt", "notReachedAt", "newBootAt", "installReportedAt")) if t]
    return max(times) if times else None


@dataclass
class Context:
    """What one page of cards shares: the caller, the zone, the next window and the group and service names."""
    caller: Any
    zone: str = "UTC"
    opens: Optional[datetime] = None
    names: Dict[str, str] = field(default_factory=dict)
    watched: List[str] = field(default_factory=list)


async def _group_names(db, tenant_id: str, ids) -> Dict[str, str]:
    wanted = sorted({g for g in ids if isinstance(g, str)})
    if not wanted:
        return {}
    found = raw(db).agent_groups.find({"tenantId": tenant_id, "id": {"$in": wanted}}, {"_id": 0, "id": 1, "name": 1})
    return {g["id"]: str(g.get("name") or g["id"]) async for g in found}


async def context_for(db, tenant_id: str, rollouts: List[Dict[str, Any]], caller, now: datetime) -> Context:
    ctx = Context(caller=caller)
    tw = await windows_mod.load(db, tenant_id)
    ctx.zone = tw.zone if tw.readable else "UTC"
    if tw.readable and tw.windows:
        ctx.opens = now if tw.open_at(now) else next(iter(windows_mod.next_open(tw.windows, tw.zone, now) or ()), None)
    ctx.names = await _group_names(db, tenant_id, (g for r in rollouts for ring in r.get("rings") or []
                                                   for g in ring.get("groupIds") or []))
    try:
        stored = await response_settings.load(db, tenant_id)
        ctx.watched = list(stored.watched_services) if stored.readable else []
    except Exception:
        ctx.watched = []
    return ctx


# ---------------------------------------------------------------- computers

def _result(host: Dict[str, Any], zone: str, now: datetime) -> str:
    state, table = host.get("state"), rm.HOST_RESULT
    at = windows_mod.clock_text(_changed(host) or now, zone)
    if state == "installing":
        return rm.fill(table["installing"], patches=_patches(host.get("patchIds")))
    if state == "installed":
        return rm.fill(table["installed"], patches=_patches(host.get("installedIds") or host.get("patchIds")))
    if state == "healthy":
        return rm.fill(table["healthy"], at=at)
    if state == "failed":
        if host.get("failureCode") == "no_new_boot":
            return table["failed_no_heartbeat"]
        left = [p for p in host.get("patchIds") or [] if p not in (host.get("installedIds") or [])]
        message = str(host.get("failureMessage") or "").strip().rstrip(".")
        return rm.fill(table["failed_install"], patch=", ".join(left[:3]) or "The patch", message=message)
    if state in ("reverted", "reverting"):
        return rm.fill(table[state], patches=_patches(host.get("installedIds")), at=at)
    if state == "not_reverted":
        return rm.NOT_REVERTED.get(host.get("notRevertedReason"), rm.NOT_REVERTED_OTHER)
    if state in ("would_install", "would_restart"):
        return rm.fill(table[state], patches=_patches(host.get("patchIds")))
    if state in ("restarting", "not_reached"):
        return table[state]
    if state == "left_out":
        return rm.fill(table["left_out"], other=host.get("otherRollout") or "another rollout")
    return table["waiting_approval" if host.get("waitReason") == "approval" else "waiting_window"]


def host_rows(hosts: List[Dict[str, Any]], zone: str = "UTC", now: Optional[datetime] = None,
              limit: int = HOST_PAGE) -> Tuple[List[Dict[str, Any]], int]:
    """The ring's first page of computers, problems first (Failed, Not reverted), then Waiting, then by name."""
    now = now or datetime.now(timezone.utc)

    def order(h):
        rank = 0 if h.get("state") in PROBLEMS else 1 if h.get("state") == "waiting" else 2
        return rank, str(h.get("hostname") or "").casefold(), str(h.get("agentId") or "")
    rows = [{"agentId": h["agentId"], "hostname": str(h.get("hostname") or h["agentId"]), "os": str(h.get("os") or ""),
             "state": h.get("state") if h.get("state") in _STATES else "waiting", "result": _result(h, zone, now),
             "changedAt": _iso(_changed(h))} for h in sorted(hosts, key=order)[:limit]]
    return rows, len(hosts)


def halt_block(rollout: Dict[str, Any], hosts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The halt reason and the revert lines. A line counts only what the computers recorded: reverted when the
    agent reported success, could not be reverted with the reason it gave, reverting while a result is pending."""
    reason = rollout.get("haltReason") if isinstance(rollout.get("haltReason"), dict) else {}
    rings = rollout.get("rings") or [{}]
    index = int(reason.get("ring", rollout.get("currentRing") or 0))
    index = index if 0 <= index < len(rings) else 0
    mine = [h for h in hosts if h.get("ring") == index]
    count = lambda state: sum(1 for h in mine if h.get("state") == state)  # noqa: E731
    lines, table = [], rm.REVERT_SUMMARY
    if count("reverting"):
        lines.append(rm.fill(table["running"], computers=_computers(count("reverting"))))
    if count("reverted"):
        lines.append(rm.fill(table["done"], computers=_computers(count("reverted"))))
    stuck: Dict[Any, int] = {}
    for h in mine:
        if h.get("state") == "not_reverted":
            stuck[h.get("notRevertedReason")] = stuck.get(h.get("notRevertedReason"), 0) + 1
    for code in sorted(stuck, key=lambda c: (c not in rm.NOT_REVERTED_REASON, str(c))):
        known = code in rm.NOT_REVERTED_REASON
        lines.append(rm.forms(stuck[code], table["could_not" if known else "could_not_other"],
                              computers=_computers(stuck[code]), reason=rm.NOT_REVERTED_REASON.get(code, "")))
    restart = sum(1 for h in mine if h.get("revertRebootNeeded"))
    if restart:
        lines.append(rm.fill(table["needs_restart"], computers=_computers(restart)))
    return {"ringName": str(rings[index].get("name") or ""), "reason": str(reason.get("text") or ""), "reverts": lines}


# ---------------------------------------------------------------- rings

def _health(ring: Dict[str, Any], ctx: Context) -> List[Dict[str, Any]]:
    table, out = rm.HEALTH, []
    for row in ring.get("health") or []:
        signal, state = row.get("signal"), row.get("state")
        if signal not in table["signals"]:
            continue
        k, n = int(row.get("k") or 0), int(row.get("n") or 0)
        shown = table["signals"][signal]
        if state == "waiting":
            text = rm.fill(table["waiting"], signal=shown)
        elif state == "no_data":
            text = rm.fill(table["no_data"], signal=shown)
        elif state == "agent_only":
            text = table["services_agent_only"]
        elif state == "not_checked":
            text = rm.fill(table["not_checked"], services=_names(ctx.watched or ["Services"]),
                           k=int(row.get("notChecked") or 0), n=n)
        else:
            text = rm.fill(table[signal], k=k, computers=_computers(n), services=_names(["The agent service", *ctx.watched]))
        out.append({"signal": signal, "state": state, "text": text})
    return out


def _failure_rate(ring: Dict[str, Any], judged: List[Dict[str, Any]]) -> str:
    table = rm.FAILURE_RATE
    if ring.get("isCanary"):
        return table["canary"]
    counts = ring.get("healthCounts") if isinstance(ring.get("healthCounts"), dict) else {}
    failed = int(counts.get("failed", sum(1 for h in judged if h.get("state") == "failed")))
    reported = max(failed, int(counts.get("reported", sum(1 for h in judged if h.get("installReportedAt")))))
    minimum, limit = int(ring.get("minSample") or 1), int(ring.get("failPct") or 0)
    if reported >= minimum:      # rounded up, so a share is never shown below the limit while it halts the ring
        return rm.fill(table["at_or_above_minimum"], f=failed, computers=_computers(reported),
                       p=math.ceil(failed * 100 / reported), limit=limit, min=minimum)
    return rm.fill(table["below_minimum"], f=failed, computers=_computers(reported), min=minimum)


def _detail(rollout: Dict[str, Any], ring: Dict[str, Any], hosts: List[Dict[str, Any]], ctx: Context,
            now: datetime) -> str:
    table, state, zone = rm.RING_DETAIL, ring.get("state"), ctx.zone
    judged = [h for h in hosts if h.get("state") not in EXCLUDED]
    n = len(judged)
    index = int(ring.get("index") or 0)
    if rollout.get("shadow") and state in ("installing", "restarting"):
        return rm.fill(table["sim_" + state], computers=_computers(n))
    if state == "not_started":
        previous = (rollout.get("rings") or [{}])[max(index - 1, 0)].get("name") or ""
        return rm.fill(table[state], previous=previous)
    if state == "waiting_for_window":
        if ctx.opens is None:
            return rm.WINDOW_STRIP["none"]
        return rm.fill(table[state], opens=windows_mod.when_text(ctx.opens, zone), zone=zone)
    if state == "installing":
        return rm.fill(table[state], k=sum(1 for h in judged if h.get("state") in INSTALLED), n=n)
    if state == "restarting":
        need = [h for h in judged if h.get("rebootNeeded") or h.get("newBootAt") or h.get("state") == "restarting"]
        return rm.fill(table[state], k=sum(1 for h in need if h.get("newBootAt") or h.get("state") == "healthy"),
                       n=len(need))
    if state == "soaking":
        ends = store.parse_time(ring.get("soakEndsAt"))
        if ends is None:
            return rm.fill(rm.SOAK, hours=_soak_phrase(ring))
        left = max(0, math.ceil((ends - store.aware(now)).total_seconds() / 3600))
        return rm.fill(table[state], h=left, ends=windows_mod.when_text(ends, zone))
    if state == "checking_health":
        waiting = next((r["signal"] for r in ring.get("health") or [] if r.get("state") in ("waiting", "no_data")),
                       "install")
        return rm.fill(table[state], signal=rm.HEALTH["signals"].get(waiting, rm.HEALTH["signals"]["install"]))
    if state == "passed":
        lost = sum(1 for h in hosts if h.get("state") == "not_reached")
        return rm.fill(table["passed_not_reached" if lost else "passed"], computers=_computers(n), k=lost)
    if state == "halted":
        reason = rollout.get("haltReason") if isinstance(rollout.get("haltReason"), dict) else {}
        text = str(reason.get("text") or "") if reason.get("ring") == index else ""
        return rm.halt_first_line(str(ring.get("name") or ""), text).rstrip()
    if state == "reverted":
        stuck = sum(1 for h in hosts if h.get("state") == "not_reverted")
        done = sum(1 for h in hosts if h.get("state") == "reverted")
        return rm.fill(table["reverted_some_not" if stuck else "reverted"], computers=_computers(done), k=stuck)
    if state == "cancelled":
        ran = any(h.get("state") not in ("waiting", "would_install", "would_restart") for h in hosts)
        return table["cancelled_running" if ran else "cancelled_before"]
    return table.get(state, "")


def _soak_phrase(ring: Dict[str, Any]) -> str:
    hours = ring.get("soakHours") or 0
    return rm.plural(int(hours), "hour", "hours") if float(hours) == int(hours) else f"{hours} hours"


def ring_view(rollout: Dict[str, Any], ring: Dict[str, Any], hosts: List[Dict[str, Any]], now: datetime,
              ctx: Context) -> Dict[str, Any]:
    """One ring as the card shows it: chip state, the server's detail line, health, failure and soak lines and the
    first page of computers."""
    state = ring.get("state") if ring.get("state") in RING_STATES else "not_started"
    judged = [h for h in hosts if h.get("state") not in EXCLUDED]
    asking = state == "waiting_for_approval"
    rows, total = host_rows(hosts, ctx.zone, now)
    return {"index": int(ring.get("index") or 0), "name": str(ring.get("name") or ""),
            "groups": [ctx.names[g] for g in ring.get("groupIds") or [] if g in ctx.names], "state": state,
            "detail": _detail(rollout, {**ring, "state": state}, hosts, ctx, now),
            "waitingText": rm.RING_DETAIL["waiting_for_approval_no_access"]
            if asking and not ctx.caller.can_open_decisions else None,
            "decisionsLink": bool(asking and ctx.caller.can_open_decisions), "health": _health(ring, ctx),
            "failureRateText": _failure_rate(ring, judged), "soakText": rm.fill(rm.SOAK, hours=_soak_phrase(ring)),
            "hosts": rows, "hostTotal": total}


# ---------------------------------------------------------------- cards and pages

def status_of(rollout: Dict[str, Any]) -> str:
    """The stored status, with a running rollout split into the two waiting states by its current ring."""
    stored = str(rollout.get("status") or "running")
    if stored != "running":
        return stored
    rings = rollout.get("rings") or []
    index = int(rollout.get("currentRing") or 0)
    state = rings[index].get("state") if 0 <= index < len(rings) else None
    return state if state in ("waiting_for_approval", "waiting_for_window") else "running"


async def rollout_card(db, tenant_id: str, rollout: Dict[str, Any], caller, now: datetime,
                       ctx: Optional[Context] = None) -> Dict[str, Any]:
    now = store.aware(now)
    ctx = ctx or await context_for(db, tenant_id, [rollout], caller, now)
    hosts = await store.host_docs(db, tenant_id, rollout["id"])
    by_ring: Dict[int, List[Dict[str, Any]]] = {}
    for h in hosts:
        by_ring.setdefault(int(h.get("ring") or 0), []).append(h)
    status = status_of(rollout)
    halted = status == "halted"
    reverting = any(h.get("state") == "reverting" for h in hosts)
    can_act = bool(caller.can_manage_patches and caller.interactive and not caller.platform_tenant)
    lost = sum(1 for h in hosts if h.get("state") == "not_reached")
    never = int(rollout.get("neverReachedCount") or 0)
    closes = store.parse_time(rollout.get("closesAt"))
    closed_text = None
    if never:
        closed_text = rm.forms(never, rm.CARD["never_reached"])
    elif status == "completed" and lost and closes:
        closed_text = rm.forms(lost, rm.CARD["not_reached"], date=windows_mod.day_text(closes, ctx.zone))
    return {
        "id": rollout["id"], "name": str(rollout.get("name") or ""), "status": status,
        "simulation": bool(rollout.get("shadow")), "patchCount": len(rollout.get("patchIds") or []),
        "computerCount": len(hosts), "startedAt": _iso(rollout.get("createdAt")),
        "startedBy": (rollout.get("createdBy") or {}).get("name"),
        "rings": [ring_view(rollout, {"index": i, **r}, by_ring.get(i, []), now, ctx)
                  for i, r in enumerate(rollout.get("rings") or [])],
        "currentRing": int(rollout.get("currentRing") or 0) if status in ("running", "halted") or status.startswith("waiting")
        else None,
        "halt": halt_block(rollout, hosts) if halted else None, "notReachedCount": lost,
        "closesAt": _iso(closes), "neverReachedCount": never, "closedText": closed_text,
        "canResume": can_act and halted and not reverting, "canCancel": can_act and halted,
        "resumeBlockedReason": rm.API_DETAIL["revert_running"] if can_act and halted and reverting else None,
        "revertRunning": reverting}


def _finished_at(rollout: Dict[str, Any]):
    times = [t for t in (store.parse_time(rollout.get(k)) for k in ("completedAt", "cancelledAt", "closedAt")) if t]
    return max(times) if times else store.parse_time(rollout.get("createdAt"))


def _listed(rollout: Dict[str, Any], now: datetime) -> bool:
    if rollout.get("status") in ("running", "halted"):
        return True
    finished = _finished_at(rollout)
    return finished is not None and finished >= now - LISTED_FOR


def _order(rollout: Dict[str, Any]) -> Tuple[int, float]:
    """Halted, waiting for approval, running, waiting for a window, then finished ones; newest first in each group."""
    rank = RANK.get(status_of(rollout), 4)
    moment = _finished_at(rollout) if rank == 4 else store.parse_time(rollout.get("createdAt"))
    return rank, -(moment.timestamp() if moment else 0.0)


async def rollout_page(db, tenant_id: str, caller, offset: int, limit: int, now: datetime) -> Dict[str, Any]:
    now = store.aware(now)
    tenant = await settings.load(db, tenant_id)
    ringed, summary = await rings_summary(db, tenant_id)
    page = {"items": [], "total": 0, "offset": offset, "limit": limit, "attentionCount": 0,
            "window": await window_strip(db, tenant_id, now), "flags": await flags(db, caller, tenant),
            "ringsSet": ringed, "ringsSummary": summary}
    if tenant_id == PLATFORM_TENANT_ID:
        return page
    docs = [store.normalise(d) async for d in store.rollouts(db).find({"tenantId": tenant_id})]
    shown = sorted((d for d in docs if _listed(d, now)), key=_order)
    chosen = shown[offset:offset + limit]
    ctx = await context_for(db, tenant_id, chosen, caller, now)
    page["items"] = [await rollout_card(db, tenant_id, d, caller, now, ctx) for d in chosen]
    page["total"] = len(shown)
    page["attentionCount"] = sum(1 for d in shown if status_of(d) in ATTENTION)
    return page


# ---------------------------------------------------------------- the window strip and the rings summary

async def window_strip(db, tenant_id: str, now: datetime) -> Dict[str, Any]:
    """Window open (closes at), closed (next opens) or none, in the organization's zone (D-03, R3)."""
    now = store.aware(now)
    tw = await windows_mod.load(db, tenant_id)
    setting = await store.maintenance_settings(db).find_one({"tenantId": tenant_id}, {"_id": 0, "timeZone": 1})
    named = (setting or {}).get("timeZone")
    zone = named if tw.readable and isinstance(named, str) and named else None
    label = zone or "UTC"
    strip = {"state": "none", "text": rm.WINDOW_STRIP["none"], "closesAt": None, "nextOpensAt": None, "timeZone": zone}
    if not tw.readable or not tw.windows:
        return strip
    current = tw.open_at(now)
    if current is not None:
        return {**strip, "state": "open", "closesAt": _iso(current[1]), "text": rm.fill(
            rm.WINDOW_STRIP["open"], closes=windows_mod.clock_text(current[1], label), zone=label)}
    coming = windows_mod.next_open(tw.windows, tw.zone, now)
    if coming is None:
        return strip
    return {**strip, "state": "closed", "nextOpensAt": _iso(coming[0]), "text": rm.fill(
        rm.WINDOW_STRIP["closed"], opens=windows_mod.when_text(coming[0], label), zone=label)}


async def rings_summary(db, tenant_id: str) -> Tuple[bool, str]:
    """(rings are set, the one-line summary): ``Canary (Canary) -> Pilot (Servers) -> Everyone else · 24-hour soak``."""
    saved = await rings_mod.load(db, tenant_id)
    if not saved.readable:
        return False, rm.API_DETAIL["rings_unreadable"]
    if len(saved.rings) < MIN_RINGS:
        return False, rm.RINGS_SUMMARY["unset"]
    names = await _group_names(db, tenant_id, (g for r in saved.rings for g in r.groupIds))
    parts = []
    for i, ring in enumerate(saved.rings):
        shown = [names[g] for g in ring.groupIds if g in names]
        parts.append(f"{ring.name} ({', '.join(shown)})" if shown else
                     rm.RINGS_SUMMARY["last"] if i == len(saved.rings) - 1 else ring.name)
    soaks = sorted({ring.soakHours for ring in saved.rings})
    soak = rm.fill(rm.RINGS_SUMMARY["soak_same"], h=_hours(soaks[0])) if len(soaks) == 1 else rm.fill(
        rm.RINGS_SUMMARY["soak_range"], lo=_hours(soaks[0]), hi=_hours(soaks[-1]))
    return True, " -> ".join(parts) + " · " + soak
