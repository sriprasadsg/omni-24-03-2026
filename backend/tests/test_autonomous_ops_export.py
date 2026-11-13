"""Autonomous Ops activity export builder (Phase 86, plan 86-06, ACTV-06, D-09, D-10, D-11).
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=the export holds exactly the rows the Activity list shows for a state and period, newest
first, capped at 5,000 with an honest note, with spreadsheet formulas and PDF markup neutralised and a
platform administrator's name kept from tenant viewers; fails_when=the file shows a row the screen would not
(another tenant, a platform health row), the cap or its note is off by one, a cell can run as a formula,
markup changes the page, or a tenant file names platform staff; no_claim=the routes, the audit event and the
dialog (86-08, 86-11).
"""
import csv
import io
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audit_ledger
import dlp_service
import export_controls
import rbac_utils
from api_key_auth import get_current_user_or_api_key
from auth_types import TokenData
from autonomous_ops import PLATFORM_TENANT_ID, protected, views
from autonomous_ops.reporting import EXPORT_ROW_CAP, export, export_pdf
from catalogue_mounts import mount_dependencies
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_agent, seed_tenant

NOW = datetime(2026, 11, 12, 12, 0, 0, tzinfo=timezone.utc)
HEADER = ["When (UTC)", "State", "Action", "Target", "Host", "Rule", "Rule id", "Approved by", "Result"]
CAP_SENTENCE = ("the newest 5,000 of 5,001 rows. Rows older than that were left out. "
                "Pick a shorter period or a single state to get the rest.")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()


def _doc(row_id, tenant, state, created, *, command="block_ip", target="203.0.113.7", targets=("a1",),
         kind="action", rule="playbook:contain-ip", approver=None, **extra):
    doc = {"id": row_id, "tenantId": tenant, "kind": kind, "origin": "playbook", "dispatcher": "instruction",
           "command": command, "actions": [command], "targets": list(targets), "target": target, "params": {},
           "state": state, "level": "undoable_auto", "shadow": state == "shadow",
           "reason": {"ruleId": rule, "inputs": {}}, "reasonCode": "class_auto",
           "reasonText": "This action is allowed to run on its own within the limits you set.",
           "approval": {"requiredBy": None, "expiresAt": None, "approver": approver, "decidedAt": None},
           "undo": {"available": False, "action": None, "params": {}, "undoneAt": None, "undoneBy": None},
           "createdAt": created, "updatedAt": created, "finishedAt": created}
    doc.update(extra)
    return doc


async def _put(db, *docs):
    await db.autonomy_actions.insert_many(list(docs))


async def _build(db, tenant="t1", *, bucket="all", days="30", staff=False, fmt="csv"):
    return await export.build(db, tenant, bucket=bucket, days=days, fmt=fmt, viewer_is_platform_staff=staff, now=NOW)


def _table(result):
    return list(csv.reader(io.StringIO(result.content.decode("utf-8"))))


# ------------------------------------------------------------------ the shared filter

async def test_activity_filter_gives_the_rows_the_list_shows(mongo_db):
    """protects=the export and the list read one filter; fails_when=they drift apart."""
    db = mongo_db
    await seed_tenant(db, "t1")
    await _put(db,
               _doc("AO-1", "t1", "executed", NOW - timedelta(minutes=1)),
               _doc("AO-2", "t1", "shadow", NOW - timedelta(minutes=2)),
               _doc("AO-3", "t1", "refused", NOW - timedelta(minutes=3)),
               _doc("AO-4", "t2", "executed", NOW - timedelta(minutes=4)),
               _doc("AO-5", "t1", "executed", NOW - timedelta(minutes=5), kind="platform_health"),
               _doc("AO-6", PLATFORM_TENANT_ID, "executed", NOW - timedelta(minutes=6), kind="control", scope="platform",
                    controlEvent="stop_pressed"))
    for bucket in ("all", "done", "simulation", "refused"):
        page = await views.list_page(db, "t1", bucket=bucket, limit=100, cursor=None, viewer_is_platform_staff=False)
        found = db.autonomy_actions.find(views.activity_filter("t1", bucket), {"_id": 0, "id": 1})
        assert {row["id"] async for row in found} == {item["id"] for item in page["items"]}, bucket


def test_activity_filter_refuses_an_unknown_bucket():
    with pytest.raises(ValueError):
        views.activity_filter("t1", "everything")


# ------------------------------------------------------------------ the CSV

