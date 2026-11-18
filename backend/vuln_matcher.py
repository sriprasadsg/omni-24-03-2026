"""Server-side vulnerability matching: the packages each endpoint reports (``software_inventory``) against OSV.dev,
flagged with CISA's Known Exploited Vulnerabilities (KEV) list.

* apt packages are checked against OSV's advisories for the endpoint's Ubuntu or Debian release, pip against PyPI,
  npm against npm. OSV answers for the exact installed version, so every match is exact (``confidence: exact``).
  A binary package whose name differs from its source package (libssl3t64 from openssl) is found only when OSV
  lists that binary; that gap is not guessed at.
* Findings go to ``vulnerabilities`` (what the Vulnerabilities screen reads) with source "osv": one row per
  endpoint, package and CVE (the OSV id when no CVE is named). A row the next run no longer finds (the package was
  upgraded) is marked Resolved with ``resolvedBy`` "osv-matcher"; found again, it reopens. A status a person set is
  left alone.
* Runs two minutes after start-up and then daily (VULN_MATCH_INTERVAL_HOURS). Advisories are cached by id and
  modified date in ``osv_advisories``; the KEV list is fetched once a day into ``kev_catalog``.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
OSV_VULN_URL = "https://api.osv.dev/v1/vulns/{}"
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
BATCH = 1000
FETCH_CONCURRENCY = 8
KEV_MAX_AGE = timedelta(hours=24)
SOURCE = "osv"
RESOLVER = "osv-matcher"
SEVERITY = {"negligible": "Low", "low": "Low", "medium": "Medium", "moderate": "Medium", "high": "High",
            "critical": "Critical", "important": "High"}


def _raw(db):
    return getattr(db, "_db", db)


def ecosystem(pkg_type: str, agent: Dict[str, Any]) -> Optional[str]:
    """OSV's ecosystem name for a package of this type on this endpoint, or None when it cannot be told."""
    kind = str(pkg_type or "").lower()
    if kind in ("pip", "pypi"):
        return "PyPI"
    if kind == "npm":
        return "npm"
    if kind not in ("apt", "deb", "dpkg"):
        return None
    meta = agent.get("meta") if isinstance(agent.get("meta"), dict) else {}
    name = f"{meta.get('os_full_name') or ''} {meta.get('os') or ''} {agent.get('os') or ''}".lower()
    release = str(agent.get("release") or meta.get("os_release") or meta.get("os_version") or "").strip()
    if "debian" in name and release:
        return f"Debian:{release.split('.')[0]}"
    if ("ubuntu" in name or not name.strip()) and release[:5].count(".") == 1 and release[:2].isdigit():
        major, minor = release[:5].split(".")[:2]
        return f"Ubuntu:{major}.{minor}" + (":LTS" if minor == "04" and int(major) % 2 == 0 else "")
    return None


def severity_of(advisory: Dict[str, Any]) -> str:
    for s in advisory.get("severity") or []:
        if s.get("type") == "Ubuntu" and str(s.get("score", "")).lower() in SEVERITY:
            return SEVERITY[str(s["score"]).lower()]
    db_sev = str((advisory.get("database_specific") or {}).get("severity") or "").lower()
    return SEVERITY.get(db_sev, "Medium")


def cve_of(advisory: Dict[str, Any]) -> str:
    names = [*(advisory.get("upstream") or []), *(advisory.get("aliases") or [])]
    return next((n for n in names if str(n).startswith("CVE-")), advisory.get("id"))


def fixed_version(advisory: Dict[str, Any], eco: str, package: str) -> Optional[str]:
    for a in advisory.get("affected") or []:
        pkg = a.get("package") or {}
        if pkg.get("name") == package and str(pkg.get("ecosystem", "")).split(":")[0] == eco.split(":")[0]:
            for r in a.get("ranges") or []:
                for e in r.get("events") or []:
                    if e.get("fixed"):
                        return e["fixed"]
    return None


async def _batch(client: httpx.AsyncClient, queries: List[Dict[str, Any]]) -> List[List[str]]:
    out: List[List[str]] = []
    for i in range(0, len(queries), BATCH):
        resp = await client.post(OSV_BATCH_URL, json={"queries": queries[i:i + BATCH]}, timeout=60.0)
        resp.raise_for_status()
        out += [[v["id"] for v in (r.get("vulns") or [])] for r in resp.json().get("results", [])]
    return out


