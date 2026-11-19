"""Fleet connector (fleet_service; open-source device management on osquery). protects/fails_when/no_claim per test;
Fleet's REST API is mocked at the HTTP layer, MongoDB is real.
"""
import json
import os
import sys

import httpx
import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import fleet_service as fs
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

T = "t-fleet"
BASE = "https://fleet.example.com"
TOKEN = "kbdYZ3w0Pq9" * 4 + "=="
REAL = httpx.AsyncClient


def _host(i, name, platform="ubuntu", failing=0):
    return {"id": i, "hostname": name, "display_name": name, "platform": platform, "os_version": "Ubuntu 24.04.5 LTS",
            "hardware_model": "Virtual Machine", "hardware_vendor": "Microsoft Corporation", "hardware_serial": f"SN{i}",
            "status": "online", "seen_time": "2026-11-19T09:00:00Z", "last_enrolled_at": "2026-11-19T08:00:00Z",
            "primary_ip": "10.0.0.4", "primary_mac": "00:0d:3a:aa:bb:cc", "osquery_version": "5.20.0",
            "issues": {"failing_policies_count": failing, "critical_vulnerabilities_count": 0, "total_issues_count": failing}}


@pytest_asyncio.fixture
async def fleet(mongo_db, monkeypatch):  # noqa: F811
    calls, state = [], {"hosts": [_host(1, "omniai-copy"), _host(2, "mac-01", "darwin", failing=2)], "policies": [{"id": 1}],
                        "status": 200, "per_page": fs.PER_PAGE}

    def handler(request: httpx.Request):
        calls.append(request)
        if request.headers.get("authorization") != f"Bearer {TOKEN}" or state["status"] != 200:
            return httpx.Response(state["status"] if state["status"] != 200 else 401, json={"message": TOKEN})
        path = request.url.path
        if path == "/api/v1/fleet/global/policies":
            return httpx.Response(200, json={"policies": state["policies"]})
        if path == "/api/v1/fleet/hosts":
            page, per = int(request.url.params["page"]), int(request.url.params["per_page"])
            return httpx.Response(200, json={"hosts": state["hosts"][page * per:(page + 1) * per]})
        if path.endswith("/refetch"):
            return httpx.Response(200, json={})
        return httpx.Response(404)
    monkeypatch.setattr(fs, "_client", lambda **kw: REAL(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setenv("OMNI_SELF_HOSTED", BASE)  # no DNS lookup for the made-up address
    return mongo_db, calls, state


@pytest.mark.asyncio
async def test_settings_keep_the_token_secret_and_check_the_address(fleet):
    """protects=the token is stored encrypted and never returned, a first save needs it and a later one keeps it, and
    an address with a path, plain http to a LAN host, or a malformed token is refused; fails_when=the token is
    readable from the database or API, or http://10.0.0.8 is accepted unlisted; no_claim=that the token works"""
    db, _, _ = fleet
    for base, token in (("https://fleet.example.com/api", TOKEN), ("http://10.0.0.8:8080", TOKEN), (BASE, "short"), (BASE, None)):
        with pytest.raises(fs.FleetError):
            await fs.save_config(db, T, base, token, "admin@t")
    out = await fs.save_config(db, T, BASE + "/", TOKEN, "admin@t")
    assert out["connected"] and out["baseUrl"] == BASE and "secret" not in out
    before = (await db.mdm_connectors.find_one({"tenantId": T, "provider": "fleet"}))["secret"]
    assert TOKEN not in json.dumps(await db.mdm_connectors.find_one({"tenantId": T}), default=str)
    await fs.save_config(db, T, BASE, None, "admin@t")
    assert (await db.mdm_connectors.find_one({"tenantId": T, "provider": "fleet"}))["secret"] == before


@pytest.mark.asyncio
async def test_sync_reads_every_page_maps_platform_and_policies_and_marks_left_hosts(fleet, monkeypatch):
    """protects=a sync pages through Fleet's hosts, maps darwin to macos and Ubuntu to linux, a host failing policies is
    non_compliant and one failing none compliant, a host that left Fleet is marked fleetRemoved (kept), and with no
    policies in Fleet compliance is unknown; fails_when=only the first page is read, a host with no policies to fail
    is called compliant, or a removed host is deleted; no_claim=Fleet's policy content"""
    db, _, state = fleet
    monkeypatch.setattr(fs, "PER_PAGE", 1)
    await fs.save_config(db, T, BASE, TOKEN, "admin@t")
    assert await fs.sync(db, T, "admin@t") == {"devices": 2, "removed": 0}
    rows = {d["externalId"]: d async for d in db.mdm_devices.find({"tenantId": T, "source": "fleet"}, {"_id": 0})}
    assert (rows["1"]["platform"], rows["1"]["compliance_status"], rows["1"]["name"]) == ("linux", "compliant", "omniai-copy")
    assert (rows["2"]["platform"], rows["2"]["compliance_status"]) == ("macos", "non_compliant")
    assert rows["2"]["compliance_details"]["failingPolicies"] == 2 and rows["1"]["id"].startswith("mdm-")
    state["hosts"], state["policies"] = [_host(1, "omniai-copy")], []
    assert await fs.sync(db, T) == {"devices": 1, "removed": 1}
    rows = {d["externalId"]: d async for d in db.mdm_devices.find({"tenantId": T, "source": "fleet"}, {"_id": 0})}
    assert rows["2"]["fleetRemoved"] is True and rows["1"]["compliance_status"] == "unknown"
    assert (await fs.get_config(db, T))["devices"] == 1


@pytest.mark.asyncio
async def test_a_refused_sync_is_recorded_without_the_token_and_only_sync_is_sent(fleet):
    """protects=a 401 from Fleet is raised and kept as lastError naming the status, never the token; the device action
    "sync" posts Fleet's refetch and is logged on the device, and lock or wipe are refused before any call;
    fails_when=the token leaks into the error, or a lock is reported as sent; no_claim=Fleet Premium actions"""
    db, calls, state = fleet
    await fs.save_config(db, T, BASE, TOKEN, "admin@t")
    await fs.sync(db, T)
    device = await db.mdm_devices.find_one({"tenantId": T, "externalId": "1"}, {"_id": 0})
    sent = len(calls)
    with pytest.raises(fs.FleetError):
        await fs.action(db, T, device, "wipe", "admin@t")
    assert len(calls) == sent
    out = await fs.action(db, T, device, "sync", "admin@t")
    assert out["status"] == "sent" and calls[-1].url.path == "/api/v1/fleet/hosts/1/refetch" and calls[-1].method == "POST"
    log = (await db.mdm_devices.find_one({"id": device["id"]}))["action_log"]
    assert log[-1]["via"] == "fleet" and log[-1]["status"] == "sent"
    state["status"] = 401
    with pytest.raises(fs.FleetError) as err:
        await fs.sync(db, T)
    cfg = await fs.get_config(db, T)
    assert "HTTP 401" in str(err.value) and cfg["lastError"] == str(err.value) and TOKEN not in json.dumps(cfg, default=str)
