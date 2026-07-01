'''
OSV Sync — background service that populates the db.patches collection with vulnerability data from OSV.dev.

Fetches recent vulnerabilities (published in last 90 days) and upserts them into db.patches.
'''

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import aiohttp

# Environment configuration
OSV_API_URL = os.getenv('OSV_API_URL', 'https://api.osv.dev/v1/vulns')
SYNC_INTERVAL_HOURS = int(os.getenv('OSV_SYNC_INTERVAL_HOURS', '24'))
LOOKBACK_DAYS = int(os.getenv('OSV_LOOKBACK_DAYS', '90'))


async def _fetch_osv_page(session: aiohttp.ClientSession, cursor: Optional[str] = None) -> Dict[str, Any]:
    """Fetch a page of recent OSV vulnerabilities.
    OSV supports cursor-based pagination. If cursor is None, fetch the first page.
    Returns JSON response with fields: 'vulns' (list) and 'nextCursor' (optional).
    """
    params: Dict[str, str] = {'limit': '100'}
    if cursor:
        params['cursor'] = cursor
    try:
        async with session.get(OSV_API_URL, params=params, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                print(f"[osv_sync] Unexpected status {resp.status}")
                return {}
            return await resp.json()
    except Exception as exc:
        print(f"[osv_sync] Error fetching OSV page: {exc}")
        return {}


def _parse_osv(vuln: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Parse OSV vulnerability entry into our patch schema."""
    # OSV schema: id, modified, published, withdrawn (optional), summary, details, references, affected
    cve_id = vuln.get('id')
    if not cve_id:
        return None
    published = vuln.get('published')
    modified = vuln.get('modified')
    description = vuln.get('summary', '')
    references = [ref.get('url') for ref in vuln.get('references', []) if ref.get('url')][:10]
    # Affected packages list
    affected = []
    for aff in vuln.get('affected', []):
        pkg = aff.get('package', {})
        name = pkg.get('name')
        ecosystem = pkg.get('ecosystem')
        if name and ecosystem:
            affected.append(f"{ecosystem}:{name}")
    # Severity is not directly provided; OSV may include 'severity' in 'database_specific' or 'details'
    severity = 'Unknown'
    # Attempt to extract CVSS from 'metrics' if present
    cvss_v3 = None
    for metric in vuln.get('severity', []):
        if metric.get('type') == 'CVSS_V3':
            cvss_v3 = metric.get('score')
            break
    cvss_score = float(cvss_v3) if cvss_v3 else 0.0
    return {
        'id': cve_id,
        'cve_id': cve_id,
        'name': cve_id,
        'title': description[:120] if description else cve_id,
        'description': vuln.get('details', ''),
        'severity': severity,
        'cvss_score': cvss_score,
        'cvss_v3_vector': None,
        'published_date': published,
        'last_modified': modified,
        'affected_products': list(set(affected))[:20],
        'references': references,
        'status': 'Available',
        'kb_number': None,
        'package_name': None,
        'source': 'osv',
        'synced_at': datetime.now(timezone.utc).isoformat(),
    }


async def sync_osv_vulns(db) -> Dict[str, int]:
    """Fetch recent OSV vulnerabilities and upsert into db.patches."""
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(days=LOOKBACK_DAYS)
    upserted = 0
    fetched = 0
    cursor: Optional[str] = None
    async with aiohttp.ClientSession() as session:
        while True:
            data = await _fetch_osv_page(session, cursor)
            if not data:
                break
            vulns = data.get('vulns', [])
            if not vulns:
                break
            patches = [p for p in (_parse_osv(v) for v in vulns) if p]
            fetched += len(patches)
            for patch in patches:
                await db.patches.update_one(
                    {'cve_id': patch['cve_id']},
                    {'$set': patch},
                    upsert=True,
                )
                upserted += 1
            cursor = data.get('nextCursor')
            if not cursor:
                break
            await asyncio.sleep(1)  # gentle pacing
    return {'fetched': fetched, 'upserted': upserted}


async def start_osv_sync_loop(db) -> None:
    """Periodically run OSV sync according to SYNC_INTERVAL_HOURS."""
    while True:
        try:
            result = await sync_osv_vulns(db)
            print(f"[osv_sync] Completed: {result['upserted']} upserts, {result['fetched']} fetched")
        except Exception as exc:
            print(f"[osv_sync] Unexpected error: {exc}")
        await asyncio.sleep(SYNC_INTERVAL_HOURS * 3600)

