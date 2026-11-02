"""The Autonomous Ops sweep (Phase 83, RESP-01): the loop that finds things worth acting on by itself.

Each tick walks the tenants that have the Autonomous Ops screen ticked (never the Platform tenant), in
sorted order. For a tenant that is neither stopped nor Off it runs every stage in ``_STAGES`` inside
``scope.tenant_scope``; a stage that fails is logged and does not stop the next tenant. Stages decide
nothing themselves: they build a request and hand it to ``gate.decide``, which owns every limit, stop
and shadow rule.

A stage has the signature ``run(db, tenant_id, tenant, response, now) -> Dict[str, int]`` where
``tenant`` is ``settings.TenantSettings`` and ``response`` is ``response_settings.ResponseSettings``.

One runner at a time: ``run_once`` holds ``distributed_lock.lock_with_renewal`` on ``autonomous_ops_sweep``
(a second runner gets None) and a tick stops between tenants when the lock reports lost. A crash between
deciding and sending leaves a ``dispatching`` row with no instruction, which the reconciler ends as
``not_delivered`` after its stuck-dispatch bound.

The platform-wide stop is read once per tick; if it cannot be read the whole pass does nothing (fail
closed). The sweep calls no model and reads no free text (PROH-83-01).

Importing this module also registers the ``security_response`` dispatcher with ``approvals``, so an
approval card of that dispatcher can be sent by the same process.

Raw Mongo handle with an explicit tenantId; the ambient tenant ContextVar is never set outside
``scope.tenant_scope``.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Callable, Dict, Optional

from . import (PLATFORM_TENANT_ID, SCREEN_PERMISSION, response_settings, scope, settings, sweep_restart,
               sweep_security, sweep_suggestions)
from .scope import raw

logger = logging.getLogger(__name__)

LOCK_NAME = "autonomous_ops_sweep"
LOCK_TTL_SECONDS = 120
LOCK_RENEW_EVERY = 30
_DEFAULT_INTERVAL_SEC = 60

_STAGES = (sweep_security.run, sweep_suggestions.run, sweep_restart.run)


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



# ---------------------------------------------------------------- one runner, and the loop

def _env_number(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, default))
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


def _interval() -> float:
    return _env_number("AUTONOMOUS_OPS_SWEEP_INTERVAL_SEC", _DEFAULT_INTERVAL_SEC)


async def run_once(db, *, now: Optional[datetime] = None) -> Optional[Dict[str, int]]:
    """One tick under the single-runner lock; None when another runner holds it."""
    import distributed_lock
    lock_db = SimpleNamespace(_db=raw(db))        # distributed_lock reads db._db
    async with distributed_lock.lock_with_renewal(lock_db, LOCK_NAME, ttl_seconds=LOCK_TTL_SECONDS,
                                                  renew_every=LOCK_RENEW_EVERY) as handle:
        if not handle.acquired:
            return None
        return await tick(db, now=now, lost=lambda: handle.lost)


async def sweep_loop() -> None:
    """Run a tick every AUTONOMOUS_OPS_SWEEP_INTERVAL_SEC. A failing pass is logged and the loop goes on."""
    from database import get_database
    while True:
        try:
            counts = await run_once(get_database())
            if counts and any(v for k, v in counts.items() if k != "tenants"):
                logger.info("autonomous_ops: sweep pass %s", counts)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("autonomous_ops: sweep pass failed: %s", exc)
        await asyncio.sleep(_interval())
