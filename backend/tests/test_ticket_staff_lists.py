"""Who sees which tickets in lists, counts, reports and exports (Phase 85, plan 85-33, gap G-85-4, WR-502).

Value: protects=WR-502 / G-85-4 UD-2 / PROH-85-24 / T-85-115 / T-85-116: GET /api/tickets, /stats, the
/reports/* routes and /export/csv hold only the tickets a caller who is not ticket staff raised, filtered in
the database query (so totals and pages agree), a name with regex characters matches only itself, and ticket
staff keep the whole tenant; fails_when=a requester lists, counts, reports or exports a colleague's ticket,
a reporter parameter or a search widens the scope, a regex-character name matches another person, a total
differs from the tickets returned, or staff lose a ticket; no_claim=the AI chat /tickets skill (A-85-G27)
and the single-ticket routes (85-32).
"""
import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.service_desk_support import desk_app, portal_user, seed_desk_tenant, staff_user

ALICE = portal_user("t1", "alice@x.co")           # a requester
BOB = staff_user("t1", "bob@x.co")                # a technician (manage:tickets)
ROOT = portal_user(None, "root@x.co", role="Super Admin")
DOTTY = portal_user("t1", "a.*@x.co")             # a name made of regex characters


@pytest.fixture
async def world(mongo_db, monkeypatch):  # noqa: F811
    await seed_desk_tenant(mongo_db, "t1")
    await seed_desk_tenant(mongo_db, "t2")
    return desk_app(mongo_db, monkeypatch)


async def _plant(world):
    """Five tickets of t1 (alice twice and once in another case, bob, a.lice, a.*) plus one of t2 by alice."""
    rows = [
        ("T1", "t1", "alice@x.co", "open", "Printer jam"),
        ("T2", "t1", "alice@x.co", "resolved", "Mail sync"),
        ("T3", "t1", "Alice@X.co", "closed", "Old VPN"),
        ("T4", "t1", "bob@x.co", "open", "Bob's secret salary question"),
        ("T5", "t1", "a.lice@x.co", "open", "Near miss"),
        ("T6", "t1", "a.*@x.co", "open", "Regex name"),
        ("T7", "t2", "alice@x.co", "open", "Other tenant"),
    ]
    for n, (tid, tenant, reporter, status, title) in enumerate(rows):
        await world.db.tickets.insert_one({
            "id": tid, "ticket_number": f"TKT-{tid}", "tenantId": tenant, "reporter": reporter, "status": status,
            "title": title, "description": "", "priority": "medium", "type": "incident", "assignee": None,
            "escalated": tid == "T4", "tags": [], "comments": [], "history": [],
            "created_at": f"2026-11-0{n + 1}T10:00:00+00:00", "updated_at": f"2026-11-0{n + 1}T10:00:00+00:00"})


def _ids(response):
    assert response.status_code == 200, response.text
    return sorted(t["id"] for t in response.json()["tickets"])


async def test_a_requester_lists_only_the_tickets_they_raised_and_the_total_agrees(world):
    """protects=UD-2 / T-85-115; fails_when=the list holds a colleague's ticket, the total counts one, or the
    reporter's name in another case misses a ticket."""
    await _plant(world)
    response = await world.call("GET", "/api/tickets", user=ALICE)
    assert _ids(response) == ["T1", "T2", "T3"]
    assert response.json()["total"] == 3
    paged = await world.call("GET", "/api/tickets?page_size=2&page=2", user=ALICE)
    assert paged.json()["total"] == 3 and len(paged.json()["tickets"]) == 1


async def test_a_reporter_parameter_or_a_search_cannot_widen_the_scope(world):
    """protects=UD-2; fails_when=?reporter= or ?search= shows a requester someone else's ticket."""
    await _plant(world)
    other = await world.call("GET", "/api/tickets?reporter=bob@x.co", user=ALICE)
    assert _ids(other) == [] and other.json()["total"] == 0
    found = await world.call("GET", "/api/tickets?search=salary", user=ALICE)
    assert _ids(found) == [] and found.json()["total"] == 0
    own = await world.call("GET", "/api/tickets?search=printer", user=ALICE)
    assert _ids(own) == ["T1"]


async def test_a_name_made_of_regex_characters_matches_only_itself(world):
    """protects=T-85-116; fails_when=a.*@x.co matches alice@x.co or a.lice@x.co tickets."""
    await _plant(world)
    assert _ids(await world.call("GET", "/api/tickets", user=DOTTY)) == ["T6"]
    nameless = portal_user("t1", "", role="user")
    assert _ids(await world.call("GET", "/api/tickets", user=nameless)) == []


async def test_staff_and_the_super_admin_list_everything_as_before(world):
    """protects=UD-2 unchanged for staff; fails_when=staff lose a ticket of their tenant, or the Super Admin loses a tenant."""
    await _plant(world)
    staff = await world.call("GET", "/api/tickets", user=BOB)
    assert _ids(staff) == ["T1", "T2", "T3", "T4", "T5", "T6"] and staff.json()["total"] == 6
    root = await world.call("GET", "/api/tickets", user=ROOT)
    assert _ids(root) == ["T1", "T2", "T3", "T4", "T5", "T6", "T7"]
