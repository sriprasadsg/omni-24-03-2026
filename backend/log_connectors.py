"""Cloud log connectors (Wave 3): Microsoft Entra ID, Microsoft 365, AWS CloudTrail, Google Workspace and authentik (an
open-source identity provider the organization runs itself) logs flow into the SIEM pipeline, so library and organization rules, Hunting and the SOC console see them like agent logs.

One row per organization and provider in ``log_connectors``: the read-only credentials (the secret part encrypted at
rest, never returned), a cursor per stream, and the outcome of the last run (``lastRunAt``, ``lastSuccessAt``,
``lastError``, ``lastCount``, ``totalEvents``). ``pull_loop`` runs every enabled connector every INTERVAL seconds;
"Pull now" runs one at once. A run stores new events in ``soc_log_events`` (siem_pipeline, unique per record), runs the
rules over them, and only then moves the cursor, so a failed run is retried from the same place.
"""
import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

import audit_ledger
import log_connector_sources as sources
import self_hosted

logger = logging.getLogger(__name__)

PROVIDERS = {"entra": "Microsoft Entra ID", "m365": "Microsoft 365", "aws": "AWS CloudTrail", "google": "Google Workspace",
             "authentik": "authentik"}
INTERVAL = 300
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
AWS_KEY_ID = re.compile(r"^(AKIA|ASIA)[A-Z0-9]{16}$")
AWS_REGION = re.compile(r"^[a-z]{2}(-gov)?-[a-z]+-\d$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SHOWN = ("provider", "enabled", "azureTenantId", "clientId", "accessKeyId", "regions", "adminEmail", "serviceAccount", "baseUrl",
         "updatedBy", "updatedAt", "lastRunAt", "lastSuccessAt", "lastError", "lastCount", "totalEvents")


