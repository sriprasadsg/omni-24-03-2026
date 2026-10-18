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

Every sidebar item a tenant role can reach has a switch of its own: its permission's switch
when no other item shares that permission, else a ``screen:<view>`` switch. A screen switch
needs the permission the item's manifest entry names; its optional parent is the switch it
sits under in Manage Tenant.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Optional, Tuple

import rbac_defaults

_CATALOGUE_PATH = Path(__file__).resolve().parent.parent / "shared" / "tenant-feature-switches.json"
ALL_FEATURES = "all"


_MANIFEST_PATH = _CATALOGUE_PATH.parent / "catalogue-access.json"
SCREEN_PREFIX = "screen:"


def _load_switches(path: Path = _CATALOGUE_PATH) -> List[Dict[str, Any]]:
    """Every switch entry in the catalogue, checked: unique permissions, known parents."""
    with open(path, encoding="utf-8") as handle:
        catalogue = json.load(handle)
    # Each entry remembers whether its group wants every screen ticked explicitly (_explicit).
    features = [{**feature, "_explicit": bool(group.get("explicitScreens"))}
                for group in catalogue["groups"] for feature in group["features"]]
    seen = set()
    for feature in features:
        if feature["permission"] in seen:
            raise ValueError(f"duplicate feature switch {feature['permission']!r} in {path.name}")
        seen.add(feature["permission"])
    for feature in features:
        if feature.get("parent") is not None and feature["parent"] not in seen:
            raise ValueError(f"feature switch {feature['permission']!r} names unknown parent {feature['parent']!r}")
    return features


def _load_manifest(path: Path = _MANIFEST_PATH) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


_SWITCHES = _load_switches()
_MANIFEST = _load_manifest()
SWITCH_PARENTS: Dict[str, Optional[str]] = {f["permission"]: f.get("parent") for f in _SWITCHES}
SWITCHABLE: FrozenSet[str] = frozenset(SWITCH_PARENTS)
# Resources whose every permission goes with an off view:X switch.
_VIEW_RESOURCES: FrozenSet[str] = frozenset(p[len("view:"):] for p in SWITCHABLE if p.startswith("view:"))


def _screen_switches() -> Dict[str, str]:
    """``{view: the permission its manifest entry needs}`` for every "screen:<view>" switch."""
    needs = {entry["view"]: entry["permission"] for entry in _MANIFEST["catalogues"]}
    screens = {}
    for perm in SWITCH_PARENTS:
        if perm.startswith(SCREEN_PREFIX):
            view = perm[len(SCREEN_PREFIX):]
            if view not in needs:
                raise ValueError(f"screen switch {perm!r} names no catalogue view")
            screens[view] = needs[view]
    return screens


# Per-screen switches ("screen:<view>"): one sidebar item whose permission other items share,
# or that no permission switch covers (Overview, Tickets, My Tasks ...).
SCREEN_SWITCHES: Dict[str, str] = _screen_switches()
# Screens the sidebar hides when off but whose routes stay open: other screens call them too.
HIDE_ONLY_SCREENS: FrozenSet[str] = frozenset(
    f["permission"][len(SCREEN_PREFIX):] for f in _SWITCHES
    if f["permission"].startswith(SCREEN_PREFIX) and f.get("hideOnly"))
# Screens of the Security and Compliance sidebar sections: on only when a Super Admin ticks them,
# never added because their feature is on (new tenants start without them).
EXPLICIT_SCREENS: FrozenSet[str] = frozenset(
    f["permission"][len(SCREEN_PREFIX):] for f in _SWITCHES
    if f["permission"].startswith(SCREEN_PREFIX) and f["_explicit"])


def _route_owners(manifest: Dict[str, Any] = _MANIFEST) -> List[tuple]:
    """(route prefix, owning view) from the sidebar manifest, longest prefix first."""
    owners = [(prefix, entry["view"]) for entry in manifest["catalogues"] for prefix in entry.get("routes") or []]
    return sorted(owners, key=lambda item: -len(item[0]))


_ROUTE_OWNERS = _route_owners()


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


