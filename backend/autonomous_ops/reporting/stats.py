"""Statistics and time saved over the decision ledger (Phase 86, ACTV-05, ACTV-07, D-05..D-08, D-19).

One aggregation per request over ``autonomy_actions`` for one tenant. Control and platform health rows
are never counted. A simulation (shadow) row adds to ``wouldHaveDone`` only: it is never a real decision,
never a real total and never adds minutes. Time saved is a fixed estimate per kind of action
(``MINUTES_PER_KIND``) over actions that really ran (executed or verified).

Read only. The raw handle and an explicit tenantId are used; the ambient tenant context is never read.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from autonomous_ops import messages, views
from autonomous_ops import settings as ao_settings
from autonomous_ops.scope import raw

from . import (DEFAULT_WINDOW, DONE_STATES, EXCLUDED_KINDS, MINUTES_PER_KIND, REFUSED_STATES, SHADOW_STATE,
               UNDONE_STATES)
from .rule_names import rule_name

UNKNOWN_RULE = "gate:unknown"
HANDOFF_LABEL = "Hand a ticket to a person"
_COLUMNS = ("fired", "done", "approved", "denied", "undone", "failed", "refused", "wouldHaveDone")


def _zero() -> Dict[str, int]:
    return {column: 0 for column in _COLUMNS}


async def compute(db, tenant_id: str, *, days: Optional[int], now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Grouped counts for one tenant: [{rule, cmd, state, approved, n}]. ``days`` None means all time."""
    match: Dict[str, Any] = {"tenantId": tenant_id, "kind": {"$nin": list(EXCLUDED_KINDS)}}
    if days is not None:
        since = (now or datetime.now(timezone.utc)) - timedelta(days=days)
        match["createdAt"] = {"$gte": since}
    pipeline = [
        {"$match": match},
        {"$group": {"_id": {"rule": "$reason.ruleId", "cmd": "$command", "state": "$state",
                            "approved": {"$ne": [{"$ifNull": ["$approval.approver", None]}, None]}},
                    "n": {"$sum": 1}}},
    ]
    groups: List[Dict[str, Any]] = []
    async for doc in raw(db).autonomy_actions.aggregate(pipeline):
        key = doc["_id"]
        groups.append({"rule": key.get("rule") or UNKNOWN_RULE, "cmd": key.get("cmd"), "state": key.get("state"),
                       "approved": bool(key.get("approved")), "n": int(doc["n"])})
    return groups


def fold(groups) -> Dict[str, Any]:
    """Per-rule rows and totals from grouped counts (D-07 column map)."""
    per_rule: Dict[str, Dict[str, int]] = {}
    totals = _zero()
    for group in groups:
        row = per_rule.setdefault(group["rule"], _zero())
        n, state = group["n"], group["state"]
        if state == SHADOW_STATE:
            row["wouldHaveDone"] += n
            totals["wouldHaveDone"] += n
            continue
        columns = ["fired"]
        if state in DONE_STATES:
            columns.append("done")
        if state in UNDONE_STATES:
            columns.append("undone")
        if state in REFUSED_STATES:
            columns.append("refused")
        if state == "denied":
            columns.append("denied")      # approvals.deny records the approver too, so approved excludes it
        if state == "failed":
            columns.append("failed")
        if group.get("approved") and state != "denied":
            columns.append("approved")
        for column in columns:
            row[column] += n
            totals[column] += n
    rules = [{"id": rule_id, "name": rule_name(rule_id), **counts} for rule_id, counts in per_rule.items()]
    rules.sort(key=lambda r: (-r["fired"], r["name"], r["id"]))
    return {"rules": rules, "totals": totals}


def _label(kind: str) -> str:
    if kind == "ticket_handoff":
        return HANDOFF_LABEL
    return messages.ACTION_LABELS.get(kind) or kind.replace("_", " ").capitalize()


def time_saved(groups) -> Dict[str, Any]:
    """The estimate: minutes per kind for executed or verified rows only. Commands outside the table count 0."""
    counted: Dict[str, int] = {}
    for group in groups:
        if group["state"] in DONE_STATES:
            counted[group["cmd"]] = counted.get(group["cmd"], 0) + group["n"]
    per_kind = [{"kind": kind, "label": _label(kind), "counted": counted.get(kind, 0), "minutesEach": each,
                 "subtotal": counted.get(kind, 0) * each} for kind, each in MINUTES_PER_KIND.items()]
    return {"minutes": sum(item["subtotal"] for item in per_kind), "estimate": True, "perKind": per_kind}


def format_minutes(minutes: int) -> str:
    """The R16 wording: "0 min", "About 45 min", "About 5 h 40 min", "About 2 h" (rounded to 5 minutes from 1 h)."""
    minutes = int(minutes)
    if minutes <= 0:
        return "0 min"
    if minutes < 60:
        return f"About {minutes} min"
    rounded = 5 * ((minutes + 2) // 5)
    hours, rest = divmod(rounded, 60)
    return f"About {hours} h" if rest == 0 else f"About {hours} h {rest} min"


async def statistics_payload(db, caller, tenant_id: str, days: int = DEFAULT_WINDOW,
                             now: Optional[datetime] = None) -> Dict[str, Any]:
    """The statistics route's answer for one tenant."""
    groups = await compute(db, tenant_id, days=days, now=now)
    folded = fold(groups)
    shadow_only, _ = ao_settings.shadow_state(await ao_settings.load(db, tenant_id))
    can_export = await views.holds(caller.user, "export:reports") and await views.holds(caller.user, "view:autonomous_ops")
    return {"tenantId": tenant_id, "days": days, "generatedAt": (now or datetime.now(timezone.utc)).isoformat(),
            "shadowOnly": bool(shadow_only), "canExport": bool(can_export),
            "rules": folded["rules"], "totals": folded["totals"], "timeSaved": time_saved(groups)}