async def test_csv_header_rows_newest_first_and_only_the_tenants_own(mongo_db):
    db = mongo_db
    await seed_tenant(db, "t1")
    await seed_agent(db, "t1", "a1", hostname="web-01")
    await _put(db,
               _doc("AO-old", "t1", "executed", NOW - timedelta(days=3)),
               _doc("AO-mid", "t1", "executed", NOW - timedelta(days=2)),
               _doc("AO-new", "t1", "executed", NOW - timedelta(days=1), rule="sweep:block_ip"),
               _doc("AO-undone", "t1", "undone", NOW - timedelta(days=1, hours=1)),
               _doc("AO-t2", "t2", "executed", NOW - timedelta(days=1), target="198.51.100.9", targets=("b1",)))
    result = await _build(db, bucket="done")
    assert (result.shown, result.total, result.truncated) == (3, 3, False)
    assert result.media_type == "text/csv"
    table = _table(result)
    assert table[0] == HEADER
    assert len(table) == 4
    assert [row[0] for row in table[1:]] == ["2026-11-11 12:00:00", "2026-11-10 12:00:00", "2026-11-09 12:00:00"]
    first = table[1]
    assert first[1] == "Done" and first[2] == "Block IP address" and first[4] == "web-01"
    assert first[6] == "sweep:block_ip" and first[5] == "Block an address two sources agree on"
    assert all("198.51.100.9" not in cell for row in table for cell in row)


async def test_simulation_reads_simulation_and_all_has_the_platform_stop_but_no_health_rows(mongo_db):
    db = mongo_db
    await seed_tenant(db, "t1")
    await _put(db,
               _doc("AO-shadow", "t1", "shadow", NOW - timedelta(hours=1), wouldHave="allow_auto"),
               _doc("AO-health", PLATFORM_TENANT_ID, "executed", NOW - timedelta(hours=2), kind="platform_health",
                    healthEvent="watchdog_restart"),
               _doc("AO-health-t1", "t1", "executed", NOW - timedelta(hours=2), kind="platform_health"),
               _doc("AO-stop", PLATFORM_TENANT_ID, "executed", NOW - timedelta(hours=3), kind="control", scope="platform",
                    controlEvent="stop_pressed", actor={"username": "root", "display": "Root", "tier": "platform"}))
    sim = _table(await _build(db, bucket="simulation"))
    assert [row[1] for row in sim[1:]] == ["Simulation"]
    everything = _table(await _build(db, bucket="all"))
    assert [row[1] for row in everything[1:]] == ["Simulation", "Control"]


async def test_period_edges_seven_days_excludes_eight_and_all_time_includes_four_hundred(mongo_db):
    db = mongo_db
    await seed_tenant(db, "t1")
    await _put(db,
               _doc("AO-recent", "t1", "executed", NOW - timedelta(days=6)),
               _doc("AO-8d", "t1", "executed", NOW - timedelta(days=8)),
               _doc("AO-400d", "t1", "executed", NOW - timedelta(days=400)))
    assert [r[0] for r in _table(await _build(db, days="7"))[1:]] == ["2026-11-06 12:00:00"]
    assert (await _build(db, days="30")).total == 2
    assert (await _build(db, days="90")).total == 2
    everything = await _build(db, days="all")
    assert everything.total == 3 and everything.shown == 3


async def test_a_period_outside_the_menu_is_refused(mongo_db):
    with pytest.raises(ValueError):
        await _build(mongo_db, days="14")
    with pytest.raises(ValueError):
        await _build(mongo_db, fmt="xml")


async def test_cap_keeps_the_newest_five_thousand_and_says_so(mongo_db):
    db = mongo_db
    await seed_tenant(db, "t1")
    await _put(db, *[_doc(f"AO-{i:05d}", "t1", "executed", NOW - timedelta(seconds=i + 1))
                     for i in range(EXPORT_ROW_CAP + 1)])
    result = await _build(db, days="all")
    assert (result.shown, result.total, result.truncated) == (5000, 5001, True)
    table = _table(result)
    assert len(table) == 1 + 5000 + 1
    assert table[1][0] == "2026-11-12 11:59:59"
    assert table[-1] == ["Note", CAP_SENTENCE]
    assert table[-2][0] != "Note"
    assert export.cap_sentence(5000, 5001) == CAP_SENTENCE


