"""Allowed networks per tenant (Phase 88, LIC-05).

The rule (D-01, D-06, D-07, D-31, D-32, D-42): a tenant keeps a list of allowed networks. The first
machine to enrol (once it passes the earlier rules) teaches the list its own address as a /32 (IPv6 /128)
entry with source ``learned``. A NEW machine from an address outside every entry is held Pending for the
platform (``new_network``); approving it allows that address, or a range around it no wider than an IPv4
/24 or an IPv6 /48. A machine that is already enrolled is never checked again.

The only address used here is the one the server observed (``request.client.host``). Behind nginx, uvicorn
trusts only 127.0.0.1 and ::1 as proxies and resolves the address nginx appended, so a caller cannot choose
it; nothing a request header or the agent itself reports about its own address is ever read. The standard
library ``ipaddress`` does all the parsing and comparison.
"""
import ipaddress
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

MAX_NETWORKS = 100
IPV4_WIDEST = 24
IPV6_WIDEST = 48

_Address = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]


def _raw(db):
    return getattr(db, "_db", db)


class EntryError(ValueError):
    pass


def _unwrap(ip: _Address) -> _Address:
    mapped = getattr(ip, "ipv4_mapped", None)
    return mapped if mapped is not None else ip


def normalize_ip(value: Any) -> Optional[_Address]:
    """The address as IPv4Address / IPv6Address (an IPv4-mapped IPv6 address becomes IPv4), or None when
    the value is missing or is not an address."""
    if isinstance(value, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
        return _unwrap(value)
    if not isinstance(value, str):
        return None
    try:
        return _unwrap(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def network_of(value: Any) -> str:
    """The normalized CIDR of an address (/32 or /128) or of a range (host bits cleared)."""
    try:
        if isinstance(value, str) and "/" in value:
            return str(ipaddress.ip_network(value.strip(), strict=False))
        ip = normalize_ip(value)
        if ip is not None:
            return str(ipaddress.ip_network(str(ip)))
    except (ValueError, TypeError):
        pass
    raise EntryError(f"not an address or network: {str(value)[:64]!r}")


def contains(entries: Optional[List[Dict[str, Any]]], ip: Optional[_Address]) -> bool:
    """Whether the address is inside any stored entry; an entry that does not parse is skipped."""
    if ip is None:
        return False
    for item in entries or []:
        try:
            if ip in ipaddress.ip_network((item or {}).get("cidr"), strict=False):
                return True
        except (ValueError, TypeError):
            continue
    return False


def entry(cidr: str, *, source: str, actor: Optional[str] = None, hostname: Optional[str] = None) -> Dict[str, Any]:
    return {"cidr": cidr, "source": source, "addedAt": datetime.now(timezone.utc).isoformat(),
            "addedBy": actor, "hostname": hostname}


def validate_widen(observed: Any, widen_to: Any) -> str:
    """The range to allow for an observed address (D-42): it must contain the address, be of the same
    IP version, be at most an IPv4 /24 or IPv6 /48 wide, and not be a private range for a public address."""
    ip = normalize_ip(observed)
    if ip is None:
        raise EntryError("there is no observed address to widen")
    try:
        net = ipaddress.ip_network(str(widen_to).strip(), strict=False)
    except ValueError:
        raise EntryError(f"widenTo is not a network: {str(widen_to)[:64]!r}")
    if net.version != ip.version:
        raise EntryError("widenTo must be the same IP version as the observed address")
    widest = IPV4_WIDEST if ip.version == 4 else IPV6_WIDEST
    if net.prefixlen < widest:
        raise EntryError(f"widenTo may be at most a /{widest} (IPv{ip.version})")
    if ip not in net:
        raise EntryError(f"widenTo must contain the observed address {ip}")
    if ip.is_global and not net.is_global:
        raise EntryError("widenTo is not a public range, but the observed address is")
    return str(net)


async def learn_first(db, tenant_id: str, ip: _Address, hostname: Optional[str] = None) -> bool:
    """Teach a tenant that has no allowed network yet the address of its first machine. One conditional
    update, so of two concurrent first enrolments only one wins; the other gets False."""
    res = await _raw(db).tenants.update_one(
        {"id": tenant_id, "allowedNetworks.0": {"$exists": False}},
        {"$push": {"allowedNetworks": entry(network_of(ip), source="learned", hostname=hostname)}})
    return res.modified_count == 1


async def allow(db, tenant_id: str, cidr: str, *, source: str, actor: Optional[str],
                hostname: Optional[str] = None) -> bool:
    """Append a network unless it is already listed or the list is full (MAX_NETWORKS). Atomic; False means
    nothing was added."""
    res = await _raw(db).tenants.update_one(
        {"id": tenant_id, "allowedNetworks.cidr": {"$ne": cidr}, "allowedNetworks.%d" % (MAX_NETWORKS - 1): {"$exists": False}},
        {"$push": {"allowedNetworks": entry(cidr, source=source, actor=actor, hostname=hostname)}})
    return res.modified_count == 1
