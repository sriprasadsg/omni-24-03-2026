"""What each Phase 83 Activity row says and whether it may be undone (ACTV-02, RESP-02, RESP-03, RESP-08).

``row_extras`` is pure: it reads one ledger row and returns the extra fields the Activity list needs, so
the browser never works out wording or permission itself. Keys always present: ``canUndo``,
``undoHint``, ``incidentId``, ``blockedUntil``, ``suggestion``. Keys present only when the row calls
for them: ``actionLabel``, ``classLine``, ``reasonText``, ``resultText`` (they replace what
``views.present_row`` built). Nothing here changes a row's state, chip or ledger entry.

Wording comes from ``response_messages`` and is rendered from ``reason.inputs`` (origins, twoSignal,
suggestion, attempt, service) so a refreshed row never shows stale words. A row with no inputs keeps its
stored text. ``canUndo`` is display only (T-83-10): ``approvals.undo`` and the route's permission check
remain the guard. Every string is plain text; the browser renders it as text (T-83-09).

Row fields read, besides the ledger's own: ``blockedFrom`` / ``blockedUntil`` (block window),
``result.healthy_after`` and ``result.still_running`` (the agent's own verify result, stored bounded),
``reason.inputs`` keys ``origins``, ``twoSignal``, ``suggestion``, ``suggestionOnly``, ``incidentId``,
``service``, ``attempt``, ``overBudget``, ``protectedPath``, ``detail`` and ``undoneAt``.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import dispatch_check, registry, response_messages as rm

ITEM_CAP = 10                # D-07: a grouped row lists at most this many items
TEXT_CAP = 300               # one item's text; agent-reported text is never trusted to be short
ID_CAP = 128
UNDOABLE_STATES = ("executed", "verified")
SECURITY_DISPATCHER = "security_response"
SUGGESTION_KINDS = ("single_signal", "vulnerability", "file_change", "correlation")
_ITEM_KEYS = {"vulnerability": ("cve", "package"), "file_change": ("path",)}

EMPTY_EXTRAS: Dict[str, Any] = {"canUndo": False, "undoHint": None, "incidentId": None, "blockedUntil": None,
                                "suggestion": None}


def _aware(value: Any) -> Optional[datetime]:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _text(value: Any) -> Optional[str]:
    return value.strip()[:TEXT_CAP] if isinstance(value, str) and value.strip() else None


def _int(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _path_of(row: Dict[str, Any]) -> Optional[str]:
    params = _dict(row.get("params"))
    return _text(params.get("path")) or _text(params.get("file_path")) or _text(row.get("target"))


def _ip_of(row: Dict[str, Any]) -> Optional[str]:
    params = _dict(row.get("params"))
    return _text(params.get("ip_address")) or _text(params.get("ip")) or _text(row.get("target"))


# ---------------------------------------------------------------- suggestions

def _suggestion(inputs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The grouped-suggestion payload {kind, count, items (at most 10), openView}, else None."""
    raw = inputs.get("suggestion")
    if not isinstance(raw, dict) or raw.get("kind") not in SUGGESTION_KINDS:
        return None
    kind = raw["kind"]
    items: List[Dict[str, str]] = []
    keys = _ITEM_KEYS.get(kind, ())
    for entry in raw.get("items") if isinstance(raw.get("items"), list) else []:
        if isinstance(entry, dict):
            item = {k: _text(entry.get(k)) for k in keys if _text(entry.get(k))}
            if item:
                items.append(item)           # type: ignore[arg-type]
        if len(items) >= ITEM_CAP:
            break
    count = _int(raw.get("count"))
    if count is None:
        count = len(items) if kind in _ITEM_KEYS else 1
    return {"kind": kind, "count": count, "items": items, "openView": rm.SUGGESTION_VIEWS.get(kind)}


def _suggestion_words(row: Dict[str, Any], inputs: Dict[str, Any], view: Dict[str, Any],
                      host: Optional[str]) -> Dict[str, str]:
    kind, raw = view["kind"], _dict(inputs.get("suggestion"))
    words: Dict[str, str] = {"classLine": rm.SUGGESTION_CLASS_LINE}
    label = rm.SUGGESTION_LABELS.get(kind if kind in _ITEM_KEYS else row.get("command"))
    if label:
        words["actionLabel"] = label
    if kind == "vulnerability":
        words["reasonText"] = rm.why_vulnerabilities(view["count"], host or "this computer",
                                                      _text(raw.get("severity")) or "unknown")
        words["resultText"] = rm.RESULT_TEMPLATES["suggestion_vulnerability"]
    elif kind == "file_change":
        words["reasonText"] = rm.why_file_changes(view["count"], host or "this computer")
        words["resultText"] = rm.RESULT_TEMPLATES["suggestion_file_change"]
    elif kind == "correlation":
        rule = _text(raw.get("rule"))
        if rule:
            words["reasonText"] = rm.fill(rm.WHY_TEMPLATES["correlation"], rule=rule)
        words["resultText"] = rm.RESULT_TEMPLATES["suggestion_correlation"]
    else:
        origins = inputs.get("origins") if isinstance(inputs.get("origins"), list) else []
        try:
            words["reasonText"] = rm.why_one_source(sorted(set(origins), key=str)[0])
        except (KeyError, IndexError, TypeError):
            pass                                   # an unknown or missing origin is never shown raw
        words["resultText"] = rm.RESULT_TEMPLATES["suggestion_one_source"]
    return words


# ---------------------------------------------------------------- reasons and results

def _origin_reason(inputs: Dict[str, Any]) -> Optional[str]:
    origins = inputs.get("origins")
    if not isinstance(origins, list) or not origins:
        return None
    try:
        if len(set(origins)) >= 2:
            return rm.why_two_sources(origins)
        if inputs.get("twoSignal") is False:
            return rm.why_rule_off(origins[0])
    except (KeyError, ValueError, TypeError):
        return None                                # never claim two sources, never show a raw id
    return None


