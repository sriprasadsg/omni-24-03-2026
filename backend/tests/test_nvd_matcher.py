"""Windows program matching against NVD (nvd_matcher, windows_cpe_catalog). protects/fails_when/no_claim per test;
real MongoDB, NVD and CISA faked with httpx.MockTransport (record shapes copied from live NVD answers on 2026-11-18)."""
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
import nvd_matcher
from tenant_context import reset_tenant_id, set_tenant_id
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from windows_cpe_catalog import identify

NOW = datetime(2026, 11, 18, 15, 0, tzinfo=timezone.utc)
ANY = ":*:*:*:*:*:*:*"


def crit(product: str, version: str = "*", target: str = "*", **bounds) -> dict:
    return {"vulnerable": True, "criteria": f"cpe:2.3:a:{product}:{version}:*:*:*:*:{target}:*:*", **bounds}


def cve(cve_id: str, matches: list, platform: str = "", severity: str = "HIGH", kev: bool = False,
        status: str = "Analyzed") -> dict:
    config = {"nodes": [{"operator": "OR", "cpeMatch": matches}]}
    if platform:
        config = {"operator": "AND", "nodes": [*config["nodes"], {"operator": "OR", "cpeMatch": [
            {"vulnerable": False, "criteria": f"cpe:2.3:o:{platform}" + ANY}]}]}
    return {"id": cve_id, "vulnStatus": status, "lastModified": "2026-11-01T00:00:00.000",
            "descriptions": [{"lang": "en", "value": f"{cve_id} in the product"}],
            "metrics": {"cvssMetricV31": [{"cvssData": {"baseSeverity": severity, "baseScore": 9.8}}]},
            "configurations": [config], **({"cisaExploitAdd": "2026-11-02"} if kev else {})}


CHROME = [
    cve("CVE-2026-0001", [crit("google:chrome", versionEndExcluding="140.0.7339.80")], severity="CRITICAL", kev=True),
    cve("CVE-2026-0002", [crit("google:chrome", versionEndExcluding="139.0")]),  # fixed before the installed one
    cve("CVE-2026-0003", [crit("google:chrome", versionEndExcluding="999")], platform="google:android"),
    cve("CVE-2026-0004", [crit("google:chrome")]),  # "every version", no range: not counted
    cve("CVE-2026-0005", [crit("google:chrome", versionEndExcluding="999")], status="Rejected"),
]
PYTHON = [cve("CVE-2026-1001", [crit("python:python", versionStartIncluding="3.13.0", versionEndExcluding="3.13.16")],
              severity="MEDIUM", platform="microsoft:windows")]


