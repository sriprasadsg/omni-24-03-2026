"""The never-touch list (GATE-08, D-19): targets an automatic decision must never act on.

Built-in entries are computed in code on every cache miss (60 seconds) and are never stored,
so they cannot be removed: loopback, link-local, unspecified and multicast addresses; every
address of the backend's own network interfaces and each interface's subnet (the management
network); the hosts named by PLATFORM_URL, BACKEND_HOST and BACKEND_WS_HOST; and every agent
enrolled in the platform tenant (by id, hostname and ipAddress). No DNS lookups are made: a
host name only ever matches an agent's recorded hostname.

Stored entries live in ``autonomy_never_touch`` (scope "platform" applies to every tenant,
scope "tenant" to one) and are read on every call, so an entry added between two decisions
applies to the second.

IP matching uses stdlib ``ipaddress`` only. A value that does not parse (including a
leading-zero form such as 010.0.0.1) is ``invalid_target``, never compared as a string; an
IPv4-mapped IPv6 address is unwrapped to its IPv4 form before matching.

Raw Mongo handle with an explicit tenantId; the ambient tenant ContextVar is never used.
"""
import ipaddress
import logging
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from . import PLATFORM_TENANT_ID
from .scope import raw

logger = logging.getLogger(__name__)

SCOPES = ("builtin", "platform", "tenant")
KINDS = ("ip", "cidr", "host", "agent")
MAX_ENTRIES = 500                 # per scope and tenant
BUILTIN_CACHE_SECONDS = 60
_ENV_HOSTS = ("PLATFORM_URL", "BACKEND_HOST", "BACKEND_WS_HOST")
_COLLECTION = "autonomy_never_touch"


@dataclass(frozen=True)
class Entry:
    id: str
    scope: str           # builtin | platform | tenant
    tenant_id: Optional[str]
    kind: str            # ip | cidr | host | agent
    value: str
    note: str = ""
    builtin: bool = False


_cache: Dict[str, Any] = {}


def cache_clear() -> None:
    """Forget the cached built-in entries (tests, and after the environment changes)."""
    _cache.clear()


def _coll(db):
    return raw(db)[_COLLECTION]


# ---------------------------------------------------------------- parsing

def _unwrap(addr):
    mapped = getattr(addr, "ipv4_mapped", None)
    return mapped if mapped is not None else addr


def parse_ip(value) -> Optional[Any]:
    """A strict IP address (IPv4-mapped IPv6 unwrapped), or None when it does not parse. Only a
    string is accepted: an int would otherwise be read as a packed address."""
    if not isinstance(value, str):
        return None
    try:
        return _unwrap(ipaddress.ip_address(value))
    except ValueError:
        return None


def _parse_loose_ip(value):
    """An address recorded by an agent (surrounding spaces and a zone suffix tolerated)."""
    if not isinstance(value, str):
        return None
    return parse_ip(value.strip().split("%", 1)[0])


def _network(value: str):
    try:
        net = ipaddress.ip_network(value, strict=False)
    except ValueError:
        return None
    mapped = getattr(net.network_address, "ipv4_mapped", None)
    if mapped is not None and net.version == 6 and net.prefixlen >= 96:
        return ipaddress.ip_network((mapped, net.prefixlen - 96), strict=False)
    return net


def _host_of(value: str) -> Optional[str]:
    """The host part of a URL or host[:port] setting; None when empty."""
    value = (value or "").strip()
    if not value:
        return None
    parsed = urlparse(value if "://" in value else "//" + value)
    try:
        host = parsed.hostname
    except ValueError:
        return None
    return host.casefold() if host else None


# ---------------------------------------------------------------- built-in entries

def _ip_entries(kind: str, values) -> List[Entry]:
    return [Entry(f"builtin:{kind}:{v}", "builtin", None, kind, str(v), "built in", True) for v in values]


def _special_networks() -> List[Entry]:
    nets = ["127.0.0.0/8", "::1/128", "169.254.0.0/16", "fe80::/10", "0.0.0.0/32", "::/128",
            "224.0.0.0/4", "ff00::/8"]
    return _ip_entries("cidr", [ipaddress.ip_network(n) for n in nets])


