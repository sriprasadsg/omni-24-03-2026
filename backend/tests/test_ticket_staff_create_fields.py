"""A requester's new ticket keeps none of the staff-only fields (Phase 85 gap G-85-5, plan 85-39, WR-603). Real
MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=WR-603 / G-85-5 / PROH-85-31 / T-85-133: a caller who is not ticket staff cannot set the assignee,
group, watchers, approval requirement, SLA hours or due date of a ticket they raise, neither in the body nor through
a template's defaults (a template's own approval requirement stays), while ticket staff set all six as before;
fails_when=a requester's stored ticket carries an assignee, group, watcher, approval setting, SLA override or due date
they sent (or a template's staff defaults other than approval), staff lose one of the six, or a requester's title,
description, type, priority, tags or custom fields are not stored as sent;
no_claim=the screen, and the desk intake that runs after the ticket is stored (stubbed here).
"""
import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service_desk import store
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.service_desk_support import desk_app, portal_user, seed_desk_tenant, staff_user

ALICE = portal_user("t1", "alice@x.co")           # a requester
BOB = staff_user("t1", "bob@x.co")                # a technician (manage:tickets)

STAFF_BODY = {
    "assignee": "x@outside.test", "assignee_group": "Team X", "watchers": ["outsider@outside.test"],
    "approval_required": True, "sla_hours": 1, "due_date": "2026-12-01T00:00",
}
PLAIN_BODY = {"title": "Printer jams", "description": "tray 2", "type": "incident", "priority": "high",
              "tags": ["printer"], "custom_fields": {"floor": "3"}}


@pytest.fixture
async def world(mongo_db, monkeypatch):  # noqa: F811
    await store.ensure_indexes(mongo_db)
    await seed_desk_tenant(mongo_db, "t1")
    import service_desk.intake as intake
    monkeypatch.setattr(intake, "on_ticket_created", AsyncMock())
    import ticket_notifications
    for name in dir(ticket_notifications):
        if name.startswith("notify_"):
            monkeypatch.setattr(ticket_notifications, name, AsyncMock())
    # The auto-assign rule must not fill the assignee (nothing in the test world configures one).
    from tickets_service import tickets_service
    monkeypatch.setattr(tickets_service, "auto_assign", AsyncMock(return_value=""))
    return desk_app(mongo_db, monkeypatch)


async def _create(world, user, **extra):
    response = await world.call("POST", "/api/tickets", user=user, json={**PLAIN_BODY, **extra})
    assert response.status_code == 200, response.text
    return await world.db.tickets.find_one({"id": response.json()["id"]}, {"_id": 0})


async def _template(world, defaults):
    await world.db.ticket_templates.insert_one({"id": "tpl1", "tenantId": "t1", "name": "T", "defaults": defaults})


async def test_requester_cannot_set_the_staff_fields(world):
    stored = await _create(world, ALICE, **STAFF_BODY)
    assert stored["assignee"] != "x@outside.test"
    assert stored["assignee_group"] != "Team X"
    assert "outsider@outside.test" not in stored["watchers"]
    assert stored["approval_required"] is False and stored["approval_status"] == "none"
    assert stored["sla_hours"] != 1
    assert stored["due_date"] != "2026-12-01T00:00"
    for key, value in PLAIN_BODY.items():
        assert stored[key] == value, key


async def test_staff_set_all_six_fields(world):
    stored = await _create(world, BOB, **STAFF_BODY)
    assert stored["assignee"] == "x@outside.test"
    assert stored["assignee_group"] == "Team X"
    assert stored["watchers"] == ["outsider@outside.test"]
    assert stored["approval_required"] is True and stored["approval_status"] == "pending"
    assert stored["sla_hours"] == 1
    assert stored["due_date"] == "2026-12-01T00:00"


TEMPLATE_DEFAULTS = {"assignee": "tech@x.co", "assignee_group": "Desk", "watchers": ["lead@x.co"],
                     "sla_hours": 2, "approval_required": True, "due_date": "2026-12-02T00:00"}


async def test_template_staff_defaults_are_dropped_for_a_requester_but_approval_stays(world):
    await _template(world, TEMPLATE_DEFAULTS)
    stored = await _create(world, ALICE, template_id="tpl1")
    assert stored["assignee"] != "tech@x.co"
    assert stored["assignee_group"] != "Desk"
    assert "lead@x.co" not in stored["watchers"]
    assert stored["sla_hours"] != 2
    assert stored["due_date"] != "2026-12-02T00:00"
    assert stored["approval_required"] is True and stored["approval_status"] == "pending"


async def test_template_defaults_apply_in_full_for_staff(world):
    await _template(world, TEMPLATE_DEFAULTS)
    stored = await _create(world, BOB, template_id="tpl1")
    assert stored["assignee"] == "tech@x.co"
    assert stored["assignee_group"] == "Desk"
    assert stored["watchers"] == ["lead@x.co"]
    assert stored["sla_hours"] == 2
    assert stored["approval_required"] is True


async def test_requester_cannot_set_approval_through_a_template_that_does_not_require_it(world):
    await _template(world, {"type": "task", "priority": "medium"})
    stored = await _create(world, ALICE, template_id="tpl1", approval_required=True)
    assert stored["approval_required"] is False and stored["approval_status"] == "none"
