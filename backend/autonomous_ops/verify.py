"""The agent's own verdict on a response action (Phase 83, RESP-06).

Two jobs, both pure bookkeeping:

``bounded_result`` cuts what an agent posted down to whitelisted, bounded fields before the result
route stores it. The agent is untrusted: an outcome or check outside the contract's closed lists,
a number outside its range, an oversized list or a wrongly typed value becomes nothing (T-83-01).

``settle`` reads that stored result for a row that reached ``executed`` and moves it to ``verified``
(the agent says its check passed, or the action was already in place) or to ``failed`` with
``verify_failed`` (the agent says its check did not pass). A result with no verify block leaves the
row ``executed``.

``failure_outcome`` names how a ``security_response`` instruction that did not succeed ended, from the
stored instruction document: (``refused``, ``hash_mismatch``) when the file no longer matches what was
flagged, (``refused``, ``protected_path``), (``refused``, ``agent_refused``) when the host declined the
target and changed nothing, (``failed``, ``blocked_by_local_security``), (``failed``, ``locked``),
(``failed``, ``capability_off``) when the poll held the instruction back because the capability was no
longer ticked, and otherwise (``failed``, ``agent_failed``). The circuit breaker counts only some of these
(``ledger.BREAKER_FAILURES``).

What this module never does (PROH-83-06): it does not look at any finding, it does not start a
re-scan, and it does not undo, compensate or repeat the action. A block whose address is still
flagged stays in place; the only thing that ends a verified block is its expiry or a person's undo.
Both transitions are compare-and-set, so two passes over one row write one audit event per change.

Raw Mongo handle with an explicit tenantId; the ambient tenant ContextVar is never used.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from . import ledger, messages
from .agent_support import CONTRACT

logger = logging.getLogger(__name__)

_OUTCOMES = frozenset(CONTRACT["outcomes"])
_CHECKS = frozenset(CONTRACT["checks"])
_CAP = int(CONTRACT["stillRunningCap"])
_MAX_EXPIRES = int(CONTRACT["blockTtlSeconds"]["max"])
_MAX_HEALTHY = 3600
_MAX_NAME = 128


def _int_in(value: Any, low: int, high: int) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        return None
    return value


def _entry(item: Any) -> Optional[Dict[str, Any]]:
    """One still-running process, or None. start_time is the process start in whole epoch seconds;
    the pair of pid and start_time tells one process from a later one that reused its PID."""
    if not isinstance(item, dict):
        return None
    pid, start, name = item.get("pid"), item.get("start_time"), item.get("name")
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 1:
        return None
    if isinstance(start, bool) or not isinstance(start, int) or start <= 0:
        return None
    if not isinstance(name, str) or len(name) > _MAX_NAME:
        return None
    return {"pid": pid, "name": name, "start_time": start}


def bounded_result(nested: Any) -> Dict[str, Any]:
    """Only the keys below, each inside its range; anything else is dropped. A list key that is
    present keeps at most the contract's cap of well-formed entries."""
    if not isinstance(nested, dict):
        return {}
    out: Dict[str, Any] = {}
    outcome = nested.get("outcome")
    if isinstance(outcome, str) and outcome in _OUTCOMES:
        out["outcome"] = outcome
    block = nested.get("verify")
    if isinstance(block, dict) and isinstance(block.get("ok"), bool):
        check = block.get("check")
        if isinstance(check, str) and check in _CHECKS:
            out["verify"] = {"ok": block["ok"], "check": check}
    expires = _int_in(nested.get("expires_in"), 0, _MAX_EXPIRES)
    if expires is not None:
        out["expires_in"] = expires
    healthy = _int_in(nested.get("healthy_after"), 0, _MAX_HEALTHY)
    if healthy is not None:
        out["healthy_after"] = healthy
    running = nested.get("still_running")
    if isinstance(running, list):
        entries = (_entry(item) for item in running)
        out["still_running"] = [e for e in entries if e is not None][:_CAP]
    return out


def failure_outcome(doc: Optional[Dict[str, Any]]) -> Tuple[str, str]:
    """(ledger state, reason code) for an instruction that ended in a failure status. Anything the contract
    does not name is ``agent_failed``."""
    result = doc.get("result") if isinstance(doc, dict) else None
    outcome = result.get("outcome") if isinstance(result, dict) else None
    if outcome in ("hash_mismatch", "protected_path"):
        return "refused", outcome
    if outcome == "refused":
        return "refused", "agent_refused"
    if outcome in ("blocked_by_local_security", "locked"):
        return "failed", outcome
    status = doc.get("status") if isinstance(doc, dict) else None
    if isinstance(status, str) and status.strip().lower() == "refused":
        return "failed", "capability_off"       # refused at the poll, never delivered (agent_capabilities.hold_back)
    return "failed", "agent_failed"


def _now(now: Optional[datetime]) -> datetime:
    now = now or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


async def settle(db, tenant_id: str, row: Dict[str, Any], doc: Optional[Dict[str, Any]], *,
                 now: Optional[datetime] = None) -> Optional[str]:
    """Move an ``executed`` row by what its instruction's stored result says. Returns "verified",
    "failed" or None (nothing changed: no result, no verify block, or another pass won)."""
    result = (doc or {}).get("result")
    if not isinstance(result, dict):
        return None
    block = result.get("verify")
    ok = block.get("ok") if isinstance(block, dict) else None
    now = _now(now)
    if ok is False:
        moved = await ledger.transition(
            db, tenant_id, row["id"], ("executed",), "failed", reasonCode="verify_failed",
            reasonText=messages.REASON_TEXT["verify_failed"],
            result={**(row.get("result") or {}), "verify": block, "outcome": result.get("outcome")})
        return "failed" if moved else None
    if ok is True or result.get("outcome") == "already_applied":
        fields: Dict[str, Any] = {"verifiedAt": now}
        expires = result.get("expires_in")
        if isinstance(expires, int) and not isinstance(expires, bool):
            fields["blockedUntil"] = now + timedelta(seconds=expires)     # relative, so clock skew cannot matter
        moved = await ledger.transition(db, tenant_id, row["id"], ("executed",), "verified", **fields)
        return "verified" if moved else None
    return None
