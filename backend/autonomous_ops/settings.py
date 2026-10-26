"""Per-tenant Autonomous Ops settings: level, maximum level, shadow flag, stop and eligibility.

Reads go through the raw Mongo handle with an explicit tenant id; the ambient tenant
ContextVar is never used. Eligibility is the literal presence of ``view:autonomous_ops`` in
the tenant's ``enabledFeatures`` (D-23), not ``tenant_features.switched_off``: a features list
holding "all" must not make an unticked tenant eligible.

Stop state is never cached. Level, maximum level and shadow are read on every call too (one
find_one each), so there is nothing to invalidate after a write through this module.
"""
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from . import DEFAULT_LEVEL, LEVEL_RANK, PLATFORM_TENANT_ID, SCREEN_PERMISSION
from .scope import raw

logger = logging.getLogger(__name__)

_MASTER_ENV = "AUTONOMOUS_REMEDIATION_DRY_RUN"
_PLATFORM_STOP_QUERY = {"type": "autonomous_ops"}


@dataclass
class TenantSettings:
    tenant_id: str
    level: str = DEFAULT_LEVEL
    max_level: str = DEFAULT_LEVEL
    shadow: bool = True
    stop: Optional[Dict[str, Any]] = None
    breaker: Optional[Dict[str, Any]] = None
    readable: bool = True      # False: a read failed or a stored value was not understood
    eligible: bool = False     # the Autonomous Ops screen is ticked for the tenant
    exists: bool = False       # an autonomy_settings document exists
    name: str = ""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_level(value) -> bool:
    return isinstance(value, str) and value in LEVEL_RANK


def _actor_name(actor) -> str:
    if isinstance(actor, dict):
        return str(actor.get("username") or actor.get("display") or "system")
    return str(actor or "system")


async def load(db, tenant_id: str) -> TenantSettings:
    """The tenant's settings and eligibility. A missing settings document reads as the
    default (Undoable-auto, shadow on); anything that cannot be read or understood sets
    ``readable`` False so the gate treats the tenant as Suggest (GATE-02, fail closed)."""
    s = TenantSettings(tenant_id=tenant_id)
    handle = raw(db)
    try:
        tenant = await handle.tenants.find_one({"id": tenant_id}, {"_id": 0, "name": 1, "enabledFeatures": 1})
    except Exception as exc:
        logger.warning("autonomous_ops: tenant %s could not be read: %s", tenant_id, exc)
        s.readable, s.eligible = False, True   # unknown eligibility: Suggest, not Off (D-23)
        return s
    features = (tenant or {}).get("enabledFeatures")
    s.eligible = isinstance(features, list) and SCREEN_PERMISSION in features
    s.name = str((tenant or {}).get("name") or "")
    try:
        doc = await handle.autonomy_settings.find_one({"tenantId": tenant_id}, {"_id": 0})
    except Exception as exc:
        logger.warning("autonomous_ops: settings for %s could not be read: %s", tenant_id, exc)
        s.readable = False
        return s
    if doc is None:
        return s
    s.exists = True
    s.level, s.max_level = doc.get("level"), doc.get("maxLevel")
    s.shadow = doc.get("shadow", True)
    s.stop = doc.get("stop") if isinstance(doc.get("stop"), dict) else None
    s.breaker = doc.get("breaker") if isinstance(doc.get("breaker"), dict) else None
    if not _is_level(s.level) or not _is_level(s.max_level) or not isinstance(s.shadow, bool):
        s.readable = False
        s.level = s.level if _is_level(s.level) else DEFAULT_LEVEL
        s.max_level = s.max_level if _is_level(s.max_level) else DEFAULT_LEVEL
        s.shadow = s.shadow if isinstance(s.shadow, bool) else True
    return s


def effective_level(s: TenantSettings) -> str:
    """"off" for the Platform tenant (D-04) and for a tenant that is not eligible (D-23);
    "suggest" when the settings cannot be read; otherwise the lower of level and maximum."""
    if s.tenant_id == PLATFORM_TENANT_ID or not s.eligible:
        return "off"
    if not s.readable:
        return "suggest"
    return min(s.level, s.max_level, key=LEVEL_RANK.__getitem__)


def master_shadow() -> bool:
    """The deployment-wide master (D-02): AUTONOMOUS_REMEDIATION_DRY_RUN, unset = true, read on
    every call. It can only force shadow on; it never raises a level."""
    return os.getenv(_MASTER_ENV, "true").strip().lower() in ("1", "true", "yes")


def shadow_state(s: TenantSettings, master: Optional[bool] = None) -> Tuple[bool, Optional[str]]:
    """(effective shadow, source): "deployment" when the master is on, else "tenant" when the
    tenant's own flag is on, else (False, None)."""
    if master is None:
        master = master_shadow()
    if master:
        return True, "deployment"
    if s.shadow:
        return True, "tenant"
    return False, None


