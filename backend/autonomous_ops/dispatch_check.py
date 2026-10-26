"""Checks on what an autonomous decision will dispatch (GATE-03, GATE-04, GATE-08, GATE-10).

The gate used to decide a playbook on its first step only. These helpers give it the whole
plan: every main step and every compensation step with its own parameters, so each is
class-checked against the registry and IP-checked against the never-touch list, and the
decided plan is recorded on the ledger row.

A request carries its plan as ``steps`` / ``rollback`` (lists of ``{"action", "params"}``).
A request without ``steps`` is the single-params form: the steps are derived from ``actions``
plus the shared ``params``, so there is one internal source.

At dispatch, ``bind`` ties each instruction the gate writes to the decided row (GATE-03 / GATE-08
/ GATE-10): a registered command of the right class, an agent the row was decided for, one of
the decided (command, params) steps, and a never-touch re-check of the IP parameters.

Raw Mongo handle and an explicit tenant only. Pure reads: nothing here writes, names the
autonomy stamp, or touches an LLM.
"""
import json
from typing import Any, Dict, List, Optional, Tuple

from . import protected, registry

Pair = Tuple[Any, Dict[str, Any]]


def _pairs(items) -> List[Pair]:
    """(action name, params) for each item; anything that is not a step dict yields (None, {})."""
    if not isinstance(items, list):
        return [(None, {})]          # malformed: an unresolvable name, refused by the class check
    out: List[Pair] = []
    for item in items:
        if isinstance(item, dict):
            params = item.get("params")
            out.append((item.get("action"), params if isinstance(params, dict) else {}))
        else:
            out.append((None, {}))
    return out


def request_steps(req) -> List[Pair]:
    """The main steps in playbook order: ``req.steps`` when it is a list, else one step per
    action with the shared params."""
    if isinstance(req.steps, list):
        return _pairs(req.steps)
    shared = req.params if isinstance(req.params, dict) else {}
    return [(name, shared) for name in (req.actions if isinstance(req.actions, list) else [])]


def request_rollback(req) -> List[Pair]:
    """The compensation steps in playbook order; None or missing means none."""
    return [] if req.rollback is None else _pairs(req.rollback)


def steps_consistent(req) -> bool:
    """True when ``steps`` is absent, or is a non-empty list of dicts whose actions equal
    ``req.actions`` one for one (same length, same order)."""
    if req.steps is None:
        return True
    if not isinstance(req.steps, list) or not req.steps or not isinstance(req.actions, list):
        return False
    if not all(isinstance(s, dict) for s in req.steps):
        return False
    return [s.get("action") for s in req.steps] == list(req.actions)


def classify(req) -> Optional[Tuple[List[registry.ActionSpec], List[registry.ActionSpec]]]:
    """GATE-04 over the whole plan: (main specs, compensation specs), or None when the request
    must be refused ``unregistered_action``. Every main step must be registered with class auto
    or approve; every compensation step must be registered with class undo_only. Reads only the
    immutable registry table."""
    if not steps_consistent(req):
        return None
    main = [registry.resolve(name) for name, _ in request_steps(req)]
    comp = [registry.resolve(name) for name, _ in request_rollback(req)]
    if not main or any(s is None or s.cls not in ("auto", "approve") for s in main):
        return None
    if any(s is None or s.cls != "undo_only" for s in comp):
        return None
    return main, comp


def spec_pairs(req, specs, rollback_specs) -> List[Tuple[Any, Dict[str, Any]]]:
    """(spec, own params) for every main step, then every compensation step."""
    return (list(zip(specs, [p for _, p in request_steps(req)]))
            + list(zip(rollback_specs, [p for _, p in request_rollback(req)])))


def plan_of(pairs: List[Pair]) -> List[Dict[str, Any]]:
    """The recorded plan: ``{command, params}`` per step (the registry command name when the
    action resolves, else the raw name)."""
    out = []
    for name, params in pairs:
        spec = registry.resolve(name)
        out.append({"command": spec.name if spec else name, "params": dict(params or {})})
    return out


