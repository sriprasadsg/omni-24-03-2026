"""GeoIP resolution for agent public (WAN) IPs.

Uses a local MaxMind GeoLite2-City database (`.mmdb`) — no per-lookup outbound
calls, works air-gapped. The DB file is licensed and supplied out-of-band: set
`GEOIP_DB_PATH` or drop it at `backend/data/geoip/GeoLite2-City.mmdb`. When the
DB is absent (or the IP is private/reserved) lookups return None and callers
simply store no geo — the public IP itself is still recorded.
"""
from __future__ import annotations

import ipaddress
import logging
import os
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "geoip", "GeoLite2-City.mmdb")

_reader = None
_reader_lock = threading.Lock()
_load_attempted = False
_warned_missing = False


def _db_path() -> str:
    return os.getenv("GEOIP_DB_PATH", _DEFAULT_DB_PATH)


def _get_reader():
    """Lazily open the .mmdb reader once. Returns None if unavailable."""
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
                    "GeoIP database not found at %s — agent geolocation disabled. "
                    "Supply a MaxMind GeoLite2-City.mmdb or set GEOIP_DB_PATH.", path
                )
                _warned_missing = True
            return None
        try:
            import maxminddb
            _reader = maxminddb.open_database(path)
            logger.info("GeoIP database loaded from %s", path)
        except Exception as exc:  # noqa: BLE001 — never let geo break the request
            logger.warning("Failed to open GeoIP database %s: %s", path, exc)
            _reader = None
        return _reader


def _is_public(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_multicast or addr.is_reserved or addr.is_unspecified)


def lookup(ip: Optional[str]) -> Optional[Dict[str, Any]]:
    """Resolve a public IP to a geo dict, or None.

    Returns: {country, country_code, city, region, latitude, longitude}.
    Never raises — any failure yields None.
    """
    if not ip or not _is_public(ip):
        return None
    reader = _get_reader()
    if reader is None:
        return None
    try:
        rec = reader.get(ip)
    except Exception as exc:  # noqa: BLE001
        logger.debug("GeoIP lookup failed for %s: %s", ip, exc)
        return None
    if not rec:
        return None

    country = rec.get("country") or rec.get("registered_country") or {}
    city = rec.get("city") or {}
    subdivs = rec.get("subdivisions") or []
    location = rec.get("location") or {}

    geo = {
        "country": (country.get("names") or {}).get("en"),
        "country_code": country.get("iso_code"),
        "city": (city.get("names") or {}).get("en"),
        "region": (subdivs[0].get("names") or {}).get("en") if subdivs else None,
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
    }
    # Drop entirely-empty results.
    if not any(v is not None for v in geo.values()):
        return None
    return geo
