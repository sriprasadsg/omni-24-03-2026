"""The signal store and host resolution for the automatic sweep (Phase 83, D-01, D-03).

``autonomy_signals`` holds one document per (tenantId, agentId, kind, indicator): which origins
have named an indicator on a host, when the sweep first and last saw each one, and the sweep's
own memory of what it decided. Origin ids in this module: ``native`` (a native scan verdict) and
``feed:urlhaus`` (the global URLhaus rows of ``edr_ioc``).

Rules this module keeps:
* Only structured fields count (a scan row's ``target``, a feed row's ``source_ip``). No free text
  from an alert, finding or ticket ever names an indicator (PROH-83-01).
* A finding is posted under the hostname the agent used, not under ``agents.id``. ``resolve`` maps
  it to one agent of the same tenant, and to nothing when two agents share the name (R7): the
  failure direction is no action, never a wrong-host action.
* Time comparisons use the sweep's own ``firstSeenAt`` (the first tick that saw the origin), never
  a feed-supplied time. ``evidenceAt`` keeps the source's time for later freshness checks.
* ``edr_ioc`` feed rows are global (no tenantId) and sit outside the tenant wrapper, so they are
  read through the raw handle with ``tenantId`` absent; a tenant's own IOC rows are never an origin.

Raw Mongo handle with an explicit tenantId; the ambient tenant ContextVar is never used. Datetimes
are timezone-aware UTC BSON datetimes.
"""
import ipaddress
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional

from .scope import raw

logger = logging.getLogger(__name__)

NATIVE = "native"
FEED_URLHAUS = "feed:urlhaus"
NATIVE_WINDOW = timedelta(hours=25)      # a native verdict counts for a little over a day
FEED_WINDOW = timedelta(hours=48)        # a feed row counts while the feed's sync still lists it
CORROBORATION_WINDOW = timedelta(hours=24)       # D-03
NATIVE_LIMIT = 500
AGENT_LIMIT = 5000
_FEED_IP_LIMIT = 1000


@dataclass
class Candidate:
    kind: str
    indicator: str
    agent_id: str
    path: Optional[str] = None
    origins: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    decision: Optional[Dict[str, Any]] = None


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if isinstance(value, datetime) and value.tzinfo is None else value


def _signals(db):
    return raw(db).autonomy_signals


async def ensure_indexes(db) -> None:
    """One signal per (tenant, host, kind, indicator)."""
    await _signals(db).create_index([("tenantId", 1), ("agentId", 1), ("kind", 1), ("indicator", 1)],
                                    unique=True, name="signal_unique")


# ---------------------------------------------------------------- hosts

async def agents_of(db, tenant_id: str) -> List[Dict[str, Any]]:
    """The tenant's enrolled agents with the fields the sweep needs."""
    found = raw(db).agents.find(
        {"tenantId": tenant_id},
        {"_id": 0, "id": 1, "hostname": 1, "status": 1, "lastSeen": 1, "platform": 1, "ipAddress": 1,
         "meta.response_actions": 1}).limit(AGENT_LIMIT)
    return [a async for a in found if a.get("id")]


