"""Maintenance windows, plan 84-05: typed, zone-aware, tenant-safe windows and the Change Management list.

Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py. The routes are
mounted on a small app with the caller's identity chosen per request; time is frozen by passing ``now`` to the
service.

Value: protects=PTCH-05 (D-01, D-02): a window is stored in the tenant's own time zone, runs past midnight, honours
daylight saving and ISO weekdays, can only be written for the caller's own tenant and is shown read-only in Change
Management; fails_when=a window past midnight is never open, a Saturday-only window is open on a Friday or Sunday,
a body field (tenantId) decides the tenant, another tenant's window can be read, edited or deleted, an unknown
zone is stored, or a legacy caller answers from the old UTC maths; no_claim=a UI, a rollout dispatch or the live
database (the Settings screen is plan 84-12).
"""
import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi import FastAPI

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import change_management_endpoints
import maintenance_endpoints
import maintenance_service
import rbac_utils
import tenant_context
from authentication_service import get_current_user
from auth_types import TokenData
from autonomous_ops.rollout import windows
from database import get_database
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

KOLKATA = ZoneInfo("Asia/Kolkata")
NEW_YORK = ZoneInfo("America/New_York")
SAT_2330 = datetime(2026, 11, 7, 23, 30, tzinfo=KOLKATA)      # 2026-11-07 is a Saturday
SUN_0130 = datetime(2026, 11, 8, 1, 30, tzinfo=KOLKATA)
SUN_0200 = datetime(2026, 11, 8, 2, 0, tzinfo=KOLKATA)
WEEKEND = {"name": "Weekend", "recurrence": "weekly", "startTime": "22:00", "endTime": "02:00",
           "daysOfWeek": [6, 7], "timeZone": "Asia/Kolkata"}


class Client:
    def __init__(self, db, monkeypatch):
        self.db = db
        self.user = None
        monkeypatch.setattr(rbac_utils, "get_database", lambda: db)
        self.app = FastAPI()
        self.app.include_router(maintenance_endpoints.router)
        self.app.include_router(change_management_endpoints.router)
        self.app.dependency_overrides[get_current_user] = lambda: self.user
        self.app.dependency_overrides[get_database] = lambda: db

    async def call(self, method, path, *, tenant="t1", role="tenant_admin", json=None):
        self.user = TokenData(username=f"{role}@{tenant}.test", role=role, tenant_id=tenant)
        token = tenant_context.set_tenant_id(tenant)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),
                                         base_url="http://testserver") as client:
                return await client.request(method, path, json=json)
        finally:
            tenant_context.reset_tenant_id(token)


@pytest.fixture
def client(mongo_db, monkeypatch):  # noqa: F811
    return Client(mongo_db, monkeypatch)


def service(db):
    return maintenance_service.get_maintenance_service(db)


# ---------------------------------------------------------------- create, validation and tenant safety

async def test_weekly_window_past_midnight_stores_the_zone_and_opens_in_it(client, mongo_db):
    reply = await client.call("POST", "/api/maintenance/windows", json=WEEKEND)
    assert reply.status_code == 201, reply.text
    made = reply.json()["window"]
    assert (made["recurrence"], made["startTime"], made["endTime"], made["daysOfWeek"]) == \
        ("weekly", "22:00", "02:00", [6, 7])
    assert made["scheduleText"] == "22:00 to 02:00 the next day"
    stored = await mongo_db.maintenance_windows.find_one({"id": made["id"]})
    assert stored["tenantId"] == "t1" and stored["isActive"] is True
    assert set(stored) == {"_id", "id", "tenantId", "name", "recurrence", "startTime", "endTime", "daysOfWeek",
                           "startsAt", "endsAt", "isActive", "createdAt", "updatedAt"}
    assert (await mongo_db.maintenance_settings.find_one({"tenantId": "t1"}))["timeZone"] == "Asia/Kolkata"

    svc = service(mongo_db)
    late = await svc.status("t1", now=SAT_2330)
    assert late["state"] == "open" and "02:00" in late["text"] and late["timeZone"] == "Asia/Kolkata"
    assert (await svc.status("t1", now=SUN_0130))["state"] == "open"      # the next day, still inside
    closed = await svc.status("t1", now=SUN_0200)
    assert closed["state"] == "closed" and "Sun 8 Nov, 22:00" in closed["text"]


async def test_a_window_that_ends_at_two_is_closed_at_two(client, mongo_db):
    body = dict(WEEKEND, daysOfWeek=[6])
    assert (await client.call("POST", "/api/maintenance/windows", json=body)).status_code == 201
    svc = service(mongo_db)
    assert (await svc.status("t1", now=SUN_0130))["state"] == "open"
    shut = await svc.status("t1", now=SUN_0200)
    assert shut["state"] == "closed" and "Sat 14 Nov, 22:00" in shut["text"]


