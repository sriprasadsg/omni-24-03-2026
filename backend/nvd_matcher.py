"""Server-side matching of the programs Windows endpoints report against NVD, flagged with CISA's KEV list.

* Programs come from each endpoint's latest heartbeat (``agents.meta.software_management.installed_software``:
  name, version, publisher). One is checked when ``windows_cpe_catalog`` names its NVD product; any other is
  counted as not checked, never guessed. The match is by name, so findings carry ``confidence: name``.
* NVD's own version filter returns nearly every CVE of a product, so each product's CVEs are downloaded once
  into ``nvd_product_cves`` (one row per product and CVE, holding only the criteria that can apply on Windows)
  and then refreshed daily by last-modified date (``nvd_products`` keeps when). The installed version is checked
  here against each criterion's version or range. A criterion naming no version or range (every version), or one
  for another platform (Android, macOS, Linux, iOS), does not count.
* Findings go to ``vulnerabilities`` with source "nvd", one row per endpoint, product and CVE, Resolved and
  reopened as vuln_matcher does. A product whose CVEs could not be loaded this run leaves its rows as they are.
* NVD allows 5 requests per 30 s without a key and 50 with one (NVD_API_KEY); requests are paced to that.
"""
import asyncio
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

from vuln_matcher import _raw, kev_cves
from windows_cpe_catalog import identify

logger = logging.getLogger(__name__)

NVD_CVE_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
PAGE = 2000
FULL_REFRESH = timedelta(days=110)  # NVD caps a last-modified window at 120 days
REFRESH_AFTER = timedelta(hours=20)
RETRY_STATUSES = {403, 429, 500, 502, 503, 504}  # NVD answers 403 when the rate is exceeded
RETRY_DELAYS = (30.0, 60.0)
SOURCE = "nvd"
RESOLVER = "nvd-matcher"
BOUNDS = ("versionStartIncluding", "versionStartExcluding", "versionEndIncluding", "versionEndExcluding")


class _Pacer:
    """Keeps requests at least ``interval`` seconds apart."""

    def __init__(self, interval: float):
        self.interval, self.last = interval, 0.0

    async def wait(self) -> None:
        delay = self.last + self.interval - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        self.last = time.monotonic()


def _pacer() -> _Pacer:
    return _Pacer(0.7 if os.getenv("NVD_API_KEY") else 6.5)


def version_key(value: Any) -> List[int]:
    """The numeric parts of a version ("8.2.12-0" -> [8, 2, 12, 0]); letters are ignored."""
    return [int(n) for n in re.findall(r"\d+", str(value or ""))]


def _cmp(a: List[int], b: List[int]) -> int:
    width = max(len(a), len(b))
    a, b = a + [0] * (width - len(a)), b + [0] * (width - len(b))
    return (a > b) - (a < b)


def _windows_target(parts: List[str]) -> bool:
    """A criterion's target software is any, none or Windows (not Android, macOS, Linux, iOS, a plugin host)."""
    return len(parts) >= 13 and parts[10] in ("*", "-", "windows")


def affects(match: Dict[str, Any], version: str) -> bool:
    """Whether one NVD criterion (vendor:product, version or range) covers this installed version on Windows."""
    parts = str(match.get("criteria") or "").split(":")
    if not _windows_target(parts):
        return False
    have = version_key(version)
    if not have:
        return False
    if parts[5] not in ("*", "-"):
        return _cmp(version_key(parts[5]), have) == 0
    if parts[5] == "-" or not any(match.get(k) for k in BOUNDS):
        return False
    checks = (("versionStartIncluding", lambda c: c >= 0), ("versionStartExcluding", lambda c: c > 0),
              ("versionEndIncluding", lambda c: c <= 0), ("versionEndExcluding", lambda c: c < 0))
    return all(ok(_cmp(have, version_key(match[k]))) for k, ok in checks if match.get(k))


def _windows_config(config: Dict[str, Any]) -> bool:
    """A configuration that ties the product to an operating system counts only when that system is Windows."""
    if str(config.get("operator") or "").upper() != "AND":
        return True
    systems = [m.get("criteria", "") for n in config.get("nodes") or [] for m in n.get("cpeMatch") or []
               if not m.get("vulnerable")]
    return not systems or any(c.startswith("cpe:2.3:o:microsoft:windows") for c in systems)


