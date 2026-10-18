"""The set of permission strings the platform knows about (Phase 77, D-11 and D-18).

``rbac_defaults.deliverable_closure`` derives ``view:X`` and ``request:X`` for every
``manage:X`` a role holds. Without a filter that would add dozens of meaningless
strings (``request:ai`` ...) to a tenant administrator, so the delivered closure is
intersected with this vocabulary: every string the role table, the sidebar manifest
(``shared/catalogue-access.json``) or the tenant switch catalogue
(``shared/tenant-feature-switches.json``) actually names.

Derived from those sources at import time; there is no literal permission list here
(the drift guard in test_rbac_defaults.py rejects one). Standard library plus
``rbac_defaults`` only, so it can be imported from ``rbac_service`` without a cycle.
"""
import json
from pathlib import Path
from typing import Any, FrozenSet, Iterable, Set

import rbac_defaults

_SHARED = Path(__file__).resolve().parent.parent / "shared"
_MANIFEST_PATH = _SHARED / "catalogue-access.json"
_SWITCHES_PATH = _SHARED / "tenant-feature-switches.json"
_NOT_A_PERMISSION_PREFIXES = ("screen:", "screen-off:")


def _load(path: Path) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _is_permission(value: Any) -> bool:
    return (isinstance(value, str) and ":" in value and value != "*"
            and not value.startswith(_NOT_A_PERMISSION_PREFIXES))


def _manifest_permissions(manifest: Any) -> Set[str]:
    found: Set[str] = set()
    for entry in manifest.get("catalogues", []):
        for key in ("permission", "read", "write"):
            value = entry.get(key)
            found.update(value if isinstance(value, list) else [value])
    return found


def _switch_permissions(catalogue: Any) -> Set[str]:
    return {feature.get("permission") for group in catalogue.get("groups", [])
            for feature in group.get("features", [])}


def build_vocabulary(manifest: Any, switches: Any) -> FrozenSet[str]:
    """Every known permission string from the role table, the manifest and the switch catalogue."""
    table: Iterable[str] = (perm for perms in rbac_defaults.ROLE_DEFAULTS.values() for perm in perms)
    found = (set(table) | set(rbac_defaults.PLATFORM_ONLY_PERMISSIONS)
             | set(rbac_defaults.SUPER_ADMIN_ONLY_PERMISSIONS)
             | _manifest_permissions(manifest) | _switch_permissions(switches))
    return frozenset(p for p in found if _is_permission(p))


KNOWN_PERMISSIONS: FrozenSet[str] = build_vocabulary(_load(_MANIFEST_PATH), _load(_SWITCHES_PATH))