def _interface_entries() -> List[Entry]:
    out: List[Entry] = []
    try:
        import psutil
        interfaces = psutil.net_if_addrs()
    except Exception as exc:  # no psutil or no permission: the other built-ins still apply
        logger.warning("autonomous_ops: interface addresses unavailable: %s", exc)
        return out
    for addrs in interfaces.values():
        for item in addrs:
            if item.family.name not in ("AF_INET", "AF_INET6"):
                continue
            addr = parse_ip(str(item.address).split("%", 1)[0])
            if addr is None:
                continue
            out.extend(_ip_entries("ip", [addr]))
            net = _interface_network(addr, item.netmask)
            if net is not None:
                out.extend(_ip_entries("cidr", [net]))
    return out


def _interface_network(addr, netmask):
    mask = parse_ip(str(netmask)) if netmask else None
    if mask is None or mask.version != addr.version:
        return None
    prefix = bin(int(mask)).count("1")
    try:
        return ipaddress.ip_network((addr, prefix), strict=False)
    except ValueError:
        return None


def _env_entries() -> List[Entry]:
    out: List[Entry] = []
    for name in _ENV_HOSTS:
        host = _host_of(os.getenv(name, ""))
        if not host:
            continue
        addr = parse_ip(host)
        out.extend(_ip_entries("ip", [addr]) if addr is not None
                   else [Entry(f"builtin:host:{host}", "builtin", None, "host", host, name, True)])
    return out


async def _platform_agent_entries(db) -> List[Entry]:
    out: List[Entry] = []
    async for agent in raw(db).agents.find({"tenantId": PLATFORM_TENANT_ID},
                                           {"_id": 0, "id": 1, "hostname": 1, "ipAddress": 1}):
        if agent.get("id"):
            out.append(Entry(f"builtin:agent:{agent['id']}", "builtin", None, "agent", str(agent["id"]),
                             "platform agent", True))
        if agent.get("hostname"):
            host = str(agent["hostname"]).strip().casefold()
            out.append(Entry(f"builtin:host:{host}", "builtin", None, "host", host, "platform agent", True))
        addr = _parse_loose_ip(agent.get("ipAddress"))
        if addr is not None:
            out.extend(_ip_entries("ip", [addr]))
    return out


async def builtin_entries(db) -> List[Entry]:
    """The built-in never-touch entries (computed, cached at most 60 s per database)."""
    key = str(getattr(raw(db), "name", id(raw(db))))
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < BUILTIN_CACHE_SECONDS:
        return list(hit[1])
    entries = _special_networks() + _interface_entries() + _env_entries()
    entries += await _platform_agent_entries(db)
    unique = list({e.id: e for e in entries}.values())
    _cache[key] = (time.monotonic(), unique)
    return list(unique)


# ---------------------------------------------------------------- stored entries

def _entry(doc: Dict[str, Any]) -> Entry:
    return Entry(doc["id"], doc["scope"], doc.get("tenantId"), doc["kind"], doc["value"],
                 doc.get("note") or "", False)


async def _stored(db, tenant_id: Optional[str]) -> List[Entry]:
    flt: Dict[str, Any] = {"scope": "platform"}
    if tenant_id:
        flt = {"$or": [{"scope": "platform"}, {"scope": "tenant", "tenantId": tenant_id}]}
    docs = _coll(db).find(flt, {"_id": 0}).limit(2 * MAX_ENTRIES + 1)
    return [_entry(d) async for d in docs]


async def list_entries(db, tenant_id: Optional[str]) -> List[Entry]:
    """Built-in entries, platform entries and (for a tenant) that tenant's own entries."""
    return await builtin_entries(db) + await _stored(db, tenant_id)


def _normalise(kind: str, value) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 253:
        raise ValueError("value must be a non-empty string of at most 253 characters")
    value = value.strip()
    if kind == "ip":
        addr = parse_ip(value)
        if addr is None:
            raise ValueError("not a valid IP address")
        return str(addr)
    if kind == "cidr":
        net = _network(value) if "/" in value else None
        if net is None:
            raise ValueError("not a valid network in CIDR form")
        return str(net)
    if any(ch.isspace() for ch in value):
        raise ValueError("value must not contain spaces")
    return value.casefold() if kind == "host" else value


