"""The rollout controller tick (Phase 84): one pass over every tenant with an active rollout.

Each pass settles agent results first (also while a stop is on, so what the computers already did is
never lost), then moves each running rollout one step: waits for a maintenance window, sends the
canary installs, and later soaks and checks. It never writes an agent queue and never calls
``gate.decide`` while a stop is on or the tenant is Off (a stopped ``decide`` records a refused row on
every call). Plan 84-22 puts the locked background loop around ``tick``.

Raw Mongo handle with an explicit tenantId; ``scope.tenant_scope`` only wraps each tenant's pass.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .. import PLATFORM_TENANT_ID, scope, settings
from . import ACTIVE_STATUSES, installs, settle, store, windows as windows_mod

logger = logging.getLogger(__name__)


def _now(now: Optional[datetime]) -> datetime:
    now = now or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)       # BSON datetimes are milliseconds


async def _may_decide(db, tenant_id: str, platform_stopped: bool) -> bool:
    """True when new decisions may be made for the tenant: no platform or tenant stop and not Off."""
    if platform_stopped:
        return False
    tenant = await settings.load(db, tenant_id)
    return not settings.stop_active(tenant.stop) and settings.effective_level(tenant) != "off"


async def _ring(db, tenant_id: str, rollout: Dict[str, Any], now: datetime, counts: Dict[str, int]) -> None:
    """Move the current ring one step."""
    index = int(rollout.get("currentRing") or 0)
    ring = rollout["rings"][index]
    hosts = [h for h in await store.host_docs(db, tenant_id, rollout["id"]) if h.get("ring") == index]
    waiting = [h for h in hosts if h.get("state") == "waiting"]
    if not waiting:
        return
    tenant_windows = await windows_mod.load(db, tenant_id)
    open_now = tenant_windows.open_at(now)
    if open_now is None:
        if ring.get("state") != "waiting_for_window":
            await store.set_ring(db, tenant_id, rollout, index, {"state": "waiting_for_window"})
        counts["waiting_for_window"] = counts.get("waiting_for_window", 0) + 1
        return
    if ring.get("state") != "installing":
        await store.set_ring(db, tenant_id, rollout, index, {"state": "installing"})
    if index == 0:         # later rings wait for a person (plan 84-03)
        for key, value in (await installs.canary_auto(db, tenant_id, rollout, index, hosts, now, open_now[1])).items():
            counts[key] = counts.get(key, 0) + value


async def _tenant(db, tenant_id: str, now: datetime, platform_stopped: bool, counts: Dict[str, int]) -> None:
    decide = await _may_decide(db, tenant_id, platform_stopped)
    with scope.tenant_scope(tenant_id):
        for rollout in await store.active_rollouts(db, tenant_id, ACTIVE_STATUSES):
            await settle.settle(db, tenant_id, rollout, now)
            if decide and rollout.get("status") == "running":
                await _ring(db, tenant_id, rollout, now, counts)


async def tick(db, *, now: Optional[datetime] = None, lost: Optional[Callable[[], bool]] = None) -> Dict[str, int]:
    """One pass over every tenant with an active rollout, in sorted order. Returns summed counts plus
    ``tenants``. ``lost`` (the lock reports it was lost) is polled between tenants."""
    now = _now(now)
    counts: Dict[str, int] = {"tenants": 0}
    try:
        platform_stopped = settings.stop_active(await settings.platform_stop(db))
    except Exception as exc:
        logger.error("autonomous_ops: rollout tick could not read the platform stop, only settling: %s", exc)
        platform_stopped = True
    tenants: List[str] = [t for t in await store.tenants_with_rollouts(db, ACTIVE_STATUSES) if t != PLATFORM_TENANT_ID]
    for tenant_id in tenants:
        counts["tenants"] += 1
        await _tenant(db, tenant_id, now, platform_stopped, counts)
    return counts