async def test_exactly_the_cap_is_not_truncated_and_has_no_note(mongo_db):
    db = mongo_db
    await seed_tenant(db, "t1")
    await _put(db, *[_doc(f"AO-{i:05d}", "t1", "executed", NOW - timedelta(seconds=i + 1)) for i in range(EXPORT_ROW_CAP)])
    result = await _build(db, days="all")
    assert (result.shown, result.total, result.truncated) == (5000, 5000, False)
    table = _table(result)
    assert len(table) == 1 + 5000
    assert all(row[0] != "Note" for row in table)


async def test_no_matching_rows_gives_no_file(mongo_db):
    db = mongo_db
    await seed_tenant(db, "t1")
    await _put(db, _doc("AO-other", "t2", "executed", NOW - timedelta(hours=1)))
    result = await _build(db, bucket="done")
    assert result.content is None and result.total == 0 and result.shown == 0 and result.truncated is False


@pytest.mark.parametrize("lead", ["=", "+", "-", "@", "\t", "\r"])
async def test_a_cell_starting_like_a_formula_cannot_run_as_one(mongo_db, lead):
    """protects=T-86-11 (CWE-1236); fails_when=a target, host or rule id can start a formula in a spreadsheet."""
    db = mongo_db
    await seed_tenant(db, "t1")
    await seed_agent(db, "t1", "a1", hostname=f"{lead}cmd-host")
    await _put(db,
               _doc("AO-evil", "t1", "executed", NOW - timedelta(hours=1), target=f'{lead}HYPERLINK("http://x")',
                    targets=("a9",), rule=f"{lead}rule"),
               _doc("AO-host", "t1", "executed", NOW - timedelta(hours=2)))
    table = _table(await _build(db, bucket="done"))
    evil, host = table[1], table[2]
    assert evil[3] == f"'{lead}HYPERLINK(\"http://x\")" and evil[6] == f"'{lead}rule"
    assert host[4] == f"'{lead}cmd-host"
    for row in table:
        assert not any(cell and cell[0] in "=+-@\t\r" for cell in row), row


@pytest.mark.parametrize("staff,expected", [(False, "Platform administrator"), (True, "Pat")])
async def test_a_platform_approver_is_named_only_to_platform_staff(mongo_db, staff, expected):
    db = mongo_db
    await seed_tenant(db, "t1")
    await _put(db,
               _doc("AO-plat", "t1", "executed", NOW - timedelta(hours=1),
                    approver={"username": "pat", "display": "Pat", "tier": "platform"}),
               _doc("AO-own", "t1", "executed", NOW - timedelta(hours=2),
                    approver={"username": "tess", "display": "Tess", "tier": "tenant"}),
               _doc("AO-auto", "t1", "executed", NOW - timedelta(hours=3)))
    table = _table(await _build(db, bucket="done", staff=staff))
    assert [row[7] for row in table[1:]] == [expected, "Tess", ""]
    assert (("Pat" in " ".join(" ".join(row) for row in table)) is staff)


def test_file_name_carries_the_tenant_and_the_day():
    assert export.file_name("t1", "csv", NOW) == "autonomous-ops-activity-t1-20261112.csv"
    assert export.file_name("t1", "pdf", NOW) == "autonomous-ops-activity-t1-20261112.pdf"
    assert export.file_name("acme corp/../x", "csv", NOW) == "autonomous-ops-activity-acme-corp----x-20261112.csv"


# ------------------------------------------------------------------ the PDF

def _pdf(**over):
    rows = over.pop("rows", [
        ["2026-11-12 11:00:00", "Done", "Block IP address", "203.0.113.7", "web-01", "Block an address two sources agree on",
         "sweep:block_ip", "", "Done."],
        ["2026-11-12 10:00:00", "Simulation", "Quarantine file", "C:\\x.exe", "web-02", "Quarantine a file two sources agree on",
         "sweep:quarantine_file", "", "Would have quarantined it."]])
    args = dict(organization="Acme Corp", generated_at=NOW, filter_line="Activity: All. Period: Last 30 days. Newest first, up to 5,000 rows.",
                summary={"fired": 2, "done": 1, "undone": 0, "wouldHaveDone": 1},
                rules=[{"id": "sweep:block_ip", "name": "Block an address two sources agree on", "fired": 1, "done": 1,
                        "approved": 0, "denied": 0, "undone": 0, "failed": 0, "refused": 0, "wouldHaveDone": 0}],
                time_saved={"minutes": 10, "estimate": True, "perKind": []}, rows=rows, cap_note=None, compress=False)
    args.update(over)
    return export_pdf.render_pdf(**args)


