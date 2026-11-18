"""Threat-intel indicators for SOC alerts, downloaded daily from abuse.ch.

* Feodo Tracker's botnet C2 IP blocklist needs no key.
* ThreatFox (the last day's IPs, domains and SHA-256 hashes) needs a free abuse.ch Auth-Key in
  ABUSECH_AUTH_KEY. Without it the feed is reported as "needs a key", never faked. (abuse.ch withdrew
  the keyless MalwareBazaar, ThreatFox and URLhaus exports; they answer 410 Gone.)

Indicators live in ``ti_indicators`` (platform-wide, no tenant: read and written through the raw handle)
and expire 30 days after a feed last listed them; ``ti_feed_status`` keeps each feed's last result. Only
lists are downloaded; nothing about the platform's alerts is sent to abuse.ch.
"""
import asyncio
import ipaddress
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List

import httpx

logger = logging.getLogger(__name__)

FEODO_URL = "https://feodotracker.abuse.ch/downloads/ipblocklist_recommended.txt"
THREATFOX_URL = "https://threatfox-api.abuse.ch/api/v1/"
EXPIRE = timedelta(days=30)
INTERVAL_SECONDS = 86400
MAX_PER_FEED = 20000


def _ip(value: str) -> str:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return ""


def parse_feodo(text: str) -> List[Dict[str, Any]]:
    out = []
    for line in str(text or "").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and _ip(line):
            out.append({"value": _ip(line), "kind": "ip", "malware": "botnet C2 (Feodo Tracker)"})
    return out[:MAX_PER_FEED]


def parse_threatfox(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for item in (body or {}).get("data") or []:
        if not isinstance(item, dict):
            continue
        kind, ioc, malware = item.get("ioc_type"), str(item.get("ioc") or ""), item.get("malware_printable") or item.get("malware")
        if kind == "ip:port" and _ip(ioc.rsplit(":", 1)[0]):
            out.append({"value": _ip(ioc.rsplit(":", 1)[0]), "kind": "ip", "malware": malware})
        elif kind == "sha256_hash" and len(ioc) == 64:
            out.append({"value": ioc.lower(), "kind": "sha256", "malware": malware})
        elif kind == "domain" and ioc:
            out.append({"value": ioc.lower().strip("."), "kind": "domain", "malware": malware})
    return out[:MAX_PER_FEED]


async def ensure_indexes(raw) -> None:
    await raw.ti_indicators.create_index([("value", 1), ("source", 1)], unique=True, name="ti_value_source")
    await raw.ti_indicators.create_index("expiresAt", expireAfterSeconds=0, name="ti_expiry")


async def _store(raw, source: str, items: List[Dict[str, Any]], now: datetime) -> int:
    for item in items:
        await raw.ti_indicators.update_one(
            {"value": item["value"], "source": source},
            {"$set": {"kind": item["kind"], "malware": item.get("malware"), "lastListedAt": now, "expiresAt": now + EXPIRE},
             "$setOnInsert": {"firstListedAt": now}}, upsert=True)
    return len(items)


async def _status(raw, source: str, **fields: Any) -> None:
    await raw.ti_feed_status.update_one({"source": source}, {"$set": {"source": source, **fields}}, upsert=True)


async def refresh(raw, now: datetime = None) -> Dict[str, Any]:
    """Download every feed once; each feed's result (count or error) is recorded on its own."""
    now = now or datetime.now(timezone.utc)
    await ensure_indexes(raw)
    out: Dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        try:
            resp = await client.get(FEODO_URL)
            resp.raise_for_status()
            n = await _store(raw, "feodo", parse_feodo(resp.text), now)
            await _status(raw, "feodo", ok=True, count=n, at=now, error=None, needsKey=False)
            out["feodo"] = n
        except Exception as e:
            await _status(raw, "feodo", ok=False, at=now, error=str(e)[:200], needsKey=False)
            out["feodo"] = f"failed: {e}"
        key = os.getenv("ABUSECH_AUTH_KEY", "").strip()
        if not key:
            await _status(raw, "threatfox", ok=False, at=now, error=None, needsKey=True, count=0)
            out["threatfox"] = "needs ABUSECH_AUTH_KEY"
        else:
            try:
                resp = await client.post(THREATFOX_URL, json={"query": "get_iocs", "days": 1}, headers={"Auth-Key": key})
                resp.raise_for_status()
                n = await _store(raw, "threatfox", parse_threatfox(resp.json()), now)
                await _status(raw, "threatfox", ok=True, count=n, at=now, error=None, needsKey=False)
                out["threatfox"] = n
            except Exception as e:
                await _status(raw, "threatfox", ok=False, at=now, error=str(e)[:200], needsKey=False)
                out["threatfox"] = f"failed: {e}"
    return out


async def lookup(raw, values: Iterable[str]) -> List[Dict[str, Any]]:
    wanted = sorted({str(v).strip().lower() for v in values if v})
    if not wanted:
        return []
    rows = await raw.ti_indicators.find({"value": {"$in": wanted}}, {"_id": 0, "value": 1, "kind": 1, "source": 1, "malware": 1}).to_list(50)
    return rows


async def feed_status(raw) -> Dict[str, Any]:
    feeds = await raw.ti_feed_status.find({}, {"_id": 0}).to_list(10)
    for f in feeds:
        if isinstance(f.get("at"), datetime):
            f["at"] = f["at"].isoformat()
    return {"feeds": feeds, "indicators": await raw.ti_indicators.estimated_document_count()}


async def feed_loop() -> None:
    """Background task: refresh a minute after start, then once a day. Never raises."""
    await asyncio.sleep(60)
    while True:
        try:
            from database import mongodb
            if mongodb.db is not None:
                result = await refresh(mongodb.db)
                logger.info("Threat-intel feeds refreshed: %s", result)
        except Exception as e:
            logger.error("Threat-intel refresh failed: %s", e)
        await asyncio.sleep(INTERVAL_SECONDS)
