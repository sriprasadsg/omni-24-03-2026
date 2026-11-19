"""Fleet connector for Mobile Device Management (open source: Fleet, built on osquery).

An organization connects its own Fleet server with its address and an API token (an API-only user; the observer
role is enough to read, maintainer to refetch). The token is encrypted at rest (encryption_service) and never
returned. A sync reads Fleet's hosts into ``mdm_devices`` (source "fleet", keyed by the Fleet host id); a host that
left Fleet is marked ``fleetRemoved``, never deleted. A host is compliant when it fails none of Fleet's policies, and
"unknown" while Fleet has no policies. The one remote action is "sync" (Fleet's refetch: the host reports again at
its next check-in); lock and wipe are Fleet Premium features and are not offered. Fleet's address must be public
https or on the server operator's self-hosted list (self_hosted).
"""
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

import httpx

import audit_ledger
import self_hosted

TOKEN = re.compile(r"^[A-Za-z0-9+/=_-]{20,512}$")
PER_PAGE = 500
MAX_PAGES = 100
TIMEOUT = 30.0
LINUX = ("ubuntu", "debian", "rhel", "centos", "fedora", "amzn", "arch", "gentoo", "linux", "sles", "opensuse", "pop", "kali", "tuxedo")


class FleetError(Exception):
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
        raise FleetError("The Fleet address is the server only, such as https://fleet.example.com")
    try:
        await self_hosted.check_url(base + "/")
    except ValueError as exc:
        raise FleetError(f"Fleet's address is refused: {exc}")
    return base


async def save_config(db, tenant: str, base_url: str, token: Optional[str], who: str) -> Dict[str, Any]:
    from encryption_service import get_encryption_service
    base = await _checked_base(base_url)
    raw = _raw(db)
    existing = await raw.mdm_connectors.find_one({"tenantId": tenant, "provider": "fleet"}, {"_id": 0, "secret": 1})
    token = (token or "").strip()
    if not token and not existing:
        raise FleetError("The API token is required")
    if token and not TOKEN.match(token):
        raise FleetError("Paste the API token of a Fleet API-only user (fleetctl user create --api-only)")
    doc = {"tenantId": tenant, "provider": "fleet", "baseUrl": base, "updatedBy": who, "updatedAt": _now()}
    if token:
        doc["secret"] = get_encryption_service().encrypt(token)
    await raw.mdm_connectors.update_one({"tenantId": tenant, "provider": "fleet"}, {"$set": doc}, upsert=True)
    await _audit(db, "mdm.fleet.connect", tenant, who, baseUrl=base)
    return await get_config(db, tenant)


async def get_config(db, tenant: str) -> Dict[str, Any]:
    raw = _raw(db)
    cfg = await raw.mdm_connectors.find_one({"tenantId": tenant, "provider": "fleet"}, {"_id": 0, "secret": 0})
    if not cfg:
        return {"connected": False}
    devices = await raw.mdm_devices.count_documents({"tenantId": tenant, "source": "fleet", "fleetRemoved": {"$ne": True}})
    return {"connected": True, **{k: cfg.get(k) for k in ("baseUrl", "updatedBy", "updatedAt", "lastSyncAt", "lastSyncCount",
                                                           "lastError")}, "devices": devices}


async def disconnect(db, tenant: str, who: str) -> None:
    raw = _raw(db)
    if (await raw.mdm_connectors.delete_one({"tenantId": tenant, "provider": "fleet"})).deleted_count == 0:
        raise FleetError("Fleet is not connected", 404)
    await raw.mdm_devices.update_many({"tenantId": tenant, "source": "fleet"}, {"$set": {"fleetDisconnected": True}})
    await _audit(db, "mdm.fleet.disconnect", tenant, who)


async def _session(db, tenant: str):
    """(base URL, client with the token) for the organization's Fleet; the address is checked again on every use."""
    from encryption_service import get_encryption_service
    cfg = await _raw(db).mdm_connectors.find_one({"tenantId": tenant, "provider": "fleet"})
    if not cfg:
        raise FleetError("Fleet is not connected", 404)
    base = await _checked_base(cfg["baseUrl"])
    token = get_encryption_service().decrypt(cfg["secret"])
    return base, _client(headers={"Authorization": f"Bearer {token}"}, verify=self_hosted.verify(base + "/"))


async def _get(c: httpx.AsyncClient, url: str, **params: Any) -> Dict[str, Any]:
    try:
        r = await c.get(url, params=params)
    except httpx.HTTPError as exc:
        raise FleetError(f"Fleet could not be reached ({type(exc).__name__})", 502)
    if r.status_code in (401, 403):
        raise FleetError(f"Fleet refused the API token (HTTP {r.status_code})", 502)
    if r.status_code != 200:
        raise FleetError(f"Fleet answered HTTP {r.status_code}", 502)
    return r.json()


def _platform(name: Optional[str]) -> str:
    p = (name or "").lower()
    if p == "darwin":
        return "macos"
    if p in ("ios", "ipados"):
        return "ios"
    if p == "chrome":
        return "chromeos"
    if p in LINUX:
        return "linux"
    return p or "unknown"


