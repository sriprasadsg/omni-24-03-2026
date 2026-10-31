"""The autonomy gate (GATE-03): the one decision function every autonomous action passes, and
the only writer of autonomous instructions.

``decide`` is an ordered list of check steps in the GATE-03 order: platform stop, tenant
eligibility, tenant stop, level, action class, protected targets, blast-radius cap, dedupe /
cooldown / undo suppression, shadow wrapper. Each step appends ``{check, result, code}`` to
the decision trace. The first hard refusal in that order is the reason recorded; soft
escalations accumulate and the strongest wins (suggest over needs_approval over allow_auto).

Every step is live: platform stop, eligibility (D-23, D-04), tenant stop, level, class
(GATE-04), protected targets (GATE-08 / D-19), blast radius (D-17 host cap, D-20 rate limit),
dedupe / cooldown / undo suppression, the shadow wrapper (D-02) and the write-ahead intent
row. A row is recorded for every decision except those for a tenant that is Off (not ticked,
the Platform tenant, or level Off), which leave no row, audit event or notification (D-23).

Every recorded decision is inserted into ``autonomy_actions`` before anything is dispatched;
if that insert fails the decision is refused ``ledger_unavailable`` (GATE-07). Shadow mode
(deployment master or the tenant's own flag, D-02) records "would have" and writes nothing
to an agent. ``execute`` and ``execute_response_task`` are the ONLY places in the repository
that write the autonomy stamp (``triggered_by`` autonomous_ops); each re-reads the ledger row,
refuses unless it is dispatchable for the kind, and binds the dispatch to what was decided.

Raw Mongo handle with an explicit tenantId everywhere; the ambient tenant ContextVar is never
used. No LLM client is imported or called anywhere in this package.
"""
import logging
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pymongo.errors import DuplicateKeyError

from . import (APPROVAL_TTL, COOLDOWN, HOST_CAP, INSTRUCTION_KINDS, OPEN_STATES, PLATFORM_TENANT_ID,
               RATE_LIMIT_PER_WINDOW, RATE_LIMIT_WINDOW, STAMP_SOURCE, STOP_EXEMPT_KINDS)
from . import decision_row, dispatch_check, ledger, messages, notify, protected, registry, settings
from .scope import raw

logger = logging.getLogger(__name__)

# Outcome strength: the strongest escalation wins.
_STRENGTH = {"allow_auto": 0, "needs_approval": 1, "suggest": 2}
# Outcome -> ledger state for a recorded decision.
_STATE = {"allow_auto": "dispatching", "needs_approval": "awaiting_approval", "suggest": "suggested"}
# Every reason code decide can record (messages.REASON_TEXT has a plain-words entry for each).
REASON_CODES = (
    "no_tenant", "platform_tenant", "not_enabled", "platform_stop", "tenant_stop", "level_off",
    "settings_unreadable", "level_suggest", "suggest_requested", "unregistered_action", "class_approve",
    "playbook_raised", "class_auto", "no_target", "cross_tenant_target", "protected_target",
    "invalid_target", "blast_radius", "rate_limit", "duplicate", "suppressed_by_undo",
    "ledger_unavailable")
# Refusals that never leave a row: the tenant is Off, so nothing is recorded (D-23).
_UNRECORDED = frozenset({"no_tenant", "platform_tenant", "not_enabled", "level_off", "duplicate",
                         "suppressed_by_undo", "ledger_unavailable"})
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
    steps: Optional[List[Dict[str, Any]]] = None      # [{action, params}] in playbook order
    rollback: Optional[List[Dict[str, Any]]] = None   # compensation steps, same shape


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
    rollback_specs: List[registry.ActionSpec] = field(default_factory=list)
    distinct: List[str] = field(default_factory=list)      # the request's distinct target ids
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

async def _load_tenant(ctx: _Ctx) -> None:
    """Load the tenant's settings once (also needed by a stop refusal, to know whether to record)."""
    tid = ctx.req.tenant_id
    if ctx.tenant is None and tid and isinstance(tid, str):
        ctx.tenant = await settings.load(ctx.db, tid)
        ctx.level = settings.effective_level(ctx.tenant)


async def _step_platform_stop(ctx: _Ctx) -> None:
    """The platform-wide stop. An unreadable stop counts as stopped (fail closed)."""
    try:
        stopped = settings.stop_active(await settings.platform_stop(ctx.db))
    except Exception as exc:
        logger.error("autonomous_ops: platform stop unreadable, treating as stopped: %s", exc)
        stopped = True
    if stopped:
        await _load_tenant(ctx)
        return ctx.refuse("platform_stop", "platform_stop")
    ctx.note("platform_stop", "pass")


