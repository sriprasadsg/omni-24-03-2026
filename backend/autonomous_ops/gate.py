"""The autonomy gate (GATE-03): the one decision function every autonomous action passes, and
the only writer of autonomous instructions.

``decide`` is an ordered list of check steps in the GATE-03 order: platform stop, tenant
eligibility, tenant stop, level, action class, protected targets, blast-radius cap, dedupe /
cooldown / undo suppression, shadow wrapper. Each step appends ``{check, result, code}`` to
the decision trace. The first hard refusal in that order is the reason recorded; soft
escalations accumulate and the strongest wins (suggest over needs_approval over allow_auto).

Plan 81-01 implements the eligibility, class and shadow steps and the write-ahead intent
row. The stop, level, protected-target, blast-radius and dedupe steps are declared in their
GATE-03 positions as named steps that record ``deferred``; plan 81-11 fills them in without
reshaping the function, and no caller exists until that is done.

Every recorded decision is inserted into ``autonomy_actions`` before anything is dispatched;
if that insert fails the decision is refused ``ledger_unavailable`` (GATE-07). Shadow mode
(deployment master or the tenant's own flag, D-02) records "would have" and writes nothing
to an agent. ``execute`` and ``execute_response_task`` are the ONLY places in the repository
that write the autonomy stamp (``triggered_by`` autonomous_ops); each re-reads the ledger row
and refuses unless the row is in a dispatchable state for the kind of instruction.

Raw Mongo handle with an explicit tenantId everywhere; the ambient tenant ContextVar is never
used. No LLM client is imported or called anywhere in this package.
"""
import logging
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pymongo.errors import DuplicateKeyError

from . import APPROVAL_TTL, INSTRUCTION_KINDS, PLATFORM_TENANT_ID, STAMP_SOURCE, STOP_EXEMPT_KINDS
from . import ledger, registry, settings
from .scope import raw

logger = logging.getLogger(__name__)

# Outcome strength: the strongest escalation wins.
_STRENGTH = {"allow_auto": 0, "needs_approval": 1, "suggest": 2}
# Outcome -> ledger state for a recorded decision.
_STATE = {"allow_auto": "dispatching", "needs_approval": "awaiting_approval", "suggest": "suggested"}
# Row states each kind of instruction may be dispatched from.
_DISPATCHABLE = {"action": ("approved", "dispatching"), "probe": ("dispatching", "executed"),
                 "compensate": ("dispatching", "failed"), "undo": ("undone",)}


@dataclass
class ActionRequest:
    tenant_id: str
    kind: str
    origin: str
    actions: List[str]
    targets: List[str]
    params: Dict[str, Any]
    dedupe_key: str
    playbook: Optional[str] = None
    playbook_raise: bool = False
    reason: Optional[Dict[str, Any]] = None
    reason_text: Optional[str] = None
    dispatcher: str = "instruction"
    force_suggest: bool = False
    remediation_id: Optional[str] = None


@dataclass
class Decision:
    outcome: str                      # refuse | suggest | needs_approval | allow_auto
    state: str                        # the ledger state of the recorded row (or "refused")
    reason: str                       # reason code
    action_id: Optional[str] = None
    shadow: bool = False
    would_have: Optional[str] = None
    trace: List[Dict[str, Any]] = field(default_factory=list)
    recorded: bool = False


@dataclass
class _Ctx:
    db: Any
    req: ActionRequest
    now: datetime
    master: Optional[bool]
    trace: List[Dict[str, Any]] = field(default_factory=list)
    tenant: Optional[settings.TenantSettings] = None
    level: str = "off"
    specs: List[registry.ActionSpec] = field(default_factory=list)
    refusal: Optional[Tuple[str, bool]] = None            # (reason code, whether a row is recorded)
    escalations: List[Tuple[str, str]] = field(default_factory=list)   # (outcome, reason code)
    shadow: Optional[str] = None                           # "deployment" | "tenant" when shadow applies

    def note(self, check: str, result: str, code: Optional[str] = None) -> None:
        self.trace.append({"check": check, "result": result, "code": code})

    def refuse(self, check: str, code: str, *, record: bool = True) -> None:
        self.refusal = (code, record)
        self.note(check, "refuse", code)

    def escalate(self, check: str, outcome: str, code: str) -> None:
        self.escalations.append((outcome, code))
        self.note(check, outcome, code)

    def strongest(self) -> Tuple[str, str]:
        """(outcome, reason code) of the strongest soft escalation, else plain allow_auto."""
        best = ("allow_auto", "class_auto")
        for outcome, code in self.escalations:
            if _STRENGTH[outcome] > _STRENGTH[best[0]]:
                best = (outcome, code)
        return best


