"""The ledger row the gate records for a decision, and the undo block it carries (GATE-07, ACTV-02).

Moved out of ``gate.py`` unchanged (it had reached 500 lines): ``display_target``, ``undo_block``,
``reason_text`` and ``build_row``. Two additions, both inert for every Phase 81 row:

* ``undo_block`` takes an optional ``claim``. An undo that must remove only one claim on the agent
  carries that claim's id: ``unblock_ip`` {ip_address, block_id}, ``unquarantine_file``
  {quarantine_id}, ``restore_host`` {isolation_id}. The claim id is the original instruction's own
  task id, which only exists after the action was sent, so the undo params are recomputed when a
  person undoes it (``approvals.undo``); with no claim the output is exactly what it always was.
* ``reason_text`` keeps the caller's own wording for a ``security_response`` or ``patch_rollout`` request
  on the escalation codes, so a sweep row or a rollout card can say why it was raised. Every other code
  and every other dispatcher behaves as before.

Pure functions over the decision context: nothing here reads or writes a database.
"""
from typing import Any, Dict, Optional

from . import APPROVAL_TTL, dispatch_check, messages, registry

# The parameter that names the one claim an undo removes, keyed by the undo command.
CLAIM_KEYS = {"unblock_ip": "block_id", "unquarantine_file": "quarantine_id", "restore_host": "isolation_id"}

# Dispatchers whose own text replaces the generic reason on the codes below (Phase 83 sweep, Phase 84 rollout).
_OWN_WORDS_DISPATCHERS = frozenset({"security_response", "patch_rollout", "service_desk"})
# Dispatchers whose suggested rows never expire as approvals: a service desk draft waits on the ticket until a
# person sends, edits or discards it (D-10), so it carries no expiry.
_NO_EXPIRY_DISPATCHERS = frozenset({"service_desk"})
# Codes for which such a request's own text replaces the generic reason.
_OWN_WORDS = frozenset({"class_auto", "suggest_requested", "playbook_raised", "class_approve", "suppressed_by_undo"})


def display_target(spec: Optional[registry.ActionSpec], req: Any) -> Optional[str]:
    if spec is not None:
        for key in spec.ip_params + spec.cidr_params:
            if req.params.get(key):
                return str(req.params[key])
    if isinstance(req.params.get("path"), str) and req.params["path"]:
        return req.params["path"]                  # a file action shows the file, not the agent id (Phase 83)
    return req.targets[0] if req.targets else None


def undo_block(spec: Optional[registry.ActionSpec], params: Dict[str, Any], multi: bool = False, *,
               claim: Optional[str] = None) -> Dict[str, Any]:
    spec = None if multi else spec      # a multi-step row offers no one-instruction undo
    undo_params: Dict[str, Any] = dict(params)
    if spec is not None:
        for key in spec.ip_params:
            if params.get(key):
                undo_params = {"ip_address": params[key]}
                break
        else:
            for key in spec.cidr_params:
                if params.get(key):
                    undo_params = {"cidr": params[key]}      # a range is lifted by its own network, never by an address
                    break
    if claim and spec is not None and spec.undo in CLAIM_KEYS:
        if spec.undo == "unblock_ip":
            undo_params = {**undo_params, CLAIM_KEYS["unblock_ip"]: claim}
        else:
            undo_params = {CLAIM_KEYS[spec.undo]: claim}
    return {"available": bool(spec and spec.undo), "action": spec.undo if spec else None,
            "params": undo_params if spec and spec.undo else {}, "undoneAt": None, "undoneBy": None}


def reason_text(req: Any, outcome: str, code: str) -> Optional[str]:
    """The caller's own wording for an automatic action (and, for a security_response request, for
    the escalation codes); otherwise the plain-words reason for the code (refusals and escalations)."""
    if outcome == "allow_auto" and req.reason_text:
        return req.reason_text
    if req.dispatcher in _OWN_WORDS_DISPATCHERS and req.reason_text and code in _OWN_WORDS:
        return req.reason_text
    return messages.REASON_TEXT.get(code, req.reason_text)


def build_row(ctx: Any, state: str, outcome: str, code: str) -> Dict[str, Any]:
    req = ctx.req
    spec = ctx.specs[0] if ctx.specs else None
    needs_card = state in ("awaiting_approval", "suggested")
    pairs = dispatch_check.request_steps(req)
    row = {
        "tenantId": req.tenant_id, "kind": req.kind, "origin": req.origin, "dispatcher": req.dispatcher,
        "action": req.actions[0] if req.actions else None,
        "actions": [s.name for s in ctx.specs] or list(req.actions or []),
        "command": spec.name if spec else None, "targets": list(req.targets or []),
        "target": display_target(spec, req), "params": dict(pairs[0][1]) if pairs else {},
        "steps": dispatch_check.plan_of(pairs), "rollback": dispatch_check.plan_of(dispatch_check.request_rollback(req)),
        "state": state, "level": ctx.level, "shadow": ctx.shadow is not None,
        "wouldHave": outcome if state == "shadow" else None,
        "reason": req.reason or {"ruleId": f"gate:{req.origin}", "inputs": {}},
        "reasonCode": code, "reasonText": reason_text(req, outcome, code), "trace": ctx.trace,
        "dedupeKey": req.dedupe_key, "remediationId": req.remediation_id, "instructionIds": [],
        "approval": {"requiredBy": code if needs_card else None,
                     "expiresAt": (ctx.now + APPROVAL_TTL if needs_card and req.dispatcher not in _NO_EXPIRY_DISPATCHERS
                                   else None),
                     "approver": None, "decidedAt": None},
        "undo": undo_block(spec, req.params or {}, multi=len(pairs) > 1),
        "autoDispatched": state == "dispatching",
        "createdAt": ctx.now, "updatedAt": ctx.now,
    }
    if isinstance(getattr(req, "desk", None), dict):
        row["desk"] = dict(req.desk)          # the service desk's own subdocument (Phase 85)
    return row
