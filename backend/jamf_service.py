"""Jamf Pro connector for Mobile Device Management (Apple devices without Intune).

An organization connects its own Jamf Pro (Jamf Cloud or self-hosted, 10.49 or later) with its address and an API
client (Settings > API Roles and Clients). The client's role needs Read Computers and Read Mobile Devices to list
devices, and for actions View MDM command information in Jamf Pro API plus the remote lock, wipe, restart and blank
push privileges. The client secret is encrypted at rest (encryption_service) and never returned. A sync reads Jamf's
computers and mobile devices into ``mdm_devices`` (source "jamf", keyed by kind and Jamf id); a device that left Jamf
is marked ``jamfRemoved``, never deleted. Jamf's inventory carries no compliance verdict, so a device is
non_compliant only when Jamf detected a jailbreak and "unknown" otherwise; encryption and supervision are kept as
details. Remote actions are sent to Jamf for real: sync (a blank push, so the device checks in), lock, restart and
wipe (v2 MDM commands), wipe only with the device's name typed; locking or wiping a Mac needs a 6-digit PIN, which
is sent to Jamf and never stored. Jamf's address must be public https or on the server operator's self-hosted list.
"""
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import httpx

import audit_ledger
import self_hosted

GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
SECRET = re.compile(r"^\S{16,512}$")
PIN = re.compile(r"^\d{6}$")
# v4 is current (Jamf Pro 11.34); older servers answer 404 there and are read through v3, then v1.
COMPUTER_PATHS = ("/api/v4/computers-inventory", "/api/v3/computers-inventory", "/api/v1/computers-inventory")
COMPUTER_SECTIONS = ("GENERAL", "HARDWARE", "OPERATING_SYSTEM", "USER_AND_LOCATION")
MOBILE_SECTIONS = ("GENERAL", "HARDWARE", "USER_AND_LOCATION", "SECURITY")
COMMANDS = {"lock": "DEVICE_LOCK", "restart": "RESTART_DEVICE", "wipe": "ERASE_DEVICE"}
ACTIONS = ("sync", "lock", "restart", "wipe")
PER_PAGE = 200
MAX_PAGES = 100
TIMEOUT = 30.0
_tokens: Dict[str, Tuple[str, float]] = {}


class JamfError(Exception):
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


