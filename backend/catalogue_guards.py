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
  * Agent-capable reads (76-13, WR-01, D-02): ``agent_tolerant(guard)`` builds the same guard on
    ``get_current_user_or_agent`` and lets exactly the auth layer's agent identity (token role
    equal to the string ``agent``) through before any permission lookup. Every other caller,
    a role spelled ``Agent`` included, gets the full catalogue check (D-03).
  * Platform staff (76-13, WR-05): ``platform_read`` lists ``rbac_defaults.PLATFORM_ONLY_PERMISSIONS``
    entries. On a safe method a caller who fails the role check is still let through when
    ``has_platform_permission`` holds for one of them (platform role in the platform tenant, or
    the owner); a tenant role never passes and non-safe methods never use it.
  Both variants keep no per-request or cross-request state: the decision is a pure function of
  the TokenData, the HTTP method and the declared permission tuples.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Tuple

from fastapi import Depends, HTTPException, Request, status

from auth_types import TokenData
from authentication_service import AGENT_ROLE, get_current_user, get_current_user_or_agent
from rbac_defaults import PLATFORM_ONLY_PERMISSIONS
from rbac_service import rbac_service as _rbac_service
from rbac_utils import has_platform_permission, verify_permission

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
    user: TokenData,
    method: str,
    read: Tuple[str, ...],
    write: Tuple[str, ...],
    *,
    platform_read: Tuple[str, ...] = (),
) -> None:
    """Raise 403 unless the caller's role (then API-key scopes) allows the request."""
    accepted = _accepted(method, read, write)
    safe = method.upper() in SAFE_METHODS
    allowed = False
    for perm in accepted:
        if await verify_permission(user, perm):
            allowed = True
            break
    platform_held: List[str] = []
    if not allowed and safe:
        for perm in platform_read:
            if await has_platform_permission(user, perm):
                platform_held.append(perm)
        allowed = bool(platform_held)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required permission: {accepted[0]}",
        )
    # A key scoped to a catalogue's write permission has always been able to read it too
    # (ITAM's _require_itam_viewer accepts the manage:assets scope), so a safe request also
    # honours the write scopes. The role check above stays read-only (D-03). Platform staff
    # who passed through platform_read must hold a scope for the platform permission they used.
    if platform_held:
        scope_accepted = platform_held
    elif safe:
        scope_accepted = accepted + [p for p in write if p not in accepted]
    else:
        scope_accepted = accepted
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
    allow_agent: bool = False,
    platform_read: Tuple[str, ...] = (),
) -> Callable:
    """Build the dependency that enforces one catalogue's read/write permissions.

    ``allow_agent`` (only with ``get_current_user_or_agent``) skips the check for the agent
    identity; ``platform_read`` adds the platform-staff read rule. Both default off, so a guard
    built without them behaves, and is tagged, exactly as before.
    """
    read_t = _validated("read", read)
    write_t = _validated("write", write)
    if allow_agent and getattr(auth, "__qualname__", None) != "get_current_user_or_agent":
        raise ValueError(f"catalogue_guard {catalogue!r}: allow_agent requires auth=get_current_user_or_agent")
    platform_t = tuple(platform_read or ())
    for perm in platform_t:
        if perm not in PLATFORM_ONLY_PERMISSIONS:
            raise ValueError(f"catalogue_guard {catalogue!r}: platform_read entry {perm!r} "
                             f"is not a platform-only permission")

    async def _require_catalogue(request: Request, user: TokenData = Depends(auth)) -> TokenData:
        if allow_agent and getattr(user, "role", None) == AGENT_ROLE:
            return user  # D-02: the agent identity is never permission-checked; the route keeps its own agent checks
        await check_catalogue_access(user, request.method, read_t, write_t, platform_read=platform_t)
        return user

    tag: Dict[str, object] = {
        "catalogue": catalogue,
        "read": list(read_t),
        "write": list(write_t),
    }
    if allow_agent:
        tag["allow_agent"] = True
    if platform_t:
        tag["platform_read"] = list(platform_t)
    _require_catalogue.__catalogue_guard__ = tag  # type: ignore[attr-defined]
    return _require_catalogue


def agent_tolerant(guard: Callable) -> Callable:
    """The same catalogue guard for a route the endpoint agent also calls (WR-01, D-02)."""
    meta = getattr(guard, "__catalogue_guard__", None)
    if not meta:
        raise ValueError("agent_tolerant requires a catalogue_guard dependency")
    return catalogue_guard(
        meta["catalogue"],
        read=tuple(meta["read"]),
        write=tuple(meta["write"]),
        auth=get_current_user_or_agent,
        allow_agent=True,
    )


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
    "agent_tolerant",
]
