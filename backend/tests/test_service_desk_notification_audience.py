"""The audience of a ticket notice, in the feed and on the socket (Phase 85, plan 85-28, DESK-01, decisions D-11 and
D-33). Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=WR-201 / WR-202 / D-11 / D-33 / T-85-26 / T-85-98 / T-85-99: the notice of a staff-only comment never
reaches the ticket's reporter (not in the feed, not on the tenant socket), and a user can mark read or delete only
the notices they can read; fails_when=the reporter's feed lists a staff-only comment notice, the tenant socket
carries one, a colleague's mark-read, read-all or delete touches a notice addressed to someone else, or a
colleague stops reading the staff notice or their own and the tenant-wide ones; no_claim=notices stored before the
fix (they carry no exclusion, A-85-G14). A notice with any audience is never pushed on the socket (85-39, WR-602;
it replaces A-85-G15). The structural test
that every notice route calls the filter moved to test_notification_audience_structure.py (85-31), which scans the
whole backend; ticket_staff notices are read by ticket staff only (G-85-4 UD-2).
"""
import ast
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth_types import TokenData
from tenant_context import reset_tenant_id, set_tenant_id
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture the imported world needs)
from tests.test_service_desk_comments import (  # noqa: F401  (world is a fixture)
    ALICE, BOB, CAROL, REPLY, SECRET, _comment, _drain, _feed, _notices, _raise, world,
)
from tests.service_desk_support import portal_user


READ = ("view:dashboard",)
STAFF = ("view:dashboard", "manage:tickets")          # IT ticket staff (G-85-4 UD-1)
ERIN = portal_user("t1", "erin@x.co")                  # a requester colleague: neither reporter nor staff


def _comment_notices(feed):
    return [n for n in feed if n["metadata"] and n["metadata"].get("event") == "ticket_comment_added"]


async def _staff_comment_world(world):
    """Alice raises, Carol and Alice watch, Bob (the assignee) writes a staff-only comment."""
    ticket = await _raise(world)
    await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {"watchers": ["carol@x.co", "alice@x.co"]}})
    assert (await _comment(world, ticket["id"], SECRET)).status_code == 200
    await _drain()
    return ticket


# ---------------------------------------------------------------- Task 1: the feed

async def test_the_staff_notice_names_the_reporter_as_excluded(world):
    """protects=WR-201 writer; fails_when=the stored staff notice carries no exclusion, or the exclusion is not the
    reporter (stripped, casefolded)."""
    await _staff_comment_world(world)
    notices = await _notices(world.db, "ticket_comment_added")
    assert len(notices) == 1
    assert notices[0]["metadata"]["audience"] == "ticket_staff"
    assert notices[0]["metadata"]["excludeRecipients"] == ["alice@x.co"]


async def test_the_reporter_never_reads_the_staff_notice_but_colleagues_do(world):
    """protects=WR-201 / D-11 / T-85-98 reader; fails_when=Alice's feed lists the staff-only comment notice, or
    Carol or Bob stops reading it with its title."""
    await _staff_comment_world(world)
    alice = await _feed(world.db, ALICE)
    carol = await _feed(world.db, CAROL, perms=STAFF)
    bob = await _feed(world.db, BOB, perms=STAFF)
    assert _comment_notices(alice) == []
    assert "New comment by bob@x.co" not in json.dumps(alice) and "hunter2" not in json.dumps(alice)
    assert len(_comment_notices(carol)) == 1 and "New comment by" in _comment_notices(carol)[0]["title"]
    assert len(_comment_notices(bob)) == 1


async def test_the_exclusion_matches_case_insensitively_and_by_email(world):
    """protects=WR-201 casefold; fails_when=a mixed-case username, or a user known by email, still reads the notice."""
    await _staff_comment_world(world)
    assert _comment_notices(await _feed(world.db, TokenData(username="  ALICE@x.CO ", tenant_id="t1"))) == []
    by_email = SimpleNamespace(username="alice", email="Alice@X.co", role="user", tenant_id="t1")
    assert _comment_notices(await _feed(world.db, by_email)) == []
    assert len(_comment_notices(await _feed(
        world.db, TokenData(username="  CAROL@x.CO ", tenant_id="t1"), perms=STAFF))) == 1


