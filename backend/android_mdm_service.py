"""Android Enterprise connector for Mobile Device Management (Google's Android Management API).

An organization connects with a Google Cloud service account that has the Android Management User role on a project
with the Android Management API enabled. The key is encrypted at rest (encryption_service) and never returned. The
organization's Android Enterprise is either named directly (``enterprises/LC...``) or created through Google's sign-up
link: the link returns to the Mobile screen with an enterprise token, which completes it here.

Omni-Agent keeps one policy per enterprise (``omni-default``: status reports on, nothing locked down) so enrollment
tokens have a policy to apply. An enrollment token comes back as a QR code (fully managed devices: tap the welcome
screen six times) and as a link (work profile on a personal phone). A sync reads the enterprise's devices into
``mdm_devices`` (source "android", keyed by the device resource name); a device that left is marked
``androidRemoved``, never deleted. Remote actions are sent to Google for real: lock and restart as commands, retire
and wipe by deleting the device (wipe also erases external storage), the destructive two only with the device's name
typed as confirmation; each is recorded on the device and in the audit ledger.
"""
import asyncio
import base64
import io
import json
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

import audit_ledger

AMAPI = "https://androidmanagement.googleapis.com/v1"
SCOPE = "https://www.googleapis.com/auth/androidmanagement"
ENTERPRISE = re.compile(r"^enterprises/[A-Za-z0-9_-]{2,64}$")
POLICY_ID = "omni-default"
ENROLL_LINK = "https://enterprise.google.com/android/enroll?et={}"
ACTIONS = ("sync", "lock", "restart", "retire", "wipe")
DESTRUCTIVE = ("retire", "wipe")
MAX_PAGES = 100
TIMEOUT = 30.0
TOKEN_HOURS = 24
_tokens: Dict[str, Tuple[str, float]] = {}


class AndroidError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _raw(db):
    return getattr(db, "_db", db)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _client(**kw) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT, **kw)


async def _audit(db, action: str, tenant: str, who: str, **fields: Any) -> None:
    await audit_ledger.event(action, tenant, actor={"email": who, "tenantId": tenant}, db=_raw(db), resourceType="mdm", **fields)


def _key_info(text: str) -> Dict[str, Any]:
    try:
        info = json.loads(text)
    except (TypeError, ValueError):
        raise AndroidError("The service account key must be the JSON file Google Cloud downloads")
    if not isinstance(info, dict) or info.get("type") != "service_account" or not all(
            isinstance(info.get(k), str) and info.get(k) for k in ("client_email", "private_key", "project_id")):
        raise AndroidError("That JSON is not a service account key (it needs type, client_email, private_key, project_id)")
    return info


async def _cfg(db, tenant: str) -> Dict[str, Any]:
    cfg = await _raw(db).mdm_connectors.find_one({"tenantId": tenant, "provider": "android"})
    if not cfg:
        raise AndroidError("Android Enterprise is not connected", 404)
    return cfg


async def save_config(db, tenant: str, key_json: Optional[str], enterprise: Optional[str], who: str) -> Dict[str, Any]:
    from encryption_service import get_encryption_service
    raw = _raw(db)
    existing = await raw.mdm_connectors.find_one({"tenantId": tenant, "provider": "android"}, {"_id": 0})
    doc: Dict[str, Any] = {"tenantId": tenant, "provider": "android", "updatedBy": who, "updatedAt": _now()}
    if key_json and key_json.strip():
        info = _key_info(key_json.strip())
        doc.update(secret=get_encryption_service().encrypt(json.dumps(info)), projectId=info["project_id"],
                   serviceAccount=info["client_email"])
    elif not existing:
        raise AndroidError("The service account key is required")
    if enterprise:
        enterprise = enterprise.strip()
        if not ENTERPRISE.match(enterprise):
            raise AndroidError("The enterprise is named like enterprises/LC01abcdef (from the Android Management API)")
        doc["enterprise"] = enterprise
    await raw.mdm_connectors.update_one({"tenantId": tenant, "provider": "android"}, {"$set": doc}, upsert=True)
    _tokens.pop(tenant, None)
    await _audit(db, "mdm.android.connect", tenant, who, projectId=doc.get("projectId"), enterprise=doc.get("enterprise"))
    if doc.get("enterprise"):
        await ensure_policy(db, tenant)
    return await get_config(db, tenant)


