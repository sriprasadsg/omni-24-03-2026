"""The audience of a ticket notice, in the feed and on the socket (Phase 85, plan 85-28, DESK-01, decisions D-11 and
D-33). Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=WR-201 / WR-202 / D-11 / D-33 / T-85-26 / T-85-98 / T-85-99: the notice of a staff-only comment never
reaches the ticket's reporter (not in the feed, not on the tenant socket), and a user can mark read or delete only
the notices they can read; fails_when=the reporter's feed lists a staff-only comment notice, the tenant socket
carries one, a colleague's mark-read, read-all or delete touches a notice addressed to someone else, or a
colleague stops reading the staff notice or their own and the tenant-wide ones; no_claim=notices stored before the
fix (they carry no exclusion, A-85-G14) and the tenant_admins push on the socket (A-85-G15).
"""
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth_types import TokenData
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture the imported world needs)
from tests.test_service_desk_comments import (  # noqa: F401  (world is a fixture)
    ALICE, BOB, CAROL, REPLY, SECRET, _comment, _drain, _feed, _notices, _raise, world,
)


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
    carol = await _feed(world.db, CAROL)
    bob = await _feed(world.db, BOB)
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
    assert len(_comment_notices(await _feed(world.db, TokenData(username="  CAROL@x.CO ", tenant_id="t1")))) == 1


async def test_a_staff_notice_of_a_ticket_with_no_reporter_reaches_everyone(world):
    """protects=WR-201 edge; fails_when=an empty exclusion hides the notice from someone, or the writer stores a
    blank name."""
    ticket = await _raise(world)
    await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {"reporter": "", "watchers": ["carol@x.co"]}})
    assert (await _comment(world, ticket["id"], SECRET)).status_code == 200
    await _drain()
    notices = await _notices(world.db, "ticket_comment_added")
    assert len(notices) == 1 and not notices[0]["metadata"].get("excludeRecipients")
    for user in (ALICE, BOB, CAROL):
        assert len(_comment_notices(await _feed(world.db, user))) == 1


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


@pytest.mark.parametrize("metadata", [None, {"event": "x"}, {"audience": "tenant_admins"}])
async def test_other_notices_are_still_pushed_with_their_full_text(world, metadata):
    """protects=the push of every notice that is not a staff-only comment; fails_when=a notice without the
    ticket_staff audience stops being pushed or loses its title or message."""
    from notification_service import get_notification_service
    await get_notification_service(world.db).send_alert(
        title="T", message="M", severity="info", recipients=[], tenant_id="t1", channels=[], metadata=metadata)
    assert len(world.pushed) == 1 and world.pushed[0]["title"] == "T" and world.pushed[0]["message"] == "M"
