"""The widget catalogue tenant admins build dashboards from (shared/dashboard-widgets.json).

Every widget belongs to one screen of the shared manifest (shared/catalogue-access.json), so a
widget is offered and shown only where that screen is: the role must read it and the tenant must
have it switched on (bought). ``can_read_view`` is the server twin of the UI's
``utils/viewAccess.canReadView`` and reads the same delivered permission list.
"""
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import rbac_defaults
import tenant_features
from rbac_utils import is_super_admin

_SHARED = Path(__file__).resolve().parent.parent / "shared"


def _load(name: str) -> Any:
    with open(_SHARED / name, encoding="utf-8") as handle:
        return json.load(handle)


CATALOGUE: Dict[str, Any] = _load("dashboard-widgets.json")
GRID: Dict[str, int] = CATALOGUE["grid"]
WIDGETS: Dict[str, Dict[str, Any]] = {w["id"]: w for w in CATALOGUE["widgets"]}
_VIEWS: Dict[str, Dict[str, Any]] = {
    entry["view"]: entry for entry in _load("catalogue-access.json")["catalogues"]}


def widget(widget_id: str) -> Optional[Dict[str, Any]]:
    return WIDGETS.get(widget_id)


def can_read_view(view: str, perms: Iterable[str], role: Optional[str]) -> bool:
    """May a user holding ``perms`` (the delivered list, with ``screen-off:`` markers) read ``view``?

    The manifest entry's read list (else its permission) must be held, and the screen must not
    be switched off for the tenant, except hide-only screens whose routes stay open. Platform
    roles skip the tenant switches; unknown views are never readable."""
    entry = _VIEWS.get(view)
    if entry is None:
        return False
    held = set(perms)
    if is_super_admin(role) or "*" in held:
        return True
    needed = entry.get("read") or [entry["permission"]]
    if not any(p in held for p in needed):
        return False
    if rbac_defaults.is_platform_role(role):
        return True
    return (f"{tenant_features.SCREEN_OFF_PREFIX}{view}" not in held
            or view in tenant_features.HIDE_ONLY_SCREENS)


def readable_widget_ids(perms: Iterable[str], role: Optional[str]) -> List[str]:
    """Catalogue ids whose screen the user can read, in catalogue order."""
    held = list(perms)
    return [w["id"] for w in CATALOGUE["widgets"] if can_read_view(w["view"], held, role)]