async def test_a_staff_notice_of_a_ticket_with_no_reporter_reaches_every_staff_member(world):
    """protects=WR-201 edge / D-11; fails_when=an empty exclusion hides the notice from a staff member, the writer
    stores a blank name, or the requester colleague reads it (ticket_staff notices are for staff)."""
    ticket = await _raise(world)
    await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {"reporter": "", "watchers": ["carol@x.co"]}})
    assert (await _comment(world, ticket["id"], SECRET)).status_code == 200
    await _drain()
    notices = await _notices(world.db, "ticket_comment_added")
    assert len(notices) == 1 and not notices[0]["metadata"].get("excludeRecipients")
    for user in (BOB, CAROL):
        assert len(_comment_notices(await _feed(world.db, user, perms=STAFF))) == 1
    assert _comment_notices(await _feed(world.db, ALICE)) == []


# ---------------------------------------------------------------- Task 2: the socket

async def test_a_staff_comment_is_not_pushed_on_the_tenant_socket_at_all(world):
    """protects=WR-201 socket / T-85-98; fails_when=any push carries the staff notice (its event, ticket id,
    excluded address or the author's name) to the tenant's sockets, or the notice is no longer stored once."""
    await _staff_comment_world(world)
    assert len(await _notices(world.db, "ticket_comment_added")) == 1
    pushed = json.dumps(world.pushed)
    assert [p for p in world.pushed if (p["metadata"] or {}).get("event") == "ticket_comment_added"] == []
    assert "ticket_staff" not in pushed and "alice@x.co" not in pushed and "bob@x.co" not in pushed


async def test_a_requester_reply_keeps_its_blank_push_for_the_recipient(world):
    """protects=D-33 socket; fails_when=the recipient notice stops being pushed, or its message goes out."""
    ticket = await _raise(world)
    assert (await _comment(world, ticket["id"], REPLY, visibility="requester")).status_code == 200
    await _drain()
    pushes = [p for p in world.pushed if p["metadata"].get("event") == "ticket_comment_added"]
    assert len(pushes) == 1 and pushes[0]["metadata"]["recipient"] == "alice@x.co" and pushes[0]["message"] == ""


@pytest.mark.parametrize("metadata", [None, {"event": "x"}])
async def test_untagged_notices_are_still_pushed_with_their_full_text(world, metadata):
    """protects=the push of every notice that carries no audience; fails_when=a notice without an audience
    stops being pushed or loses its title or message."""
    from notification_service import get_notification_service
    await get_notification_service(world.db).send_alert(
        title="T", message="M", severity="info", recipients=[], tenant_id="t1", channels=[], metadata=metadata)
    assert len(world.pushed) == 1 and world.pushed[0]["title"] == "T" and world.pushed[0]["message"] == "M"


@pytest.mark.parametrize("audience", ["tenant_admins", "ticket_staff", "anything_new"])
async def test_a_notice_with_an_audience_is_stored_once_and_never_pushed(world, audience):
    """protects=WR-602 / G-85-5 / PROH-85-32 / T-85-134; fails_when=a notice whose metadata carries any
    audience reaches the tenant-wide socket (which cannot apply reader_filter), or is not stored exactly once."""
    from notification_service import get_notification_service
    await get_notification_service(world.db).send_alert(
        title="T", message="host WIN-7 uses 5 of 5 seats", severity="info", recipients=[], tenant_id="t1",
        channels=[], metadata={"audience": audience})
    assert world.pushed == []
    assert await world.db.notifications.count_documents({"metadata.audience": audience}) == 1


@pytest.mark.parametrize("metadata, expected", [
    (None, True), ({}, True), ({"event": "x"}, True), ({"recipient": "a@x.co"}, True),
    ({"audience": "tenant_admins"}, False), ({"audience": "ticket_staff"}, False), ({"audience": "anything_new"}, False),
    ("", True), ("audience", False), (["tenant_admins"], False),
])
def test_broadcastable_is_true_only_without_an_audience(metadata, expected):
    """protects=WR-602 push rule; fails_when=a notice with an audience is broadcastable, or one without is not;
    a non-dict value is broadcastable only when it is None or empty."""
    from notification_audience import broadcastable
    assert broadcastable(metadata) is expected