class ConnectorError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _raw(db):
    return getattr(db, "_db", db)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _settings(provider: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """The non-secret settings, checked; the secret itself is checked in save_config."""
    if provider in ("entra", "m365"):
        tid, cid = str(body.get("azureTenantId") or "").strip(), str(body.get("clientId") or "").strip()
        if not GUID.match(tid) or not GUID.match(cid):
            raise ConnectorError("The directory (tenant) id and the application (client) id are GUIDs from the app registration")
        return {"azureTenantId": tid.lower(), "clientId": cid.lower()}
    if provider == "aws":
        key_id = str(body.get("accessKeyId") or "").strip()
        regions = body.get("regions") or ["us-east-1"]
        if not AWS_KEY_ID.match(key_id):
            raise ConnectorError("The access key id starts with AKIA or ASIA and has 20 characters")
        if not isinstance(regions, list) or not 1 <= len(regions) <= 10 or not all(isinstance(r, str) and AWS_REGION.match(r) for r in regions):
            raise ConnectorError("regions must list 1 to 10 AWS regions such as eu-west-1")
        return {"accessKeyId": key_id, "regions": sorted(set(regions))}
    if provider == "authentik":
        base = str(body.get("baseUrl") or "").strip().rstrip("/")
        try:
            p = urlsplit(base)
            ok = p.scheme in ("http", "https") and bool(p.hostname) and p.path in ("", "/") and not (p.query or p.fragment or p.username)
            p.port  # noqa: B018  (raises on a malformed port)
        except ValueError:
            ok = False
        if not ok:
            raise ConnectorError("baseUrl is authentik's address only, such as https://auth.example.com")
        return {"baseUrl": base}
    email = str(body.get("adminEmail") or "").strip()
    if not EMAIL.match(email):
        raise ConnectorError("adminEmail is the Google Workspace admin the service account acts as")
    return {"adminEmail": email.lower()}


def _check_secret(provider: str, secret: str) -> Dict[str, Any]:
    if provider == "aws" and not re.fullmatch(r"[A-Za-z0-9/+=]{40}", secret):
        raise ConnectorError("The AWS secret access key has 40 characters")
    if provider == "google":
        try:
            info = json.loads(secret)
        except ValueError:
            raise ConnectorError("Paste the service account's JSON key file")
        if info.get("type") != "service_account" or not info.get("client_email") or not info.get("private_key"):
            raise ConnectorError("That JSON is not a service account key (type service_account, client_email, private_key)")
        return {"serviceAccount": info["client_email"]}
    if provider == "authentik" and not re.fullmatch(r"[A-Za-z0-9]{20,128}", secret):
        raise ConnectorError("Paste the key of an authentik API token (Directory > Tokens and App passwords)")
    return {}


async def save_config(db, tenant: str, provider: str, body: Dict[str, Any], who: str) -> Dict[str, Any]:
    from encryption_service import get_encryption_service
    if provider not in PROVIDERS:
        raise ConnectorError(f"provider must be one of: {', '.join(PROVIDERS)}", 404)
    raw = _raw(db)
    existing = await raw.log_connectors.find_one({"tenantId": tenant, "provider": provider}, {"_id": 0, "secret": 1})
    secret = str(body.get("secret") or "").strip()
    if not secret and not existing:
        raise ConnectorError("The secret is required")
    doc = {"tenantId": tenant, "provider": provider, **_settings(provider, body),
           "enabled": bool(body.get("enabled", True)), "updatedBy": who, "updatedAt": _now().isoformat()}
    if provider == "authentik":
        try:
            await self_hosted.check_url(doc["baseUrl"] + "/")
        except ValueError as exc:
            raise ConnectorError(f"authentik's address is refused: {exc}")
    if secret:
        doc.update(_check_secret(provider, secret), secret=get_encryption_service().encrypt(secret))
    await raw.log_connectors.update_one({"tenantId": tenant, "provider": provider},
                                        {"$set": doc, "$setOnInsert": {"cursor": {}, "totalEvents": 0}}, upsert=True)
    await _audit(db, "siem.log_connector.save", tenant, who, provider=provider, enabled=doc["enabled"])
    return (await list_config(db, tenant))[provider]


async def list_config(db, tenant: str) -> Dict[str, Dict[str, Any]]:
    """Every provider, connected or not, without secrets."""
    rows = {r["provider"]: r async for r in _raw(db).log_connectors.find({"tenantId": tenant}, {"_id": 0, "secret": 0, "cursor": 0})}
    return {p: {"name": name, "connected": p in rows, **{k: rows[p].get(k) for k in SHOWN if p in rows}} for p, name in PROVIDERS.items()}


async def remove(db, tenant: str, provider: str, who: str) -> None:
    if (await _raw(db).log_connectors.delete_one({"tenantId": tenant, "provider": provider})).deleted_count == 0:
        raise ConnectorError("That connector is not set up", 404)
    await _audit(db, "siem.log_connector.remove", tenant, who, provider=provider)


async def _audit(db, action: str, tenant: str, who: str, **fields: Any) -> None:
    try:
        await audit_ledger.event(action, tenant, actor={"email": who, "tenantId": tenant}, db=_raw(db), resourceType="siem", **fields)
    except Exception as exc:  # the ledger spools on failure; never undo the change over it
        logger.warning("Audit entry %s not recorded: %s", action, exc)


async def run(db, row: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    """One pull for one connector row (with its secret); records the outcome on the row and returns it."""
    import siem_pipeline
    from encryption_service import get_encryption_service
    raw, now = _raw(db), now or _now()
    where = {"tenantId": row["tenantId"], "provider": row["provider"]}
    cfg = {**row, "secret": get_encryption_service().decrypt(row["secret"])}
    try:
        events, cursor = await sources.FETCH[row["provider"]](cfg, row.get("cursor") or {}, now)
    except sources.SourceError as exc:
        await raw.log_connectors.update_one(where, {"$set": {"lastRunAt": now.isoformat(), "lastError": str(exc)}})
        return {"ok": False, "error": str(exc)}
    new: List[Dict[str, Any]] = []
    for event in events:
        event.update(tenantId=row["tenantId"], agentId=None)
        if await siem_pipeline._store(db, event):
            new.append(event)
    hits = await siem_pipeline.evaluate(db, new, now) if new else []
    await raw.log_connectors.update_one(where, {"$set": {"cursor": cursor, "lastRunAt": now.isoformat(), "lastSuccessAt": now.isoformat(),
                                                         "lastError": None, "lastCount": len(new)}, "$inc": {"totalEvents": len(new)}})
    return {"ok": True, "read": len(events), "new": len(new), "hits": len(hits)}


async def pull_now(db, tenant: str, provider: str, who: str) -> Dict[str, Any]:
    row = await _raw(db).log_connectors.find_one({"tenantId": tenant, "provider": provider}, {"_id": 0})
    if not row:
        raise ConnectorError("That connector is not set up", 404)
    out = await run(db, row)
    await _audit(db, "siem.log_connector.pull", tenant, who, provider=provider, ok=out["ok"], new=out.get("new"))
    return out


async def pull_loop() -> None:
    """Every INTERVAL seconds, pull every enabled connector (one organization's failure never stops the others)."""
    from database import get_database
    await asyncio.sleep(150)
    while True:
        db = get_database()
        for row in await _raw(db).log_connectors.find({"enabled": True}, {"_id": 0}).to_list(1000):
            try:
                await run(db, row)
            except Exception as exc:
                logger.warning("Log connector %s/%s failed: %s", row.get("tenantId"), row.get("provider"), exc)
        await asyncio.sleep(INTERVAL)
