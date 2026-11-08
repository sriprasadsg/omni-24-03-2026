"""How one service desk row reads in the Activity list (Phase 85, DESK-01).

Pure: no database, no clock of its own. ``response_views.row_extras`` hands a row whose dispatcher is the
service desk to ``row_extras`` here, before any security or rollout logic, and merges the result over the
empty extras. Only the keys that differ from the generic row are returned, plus the two ticket fields every
desk row carries. Every word comes from ``messages`` or from the row's own stored ``reasonText`` /
``activityResult``; nothing is imported from the service desk package.
"""
from datetime import datetime
from typing import Any, Dict, Optional

from . import messages

TEXT_CAP = 300       # the stored words are written by the desk, but a row is data: never trust it to be short
ID_CAP = 128
POSTED_PHASES = ("posted", "sent")      # Undo means something only while the answer is on the ticket


def _text(value: Any, cap: int) -> Optional[str]:
    return value.strip()[:cap] if isinstance(value, str) and value.strip() else None


def _can_undo(row: Dict[str, Any], desk: Dict[str, Any], can_act: bool) -> bool:
    """Only for a person who may act, an executed answer (not a simulation), marked undoable and still posted
    or sent: once the requester confirmed it, or a person took over, there is nothing sensible to withdraw."""
    return bool(can_act and row.get("state") == "executed" and not row.get("shadow")
                and desk.get("undoable") is True and desk.get("phase") in POSTED_PHASES)


def row_extras(row: Dict[str, Any], *, can_act: bool = False, now: Optional[datetime] = None) -> Dict[str, Any]:
    """The Activity fields of one desk row: its ticket, the draft label, the stored result and Undo."""
    desk = row.get("desk") if isinstance(row.get("desk"), dict) else {}
    out: Dict[str, Any] = {"ticketId": _text(desk.get("ticketId"), ID_CAP),
                           "ticketNumber": _text(desk.get("ticketNumber"), ID_CAP),
                           "suggestion": None, "incidentId": None, "canUndo": False, "undoHint": None}
    state = row.get("state")
    if state == "suggested" or (state == "shadow" and desk.get("phase") == "drafted"):
        out["actionLabel"] = messages.DESK_ACTION_LABELS["draft"]
    result = _text(row.get("activityResult"), TEXT_CAP)
    if result:
        out["resultText"] = result
    if _can_undo(row, desk, can_act):
        out["canUndo"] = True
        out["undoHint"] = messages.DESK_UNDO_HINT
    return out
