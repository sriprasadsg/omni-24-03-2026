"""
NVD CVE Sync — background service that populates the db.patches collection
with real vulnerability data from the NIST National Vulnerability Database.

Fetches Critical + High CVEs published in the last 90 days, enriches each
with EPSS exploitation probability, then upserts into db.patches so the
patch management endpoints have data to work with.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import aiohttp

NVD_API_KEY = os.getenv("NVD_API_KEY", "")
NVD_BASE_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
EPSS_BASE_URL = "https://api.first.org/data/v1/epss"
SYNC_INTERVAL_HOURS = int(os.getenv("NVD_SYNC_INTERVAL_HOURS", "24"))
LOOKBACK_DAYS = 90
PAGE_SIZE = 100


async def _fetch_nvd_page(
    session: aiohttp.ClientSession,
    start_index: int,
    pub_start: str,
    pub_end: str,
) -> Dict[str, Any]:
    headers = {"apiKey": NVD_API_KEY} if NVD_API_KEY else {}
    params = {
        "pubStartDate": pub_start,
        "pubEndDate": pub_end,
        "cvssV3Severity": "CRITICAL",
        "resultsPerPage": PAGE_SIZE,
        "startIndex": start_index,
    }
    for attempt in range(3):
        try:
            timeout = aiohttp.ClientTimeout(total=20 + attempt * 10)
            async with session.get(NVD_BASE_URL, headers=headers, params=params, timeout=timeout) as resp:
                if resp.status == 429:
                    await asyncio.sleep(2 ** attempt * 6)
                    continue
                if resp.status != 200:
                    return {}
                return await resp.json()
        except asyncio.TimeoutError:
            await asyncio.sleep(2 ** attempt)
        except Exception as exc:
            print(f"[nvd_sync] NVD fetch error (attempt {attempt+1}): {exc}")
            return {}
    return {}


async def _fetch_epss_batch(session: aiohttp.ClientSession, cve_ids: List[str]) -> Dict[str, float]:
    """Return {cve_id: epss_score} for a batch of CVE IDs."""
    if not cve_ids:
        return {}
    try:
        params = {"cve": ",".join(cve_ids)}
        async with session.get(EPSS_BASE_URL, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return {}
            data = await resp.json()
            return {row["cve"]: float(row.get("epss", 0)) for row in data.get("data", [])}
    except Exception as exc:
        print(f"[nvd_sync] EPSS fetch error: {exc}")
        return {}


def _parse_cve(vuln: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    cve = vuln.get("cve", {})
    cve_id = cve.get("id", "")
    if not cve_id:
        return None

    metrics = cve.get("metrics", {})
    cvss_v3 = (metrics.get("cvssMetricV31") or metrics.get("cvssMetricV30") or [{}])[0].get("cvssData", {})
    cvss_v2 = (metrics.get("cvssMetricV2") or [{}])[0].get("cvssData", {})

    base_score = cvss_v3.get("baseScore") or cvss_v2.get("baseScore") or 0.0
    severity = cvss_v3.get("baseSeverity") or cvss_v2.get("baseSeverity") or "Unknown"

    descriptions = cve.get("descriptions", [])
    description = next((d["value"] for d in descriptions if d.get("lang") == "en"), "")

    # Extract affected CPEs to build affected_products list
    affected = []
    for config in cve.get("configurations", []):
        for node in config.get("nodes", []):
            for match in node.get("cpeMatch", []):
                cpe = match.get("criteria", "")
                parts = cpe.split(":")
                if len(parts) > 4:
                    affected.append(f"{parts[3]} {parts[4]}")

    return {
        "id": cve_id,
        "cve_id": cve_id,
        "name": cve_id,
        "title": description[:120] if description else cve_id,
        "description": description,
        "severity": severity.capitalize() if severity else "Unknown",
        "cvss_score": base_score,
        "cvss_v3_vector": cvss_v3.get("vectorString"),
        "published_date": cve.get("published"),
        "last_modified": cve.get("lastModified"),
        "affected_products": list(set(affected))[:20],
        "references": [r.get("url") for r in cve.get("references", [])[:10]],
        "status": "Available",
        "kb_number": None,
        "package_name": None,
        "source": "nvd",
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }


async def sync_nvd_cves(db) -> Dict[str, int]:
    """
    Fetch recent Critical CVEs from NVD, enrich with EPSS, upsert into db.patches.
    Returns summary dict with counts.
    """
    now = datetime.now(timezone.utc)
    pub_start = (now - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%dT00:00:00.000")
    pub_end = now.strftime("%Y-%m-%dT%H:%M:%S.000")

    upserted = 0
    fetched = 0

    async with aiohttp.ClientSession() as session:
        start_index = 0
        while True:
            data = await _fetch_nvd_page(session, start_index, pub_start, pub_end)
            if not data:
                break

            vulns = data.get("vulnerabilities", [])
            total = data.get("totalResults", 0)

            if not vulns:
                break

            # Parse CVE docs
            patches = [p for p in (_parse_cve(v) for v in vulns) if p]
            fetched += len(patches)

            # Enrich with EPSS in batches of 50
            cve_ids = [p["cve_id"] for p in patches]
            epss_map: Dict[str, float] = {}
            for i in range(0, len(cve_ids), 50):
                batch = await _fetch_epss_batch(session, cve_ids[i:i + 50])
                epss_map.update(batch)
                await asyncio.sleep(0.5)

            for patch in patches:
                epss = epss_map.get(patch["cve_id"], 0.0)
                patch["epss_score"] = epss
                patch["exploit_probability"] = f"{epss * 100:.2f}%"

            # Upsert into db.patches
            for patch in patches:
                await db.patches.update_one(
                    {"cve_id": patch["cve_id"]},
                    {"$set": patch},
                    upsert=True,
                )
                upserted += 1

            start_index += PAGE_SIZE
            if start_index >= total:
                break

            # Respect NVD rate limit (6 requests/30s without key, 50/30s with key)
            await asyncio.sleep(1 if NVD_API_KEY else 6)

    # Also fetch High severity CVEs (separate query)
    async with aiohttp.ClientSession() as session:
        headers = {"apiKey": NVD_API_KEY} if NVD_API_KEY else {}
        params = {
            "pubStartDate": pub_start,
            "pubEndDate": pub_end,
            "cvssV3Severity": "HIGH",
            "resultsPerPage": PAGE_SIZE,
            "startIndex": 0,
        }
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with session.get(NVD_BASE_URL, headers=headers, params=params, timeout=timeout) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for vuln in data.get("vulnerabilities", []):
                        patch = _parse_cve(vuln)
                        if patch:
                            fetched += 1
                            await db.patches.update_one(
                                {"cve_id": patch["cve_id"]},
                                {"$set": patch},
                                upsert=True,
                            )
                            upserted += 1
        except Exception as exc:
            print(f"[nvd_sync] High severity fetch error: {exc}")

    print(f"[nvd_sync] Sync complete — fetched={fetched}, upserted={upserted}")
    return {"fetched": fetched, "upserted": upserted}


async def start_nvd_sync_loop(db):
    """Run NVD sync immediately on startup, then every SYNC_INTERVAL_HOURS."""
    while True:
        try:
            await sync_nvd_cves(db)
        except Exception as exc:
            print(f"[nvd_sync] Sync loop error: {exc}")
        await asyncio.sleep(SYNC_INTERVAL_HOURS * 3600)