async def _step_eligibility(ctx: _Ctx) -> None:
    """D-23 / D-04: an unticked tenant, and the Platform tenant, are Off: refused and nothing
    is recorded. A tenant whose settings cannot be read is Suggest (fail closed)."""
    if not ctx.req.tenant_id or not isinstance(ctx.req.tenant_id, str):
        return ctx.refuse("eligibility", "no_tenant", record=False)
    await _load_tenant(ctx)
    if ctx.req.tenant_id == PLATFORM_TENANT_ID:
        return ctx.refuse("eligibility", "platform_tenant", record=False)
    if not ctx.tenant.eligible:
        return ctx.refuse("eligibility", "not_enabled", record=False)
    if not ctx.tenant.readable:
        ctx.escalate("eligibility", "suggest", "settings_unreadable")
        return
    ctx.note("eligibility", "pass")


async def _step_tenant_stop(ctx: _Ctx) -> None:
    if settings.stop_active(ctx.tenant.stop):
        return ctx.refuse("tenant_stop", "tenant_stop")
    ctx.note("tenant_stop", "pass")


async def _step_level(ctx: _Ctx) -> None:
    """Off refuses, Suggest escalates; a caller can also force Suggest."""
    if ctx.level == "off":
        return ctx.refuse("level", "level_off", record=False)
    if ctx.level == "suggest":
        return ctx.escalate("level", "suggest", "level_suggest")
    if ctx.req.force_suggest:
        return ctx.escalate("level", "suggest", "suggest_requested")
    ctx.note("level", "pass")


async def _step_class(ctx: _Ctx) -> None:
    """GATE-04: class comes only from the registry (and a playbook raise), for every step and compensation step."""
    ctx.specs, ctx.rollback_specs = dispatch_check.classify(ctx.req) or ([], [])
    specs = ctx.specs
    if not specs:
        return ctx.refuse("class", "unregistered_action")
    if any(s.cls == "approve" for s in specs):
        return ctx.escalate("class", "needs_approval", "class_approve")
    if registry.effective_class(specs[0], playbook_raise=ctx.req.playbook_raise) == "approve":
        return ctx.escalate("class", "needs_approval", "playbook_raised")
    ctx.note("class", "allow_auto", "class_auto")


async def _agent_of(ctx: _Ctx, target: str) -> Optional[Dict[str, Any]]:
    """The enrolled agent for a target id, read raw; None when missing or unreadable."""
    try:
        return await raw(ctx.db).agents.find_one(
            {"id": target}, {"_id": 0, "id": 1, "tenantId": 1, "hostname": 1, "ipAddress": 1})
    except Exception as exc:
        logger.error("autonomous_ops: agent %s could not be read: %s", target, exc)
        return None


async def _step_protected_targets(ctx: _Ctx) -> None:
    """GATE-08 / D-19: every target must be an agent of this tenant and none may be on the
    never-touch list; every IP parameter must parse and must not be on it either."""
    req = ctx.req
    targets = req.targets if isinstance(req.targets, list) else []
    if not targets:
        return ctx.refuse("protected_targets", "no_target")
    if any(not isinstance(t, str) or not t for t in targets):
        return ctx.refuse("protected_targets", "invalid_target")
    ctx.distinct = list(dict.fromkeys(targets))
    try:
        for target in ctx.distinct:
            agent = await _agent_of(ctx, target)
            if agent is None or agent.get("tenantId") != req.tenant_id:
                return ctx.refuse("protected_targets", "cross_tenant_target")
            code = await protected.check(ctx.db, req.tenant_id, agent=agent)
            if code:
                return ctx.refuse("protected_targets", code)
        code = await dispatch_check.ip_refusal(
            ctx.db, req.tenant_id, dispatch_check.spec_pairs(req, ctx.specs, ctx.rollback_specs))
        if code:
            return ctx.refuse("protected_targets", code)
    except Exception as exc:  # the never-touch list could not be read: do not act
        logger.error("autonomous_ops: never-touch list unreadable, refusing: %s", exc)
        return ctx.refuse("protected_targets", "protected_target")
    ctx.note("protected_targets", "pass")


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if isinstance(value, datetime) and value.tzinfo is None else value