async def _checked_base(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    try:
        p = urlsplit(base)
        ok = p.scheme in ("http", "https") and bool(p.hostname) and p.path == "" and not (p.query or p.fragment or p.username)
        p.port  # noqa: B018  (raises on a malformed port)
    except ValueError:
        ok = False
    if not ok:
        raise JamfError("The Jamf Pro address is the server only, such as https://yourorg.jamfcloud.com")
    try:
        await self_hosted.check_url(base + "/")
    except ValueError as exc:
        raise JamfError(f"Jamf Pro's address is refused: {exc}")
    return base


async def save_config(db, tenant: str, base_url: str, client_id: str, client_secret: Optional[str], who: str) -> Dict[str, Any]:
    from encryption_service import get_encryption_service
    base = await _checked_base(base_url)
    if not GUID.match((client_id or "").strip()):
        raise JamfError("The client ID is the GUID shown on the API client in Jamf Pro (Settings > API Roles and Clients)")
    raw = _raw(db)
    existing = await raw.mdm_connectors.find_one({"tenantId": tenant, "provider": "jamf"}, {"_id": 0, "secret": 1})
    client_secret = (client_secret or "").strip()
    if not client_secret and not existing:
        raise JamfError("The client secret is required")
    if client_secret and not SECRET.match(client_secret):
        raise JamfError("Paste the client secret Jamf Pro generated for the API client")
    doc = {"tenantId": tenant, "provider": "jamf", "baseUrl": base, "clientId": client_id.strip().lower(),
           "updatedBy": who, "updatedAt": _now()}
    if client_secret:
        doc["secret"] = get_encryption_service().encrypt(client_secret)
    await raw.mdm_connectors.update_one({"tenantId": tenant, "provider": "jamf"}, {"$set": doc}, upsert=True)
    _tokens.pop(tenant, None)
    await _audit(db, "mdm.jamf.connect", tenant, who, baseUrl=base, clientId=doc["clientId"])
    return await get_config(db, tenant)


async def get_config(db, tenant: str) -> Dict[str, Any]:
    raw = _raw(db)
    cfg = await raw.mdm_connectors.find_one({"tenantId": tenant, "provider": "jamf"}, {"_id": 0, "secret": 0})
    if not cfg:
        return {"connected": False}
    devices = await raw.mdm_devices.count_documents({"tenantId": tenant, "source": "jamf", "jamfRemoved": {"$ne": True}})
    return {"connected": True, **{k: cfg.get(k) for k in ("baseUrl", "clientId", "updatedBy", "updatedAt", "lastSyncAt",
                                                           "lastSyncCount", "lastError")}, "devices": devices}


async def disconnect(db, tenant: str, who: str) -> None:
    raw = _raw(db)
    if (await raw.mdm_connectors.delete_one({"tenantId": tenant, "provider": "jamf"})).deleted_count == 0:
        raise JamfError("Jamf Pro is not connected", 404)
    await raw.mdm_devices.update_many({"tenantId": tenant, "source": "jamf"}, {"$set": {"jamfDisconnected": True}})
    _tokens.pop(tenant, None)
    await _audit(db, "mdm.jamf.disconnect", tenant, who)


async def _session(db, tenant: str):
    """(base URL, client with a bearer token) for the organization's Jamf Pro; the address is checked on every use."""
    from encryption_service import get_encryption_service
    cfg = await _raw(db).mdm_connectors.find_one({"tenantId": tenant, "provider": "jamf"})
    if not cfg:
        raise JamfError("Jamf Pro is not connected", 404)
    base = await _checked_base(cfg["baseUrl"])
    verify = self_hosted.verify(base + "/")
    cached = _tokens.get(tenant)
    if cached and cached[1] > time.time() + 10:
        token = cached[0]
    else:
        async with _client(verify=verify) as c:
            try:
                r = await c.post(f"{base}/api/oauth/token", data={
                    "grant_type": "client_credentials", "client_id": cfg["clientId"],
                    "client_secret": get_encryption_service().decrypt(cfg["secret"])})
            except httpx.HTTPError as exc:
                raise JamfError(f"Jamf Pro could not be reached ({type(exc).__name__})", 502)
        if r.status_code != 200:
            raise JamfError(f"Jamf Pro refused the API client (HTTP {r.status_code}); check the client ID and secret", 502)
        body = r.json()
        token = body["access_token"]
        _tokens[tenant] = (token, time.time() + int(body.get("expires_in", 60)))
    return base, _client(headers={"Authorization": f"Bearer {token}"}, verify=verify)


def _jamf_error(r: httpx.Response) -> JamfError:
    if r.status_code in (401, 403):
        return JamfError(f"Jamf Pro refused (HTTP {r.status_code}): give the API client's role Read Computers, Read Mobile "
                         "Devices and the remote command privileges", 502)
    return JamfError(f"Jamf Pro answered HTTP {r.status_code}", 502)


async def _send(c: httpx.AsyncClient, method: str, url: str, **kw: Any) -> httpx.Response:
    try:
        return await c.request(method, url, **kw)
    except httpx.HTTPError as exc:
        raise JamfError(f"Jamf Pro could not be reached ({type(exc).__name__})", 502)


async def _pages(c: httpx.AsyncClient, url: str, sections: Tuple[str, ...], **extra: Any):
    """Yield every inventory record of a paged Jamf Pro API list; a 404 on the first page is returned as None."""
    for page in range(MAX_PAGES):
        params = [("section", s) for s in sections] + [("page", page), ("page-size", PER_PAGE)] + list(extra.items())
        r = await _send(c, "GET", url, params=params)
        if r.status_code == 404 and page == 0:
            yield None
            return
        if r.status_code != 200:
            raise _jamf_error(r)
        body = r.json()
        results = body.get("results") or []
        for item in results:
            yield item
        if not results or (page + 1) * PER_PAGE >= int(body.get("totalCount") or 0):
            return


def _encrypted(status: Optional[str]) -> Optional[bool]:
    s = (status or "").upper()
    return True if s in ("ALL_ENCRYPTED", "BOOT_ENCRYPTED") else False if s == "NOT_ENCRYPTED" else None


def _base_row(tenant: str, now: str) -> Dict[str, Any]:
    return {"tenantId": tenant, "source": "jamf", "manufacturer": "Apple", "jamfRemoved": False, "jamfDisconnected": False,
            "syncedAt": now, "updated_at": now}


def _computer_row(tenant: str, d: Dict[str, Any], now: str) -> Dict[str, Any]:
    g, hw = d.get("general") or {}, d.get("hardware") or {}
    os_, user = d.get("operatingSystem") or {}, d.get("userAndLocation") or {}
    managed = (g.get("remoteManagement") or {}).get("managed")
    return {**_base_row(tenant, now), "externalId": f"computer-{d['id']}", "jamfKind": "computer", "jamfId": str(d["id"]),
            "jamfManagementId": g.get("managementId"), "name": g.get("name"), "platform": "macos",
            "os_version": os_.get("version"), "model": hw.get("model"), "serial_number": hw.get("serialNumber"),
            "assigned_user": user.get("email") or user.get("username"),
            "enrollment_status": "enrolled" if managed else "unmanaged", "compliance_status": "unknown",
            "last_seen": g.get("lastContact") or g.get("lastContactTime"), "enrolled_at": g.get("lastEnrolledDate"),
            "compliance_details": {"encrypted": _encrypted(os_.get("fileVault2Status")), "fileVault": os_.get("fileVault2Status"),
                                   "supervised": g.get("supervised"), "managed": managed, "mac": hw.get("macAddress")}}


def _mobile_row(tenant: str, d: Dict[str, Any], now: str) -> Dict[str, Any]:
    g, hw = d.get("general") or {}, d.get("hardware") or {}
    user, sec = d.get("userAndLocation") or {}, d.get("security") or {}
    jailbroken = sec.get("jailBreakDetected")
    return {**_base_row(tenant, now), "externalId": f"mobile-{d['mobileDeviceId']}", "jamfKind": "mobile",
            "jamfId": str(d["mobileDeviceId"]), "jamfManagementId": g.get("managementId"), "name": g.get("displayName"),
            "platform": (d.get("deviceType") or "ios").lower(), "os_version": g.get("osVersion"), "model": hw.get("model"),
            "serial_number": hw.get("serialNumber"), "assigned_user": user.get("emailAddress") or user.get("username"),
            "enrollment_status": "enrolled" if g.get("managed") else "unmanaged",
            "compliance_status": "non_compliant" if jailbroken is True else "unknown",
            "last_seen": g.get("lastInventoryUpdateDate"), "enrolled_at": g.get("lastEnrolledDate"),
            "compliance_details": {"encrypted": sec.get("dataProtected"), "jailbroken": jailbroken,
                                   "supervised": g.get("supervised"), "managed": g.get("managed")}}


async def sync(db, tenant: str, who: str = "system") -> Dict[str, Any]:
    """Read every Jamf Pro computer and mobile device into mdm_devices; returns {devices, removed}."""
    raw, now = _raw(db), _now()
    seen: List[str] = []

    async def store(row: Dict[str, Any]) -> None:
        seen.append(row["externalId"])
        await raw.mdm_devices.update_one({"tenantId": tenant, "source": "jamf", "externalId": row["externalId"]},
                                         {"$set": row, "$setOnInsert": {"id": f"mdm-{uuid.uuid4().hex[:12]}"}}, upsert=True)
    try:
        base, client = await _session(db, tenant)
        async with client as c:
            for path in COMPUTER_PATHS:
                found = True
                async for d in _pages(c, base + path, COMPUTER_SECTIONS):
                    if d is None:
                        found = False
                    elif d.get("id") is not None:
                        await store(_computer_row(tenant, d, now))
                if found:
                    break
            else:
                raise JamfError("Jamf Pro has no computer inventory API here (it needs Jamf Pro 10.49 or later)", 502)
            # LENIENT: a device whose inventory Jamf cannot read comes back with empty sections instead of failing the page.
            async for d in _pages(c, f"{base}/api/v2/mobile-devices/detail", MOBILE_SECTIONS, **{"exception-handling": "LENIENT"}):
                if d is None:
                    raise JamfError("Jamf Pro has no mobile device inventory API here (it needs Jamf Pro 10.49 or later)", 502)
                if d.get("mobileDeviceId") is not None:
                    await store(_mobile_row(tenant, d, now))
    except JamfError as e:
        await raw.mdm_connectors.update_one({"tenantId": tenant, "provider": "jamf"}, {"$set": {"lastError": str(e), "lastErrorAt": now}})
        raise
    removed = (await raw.mdm_devices.update_many({"tenantId": tenant, "source": "jamf", "externalId": {"$nin": seen}},
                                                 {"$set": {"jamfRemoved": True, "updated_at": now}})).modified_count
    await raw.mdm_connectors.update_one({"tenantId": tenant, "provider": "jamf"},
                                        {"$set": {"lastSyncAt": now, "lastSyncCount": len(seen), "lastError": None}})
    await _audit(db, "mdm.jamf.sync", tenant, who, devices=len(seen), removed=removed)
    return {"devices": len(seen), "removed": removed}


def _command(name: str, device: Dict[str, Any], pin: Optional[str]) -> Dict[str, Any]:
    data: Dict[str, Any] = {"commandType": COMMANDS[name]}
    if device.get("jamfKind") == "computer" and name in ("lock", "wipe"):
        data["pin"] = pin
    if device.get("jamfKind") == "computer" and name == "wipe":
        data["obliterationBehavior"] = "Default"
    return data


async def action(db, tenant: str, device: Dict[str, Any], name: str, who: str, confirm: Optional[str],
                 pin: Optional[str] = None) -> Dict[str, Any]:
    """Send one remote action on a Jamf Pro device; recorded on the device as sent or failed (never with the PIN)."""
    if name not in ACTIONS:
        raise JamfError(f"Jamf Pro devices take {', '.join(ACTIONS)}")
    if name == "wipe" and (confirm or "").strip() != (device.get("name") or ""):
        raise JamfError("Type the device name to confirm wipe")
    pin = (pin or "").strip()
    if device.get("jamfKind") == "computer" and name in ("lock", "wipe") and not PIN.match(pin):
        raise JamfError(f"A Mac needs a 6-digit PIN to {name}; it is the code that unlocks the Mac afterwards")
    mid = device.get("jamfManagementId")
    if not mid:
        raise JamfError("Jamf Pro has no management ID for this device, so it is not under Jamf's MDM", 409)
    base, client = await _session(db, tenant)
    async with client as c:
        if name == "sync":
            r = await _send(c, "POST", f"{base}/api/v2/mdm/blank-push", json={"clientManagementIds": [mid]})
            try:
                failed = (r.json() or {}).get("errorUuids") or [] if r.status_code == 200 else []
            except ValueError:
                failed = []
            ok = r.status_code == 200 and mid not in failed
        else:
            r = await _send(c, "POST", f"{base}/api/v2/mdm/commands",
                            json={"clientData": [{"managementId": mid}], "commandData": _command(name, device, pin)})
            ok = r.status_code in (200, 201)
    now = _now()
    entry = {"action": name, "actor": who, "timestamp": now, "status": "sent" if ok else "failed", "via": "jamf",
             **({} if ok else {"error": f"HTTP {r.status_code}"})}
    await _raw(db).mdm_devices.update_one({"id": device["id"], "tenantId": tenant}, {"$push": {"action_log": entry}})
    await _audit(db, f"mdm.jamf.{name}", tenant, who, outcome="success" if ok else "failure", resourceId=device["id"],
                 target=device.get("name"))
    if not ok:
        raise JamfError("Jamf Pro could not send the blank push to this device", 502) if r.status_code == 200 else _jamf_error(r)
    return {"device_id": device["id"], "action": name, "status": "sent", "timestamp": now}


async def sync_loop() -> None:
    """Every hour, sync each connected organization (a failure is recorded on its connector)."""
    import asyncio
    import logging
    from database import get_database
    await asyncio.sleep(300)
    while True:
        db = get_database()
        for cfg in await _raw(db).mdm_connectors.find({"provider": "jamf"}, {"_id": 0, "tenantId": 1}).to_list(500):
            try:
                await sync(db, cfg["tenantId"])
            except Exception as exc:  # one organization's failure must not stop the others
                logging.getLogger(__name__).warning("Jamf Pro sync for %s failed: %s", cfg["tenantId"], exc)
        await asyncio.sleep(3600)