# ---------------------------------------------------------------- decision steps (GATE-03 order)

async def _step_platform_stop(ctx: _Ctx) -> None:
    ctx.note("platform_stop", "deferred", "81-11")


async def _step_eligibility(ctx: _Ctx) -> None:
    """D-23 / D-04: an unticked tenant, and the Platform tenant, are Off: refused and nothing
    is recorded. A tenant whose settings cannot be read is Suggest (fail closed)."""
    if not ctx.req.tenant_id or not isinstance(ctx.req.tenant_id, str):
        return ctx.refuse("eligibility", "no_tenant", record=False)
    ctx.tenant = await settings.load(ctx.db, ctx.req.tenant_id)
    ctx.level = settings.effective_level(ctx.tenant)
    if ctx.req.tenant_id == PLATFORM_TENANT_ID:
        return ctx.refuse("eligibility", "platform_tenant", record=False)
    if not ctx.tenant.eligible:
        return ctx.refuse("eligibility", "not_enabled", record=False)
    if not ctx.tenant.readable:
        ctx.escalate("eligibility", "suggest", "settings_unreadable")
        return
    ctx.note("eligibility", "pass")


async def _step_tenant_stop(ctx: _Ctx) -> None:
    ctx.note("tenant_stop", "deferred", "81-11")


async def _step_level(ctx: _Ctx) -> None:
    """Stored-level handling is added by 81-11; here only a caller-forced Suggest applies."""
    if ctx.req.force_suggest:
        return ctx.escalate("level", "suggest", "suggest_requested")
    ctx.note("level", "deferred", "81-11")


async def _step_class(ctx: _Ctx) -> None:
    """GATE-04: the class comes only from the registry (and an explicit playbook raise)."""
    names = ctx.req.actions if isinstance(ctx.req.actions, list) else []
    specs = [registry.resolve(n) for n in names]
    if not specs or any(s is None for s in specs) or specs[0].cls not in ("auto", "approve"):
        return ctx.refuse("class", "unregistered_action")
    ctx.specs = specs
    if any(s.cls == "approve" for s in specs):
        return ctx.escalate("class", "needs_approval", "class_approve")
    if registry.effective_class(specs[0], playbook_raise=ctx.req.playbook_raise) == "approve":
        return ctx.escalate("class", "needs_approval", "playbook_raised")
    ctx.note("class", "allow_auto", "class_auto")


async def _step_protected_targets(ctx: _Ctx) -> None:
    ctx.note("protected_targets", "deferred", "81-11")


async def _step_blast_radius(ctx: _Ctx) -> None:
    ctx.note("blast_radius", "deferred", "81-11")


async def _step_dedupe(ctx: _Ctx) -> None:
    ctx.note("dedupe", "deferred", "81-11")


async def _step_shadow(ctx: _Ctx) -> None:
    """D-02: with either shadow layer on, an outcome that would dispatch or create an approval
    card is recorded as a simulation instead. Refusals stay refusals."""
    on, source = settings.shadow_state(ctx.tenant, ctx.master)
    if on:
        ctx.shadow = source
        ctx.note("shadow", "shadow", source)
    else:
        ctx.note("shadow", "pass")


_STEPS = (_step_platform_stop, _step_eligibility, _step_tenant_stop, _step_level, _step_class,
          _step_protected_targets, _step_blast_radius, _step_dedupe, _step_shadow)


# ---------------------------------------------------------------- the decision

def _display_target(spec: Optional[registry.ActionSpec], req: ActionRequest) -> Optional[str]:
    if spec is not None:
        for key in spec.ip_params:
            if req.params.get(key):
                return str(req.params[key])
    return req.targets[0] if req.targets else None