def nvd(records: dict, calls: list, busy: set = frozenset()):
    """A fake NVD/CISA: ``records`` maps vendor:product to CVE records; a product in ``busy`` answers 503."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.cisa.gov":
            return httpx.Response(200, json={"vulnerabilities": [{"cveID": "CVE-2026-1001"}]})
        q = request.url.params
        product = q["virtualMatchString"].removeprefix("cpe:2.3:a:")
        calls.append((product, q.get("startIndex"), q.get("lastModStartDate")))
        if product in busy:
            return httpx.Response(503)
        rows, start, size = records.get(product, []), int(q["startIndex"]), int(q["resultsPerPage"])
        return httpx.Response(200, json={"resultsPerPage": size, "startIndex": start, "totalResults": len(rows),
                                         "vulnerabilities": [{"cve": c} for c in rows[start:start + size]]})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def software(*rows):
    return {"software_management": {"installed_software": [{"name": n, "publisher": p, "version": v} for n, p, v in rows]}}


@pytest_asyncio.fixture
async def db(mongo_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(database.mongodb, "db", mongo_db)
    monkeypatch.setattr(nvd_matcher, "_pacer", lambda: nvd_matcher._Pacer(0))
    monkeypatch.setattr(nvd_matcher, "RETRY_DELAYS", (0, 0))
    monkeypatch.setattr(nvd_matcher, "PAGE", 2)  # five Chrome records span three pages
    await mongo_db.agents.insert_many([
        {"id": "win1", "tenantId": "t1", "hostname": "pc-1", "platform": "Windows", "meta": software(
            ("Google Chrome", "Google LLC", "140.0.7339.79"),
            ("Python 3.13.15 Core Interpreter (64-bit)", "Python Software Foundation", "3.13.15150.0"),
            ("Python 3.13.15 Test Suite (64-bit)", "Python Software Foundation", "3.13.15150.0"),
            ("Windows SDK", "Microsoft Corporation", "10.1.26100.8249"))},
        {"id": "win2", "tenantId": "t2", "hostname": "pc-2", "platform": "Windows",
         "meta": software(("Google Chrome", "Google LLC", "141.0.7390.54"))},
        {"id": "lin1", "tenantId": "t2", "hostname": "srv", "platform": "Linux",
         "meta": software(("Google Chrome", "Google LLC", "1.0"))}])
    token = set_tenant_id("platform-admin")
    try:
        yield mongo_db
    finally:
        reset_tenant_id(token)


@pytest.mark.parametrize("name,publisher,version,expected", [
    ("Python 3.13.15 Core Interpreter (64-bit)", "Python Software Foundation", "3.13.15150.0", ("Python", "python:python", "3.13.15")),
    ("OpenVPN 2.7.7-I001 amd64", "OpenVPN, Inc.", "2.7.701", ("OpenVPN", "openvpn:openvpn", "2.7.7")),
    ("OpenVPN Connect", "OpenVPN Inc.", "3.9.0", ("OpenVPN Connect", "openvpn:connect", "3.9.0")),
    ("Cisco Secure Client - AnyConnect VPN ", "Cisco Systems, Inc.", "5.1.12.146", ("Cisco Secure Client", "cisco:secure_client", "5.1.12.146")),
    ("Mozilla Firefox 115.5.0 ESR (x64 en-US)", "Mozilla", "115.5.0", ("Mozilla Firefox ESR", "mozilla:firefox_esr", "115.5.0")),
    ("Microsoft Edge WebView2 Runtime", "Microsoft Corporation", "157.0.4341.60", None),
    ("Google Chrome", "Some Repackager", "157.0.8103.79", None),
    ("Wazuh Agent", "Wazuh, Inc.", "4.14.10", None),
    ("Python 3.13.15 Test Suite (64-bit)", "Python Software Foundation", "3.13.15150.0", None),
    ("Google Chrome", "Google LLC", "", None),
])
def test_the_catalogue_names_the_product_and_real_version_and_leaves_the_rest_unchecked(name, publisher, version, expected):
    """protects=a catalogued program maps to its NVD product with the version people know (from the name when the
    version field is an MSI build), one Python component stands for the install, an unknown or lookalike program
    is not checked; fails_when=Python 3.13.15 is checked as 3.13.15150, a repackaged "Google Chrome" or the Wazuh
    agent is matched against products it is not; no_claim=coverage of programs outside the catalogue"""
    assert identify(name, publisher, version) == expected


@pytest.mark.parametrize("match,version,expected", [
    (crit("google:chrome", versionEndExcluding="140.0.7339.80"), "140.0.7339.79", True),
    (crit("google:chrome", versionEndExcluding="140.0.7339.80"), "140.0.7339.80", False),
    (crit("x:y", versionStartIncluding="2.0", versionEndIncluding="2.3"), "2.3", True),
    (crit("x:y", versionStartIncluding="2.0", versionEndIncluding="2.3"), "2.4", False),
    (crit("x:y", versionStartExcluding="2.0", versionEndIncluding="2.3"), "2.0", False),
    (crit("x:y", "1.2.3"), "1.2.3", True),
    (crit("x:y", "1.2.3"), "1.2.4", False),
    (crit("x:y"), "1.0", False),
    (crit("x:y", "-"), "1.0", False),
    (crit("x:y", target="android", versionEndExcluding="9"), "1.0", False),
    (crit("x:y", target="windows", versionEndExcluding="9"), "1.0", True),
    (crit("apachefriends:xampp", versionEndExcluding="8.2.13"), "8.2.12-0", True),
])
def test_a_criterion_counts_only_for_its_version_or_range_on_windows(match, version, expected):
    """protects=range bounds (including/excluding), an exact version, Windows or any target software;
    fails_when=a criterion for every version, for Android, or one ending at the installed version flags it;
    no_claim=NVD's own accuracy"""
    assert nvd_matcher.affects(match, version) is expected


