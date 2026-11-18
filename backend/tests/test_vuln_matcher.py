"""Server-side vulnerability matching (vuln_matcher). protects/fails_when/no_claim per test; real MongoDB, OSV and
CISA faked with httpx.MockTransport (shapes copied from live answers on 2026-11-18)."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
import vuln_matcher
from tenant_context import reset_tenant_id, set_tenant_id
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

NOW = datetime(2026, 11, 18, 15, 0, tzinfo=timezone.utc)
CURL_ADV = {"id": "UBUNTU-CVE-2024-11053", "modified": "2026-01-01T00:00:00Z", "upstream": ["CVE-2024-11053"],
            "summary": "curl could leak the password", "severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N"},
                                                                     {"type": "Ubuntu", "score": "low"}],
            "affected": [{"package": {"ecosystem": "Ubuntu:24.04:LTS", "name": "curl"},
                          "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "8.5.0-2ubuntu10.6"}]}]}]}
URLLIB_ADV = {"id": "GHSA-34jh-p97f-mpxf", "modified": "2026-01-01T00:00:00Z", "aliases": ["CVE-2024-37891"],
              "summary": "urllib3 Proxy-Authorization header kept on redirect", "database_specific": {"severity": "MODERATE"},
              "affected": [{"package": {"ecosystem": "PyPI", "name": "urllib3"},
                            "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "1.26.19"}]}]}]}


def osv(vulnerable: dict, calls: list, busy: int = 0):
    """A fake OSV/CISA: ``vulnerable`` maps (name, version) to advisory ids; each OSV path answers 503 ``busy`` times
    before it answers."""
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.host == "www.cisa.gov":
            return httpx.Response(200, json={"vulnerabilities": [{"cveID": "CVE-2024-37891"}]})
        if calls.count(request.url.path) <= busy:
            return httpx.Response(503)
        if request.url.path == "/v1/querybatch":
            qs = json.loads(request.content)["queries"]
            return httpx.Response(200, json={"results": [{"vulns": [{"id": i} for i in vulnerable.get((q["package"]["name"], q["version"]), [])]}
                                                         for q in qs]})
        vid = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json={CURL_ADV["id"]: CURL_ADV, URLLIB_ADV["id"]: URLLIB_ADV}[vid])
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest_asyncio.fixture
async def db(mongo_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(database.mongodb, "db", mongo_db)
    await mongo_db.agents.insert_many([
        {"id": "ag1", "tenantId": "t1", "hostname": "srv-1", "release": "24.04", "platform": "Linux"},
        {"id": "ag9", "tenantId": "t2", "hostname": "other", "release": "24.04", "platform": "Linux"}])
    await mongo_db.software_inventory.insert_many([
        {"agent_id": "ag1", "tenantId": "t1", "name": "curl", "current_version": "8.5.0-2ubuntu10.1", "pkg_type": "apt"},
        {"agent_id": "ag1", "tenantId": "t1", "name": "urllib3", "current_version": "1.26.5", "pkg_type": "pip"},
        {"agent_id": "ag1", "tenantId": "t1", "name": "vim", "current_version": "2:9.1", "pkg_type": "apt"},
        {"agent_id": "ag9", "tenantId": "t2", "name": "curl", "current_version": "8.5.0-2ubuntu10.16", "pkg_type": "apt"}])
    token = set_tenant_id("platform-admin")
    try:
        yield mongo_db
    finally:
        reset_tenant_id(token)


@pytest.mark.parametrize("pkg_type,agent,expected", [
    ("apt", {"release": "24.04"}, "Ubuntu:24.04:LTS"), ("apt", {"release": "23.10"}, "Ubuntu:23.10"),
    ("apt", {"meta": {"os_full_name": "Debian GNU/Linux 12 (bookworm)", "os_release": "12"}}, "Debian:12"),
    ("apt", {"meta": {"os_full_name": "Microsoft Windows 11 Pro"}}, None), ("pip", {}, "PyPI"), ("npm", {}, "npm"),
    ("msi", {"release": "24.04"}, None),
])
def test_ecosystem_names_follow_osv(pkg_type, agent, expected):
    """protects=apt maps to OSV's Ubuntu (":LTS" on even .04) or Debian release, pip/npm to their registries, an
    unknown kind to nothing; fails_when=packages are queried in the wrong ecosystem (silently no findings); no_claim=-"""
    assert vuln_matcher.ecosystem(pkg_type, agent) == expected


@pytest.mark.asyncio
async def test_findings_are_exact_per_endpoint_with_fix_and_kev_and_never_cross_tenants(db):
    """protects=one Open row per endpoint, package and CVE with severity (Ubuntu priority, GHSA rating), installed and
    fixed versions, a KEV flag and the tenant of the endpoint; an up-to-date endpoint gets none; advisories are cached;
    fails_when=rows lack the fix or tenant, or a second run refetches every advisory; no_claim=OSV's own accuracy"""
    calls: list = []
    vulnerable = {("curl", "8.5.0-2ubuntu10.1"): [CURL_ADV["id"]], ("urllib3", "1.26.5"): [URLLIB_ADV["id"]]}
    async with osv(vulnerable, calls) as client:
        out = await vuln_matcher.run(db, client, NOW)
    assert out == {"agents": 2, "open": 2, "resolved": 0, "checked": 4}
    rows = {r["cve_id"]: r for r in await db.vulnerabilities.find({}, {"_id": 0}).to_list(10)}
    assert set(rows) == {"CVE-2024-11053", "CVE-2024-37891"}
    curl = rows["CVE-2024-11053"]
    assert (curl["tenantId"], curl["agentId"], curl["severity"], curl["status"]) == ("t1", "ag1", "Low", "Open")
    assert curl["fixedVersion"] == "8.5.0-2ubuntu10.6" and curl["remediation_hint"] == "Upgrade curl to 8.5.0-2ubuntu10.6 or later"
    assert curl["kev"] is False and rows["CVE-2024-37891"]["kev"] is True and rows["CVE-2024-37891"]["severity"] == "Medium"
    assert curl["source"] == "osv" and curl["confidence"] == "exact" and curl["installedVersion"] == "8.5.0-2ubuntu10.1"
    calls.clear()
    async with osv(vulnerable, calls) as client:
        await vuln_matcher.run(db, client, NOW + timedelta(hours=1))
    assert calls == ["/v1/querybatch", "/v1/querybatch"]  # advisories and KEV from the cache