def index_agents(agents: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Agents by id and by casefolded hostname; a key maps to a list so a shared name is visible."""
    index: Dict[str, List[Dict[str, Any]]] = {}
    for agent in agents:
        keys = {str(agent["id"]).casefold()}
        if agent.get("hostname"):
            keys.add(str(agent["hostname"]).strip().casefold())
        for key in keys:
            bucket = index.setdefault(key, [])
            if all(a["id"] != agent["id"] for a in bucket):
                bucket.append(agent)
    return index


def resolve(hosts_by_key: Mapping[str, List[Dict[str, Any]]], name: Any) -> Optional[Dict[str, Any]]:
    """The one agent an id or hostname names, or None when it names none or more than one."""
    if not isinstance(name, str) or not name.strip():
        return None
    matches = hosts_by_key.get(name.strip().casefold()) or []
    return matches[0] if len(matches) == 1 else None


# ---------------------------------------------------------------- indicators

def global_ip(value: Any) -> Optional[str]:
    """The canonical text of a strictly-parsed, globally routable address, else None. An
    IPv4-mapped IPv6 address is unwrapped; private, loopback, link-local, multicast, reserved and
    documentation ranges never count."""
    if not isinstance(value, str):
        return None
    try:
        addr = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return str(addr) if addr.is_global else None


def _when(value: Any) -> Optional[datetime]:
    """An aware datetime from an ISO string or a datetime, else None."""
    if isinstance(value, datetime):
        return _aware(value)
    if isinstance(value, str) and value:
        try:
            return _aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


async def _upsert(db, tenant_id: str, agent_id: str, indicator: str, origin: str, now: datetime,
                  evidence_at: datetime, ref: str, path: Optional[str] = None) -> None:
    key = {"tenantId": tenant_id, "agentId": agent_id, "kind": "ip", "indicator": indicator}
    sets: Dict[str, Any] = {f"origins.{origin}.ref": ref}
    if path:
        sets["path"] = path
    await _signals(db).update_one(
        key,
        {"$min": {f"origins.{origin}.firstSeenAt": now},
         "$max": {f"origins.{origin}.lastSeenAt": now, f"origins.{origin}.evidenceAt": evidence_at},
         "$set": sets},
        upsert=True)


async def observe(db, tenant_id: str, agents: List[Dict[str, Any]], now: datetime) -> List[Candidate]:
    """Read this tenant's host-bound observations, record each origin on its signal and return the
    merged ip Candidates touched, sorted by (agent, indicator). Native Malicious ip verdicts bind an
    address to a host; a global URLhaus row corroborates only an address some host already has."""
    index = index_agents(agents)
    touched: Dict[tuple, None] = {}
    native_cut = (now - NATIVE_WINDOW).isoformat()
    found = raw(db).security_scan_results.find(
        {"tenantId": tenant_id, "source": "native", "verdict": "Malicious", "type": "ip",
         "created_at": {"$gte": native_cut}},
        {"_id": 0, "agentId": 1, "target": 1, "created_at": 1, "id": 1}).sort("created_at", -1).limit(NATIVE_LIMIT)
    on_host: Dict[str, set] = {}
    async for row in found:
        agent = resolve(index, row.get("agentId"))
        ip = global_ip(row.get("target"))
        evidence = _when(row.get("created_at"))
        if agent is None or ip is None or evidence is None:
            continue
        await _upsert(db, tenant_id, agent["id"], ip, NATIVE, now, evidence, str(row.get("id") or ""))
        touched[(agent["id"], ip)] = None
        on_host.setdefault(ip, set()).add(agent["id"])

    if on_host:
        feed_cut = (now - FEED_WINDOW).isoformat()
        feed = raw(db).edr_ioc.find(
            {"tenantId": {"$exists": False}, "source_feed": "urlhaus", "ioc_type": "url",
             "source_ip": {"$in": sorted(on_host)[:_FEED_IP_LIMIT]}, "updated_at": {"$gte": feed_cut}},
            {"_id": 0, "source_ip": 1, "updated_at": 1, "ioc_value": 1}).limit(NATIVE_LIMIT)
        async for row in feed:
            ip = global_ip(row.get("source_ip"))
            evidence = _when(row.get("updated_at"))
            if ip is None or evidence is None or ip not in on_host:
                continue
            for agent_id in sorted(on_host[ip]):
                await _upsert(db, tenant_id, agent_id, ip, FEED_URLHAUS, now, evidence, "urlhaus")
                touched[(agent_id, ip)] = None

    out: List[Candidate] = []
    for agent_id, ip in sorted(touched):
        doc = await _signals(db).find_one(
            {"tenantId": tenant_id, "agentId": agent_id, "kind": "ip", "indicator": ip}, {"_id": 0})
        if doc:
            out.append(_candidate(doc))
    return out


def _candidate(doc: Dict[str, Any]) -> Candidate:
    origins = {}
    for name, value in (doc.get("origins") or {}).items():
        if isinstance(value, dict):
            origins[name] = {k: _aware(v) for k, v in value.items()}
    decision = doc.get("decision")
    if isinstance(decision, dict):
        decision = {k: _aware(v) for k, v in decision.items()}
    return Candidate(kind=doc.get("kind", "ip"), indicator=doc.get("indicator", ""), agent_id=doc.get("agentId", ""),
                     path=doc.get("path"), origins=origins, decision=decision if isinstance(decision, dict) else None)


# ---------------------------------------------------------------- the rule and the memory

def corroborated(doc: Any, *, two_signal: bool) -> bool:
    """D-03: two different origins whose firstSeenAt are at most 24 hours apart; with two_signal
    off (D-04) one origin is enough. ``doc`` is a Candidate or a mapping holding ``origins``."""
    origins = doc.origins if isinstance(doc, Candidate) else (doc or {}).get("origins")
    firsts = sorted(t for t in (_aware((v or {}).get("firstSeenAt")) for v in (origins or {}).values())
                    if isinstance(t, datetime))
    if not firsts:
        return False
    if len(firsts) == 1:
        return not two_signal
    return firsts[-1] - firsts[0] <= CORROBORATION_WINDOW or not two_signal


async def remember(db, doc_key: Dict[str, Any], decision: Dict[str, Any]) -> None:
    """Write the sweep's memory of what it decided for this signal: {actionId, at, outcome,
    blockedFrom?, blockedUntil?}."""
    keep = {k: decision[k] for k in ("actionId", "at", "outcome", "blockedFrom", "blockedUntil") if k in decision}
    await _signals(db).update_one(doc_key, {"$set": {"decision": keep}})