def _row(tenant: str, h: Dict[str, Any], has_policies: bool, now: str) -> Dict[str, Any]:
    issues = h.get("issues") or {}
    failing = issues.get("failing_policies_count") or 0
    return {"tenantId": tenant, "source": "fleet", "externalId": str(h["id"]), "name": h.get("display_name") or h.get("computer_name") or h.get("hostname"),
            "platform": _platform(h.get("platform")), "os_version": h.get("os_version"), "model": h.get("hardware_model"),
            "manufacturer": h.get("hardware_vendor"), "serial_number": h.get("hardware_serial") or None, "assigned_user": None,
            "enrollment_status": "enrolled",
            "compliance_status": "unknown" if not has_policies else "non_compliant" if failing else "compliant",
            "last_seen": h.get("seen_time"), "enrolled_at": h.get("last_enrolled_at"),
            "compliance_details": {"failingPolicies": failing, "criticalVulnerabilities": issues.get("critical_vulnerabilities_count"),
                                   "online": h.get("status") == "online", "ip": h.get("primary_ip"), "mac": h.get("primary_mac"),
                                   "osqueryVersion": h.get("osquery_version")},
            "fleetRemoved": False, "fleetDisconnected": False, "syncedAt": now, "updated_at": now}


async def sync(db, tenant: str, who: str = "system") -> Dict[str, Any]:
    """Read every Fleet host into mdm_devices; returns {devices, removed}."""
    raw, now = _raw(db), _now()
    try:
        base, client = await _session(db, tenant)
        seen: List[str] = []
        async with client as c:
            policies = await _get(c, f"{base}/api/v1/fleet/global/policies")
            has_policies = bool(policies.get("policies"))
            for page in range(MAX_PAGES):
                hosts = (await _get(c, f"{base}/api/v1/fleet/hosts", page=page, per_page=PER_PAGE, order_key="id")).get("hosts") or []
                for h in hosts:
                    if h.get("id") is None:
                        continue
                    seen.append(str(h["id"]))
                    await raw.mdm_devices.update_one({"tenantId": tenant, "source": "fleet", "externalId": str(h["id"])},
                                                     {"$set": _row(tenant, h, has_policies, now), "$setOnInsert": {"id": f"mdm-{uuid.uuid4().hex[:12]}"}},
                                                     upsert=True)
                if len(hosts) < PER_PAGE:
                    break
    except FleetError as e:
        await raw.mdm_connectors.update_one({"tenantId": tenant, "provider": "fleet"}, {"$set": {"lastError": str(e), "lastErrorAt": now}})
        raise
    removed = (await raw.mdm_devices.update_many({"tenantId": tenant, "source": "fleet", "externalId": {"$nin": seen}},
                                                 {"$set": {"fleetRemoved": True, "updated_at": now}})).modified_count
    await raw.mdm_connectors.update_one({"tenantId": tenant, "provider": "fleet"},
                                        {"$set": {"lastSyncAt": now, "lastSyncCount": len(seen), "lastError": None}})
    await _audit(db, "mdm.fleet.sync", tenant, who, devices=len(seen), removed=removed)
    return {"devices": len(seen), "removed": removed}


async def action(db, tenant: str, device: Dict[str, Any], name: str, who: str) -> Dict[str, Any]:
    """Ask Fleet to refetch one host (the only action Fleet's free edition has); recorded on the device."""
    if name != "sync":
        raise FleetError("Fleet devices take sync only (lock and wipe need Fleet Premium)")
    base, client = await _session(db, tenant)
    async with client as c:
        try:
            r = await c.post(f"{base}/api/v1/fleet/hosts/{device['externalId']}/refetch")
        except httpx.HTTPError as exc:
            raise FleetError(f"Fleet could not be reached ({type(exc).__name__})", 502)
    ok, now = r.status_code in (200, 202, 204), _now()
    entry = {"action": name, "actor": who, "timestamp": now, "status": "sent" if ok else "failed", "via": "fleet",
             **({} if ok else {"error": f"HTTP {r.status_code}"})}
    await _raw(db).mdm_devices.update_one({"id": device["id"], "tenantId": tenant}, {"$push": {"action_log": entry}})
    await _audit(db, "mdm.fleet.sync_host", tenant, who, outcome="success" if ok else "failure", resourceId=device["id"],
                 target=device.get("name"))
    if not ok:
        raise FleetError(f"Fleet answered HTTP {r.status_code}", 502)
    return {"device_id": device["id"], "action": name, "status": "sent", "timestamp": now}


async def sync_loop() -> None:
    """Every hour, sync each connected organization (a failure is recorded on its connector)."""
    import asyncio
    import logging
    from database import get_database
    await asyncio.sleep(240)
    while True:
        db = get_database()
        for cfg in await _raw(db).mdm_connectors.find({"provider": "fleet"}, {"_id": 0, "tenantId": 1}).to_list(500):
            try:
                await sync(db, cfg["tenantId"])
            except Exception as exc:  # one organization's failure must not stop the others
                logging.getLogger(__name__).warning("Fleet sync for %s failed: %s", cfg["tenantId"], exc)
        await asyncio.sleep(3600)