def _reason_text(row: Dict[str, Any], inputs: Dict[str, Any]) -> Optional[str]:
    command, code = row.get("command"), row.get("reasonCode")
    if code == "suppressed_by_undo" and inputs.get("undoneAt"):
        when = rm.short_date(inputs["undoneAt"])
        return rm.fill(rm.WHY_TEMPLATES["undone_earlier"], date=when) if when else None
    service = _text(inputs.get("service"))
    if command == "restart_service" and service:
        key = "restart_over_budget" if inputs.get("overBudget") else "restart_watched"
        return rm.fill(rm.WHY_TEMPLATES[key], service=service)
    if command == "quarantine_file" and (inputs.get("protectedPath") or code == "protected_path"):
        return rm.fill(rm.WHY_TEMPLATES["protected_file"], reason=_text(inputs.get("detail")) or "").strip()
    if command in ("block_ip", "quarantine_file"):
        return _origin_reason(inputs)
    return None


def _block_result(row: Dict[str, Any], until: Optional[datetime], now: datetime) -> Optional[str]:
    state = row.get("state")
    if state == "failed" and row.get("reasonCode") == "verify_failed":
        return rm.RESULT_TEMPLATES["block_check_failed"]
    if state not in UNDOABLE_STATES or until is None:
        return None
    if until <= now:
        return rm.RESULT_TEMPLATES["block_expired"]       # {at} is filled by the browser, in the viewer's time
    if state != "verified":
        return None
    ttl = _int(_dict(row.get("params")).get("ttl_seconds"))
    began = _aware(row.get("blockedFrom"))
    seconds = ttl if ttl else int((until - began).total_seconds()) if began else None
    if not seconds:
        return None
    return rm.fill(rm.RESULT_TEMPLATES["block_active"], length=rm.length_text(seconds))


def _result_text(row: Dict[str, Any], inputs: Dict[str, Any], until: Optional[datetime], now: datetime,
                 host: Optional[str]) -> Optional[str]:
    command, state = row.get("command"), row.get("state")
    if row.get("reasonCode") == "suppressed_by_undo" and inputs.get("undoneAt"):
        return rm.RESULT_TEMPLATES["not_repeated"]
    if row.get("dispatcher") != SECURITY_DISPATCHER:
        return None
    result = _dict(row.get("result"))
    if command == "block_ip":
        return _block_result(row, until, now)
    if command == "quarantine_file" and state == "verified":
        path = _path_of(row)
        if not path:
            return None
        text = rm.fill(rm.RESULT_TEMPLATES["quarantine_done"], path=path)
        # The row's own list (cleared when the kill-only card ends the process) wins over what the host reported.
        still = row["stillRunning"] if "stillRunning" in row else result.get("still_running")
        if still and not inputs.get("parentActionId"):       # a retry has no card to point at (D-06)
            text += " " + rm.RESULT_TEMPLATES["quarantine_still_running"]
        return text
    if command == "restart_service" and state in UNDOABLE_STATES:
        service, attempt, seconds = _text(inputs.get("service")), _int(inputs.get("attempt")), _int(result.get("healthy_after"))
        if service and attempt and seconds is not None:
            return rm.fill(rm.RESULT_TEMPLATES["restart_done"], service=service, seconds=seconds, attempt=attempt)
    if command == "isolate_host":
        if state in ("undone", "rolled_back") and row.get("reasonCode") == "auto_reverted":
            return rm.RESULT_TEMPLATES["isolation_reverted"]
        name = host or _text(row.get("target"))
        if state in UNDOABLE_STATES and name:
            return rm.fill(rm.RESULT_TEMPLATES["isolation_done"], host=name)
    return None


# ---------------------------------------------------------------- undo

def _can_undo(row: Dict[str, Any], spec: Optional[registry.ActionSpec], until: Optional[datetime],
              now: datetime, can_act: bool) -> bool:
    """True only for: a registered undo, state executed or verified, one step, not simulated, a target,
    not past ``blockedUntil``, and a viewer who may act in an interactive session."""
    return bool(can_act and spec is not None and spec.undo and row.get("state") in UNDOABLE_STATES
                and not row.get("shadow") and dispatch_check.step_count(row) == 1 and (row.get("targets") or [])
                and not (until is not None and until <= now))


def row_extras(row: Dict[str, Any], *, host: Optional[str] = None, can_act: bool = False,
               now: Optional[datetime] = None) -> Dict[str, Any]:
    """The extra fields for one Activity row (see the module docstring)."""
    out = dict(EMPTY_EXTRAS)
    if row.get("kind") == "control":
        return out
    now = _aware(now) or datetime.now(timezone.utc)
    inputs = _dict(_dict(row.get("reason")).get("inputs"))
    until = _aware(row.get("blockedUntil"))
    spec = registry.resolve(row.get("command"))
    out["blockedUntil"] = until.isoformat() if until else None
    incident = inputs.get("incidentId")
    out["incidentId"] = incident[:ID_CAP] if isinstance(incident, str) and incident else None
    if _can_undo(row, spec, until, now, can_act):
        out["canUndo"] = True
        out["undoHint"] = rm.undo_hint(spec.undo, ip=_ip_of(row), path=_path_of(row))
    suggestion = _suggestion(inputs)
    out["suggestion"] = suggestion
    if suggestion is not None:
        out.update(_suggestion_words(row, inputs, suggestion, host))
        return out
    if inputs:
        reason = _reason_text(row, inputs)
        if reason:
            out["reasonText"] = reason
    result = _result_text(row, inputs, until, now, host)
    if result:
        out["resultText"] = result
    return out