def _text(pdf):
    """The text shown on every page, lines joined by a space (uncompressed streams only)."""
    joined = b" ".join(re.findall(rb"\((.*?)\) Tj", pdf)).decode("latin-1")
    return re.sub(r"\s+", " ", joined.replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\"))


def _pages(pdf):
    return len(re.findall(rb"/Type /Page\b(?!s)", pdf))


def test_pdf_has_a_summary_page_then_the_rows():
    pdf = _pdf()
    text = _text(pdf)
    assert pdf.startswith(b"%PDF")
    assert _pages(pdf) >= 2
    assert "Acme Corp" in text and "Generated 2026-11-12 12:00 UTC" in text
    assert "Activity: All. Period: Last 30 days. Newest first, up to 5,000 rows." in text
    assert "Time saved (estimate): About 10 min" in text
    assert "This is an estimate, not a measurement" in text
    assert "Would have done (simulation)" in text
    assert "Block IP address" in text and "Quarantine file" in text and "Simulation" in text
    assert text.index("Time saved (estimate)") < text.index("Block IP address")


def test_pdf_summary_carries_the_cap_sentence_only_when_cut():
    cut = _text(_pdf(cap_note=export.cap_sentence(5000, 5001)))
    assert export.cap_sentence(5000, 5001) in cut
    assert "Rows older than that were left out" not in _text(_pdf())


def test_pdf_cell_text_is_shown_literally_never_as_markup():
    """protects=T-86-12; fails_when=markup or an ampersand in a target changes or breaks the page."""
    row = ["2026-11-12 11:00:00", "Done", "Answer a ticket", "Pay <b>now</b> & win", "web-01", "", "", "", "Done."]
    text = _text(_pdf(rows=[row]))
    assert "Pay <b>now</b> & win" in text
    assert "&lt;" not in text and "&amp;" not in text
    unbalanced = ["2026-11-12 11:00:00", "Done", "Answer a ticket", "<b>open & <i>never closed", "web-01", "", "", "", ""]
    squeezed = _text(_pdf(rows=[unbalanced], organization="A <u>& B")).replace(" ", "")   # the engine splits runs at < and >
    assert "<b>open&<i>neverclosed" in squeezed and "A<u>&B" in squeezed


def test_pdf_repeats_the_rows_header_on_every_page():
    many = [["2026-11-12 11:00:00", "Done", "Block IP address", f"203.0.113.{i % 250}", "web-01", "", "", "", "Done."]
            for i in range(120)]
    pdf = _pdf(rows=many)
    assert _pages(pdf) >= 3
    assert _text(pdf).count("Approved by") >= 2


async def test_build_pdf_uses_the_statistics_of_the_same_window(mongo_db, monkeypatch):
    db = mongo_db
    await seed_tenant(db, "t1", name="Acme Corp")
    await _put(db,
               _doc("AO-1", "t1", "executed", NOW - timedelta(days=1), rule="sweep:block_ip"),
               _doc("AO-2", "t1", "executed", NOW - timedelta(days=2), rule="sweep:block_ip"),
               _doc("AO-3", "t1", "shadow", NOW - timedelta(days=3), rule="sweep:block_ip"),
               _doc("AO-4", "t1", "executed", NOW - timedelta(days=40), rule="sweep:block_ip"),
               _doc("AO-t2", "t2", "executed", NOW - timedelta(days=1), rule="sweep:block_ip"))
    seen = {}
    real = export_pdf.render_pdf

    def spy(**kwargs):
        seen.update(kwargs)
        return real(**{**kwargs, "compress": False})

    monkeypatch.setattr(export_pdf, "render_pdf", spy)
    result = await _build(db, days="30", fmt="pdf")
    assert result.media_type == "application/pdf" and result.filename == "autonomous-ops-activity-t1-20261112.pdf"
    assert result.content.startswith(b"%PDF")
    assert (result.shown, result.total, result.truncated) == (3, 3, False)
    assert seen["organization"] == "Acme Corp" and seen["generated_at"] == NOW
    assert seen["filter_line"] == "Activity: All. Period: Last 30 days. Newest first, up to 5,000 rows."
    assert seen["summary"]["done"] == 2 and seen["summary"]["wouldHaveDone"] == 1
    assert seen["time_saved"]["minutes"] == 20
    assert [r["id"] for r in seen["rules"]] == ["sweep:block_ip"] and seen["rules"][0]["fired"] == 2
    assert seen["cap_note"] is None and len(seen["rows"]) == 3
    everything = await _build(db, days="all", fmt="pdf")
    assert everything.total == 4 and seen["summary"]["done"] == 3 and seen["time_saved"]["minutes"] == 30
    assert seen["filter_line"].endswith("Period: All time. Newest first, up to 5,000 rows.")


async def test_build_pdf_with_no_rows_gives_no_file(mongo_db):
    await seed_tenant(mongo_db, "t1")
    result = await _build(mongo_db, fmt="pdf")
    assert result.content is None and result.total == 0


# ------------------------------------------------------------------ the screen's export route (86-08, D-09, D-10, D-12)

EXPORT = "/api/autonomous-ops/export"
DENIED = ("You don't have permission to export this. "
          "It needs the right to export reports and to view Autonomous Ops.")
PLATFORM = "platform-admin"


class ExportApi:
    """The reporting router behind its catalogue guard; the caller's identity is chosen per request."""

    def __init__(self, db, monkeypatch):
        import autonomous_ops_endpoints
        import autonomous_ops_reporting_endpoints as reporting
        self.db, self.user = db, None
        self.audit = AsyncMock()
        self.incident = AsyncMock()
        for module in (autonomous_ops_endpoints, reporting, rbac_utils):
            monkeypatch.setattr(module, "get_database", lambda: db)
        monkeypatch.setattr(audit_ledger, "event", self.audit)
        monkeypatch.setattr(dlp_service, "scan_export", AsyncMock(return_value=([], [])))
        monkeypatch.setattr(dlp_service, "record_export_incident", self.incident)
        self.app = FastAPI()
        self.app.include_router(reporting.router,
                                dependencies=mount_dependencies("autonomous_ops_reporting_endpoints", "router"))
        self.app.dependency_overrides[get_current_user_or_api_key] = lambda: self.user

    async def get(self, path, *, role="tenant_admin", tenant="t1"):
        platform = role in ("super_admin", "platform_support", "platform_billing")
        self.user = TokenData(username=f"{role}@example.test", role=role,
                              tenant_id=PLATFORM if platform else tenant, scopes=None, auth_source="session")
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get(path)


@pytest.fixture
async def api(mongo_db, monkeypatch):
    for tenant in ("t1", "t2"):
        await seed_tenant(mongo_db, tenant)
        await mongo_db.tenants.update_one({"id": tenant}, {"$addToSet": {"enabledFeatures": "export:reports"}})
    return ExportApi(mongo_db, monkeypatch)


def _recent(count, tenant="t1", state="executed", prefix="AO"):
    now = datetime.now(timezone.utc)
    return [_doc(f"{prefix}-{i:05d}", tenant, state, now - timedelta(seconds=i + 1)) for i in range(count)]


async def test_screen_export_csv_follows_bucket_and_period_and_audits_it(api):
    await _put(api.db, *_recent(3), *_recent(2, state="failed", prefix="FA"), *_recent(2, "t2", prefix="T2"))
    got = await api.get(f"{EXPORT}?format=csv&bucket=done&days=30")
    assert got.status_code == 200
    assert got.headers["content-type"].startswith("text/csv")
    assert re.fullmatch(r'attachment; filename="autonomous-ops-activity-t1-\d{8}\.csv"',
                        got.headers["content-disposition"])
    assert (got.headers["x-export-rows"], got.headers["x-export-total"], got.headers["x-export-truncated"]) == \
        ("3", "3", "false")
    table = list(csv.reader(io.StringIO(got.text)))
    assert table[0] == HEADER and len(table) == 4 and {row[1] for row in table[1:]} == {"Done"}
    api.audit.assert_awaited_once()
    args, fields = api.audit.await_args.args, api.audit.await_args.kwargs
    assert args == ("autonomous_ops.export", "t1")
    assert (fields["outcome"], fields["format"], fields["bucket"], fields["days"]) == ("success", "csv", "done", "30")
    assert (fields["rows"], fields["total"], fields["truncated"], fields["entry"]) == (3, 3, False, "screen")
    assert fields["actor"] == {"email": "tenant_admin@example.test", "role": "tenant_admin", "tenantId": "t1"}


async def test_screen_export_pdf_is_a_pdf(api):
    await _put(api.db, *_recent(2))
    got = await api.get(f"{EXPORT}?format=pdf&bucket=all&days=7")
    assert got.status_code == 200 and got.headers["content-type"] == "application/pdf"
    assert got.content.startswith(b"%PDF") and got.headers["x-export-rows"] == "2"


async def test_screen_export_says_so_when_the_cap_cut_rows(api):
    await _put(api.db, *_recent(EXPORT_ROW_CAP + 1))
    got = await api.get(f"{EXPORT}?format=csv&bucket=all&days=all")
    assert (got.headers["x-export-rows"], got.headers["x-export-total"], got.headers["x-export-truncated"]) == \
        ("5000", "5001", "true")
    assert api.audit.await_args.kwargs["truncated"] is True and api.audit.await_args.kwargs["total"] == 5001


async def test_screen_export_with_nothing_to_export_is_204_and_not_audited(api):
    await _put(api.db, *_recent(2, "t2", prefix="T2"))
    got = await api.get(f"{EXPORT}?format=csv&bucket=done&days=30")
    assert got.status_code == 204 and got.content == b"" and got.headers["x-export-total"] == "0"
    api.audit.assert_not_awaited()


@pytest.mark.parametrize("query,role,tenant,status,detail", [
    ("format=csv&days=30", "analyst", "t1", 403, DENIED),                       # views, may not export
    ("format=csv&tenantId=t1", "platform_support", "t1", 403, DENIED),          # Platform Support has no export:reports
    ("format=csv&tenantId=t2", "tenant_admin", "t1", 403, None),                # another organization
    ("format=csv&tenantId=platform-admin", "super_admin", "t1", 409, None),     # the platform organization
    ("format=csv", "super_admin", "t1", 400, None),                             # platform staff must name one
    ("format=xlsx", "tenant_admin", "t1", 422, None),
    ("format=csv&bucket=nope", "tenant_admin", "t1", 422, None),
    ("format=csv&days=14", "tenant_admin", "t1", 422, None),
    ("days=30", "tenant_admin", "t1", 422, None),
])
async def test_screen_export_refusals(api, query, role, tenant, status, detail):
    await _put(api.db, *_recent(2))
    got = await api.get(f"{EXPORT}?{query}", role=role, tenant=tenant)
    assert got.status_code == status
    if detail:
        assert got.json()["detail"] == detail
    api.audit.assert_not_awaited()


async def test_platform_owner_exports_the_organization_they_name_and_only_that_one(api):
    await _put(api.db, *_recent(2), *_recent(3, "t2", prefix="T2"))
    got = await api.get(f"{EXPORT}?format=csv&tenantId=t2", role="super_admin")
    assert got.status_code == 200 and got.headers["x-export-rows"] == "3"
    assert {row[6] for row in list(csv.reader(io.StringIO(got.text)))[1:]} == {"playbook:contain-ip"}
    assert api.audit.await_args.args == ("autonomous_ops.export", "t2")
    assert api.audit.await_args.kwargs["actor"]["tenantId"] == PLATFORM


async def test_a_blocking_dlp_finding_refuses_the_export_and_records_the_incident(api, monkeypatch):
    await _put(api.db, *_recent(2))
    finding = {"name": "Credit card"}
    monkeypatch.setattr(dlp_service, "scan_export", AsyncMock(return_value=([finding], [])))
    got = await api.get(f"{EXPORT}?format=csv")
    assert got.status_code == 403 and got.json()["detail"] == "Export blocked by DLP policy: Credit card"
    api.incident.assert_awaited_once()
    assert api.incident.await_args.kwargs["blocked"] is True
    api.audit.assert_not_awaited()


def test_the_export_controls_cover_the_route_and_the_browser_may_read_its_headers():
    assert export_controls.EXPORT_PATHS.match("/api/autonomous-ops/export")
    assert not export_controls.EXPORT_PATHS.match("/api/autonomous-ops/export/other")
    for path in ("/api/reports/export", "/api/itam/data/export", "/api/tickets/export/csv"):
        assert export_controls.EXPORT_PATHS.match(path)
    import app_middleware
    from rate_limiter import limiter
    app = FastAPI()
    app_middleware.register_middleware(app, limiter)
    cors = next(m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware")
    assert {"X-Export-Rows", "X-Export-Total", "X-Export-Truncated"} <= set(cors.kwargs["expose_headers"])
