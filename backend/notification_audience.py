"""The one notice audience filter (Phase 85 gap G-85-4, CR-501, decisions D-11 and D-33).

Every route that reads or changes ``db.notifications`` for a signed-in user (the feed, mark-read, read-all, delete
and the history) starts its query from ``reader_filter``, so what a person can list is exactly what they can mark
or delete, and no second route can serve a notice the first one hides. The repository-wide scan in
tests/test_notification_audience_structure.py keeps it that way.

Module-level imports are limited to ``typing``, ``rbac_service`` and ``ticket_access`` so any module can import
this one without a cycle.
"""
from typing import Any, Dict, List

from rbac_service import rbac_service
from ticket_access import is_ticket_staff


def reader_names(user: Any) -> List[str]:
    """The reader's username and email, stripped and casefolded (empties dropped): how a notice names a person."""
    return [n for n in (str(getattr(user, f, "") or "").strip().casefold() for f in ("username", "email")) if n]


async def reader_filter(user: Any, tenant_id: str, *, all_tenants: bool = False) -> Dict[str, Any]:
    """The notices ``user`` may read.

    ``tenantId`` is the canonical tenant field; ``all_tenants`` drops that clause (the Super Admin history only)
    and leaves every per-person rule in place. A notice addressed to tenant admins needs ``*`` or
    ``manage:agents``, one addressed to ticket staff needs ``manage:tickets`` (D-11), a notice addressed to one
    person (``metadata.recipient``, stored lowercase) is read by that person only, and a notice that names the
    reader in ``metadata.excludeRecipients`` is never read by them (WR-201).
    """
    query: Dict[str, Any] = {} if all_tenants else {"tenantId": tenant_id}
    perms = await rbac_service.get_user_permissions(user)
    hidden = []
    if "*" not in perms and "manage:agents" not in perms:
        hidden.append("tenant_admins")  # carries host details of agents waiting for approval (spec C3)
    if not await is_ticket_staff(user, perms):
        hidden.append("ticket_staff")
    if hidden:
        query["metadata.audience"] = {"$nin": hidden}
    me = reader_names(user)
    query["$and"] = [
        {"$or": [
            {"metadata.recipient": {"$exists": False}},
            {"metadata.recipient": None},
            {"metadata.recipient": {"$in": me}},
        ]},
        {"metadata.excludeRecipients": {"$nin": me}},
    ]
    return query


def broadcastable(metadata: Any) -> bool:
    """Whether a notice may be pushed on the tenant-wide WebSocket: only when its metadata carries no audience.

    The tenant socket reaches every connected user of the tenant and cannot apply ``reader_filter``, so a notice
    addressed to an audience (``tenant_admins``, ``ticket_staff`` or any value added later) is stored once and read
    from the feed only (WR-602). ``metadata`` that is not a dict is broadcastable only when it is None or empty.
    """
    if not isinstance(metadata, dict):
        return not metadata
    return "audience" not in metadata