async def ip_refusal(db, tenant_id: str, pairs) -> Optional[str]:
    """The first never-touch code (``invalid_target`` / ``protected_target``) for any IP
    parameter of any (spec, params) pair, in order; None when all pass. A None spec is skipped.
    Errors propagate: the caller fails closed."""
    for spec, params in pairs:
        if spec is None:
            continue
        params = params if isinstance(params, dict) else {}
        for key in spec.ip_params:
            if params.get(key) is not None:
                code = await protected.check(db, tenant_id, ip=params[key])
                if code:
                    return code
    return None


# ---------------------------------------------------------------- approval-time re-check (81-18)

def row_pairs(row) -> List[Tuple[Any, Dict[str, Any]]]:
    """(spec, own params) for every recorded step of a ledger row, then every recorded
    compensation step. A row written before the plan was recorded (no ``steps`` list) yields one
    pair per name in ``actions`` (else its ``command``) with the row's params. Pure: no reads."""
    if isinstance(row.get("steps"), list):
        items = row["steps"] + (row["rollback"] if isinstance(row.get("rollback"), list) else [])
        return [(registry.resolve(i.get("command")), i.get("params") if isinstance(i.get("params"), dict) else {})
                if isinstance(i, dict) else (None, {}) for i in items]
    names = row.get("actions") if isinstance(row.get("actions"), list) and row["actions"] else [row.get("command")]
    params = row.get("params") if isinstance(row.get("params"), dict) else {}
    return [(registry.resolve(n), params) for n in names]


def step_count(row) -> int:
    """How many steps the row was decided with: the recorded steps, else 1 when it has a
    command, else 0."""
    if isinstance(row.get("steps"), list):
        return len(row["steps"])
    return 1 if row.get("command") else 0


# ---------------------------------------------------------------- dispatch-time binding (81-15)

_KIND_CLASSES = {"action": ("auto", "approve"), "compensate": ("undo_only",), "undo": ("undo_only",),
                 "probe": ("probe",)}


def same_params(a, b) -> bool:
    """True when both parameter dicts have the same canonical JSON (sorted keys, ``default=str``).
    A value whose representation differs (int 5 versus "5") is not the same: fail closed."""
    try:
        return (json.dumps(a or {}, sort_keys=True, default=str)
                == json.dumps(b or {}, sort_keys=True, default=str))
    except (TypeError, ValueError):
        return False


def _items(value) -> List[Dict[str, Any]]:
    return [i for i in value if isinstance(i, dict)] if isinstance(value, list) else []


def decided_steps(row, kind: str) -> Optional[List[Dict[str, Any]]]:
    """The ``{command, params}`` steps the row was decided with for this kind of instruction;
    None for a probe (any probe command). action: the recorded steps, else the row's actions
    with its params. compensate: the recorded rollback. undo: the recorded undo action."""
    if kind == "probe":
        return None
    if kind == "compensate":
        return _items(row.get("rollback"))
    if kind == "undo":
        undo = row.get("undo") if isinstance(row.get("undo"), dict) else {}
        return [{"command": undo["action"], "params": undo.get("params") or {}}] if undo.get("action") else []
    if isinstance(row.get("steps"), list):
        return _items(row["steps"])
    names = row.get("actions") if isinstance(row.get("actions"), list) else [row.get("command")]
    return [{"command": n, "params": row.get("params") or {}} for n in names]


async def bind(db, tenant_id: str, row, *, command, agent_id, params, kind: str) -> Optional[str]:
    """None when this dispatch is exactly what the row decided, else the refusal code:
    ``unregistered_action``, ``target_mismatch``, ``step_mismatch``, or (auto / approve
    commands only, checked now against the current list) ``protected_target`` /
    ``invalid_target``. An unreadable never-touch list refuses ``protected_target``."""
    spec = registry.resolve(command)
    if spec is None:
        return "unregistered_action"
    targets = row.get("targets")
    if not isinstance(targets, list) or agent_id not in targets:
        return "target_mismatch"
    if spec.cls not in _KIND_CLASSES.get(kind, ()):
        return "step_mismatch"
    steps = decided_steps(row, kind)
    if steps is not None and not any(
            registry.resolve(s.get("command")) is spec and same_params(s.get("params"), params) for s in steps):
        return "step_mismatch"
    if spec.cls in ("auto", "approve"):
        try:
            return await ip_refusal(db, tenant_id, [(spec, params)])
        except Exception:
            return "protected_target"
    return None