def stop_active(stop: Optional[Dict[str, Any]]) -> bool:
    """A stop is on only when its ``active`` is literally True."""
    return isinstance(stop, dict) and stop.get("active") is True


async def platform_stop(db) -> Optional[Dict[str, Any]]:
    """The platform-wide stop document from system_settings, uncached. Errors propagate so the
    caller can treat an unreadable stop as stopped."""
    doc = await raw(db).system_settings.find_one(_PLATFORM_STOP_QUERY, {"_id": 0, "stop": 1})
    stop = (doc or {}).get("stop")
    return stop if isinstance(stop, dict) else None


async def ensure_tenant(db, tenant_id: str) -> None:
    """Create the tenant's settings document if it is missing (idempotent)."""
    level = "off" if tenant_id == PLATFORM_TENANT_ID else DEFAULT_LEVEL
    await raw(db).autonomy_settings.update_one(
        {"tenantId": tenant_id},
        {"$setOnInsert": {"tenantId": tenant_id, "level": level, "maxLevel": level, "shadow": True,
                          "stop": None, "breaker": None, "updatedAt": _now(), "updatedBy": "system"}},
        upsert=True)


async def ensure_all_tenants(db) -> int:
    """ensure_tenant for every tenant; returns how many were visited."""
    handle = raw(db)
    count = 0
    async for tenant in handle.tenants.find({}, {"_id": 0, "id": 1}):
        if tenant.get("id"):
            await ensure_tenant(db, tenant["id"])
            count += 1
    return count


async def update(db, tenant_id: str, fields: Dict[str, Any], *, actor) -> None:
    """Raw $set of ``fields`` plus updatedAt and updatedBy."""
    await raw(db).autonomy_settings.update_one(
        {"tenantId": tenant_id},
        {"$set": {**fields, "updatedAt": _now(), "updatedBy": _actor_name(actor)}})


async def set_level(db, tenant_id: str, level: str, *, actor) -> Dict[str, Any]:
    """Change a tenant's level. Refused above its maximum level, for the Platform tenant and
    for a value that is not a level. Setting Undoable-auto by hand also clears a tripped circuit
    breaker in the same update (so it can trip again) and records ``level_restored`` with the
    person as actor; ``breakerCleared`` is then True. Suggest and Off leave the breaker in place."""
    if not _is_level(level):
        return {"status": "invalid"}
    if tenant_id == PLATFORM_TENANT_ID:
        return {"status": "platform_tenant"}
    await ensure_tenant(db, tenant_id)
    s = await load(db, tenant_id)
    if LEVEL_RANK[level] > LEVEL_RANK[s.max_level]:
        return {"status": "above_max"}
    if level != "undoable_auto":
        await update(db, tenant_id, {"level": level}, actor=actor)
        return {"status": "ok"}
    from pymongo import ReturnDocument
    before = await raw(db).autonomy_settings.find_one_and_update(
        {"tenantId": tenant_id},
        {"$set": {"level": level, "breaker": None, "updatedAt": _now(), "updatedBy": _actor_name(actor)}},
        projection={"_id": 0, "breaker": 1}, return_document=ReturnDocument.BEFORE)
    if not isinstance((before or {}).get("breaker"), dict):
        return {"status": "ok"}
    from . import ledger, messages      # local: breaker imports this module too
    try:
        await ledger.record_control(db, tenant_id, "level_restored", scope="tenant",
                                    actor=actor if isinstance(actor, dict) else {"username": _actor_name(actor)},
                                    reason=messages.CONTROL_LABELS["level_restored"])
    except Exception as exc:
        logger.error("autonomous_ops: level restore for %s not recorded in the ledger: %s", tenant_id, exc)
    return {"status": "ok", "breakerCleared": True}


async def set_max_level(db, tenant_id: str, max_level: str, *, actor) -> Dict[str, str]:
    """Change a tenant's maximum level; the level is lowered when it is above the new maximum."""
    if not _is_level(max_level):
        return {"status": "invalid"}
    if tenant_id == PLATFORM_TENANT_ID:
        return {"status": "platform_tenant"}
    await ensure_tenant(db, tenant_id)
    s = await load(db, tenant_id)
    fields: Dict[str, Any] = {"maxLevel": max_level}
    if LEVEL_RANK[s.level] > LEVEL_RANK[max_level]:
        fields["level"] = max_level
    await update(db, tenant_id, fields, actor=actor)
    return {"status": "ok"}


async def set_shadow(db, tenant_id: str, shadow: bool, *, actor) -> Dict[str, str]:
    """Turn a tenant's own shadow flag on or off (a Super Admin decision, D-03)."""
    if not isinstance(shadow, bool):
        return {"status": "invalid"}
    await ensure_tenant(db, tenant_id)
    await update(db, tenant_id, {"shadow": shadow}, actor=actor)
    return {"status": "ok"}


async def ensure_indexes(db) -> None:
    """autonomy_settings: one document per tenant."""
    await raw(db).autonomy_settings.create_index("tenantId", unique=True, name="tenant_unique")
