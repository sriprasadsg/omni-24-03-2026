"""
Threat Feed Synchronisation Service

Pulls IOC data from free public feeds (no API key required) and an optional
AlienVault OTX feed (requires OTX_API_KEY env var).

Sources
-------
- abuse.ch URLhaus  : malicious URLs  (https://urlhaus-api.abuse.ch/v1/)
- abuse.ch MalwareBazaar: malware hashes (https://bazaar.abuse.ch/export/)
- AlienVault OTX    : multi-type IOCs (optional, requires OTX_API_KEY)

Schedule
--------
Runs once at startup then every SYNC_INTERVAL_HOURS (default 6) hours.
Each run upserts IOCs into the `edr_ioc` MongoDB collection so the UEBA
service, correlation engine, and EDR agents can query them.

IOC document schema (matches existing `edr_ioc` usage in ueba_service.py)
-------------------------------------------------------------------------
{
    "source_ip":   str | None,   # for IP-type IOCs
    "ioc_type":   "ip" | "url" | "hash" | "domain",
    "ioc_value":  str,
    "threat_type": str,          # e.g. "malware_download", "botnet_cc"
    "confidence": float,         # 0.0–1.0
    "source_feed": str,          # "urlhaus" | "malwarebazaar" | "otx"
    "tags":       [str],
    "last_seen":  ISO datetime,
    "updated_at": ISO datetime,
}
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

SYNC_INTERVAL_HOURS: int = int(os.getenv("THREAT_FEED_INTERVAL_HOURS", "6"))
OTX_API_KEY: str = os.getenv("OTX_API_KEY", "")
OTX_BASE = "https://otx.alienvault.com/api/v1"
URLHAUS_RECENT = "https://urlhaus-api.abuse.ch/v1/urls/recent/"
BAZAAR_EXPORT = "https://bazaar.abuse.ch/export/json/recent/"

# Maximum IOCs to ingest per source per run (keeps the DB from bloating)
MAX_PER_SOURCE = int(os.getenv("THREAT_FEED_MAX_PER_SOURCE", "500"))


# ── Individual feed fetchers ─────────────────────────────────────────────────

async def _fetch_urlhaus(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    """Fetch recent malicious URLs from URLhaus."""
    iocs: List[Dict[str, Any]] = []
    try:
        async with session.post(URLHAUS_RECENT, data={"limit": MAX_PER_SOURCE},
                                timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                logger.warning("[ThreatFeed] URLhaus returned HTTP %d", resp.status)
                return iocs
            data = await resp.json(content_type=None)
            for entry in (data.get("urls") or [])[:MAX_PER_SOURCE]:
                url = entry.get("url", "")
                if not url:
                    continue
                iocs.append({
                    "ioc_type": "url",
                    "ioc_value": url,
                    "source_ip": entry.get("host"),
                    "threat_type": entry.get("threat", "malware_download"),
                    "confidence": 0.85,
                    "source_feed": "urlhaus",
                    "tags": entry.get("tags") or [],
                    "last_seen": entry.get("date_added", datetime.now(timezone.utc).isoformat()),
                })
    except Exception as exc:
        logger.warning("[ThreatFeed] URLhaus fetch failed: %s", exc)
    logger.info("[ThreatFeed] URLhaus: %d IOCs", len(iocs))
    return iocs


async def _fetch_malwarebazaar(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    """Fetch recent malware file hashes from MalwareBazaar."""
    iocs: List[Dict[str, Any]] = []
    try:
        async with session.post(
            "https://mb-api.abuse.ch/api/v1/",
            data={"query": "get_recent", "selector": "100"},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status != 200:
                logger.warning("[ThreatFeed] MalwareBazaar returned HTTP %d", resp.status)
                return iocs
            data = await resp.json(content_type=None)
            for entry in (data.get("data") or [])[:MAX_PER_SOURCE]:
                sha256 = entry.get("sha256_hash", "")
                if not sha256:
                    continue
                iocs.append({
                    "ioc_type": "hash",
                    "ioc_value": sha256,
                    "source_ip": None,
                    "threat_type": entry.get("tags", ["malware"])[0] if entry.get("tags") else "malware",
                    "confidence": 0.90,
                    "source_feed": "malwarebazaar",
                    "tags": entry.get("tags") or [],
                    "last_seen": entry.get("first_seen", datetime.now(timezone.utc).isoformat()),
                    "file_name": entry.get("file_name"),
                    "file_type": entry.get("file_type_mime"),
                    "signature": entry.get("signature"),
                })
    except Exception as exc:
        logger.warning("[ThreatFeed] MalwareBazaar fetch failed: %s", exc)
    logger.info("[ThreatFeed] MalwareBazaar: %d IOCs", len(iocs))
    return iocs


async def _fetch_otx(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    """Fetch recent threat pulses from AlienVault OTX (requires OTX_API_KEY)."""
    if not OTX_API_KEY:
        return []
    iocs: List[Dict[str, Any]] = []
    headers = {"X-OTX-API-KEY": OTX_API_KEY}
    try:
        url = f"{OTX_BASE}/pulses/subscribed?limit=10&modified_since="
        async with session.get(url, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                logger.warning("[ThreatFeed] OTX returned HTTP %d", resp.status)
                return iocs
            data = await resp.json(content_type=None)
            for pulse in data.get("results", []):
                tags = [t.get("name", "") for t in (pulse.get("tags") or [])]
                for indicator in (pulse.get("indicators") or [])[:50]:
                    ioc_val = indicator.get("indicator", "")
                    ioc_type_raw = indicator.get("type", "")
                    ioc_type = _normalise_otx_type(ioc_type_raw)
                    if not ioc_val or not ioc_type:
                        continue
                    iocs.append({
                        "ioc_type": ioc_type,
                        "ioc_value": ioc_val,
                        "source_ip": ioc_val if ioc_type == "ip" else None,
                        "threat_type": pulse.get("name", "unknown"),
                        "confidence": 0.75,
                        "source_feed": "otx",
                        "tags": tags,
                        "last_seen": indicator.get("created", datetime.now(timezone.utc).isoformat()),
                        "pulse_id": pulse.get("id"),
                    })
                    if len(iocs) >= MAX_PER_SOURCE:
                        break
                if len(iocs) >= MAX_PER_SOURCE:
                    break
    except Exception as exc:
        logger.warning("[ThreatFeed] OTX fetch failed: %s", exc)
    logger.info("[ThreatFeed] OTX: %d IOCs", len(iocs))
    return iocs


def _normalise_otx_type(raw: str) -> Optional[str]:
    raw = raw.lower()
    if "ipv4" in raw or "ipv6" in raw:
        return "ip"
    if "domain" in raw or "hostname" in raw:
        return "domain"
    if "url" in raw:
        return "url"
    if "sha256" in raw or "sha1" in raw or "md5" in raw or "hash" in raw:
        return "hash"
    return None


# ── DB upsert ────────────────────────────────────────────────────────────────

async def _upsert_iocs(db, iocs: List[Dict[str, Any]]) -> int:
    """Upsert IOCs into `edr_ioc` collection; returns count of upserted docs."""
    if not iocs:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    upserted = 0
    for ioc in iocs:
        ioc["updated_at"] = now
        try:
            result = await db.edr_ioc.update_one(
                {"ioc_type": ioc["ioc_type"], "ioc_value": ioc["ioc_value"]},
                {"$set": ioc},
                upsert=True,
            )
            if result.upserted_id or result.modified_count:
                upserted += 1
        except Exception as exc:
            logger.debug("[ThreatFeed] Upsert error for %s: %s", ioc.get("ioc_value"), exc)
    return upserted


# ── Signature library versioning ─────────────────────────────────────────────

async def _record_sync_version(db, counts: Dict[str, int], total: int) -> None:
    """Write a version entry to `signature_library` for audit / rollback."""
    try:
        await db.signature_library.insert_one({
            "version_type": "threat_feed",
            "synced_at": datetime.now(timezone.utc).isoformat(),
            "source_counts": counts,
            "total_iocs": total,
        })
    except Exception as exc:
        logger.warning("[ThreatFeed] Could not write version record: %s", exc)


# ── Main sync entry point ────────────────────────────────────────────────────

async def run_threat_feed_sync(db) -> Dict[str, Any]:
    """
    Fetch IOCs from all configured sources and upsert into MongoDB.
    Returns a summary dict.
    """
    logger.info("[ThreatFeed] Starting IOC sync...")
    async with aiohttp.ClientSession() as session:
        urlhaus_iocs, bazaar_iocs, otx_iocs = await asyncio.gather(
            _fetch_urlhaus(session),
            _fetch_malwarebazaar(session),
            _fetch_otx(session),
            return_exceptions=True,
        )

    def _safe(result, name: str) -> List[Dict]:
        if isinstance(result, Exception):
            logger.warning("[ThreatFeed] %s gather error: %s", name, result)
            return []
        return result or []

    all_iocs = (
        _safe(urlhaus_iocs, "URLhaus")
        + _safe(bazaar_iocs, "MalwareBazaar")
        + _safe(otx_iocs, "OTX")
    )
    upserted = await _upsert_iocs(db, all_iocs)

    counts = {
        "urlhaus": len(_safe(urlhaus_iocs, "URLhaus")),
        "malwarebazaar": len(_safe(bazaar_iocs, "MalwareBazaar")),
        "otx": len(_safe(otx_iocs, "OTX")),
    }
    await _record_sync_version(db, counts, upserted)
    logger.info("[ThreatFeed] Sync complete - %d/%d IOCs upserted", upserted, len(all_iocs))
    return {"total_fetched": len(all_iocs), "upserted": upserted, "sources": counts}


# -- Background loop ----------------------------------------------------------

async def start_threat_feed_loop(db) -> None:
    """
    Async background loop: sync immediately, then every SYNC_INTERVAL_HOURS.
    Designed to be launched with asyncio.create_task() from app.py lifespan.
    """
    interval_seconds = SYNC_INTERVAL_HOURS * 3600
    logger.info(
        "[ThreatFeed] Background loop started - interval=%dh, OTX=%s",
        SYNC_INTERVAL_HOURS,
        "enabled" if OTX_API_KEY else "disabled (set OTX_API_KEY to enable)",
    )
    while True:
        try:
            await run_threat_feed_sync(db)
        except Exception as exc:
            logger.error("[ThreatFeed] Sync cycle error: %s", exc)
        await asyncio.sleep(interval_seconds)