@pytest.mark.asyncio
async def test_findings_are_per_windows_endpoint_with_fix_kev_and_tenant_and_refresh_by_modified_date(db):
    """protects=one Open row per Windows endpoint, product and CVE (severity, fix, KEV from NVD or CISA, tenant,
    confidence "name"); Android-only, every-version, rejected and already-fixed CVEs and Linux endpoints give none;
    NVD is not asked again within the day, then only for records modified since, and a CVE narrowed below the
    installed version resolves; fails_when=findings cross tenants or platforms, each run downloads every CVE again,
    a narrowed CVE stays open; no_claim=-"""
    calls: list = []
    async with nvd({"google:chrome": CHROME, "python:python": PYTHON}, calls) as client:
        out = await nvd_matcher.run(db, client, NOW)
    assert out == {"agents": 2, "programs": 5, "checked": 3, "open": 2, "resolved": 0, "productsFailed": 0}
    assert [c[1] for c in calls if c[0] == "google:chrome"] == ["0", "2", "4"]
    rows = {r["cve_id"]: r for r in await db.vulnerabilities.find({}, {"_id": 0}).to_list(10)}
    assert set(rows) == {"CVE-2026-0001", "CVE-2026-1001"}
    chrome, py = rows["CVE-2026-0001"], rows["CVE-2026-1001"]
    assert (chrome["tenantId"], chrome["agentId"], chrome["affected_path"], chrome["severity"]) == ("t1", "win1", "Google Chrome", "Critical")
    assert chrome["fixedVersion"] == "140.0.7339.80" and chrome["kev"] is True and chrome["installedVersion"] == "140.0.7339.79"
    assert (chrome["source"], chrome["confidence"], chrome["status"], chrome["cpeProduct"]) == ("nvd", "name", "Open", "google:chrome")
    assert py["installedVersion"] == "3.13.15" and py["severity"] == "Medium" and py["kev"] is True  # KEV via CISA
    assert await db.nvd_product_cves.count_documents({"product": "google:chrome"}) == 3  # not Android, not rejected

    calls.clear()
    async with nvd({"google:chrome": CHROME, "python:python": PYTHON}, calls) as client:
        await nvd_matcher.run(db, client, NOW + timedelta(hours=2))
    assert calls == []

    narrowed = [cve("CVE-2026-0001", [crit("google:chrome", versionEndExcluding="140.0.7339.70")], severity="CRITICAL")]
    async with nvd({"google:chrome": narrowed, "python:python": []}, calls) as client:
        out = await nvd_matcher.run(db, client, NOW + timedelta(days=2))
    assert all(c[2] for c in calls)  # last-modified window only
    assert out["resolved"] == 1
    assert (await db.vulnerabilities.find_one({"cve_id": "CVE-2026-0001"}))["resolvedBy"] == "nvd-matcher"
    assert (await db.vulnerabilities.find_one({"cve_id": "CVE-2026-1001"}))["status"] == "Open"


@pytest.mark.asyncio
async def test_a_product_nvd_cannot_load_keeps_its_findings_and_an_uninstalled_program_resolves(db):
    """protects=when NVD keeps failing for one product its findings stay as they are; a program removed from the
    endpoint resolves; fails_when=an NVD outage marks findings Resolved, or an uninstalled program's CVEs stay
    open forever; no_claim=-"""
    async with nvd({"google:chrome": CHROME, "python:python": PYTHON}, []) as client:
        await nvd_matcher.run(db, client, NOW)
    await db.agents.update_one({"id": "win1"}, {"$set": {"meta": software(
        ("Python 3.13.15 Core Interpreter (64-bit)", "Python Software Foundation", "3.13.15150.0"))}})
    async with nvd({"google:chrome": CHROME, "python:python": PYTHON}, [], busy={"python:python"}) as client:
        out = await nvd_matcher.run(db, client, NOW + timedelta(days=1))
    assert out["productsFailed"] == 1 and out["resolved"] == 1
    assert (await db.vulnerabilities.find_one({"cve_id": "CVE-2026-0001"}))["status"] == "Resolved"
    assert (await db.vulnerabilities.find_one({"cve_id": "CVE-2026-1001"}))["status"] == "Open"
