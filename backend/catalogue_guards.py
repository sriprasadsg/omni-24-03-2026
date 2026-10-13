"""Catalogue access guard (Phase 76, ACC-03/ACC-04).

One FastAPI dependency per catalogue, mounted at router-include time from
``catalogue_mounts_*.py``. The guard is strictly additive: it runs next to the
permission dependencies a route already carries and never replaces them.

Rules (76-CONTEXT D-02, D-03, D-07):
  * Safe methods (GET/HEAD/OPTIONS) accept any declared read permission or its
    ``manage:`` twin. The twin closure lives here only; ``rbac_defaults`` and
    ``rbac_service`` keep the un-closed permission list that /me delivers.
  * Other methods accept exactly the declared write permissions.
  * The role check runs first (``verify_permission``, which already lets a
    super-admin through); API-key scope narrowing runs second, so a narrowed
    key is refused even when its owner's role allows the route.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Tuple

from fastapi import Depends, HTTPException, Request, status

from auth_types import TokenData
from authentication_service import get_current_user
from rbac_service import rbac_service as _rbac_service
from rbac_utils import verify_permission

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def manage_twin(perm: str) -> str:
    """``view:x`` -> ``manage:x``; any other string comes back unchanged."""
    if perm.startswith("view:"):
        return "manage:" + perm[len("view:"):]
    return perm


def _accepted(method: str, read: Tuple[str, ...], write: Tuple[str, ...]) -> List[str]:
    """Ordered, de-duplicated permission strings that satisfy this request."""
    if method.upper() in SAFE_METHODS:
        candidates: List[str] = []
        for perm in read:
            candidates.append(perm)
            candidates.append(manage_twin(perm))
    else:
        candidates = list(write)
    seen: List[str] = []
    for perm in candidates:
        if perm not in seen:
            seen.append(perm)
    return seen


async def check_catalogue_access(
    user: TokenData, method: str, read: Tuple[str, ...], write: Tuple[str, ...]
) -> None:
    """Raise 403 unless the caller's role (then API-key scopes) allows the request."""
    accepted = _accepted(method, read, write)
    allowed = False
    for perm in accepted:
        if await verify_permission(user, perm):
            allowed = True
            break
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required permission: {accepted[0]}",
        )
    # A key scoped to a catalogue's write permission has always been able to read it too
    # (ITAM's _require_itam_viewer accepts the manage:assets scope), so a safe request also
    # honours the write scopes. The role check above stays read-only (D-03).
    scope_accepted = accepted + [p for p in write if p not in accepted] if method.upper() in SAFE_METHODS else accepted
    if not any(_rbac_service._scopes_allow(user, perm) for perm in scope_accepted):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"API key scope does not permit: {accepted[0]}",
        )


def _validated(name: str, perms: Tuple[str, ...]) -> Tuple[str, ...]:
    if not isinstance(perms, (tuple, list)) or not perms:
        raise ValueError(f"catalogue_guard {name} must be a non-empty tuple of permission strings")
    for perm in perms:
        if not isinstance(perm, str) or ":" not in perm:
            raise ValueError(f"catalogue_guard {name} entry {perm!r} is not a 'verb:noun' permission")
    return tuple(perms)


def catalogue_guard(
    catalogue: str,
    *,
    read: Tuple[str, ...],
    write: Tuple[str, ...],
    auth: Callable = get_current_user,
) -> Callable:
    """Build the dependency that enforces one catalogue's read/write permissions."""
    read_t = _validated("read", read)
    write_t = _validated("write", write)

    async def _require_catalogue(request: Request, user: TokenData = Depends(auth)) -> TokenData:
        await check_catalogue_access(user, request.method, read_t, write_t)
        return user

    _require_catalogue.__catalogue_guard__ = {  # type: ignore[attr-defined]
        "catalogue": catalogue,
        "read": list(read_t),
        "write": list(write_t),
    }
    return _require_catalogue


def catalogue_exempt(reason: str) -> Callable:
    """Marker dependency for routes deliberately outside the catalogue guard."""
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("catalogue_exempt requires a non-blank reason")

    async def _catalogue_exempt_marker() -> None:
        return None

    _catalogue_exempt_marker.__catalogue_exempt__ = reason  # type: ignore[attr-defined]
    return _catalogue_exempt_marker


__all__ = [
    "SAFE_METHODS",
    "manage_twin",
    "check_catalogue_access",
    "catalogue_guard",
    "catalogue_exempt",
]