async def get_config(db, tenant: str) -> Dict[str, Any]:
    raw = _raw(db)
    cfg = await raw.mdm_connectors.find_one({"tenantId": tenant, "provider": "android"}, {"_id": 0, "secret": 0})
    if not cfg:
        return {"connected": False}
    devices = await raw.mdm_devices.count_documents({"tenantId": tenant, "source": "android", "androidRemoved": {"$ne": True}})
    return {"connected": True, **{k: cfg.get(k) for k in ("projectId", "serviceAccount", "enterprise", "enterpriseName",
                                                           "updatedBy", "updatedAt", "lastSyncAt", "lastSyncCount",
                                                           "lastError", "signupPending")}, "devices": devices}


async def disconnect(db, tenant: str, who: str) -> None:
    raw = _raw(db)
    if (await raw.mdm_connectors.delete_one({"tenantId": tenant, "provider": "android"})).deleted_count == 0:
        raise AndroidError("Android Enterprise is not connected", 404)
    await raw.mdm_devices.update_many({"tenantId": tenant, "source": "android"}, {"$set": {"androidDisconnected": True}})
    _tokens.pop(tenant, None)
    await _audit(db, "mdm.android.disconnect", tenant, who)


def _google_token(info: Dict[str, Any]) -> str:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    try:
        creds = service_account.Credentials.from_service_account_info(info, scopes=[SCOPE])
        creds.refresh(Request())
    except Exception as exc:  # google-auth raises several types; never echo the key
        raise AndroidError(f"Google refused the service account ({type(exc).__name__}); check the key and that the "
                           "Android Management API is enabled", 502)
    return creds.token


async def _token(db, tenant: str) -> str:
    from encryption_service import get_encryption_service
    cached = _tokens.get(tenant)
    if cached and cached[1] > time.time() + 60:
        return cached[0]
    cfg = await _cfg(db, tenant)
    token = await asyncio.to_thread(_google_token, json.loads(get_encryption_service().decrypt(cfg["secret"])))
    _tokens[tenant] = (token, time.time() + 3000)
    return token


def _api_error(r: httpx.Response, what: str) -> AndroidError:
    try:
        message = (r.json().get("error") or {}).get("message") or ""
    except ValueError:
        message = ""
    if r.status_code in (401, 403):
        return AndroidError(f"Google refused {what} (HTTP {r.status_code}): give the service account the Android "
                            "Management User role and enable the API", 502)
    return AndroidError(f"Google refused {what} (HTTP {r.status_code}){': ' + message[:200] if message else ''}", 502)


async def _call(db, tenant: str, method: str, path: str, what: str, **kw) -> Dict[str, Any]:
    token = await _token(db, tenant)
    async with _client(headers={"Authorization": f"Bearer {token}"}) as c:
        r = await c.request(method, f"{AMAPI}/{path}", **kw)
    if r.status_code not in (200, 204):
        raise _api_error(r, what)
    return r.json() if r.content else {}


# ── enterprise sign-up ──────────────────────────────────────────────────────────

async def signup_url(db, tenant: str, callback_url: str, who: str) -> Dict[str, Any]:
    """A Google sign-up link that creates this organization's Android Enterprise and returns to callback_url."""
    if not re.match(r"^https://[^\s]{4,500}$", callback_url or ""):
        raise AndroidError("The return address must be an https address of this platform")
    cfg = await _cfg(db, tenant)
    out = await _call(db, tenant, "POST", "signupUrls", "the sign-up link",
                      params={"projectId": cfg["projectId"], "callbackUrl": callback_url})
    await _raw(db).mdm_connectors.update_one({"tenantId": tenant, "provider": "android"},
                                             {"$set": {"signupUrlName": out.get("name"), "signupPending": True}})
    await _audit(db, "mdm.android.signup_started", tenant, who)
    return {"url": out.get("url")}