@pytest.mark.asyncio
async def test_an_upgraded_package_resolves_and_a_person_set_status_is_kept(db):
    """protects=a finding the next run does not see is Resolved by the matcher and reopens if it returns; a status a
    person set (Accepted) is not touched; fails_when=fixed issues stay open forever, or the matcher overrides an
    analyst's decision; no_claim=-"""
    vulnerable = {("curl", "8.5.0-2ubuntu10.1"): [CURL_ADV["id"]], ("urllib3", "1.26.5"): [URLLIB_ADV["id"]]}
    async with osv(vulnerable, []) as client:
        await vuln_matcher.run(db, client, NOW)
    await db.vulnerabilities.update_one({"cve_id": "CVE-2024-37891"}, {"$set": {"status": "Accepted"}})
    async with osv({}, []) as client:  # both packages upgraded
        out = await vuln_matcher.run(db, client, NOW + timedelta(days=1))
    assert out["resolved"] == 1
    curl = await db.vulnerabilities.find_one({"cve_id": "CVE-2024-11053"})
    assert curl["status"] == "Resolved" and curl["resolvedBy"] == "osv-matcher"
    assert (await db.vulnerabilities.find_one({"cve_id": "CVE-2024-37891"}))["status"] == "Accepted"
    async with osv(vulnerable, []) as client:  # curl downgraded again
        await vuln_matcher.run(db, client, NOW + timedelta(days=2))
    curl = await db.vulnerabilities.find_one({"cve_id": "CVE-2024-11053"})
    assert curl["status"] == "Open" and "resolvedBy" not in curl


@pytest.mark.asyncio
async def test_a_brief_osv_overload_is_retried_and_an_outage_resolves_nothing(db, monkeypatch):
    """protects=an OSV 503 on the batch or an advisory is tried again, so the finding is recorded this run; when OSV
    stays down the endpoint is skipped and its open findings stay open; fails_when=a burst of 503s hides findings until
    the next daily run (live 2026-11-18: 11 advisories), or an outage marks every finding Resolved; no_claim=-"""
    monkeypatch.setattr(vuln_matcher, "RETRY_DELAYS", (0, 0))
    vulnerable = {("curl", "8.5.0-2ubuntu10.1"): [CURL_ADV["id"]], ("urllib3", "1.26.5"): [URLLIB_ADV["id"]]}
    async with osv(vulnerable, [], busy=2) as client:
        out = await vuln_matcher.run(db, client, NOW)
    assert out["open"] == 2
    async with osv(vulnerable, [], busy=3) as client:
        out = await vuln_matcher.run(db, client, NOW + timedelta(days=1))
    # srv-1 gets all three 503s and is skipped; the other endpoint's batch then gets through
    assert out == {"agents": 1, "open": 0, "resolved": 0, "checked": 1}
    assert await db.vulnerabilities.count_documents({"agentId": "ag1", "status": "Open"}) == 2