async def _advisories(db, client: httpx.AsyncClient, ids: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    """Advisory records by id, from the cache or OSV."""
    ids = sorted(set(ids))
    cached = {d["id"]: d for d in await _raw(db).osv_advisories.find({"id": {"$in": ids}}, {"_id": 0}).to_list(len(ids) or 1)}
    gate = asyncio.Semaphore(FETCH_CONCURRENCY)

    async def fetch(vid: str) -> None:
        async with gate:
            try:
                resp = await client.get(OSV_VULN_URL.format(vid), timeout=30.0)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("OSV advisory %s not fetched: %s", vid, exc)
                return
            doc = {k: v for k, v in resp.json().items() if k in ("id", "modified", "summary", "details", "aliases",
                                                                  "upstream", "severity", "affected", "database_specific")}
            cached[vid] = doc
            await _raw(db).osv_advisories.replace_one({"id": vid}, doc, upsert=True)

    await asyncio.gather(*(fetch(v) for v in ids if v not in cached))
    return cached


async def kev_cves(db, client: httpx.AsyncClient, now: datetime) -> set:
    doc = await _raw(db).kev_catalog.find_one({"id": "kev"}, {"_id": 0})
    if doc and doc.get("fetchedAt") and now - datetime.fromisoformat(doc["fetchedAt"]) < KEV_MAX_AGE:
        return set(doc.get("cves") or [])
    try:
        resp = await client.get(KEV_URL, timeout=60.0)
        resp.raise_for_status()
        cves = sorted({v.get("cveID") for v in resp.json().get("vulnerabilities", []) if v.get("cveID")})
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("CISA KEV list not fetched: %s", exc)
        return set((doc or {}).get("cves") or [])
    await _raw(db).kev_catalog.replace_one({"id": "kev"}, {"id": "kev", "cves": cves, "fetchedAt": now.isoformat()}, upsert=True)
    return set(cves)


async def match_agent(db, client: httpx.AsyncClient, agent: Dict[str, Any], packages: List[Dict[str, Any]],
                      kev: set, now: datetime) -> Dict[str, int]:
    """Check one endpoint's packages; returns counts of open findings and rows resolved."""
    queries: List[Tuple[Dict[str, Any], str]] = []
    for p in packages:
        eco = ecosystem(p.get("pkg_type"), agent)
        if eco and p.get("name") and p.get("current_version"):
            queries.append(({"package": {"name": p["name"], "ecosystem": eco}, "version": p["current_version"]}, eco))
    hits = await _batch(client, [q for q, _ in queries]) if queries else []
    advisories = await _advisories(db, client, (v for ids in hits for v in ids))
    tenant, agent_id, stamp = agent.get("tenantId"), agent["id"], now.isoformat()
    raw, seen = _raw(db), set()
    for (query, eco), ids in zip(queries, hits):
        name, version = query["package"]["name"], query["version"]
        for vid in ids:
            adv = advisories.get(vid)
            if not adv:
                continue
            cve = cve_of(adv)
            if (name, cve) in seen:
                continue
            seen.add((name, cve))
            fix = fixed_version(adv, eco, name)
            await raw.vulnerabilities.update_one(
                {"tenantId": tenant, "agentId": agent_id, "cve_id": cve, "affected_path": name},
                {"$set": {"cveId": cve, "osvId": vid, "severity": severity_of(adv), "package": name, "affectedSoftware": name,
                          "installedVersion": version, "fixedVersion": fix, "ecosystem": eco, "kev": cve in kev,
                          "description": (adv.get("summary") or adv.get("details") or cve)[:500], "type": "package",
                          "remediation_hint": f"Upgrade {name} to {fix} or later" if fix else "No fixed version is published yet",
                          "hostname": agent.get("hostname"), "source": SOURCE, "confidence": "exact", "last_seen": stamp},
                 "$setOnInsert": {"status": "Open", "first_seen": stamp, "created_at": stamp}},
                upsert=True)
    reopened = await raw.vulnerabilities.update_many(
        {"tenantId": tenant, "agentId": agent_id, "source": SOURCE, "status": "Resolved", "resolvedBy": RESOLVER,
         "last_seen": stamp}, {"$set": {"status": "Open"}, "$unset": {"resolvedAt": "", "resolvedBy": ""}})
    resolved = await raw.vulnerabilities.update_many(
        {"tenantId": tenant, "agentId": agent_id, "source": SOURCE, "status": "Open", "last_seen": {"$ne": stamp}},
        {"$set": {"status": "Resolved", "resolvedAt": stamp, "resolvedBy": RESOLVER}})
    return {"open": len(seen), "resolved": resolved.modified_count, "reopened": reopened.modified_count, "checked": len(queries)}


async def run(db, client: Optional[httpx.AsyncClient] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Check every endpoint that reports packages."""
    now = now or datetime.now(timezone.utc)
    raw = _raw(db)
    owned = client is None
    client = client or httpx.AsyncClient()
    try:
        kev = await kev_cves(db, client, now)
        by_agent: Dict[str, List[Dict[str, Any]]] = {}
        async for p in raw.software_inventory.find({}, {"_id": 0, "agent_id": 1, "name": 1, "current_version": 1, "pkg_type": 1}):
            by_agent.setdefault(p.get("agent_id"), []).append(p)
        totals: Dict[str, Any] = {"agents": 0, "open": 0, "resolved": 0, "checked": 0}
        for agent_id, packages in by_agent.items():
            agent = await raw.agents.find_one({"id": agent_id}, {"_id": 0, "id": 1, "tenantId": 1, "hostname": 1, "os": 1,
                                                                 "release": 1, "meta.os": 1, "meta.os_release": 1,
                                                                 "meta.os_version": 1, "meta.os_full_name": 1})
            if not agent:
                continue
            try:
                got = await match_agent(db, client, agent, packages, kev, now)
            except httpx.HTTPError as exc:
                logger.warning("Vulnerability matching for %s failed: %s", agent.get("hostname"), exc)
                continue
            totals["agents"] += 1
            for k in ("open", "resolved", "checked"):
                totals[k] += got[k]
        logger.info("Vulnerability matching: %s", totals)
        return totals
    finally:
        if owned:
            await client.aclose()


async def match_loop() -> None:
    from database import get_database
    await asyncio.sleep(120)
    while True:
        try:
            await run(get_database())
        except Exception as exc:  # the loop must survive a bad run
            logger.warning("Vulnerability matching run failed: %s", exc)
        await asyncio.sleep(float(os.getenv("VULN_MATCH_INTERVAL_HOURS", "24")) * 3600)
