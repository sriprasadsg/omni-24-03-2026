"""Jamf Pro connector (jamf_service; Apple devices without Intune). protects/fails_when/no_claim per test;
Jamf Pro's API is mocked at the HTTP layer, MongoDB is real.
"""
import json
import os
import sys

import httpx
import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import jamf_service as js
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

T = "t-jamf"
BASE = "https://acme.jamfcloud.com"
CLIENT = "0f6c3a52-8d1e-4b7a-9c2d-5e4f3a2b1c0d"
SECRET = "Jx7-qL2vR9sT4wY6zA8bC1dE3fG5hK0mN"
TOKEN = "jamf-bearer-token"
REAL = httpx.AsyncClient


def _computer(i, name, filevault="ALL_ENCRYPTED", mid=None):
    return {"id": str(i), "udid": f"UDID-{i}",
            "general": {"name": name, "lastContact": "2026-11-19T09:00:00Z", "lastEnrolledDate": "2026-11-01T08:00:00Z",
                        "remoteManagement": {"managed": True}, "supervised": True, "managementId": mid or f"mid-c{i}"},
            "hardware": {"model": "MacBook Pro (14-inch, 2023)", "serialNumber": f"C02X{i}", "macAddress": "a4:83:e7:00:00:0" + str(i)},
            "operatingSystem": {"name": "macOS", "version": "15.6", "fileVault2Status": filevault},
            "userAndLocation": {"username": "sri", "email": "sri@acme.example"}}


def _mobile(i, name, jailbroken=False, managed=True):
    return {"mobileDeviceId": str(i), "deviceType": "iOS",
            "general": {"displayName": name, "osVersion": "18.6", "managed": managed, "supervised": True,
                        "managementId": f"mid-m{i}", "lastInventoryUpdateDate": "2026-11-19T07:00:00Z",
                        "lastEnrolledDate": "2026-10-01T07:00:00Z"},
            "hardware": {"serialNumber": f"DMQ{i}", "model": "iPhone 16"},
            "userAndLocation": {"username": "anu", "emailAddress": "anu@acme.example"},
            "security": {"dataProtected": True, "jailBreakDetected": jailbroken}}


