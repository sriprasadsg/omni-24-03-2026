"""Mount-time catalogue guards (Phase 76).

Every ``catalogue_mounts_*.py`` file in this directory exports a module-level
``MOUNTS`` dict keyed by ``(module_name, attr)`` whose value is a
``catalogue_guard`` dependency. ``router_registry._load`` adds the matching
dependency to ``include_router`` so the route files themselves stay untouched.

A broken slice file must stop startup: import errors and duplicate keys
propagate, they are never swallowed.
"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from fastapi import Depends


def _collect() -> Dict[Tuple[str, str], Callable]:
    guards: Dict[Tuple[str, str], Callable] = {}
    here = Path(__file__).parent
    for path in sorted(here.glob("catalogue_mounts_*.py")):
        mod = importlib.import_module(path.stem)
        for key, guard in getattr(mod, "MOUNTS", {}).items():
            if key in guards:
                raise ValueError(f"duplicate catalogue mount for {key} (second definition in {path.name})")
            guards[key] = guard
    return guards


MOUNT_GUARDS: Dict[Tuple[str, str], Callable] = _collect()


def mount_dependencies(module_name: str, attr: str) -> List:
    """``[Depends(guard)]`` for a guarded router, otherwise an empty list."""
    guard = MOUNT_GUARDS.get((module_name, attr))
    return [Depends(guard)] if guard is not None else []
