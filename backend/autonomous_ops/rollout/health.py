"""The health verdict of a ring (PTCH-01, PTCH-02, PTCH-03): green, still waiting, or halt.

``ring_verdict`` is a pure function: it reads plain per-host signal dicts (``signals.host_signals``) and the
ring's settings and decides. A signal is True (good), False (bad) or None (no data); the strings
``agent_only`` and ``not_checked`` (services) are not None: they neither pass a check nor halt the ring. Missing
data never passes: once the soak is over, any computer with no data for a signal halts the ring with
``no_data:<signal>``. A computer that is ``not_reached`` or ``left_out`` is judged on nothing and counted in
neither the reported nor the failed numbers (D-18).

The canary ring halts on any failure, at once. A later ring halts at once when too large a share of the
computers that reported failed (integer maths: failed * 100 > failPct * reported, once at least ``minSample``
reported), or when any failed while fewer than ``minSample`` had reported. The verdict does not depend on the
order of the list: a halt names the first failing computer by (hostname casefold, agent id). With no computer
reported there is no failure share, so a ring with computers but no report keeps waiting. The canary also
needs one installed computer for every operating system named in ``required_os`` (D-18). ``health_rows`` is
what the views show for the four checks. No database access in this module.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

from . import store
from .signals import AGENT_ONLY, NOT_CHECKED, host_signals  # noqa: F401  (host_signals moved to signals.py)

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


def _order(host: Dict[str, Any]):
    return str(host.get("hostname") or "").casefold(), str(host.get("agentId") or "")


def ring_verdict(hosts: List[Dict[str, Any]], ring: Dict[str, Any], now: datetime,
                 required_os: Iterable[str] = ()) -> Verdict:
    """The verdict for one ring. ``hosts`` are signal dicts; ``ring`` carries isCanary, failPct, minSample
    and soakEndsAt; ``required_os`` the operating systems the canary must have installed on."""
    judged = sorted((h for h in hosts if h.get("state") not in EXCLUDED_STATES), key=_order)
    failed = [h for h in judged if h.get("failed")]
    reported = [h for h in judged if h.get("reported")]
    if ring.get("isCanary"):
        if failed:
            return halt("canary_failed", failed[0]["agentId"])
    else:
        min_sample = int(ring.get("minSample") or 1)
        if failed and len(reported) < min_sample:
            return halt("host_failed", failed[0]["agentId"])
        if len(reported) >= min_sample and len(failed) * 100 > int(ring.get("failPct") or 0) * len(reported):
            return halt("failure_share", failed[0]["agentId"])
    if judged and not reported:
        return waiting("no_reports")
    soak_ends = store.parse_time(ring.get("soakEndsAt"))
    if soak_ends is None or store.aware(now) < soak_ends:
        return waiting("soak")
    for signal in SIGNALS:
        missing = [h for h in judged if not h.get("failed") and h.get(signal) is None]
        if missing:
            return halt(f"no_data:{signal}", missing[0]["agentId"])
    if ring.get("isCanary") and set(required_os) - {h.get("os") for h in judged if h.get("install") is True}:
        return waiting("canary_os")
    return green()


def health_rows(hosts: List[Dict[str, Any]], ring: Dict[str, Any], now: datetime) -> List[Dict[str, Any]]:
    """One row per check for the views: {signal, state, k, n, notChecked}. ``k`` computers are good out of the
    ``n`` that are judged; state is failed, no_data (soak over, nothing known), waiting (soak still on),
    not_checked, agent_only or passed."""
    judged = [h for h in hosts if h.get("state") not in EXCLUDED_STATES]
    soak_ends = store.parse_time(ring.get("soakEndsAt"))
    over = soak_ends is not None and store.aware(now) >= soak_ends
    rows = []
    for signal in SIGNALS:
        values = [h.get(signal) for h in judged]
        unchecked = sum(1 for v in values if v == NOT_CHECKED)
        if any(v is False for v in values):
            state = "failed"
        elif any(v is None for v in values):
            state = "no_data" if over else "waiting"
        elif unchecked:
            state = "not_checked"
        elif values and all(v == AGENT_ONLY for v in values):
            state = "agent_only"
        else:
            state = "passed"
        rows.append({"signal": signal, "state": state, "n": len(judged), "notChecked": unchecked,
                     "k": sum(1 for v in values if v is True or v == AGENT_ONLY)})
    return rows


def last_change(hosts: List[Dict[str, Any]]) -> Optional[datetime]:
    """The latest install report or new boot of the ring's computers, None when none reported."""
    times = [t for t in (store.parse_time(h.get(key)) for h in hosts for key in ("installReportedAt", "newBootAt"))
            if t is not None]
    return max(times) if times else None


def soak_end(hosts: List[Dict[str, Any]], soak_hours: float, now: datetime) -> datetime:
    """When the ring's soak ends (D-10): the latest install report or new boot plus the soak, or now plus the
    soak when no computer reported."""
    return (last_change(hosts) or store.aware(now)) + timedelta(hours=soak_hours)