SCREEN_OFF_PREFIX = "screen-off:"


def screen_permissions(perms: Iterable[str], enabled: Optional[Iterable[str]]) -> List[str]:
    """``screen:<view>`` for every switched screen whose needed permission is in ``perms`` and whose
    switch (and parent switch) is on: what the route middleware checks."""
    held, off = set(perms), switched_off(enabled)
    return [f"{SCREEN_PREFIX}{view}" for view, needs in SCREEN_SWITCHES.items()
            if needs in held and f"{SCREEN_PREFIX}{view}" not in off]


def hidden_screens(perms: Iterable[str], enabled: Optional[Iterable[str]]) -> List[str]:
    """``screen-off:<view>`` for every switched screen the user would otherwise reach (its needed
    permission is held) but that is switched off; delivered with the permissions so the UI hides
    it. A tenant with every screen on gets no markers, so its list is the role's permissions."""
    held, on = set(perms), set(screen_permissions(perms, enabled))
    return [f"{SCREEN_OFF_PREFIX}{view}" for view, needs in SCREEN_SWITCHES.items()
            if needs in held and f"{SCREEN_PREFIX}{view}" not in on]


# Every sidebar screen of the shared manifest, in manifest order: (view, label, group id, permission).
NAV_SCREENS: Tuple[Tuple[str, str, str, str], ...] = tuple(
    (entry["view"], entry["label"], entry["group"], entry["permission"])
    for entry in _MANIFEST["catalogues"] if entry.get("nav"))
# The manifest's sidebar sections, in order: (id, title).
NAV_GROUPS: Tuple[Tuple[str, str], ...] = tuple((group["id"], group["title"]) for group in _MANIFEST["groups"])


def switched_off_nav_screens(perms: Iterable[str], narrowed: Iterable[str]) -> List[str]:
    """``screen-off:<view>`` for every sidebar screen whose permission the role holds (``perms``)
    but the tenant's switches removed (it is missing from ``narrowed``), in manifest order (D-16).

    This is what lets the UI say "switched off for your organization" for a screen the role
    would otherwise reach, instead of treating it like a screen the role lacks."""
    held, kept = set(perms), set(narrowed)
    return [f"{SCREEN_OFF_PREFIX}{view}" for view, _label, _group, needs in NAV_SCREENS
            if needs in held and needs not in kept]


def apply_tenant(perms: Iterable[str], enabled: Optional[Iterable[str]]) -> List[str]:
    """``perms`` narrowed by the tenant's switches, followed by the D-16 ``screen-off:<view>``
    markers (per-screen switches first, then every other switched-off sidebar screen), each
    once, in first-seen order. A tenant with every switch on gets no markers.

    The one step shared by ``rbac_service.granted_permissions`` and its fallback, and reused
    by the role visibility view (plan 77-07)."""
    perms = list(perms)
    narrowed = narrow(perms, enabled)
    markers = hidden_screens(narrowed, enabled) + switched_off_nav_screens(perms, narrowed)
    return list(dict.fromkeys(narrowed + markers))


def screen_of(path: str) -> Optional[str]:
    """The switched screen that owns ``path`` (longest manifest route prefix), if its switch
    guards routes (hide-only screens do not)."""
    for prefix, view in _ROUTE_OWNERS:
        if path == prefix or path.startswith(prefix + "/"):
            return view if view in SCREEN_SWITCHES and view not in HIDE_ONLY_SCREENS else None
    return None


def with_all_screens(features: Iterable[str]) -> List[str]:
    """``features`` plus every screen switch that has no parent or whose parent switch is in it
    (new tenants, and the migrations that introduced screen switches, keep every screen of a
    feature they have), except the Security and Compliance screens: a Super Admin ticks those."""
    features = list(features)
    have = set(features)
    screens = [f"{SCREEN_PREFIX}{view}" for view in SCREEN_SWITCHES if view not in EXPLICIT_SCREENS]
    return features + [s for s in screens
                       if s not in have and (SWITCH_PARENTS[s] is None or SWITCH_PARENTS[s] in have)]


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
