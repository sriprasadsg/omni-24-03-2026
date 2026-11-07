"""Per-computer signals for the rollout health gate (Phase 84, PTCH-02).

Each signal is True (good), False (bad) or None (no data). A signal is only ever read from data NEWER than the
change it judges, so absence of a problem is never taken for success:

* ``install``: the host's own install result (``installed``, ``restarting`` and ``healthy`` read True, ``failed``
  False, anything else no data).
* ``inventory``: a patch scan timestamped more than 5 minutes after the change (the install, or the new boot
  when the computer restarted) that no longer lists the patches. A scan that still lists them fails the
  computer (T-84-27: the pending list stored when the job reported is ignored).
* ``heartbeat``: after the install report when no restart was needed, else the new boot (``reboots.is_new_boot``
  or a new boot already recorded). A heartbeat from before the restart is never the new boot (PROH-84-06).
* ``services`` (OQ6, DEV-2): ``"agent_only"`` with an empty watched list (only the agent's heartbeat is checked
  and that is not no data); for an agent that reports the ``service_state`` token every watched service must
  be running in a block newer than the change plus 120 s (stopped or failed fails the computer, a missing or
  stale block is no data); a service reported ``absent`` (not installed or masked) is judged against the host's
  pre-change baseline (``servicesPresentBefore`` / ``servicesAbsentBefore``, CR-03, KD-84-G2): present before
  fails, absent before leaves the wanted list (all gone reads ``"agent_only"``), no record is no data;
  an agent without the token reads ``"not_checked"`` unless its ``service_failures``
  name a watched service (then False). ``"not_checked"`` neither passes nor halts and is shown as Not checked
  (T-84-28: never reported as passed).

``host_signals`` also returns ``failed`` (any signal False), ``reported`` (the install result is known), the
computer's ``state``, ``os`` and ``hostname``. Reads only.
"""
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

import agent_capabilities

from .. import agent_support, response_settings
from ..scope import raw
from . import INVENTORY_FRESH_AFTER, SERVICE_SETTLE, TOKEN_SERVICE_STATE, reboots, store
from .start import pending_ids

AGENT_FIELDS = {"_id": 0, "id": 1, "status": 1, "lastSeen": 1, "meta.system_patching": 1, "meta.os_patches": 1,
                "meta.response_state": 1, "meta.response_actions": 1, "meta.service_state": 1,
                "meta.service_failures": 1}
INSTALLED_STATES = ("installed", "restarting", "healthy")
REMEDIATION = "remediation_executor"        # the capability that carries service_failures to the server
NOT_CHECKED = "not_checked"
AGENT_ONLY = "agent_only"


