"""The health verdict of a ring (PTCH-01): green, still waiting, or halt.

``ring_verdict`` is a pure function: it reads plain per-host signal dicts and the ring's settings and
decides. A signal is True (good), False (bad) or None (no data). Missing data never passes: once the soak
is over, any host with no data for a signal halts the ring with ``no_data:<signal>``.

The canary ring halts on any failure. A later ring halts when too large a share of the computers that
reported failed (integer maths: failed * 100 > failPct * reported, once at least ``minSample`` reported),
or when any failed while fewer than ``minSample`` had reported. ``host_signals`` reads the signals from
the agent document: the install result, a patch scan taken more than five minutes after the install that
no longer lists the patches (so absence cannot pass by itself: the stored pending list is cleared when the
job reports), and a heartbeat newer than the install. Service and restart checks arrive in plan 84-08.

No database access in this module.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from . import INVENTORY_FRESH_AFTER, store
from .start import pending_ids

SIGNALS = ("install", "inventory", "heartbeat", "services")
EXCLUDED_STATES = ("not_reached", "left_out")


@dataclass
class Verdict:
    kind: str                      # "green" | "waiting" | "halt"
    code: Optional[str] = None
    host: Optional[str] = None     # the agent id the verdict names, when it names one


def green() -> Verdict:
    return Verdict("green")


def waiting(code: str = "soak") -> Verdict:
    return Verdict("waiting", code)


def halt(code: str, host: Optional[str] = None) -> Verdict:
    return Verdict("halt", code, host)


def host_signals(agent: Optional[Dict[str, Any]], host: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    """The plain signal dict ``ring_verdict`` reads for one computer."""
    state = host.get("state")
    install = True if state in ("installed", "restarting", "healthy") else False if state == "failed" else None
    installed_at = store.parse_time(host.get("installReportedAt"))
    meta = (agent or {}).get("meta") if isinstance((agent or {}).get("meta"), dict) else {}
    scan = meta.get("system_patching") if isinstance(meta.get("system_patching"), dict) else {}
    scanned_at = store.parse_time(scan.get("timestamp"))
    still_listed = any(p in pending_ids(agent or {}) for p in host.get("patchIds") or [])
    inventory = None
    if installed_at and scanned_at and scanned_at > installed_at + INVENTORY_FRESH_AFTER and not still_listed:
        inventory = True
    seen = store.parse_time((agent or {}).get("lastSeen"))
    heartbeat = True if installed_at and seen and seen > installed_at else None
    return {"agentId": host["agentId"], "state": state, "failed": install is False, "reported": install is not None,
            "install": install, "inventory": inventory, "heartbeat": heartbeat,
            "services": True}          # "agent only": 84-08 adds the restart and watched-service checks


def ring_verdict(hosts: List[Dict[str, Any]], ring: Dict[str, Any], now: datetime) -> Verdict:
    """The verdict for one ring. ``hosts`` are signal dicts; ``ring`` carries isCanary, failPct, minSample
    and soakEndsAt."""
    judged = [h for h in hosts if h.get("state") not in EXCLUDED_STATES]
    failed = [h for h in judged if h.get("failed")]
    if ring.get("isCanary") and failed:
        return halt("canary_failed", failed[0]["agentId"])
    reported = [h for h in judged if h.get("reported")]
    if not ring.get("isCanary"):
        min_sample = int(ring.get("minSample") or 1)
        if failed and len(reported) < min_sample:
            return halt("host_failed", failed[0]["agentId"])
        if len(reported) >= min_sample and len(failed) * 100 > int(ring.get("failPct") or 0) * len(reported):
            return halt("failure_share")
    soak_ends = store.parse_time(ring.get("soakEndsAt"))
    if soak_ends is None or store.aware(now) < soak_ends:
        return waiting("soak")
    for signal in SIGNALS:
        missing = [h for h in judged if not h.get("failed") and h.get(signal) is None]
        if missing:
            return halt(f"no_data:{signal}", missing[0]["agentId"])
    return green()


def soak_end(hosts: List[Dict[str, Any]], soak_hours: float, now: datetime) -> datetime:
    """When the ring's soak ends (D-10): the latest install report or new boot plus the soak, or now plus the
    soak when no computer reported."""
    reported = [t for t in (store.parse_time(h.get(key)) for h in hosts for key in ("installReportedAt", "newBootAt"))
                if t is not None]
    return (max(reported) if reported else store.aware(now)) + timedelta(hours=soak_hours)