async def complete_signup(db, tenant: str, enterprise_token: str, display_name: str, who: str) -> Dict[str, Any]:
    cfg = await _cfg(db, tenant)
    if not cfg.get("signupUrlName"):
        raise AndroidError("Start the sign-up from this screen first")
    if not re.match(r"^[A-Za-z0-9_-]{8,400}$", enterprise_token or ""):
        raise AndroidError("That enterprise token is not one Google returns")
    out = await _call(db, tenant, "POST", "enterprises", "the new enterprise",
                      params={"projectId": cfg["projectId"], "signupUrlName": cfg["signupUrlName"],
                              "enterpriseToken": enterprise_token},
                      json={"enterpriseDisplayName": (display_name or "Omni-Agent")[:100]})
    name = out.get("name") or ""
    if not ENTERPRISE.match(name):
        raise AndroidError("Google did not return an enterprise name", 502)
    await _raw(db).mdm_connectors.update_one({"tenantId": tenant, "provider": "android"},
                                             {"$set": {"enterprise": name, "enterpriseName": out.get("enterpriseDisplayName"),
                                                       "signupPending": False}, "$unset": {"signupUrlName": ""}})
    await _audit(db, "mdm.android.enterprise_created", tenant, who, enterprise=name)
    await ensure_policy(db, tenant)
    return await get_config(db, tenant)


async def _enterprise(db, tenant: str) -> str:
    cfg = await _cfg(db, tenant)
    if not cfg.get("enterprise"):
        raise AndroidError("Name the Android Enterprise or create one with the sign-up link first", 409)
    return cfg["enterprise"]


async def ensure_policy(db, tenant: str) -> str:
    """The enterprise's omni-default policy (status reports on); created or updated in place."""
    enterprise = await _enterprise(db, tenant)
    name = f"{enterprise}/policies/{POLICY_ID}"
    await _call(db, tenant, "PATCH", name, "the omni-default policy", json={"statusReportingSettings": {
        "applicationReportsEnabled": True, "deviceSettingsEnabled": True, "softwareInfoEnabled": True,
        "hardwareStatusEnabled": True, "memoryInfoEnabled": True, "networkInfoEnabled": True,
        "powerManagementEventsEnabled": True}})
    return name


def _qr_png(text: str) -> Optional[str]:
    try:
        import qrcode
        img = qrcode.make(text)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


async def enrollment_token(db, tenant: str, who: str) -> Dict[str, Any]:
    """A 24-hour enrollment token: a QR code for fully managed devices and a link for a work profile."""
    enterprise = await _enterprise(db, tenant)
    policy = await ensure_policy(db, tenant)
    out = await _call(db, tenant, "POST", f"{enterprise}/enrollmentTokens", "the enrollment token",
                      json={"policyName": policy, "duration": f"{TOKEN_HOURS * 3600}s"})
    value = out.get("value") or ""
    await _audit(db, "mdm.android.enrollment_token", tenant, who)
    return {"value": value, "expires": out.get("expirationTimestamp"), "link": ENROLL_LINK.format(value),
            "qrPng": _qr_png(out.get("qrCode") or ""), "hours": TOKEN_HOURS}


# ── devices ────────────────────────────────────────────────────────────────────

def _label(d: Dict[str, Any]) -> str:
    hw = d.get("hardwareInfo") or {}
    base = " ".join(x for x in (hw.get("brand"), hw.get("model")) if x) or "Android device"
    serial = hw.get("serialNumber") or d.get("name", "").rsplit("/", 1)[-1]
    return f"{base} ({serial[-6:]})" if serial else base


def _row(tenant: str, d: Dict[str, Any], now: str) -> Dict[str, Any]:
    hw, sw = d.get("hardwareInfo") or {}, d.get("softwareInfo") or {}
    state = str(d.get("state") or "").upper()
    return {"tenantId": tenant, "source": "android", "externalId": d["name"], "name": _label(d), "platform": "android",
            "os_version": sw.get("androidVersion"), "model": hw.get("model"), "manufacturer": hw.get("manufacturer") or hw.get("brand"),
            "serial_number": hw.get("serialNumber"), "assigned_user": d.get("userName"),
            "enrollment_status": "enrolled" if state == "ACTIVE" else state.lower() or "unknown",
            "compliance_status": "compliant" if d.get("policyCompliant") is True else
                                 "non_compliant" if d.get("policyCompliant") is False else "unknown",
            "last_seen": d.get("lastStatusReportTime"), "enrolled_at": d.get("enrollmentTime"),
            "compliance_details": {"managementMode": d.get("managementMode"), "ownership": d.get("ownership"),
                                   "securityPatchLevel": sw.get("securityPatchLevel"),
                                   "nonCompliance": [n.get("settingName") for n in d.get("nonComplianceDetails") or []][:20]},
            "androidRemoved": False, "androidDisconnected": False, "syncedAt": now, "updated_at": now}