async def test_saturday_only_window_is_open_on_a_saturday_not_a_friday_or_sunday(client, mongo_db):
    body = {"name": "Sat", "recurrence": "weekly", "startTime": "09:00", "endTime": "11:00", "daysOfWeek": [6],
            "timeZone": "Asia/Kolkata"}
    assert (await client.call("POST", "/api/maintenance/windows", json=body)).status_code == 201
    svc = service(mongo_db)
    assert (await svc.status("t1", now=datetime(2026, 11, 7, 10, 0, tzinfo=KOLKATA)))["state"] == "open"
    assert (await svc.status("t1", now=datetime(2026, 11, 6, 10, 0, tzinfo=KOLKATA)))["state"] == "closed"
    assert (await svc.status("t1", now=datetime(2026, 11, 8, 10, 0, tzinfo=KOLKATA)))["state"] == "closed"


async def test_the_first_window_without_a_stored_zone_needs_a_time_zone(client, mongo_db):
    body = {k: v for k, v in WEEKEND.items() if k != "timeZone"}
    reply = await client.call("POST", "/api/maintenance/windows", json=body)
    assert reply.status_code == 422
    assert reply.json()["detail"] == "Choose a time zone from the list, for example Asia/Kolkata."
    assert await mongo_db.maintenance_windows.count_documents({}) == 0
    assert (await client.call("POST", "/api/maintenance/windows", json=dict(body, timeZone="Mars/Olympus"))
            ).status_code == 422
    assert await mongo_db.maintenance_settings.count_documents({}) == 0


@pytest.mark.parametrize("change, sentence", [
    ({"daysOfWeek": [0]}, "Choose days from Monday (1) to Sunday (7)."),
    ({"daysOfWeek": [8]}, "Choose days from Monday (1) to Sunday (7)."),
    ({"daysOfWeek": []}, "Choose at least one day."),
    ({"startTime": "22:00", "endTime": "22:00"}, "The window can't start and end at the same time."),
    ({"name": ""}, "Enter a window name."),
    ({"name": "   "}, "Enter a window name."),
    ({"name": "x" * 61}, "A window name can be up to 60 characters."),
    ({"recurrence": "monthly"}, "Choose One-time, Daily or Weekly."),
    ({"startTime": "25:00"}, "Enter a start and end time."),
    ({"endTime": None}, "Enter a start and end time."),
])
async def test_a_bad_window_is_refused_with_the_screen_sentence(client, mongo_db, change, sentence):
    reply = await client.call("POST", "/api/maintenance/windows", json=dict(WEEKEND, **change))
    assert reply.status_code == 422, reply.text
    assert reply.json()["detail"] == sentence
    assert await mongo_db.maintenance_windows.count_documents({}) == 0


async def test_one_time_windows_are_checked_for_order_and_length(client, mongo_db):
    once = {"name": "Freeze", "recurrence": "none", "timeZone": "Asia/Kolkata"}
    too_long = await client.call("POST", "/api/maintenance/windows",
                                 json=dict(once, startsAt="2026-11-07T22:00", endsAt="2026-11-08T23:00"))
    assert (too_long.status_code, too_long.json()["detail"]) == (422, "A window can be up to 24 hours long.")
    backwards = await client.call("POST", "/api/maintenance/windows",
                                  json=dict(once, startsAt="2026-11-07T22:00", endsAt="2026-11-07T21:00"))
    assert (backwards.status_code, backwards.json()["detail"]) == (422, "The end must be after the start.")
    same = await client.call("POST", "/api/maintenance/windows",
                             json=dict(once, startsAt="2026-11-07T22:00", endsAt="2026-11-07T22:00"))
    assert same.status_code == 422
    ok = await client.call("POST", "/api/maintenance/windows",
                           json=dict(once, startsAt="2026-11-07T22:00", endsAt="2026-11-08T02:00"))
    assert ok.status_code == 201, ok.text
    assert ok.json()["window"]["scheduleText"] == "Sat 7 Nov, 22:00 to Sun 8 Nov, 02:00"
    assert (await service(mongo_db).status("t1", now=SUN_0130))["state"] == "open"
    assert (await service(mongo_db).status("t1", now=SUN_0200))["state"] == "closed"


async def test_a_tenant_id_in_the_body_is_ignored_and_other_fields_are_not_stored(client, mongo_db):
    reply = await client.call("POST", "/api/maintenance/windows",
                              json=dict(WEEKEND, tenantId="other", isActive=False, is_active=False, role="x"))
    assert reply.status_code == 201
    stored = await mongo_db.maintenance_windows.find_one({"id": reply.json()["window"]["id"]})
    assert stored["tenantId"] == "t1" and stored["isActive"] is True and "role" not in stored
    assert await mongo_db.maintenance_windows.count_documents({"tenantId": "other"}) == 0