def product_criteria(cve: Dict[str, Any], product: str) -> List[Dict[str, Any]]:
    """The vulnerable criteria for this vendor:product that can apply on Windows."""
    prefix, out = f"cpe:2.3:a:{product}:", []
    for config in cve.get("configurations") or []:
        if not _windows_config(config):
            continue
        for node in config.get("nodes") or []:
            for m in node.get("cpeMatch") or []:
                crit = str(m.get("criteria") or "")
                if m.get("vulnerable") and crit.startswith(prefix) and _windows_target(crit.split(":")):
                    out.append({"criteria": crit, **{k: m[k] for k in BOUNDS if m.get(k)}})
    return out


def severity_of(cve: Dict[str, Any]) -> Tuple[str, Optional[float]]:
    metrics = cve.get("metrics") or {}
    for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        for m in metrics.get(key) or []:
            data = m.get("cvssData") or {}
            sev = data.get("baseSeverity") or m.get("baseSeverity")
            if sev:
                return str(sev).title(), data.get("baseScore")
    return "Medium", None


async def _nvd(client: httpx.AsyncClient, pacer: _Pacer, params: Dict[str, Any]) -> Dict[str, Any]:
    headers = {"apiKey": os.environ["NVD_API_KEY"]} if os.getenv("NVD_API_KEY") else {}
    for delay in (*RETRY_DELAYS, None):
        await pacer.wait()
        resp = await client.get(NVD_CVE_URL, params=params, headers=headers, timeout=120.0)
        if resp.status_code in RETRY_STATUSES and delay is not None:
            await asyncio.sleep(delay)
            continue
        resp.raise_for_status()
        return resp.json()


async def refresh_product(db, client: httpx.AsyncClient, pacer: _Pacer, product: str, now: datetime) -> int:
    """Bring ``nvd_product_cves`` for one product up to date; returns the CVE records read."""
    raw = _raw(db)
    state = await raw.nvd_products.find_one({"product": product}, {"_id": 0}) or {}
    fetched = datetime.fromisoformat(state["fetchedAt"]) if state.get("fetchedAt") else None
    if fetched and now - fetched < REFRESH_AFTER:
        return 0
    params: Dict[str, Any] = {"virtualMatchString": f"cpe:2.3:a:{product}", "resultsPerPage": PAGE}
    if fetched and now - fetched < FULL_REFRESH:
        params.update(lastModStartDate=(fetched - timedelta(hours=1)).isoformat(timespec="milliseconds"),
                      lastModEndDate=now.isoformat(timespec="milliseconds"))
    else:
        await raw.nvd_product_cves.delete_many({"product": product})
    read, start = 0, 0
    while True:
        page = await _nvd(client, pacer, {**params, "startIndex": start})
        for item in page.get("vulnerabilities") or []:
            cve = item.get("cve") or {}
            crit = product_criteria(cve, product) if cve.get("vulnStatus") != "Rejected" else []
            key = {"product": product, "cve": cve.get("id")}
            if not crit:
                await raw.nvd_product_cves.delete_one(key)
                continue
            sev, score = severity_of(cve)
            text = next((d.get("value") for d in cve.get("descriptions") or [] if d.get("lang") == "en"), "")
            await raw.nvd_product_cves.replace_one(key, {**key, "criteria": crit, "severity": sev, "score": score,
                                                         "kev": bool(cve.get("cisaExploitAdd")),
                                                         "summary": (text or cve.get("id"))[:500],
                                                         "modified": cve.get("lastModified")}, upsert=True)
        read += len(page.get("vulnerabilities") or [])
        start += int(page.get("resultsPerPage") or PAGE)
        if start >= int(page.get("totalResults") or 0):
            break
    await raw.nvd_products.replace_one({"product": product}, {"product": product, "fetchedAt": now.isoformat()},
                                       upsert=True)
    return read


def programs_of(agent: Dict[str, Any]) -> Tuple[Dict[Tuple[str, str], Set[str]], int]:
    """{(label, product): installed versions} for the catalogued programs, and the count of all programs."""
    listed = (((agent.get("meta") or {}).get("software_management") or {}).get("installed_software") or [])
    found: Dict[Tuple[str, str], Set[str]] = {}
    for p in listed:
        hit = identify(p.get("name"), p.get("publisher"), p.get("version")) if isinstance(p, dict) else None
        if hit:
            label, product, version = hit
            found.setdefault((label, product), set()).add(version)
    return found, len(listed)


