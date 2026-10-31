"""The Autonomous Ops sweep (Phase 83, RESP-01): the loop that finds things worth acting on by itself.

Each tick walks the tenants that have the Autonomous Ops screen ticked (never the Platform tenant), in
sorted order. For a tenant that is neither stopped nor Off it runs every stage in ``_STAGES`` inside
``scope.tenant_scope``; a stage that fails is logged and does not stop the next tenant. Stages decide
nothing themselves: they build a request and hand it to ``gate.decide``, which owns every limit, stop
and shadow rule.

A stage has the signature ``run(db, tenant_id, tenant, response, now) -> Dict[str, int]`` where
``tenant`` is ``settings.TenantSettings`` and ``response`` is ``response_settings.ResponseSettings``.

The platform-wide stop is read once per tick; if it cannot be read the whole pass does nothing (fail
closed). The sweep calls no model and reads no free text (PROH-83-01).

Importing this module also registers the ``security_response`` dispatcher with ``approvals``, so an
approval card of that dispatcher can be sent by the same process.

Raw Mongo handle with an explicit tenantId; the ambient tenant ContextVar is never set outside
``scope.tenant_scope``.
"""
import logging
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

from . import PLATFORM_TENANT_ID, SCREEN_PERMISSION, response_settings, scope, settings, sweep_security
from .scope import raw

logger = logging.getLogger(__name__)

_STAGES = (sweep_security.run,)


def _now(now: Optional[datetime]) -> datetime:
    now = now or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)   # BSON datetimes are milliseconds


async def _ticked_tenants(db) -> list:
    found = raw(db).tenants.find({"enabledFeatures": SCREEN_PERMISSION}, {"_id": 0, "id": 1})
    return sorted({t["id"] async for t in found if isinstance(t.get("id"), str) and t["id"]} - {PLATFORM_TENANT_ID})


async def tick(db, *, now: Optional[datetime] = None, lost: Optional[Callable[[], bool]] = None) -> Dict[str, int]:
    """One pass over every ticked tenant. Returns the summed stage counts plus ``tenants`` (how many
    ran). ``lost`` is polled between tenants; when it returns True the pass stops (the lock was lost)."""
    now = _now(now)
    counts: Dict[str, int] = {"tenants": 0}
    try:
        if settings.stop_active(await settings.platform_stop(db)):
            return counts
    except Exception as exc:
        logger.error("autonomous_ops: sweep could not read the platform stop, doing nothing: %s", exc)
        return counts
    for tenant_id in await _ticked_tenants(db):
        if lost is not None and lost():
            logger.warning("autonomous_ops: sweep lost its lock, stopping this pass")
            break
        try:
            tenant = await settings.load(db, tenant_id)
            if settings.stop_active(tenant.stop) or settings.effective_level(tenant) == "off":
                continue
            response = await response_settings.load(db, tenant_id)
            counts["tenants"] += 1
            with scope.tenant_scope(tenant_id):
                for stage in _STAGES:
                    for key, value in (await stage(db, tenant_id, tenant, response, now)).items():
                        counts[key] = counts.get(key, 0) + value
        except Exception as exc:
            logger.error("autonomous_ops: sweep failed for tenant %s: %s", tenant_id, exc)
    return counts