@pytest_asyncio.fixture
async def jamf(mongo_db, monkeypatch):  # noqa: F811
    calls, state = [], {"computers": [_computer(1, "mac-01"), _computer(2, "mac-02", "NOT_ENCRYPTED")],
                        "mobiles": [_mobile(1, "iphone-01"), _mobile(2, "ipad-02", jailbroken=True)],
                        "v4": False, "status": 200, "push_errors": []}

    def page(items, request):
        p, size = int(request.url.params["page"]), int(request.url.params["page-size"])
        return httpx.Response(200, json={"totalCount": len(items), "results": items[p * size:(p + 1) * size]})

    def handler(request: httpx.Request):
        calls.append(request)
        path = request.url.path
        if path == "/api/oauth/token":
            form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
            if form.get("client_id") != CLIENT or form.get("client_secret") != SECRET or form.get("grant_type") != "client_credentials":
                return httpx.Response(401, json={"error": "invalid_client"})
            return httpx.Response(200, json={"access_token": TOKEN, "token_type": "Bearer", "expires_in": 60})
        if request.headers.get("authorization") != f"Bearer {TOKEN}" or state["status"] != 200:
            return httpx.Response(state["status"] if state["status"] != 200 else 401, json={"secret": SECRET})
        if path == "/api/v4/computers-inventory" and not state["v4"]:
            return httpx.Response(404)
        if path in ("/api/v4/computers-inventory", "/api/v3/computers-inventory"):
            assert request.url.params.get_list("section") == list(js.COMPUTER_SECTIONS)
            return page(state["computers"], request)
        if path == "/api/v2/mobile-devices/detail":
            assert request.url.params["exception-handling"] == "LENIENT"
            return page(state["mobiles"], request)
        if path == "/api/v2/mdm/blank-push":
            return httpx.Response(200, json={"errorUuids": state["push_errors"]})
        if path == "/api/v2/mdm/commands":
            return httpx.Response(201, json=[{"id": "1", "href": f"{BASE}/api/v2/mdm/commands/1"}])
        return httpx.Response(404)
    monkeypatch.setattr(js, "_client", lambda **kw: REAL(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setenv("OMNI_SELF_HOSTED", BASE)  # no DNS lookup for the made-up address
    js._tokens.clear()
    return mongo_db, calls, state


async def _devices(db):
    return {d["externalId"]: d async for d in db.mdm_devices.find({"tenantId": T, "source": "jamf"}, {"_id": 0})}


@pytest.mark.asyncio
async def test_settings_keep_the_secret_and_check_the_address_and_client_id(jamf):
    """protects=the client secret is stored encrypted and never returned, a first save needs it and a later one keeps
    it, and an address with a path, plain http to a LAN host, a client ID that is not a GUID or a short secret is
    refused; fails_when=the secret is readable from the database or API, or http://10.0.0.8 is accepted unlisted;
    no_claim=that the API client's role has the right privileges"""
    db, _, _ = jamf
    for base, cid, secret in ((BASE + "/JSSResource", CLIENT, SECRET), ("http://10.0.0.8:8443", CLIENT, SECRET),
                              (BASE, "my-client", SECRET), (BASE, CLIENT, "short"), (BASE, CLIENT, None)):
        with pytest.raises(js.JamfError):
            await js.save_config(db, T, base, cid, secret, "admin@t")
    out = await js.save_config(db, T, BASE + "/", CLIENT.upper(), SECRET, "admin@t")
    assert out["connected"] and out["baseUrl"] == BASE and out["clientId"] == CLIENT and "secret" not in out
    before = (await db.mdm_connectors.find_one({"tenantId": T, "provider": "jamf"}))["secret"]
    assert SECRET not in json.dumps(await db.mdm_connectors.find_one({"tenantId": T}), default=str)
    await js.save_config(db, T, BASE, CLIENT, None, "admin@t")
    assert (await db.mdm_connectors.find_one({"tenantId": T, "provider": "jamf"}))["secret"] == before


@pytest.mark.asyncio
async def test_sync_reads_macs_and_mobiles_on_every_page_and_marks_left_devices(jamf, monkeypatch):
    """protects=a sync falls back from v4 to v3 computer inventory, pages through computers and mobile devices, maps
    Macs to macos and iPhones to ios, keeps FileVault as encrypted, calls a jailbroken device non_compliant and every
    other device unknown (Jamf gives no compliance verdict), and marks a device that left Jamf jamfRemoved (kept);
    fails_when=only the first page is read, a 404 on v4 fails the sync, a device is called compliant, or a removed
    device is deleted; no_claim=Jamf's smart-group compliance"""
    db, calls, state = jamf
    monkeypatch.setattr(js, "PER_PAGE", 1)
    await js.save_config(db, T, BASE, CLIENT, SECRET, "admin@t")
    assert await js.sync(db, T, "admin@t") == {"devices": 4, "removed": 0}
    assert any(c.url.path == "/api/v4/computers-inventory" for c in calls)
    rows = await _devices(db)
    mac, mac2, phone, ipad = rows["computer-1"], rows["computer-2"], rows["mobile-1"], rows["mobile-2"]
    assert (mac["platform"], mac["name"], mac["jamfManagementId"], mac["last_seen"]) == ("macos", "mac-01", "mid-c1", "2026-11-19T09:00:00Z")
    assert mac["compliance_details"]["encrypted"] is True and mac2["compliance_details"]["encrypted"] is False
    assert (phone["platform"], phone["assigned_user"], phone["enrollment_status"]) == ("ios", "anu@acme.example", "enrolled")
    assert {d["compliance_status"] for d in (mac, mac2, phone)} == {"unknown"} and ipad["compliance_status"] == "non_compliant"
    assert mac["id"].startswith("mdm-") and mac["manufacturer"] == "Apple"
    state["computers"], state["mobiles"], state["v4"] = [_computer(1, "mac-01")], [_mobile(1, "iphone-01")], True
    assert await js.sync(db, T) == {"devices": 2, "removed": 2}
    rows = await _devices(db)
    assert rows["computer-2"]["jamfRemoved"] is True and rows["mobile-2"]["jamfRemoved"] is True
    assert (await js.get_config(db, T))["devices"] == 2


@pytest.mark.asyncio
async def test_actions_need_the_name_and_a_mac_pin_and_the_pin_is_never_stored(jamf):
    """protects=wipe without the typed name, a Mac lock or wipe without a 6-digit PIN, and retire are refused before
    any call; a Mac lock sends DEVICE_LOCK with the PIN to the device's management ID, an iPhone wipe sends
    ERASE_DEVICE with no PIN, sync sends a blank push, and none of the PIN lands on the device or in the ledger;
    fails_when=a wipe goes out unconfirmed, the PIN is stored, or a blank push Jamf could not deliver is reported as
    sent; no_claim=that the device carries the command out"""
    db, calls, state = jamf
    await js.save_config(db, T, BASE, CLIENT, SECRET, "admin@t")
    await js.sync(db, T)
    rows = await _devices(db)
    mac, phone = rows["computer-1"], rows["mobile-1"]
    sent = len(calls)
    for device, name, confirm, pin in ((phone, "wipe", "wrong", None), (mac, "lock", None, None), (mac, "lock", None, "12a456"),
                                       (mac, "wipe", "mac-01", None), (phone, "retire", "iphone-01", None)):
        with pytest.raises(js.JamfError):
            await js.action(db, T, device, name, "admin@t", confirm, pin)
    assert len(calls) == sent
    assert (await js.action(db, T, mac, "lock", "admin@t", None, "482916"))["status"] == "sent"
    body = json.loads(calls[-1].content)
    assert body == {"clientData": [{"managementId": "mid-c1"}], "commandData": {"commandType": "DEVICE_LOCK", "pin": "482916"}}
    await js.action(db, T, phone, "wipe", "admin@t", "iphone-01")
    assert json.loads(calls[-1].content)["commandData"] == {"commandType": "ERASE_DEVICE"}
    await js.action(db, T, phone, "sync", "admin@t", None)
    assert calls[-1].url.path == "/api/v2/mdm/blank-push" and json.loads(calls[-1].content) == {"clientManagementIds": ["mid-m1"]}
    state["push_errors"] = ["mid-m1"]
    with pytest.raises(js.JamfError):
        await js.action(db, T, phone, "sync", "admin@t", None)
    log = (await db.mdm_devices.find_one({"id": phone["id"]}))["action_log"]
    assert [e["status"] for e in log] == ["sent", "sent", "failed"] and log[0]["via"] == "jamf"
    assert "482916" not in json.dumps(await db.mdm_devices.find_one({"id": mac["id"]}, {"_id": 0}), default=str)
    ledger = await db.audit_logs.find({"tenantId": T}, {"_id": 0}).to_list(200)
    assert any(e.get("action") == "mdm.jamf.lock" for e in ledger)
    assert "482916" not in json.dumps(ledger, default=str)


@pytest.mark.asyncio
async def test_a_refused_sync_is_recorded_without_the_secret(jamf):
    """protects=a 403 from Jamf is raised and kept as lastError naming the status and the privileges, never the secret,
    and a wrong secret fails at the token step; fails_when=the secret leaks into the error or a failed sync clears
    lastError; no_claim=which privilege is missing"""
    db, _, state = jamf
    await js.save_config(db, T, BASE, CLIENT, SECRET, "admin@t")
    state["status"] = 403
    with pytest.raises(js.JamfError) as err:
        await js.sync(db, T)
    cfg = await js.get_config(db, T)
    assert "HTTP 403" in str(err.value) and "Read Computers" in str(err.value) and cfg["lastError"] == str(err.value)
    assert SECRET not in json.dumps(cfg, default=str)
    js._tokens.clear()
    await js.save_config(db, T, BASE, CLIENT, "Wrong-secret-0123456789", "admin@t")
    with pytest.raises(js.JamfError) as err:
        await js.sync(db, T)
    assert "refused the API client (HTTP 401)" in str(err.value)
