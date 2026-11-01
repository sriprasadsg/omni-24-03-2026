"""The circuit breaker (GATE-14, D-18).

When a tenant's three most recently finished automatic actions all ended failed, rolled_back
or undone, and the oldest of the three finished within 24 hours, the tenant drops to Suggest
(its stored level becomes ``suggest``; the previous level is kept in ``breaker``). Simulation
rows, control rows and rows a person approved never count: only ``autoDispatched`` rows do.

Only real failures lower a level (Phase 83, RESP-10, PROH-83-11). A row counts when it ended undone or
rolled_back, or failed with no reason (Phase 81) or with ``verify_failed``, ``agent_failed`` or
``blocked_by_local_security`` (``ledger.BREAKER_FAILURES``). A row that ended for the reasons in
``ledger.BREAKER_IGNORED`` (an instruction never delivered or never answered, a capability not ticked, an
unsupported or offline agent, a file that no longer matches, is in use or is protected, a refused target) is
transparent: it is not counted and it does not break a run of three, because plumbing must never cost a
tenant its automatic level.

The breaker NEVER re-arms itself: nothing time-driven calls ``restore``. Only a person holding
``manage:autonomous_ops`` (checked by the route in plan 81-09) restores the previous level,
capped at the tenant's maximum level.

Trip and restore are compare-and-set updates of the tenant's settings document, so concurrent
evaluations (an undo click and the reconciler) trip it once and notify once.

Raw Mongo handle with an explicit tenantId everywhere; the ambient tenant ContextVar is never
used.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from . import BREAKER_THRESHOLD, BREAKER_WINDOW, LEVEL_RANK, ledger, messages, notify, settings
from .scope import raw

logger = logging.getLogger(__name__)

_BAD_STATES = ("failed", "rolled_back", "undone")
_SYSTEM = {"username": "autonomous_ops", "display": "Autonomous Ops", "tier": "system"}


def _now(now: Optional[datetime]) -> datetime:
    now = now or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


async def evaluate(db, tenant_id: str, *, now: Optional[datetime] = None) -> bool:
    """Trip the breaker when the last three automatic actions went wrong. True when THIS call
    tripped it. A tenant that is already tripped, not Undoable-auto, or unreadable is left alone."""
    now = _now(now)
    s = await settings.load(db, tenant_id)
    if not s.exists or not s.readable or s.breaker is not None or s.level != "undoable_auto":
        return False
    rows = await ledger.recent_finished_auto(db, tenant_id, n=BREAKER_THRESHOLD)
    if len(rows) < BREAKER_THRESHOLD or any(r.get("state") not in _BAD_STATES for r in rows):
        return False
    oldest = min(r["finishedAt"] for r in rows)
    if now - oldest > BREAKER_WINDOW:
        return False

    breaker = {"trippedAt": now, "previousLevel": s.level, "actionIds": [r["id"] for r in rows]}
    won = await raw(db).autonomy_settings.update_one(
        {"tenantId": tenant_id, "level": s.level, "breaker": None},
        {"$set": {"level": "suggest", "breaker": breaker, "updatedAt": now, "updatedBy": "system"}})
    if won.modified_count != 1:
        return False                                  # another evaluation tripped it first
    try:
        await ledger.record_control(db, tenant_id, "breaker_tripped", scope="tenant", actor=_SYSTEM,
                                    reason=messages.CONTROL_LABELS["breaker_tripped"])
    except Exception as exc:                          # the level is already lowered; say so in the log
        logger.error("autonomous_ops: breaker trip for %s not recorded in the ledger: %s", tenant_id, exc)
    title, text = messages.NOTICES["breaker_tripped"]
    await notify.notify(db, tenant_id, title=title, message=text.format(tenant=s.name or tenant_id),
                        metadata={"event": "breaker_tripped", "tenantId": tenant_id,
                                  "actionIds": breaker["actionIds"]})
    return True


async def restore(db, tenant_id: str, *, actor: Dict[str, Any]) -> Dict[str, str]:
    """Put the level back after a trip (a person's decision; never called by any loop). The
    level is capped at the tenant's maximum level."""
    s = await settings.load(db, tenant_id)
    if s.breaker is None:
        return {"status": "not_tripped", "level": s.level}
    previous = s.breaker.get("previousLevel")
    if previous not in LEVEL_RANK:
        previous = "suggest"
    level = min(previous, s.max_level, key=LEVEL_RANK.__getitem__)
    won = await raw(db).autonomy_settings.update_one(
        {"tenantId": tenant_id, "breaker": {"$ne": None}},
        {"$set": {"level": level, "breaker": None, "updatedAt": _now(None),
                  "updatedBy": str(actor.get("username") or actor.get("display") or "system")}})
    if won.modified_count != 1:
        return {"status": "not_tripped", "level": s.level}
    try:
        await ledger.record_control(db, tenant_id, "level_restored", scope="tenant", actor=actor,
                                    reason=messages.CONTROL_LABELS["level_restored"])
    except Exception as exc:
        logger.error("autonomous_ops: level restore for %s not recorded in the ledger: %s", tenant_id, exc)
    return {"status": "restored", "level": level}
