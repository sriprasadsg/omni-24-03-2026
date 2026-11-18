"""Intune connector (intune_service, Wave 5). protects/fails_when/no_claim per test; Graph and Entra are mocked,
MongoDB is real.
"""
import json
import os
import sys
from urllib.parse import parse_qs

import httpx
import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import intune_service as its
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

TID, CID, SECRET = "11111111-2222-3333-4444-555555555555", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "s3cr3t~value"
REAL = httpx.AsyncClient


def _dev(i, name, os_name="iOS", state="compliant"):
    return {"id": f"intune-{i}", "deviceName": name, "operatingSystem": os_name, "osVersion": "18.1", "complianceState": state,
            "managementState": "managed", "lastSyncDateTime": "2026-11-18T10:00:00Z", "userPrincipalName": "anna@contoso.example",
            "model": "iPhone 16", "manufacturer": "Apple", "serialNumber": f"SN{i}", "isEncrypted": True, "jailBroken": "False"}


@pytest_asyncio.fixture
async def graph(mongo_db, monkeypatch):  # noqa: F811
    its._tokens.clear()
    calls, pages = [], {"devices": [[_dev(1, "Anna iPhone"), _dev(2, "Ben Pixel", "Android", "noncompliant")], [_dev(3, "Kiosk")]],
                        "status": 200, "action": 204}

    def handler(request: httpx.Request):
        calls.append(request)
        url = str(request.url)
        if url.startswith("https://login.microsoftonline.com/"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        if "/managedDevices?" in url:
            if pages["status"] != 200:
                return httpx.Response(pages["status"], json={"error": {"message": SECRET}})
            first = "skiptoken" not in url
            body = {"value": pages["devices"][0 if first else 1]}
            if first and len(pages["devices"]) > 1:
                body["@odata.nextLink"] = pages.get("next", f"{its.GRAPH}/deviceManagement/managedDevices?$skiptoken=x")
            return httpx.Response(200, json=body)
        return httpx.Response(pages["action"])
    monkeypatch.setattr(its, "_client", lambda **kw: REAL(transport=httpx.MockTransport(handler), **kw))
    await its.save_config(mongo_db, "t-a", TID, CID, SECRET, "admin@a")
    return mongo_db, calls, pages


@pytest.mark.asyncio
async def test_config_keeps_the_secret_encrypted_and_never_returns_it(graph):
    """protects=the ids must be GUIDs, the secret is stored encrypted and never read back, another organization sees
    nothing; fails_when=the client secret is readable from the database or an API answer; no_claim=key rotation"""
    db, _, _ = graph
    stored = await db.mdm_connectors.find_one({"tenantId": "t-a"})
    assert SECRET not in json.dumps(stored, default=str) and stored["secret"]
    cfg = await its.get_config(db, "t-a")
    assert cfg["connected"] and cfg["clientId"] == CID and SECRET not in json.dumps(cfg) and "secret" not in cfg
    assert await its.get_config(db, "t-b") == {"connected": False}
    with pytest.raises(its.IntuneError, match="GUIDs"):
        await its.save_config(db, "t-a", "not-a-guid", CID, SECRET, "admin@a")
    await its.save_config(db, "t-a", TID, CID, None, "admin@a")  # keeps the stored secret
    assert (await db.mdm_connectors.find_one({"tenantId": "t-a"}))["secret"] == stored["secret"]


@pytest.mark.asyncio
async def test_sync_mirrors_every_page_and_marks_removed_devices_without_deleting(graph):
    """protects=client-credentials token, every Graph page read into mdm_devices with platform and compliance mapped,
    a second sync updates in place, a device gone from Intune is marked not deleted, rows stay in their tenant;
    fails_when=devices duplicate, vanish, or land in another organization; no_claim=Graph throttling"""
    db, calls, pages = graph
    assert await its.sync(db, "t-a") == {"devices": 3, "removed": 0}
    form = parse_qs(calls[0].content.decode())
    assert form["grant_type"] == ["client_credentials"] and form["client_secret"] == [SECRET] and TID in str(calls[0].url)
    ben = await db.mdm_devices.find_one({"externalId": "intune-2"})
    assert (ben["platform"], ben["compliance_status"], ben["tenantId"], ben["source"]) == ("android", "non_compliant", "t-a", "intune")
    pages["devices"] = [[_dev(1, "Anna iPhone"), _dev(2, "Ben Pixel")]]
    assert await its.sync(db, "t-a") == {"devices": 2, "removed": 1}
    assert await db.mdm_devices.count_documents({"tenantId": "t-a"}) == 3
    assert (await db.mdm_devices.find_one({"externalId": "intune-3"}))["intuneRemoved"] is True
    assert (await its.get_config(db, "t-a"))["devices"] == 2


@pytest.mark.asyncio
async def test_graph_refusals_say_what_to_grant_and_a_foreign_next_page_is_refused(graph):
    """protects=a 403 names the missing permissions and is stored as lastError (the provider body never is), a
    nextLink off graph.microsoft.com is not followed; fails_when=the token goes to another host; no_claim=-"""
    db, calls, pages = graph
    pages["status"] = 403
    with pytest.raises(its.IntuneError, match="DeviceManagementManagedDevices"):
        await its.sync(db, "t-a")
    cfg = await its.get_config(db, "t-a")
    assert "HTTP 403" in cfg["lastError"] and SECRET not in cfg["lastError"]
    pages["status"], pages["next"] = 200, "https://evil.example/steal"
    with pytest.raises(its.IntuneError, match="unexpected next page"):
        await its.sync(db, "t-a")
    assert not any("evil.example" in str(c.url) for c in calls)


@pytest.mark.asyncio
async def test_actions_are_sent_and_destructive_ones_need_the_device_name(graph):
    """protects=lock goes to Graph remoteLock and is logged as sent, wipe and retire need the device name typed and
    call nothing without it, a Graph failure is logged as failed and raised; fails_when=a phone is wiped by a stray
    click or an action is reported sent when it was not; no_claim=-"""
    db, calls, pages = graph
    await its.sync(db, "t-a")
    anna = await db.mdm_devices.find_one({"externalId": "intune-1"}, {"_id": 0})
    out = await its.action(db, "t-a", anna, "lock", "admin@a", None)
    assert out["status"] == "sent" and str(calls[-1].url).endswith("/managedDevices/intune-1/remoteLock")
    before = len(calls)
    with pytest.raises(its.IntuneError, match="Type the device name"):
        await its.action(db, "t-a", anna, "wipe", "admin@a", "anna iphone")
    assert len(calls) == before
    await its.action(db, "t-a", anna, "wipe", "admin@a", "Anna iPhone")
    assert str(calls[-1].url).endswith("/wipe")
    pages["action"] = 403
    with pytest.raises(its.IntuneError):
        await its.action(db, "t-a", anna, "sync", "admin@a", None)
    log = (await db.mdm_devices.find_one({"externalId": "intune-1"}))["action_log"]
    assert [(e["action"], e["status"]) for e in log] == [("lock", "sent"), ("wipe", "sent"), ("sync", "failed")]