def _broadcast_functions(tree):
    """The functions of one module that import or call broadcast_notification (any alias) and whether each
    also calls broadcastable."""
    aliases = {"broadcast_notification"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            aliases |= {a.asname for a in node.names if a.name == "broadcast_notification" and a.asname}
    found = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        uses, gated = False, False
        for node in ast.walk(fn):
            if isinstance(node, ast.ImportFrom) and any(a.name == "broadcast_notification" for a in node.names):
                uses = True
            elif isinstance(node, ast.Name) and node.id in aliases:
                uses = True
            elif isinstance(node, ast.Attribute) and node.attr == "broadcast_notification":
                uses = True
            if isinstance(node, ast.Call):
                callee = node.func
                if (isinstance(callee, ast.Name) and callee.id == "broadcastable") or \
                        (isinstance(callee, ast.Attribute) and callee.attr == "broadcastable"):
                    gated = True
        if uses:
            found.append((fn.name, gated))
    return found


def _scan_broadcast_callers(root):
    skip = {"venv", "tests", "__pycache__", "node_modules"}
    result = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")]
        for name in filenames:
            if not name.endswith(".py") or name == "websocket_manager.py":
                continue
            path = os.path.join(dirpath, name)
            with open(path, "rb") as handle:
                raw = handle.read()
            if b"broadcast_notification" in raw:
                result[os.path.relpath(path, root)] = _broadcast_functions(ast.parse(raw))
    return result


def test_every_caller_of_the_tenant_broadcast_asks_broadcastable_first():
    """protects=WR-602 / PROH-85-32 for future callers; fails_when=a backend function pushes through
    broadcast_notification without calling broadcastable, or the scan stops finding the two known callers."""
    backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    callers = _scan_broadcast_callers(backend)
    names = {(path, fn) for path, fns in callers.items() for fn, _ in fns}
    assert ("notification_service.py", "send_alert") in names and ("pending_agents.py", "_post_in_app") in names
    ungated = [(path, fn) for path, fns in callers.items() for fn, gated in fns if not gated]
    assert ungated == []


def test_the_caller_scan_fails_for_a_function_that_broadcasts_without_the_rule():
    """protects=the scan itself; fails_when=an aliased or attribute call of broadcast_notification with no
    broadcastable call passes, or a gated one fails."""
    bad = ("async def a(t, m):\n    from websocket_manager import broadcast_notification as push\n    await push(t, m)\n"
           "async def b(t, m):\n    import websocket_manager\n    await websocket_manager.broadcast_notification(t, m)\n")
    good = ("async def c(t, m):\n    from notification_audience import broadcastable\n"
            "    from websocket_manager import broadcast_notification\n"
            "    if broadcastable(m):\n        await broadcast_notification(t, m)\n")
    assert _broadcast_functions(ast.parse(bad)) == [("a", False), ("b", False)]
    assert _broadcast_functions(ast.parse(good)) == [("c", True)]


# ---------------------------------------------------------------- Task 3: the write routes

ADMIN = ("view:dashboard", "manage:agents")


async def _seed(db):
    def notice(alert_id, tenant="t1", **metadata):
        return {"alert_id": alert_id, "tenantId": tenant, "sent_at": "2026-11-08T00:00:01", "read": False,
                "metadata": metadata or None}
    await db.notifications.insert_many([
        notice("alice-only", recipient="alice@x.co"),
        notice("carol-only", recipient="carol@x.co"),
        notice("tenant-wide"),
        notice("admins", audience="tenant_admins"),
        notice("staff", audience="ticket_staff", excludeRecipients=["alice@x.co"]),
        notice("other-tenant", tenant="t2"),
    ])


async def _call(db, route, user, *args, perms=READ, tenant="t1", **kwargs):
    """Run a notification route function as ``user`` (the way the feed helper of the comments tests does)."""
    import notification_endpoints as ne
    from database import TenantIsolatedDatabase
    token = set_tenant_id(tenant)
    try:
        with patch.object(ne, "get_database", return_value=TenantIsolatedDatabase(db)):
            with patch.object(ne.rbac_service, "get_user_permissions", AsyncMock(return_value=list(perms))):
                return await getattr(ne, route)(*args, current_user=user, **kwargs)
    finally:
        reset_tenant_id(token)


async def _read_ids(db):
    return sorted([n["alert_id"] for n in await db.notifications.find({"read": True}, {"_id": 0}).to_list(50)])


async def test_a_colleague_cannot_mark_an_addressed_notice_read(world):
    """protects=WR-202 / D-33 / T-85-99; fails_when=Carol marks Alice's notice read, or the refusal is not a 404."""
    await _seed(world.db)
    with pytest.raises(HTTPException) as refused:
        await _call(world.db, "mark_as_read", CAROL, "alice-only")
    assert refused.value.status_code == 404
    assert (await world.db.notifications.find_one({"alert_id": "alice-only"}))["read"] is False


async def test_a_colleague_cannot_delete_an_addressed_notice(world):
    """protects=WR-202 / D-33 / T-85-99; fails_when=Carol deletes Alice's notice, or the refusal is not a 404."""
    await _seed(world.db)
    with pytest.raises(HTTPException) as refused:
        await _call(world.db, "delete_notification", CAROL, "alice-only")
    assert refused.value.status_code == 404
    assert await world.db.notifications.count_documents({"alert_id": "alice-only"}) == 1


async def test_read_all_without_ids_marks_only_what_the_reader_can_read(world):
    """protects=WR-202 / PROH-85-17; fails_when=read-all touches Alice's notice, the tenant_admins notice, another
    tenant's notice, or leaves Carol's own, the tenant-wide or the staff notice unread."""
    await _seed(world.db)
    result = await _call(world.db, "mark_all_as_read", CAROL, notification_ids=None, perms=STAFF)
    assert result == {"success": True, "modified_count": 3}
    assert await _read_ids(world.db) == ["carol-only", "staff", "tenant-wide"]


async def test_read_all_without_ticket_staff_permission_leaves_the_staff_notice_alone(world):
    """protects=D-11 / UD-2 / T-85-110 on the writers; fails_when=a reader without manage:tickets marks the
    ticket_staff notice read with read-all, or read-all stops marking their own and the tenant-wide ones."""
    await _seed(world.db)
    result = await _call(world.db, "mark_all_as_read", CAROL, notification_ids=None)
    assert result == {"success": True, "modified_count": 2}
    assert await _read_ids(world.db) == ["carol-only", "tenant-wide"]
    with pytest.raises(HTTPException) as refused:
        await _call(world.db, "delete_notification", CAROL, "staff")
    assert refused.value.status_code == 404


async def test_a_requester_colleague_has_no_staff_comment_notice_in_the_feed(world):
    """protects=D-11 / UD-2 / T-85-110; fails_when=Erin (a requester who is neither the reporter nor staff) lists
    the staff-only comment notice, or Carol or Bob (manage:tickets) stop reading it, or Alice reads it."""
    await _staff_comment_world(world)
    assert _comment_notices(await _feed(world.db, ERIN)) == []
    assert len(_comment_notices(await _feed(world.db, CAROL, perms=STAFF))) == 1
    assert len(_comment_notices(await _feed(world.db, BOB, perms=STAFF))) == 1
    assert _comment_notices(await _feed(world.db, ALICE)) == []


async def test_read_all_with_an_unreadable_id_modifies_nothing_for_it(world):
    """protects=WR-202; fails_when=listing Alice's notice id lets Carol mark it read."""
    await _seed(world.db)
    result = await _call(world.db, "mark_all_as_read", CAROL, notification_ids=["alice-only"])
    assert result == {"success": True, "modified_count": 0}
    assert await _read_ids(world.db) == []
    mixed = await _call(world.db, "mark_all_as_read", CAROL, notification_ids=["alice-only", "carol-only"])
    assert mixed["modified_count"] == 1 and await _read_ids(world.db) == ["carol-only"]


async def test_the_reporter_keeps_her_own_notices_but_not_the_staff_one(world):
    """protects=WR-202 / WR-201 on the writers; fails_when=Alice cannot mark read or delete her own addressed
    notice, or can still mark the staff notice that excludes her."""
    await _seed(world.db)
    with pytest.raises(HTTPException) as refused:
        await _call(world.db, "mark_as_read", ALICE, "staff", perms=STAFF)     # staff, but the notice excludes her
    assert refused.value.status_code == 404
    assert await _call(world.db, "mark_as_read", ALICE, "alice-only") == {"success": True}
    assert await _read_ids(world.db) == ["alice-only"]
    assert await _call(world.db, "delete_notification", ALICE, "alice-only") == {"success": True}
    assert await world.db.notifications.count_documents({"alert_id": "alice-only"}) == 0


async def test_the_tenant_admin_notice_needs_manage_agents_to_be_changed(world):
    """protects=WR-202 audience rule on the writers; fails_when=a user without manage:agents marks or deletes a
    tenant_admins notice, or one with it cannot."""
    await _seed(world.db)
    with pytest.raises(HTTPException) as refused:
        await _call(world.db, "mark_as_read", CAROL, "admins")
    assert refused.value.status_code == 404
    with pytest.raises(HTTPException):
        await _call(world.db, "delete_notification", CAROL, "admins")
    assert await _call(world.db, "mark_as_read", CAROL, "admins", perms=ADMIN) == {"success": True}
    assert await _call(world.db, "delete_notification", CAROL, "admins", perms=ADMIN) == {"success": True}