def _meta(agent: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    meta = (agent or {}).get("meta")
    return meta if isinstance(meta, dict) else {}


def _names(value: Any) -> set:
    """The casefolded names of a stored baseline list (anything but a list of strings reads as empty)."""
    return {n.casefold() for n in value if isinstance(n, str)} if isinstance(value, list) else set()


def _inventory(agent: Optional[Dict[str, Any]], host: Dict[str, Any], since) -> Optional[bool]:
    scan = _meta(agent).get("system_patching")
    scanned_at = store.parse_time(scan.get("timestamp")) if isinstance(scan, dict) else None
    if since is None or scanned_at is None or scanned_at <= since + INVENTORY_FRESH_AFTER:
        return None
    ids = host.get("installedIds") or host.get("patchIds") or []
    return not any(p in pending_ids(agent or {}) for p in ids)


def _heartbeat(agent: Optional[Dict[str, Any]], host: Dict[str, Any], restart: bool, installed_at) -> Optional[bool]:
    if restart:
        if host.get("newBootAt") or reboots.is_new_boot(agent, host) is True:
            return True
        return None
    seen = store.parse_time((agent or {}).get("lastSeen"))
    return True if installed_at is not None and seen is not None and seen > installed_at else None


def _from_block(block: Any, wanted: List[str], since, present: Iterable[str] = (), absent: Iterable[str] = ()) -> Any:
    """Every wanted service running in a block newer than ``since`` plus the settle time. A service the block
    reports ``absent`` (not installed or masked, CR-03) is judged against the host's pre-change baseline
    (``present``/``absent``, casefolded): present before fails the signal, absent before leaves the wanted list,
    in neither is no data. When every wanted name left the list the value is ``AGENT_ONLY``."""
    at = block.get("at") if isinstance(block, dict) else None
    entries = block.get("services") if isinstance(block, dict) else None
    if since is None or isinstance(at, bool) or not isinstance(at, (int, float)) or not isinstance(entries, list) \
            or at <= since.timestamp() + SERVICE_SETTLE.total_seconds():
        return None
    states = {str(e["name"]).casefold(): str(e.get("state")).casefold() for e in entries
              if isinstance(e, dict) and isinstance(e.get("name"), str)}
    was_present, was_absent = set(present), set(absent)
    gone = [name for name in wanted if states.get(name) == "absent"]
    if any(states.get(name) in ("stopped", "failed") for name in wanted) or any(name in was_present for name in gone):
        return False
    missing_baseline = any(name not in was_absent for name in gone)
    wanted = [name for name in wanted if name not in gone]
    if missing_baseline:
        return None
    if not wanted:
        return AGENT_ONLY
    return True if all(states.get(name) == "running" for name in wanted) else None


def _services(agent: Optional[Dict[str, Any]], watched: Optional[Iterable[str]], capabilities: Iterable[str],
              since, host: Optional[Dict[str, Any]] = None) -> Any:
    if watched is None:                       # the watched list could not be read: nothing can be said
        return None
    wanted = sorted({str(n).casefold() for n in watched if isinstance(n, str) and n.strip()})
    if not wanted:
        return AGENT_ONLY
    meta = _meta(agent)
    if TOKEN_SERVICE_STATE in agent_support.tokens_of(agent):
        return _from_block(meta.get("service_state"), wanted, since, _names((host or {}).get("servicesPresentBefore")),
                           _names((host or {}).get("servicesAbsentBefore")))
    failures = meta.get("service_failures") if REMEDIATION in set(capabilities) else None
    if isinstance(failures, list) and any(isinstance(f, dict) and str(f.get("name") or "").casefold() in wanted
                                          for f in failures):
        return False
    return NOT_CHECKED


def read(agent: Optional[Dict[str, Any]], host: Dict[str, Any], watched: Optional[Iterable[str]],
         capabilities: Iterable[str]) -> Dict[str, Any]:
    """The plain signal dict ``health.ring_verdict`` reads for one computer (no database access)."""
    state = host.get("state")
    install = True if state in INSTALLED_STATES else False if state == "failed" else None
    restart = bool(host.get("rebootNeeded"))
    installed_at = store.parse_time(host.get("installReportedAt"))
    since = store.parse_time(host.get("newBootAt")) if restart else installed_at     # data counts only when newer
    out = {"agentId": host["agentId"], "hostname": host.get("hostname"), "os": host.get("os"), "state": state,
           "install": install, "inventory": _inventory(agent, host, since),
           "heartbeat": _heartbeat(agent, host, restart, installed_at),
           "services": _services(agent, watched, capabilities, since, host)}
    out["reported"] = install is not None
    out["failed"] = any(out[s] is False for s in ("install", "inventory", "heartbeat", "services"))
    return out


async def host_signals(db, tenant_id: str, rollout: Dict[str, Any], host: Dict[str, Any],
                       agent: Optional[Dict[str, Any]], watched: Optional[Iterable[str]], capabilities: Iterable[str],
                       now: datetime) -> Dict[str, Any]:
    """The signals for one computer of ``rollout``. ``agent`` is the computer's agent document (read here when
    not given and a database is); ``watched`` the tenant's watched services (None when unreadable);
    ``capabilities`` the tenant's permitted agent capabilities."""
    if agent is None and db is not None:
        agent = await raw(db).agents.find_one({"id": host["agentId"], "tenantId": tenant_id}, AGENT_FIELDS)
    return read(agent, host, watched, capabilities)


async def ring_signals(db, tenant_id: str, rollout: Dict[str, Any], hosts: List[Dict[str, Any]],
                       now: datetime) -> List[Dict[str, Any]]:
    """The signals for every computer in ``hosts`` against the organization's watched services and permitted
    capabilities, read once. The controller's pass and Resume both judge a ring from exactly this."""
    stored = await response_settings.load(db, tenant_id)
    watched = list(stored.watched_services) if stored.readable else None       # unreadable: no data, not a pass
    permitted = await agent_capabilities.allowed_for(raw(db), tenant_id)
    agents = {}
    async for agent in raw(db).agents.find({"tenantId": tenant_id, "id": {"$in": [h["agentId"] for h in hosts]}},
                                           AGENT_FIELDS):
        agents[agent["id"]] = agent
    return [await host_signals(db, tenant_id, rollout, h, agents.get(h["agentId"]), watched, permitted, now)
            for h in hosts]