def _undo_block(spec: Optional[registry.ActionSpec], params: Dict[str, Any]) -> Dict[str, Any]:
    undo_params: Dict[str, Any] = dict(params)
    if spec is not None:
        for key in spec.ip_params:
            if params.get(key):
                undo_params = {"ip_address": params[key]}
                break
    return {"available": bool(spec and spec.undo), "action": spec.undo if spec else None,
            "params": undo_params if spec and spec.undo else {}, "undoneAt": None, "undoneBy": None}


def _row(ctx: _Ctx, state: str, outcome: str, code: str) -> Dict[str, Any]:
    req = ctx.req
    spec = ctx.specs[0] if ctx.specs else None
    needs_card = state in ("awaiting_approval", "suggested")
    return {
        "tenantId": req.tenant_id, "kind": req.kind, "origin": req.origin, "dispatcher": req.dispatcher,
        "action": req.actions[0] if req.actions else None,
        "actions": [s.name for s in ctx.specs] or list(req.actions or []),
        "command": spec.name if spec else None, "targets": list(req.targets or []),
        "target": _display_target(spec, req), "params": dict(req.params or {}),
        "state": state, "level": ctx.level, "shadow": ctx.shadow is not None,
        "wouldHave": outcome if state == "shadow" else None,
        "reason": req.reason or {"ruleId": f"gate:{req.origin}", "inputs": {}},
        "reasonCode": code, "reasonText": req.reason_text, "trace": ctx.trace,
        "dedupeKey": req.dedupe_key, "remediationId": req.remediation_id, "instructionIds": [],
        "approval": {"requiredBy": code if needs_card else None,
                     "expiresAt": ctx.now + APPROVAL_TTL if needs_card else None,
                     "approver": None, "decidedAt": None},
        "undo": _undo_block(spec, req.params or {}),
        "autoDispatched": state == "dispatching",
        "createdAt": ctx.now, "updatedAt": ctx.now,
    }


