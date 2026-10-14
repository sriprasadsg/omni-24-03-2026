"""Per-tenant feature switches (spec C6).

A Super Admin switches features on or off per tenant (Manage Tenant); the list lives in
``tenants.enabledFeatures``. This module turns that list into the permissions a tenant
user loses. The switch catalogue is ``shared/tenant-feature-switches.json``, which the
Manage Tenant screen reads too, so the screen and the server always agree.

Rules, applied to every role except the platform roles (spec C1):
  * a switch is off when it is missing from the tenant's list, or when its parent is off;
  * an off switch removes its own permission and, for an off ``view:X``, every permission
    on resource X (``manage:X``, ``remediate:X`` ...) so a write grant cannot stand in for
    the hidden read (catalogue guards accept ``manage:X`` for reads);
  * ``"all"`` in the list switches nothing off;
  * a missing tenant, a missing list or a failed lookup counts as an empty list: every
    switch is off (fail closed). Permissions outside the catalogue are never removed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Optional

import rbac_defaults

_CATALOGUE_PATH = Path(__file__).resolve().parent.parent / "shared" / "tenant-feature-switches.json"
ALL_FEATURES = "all"


def _load_parents(path: Path = _CATALOGUE_PATH) -> Dict[str, Optional[str]]:
    """``{permission: parent permission or None}`` for every switch in the catalogue."""
    with open(path, encoding="utf-8") as handle:
        catalogue = json.load(handle)
    parents: Dict[str, Optional[str]] = {}
    for group in catalogue["groups"]:
        for feature in group["features"]:
            perm = feature["permission"]
            if perm in parents:
                raise ValueError(f"duplicate feature switch {perm!r} in {path.name}")
            parents[perm] = feature.get("parent")
    for perm, parent in parents.items():
        if parent is not None and parent not in parents:
            raise ValueError(f"feature switch {perm!r} names unknown parent {parent!r}")
    return parents


SWITCH_PARENTS: Dict[str, Optional[str]] = _load_parents()
SWITCHABLE: FrozenSet[str] = frozenset(SWITCH_PARENTS)
# Resources whose every permission goes with an off view:X switch.
_VIEW_RESOURCES: FrozenSet[str] = frozenset(p[len("view:"):] for p in SWITCHABLE if p.startswith("view:"))


def _resource(perm: str) -> Optional[str]:
    return perm.split(":", 1)[1] if ":" in perm else None


def is_switchable(perm: str) -> bool:
    """True when some tenant's switches could remove ``perm`` (directly or as a view twin)."""
    return perm in SWITCHABLE or _resource(perm) in _VIEW_RESOURCES


def switched_off(enabled: Optional[Iterable[str]]) -> FrozenSet[str]:
    """The switches that are off for a tenant whose list is ``enabled``."""
    on = set(enabled or ())
    if ALL_FEATURES in on:
        return frozenset()

    def is_on(perm: str) -> bool:
        parent = SWITCH_PARENTS[perm]
        return perm in on and (parent is None or is_on(parent))

    return frozenset(p for p in SWITCHABLE if not is_on(p))


def narrow(perms: Iterable[str], enabled: Optional[Iterable[str]]) -> List[str]:
    """``perms`` without what the tenant's switches turn off, order kept."""
    off = switched_off(enabled)
    off_resources = {p[len("view:"):] for p in off if p.startswith("view:")}
    return [p for p in perms if p not in off and _resource(p) not in off_resources]


def applies_to(role: Optional[str]) -> bool:
    """Platform roles (owner, support, billing) work across tenants and are never switched."""
    return not rbac_defaults.is_platform_role(role)


async def enabled_features(tenant_id: Optional[str], get_db: Callable[[], Any]) -> List[str]:
    """The tenant's switch list; ``[]`` for no tenant id, no tenant or no list.

    ``get_db`` is called only when there is a tenant to read. The raw collection is read
    with an explicit id: /login has no tenant context, and callers only ever ask about the
    user's own tenant. Database errors propagate so the caller can fail closed.
    """
    if not tenant_id:
        return []
    db = get_db()
    raw = getattr(db, "_db", db)
    doc = await raw.tenants.find_one({"id": tenant_id}, {"_id": 0, "enabledFeatures": 1})
    features = (doc or {}).get("enabledFeatures")
    return [f for f in features if isinstance(f, str)] if isinstance(features, list) else []
