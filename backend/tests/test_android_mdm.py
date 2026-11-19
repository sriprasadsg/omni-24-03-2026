"""Android Enterprise connector (android_mdm_service, Android Management API). protects/fails_when/no_claim per test;
Google's API is mocked, MongoDB is real.
"""
import json
import os
import sys

import httpx
import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import android_mdm_service as ams
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

ENT = "enterprises/LC01abcdef"
PRIVATE = "-----BEGIN PRIVATE KEY-----\nMIIEsecretkeymaterial\n-----END PRIVATE KEY-----\n"
KEY = json.dumps({"type": "service_account", "project_id": "omni-mdm", "client_email": "mdm@omni-mdm.iam.gserviceaccount.com",
                  "private_key": PRIVATE, "private_key_id": "k1"})
REAL = httpx.AsyncClient


def _dev(i, compliant=True, state="ACTIVE"):
    return {"name": f"{ENT}/devices/d{i}", "state": state, "policyCompliant": compliant, "managementMode": "DEVICE_OWNER",
            "ownership": "COMPANY_OWNED", "lastStatusReportTime": "2026-11-19T10:00:00Z", "enrollmentTime": "2026-11-01T09:00:00Z",
            "hardwareInfo": {"brand": "Google", "model": "Pixel 9", "serialNumber": f"SERIAL00{i}", "manufacturer": "Google"},
            "softwareInfo": {"androidVersion": "15", "securityPatchLevel": "2026-11-05"},
            "nonComplianceDetails": [] if compliant else [{"settingName": "passwordPolicies"}]}


