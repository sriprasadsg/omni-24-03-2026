"""What the sweep remembers about a decision, so the same finding is never decided twice (Phase 83, RESP-07).

``autonomy_signals.decision`` holds the last decision the sweep made for a signal: {actionId, at, outcome,
origins, blockedFrom?, blockedUntil?, holdUntil?}. ``skip_reason`` says whether that decision still holds
the finding quiet, from the ledger row it points at (its state is the truth, the memory only points):

* a decision still open (dispatching, approved, awaiting approval, suggested) holds it;
* a done action holds it until its block ran out (``blockedUntil``; no window recorded: 24 hours from
  the decision), and expiry changes nothing in the ledger (D-14);
* a simulation, a denied or an expired card and a refused row wait 24 hours, a failed row 1 hour, a row
  ended by a stop does not wait (the stop itself already kept the sweep away);
* a refused row is tried again at once when an origin appears that it was not decided on;
* an undone row holds nothing here: the 24 hour undo window is the sweep's separate check, and a refusal
  written for it carries ``holdUntil`` (the end of that window) which wins over the 24 hours of a refusal.

Raw Mongo handle with an explicit tenantId; the ambient tenant ContextVar is never used.
"""
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, Optional, Tuple

from . import OPEN_STATES, ledger

DAY = timedelta(hours=24)
WINDOWS: Dict[str, Optional[timedelta]] = {
    "shadow": DAY, "denied": DAY, "expired": DAY, "failed": timedelta(hours=1), "refused": DAY,
    "cancelled_by_stop": None}
_DONE = ("executed", "verified")


async def latest_state(db, tenant_id: str, decision: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The ledger row the memory points at, or None (no memory, or the row is gone)."""
    action_id = (decision or {}).get("actionId")
    return await ledger.get(db, tenant_id, action_id) if action_id else None


def block_window(decision: Optional[Dict[str, Any]], row: Optional[Dict[str, Any]]) -> Tuple[Optional[datetime], Optional[datetime]]:
    """(began, until) of the last block: the ledger row's window first, the memory's second; with no window
    recorded at all, 24 hours from the decision (the default length)."""
    decision = decision or {}
    began = (row or {}).get("blockedFrom") or decision.get("blockedFrom")
    until = (row or {}).get("blockedUntil") or decision.get("blockedUntil")
    if not isinstance(until, datetime) and isinstance(decision.get("at"), datetime):
        until = decision["at"] + DAY
    return (began if isinstance(began, datetime) else None), (until if isinstance(until, datetime) else None)


def skip_reason(decision: Optional[Dict[str, Any]], row: Optional[Dict[str, Any]], origins: Iterable[str],
                now: datetime) -> Optional[str]:
    """A short code when the remembered decision still holds this finding quiet, else None."""
    if not isinstance(decision, dict) or not decision:
        return None
    state = row.get("state") if isinstance(row, dict) else None
    outcome = decision.get("outcome")
    if state in OPEN_STATES:
        return "open"
    if state in _DONE or (state is None and outcome == "blocked"):
        _, until = block_window(decision, row)
        return "block_holds" if until is not None and now < until else None
    hold = decision.get("holdUntil")
    if isinstance(hold, datetime):
        return "undo_hold" if now < hold else None
    kind = state or outcome
    window = WINDOWS.get(kind)
    if window is None:
        return None
    if kind == "refused" and not set(origins) <= set(decision.get("origins") or ()):
        return None                                                  # a source the refusal was not decided on
    finished = row.get("finishedAt") if isinstance(row, dict) else None
    start = finished if isinstance(finished, datetime) else decision.get("at")
    return kind if isinstance(start, datetime) and now < start + window else None
