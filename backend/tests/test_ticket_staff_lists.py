"""Who sees which tickets in lists, counts, reports and exports (Phase 85, plan 85-33, gap G-85-4, WR-502).

Value: protects=WR-502 / G-85-4 UD-2 / PROH-85-24 / T-85-115 / T-85-116: GET /api/tickets, /stats, the
/reports/* routes and /export/csv hold only the tickets a caller who is not ticket staff raised, filtered in
the database query (so totals and pages agree), a name with regex characters matches only itself, and ticket
staff keep the whole tenant; fails_when=a requester lists, counts, reports or exports a colleague's ticket,
a reporter parameter or a search widens the scope, a regex-character name matches another person, a total
differs from the tickets returned, or staff lose a ticket; no_claim=the AI chat /tickets skill (A-85-G27)
and the single-ticket routes (85-32). The stats, report and export tests mount ticket_reports_endpoints on the same app.
"""
import csv
import io
import os
import sys
from datetime import datetime, timedelta, timezone

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
    """Six tickets of t1 (alice twice and once in another case, bob, a.lice, a.*) plus one of t2 by alice. Alice's
    T1 is open and met its SLA, T2 resolved and breached it, T3 closed; bob's T4 is open, escalated and met its SLA;
    a.lice's T5 is resolved. T1, T2 and T4 have an assignee."""
    now = datetime.now(timezone.utc)
    rows = [
        ("T1", "t1", "alice@x.co", "open", "Printer jam", "amy", "met"),
        ("T2", "t1", "alice@x.co", "resolved", "Mail sync", "amy", "breached"),
        ("T3", "t1", "Alice@X.co", "closed", "Old VPN", None, None),
        ("T4", "t1", "bob@x.co", "open", "Bob's secret salary question", "zed", "met"),
        ("T5", "t1", "a.lice@x.co", "resolved", "Near miss", None, None),
        ("T6", "t1", "a.*@x.co", "open", "Regex name", None, None),
        ("T7", "t2", "alice@x.co", "open", "Other tenant", None, None),
    ]
    for n, (tid, tenant, reporter, status, title, assignee, sla) in enumerate(rows):
        created = (now - timedelta(days=n + 1)).isoformat()
        doc = {
            "id": tid, "ticket_number": f"TKT-{tid}", "tenantId": tenant, "reporter": reporter, "status": status,
            "title": title, "description": "", "priority": "medium", "type": "incident", "assignee": assignee,
            "escalated": tid == "T4", "tags": [], "comments": [], "history": [],
            "created_at": created, "updated_at": created}
        if sla:
            doc["sla_status"] = sla
        if status == "resolved":
            doc["resolved_at"] = (now - timedelta(hours=1)).isoformat()
        await world.db.tickets.insert_one(doc)


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


# ---------------------------------------------------------------- stats, reports and the CSV export (85-33, Task 2)

@pytest.fixture
async def reports(world, monkeypatch):
    """The ticket routes plus the report router on one app, the report limiter off, planted tickets."""
    import ticket_reports_endpoints
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    monkeypatch.setattr(ticket_reports_endpoints, "get_database", lambda: world.db)
    world.app.include_router(ticket_reports_endpoints.router)
    world.app.state.limiter = Limiter(key_func=get_remote_address, enabled=False)
    await _plant(world)
    return world


async def _json(world, path, user):
    response = await world.call("GET", path, user=user)
    assert response.status_code == 200, response.text
    return response.json()


async def test_stats_count_only_a_requesters_own_tickets(reports):
    """protects=UD-2 on GET /stats; fails_when=a requester's total, status counts or escalated count include a colleague's ticket."""
    mine = await _json(reports, "/api/tickets/stats", ALICE)
    assert mine["total"] == 3 and mine["by_status"] == {"open": 1, "resolved": 1, "closed": 1} and mine["escalated"] == 0
    other = await _json(reports, "/api/tickets/stats?reporter=bob@x.co", ALICE)
    assert other["total"] == 0
    staff = await _json(reports, "/api/tickets/stats", BOB)
    assert staff["total"] == 6 and staff["escalated"] == 1


async def test_the_summary_sla_and_resolution_reports_count_only_a_requesters_own_tickets(reports):
    """protects=UD-2 / A-85-G26 on /reports/summary, /sla and /resolution; fails_when=a count or an average includes a
    colleague's ticket for a requester, or staff lose the tenant."""
    mine = await _json(reports, "/api/tickets/reports/summary", ALICE)
    assert (mine["total"], mine["open"], mine["closed"], mine["escalated"]) == (3, 1, 2, 0)
    staff = await _json(reports, "/api/tickets/reports/summary", BOB)
    assert (staff["total"], staff["open"], staff["closed"], staff["escalated"]) == (6, 3, 3, 1)
    sla = await _json(reports, "/api/tickets/reports/sla", ALICE)
    assert (sla["sla_met"], sla["sla_breached"]) == (1, 1)
    assert (await _json(reports, "/api/tickets/reports/sla", BOB))["sla_met"] == 2
    resolution = await _json(reports, "/api/tickets/reports/resolution", ALICE)
    assert resolution["overall"]["count"] == 1
    assert (await _json(reports, "/api/tickets/reports/resolution", BOB))["overall"]["count"] == 2


async def test_the_trends_assignee_and_ageing_reports_count_only_a_requesters_own_tickets(reports):
    """protects=UD-2 / A-85-G26 on /reports/trends, /assignee and /ageing; fails_when=a requester sees a colleague's
    assignee, an opened count or an open ticket in the ageing buckets."""
    trends = await _json(reports, "/api/tickets/reports/trends?days=30", ALICE)
    assert sum(day["opened"] for day in trends["data"]) == 3
    assert sum(day["opened"] for day in (await _json(reports, "/api/tickets/reports/trends?days=30", BOB))["data"]) == 6
    mine = (await _json(reports, "/api/tickets/reports/assignee", ALICE))["assignees"]
    assert [(row["assignee"], row["total"]) for row in mine] == [("amy", 2)]
    staff = (await _json(reports, "/api/tickets/reports/assignee", BOB))["assignees"]
    assert sorted((row["assignee"], row["total"]) for row in staff) == [("amy", 2), ("zed", 1)]
    assert (await _json(reports, "/api/tickets/reports/ageing", ALICE))["total_open"] == 1
    assert (await _json(reports, "/api/tickets/reports/ageing", BOB))["total_open"] == 3


async def test_the_csv_export_holds_only_a_requesters_own_tickets(reports):
    """protects=UD-2 / T-85-115 on /export/csv; fails_when=an exported row names a ticket the caller did not raise, a
    status or assignee parameter widens the export, or staff lose a ticket."""
    async def numbers(user, query=""):
        response = await reports.call("GET", f"/api/tickets/export/csv{query}", user=user)
        assert response.status_code == 200, response.text
        return sorted(row["ticket_number"] for row in csv.DictReader(io.StringIO(response.text)))

    assert await numbers(ALICE) == ["TKT-T1", "TKT-T2", "TKT-T3"]
    assert await numbers(ALICE, "?assignee=zed") == []
    assert await numbers(BOB) == ["TKT-T1", "TKT-T2", "TKT-T3", "TKT-T4", "TKT-T5", "TKT-T6"]