async def match_agent(db, agent: Dict[str, Any], found: Dict[Tuple[str, str], Set[str]],
                      cves: Dict[str, List[Dict[str, Any]]], failed: Set[str], kev: set,
                      now: datetime) -> Dict[str, int]:
    tenant, agent_id, stamp = agent.get("tenantId"), agent["id"], now.isoformat()
    raw, opened = _raw(db), 0
    for (label, product), versions in found.items():
        if product in failed:
            continue
        for doc in cves.get(product, []):
            hit = [m for m in doc["criteria"] for v in versions if affects(m, v)]
            if not hit:
                continue
            installed = sorted({v for v in versions if any(affects(m, v) for m in doc["criteria"])}, key=version_key)
            ends = sorted((m["versionEndExcluding"] for m in hit if m.get("versionEndExcluding")), key=version_key)
            fix = ends[-1] if ends else None
            opened += 1
            await raw.vulnerabilities.update_one(
                {"tenantId": tenant, "agentId": agent_id, "cve_id": doc["cve"], "affected_path": label},
                {"$set": {"cveId": doc["cve"], "severity": doc["severity"], "cvssScore": doc.get("score"),
                          "package": label, "affectedSoftware": label, "installedVersion": ", ".join(installed),
                          "fixedVersion": fix, "ecosystem": "Windows", "cpeProduct": product,
                          "kev": doc.get("kev") or doc["cve"] in kev, "description": doc.get("summary"),
                          "type": "application", "hostname": agent.get("hostname"), "source": SOURCE,
                          "remediation_hint": f"Update {label} to {fix} or later" if fix else "Check the vendor's advisory for a fixed version",
                          "confidence": "name", "last_seen": stamp},
                 "$setOnInsert": {"status": "Open", "first_seen": stamp, "created_at": stamp}},
                upsert=True)
    scope = {"tenantId": tenant, "agentId": agent_id, "source": SOURCE, "cpeProduct": {"$nin": sorted(failed)}}
    reopened = await raw.vulnerabilities.update_many(
        {**scope, "status": "Resolved", "resolvedBy": RESOLVER, "last_seen": stamp},
        {"$set": {"status": "Open"}, "$unset": {"resolvedAt": "", "resolvedBy": ""}})
    resolved = await raw.vulnerabilities.update_many(
        {**scope, "status": "Open", "last_seen": {"$ne": stamp}},
        {"$set": {"status": "Resolved", "resolvedAt": stamp, "resolvedBy": RESOLVER}})
    return {"open": opened, "resolved": resolved.modified_count, "reopened": reopened.modified_count}


async def run(db, client: Optional[httpx.AsyncClient] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Check every endpoint that reports Windows programs."""
    now = now or datetime.now(timezone.utc)
    raw, owned = _raw(db), client is None
    client = client or httpx.AsyncClient()
    try:
        agents = await raw.agents.find(
            {"platform": {"$regex": "^windows", "$options": "i"},
             "meta.software_management.installed_software.0": {"$exists": True}},
            {"_id": 0, "id": 1, "tenantId": 1, "hostname": 1, "meta.software_management.installed_software": 1},
        ).to_list(10000)
        per_agent = [(a, *programs_of(a)) for a in agents]
        products = sorted({product for _, found, _ in per_agent for _, product in found})
        pacer, failed = _pacer(), set()
        for product in products:
            try:
                await refresh_product(db, client, pacer, product, now)
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("NVD CVEs for %s not loaded: %s", product, exc)
                failed.add(product)
        cves = {p: await raw.nvd_product_cves.find({"product": p}, {"_id": 0}).to_list(None)
                for p in products if p not in failed}
        kev = await kev_cves(db, client, now)
        totals = {"agents": 0, "programs": 0, "checked": 0, "open": 0, "resolved": 0, "productsFailed": len(failed)}
        for agent, found, listed in per_agent:
            got = await match_agent(db, agent, found, cves, failed, kev, now)
            totals["agents"] += 1
            totals["programs"] += listed
            totals["checked"] += sum(len(v) for v in found.values())
            totals["open"] += got["open"]
            totals["resolved"] += got["resolved"]
        logger.info("Windows program matching: %s", totals)
        return totals
    finally:
        if owned:
            await client.aclose()
