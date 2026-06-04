"""Background service: auto-escalate tickets at SLA thresholds."""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from tickets_helpers import _compute_sla, _now

logger = logging.getLogger(__name__)

_PRIORITY_LADDER = ["low", "medium", "high", "critical"]


def _bump_priority(current: str) -> str:
    """Return the next higher priority, capped at critical."""
    try:
        idx = _PRIORITY_LADDER.index(current)
    except ValueError:
        idx = 0
    return _PRIORITY_LADDER[min(idx + 1, len(_PRIORITY_LADDER) - 1)]


def _history_entry(action: str, changes: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id":         str(uuid.uuid4()),
        "actor":      "system:escalation",
        "action":     action,
        "changes":    changes,
        "created_at": _now(),
    }


async def run_escalation_pass(db: Any) -> None:
    """Scan open tickets and apply escalation rules based on SLA status."""
    query = {
        "status":    {"$in": ["open", "in_progress"]},
        "escalated": False,
    }
    try:
        cursor = db.tickets.find(query, {"_id": 0})
        async for ticket in cursor:
            _compute_sla(ticket)
            sla_status     = ticket.get("sla_status", "ok")
            priority       = ticket.get("priority", "low")
            ticket_id      = ticket.get("id")
            escalation_lvl = ticket.get("escalation_level", 0) or 0

            if not ticket_id:
                continue

            updates: Dict[str, Any] = {}
            history_entry = None

            if sla_status == "breached" and priority != "critical":
                new_priority = _bump_priority(priority)
                updates = {
                    "priority":        new_priority,
                    "escalated":       True,
                    "escalated_at":    _now(),
                    "escalation_level": escalation_lvl + 1,
                    "updated_at":      _now(),
                }
                history_entry = _history_entry(
                    "auto_escalated",
                    {
                        "reason":   "SLA breached",
                        "priority": {"from": priority, "to": new_priority},
                    },
                )
            elif sla_status == "at_risk" and escalation_lvl == 0:
                updates = {
                    "escalation_level": 1,
                    "updated_at":       _now(),
                }
                history_entry = _history_entry(
                    "auto_escalated",
                    {"reason": "SLA at risk — auto-escalated to level 1"},
                )

            if updates:
                op: Dict[str, Any] = {"$set": updates}
                if history_entry:
                    op["$push"] = {"history": history_entry}
                await db.tickets.update_one({"id": ticket_id}, op)
                logger.info(
                    "Escalated ticket %s: sla_status=%s updates=%s",
                    ticket_id, sla_status, list(updates.keys()),
                )
    except Exception as exc:
        logger.error("Escalation pass failed: %s", exc)


async def start_escalation_scheduler(db: Any) -> None:
    """Loop every 5 minutes running the escalation pass."""
    logger.info("Escalation scheduler started (interval=300s)")
    while True:
        await run_escalation_pass(db)
        await asyncio.sleep(300)