async def decide(db, req: ActionRequest, *, master_shadow: Optional[bool] = None,
                 now: Optional[datetime] = None) -> Decision:
    """Decide one autonomous action request and record the decision before returning it."""
    now = now or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    now = now.replace(microsecond=now.microsecond // 1000 * 1000)   # BSON datetimes are milliseconds
    ctx = _Ctx(db=db, req=req, now=now, master=master_shadow)
    for step in _STEPS:
        await step(ctx)
        if ctx.refusal:
            break

    if ctx.refusal:
        code, record = ctx.refusal
        if not record:
            return Decision("refuse", "refused", code, trace=ctx.trace)
        outcome, state = "refuse", "refused"
    else:
        outcome, code = ctx.strongest()
        state = "shadow" if ctx.shadow else _STATE[outcome]

    try:
        row = await ledger.create_intent(db, _row(ctx, state, outcome, code))
    except ledger.LedgerUnavailable as exc:
        logger.error("autonomous_ops: decision not recorded, refusing: %s", exc)
        ctx.note("ledger", "refuse", "ledger_unavailable")
        return Decision("refuse", "refused", "ledger_unavailable", trace=ctx.trace)
    except DuplicateKeyError:
        ctx.note("dedupe", "refuse", "duplicate")
        return Decision("refuse", "refused", "duplicate", trace=ctx.trace)
    return Decision(outcome, state, code, action_id=row["id"], shadow=ctx.shadow is not None,
                    would_have=outcome if state == "shadow" else None, trace=ctx.trace, recorded=True)


async def suggest(db, req: ActionRequest, **kw) -> Decision:
    """``decide`` with the outcome forced to at most Suggest."""
    return await decide(db, replace(req, force_suggest=True), **kw)


# ---------------------------------------------------------------- the only stamped writers

async def _stopped(db, tenant_id: str) -> bool:
    """A platform or tenant stop is on. Anything unreadable counts as stopped (fail closed)."""
    try:
        if settings.stop_active(await settings.platform_stop(db)):
            return True
        s = await settings.load(db, tenant_id)
    except Exception as exc:
        logger.error("autonomous_ops: stop state unreadable, treating as stopped: %s", exc)
        return True
    return (not s.readable) or settings.stop_active(s.stop)


async def _authorise(db, tenant_id: str, action_id: str, kind: str):
    """(row, None) when this kind of instruction may be written for the row, else (None, reason)."""
    if kind not in INSTRUCTION_KINDS:
        return None, "invalid_kind"
    row = await ledger.get(db, tenant_id, action_id)
    if row is None:
        return None, "not_found"
    if row.get("state") not in _DISPATCHABLE[kind]:
        return None, "not_dispatchable"
    if kind not in STOP_EXEMPT_KINDS and await _stopped(db, tenant_id):
        return None, "stopped"
    if kind == "action" and row["state"] == "approved":
        row = await ledger.transition(db, tenant_id, action_id, ("approved",), "dispatching")
        if row is None:
            return None, "not_dispatchable"
    return row, None


async def _link(db, tenant_id: str, action_id: str, doc_id: str) -> None:
    try:
        await raw(db).autonomy_actions.update_one(
            {"id": action_id, "tenantId": tenant_id},
            {"$push": {"instructionIds": doc_id}, "$set": {"updatedAt": datetime.now(timezone.utc)}})
    except Exception as exc:
        logger.error("autonomous_ops: could not link %s to %s: %s", doc_id, action_id, exc)


async def execute(db, tenant_id: str, action_id: str, *, command: str, agent_id: str,
                  params: Dict[str, Any], kind: str = "action") -> Dict[str, Any]:
    """Write one stamped agent instruction for a ledger row. This and ``execute_response_task``
    are the only functions in the repository that write the autonomy stamp. Refused unless the
    row is in a dispatchable state for ``kind`` and (except undo/compensate, D-12) no stop is on."""
    row, reason = await _authorise(db, tenant_id, action_id, kind)
    if row is None:
        return {"status": "refused", "reason": reason}
    task_id = uuid.uuid4().hex
    doc = {"id": task_id, "type": command, "agent_id": agent_id, "tenantId": tenant_id,
           "payload": params, "parameters": params, "status": "pending", "triggered_by": STAMP_SOURCE,
           "autonomy": {"actionId": action_id, "tenantId": tenant_id, "kind": kind},
           "created_at": datetime.now(timezone.utc).isoformat()}
    try:
        await raw(db).agent_instructions.insert_one(doc)
    except Exception as exc:
        logger.error("autonomous_ops: instruction for %s not written: %s", action_id, exc)
        return {"status": "refused", "reason": "dispatch_failed"}
    await _link(db, tenant_id, action_id, task_id)
    return {"status": "queued", "task_id": task_id}


async def execute_response_task(db, tenant_id: str, action_id: str, *, action: str, agent_id: str,
                                params: Dict[str, Any],
                                playbook_execution_id: Optional[str] = None) -> Dict[str, Any]:
    """Write one stamped response task (the third delivery queue) for a ledger row, under the
    same state and stop rules as ``execute`` for kind "action"."""
    row, reason = await _authorise(db, tenant_id, action_id, "action")
    if row is None:
        return {"status": "refused", "reason": reason}
    now = datetime.now(timezone.utc)
    task_id = f"RSP-{now.strftime('%Y%m%d%H%M%S%f')}-{uuid.uuid4().hex[:6]}"
    doc = {"task_id": task_id, "agent_id": agent_id, "action": action, "params": params,
           "tenantId": tenant_id, "status": "queued", "triggered_by": STAMP_SOURCE,
           "autonomy": {"actionId": action_id, "tenantId": tenant_id, "kind": "action"},
           "playbook_execution_id": playbook_execution_id, "created_at": now.isoformat(),
           "executed_at": None, "result": None}
    try:
        await raw(db).response_tasks.insert_one(doc)
    except Exception as exc:
        logger.error("autonomous_ops: response task for %s not written: %s", action_id, exc)
        return {"status": "refused", "reason": "dispatch_failed"}
    await _link(db, tenant_id, action_id, task_id)
    return {"status": "queued", "task_id": task_id}
