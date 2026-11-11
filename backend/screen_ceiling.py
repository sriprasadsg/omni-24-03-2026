"""One screen-ceiling check for every writer of a tenant's screen list (Phase 88, D-27, D-28, D-30, D-40).

A plan is a ceiling on the screens (switch keys) a tenant can have (D-27). The partner path (a partner's
customer: inside both the partner's own ceiling and the customer's plan, D-30) and the Super Admin path
(the plan only, D-40) both call ``final_screens`` with a list of limits, so the two cannot drift.

Screens a tenant already has outside a limit are "kept" (D-28): they may be re-submitted and stay on,
and a plan change or a ceiling edit never switches one off; only a new screen outside a limit is refused.
``sticky`` screens (the partner path passes the ones outside the partner's own ceiling) stay on even when
not submitted, as in Phase 87. ``plan_allowed`` reads the stored plans document at once (no cache, D-14);
only the shipped seed file (shared/plan-screen-seed.json, D-29, D-46) is cached, never the database.
"""
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Set, Tuple

import plan_service
import tenant_features

SEED_PATH = Path(__file__).resolve().parent.parent / "shared" / "plan-screen-seed.json"
_seed_cache: Dict[str, List[str]] = {}

# (allowed set, message template using {label} and {plan}, refusal code)
Limit = Tuple[Set[str], str, str]


class CeilingError(Exception):
    """A refused screen list: a stable ``code``, the sentence the user reads, and extra fields (screen, parent)."""

    def __init__(self, code: str, message: str, **numbers: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.numbers: Dict[str, Any] = numbers


def seed_screens(plan: str) -> List[str]:
    """The committed D-29 screen list for ``plan``; Custom, like any plan outside the file, gets every switch."""
    if not _seed_cache:
        with open(SEED_PATH, encoding="utf-8") as handle:
            _seed_cache.update({k: list(v) for k, v in json.load(handle)["plans"].items()})
    return list(_seed_cache.get(plan) or sorted(tenant_features.SWITCHABLE))


async def plan_allowed(db, plan: Any, *, exempt: bool = False) -> Set[str]:
    """The switches ``plan`` allows, read from the stored plans document now (D-14), plus the start screens.

    Custom and the platform organization (``exempt``) allow every switch (D-17, D-26); a stored ``"all"`` does
    too; a missing document or ``screens`` field falls back to the seed."""
    key = plan_service.normalize_plan(plan) or "Free"
    everything = set(tenant_features.SWITCHABLE)
    if exempt or key == "Custom":
        base = everything
    else:
        doc = await plan_service._raw(db)[plan_service.COLLECTION].find_one({"key": key}, {"_id": 0, "screens": 1})
        screens = (doc or {}).get("screens")
        if screens == "all":
            base = everything
        elif isinstance(screens, list):
            base = {s for s in screens if isinstance(s, str)}
        else:
            base = set(seed_screens(key))
    return base | set(tenant_features.START_FEATURES)


def _label(screen: str) -> str:
    return tenant_features.SWITCH_LABELS.get(screen, screen)


def final_screens(limits: Sequence[Limit], submitted: Iterable[Any], current: Iterable[Any], *,
                  sticky: Iterable[str] = (), plan: str = "", passthrough_prefixes: Tuple[str, ...] = ()) -> List[str]:
    """The screen list to store: the submitted order de-duplicated, then the sticky screens in their stored
    order, then any missing start screen. Refuses ``all``, unknown strings (``invalid_screen``), a new screen
    outside a limit (that limit's code) and a switch whose parent is missing (``missing_parent``).

    Entries starting with one of ``passthrough_prefixes`` are not switches and are stored as submitted."""
    limits = list(limits)
    stored = [s for s in dict.fromkeys(s for s in current if isinstance(s, str))]
    sticky = list(dict.fromkeys(sticky))

    def passthrough(value: str) -> bool:
        return bool(passthrough_prefixes) and value.startswith(tuple(passthrough_prefixes))

    kept = [s for s in stored if not passthrough(s) and not all(s in allowed for allowed, _, _ in limits)]
    known = set(tenant_features.SWITCHABLE) | set(tenant_features.START_FEATURES) | set(kept)
    known.discard(tenant_features.ALL_FEATURES)
    submitted = list(submitted)
    for value in submitted:
        if not isinstance(value, str) or not (value in known or passthrough(value)):
            raise CeilingError("invalid_screen", f"'{str(value)[:60]}' is not a screen that can be sold.")
    wanted = list(dict.fromkeys(submitted))
    for value in wanted:
        if passthrough(value) or value in kept:
            continue
        for allowed, message, code in limits:
            if value not in allowed:
                raise CeilingError(code, message.format(label=_label(value), plan=plan), screen=value)
    final = list(dict.fromkeys([*wanted, *sticky, *tenant_features.START_FEATURES]))
    for value in final:
        parent = tenant_features.SWITCH_PARENTS.get(value)
        if value not in kept and value not in sticky and parent is not None and parent not in final:
            raise CeilingError("missing_parent", f"{_label(value)} needs {_label(parent)}.", screen=value, parent=parent)
    return final
