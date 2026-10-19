"""What can this role see (phase 77, D-09, D-10, SC3).

Pure functions. The set of visible screens is computed by the same pipeline that delivers
permissions to a user (``rbac_service.granted_permissions``): the role's effective permissions,
``rbac_defaults.deliverable_closure``, then ``tenant_features.apply_tenant``. Nothing here is a
second rule, so the view cannot drift from what ``/login`` and ``/me`` hand out (SC3), and the UI
only renders this payload (PROH-77-07).
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

import permission_vocabulary
import rbac_defaults
import tenant_features

WILDCARD = "*"


def _closed(effective: Iterable[str]) -> List[str]:
    return rbac_defaults.deliverable_closure(effective, permission_vocabulary.KNOWN_PERMISSIONS)


def delivered_for(effective: Iterable[str], enabled: Optional[Iterable[str]], *, narrowed: bool) -> List[str]:
    """The permission list a holder of ``effective`` is handed (``["*"]`` for the super-admin tier).

    ``narrowed`` applies the tenant's feature switches (``apply_tenant``, markers included);
    platform roles and an unselected tenant are not narrowed.
    """
    effective = list(effective)
    if WILDCARD in effective:
        return [WILDCARD]
    closed = _closed(effective)
    return tenant_features.apply_tenant(closed, enabled) if narrowed else closed


def _access(permission: str, delivered: set) -> str:
    """"manage" when the role holds a manage: permission paired with the screen's permission."""
    if WILDCARD in delivered or permission.startswith("manage:"):
        return "manage"
    if permission.startswith("view:") and "manage:" + permission[len("view:"):] in delivered:
        return "manage"
    return "view"


def build_visibility(*, role_id: str, role_name: str, built_in: bool, effective: Iterable[str],
                     enabled: Optional[Iterable[str]], narrowed: bool, basis: Dict[str, Any]) -> Dict[str, Any]:
    """The visibility payload: every sidebar screen grouped in manifest order, each visible
    screen marked view or manage, and the screens granted but switched off listed apart."""
    effective = list(effective)
    delivered_list = delivered_for(effective, enabled, narrowed=narrowed)
    delivered = set(delivered_list)
    everything = WILDCARD in delivered
    closed = set() if everything else set(_closed(effective))
    groups = {gid: {"id": gid, "title": title, "total": 0, "visibleCount": 0, "screens": [], "switchedOff": []}
              for gid, title in tenant_features.NAV_GROUPS}
    visible_total = 0
    for view, label, group_id, permission in tenant_features.NAV_SCREENS:
        group = groups[group_id]
        group["total"] += 1
        marker = f"{tenant_features.SCREEN_OFF_PREFIX}{view}" in delivered
        visible = everything or (permission in delivered and not marker)
        if visible:
            group["screens"].append({"view": view, "label": label, "access": _access(permission, delivered)})
            group["visibleCount"] += 1
            visible_total += 1
        elif marker or (permission in closed and permission not in delivered):
            group["switchedOff"].append({"view": view, "label": label})
    return {
        "roleId": role_id, "roleName": role_name, "builtIn": built_in, "basis": basis,
        "visibleCount": visible_total, "totalCount": len(tenant_features.NAV_SCREENS),
        "groups": list(groups.values()),
    }
