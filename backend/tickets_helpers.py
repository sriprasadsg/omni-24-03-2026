"""Pure helpers and constants shared across the tickets sub-package."""
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

# ── SLA defaults by priority (hours) ─────────────────────────────────────────
_SLA_HOURS: Dict[str, int] = {
    "critical": 4,
    "high":     8,
    "medium":   24,
    "low":      72,
}

# ── Allowed link types ────────────────────────────────────────────────────────
LINK_TYPES = {"blocks", "blocked_by", "relates_to", "duplicates", "duplicated_by", "clones"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sla_due(priority: str, sla_hours: Optional[int], created_at: str) -> str:
    """Calculate due date from creation time and SLA hours. Always returns UTC ISO string."""
    hours = sla_hours if sla_hours is not None else _SLA_HOURS.get(priority, 24)
    base = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return (base + timedelta(hours=hours)).isoformat()


def _compute_sla(ticket: Dict[str, Any]) -> Dict[str, Any]:
    """Inject computed sla_status into a ticket dict (does not persist)."""
    due = ticket.get("due_date")
    if not due:
        ticket["sla_status"] = "none"
        return ticket
    try:
        if isinstance(due, datetime):
            due_dt = due if due.tzinfo else due.replace(tzinfo=timezone.utc)
        else:
            due_str = str(due).replace("Z", "+00:00")
            due_dt = datetime.fromisoformat(due_str)
            if due_dt.tzinfo is None:
                due_dt = due_dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        ticket["sla_status"] = "none"
        return ticket

    now_dt = datetime.now(timezone.utc)

    # Adjust due date by accumulated hold duration (paused time does not count)
    hold_secs = ticket.get("total_hold_duration", 0) or 0
    hold_started_raw = ticket.get("hold_started_at")
    if hold_started_raw:
        try:
            hs = hold_started_raw if isinstance(hold_started_raw, datetime) else \
                datetime.fromisoformat(str(hold_started_raw).replace("Z", "+00:00"))
            if hs.tzinfo is None:
                hs = hs.replace(tzinfo=timezone.utc)
            hold_secs += (now_dt - hs).total_seconds()
        except (ValueError, TypeError):
            pass
    adjusted_due = due_dt + timedelta(seconds=hold_secs)

    if ticket.get("status") in ("resolved", "closed"):
        ticket["sla_status"] = "met"
    elif now_dt > adjusted_due:
        ticket["sla_status"] = "breached"
    elif (adjusted_due - now_dt).total_seconds() < 3600:
        ticket["sla_status"] = "at_risk"
    else:
        ticket["sla_status"] = "ok"
    ticket["sla_remaining_minutes"] = max(0, int((adjusted_due - now_dt).total_seconds() / 60))
    return ticket