async def sync(db, tenant: str, who: str = "system") -> Dict[str, Any]:
    """Read every device of the enterprise into mdm_devices; returns {devices, removed}."""
    raw, now = _raw(db), _now()
    try:
        enterprise = await _enterprise(db, tenant)
        seen: List[str] = []
        params: Dict[str, Any] = {"pageSize": 100}
        for _ in range(MAX_PAGES):
            body = await _call(db, tenant, "GET", f"{enterprise}/devices", "the device list", params=params)
            for d in body.get("devices") or []:
                if not str(d.get("name") or "").startswith(f"{enterprise}/devices/"):
                    continue
                seen.append(d["name"])
                await raw.mdm_devices.update_one({"tenantId": tenant, "source": "android", "externalId": d["name"]},
                                                 {"$set": _row(tenant, d, now), "$setOnInsert": {"id": f"mdm-{uuid.uuid4().hex[:12]}"}},
                                                 upsert=True)
            if not body.get("nextPageToken"):
                break
            params = {"pageSize": 100, "pageToken": body["nextPageToken"]}
    except AndroidError as e:
        await raw.mdm_connectors.update_one({"tenantId": tenant, "provider": "android"}, {"$set": {"lastError": str(e), "lastErrorAt": now}})
        raise
    removed = (await raw.mdm_devices.update_many({"tenantId": tenant, "source": "android", "externalId": {"$nin": seen}},
                                                 {"$set": {"androidRemoved": True, "updated_at": now}})).modified_count
    await raw.mdm_connectors.update_one({"tenantId": tenant, "provider": "android"},
                                        {"$set": {"lastSyncAt": now, "lastSyncCount": len(seen), "lastError": None}})
    await _audit(db, "mdm.android.sync", tenant, who, devices=len(seen), removed=removed)
    return {"devices": len(seen), "removed": removed}


async def action(db, tenant: str, device: Dict[str, Any], name: str, who: str, confirm: Optional[str]) -> Dict[str, Any]:
    """Send one remote action on an Android device to Google; recorded on the device as sent or failed."""
    if name not in ACTIONS:
        raise AndroidError(f"Android devices take {', '.join(ACTIONS)}")
    if name in DESTRUCTIVE and (confirm or "").strip() != (device.get("name") or ""):
        raise AndroidError(f"Type the device name to confirm {name}")
    enterprise = await _enterprise(db, tenant)
    resource = device["externalId"]
    if not resource.startswith(f"{enterprise}/devices/"):
        raise AndroidError("This device is not in the connected enterprise", 409)
    now = _now()
    try:
        if name == "sync":
            d = await _call(db, tenant, "GET", resource, "the device")
            await _raw(db).mdm_devices.update_one({"id": device["id"], "tenantId": tenant}, {"$set": _row(tenant, d, now)})
        elif name in ("lock", "restart"):
            await _call(db, tenant, "POST", f"{resource}:issueCommand", f"the {name} command",
                        json={"type": "LOCK" if name == "lock" else "REBOOT"})
        else:
            await _call(db, tenant, "DELETE", resource, f"the {name}",
                        params={"wipeDataFlags": "WIPE_EXTERNAL_STORAGE"} if name == "wipe" else None)
        error = None
    except AndroidError as e:
        error = str(e)
    entry = {"action": name, "actor": who, "timestamp": now, "status": "failed" if error else "sent", "via": "android",
             **({"error": error} if error else {})}
    await _raw(db).mdm_devices.update_one({"id": device["id"], "tenantId": tenant}, {"$push": {"action_log": entry}})
    await _audit(db, f"mdm.android.{name}", tenant, who, outcome="failure" if error else "success", resourceId=device["id"],
                 target=device.get("name"))
    if error:
        raise AndroidError(error, 502)
    return {"device_id": device["id"], "action": name, "status": "sent", "timestamp": now}


async def sync_loop() -> None:
    """Every hour, sync each organization whose enterprise is set (a failure is recorded on its connector)."""
    import logging
    from database import get_database
    await asyncio.sleep(240)
    while True:
        db = get_database()
        for cfg in await _raw(db).mdm_connectors.find({"provider": "android", "enterprise": {"$exists": True}},
                                                     {"_id": 0, "tenantId": 1}).to_list(500):
            try:
                await sync(db, cfg["tenantId"])
            except Exception as exc:  # one organization's failure must not stop the others
                logging.getLogger(__name__).warning("Android sync for %s failed: %s", cfg["tenantId"], exc)
        await asyncio.sleep(3600)