# ---------------------------------------------------------------- edit, delete, list are tenant-scoped

async def test_edit_changes_the_callers_window_and_another_tenant_gets_404(client, mongo_db):
    made = (await client.call("POST", "/api/maintenance/windows", json=WEEKEND)).json()["window"]
    path = f"/api/maintenance/windows/{made['id']}"
    edited = await client.call("PUT", path, json={"name": "Weeknight", "recurrence": "daily",
                                                  "startTime": "01:00", "endTime": "03:00"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["window"]["name"] == "Weeknight" and edited.json()["window"]["daysOfWeek"] is None
    stored = await mongo_db.maintenance_windows.find_one({"id": made["id"]})
    assert (stored["recurrence"], stored["startTime"], stored["endTime"], stored["daysOfWeek"]) == \
        ("daily", "01:00", "03:00", None)

    attempt = {"name": "Hijack", "recurrence": "daily", "startTime": "01:00", "endTime": "03:00"}
    assert (await client.call("PUT", path, tenant="t2", json=attempt)).status_code == 404
    assert (await client.call("DELETE", path, tenant="t2")).status_code == 404
    assert (await mongo_db.maintenance_windows.find_one({"id": made["id"]}))["name"] == "Weeknight"
    assert (await client.call("GET", "/api/maintenance/windows", tenant="t2")).json() == []
    assert len((await client.call("GET", "/api/maintenance/windows")).json()) == 1

    assert (await client.call("DELETE", path)).status_code == 200
    assert (await client.call("DELETE", path)).status_code == 404
    assert await mongo_db.maintenance_windows.count_documents({}) == 0


async def test_the_list_carries_texts_and_openness_in_the_tenant_zone(client, mongo_db):
    await client.call("POST", "/api/maintenance/windows", json=WEEKEND)
    row = (await client.call("GET", "/api/maintenance/windows")).json()[0]
    assert row["scheduleText"] == "22:00 to 02:00 the next day"
    assert row["nextText"].startswith("Next: ") and ", 22:00" in row["nextText"]
    assert row["openNow"] in (True, False)
    listed = await service(mongo_db).list_windows("t1", now=SAT_2330)
    assert listed[0]["openNow"] is True and listed[0]["nextText"] == "Next: Sun 8 Nov, 22:00"
    assert listed[0]["fullScheduleText"] == "Weekly, Sat and Sun, 22:00 to 02:00 the next day (Asia/Kolkata)"
    assert "_id" not in listed[0]


async def test_a_finished_one_time_window_says_not_scheduled(client, mongo_db):
    body = {"name": "Old", "recurrence": "none", "startsAt": "2026-01-02T22:00", "endsAt": "2026-01-02T23:00",
            "timeZone": "UTC"}
    assert (await client.call("POST", "/api/maintenance/windows", json=body)).status_code == 201
    listed = await service(mongo_db).list_windows("t1", now=SAT_2330)
    assert listed[0]["nextText"] == "Next: not scheduled" and listed[0]["openNow"] is False


async def test_the_window_count_is_capped(client, mongo_db):
    for i in range(50):
        await mongo_db.maintenance_windows.insert_one({"id": f"w{i}", "tenantId": "t1"})
    await mongo_db.maintenance_settings.insert_one({"tenantId": "t1", "timeZone": "UTC"})
    reply = await client.call("POST", "/api/maintenance/windows", json=WEEKEND)
    assert reply.status_code == 422 and "50" in reply.json()["detail"]


# ---------------------------------------------------------------- time zone

async def test_the_time_zone_is_stored_per_tenant_and_must_be_a_real_zone(client, mongo_db):
    assert (await client.call("GET", "/api/maintenance/time-zone")).json() == {"timeZone": None}
    ok = await client.call("PUT", "/api/maintenance/time-zone", json={"timeZone": "Asia/Kolkata"})
    assert ok.status_code == 200 and ok.json() == {"timeZone": "Asia/Kolkata"}
    assert (await client.call("GET", "/api/maintenance/time-zone")).json() == {"timeZone": "Asia/Kolkata"}
    assert (await client.call("GET", "/api/maintenance/time-zone", tenant="t2")).json() == {"timeZone": None}
    for bad in ("Mars/Olympus", "", "../etc/passwd", "UTC+5", None):
        reply = await client.call("PUT", "/api/maintenance/time-zone", json={"timeZone": bad})
        assert reply.status_code == 422, bad
    assert (await mongo_db.maintenance_settings.find_one({"tenantId": "t1"}))["timeZone"] == "Asia/Kolkata"
    await client.call("PUT", "/api/maintenance/time-zone", json={"timeZone": "Europe/London", "tenantId": "t2"})
    assert await mongo_db.maintenance_settings.count_documents({"tenantId": "t2"}) == 0


async def test_status_with_no_window_says_none(client, mongo_db):
    status = await service(mongo_db).status("t1", now=SAT_2330)
    assert status["state"] == "none" and status["timeZone"] is None
    assert (await client.call("GET", "/api/maintenance/status")).json()["state"] == "none"


# ---------------------------------------------------------------- daylight saving, round trip, legacy callers

async def test_a_new_york_window_is_two_hours_long_on_the_spring_forward_night(client, mongo_db):
    body = {"name": "Night", "recurrence": "daily", "startTime": "01:00", "endTime": "04:00",
            "timeZone": "America/New_York"}
    assert (await client.call("POST", "/api/maintenance/windows", json=body)).status_code == 201
    tenant = await windows.load(mongo_db, "t1")
    around = datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc)
    lengths = {opens.astimezone(NEW_YORK).date().isoformat(): (closes - opens).total_seconds() / 3600
               for opens, closes in windows.occurrences(tenant.zone, tenant.windows[0], around)}
    assert lengths["2026-03-08"] == 2.0
    assert lengths["2026-03-07"] == 3.0


@pytest.mark.parametrize("body", [
    {"name": "D", "recurrence": "daily", "startTime": "22:00", "endTime": "02:00", "timeZone": "Asia/Kolkata"},
    {"name": "W", "recurrence": "weekly", "startTime": "22:00", "endTime": "02:00", "daysOfWeek": [5, 6],
     "timeZone": "Asia/Kolkata"},
])
async def test_every_saved_window_round_trips_through_load_and_is_open(client, mongo_db, body):
    assert (await client.call("POST", "/api/maintenance/windows", json=body)).status_code == 201
    tenant = await windows.load(mongo_db, "t1")
    assert tenant.readable and tenant.zone == "Asia/Kolkata" and len(tenant.windows) == 1
    saturday = datetime(2026, 11, 7, 23, 0, tzinfo=KOLKATA)                       # a Saturday, 23:00 local
    assert windows.is_open(tenant.windows, tenant.zone, saturday) is not None


async def test_legacy_callers_answer_from_the_zone_aware_maths(client, mongo_db):
    svc = service(mongo_db)
    assert await svc.is_in_maintenance_window("t1") is False                      # no window means closed
    await client.call("POST", "/api/maintenance/windows",
                      json={"name": "Always", "recurrence": "daily", "startTime": "00:00", "endTime": "23:59",
                            "timeZone": "UTC"})
    now = datetime.now(timezone.utc)
    expected = windows.is_open((await windows.load(mongo_db, "t1")).windows, "UTC", now) is not None
    assert await svc.is_in_maintenance_window("t1") is expected
    reply = await client.call("GET", "/api/maintenance/check")
    assert reply.status_code == 200 and reply.json() == {"is_in_window": expected}
    assert await svc.is_in_maintenance_window("t2") is False


# ---------------------------------------------------------------- Change Management, read-only

async def test_change_management_lists_only_the_callers_windows(client, mongo_db):
    await client.call("POST", "/api/maintenance/windows", json=WEEKEND)
    await client.call("POST", "/api/maintenance/windows",
                      json={"name": "Other tenant", "recurrence": "daily", "startTime": "01:00", "endTime": "02:00",
                            "timeZone": "UTC"}, tenant="t2")
    reply = await client.call("GET", "/api/changes/maintenance-windows")
    assert reply.status_code == 200, reply.text
    rows = reply.json()
    assert [r["name"] for r in rows] == ["Weekend"]
    assert set(rows[0]) == {"id", "name", "scheduleText", "openNow", "nextText"}
    assert rows[0]["scheduleText"] == "Weekly, Sat and Sun, 22:00 to 02:00 the next day (Asia/Kolkata)"
    assert (await client.call("GET", "/api/changes/maintenance-windows", tenant="t3")).json() == []


def test_the_change_management_route_has_no_write_verb():
    methods = {m for r in change_management_endpoints.router.routes
               if getattr(r, "path", "") == "/api/changes/maintenance-windows" for m in r.methods}
    assert methods == {"GET"}


def test_the_old_raw_dict_create_body_is_gone():
    source = open(maintenance_endpoints.__file__, encoding="utf-8").read()
    assert "window_data: Dict" not in source
    puts = [r for r in maintenance_endpoints.router.routes if "PUT" in getattr(r, "methods", ())]
    assert len(puts) >= 2
