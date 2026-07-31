"""ASN + VPN/hosting heuristic enrichment for agent public (WAN) IPs.

Clones `geoip_service.py`'s lazy-singleton `.mmdb`-reader pattern (D-11),
adding a second, independent lazy resource: a bundled X4BNet public-VPN
IPv4 CIDR snapshot matched with a stdlib `bisect` range lookup (D-12).
No runtime network fetch anywhere — air-gap safe.

Env:
  GEOIP_ASN_DB_PATH — path to GeoLite2-ASN.mmdb (optional; graceful no-op
    when unset/absent, matching geoip_service.py's GEOIP_DB_PATH contract).

Returns: {"asn": {"number", "org"}, "vpn_heuristic": bool} or None.
Never raises — any failure yields None.
"""
from __future__ import annotations

import bisect
import ipaddress
import logging
import os
import threading
from typing import Any, Dict, List, Optional, Tuple

from geoip_service import _is_public

logger = logging.getLogger(__name__)

_DEFAULT_ASN_DB_PATH = os.path.join(
    os.path.dirname(__file__), "data", "geoip", "GeoLite2-ASN.mmdb"
)
_VPN_RANGES_PATH = os.path.join(
    os.path.dirname(__file__), "data", "vpn_ranges", "x4bnet_vpn_ipv4.txt"
)

# --- ASN reader lazy singleton (matches geoip_service._get_reader exactly) ---
_reader = None
_reader_lock = threading.Lock()
_load_attempted = False
_warned_missing = False

# --- VPN CIDR-range lazy singleton — independent resource, same pattern ---
_vpn_ranges: Optional[List[Tuple[int, int]]] = None
_vpn_ranges_lock = threading.Lock()
_vpn_load_attempted = False
_vpn_warned_missing = False


def _db_path() -> str:
    return os.getenv("GEOIP_ASN_DB_PATH", _DEFAULT_ASN_DB_PATH)


def _get_reader():
    """Lazily open the ASN .mmdb reader once. Returns None if unavailable."""
    global _reader, _load_attempted, _warned_missing
    if _reader is not None:
        return _reader
    if _load_attempted:
        return _reader  # already tried and failed; don't retry every call
    with _reader_lock:
        if _reader is not None or _load_attempted:
            return _reader
        _load_attempted = True
        path = _db_path()
        if not os.path.isfile(path):
            if not _warned_missing:
                logger.warning(
                    "GeoLite2-ASN database not found at %s — ASN enrichment "
                    "disabled. Supply GeoLite2-ASN.mmdb or set GEOIP_ASN_DB_PATH.",
                    path,
                )
                _warned_missing = True
            return None
        try:
            import maxminddb

            _reader = maxminddb.open_database(path)
            logger.info("GeoLite2-ASN database loaded from %s", path)
        except Exception as exc:  # noqa: BLE001 — never break the request
            logger.warning("Failed to open GeoLite2-ASN database %s: %s", path, exc)
            _reader = None
        return _reader


def _load_vpn_ranges() -> List[Tuple[int, int]]:
    """Lazily read + parse the bundled X4BNet snapshot into sorted ranges.

    Single-attempt-then-cache, matching the ASN reader's pattern for an
    independent second lazy resource. Skips blank lines, comment lines
    (leading '#'), and non-IPv4 entries defensively. Missing/unreadable
    file logs a warning once and caches an empty list (VPN heuristic then
    evaluates False for everything, never raises).
    """
    global _vpn_ranges, _vpn_load_attempted, _vpn_warned_missing
    if _vpn_ranges is not None:
        return _vpn_ranges
    if _vpn_load_attempted:
        return _vpn_ranges or []
    with _vpn_ranges_lock:
        if _vpn_ranges is not None or _vpn_load_attempted:
            return _vpn_ranges or []
        _vpn_load_attempted = True
        path = _VPN_RANGES_PATH
        if not os.path.isfile(path):
            if not _vpn_warned_missing:
                logger.warning(
                    "X4BNet VPN range snapshot not found at %s — VPN heuristic "
                    "disabled.",
                    path,
                )
                _vpn_warned_missing = True
            _vpn_ranges = []
            return _vpn_ranges

        ranges: List[Tuple[int, int]] = []
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    try:
                        net = ipaddress.ip_network(line, strict=False)
                    except ValueError:
                        continue  # defensive: skip malformed lines silently
                    if net.version != 4:
                        continue  # defensive: skip IPv6 entries
                    ranges.append((int(net.network_address), int(net.broadcast_address)))
            ranges.sort()
        except Exception as exc:  # noqa: BLE001 — never let a bad file break lookup
            logger.warning("Failed to load X4BNet VPN ranges from %s: %s", path, exc)
            ranges = []
        _vpn_ranges = ranges
        return _vpn_ranges


def _is_known_vpn_range(ip: str) -> bool:
    """stdlib bisect membership test against the sorted VPN CIDR ranges."""
    ranges = _load_vpn_ranges()
    if not ranges:
        return False
    try:
        ip_int = int(ipaddress.ip_address(ip))
    except ValueError:
        return False
    idx = bisect.bisect_right(ranges, (ip_int, float("inf"))) - 1
    if idx < 0:
        return False
    start, end = ranges[idx]
    return start <= ip_int <= end


def _asn_from_record(rec: Any) -> Optional[Dict[str, Any]]:
    """Extract {number, org} from a raw GeoLite2-ASN reader record.

    Field names per RESEARCH.md Assumptions Log A1 (flat top-level keys,
    unlike the nested City-record shape in geoip_service.py). Never raises —
    a differing field layout silently omits the asn sub-object.
    """
    try:
        number = rec.get("autonomous_system_number")
        org = rec.get("autonomous_system_organization")
    except Exception:  # noqa: BLE001
        return None
    if number is None and org is None:
        return None
    return {"number": number, "org": org}


def lookup(ip: Optional[str]) -> Optional[Dict[str, Any]]:
    """Resolve a public IP to ASN + VPN-heuristic enrichment, or None.

    Returns: {"asn": {"number", "org"}, "vpn_heuristic": bool} or None.
    Never raises — any failure yields None. Private/loopback/reserved IPs
    are skipped entirely (no reader/range access at all).
    """
    if not ip or not _is_public(ip):
        return None

    result: Dict[str, Any] = {}

    reader = _get_reader()
    if reader is not None:
        try:
            rec = reader.get(ip)
        except Exception as exc:  # noqa: BLE001
            logger.debug("ASN lookup failed for %s: %s", ip, exc)
            rec = None
        if rec:
            asn = _asn_from_record(rec)
            if asn is not None:
                result["asn"] = asn

    ranges = _load_vpn_ranges()
    if ranges:
        result["vpn_heuristic"] = _is_known_vpn_range(ip)

    return result or None