async def add_entry(db, *, scope: str, tenant_id: Optional[str], kind: str, value, note: str = "",
                    actor=None) -> Entry:
    """Store a never-touch entry. Raises ValueError for a bad scope, kind or value and when the
    scope already holds MAX_ENTRIES entries. Adding an entry that exists returns it."""
    if scope not in ("platform", "tenant"):
        raise ValueError("scope must be platform or tenant")
    if kind not in KINDS:
        raise ValueError("kind must be ip, cidr, host or agent")
    if scope == "tenant" and (not tenant_id or not isinstance(tenant_id, str)):
        raise ValueError("a tenant entry needs a tenant id")
    owner = tenant_id if scope == "tenant" else None
    value = _normalise(kind, value)
    key = {"scope": scope, "tenantId": owner, "kind": kind, "value": value}
    existing = await _coll(db).find_one(key, {"_id": 0})
    if existing:
        return _entry(existing)
    if await _coll(db).count_documents({"scope": scope, "tenantId": owner}) >= MAX_ENTRIES:
        raise ValueError(f"at most {MAX_ENTRIES} entries are allowed for one {scope}")
    name = actor.get("username") if isinstance(actor, dict) else actor
    doc = {"id": "NT-" + uuid.uuid4().hex, **key, "note": str(note or "")[:500],
           "createdBy": str(name or "system"), "createdAt": datetime.now(timezone.utc)}
    await _coll(db).insert_one(dict(doc))
    return _entry(doc)


async def remove_entry(db, entry_id, *, scope: str, tenant_id: Optional[str]) -> bool:
    """Delete a stored entry. False for every built-in id and for an entry that is not in the
    given scope and tenant."""
    if not isinstance(entry_id, str) or entry_id.startswith("builtin:") or scope not in ("platform", "tenant"):
        return False
    owner = tenant_id if scope == "tenant" else None
    if scope == "tenant" and not owner:
        return False
    result = await _coll(db).delete_one({"id": entry_id, "scope": scope, "tenantId": owner})
    return result.deleted_count == 1


async def ensure_indexes(db) -> None:
    coll = _coll(db)
    await coll.create_index("id", unique=True, name="id_unique")
    await coll.create_index([("scope", 1), ("tenantId", 1), ("kind", 1), ("value", 1)], unique=True,
                            name="entry_unique")


# ---------------------------------------------------------------- the check

def _matches_ip(entries: List[Entry], addr) -> bool:
    for e in entries:
        if e.kind == "ip":
            other = parse_ip(e.value)
            if other is not None and other == addr:
                return True
        elif e.kind == "cidr":
            net = _network(e.value)
            if net is not None and net.version == addr.version and addr in net:
                return True
    return False


async def check(db, tenant_id: Optional[str], *, agent: Optional[Dict[str, Any]] = None,
                ip=None) -> Optional[str]:
    """"invalid_target" when ``ip`` is given and does not parse, "protected_target" when the IP
    or the agent (id, hostname or recorded address) matches a never-touch entry, else None.
    Errors propagate: the caller treats an unreadable list as a refusal."""
    addr = None
    if ip is not None:
        addr = parse_ip(ip)
        if addr is None:
            return "invalid_target"
    entries = await list_entries(db, tenant_id)
    if addr is not None and _matches_ip(entries, addr):
        return "protected_target"
    if agent:
        agent_id = agent.get("id")
        hostname = agent.get("hostname")
        host = str(hostname).strip().casefold() if hostname else None
        for e in entries:
            if e.kind == "agent" and agent_id is not None and e.value == str(agent_id):
                return "protected_target"
            if e.kind == "host" and host and e.value == host:
                return "protected_target"
        recorded = _parse_loose_ip(agent.get("ipAddress") or agent.get("ip_address"))
        if recorded is not None and _matches_ip(entries, recorded):
            return "protected_target"
    return None


async def check_network(db, tenant_id: Optional[str], cidr) -> Optional[str]:
    """For a whole network (Phase 83, RESP-02): "invalid_target" when ``cidr`` does not parse as a
    network, "protected_target" when it overlaps any never-touch IP or network entry (built in, platform
    or this tenant's: the same list ``check`` reads), else None. A host or agent entry names a computer, not
    an address range, so it does not apply here. Errors propagate: the caller treats an unreadable list as
    a refusal."""
    net = _network(cidr.strip()) if isinstance(cidr, str) and "/" in cidr else None
    if net is None:
        return "invalid_target"
    for e in await list_entries(db, tenant_id):
        if e.kind == "ip":
            other = parse_ip(e.value)
            if other is not None and other.version == net.version and other in net:
                return "protected_target"
        elif e.kind == "cidr":
            other = _network(e.value)
            if other is not None and other.version == net.version and net.overlaps(other):
                return "protected_target"
    return None
