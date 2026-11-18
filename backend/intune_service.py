"""Microsoft Intune connector for Mobile Device Management (Wave 5).

An organization connects its own Intune with an Entra app registration (directory/tenant id, client id, client
secret; Graph application permissions DeviceManagementManagedDevices.Read.All and
DeviceManagementManagedDevices.PrivilegedOperations.All, admin consent). The secret is encrypted at rest
(encryption_service) and never returned. A sync reads Graph's managedDevices into ``mdm_devices`` (source "intune",
keyed by the Intune id); a device that left Intune is marked ``intuneRemoved``, never deleted. Remote actions on an
Intune device are sent to Graph for real (sync, lock, restart, retire, wipe), the destructive two only with the
device's name typed as confirmation; each is recorded on the device and in the audit ledger.
"""
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

import audit_ledger

GRAPH = "https://graph.microsoft.com/v1.0"
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
FIELDS = ("id,deviceName,operatingSystem,osVersion,complianceState,managementState,lastSyncDateTime,enrolledDateTime,"
          "userPrincipalName,model,manufacturer,serialNumber,isEncrypted,jailBroken,phoneNumber")
ACTIONS = {"sync": "syncDevice", "lock": "remoteLock", "restart": "rebootNow", "retire": "retire", "wipe": "wipe"}
DESTRUCTIVE = ("retire", "wipe")
MAX_PAGES = 100
TIMEOUT = 30.0
_tokens: Dict[str, Tuple[str, float]] = {}


class IntuneError(Exception):
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


async def save_config(db, tenant: str, azure_tenant_id: str, client_id: str, client_secret: Optional[str], who: str) -> Dict[str, Any]:
    from encryption_service import get_encryption_service
    if not GUID.match(azure_tenant_id or "") or not GUID.match(client_id or ""):
        raise IntuneError("The directory (tenant) id and the application (client) id are GUIDs from the app registration")
    raw = _raw(db)
    existing = await raw.mdm_connectors.find_one({"tenantId": tenant, "provider": "intune"}, {"_id": 0, "secret": 1})
    if not client_secret and not existing:
        raise IntuneError("The client secret is required")
    doc = {"tenantId": tenant, "provider": "intune", "azureTenantId": azure_tenant_id.lower(), "clientId": client_id.lower(),
           "updatedBy": who, "updatedAt": _now()}
    if client_secret:
        doc["secret"] = get_encryption_service().encrypt(client_secret.strip())
    await raw.mdm_connectors.update_one({"tenantId": tenant, "provider": "intune"}, {"$set": doc}, upsert=True)
    _tokens.pop(tenant, None)
    await _audit(db, "mdm.intune.connect", tenant, who, azureTenantId=doc["azureTenantId"], clientId=doc["clientId"])
    return await get_config(db, tenant)


async def get_config(db, tenant: str) -> Dict[str, Any]:
    raw = _raw(db)
    cfg = await raw.mdm_connectors.find_one({"tenantId": tenant, "provider": "intune"}, {"_id": 0, "secret": 0})
    if not cfg:
        return {"connected": False}
    devices = await raw.mdm_devices.count_documents({"tenantId": tenant, "source": "intune", "intuneRemoved": {"$ne": True}})
    return {"connected": True, **{k: cfg.get(k) for k in ("azureTenantId", "clientId", "updatedBy", "updatedAt",
                                                           "lastSyncAt", "lastSyncCount", "lastError")}, "devices": devices}


async def disconnect(db, tenant: str, who: str) -> None:
    raw = _raw(db)
    if (await raw.mdm_connectors.delete_one({"tenantId": tenant, "provider": "intune"})).deleted_count == 0:
        raise IntuneError("Intune is not connected", 404)
    await raw.mdm_devices.update_many({"tenantId": tenant, "source": "intune"}, {"$set": {"intuneDisconnected": True}})
    _tokens.pop(tenant, None)
    await _audit(db, "mdm.intune.disconnect", tenant, who)


async def _token(db, tenant: str) -> str:
    from encryption_service import get_encryption_service
    cached = _tokens.get(tenant)
    if cached and cached[1] > time.time() + 60:
        return cached[0]
    cfg = await _raw(db).mdm_connectors.find_one({"tenantId": tenant, "provider": "intune"})
    if not cfg:
        raise IntuneError("Intune is not connected", 404)
    async with _client() as c:
        r = await c.post(f"https://login.microsoftonline.com/{cfg['azureTenantId']}/oauth2/v2.0/token", data={
            "grant_type": "client_credentials", "client_id": cfg["clientId"],
            "client_secret": get_encryption_service().decrypt(cfg["secret"]), "scope": "https://graph.microsoft.com/.default"})
    if r.status_code != 200:
        raise IntuneError(f"Entra refused the app's credentials (HTTP {r.status_code}); check the ids and the secret", 502)
    body = r.json()
    _tokens[tenant] = (body["access_token"], time.time() + int(body.get("expires_in", 3600)))
    return body["access_token"]


def _graph_error(r: httpx.Response) -> IntuneError:
    if r.status_code in (401, 403):
        return IntuneError(f"Graph refused (HTTP {r.status_code}): grant the app DeviceManagementManagedDevices permissions "
                           "and admin consent", 502)
    return IntuneError(f"Graph answered HTTP {r.status_code}", 502)


def _platform(os_name: Optional[str]) -> str:
    o = (os_name or "").lower()
    return "ios" if o in ("ios", "ipados") else "macos" if o == "macos" else o or "unknown"


