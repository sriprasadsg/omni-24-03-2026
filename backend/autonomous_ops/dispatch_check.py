"""Checks on what an autonomous decision will dispatch (GATE-03, GATE-04, GATE-08, GATE-10).

The gate used to decide a playbook on its first step only. These helpers give it the whole
plan: every main step and every compensation step with its own parameters, so each is
class-checked against the registry and IP-checked against the never-touch list, and the
decided plan is recorded on the ledger row.

A request carries its plan as ``steps`` / ``rollback`` (lists of ``{"action", "params"}``).
A request without ``steps`` is the single-params form: the steps are derived from ``actions``
plus the shared ``params``, so there is one internal source.

Raw Mongo handle and an explicit tenant only. Pure reads: nothing here writes, names the
autonomy stamp, or touches an LLM.
"""
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