@pytest_asyncio.fixture
async def google(mongo_db, monkeypatch):  # noqa: F811
    ams._tokens.clear()
    calls, state = [], {"pages": [[_dev(1), _dev(2, compliant=False)], [_dev(3)]], "status": 200}

    def handler(request: httpx.Request):
        calls.append(request)
        path, url = request.url.path, str(request.url)
        if state["status"] != 200 and request.method == "GET":
            return httpx.Response(state["status"], json={"error": {"message": "denied for mdm@omni-mdm"}})
        if path.endswith("/signupUrls"):
            return httpx.Response(200, json={"name": "signupUrls/C1", "url": "https://play.google.com/work/adminsignup?token=x"})
        if path == "/v1/enterprises" and request.method == "POST":
            return httpx.Response(200, json={"name": ENT, "enterpriseDisplayName": "Contoso"})
        if "/policies/" in path:
            return httpx.Response(200, json={"name": f"{ENT}/policies/omni-default"})
        if path.endswith("/enrollmentTokens"):
            return httpx.Response(200, json={"name": f"{ENT}/enrollmentTokens/t1", "value": "ABCDEFGHIJ",
                                             "qrCode": '{"android.app.extra.PROVISIONING_ADMIN_EXTRAS_BUNDLE":{}}',
                                             "expirationTimestamp": "2026-11-20T12:00:00Z"})
        if path.endswith("/devices") and request.method == "GET":
            second = "pageToken" in url
            body = {"devices": state["pages"][1 if second else 0]}
            if not second and len(state["pages"]) > 1:
                body["nextPageToken"] = "p2"
            return httpx.Response(200, json=body)
        if request.method == "GET" and "/devices/" in path:
            return httpx.Response(200, json=_dev(int(path[-1])))
        return httpx.Response(state.get("action", 200), json={})
    monkeypatch.setattr(ams, "_client", lambda **kw: REAL(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(ams, "_google_token", lambda info: "tok-" + info["project_id"])
    return mongo_db, calls, state


@pytest.mark.asyncio
async def test_the_key_is_encrypted_never_returned_and_must_be_a_service_account(google):
    """protects=the private key is stored encrypted and never in an answer, the enterprise name is checked, another
    organization sees nothing, a later save without the key keeps it; fails_when=the key is readable from the database
    or the API; no_claim=key rotation at Google"""
    db, calls, _ = google
    cfg = await ams.save_config(db, "t-a", KEY, None, "admin@a")
    stored = await db.mdm_connectors.find_one({"tenantId": "t-a", "provider": "android"})
    assert "MIIEsecret" not in json.dumps(stored, default=str) and stored["secret"]
    assert cfg["connected"] and cfg["projectId"] == "omni-mdm" and "MIIEsecret" not in json.dumps(cfg) and "secret" not in cfg
    assert calls == []  # no enterprise yet, so no policy call
    assert await ams.get_config(db, "t-b") == {"connected": False}
    with pytest.raises(ams.AndroidError, match="not a service account"):
        await ams.save_config(db, "t-a", json.dumps({"type": "authorized_user"}), None, "admin@a")
    with pytest.raises(ams.AndroidError, match="enterprises/LC01"):
        await ams.save_config(db, "t-a", None, "enterprises/../x", "admin@a")
    await ams.save_config(db, "t-a", None, ENT, "admin@a")
    assert (await db.mdm_connectors.find_one({"tenantId": "t-a"}))["secret"] == stored["secret"]
    assert calls[-1].method == "PATCH" and calls[-1].url.path == f"/v1/{ENT}/policies/omni-default"
    assert calls[-1].headers["authorization"] == "Bearer tok-omni-mdm"


@pytest.mark.asyncio
async def test_signup_creates_the_enterprise_and_its_policy(google):
    """protects=the sign-up link carries the project and an https return address, the returned token creates the
    enterprise and the omni-default policy; fails_when=an http return address is accepted or the enterprise is not
    stored; no_claim=Google's own sign-up pages"""
    db, calls, _ = google
    await ams.save_config(db, "t-a", KEY, None, "admin@a")
    with pytest.raises(ams.AndroidError, match="https"):
        await ams.signup_url(db, "t-a", "http://evil.example/cb", "admin@a")
    out = await ams.signup_url(db, "t-a", "https://omni.example/mobile", "admin@a")
    assert out["url"].startswith("https://play.google.com/") and calls[-1].url.params["projectId"] == "omni-mdm"
    cfg = await ams.complete_signup(db, "t-a", "EnterpriseToken_0123", "Contoso", "admin@a")
    assert cfg["enterprise"] == ENT and cfg["enterpriseName"] == "Contoso" and not cfg["signupPending"]
    create = [c for c in calls if c.url.path == "/v1/enterprises"][0]
    assert create.url.params["signupUrlName"] == "signupUrls/C1" and create.url.params["enterpriseToken"] == "EnterpriseToken_0123"


@pytest.mark.asyncio
async def test_enrollment_token_is_a_qr_code_and_a_work_profile_link(google):
    """protects=an enrollment token uses the omni-default policy for 24 hours and comes back as a PNG QR code and an
    enroll link; fails_when=a token is created without a policy or without an enterprise; no_claim=device provisioning"""
    db, calls, _ = google
    await ams.save_config(db, "t-a", KEY, None, "admin@a")
    with pytest.raises(ams.AndroidError, match="Name the Android Enterprise"):
        await ams.enrollment_token(db, "t-a", "admin@a")
    await ams.save_config(db, "t-a", None, ENT, "admin@a")
    out = await ams.enrollment_token(db, "t-a", "admin@a")
    assert out["link"] == "https://enterprise.google.com/android/enroll?et=ABCDEFGHIJ" and out["hours"] == 24
    assert out["qrPng"] and out["qrPng"].startswith("iVBOR")  # base64 of a PNG header
    body = json.loads(calls[-1].content)
    assert body == {"policyName": f"{ENT}/policies/omni-default", "duration": "86400s"}


@pytest.mark.asyncio
async def test_sync_reads_every_page_and_marks_removed_devices_without_deleting(google):
    """protects=every page is read into mdm_devices with compliance mapped, a device gone is marked not deleted, rows
    stay in their tenant; fails_when=devices duplicate, vanish, or land in another organization; no_claim=quotas"""
    db, _, state = google
    await ams.save_config(db, "t-a", KEY, ENT, "admin@a")
    assert await ams.sync(db, "t-a") == {"devices": 3, "removed": 0}
    two = await db.mdm_devices.find_one({"externalId": f"{ENT}/devices/d2"})
    assert (two["platform"], two["compliance_status"], two["tenantId"], two["source"], two["name"]) == \
        ("android", "non_compliant", "t-a", "android", "Google Pixel 9 (IAL002)")
    assert two["compliance_details"]["nonCompliance"] == ["passwordPolicies"]
    state["pages"] = [[_dev(1), _dev(2)]]
    assert await ams.sync(db, "t-a") == {"devices": 2, "removed": 1}
    assert await db.mdm_devices.count_documents({"tenantId": "t-a"}) == 3
    assert (await db.mdm_devices.find_one({"externalId": f"{ENT}/devices/d3"}))["androidRemoved"] is True
    state["status"] = 403
    with pytest.raises(ams.AndroidError, match="Android Management User"):
        await ams.sync(db, "t-a")
    assert "HTTP 403" in (await ams.get_config(db, "t-a"))["lastError"]


@pytest.mark.asyncio
async def test_actions_are_sent_and_destructive_ones_need_the_device_name(google):
    """protects=lock and restart are issueCommand LOCK and REBOOT, wipe deletes the device with external storage and
    needs the name typed (nothing is called without it), a refusal is logged as failed; fails_when=a phone is wiped by a
    stray click or an action is reported sent when it was not; no_claim=-"""
    db, calls, state = google
    await ams.save_config(db, "t-a", KEY, ENT, "admin@a")
    await ams.sync(db, "t-a")
    dev = await db.mdm_devices.find_one({"externalId": f"{ENT}/devices/d1"}, {"_id": 0})
    await ams.action(db, "t-a", dev, "lock", "admin@a", None)
    assert calls[-1].url.path == f"/v1/{ENT}/devices/d1:issueCommand" and json.loads(calls[-1].content) == {"type": "LOCK"}
    await ams.action(db, "t-a", dev, "restart", "admin@a", None)
    assert json.loads(calls[-1].content) == {"type": "REBOOT"}
    before = len(calls)
    with pytest.raises(ams.AndroidError, match="Type the device name"):
        await ams.action(db, "t-a", dev, "wipe", "admin@a", "pixel")
    assert len(calls) == before
    await ams.action(db, "t-a", dev, "wipe", "admin@a", dev["name"])
    assert calls[-1].method == "DELETE" and calls[-1].url.params["wipeDataFlags"] == "WIPE_EXTERNAL_STORAGE"
    state["action"] = 403
    with pytest.raises(ams.AndroidError):
        await ams.action(db, "t-a", dev, "lock", "admin@a", None)
    log = (await db.mdm_devices.find_one({"externalId": f"{ENT}/devices/d1"}))["action_log"]
    assert [(e["action"], e["status"]) for e in log] == [("lock", "sent"), ("restart", "sent"), ("wipe", "sent"), ("lock", "failed")]
    foreign = {**dev, "externalId": "enterprises/LC99other/devices/x"}
    with pytest.raises(ams.AndroidError, match="not in the connected enterprise"):
        await ams.action(db, "t-a", foreign, "lock", "admin@a", None)