def _row(tenant: str, d: Dict[str, Any], now: str) -> Dict[str, Any]:
    state = str(d.get("complianceState") or "").lower()
    return {"tenantId": tenant, "source": "intune", "externalId": d["id"], "name": d.get("deviceName"),
            "platform": _platform(d.get("operatingSystem")), "os_version": d.get("osVersion"), "model": d.get("model"),
            "manufacturer": d.get("manufacturer"), "serial_number": d.get("serialNumber"),
            "assigned_user": d.get("userPrincipalName"), "phone_number": d.get("phoneNumber"),
            "enrollment_status": "enrolled" if str(d.get("managementState") or "").lower() == "managed" else str(d.get("managementState") or "unknown").lower(),
            "compliance_status": "compliant" if state == "compliant" else "non_compliant" if state == "noncompliant" else "unknown",
            "last_seen": d.get("lastSyncDateTime"), "enrolled_at": d.get("enrolledDateTime"),
            "compliance_details": {"encrypted": d.get("isEncrypted"), "jailbroken": d.get("jailBroken")},
            "intuneRemoved": False, "intuneDisconnected": False, "syncedAt": now, "updated_at": now}


async def sync(db, tenant: str, who: str = "system") -> Dict[str, Any]:
    """Read every managed device from Graph into mdm_devices; returns {devices, removed}."""
    raw, now = _raw(db), _now()
    try:
        token = await _token(db, tenant)
        url: Optional[str] = f"{GRAPH}/deviceManagement/managedDevices?$select={FIELDS}&$top=999"
        seen: List[str] = []
        async with _client(headers={"Authorization": f"Bearer {token}"}) as c:
            for _ in range(MAX_PAGES):
                if not url:
                    break
                r = await c.get(url)
                if r.status_code != 200:
                    raise _graph_error(r)
                body = r.json()
                for d in body.get("value", []):
                    if not d.get("id"):
                        continue
                    seen.append(d["id"])
                    await raw.mdm_devices.update_one({"tenantId": tenant, "source": "intune", "externalId": d["id"]},
                                                     {"$set": _row(tenant, d, now), "$setOnInsert": {"id": f"mdm-{uuid.uuid4().hex[:12]}"}},
                                                     upsert=True)
                url = body.get("@odata.nextLink")
                if url and not url.startswith(GRAPH + "/"):
                    raise IntuneError("Graph returned an unexpected next page address", 502)
    except IntuneError as e:
        await raw.mdm_connectors.update_one({"tenantId": tenant, "provider": "intune"}, {"$set": {"lastError": str(e), "lastErrorAt": now}})
        raise
    removed = (await raw.mdm_devices.update_many({"tenantId": tenant, "source": "intune", "externalId": {"$nin": seen}},
                                                 {"$set": {"intuneRemoved": True, "updated_at": now}})).modified_count
    await raw.mdm_connectors.update_one({"tenantId": tenant, "provider": "intune"},
                                        {"$set": {"lastSyncAt": now, "lastSyncCount": len(seen), "lastError": None}})
    await _audit(db, "mdm.intune.sync", tenant, who, devices=len(seen), removed=removed)
    return {"devices": len(seen), "removed": removed}


async def action(db, tenant: str, device: Dict[str, Any], name: str, who: str, confirm: Optional[str]) -> Dict[str, Any]:
    """Send one remote action on an Intune device to Graph; recorded on the device as sent or failed."""
    if name not in ACTIONS:
        raise IntuneError(f"Intune devices take {', '.join(ACTIONS)}")
    if name in DESTRUCTIVE and (confirm or "").strip() != (device.get("name") or ""):
        raise IntuneError(f"Type the device name to confirm {name}")
    token = await _token(db, tenant)
    async with _client(headers={"Authorization": f"Bearer {token}"}) as c:
        r = await c.post(f"{GRAPH}/deviceManagement/managedDevices/{device['externalId']}/{ACTIONS[name]}",
                         json={"keepEnrollmentData": False, "keepUserData": False} if name == "wipe" else None)
    ok, now = r.status_code in (200, 202, 204), _now()
    entry = {"action": name, "actor": who, "timestamp": now, "status": "sent" if ok else "failed", "via": "intune",
             **({} if ok else {"error": f"HTTP {r.status_code}"})}
    await _raw(db).mdm_devices.update_one({"id": device["id"], "tenantId": tenant}, {"$push": {"action_log": entry}})
    await _audit(db, f"mdm.intune.{name}", tenant, who, outcome="success" if ok else "failure", resourceId=device["id"],
                 target=device.get("name"))
    if not ok:
        raise _graph_error(r)
    return {"device_id": device["id"], "action": name, "status": "sent", "timestamp": now}


async def sync_loop() -> None:
    """Every hour, sync each connected organization (a failure is recorded on its connector)."""
    import asyncio
    import logging
    from database import get_database
    await asyncio.sleep(180)
    while True:
        db = get_database()
        for cfg in await _raw(db).mdm_connectors.find({"provider": "intune"}, {"_id": 0, "tenantId": 1}).to_list(500):
            try:
                await sync(db, cfg["tenantId"])
            except Exception as exc:  # one organization's failure must not stop the others
                logging.getLogger(__name__).warning("Intune sync for %s failed: %s", cfg["tenantId"], exc)
        await asyncio.sleep(3600)
