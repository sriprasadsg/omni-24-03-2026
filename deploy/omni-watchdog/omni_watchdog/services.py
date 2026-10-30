"""Per-service state and the D-06 debounce.

A service is ``checking`` after 1 failed check and ``down`` only after 2 failed checks in a row.
One passing check resets ``failedChecks`` to 0 and returns it to ``healthy``, with a
``service_recovered`` event when it had been checking or down. Timestamps are epoch seconds.
Ollama is not debounced: its detail says whether it is off as expected or running unexpectedly.

The restart plan (restart.py, 82-03) owns the ``restarting`` and ``gave_up`` states and the extra
fields it keeps in each service entry (``restarts``, ``nextActionAt``, ``healthySince``, ``gaveUp``,
``rearmPending``, ``skipped``, plus the reported restartsInWindow, nextRestartAt, budgetReturnsAt,
pagedAt, waitingOn). ``observe`` carries all of them over untouched.
"""
from datetime import datetime, timezone

from . import SERVICE_ORDER  # noqa: F401  (re-exported for callers that iterate in order)
from .state import new_event_id

DOWN_AFTER = 2
_RECOVERS_FROM = ("checking", "down", "restarting", "gave_up")
_RECOMPUTED = ("state", "failedChecks", "detail", "since")


def iso(epoch):
    """Epoch seconds as an ISO-8601 UTC string, or None."""
    if epoch is None:
        return None
    return datetime.fromtimestamp(float(epoch), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_event(kind, severity, target, now, params=None):
    """A new event with its id generated once; the id is what makes a re-send idempotent."""
    return {"id": new_event_id(), "at": iso(now), "kind": kind, "severity": severity,
            "target": target, "params": dict(params or {})}


def observe(service_state, ok, detail, now, target=None):
    """Apply one check result. Returns (new service state, [events]); the input is not modified."""
    prev = dict(service_state or {})
    prev_state = prev.get("state")
    new = {"restartsInWindow": 0, "nextRestartAt": None, "budgetReturnsAt": None, "pagedAt": None,
           "waitingOn": None}
    new.update({k: v for k, v in prev.items() if k not in _RECOMPUTED})
    if isinstance(new.get("restarts"), list):
        new["restarts"] = list(new["restarts"])          # never share a list with the input
    events = []

    if detail in ("expected_off", "unexpected_running"):
        state, failed = detail, 0
        if state == "unexpected_running" and prev_state != "unexpected_running":
            events.append(make_event("unexpected_running", "warning", target, now))
    elif ok:
        state, failed = "healthy", 0
        if prev_state in _RECOVERS_FROM:
            events.append(make_event("service_recovered", "info", target, now))
    else:
        failed = int(prev.get("failedChecks") or 0) + 1
        if prev_state in ("restarting", "gave_up") and failed >= DOWN_AFTER:
            state = prev_state          # the restart plan (82-03) owns these states
        else:
            state = "checking" if failed < DOWN_AFTER else "down"
        if state == "down" and prev_state != "down":
            events.append(make_event("service_down", "critical", target, now))

    new["state"] = state
    new["failedChecks"] = failed
    new["detail"] = detail or ""
    new["since"] = prev.get("since") if state == prev_state and prev.get("since") is not None else now
    return new, events