async def _notice_rate_limit(ctx: _Ctx) -> None:
    """Tell the platform and the tenant's admins once per rate-limit window (the marker is
    rateLimitNotifiedAt on autonomy_settings). Never raises."""
    tid = ctx.req.tenant_id
    try:
        doc = await raw(ctx.db).autonomy_settings.find_one({"tenantId": tid}, {"_id": 0, "rateLimitNotifiedAt": 1})
        last = _aware((doc or {}).get("rateLimitNotifiedAt"))
        if isinstance(last, datetime) and last > ctx.now - RATE_LIMIT_WINDOW:
            return
        await settings.ensure_tenant(ctx.db, tid)
        await settings.update(ctx.db, tid, {"rateLimitNotifiedAt": ctx.now}, actor="system")
        title, text = messages.NOTICES["rate_limit_reached"]
        await notify.notify(ctx.db, tid, title=title,
                            message=text.format(tenant=ctx.tenant.name or tid, limit=RATE_LIMIT_PER_WINDOW),
                            metadata={"event": "rate_limit_reached", "tenantId": tid})
    except Exception as exc:
        logger.warning("autonomous_ops: rate-limit notice for %s not sent: %s", tid, exc)


async def _step_blast_radius(ctx: _Ctx) -> None:
    """D-17: one automatic decision touches exactly one host. D-20: at most 20 automatic
    actions in a rolling hour; the 21st waits for approval."""
    escalated = False
    if len(ctx.distinct) > HOST_CAP:
        ctx.escalate("blast_radius", "needs_approval", "blast_radius")
        escalated = True
    if ctx.strongest()[0] == "allow_auto":
        try:
            recent = await ledger.count_auto_since(ctx.db, ctx.req.tenant_id, ctx.now - RATE_LIMIT_WINDOW)
        except Exception as exc:
            logger.error("autonomous_ops: rate limit unreadable, holding for approval: %s", exc)
            recent = RATE_LIMIT_PER_WINDOW
        if recent >= RATE_LIMIT_PER_WINDOW:
            ctx.escalate("blast_radius", "needs_approval", "rate_limit")
            escalated = True
            await _notice_rate_limit(ctx)
    if not escalated:
        ctx.note("blast_radius", "pass")


async def _step_dedupe(ctx: _Ctx) -> None:
    """An open row with the same dedupeKey, a simulation younger than the cooldown, or an
    undone row younger than the cooldown refuses the request without recording it."""
    key = ctx.req.dedupe_key
    if not isinstance(key, str) or not key:
        return ctx.note("dedupe", "skipped")
    since = ctx.now - COOLDOWN
    base = {"tenantId": ctx.req.tenant_id, "dedupeKey": key}
    coll = raw(ctx.db).autonomy_actions
    try:
        if await coll.find_one({**base, "state": {"$in": list(OPEN_STATES)}}, {"_id": 1}):
            return ctx.refuse("dedupe", "duplicate", record=False)
        if await coll.find_one({**base, "state": "shadow", "createdAt": {"$gt": since}}, {"_id": 1}):
            return ctx.refuse("dedupe", "duplicate", record=False)
        undone = {**base, "state": "undone", "$or": [{"undo.undoneAt": {"$gt": since}},
                                                       {"finishedAt": {"$gt": since}}, {"createdAt": {"$gt": since}}]}
        if await coll.find_one(undone, {"_id": 1}):
            return ctx.refuse("dedupe", "suppressed_by_undo", record=False)
    except Exception as exc:
        logger.error("autonomous_ops: dedupe check failed, refusing: %s", exc)
        return ctx.refuse("dedupe", "ledger_unavailable", record=False)
    ctx.note("dedupe", "pass")


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
        record = record and code not in _UNRECORDED and ctx.tenant is not None and ctx.level != "off"
        if not record:
            return Decision("refuse", "refused", code, trace=ctx.trace)
        outcome, state = "refuse", "refused"
    else:
        outcome, code = ctx.strongest()
        state = "shadow" if ctx.shadow else _STATE[outcome]

    try:
        row = await ledger.create_intent(db, decision_row.build_row(ctx, state, outcome, code))
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


async def _authorise(db, tenant_id: str, action_id: str, kind: str, *, command=None, agent_id=None, params=None):
    """(row, None) when this dispatch may be written for the row, else (None, reason)."""
    if kind not in INSTRUCTION_KINDS:
        return None, "invalid_kind"
    row = await ledger.get(db, tenant_id, action_id)
    if row is None:
        return None, "not_found"
    if row.get("state") not in _DISPATCHABLE[kind]:
        return None, "not_dispatchable"
    if kind not in STOP_EXEMPT_KINDS and await _stopped(db, tenant_id):
        return None, "stopped"
    if reason := await dispatch_check.bind(db, tenant_id, row, command=command, agent_id=agent_id, params=params, kind=kind):
        return None, reason
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
    row is dispatchable for ``kind``, no stop is on (undo/compensate exempt, D-12) and ``bind`` passes."""
    row, reason = await _authorise(db, tenant_id, action_id, kind, command=command, agent_id=agent_id, params=params)
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
    row, reason = await _authorise(db, tenant_id, action_id, "action", command=action, agent_id=agent_id, params=params)
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
