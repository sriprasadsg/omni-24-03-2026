"""SOC case work (soc_cases, soc_case_endpoints): tasks and evidence. protects/fails_when/no_claim per test; real MongoDB."""
import hashlib
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
import soc_cases
from tenant_context import reset_tenant_id, set_tenant_id
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def db(mongo_db, monkeypatch, tmp_path):  # noqa: F811
    monkeypatch.setattr(database.mongodb, "db", mongo_db)
    monkeypatch.setattr(soc_cases, "EVIDENCE_DIR", str(tmp_path / "evidence"))
    await mongo_db.security_cases.insert_many([
        {"id": "case-1", "tenantId": "t1", "title": "Case: persistence", "alertIds": ["a1", "a2"], "relatedEvents": []},
        {"id": "case-9", "tenantId": "t2", "title": "Other tenant", "alertIds": []},
    ])
    await mongo_db.security_alerts.insert_many([
        {"id": "a1", "tenantId": "t1", "agent_id": "h1", "type": "persistence_mechanism", "location": "Windows Task Scheduler",
         "metadata": {"user": "bob"}, "remote_ip": "45.33.32.156", "status": "open"},
        {"id": "a2", "tenantId": "t1", "agent_id": "h1", "type": "fim_violation", "metadata": {"path": "/etc/passwd", "user": "bob"},
         "status": "open"},
    ])
    token = set_tenant_id("platform-admin")
    try:
        yield mongo_db
    finally:
        reset_tenant_id(token)


async def test_standard_steps_follow_the_alert_types_and_are_added_once(db):
    """protects=the checklist starts with confirm, adds a step per alert type, then scope..write-up; a second run adds
    nothing; fails_when=steps duplicate or ignore the case's alerts; no_claim=-"""
    first = await soc_cases.add_standard_steps(db, "t1", "case-1", "ana")
    titles = [t["title"] for t in first["tasks"]]
    assert titles[0] == soc_cases.STANDARD_STEPS[0]
    assert soc_cases.TYPE_STEPS["persistence_mechanism"] in titles and soc_cases.TYPE_STEPS["fim_violation"] in titles
    assert titles[-1] == soc_cases.STANDARD_STEPS[-1] and first["added"] == len(soc_cases.STANDARD_STEPS) + 2
    again = await soc_cases.add_standard_steps(db, "t1", "case-1", "ana")
    assert again["added"] == 0
    assert (await soc_cases.work(db, "t1", "case-1"))["standardSteps"] == []


async def test_task_lifecycle_records_who_and_needs_a_reason_to_skip(db):
    """protects=done records who and when, reopening clears it, skipping needs a note, another tenant's case is 404;
    fails_when=a task closes anonymously, is skipped silently or reached across tenants; no_claim=-"""
    task = await soc_cases.add_task(db, "t1", "case-1", "ana", "  Check   the   host ", assignee="bo", due_at="2026-11-20T09:00:00Z")
    assert task["title"] == "Check the host" and task["dueAt"] == "2026-11-20T09:00:00+00:00"
    done = await soc_cases.update_task(db, "t1", "case-1", task["id"], "bo", {"status": "done"})
    assert done["status"] == "done" and done["closedBy"] == "bo" and done["closedAt"]
    back = await soc_cases.update_task(db, "t1", "case-1", task["id"], "bo", {"status": "todo"})
    assert "closedBy" not in back and "closedAt" not in back
    with pytest.raises(soc_cases.CaseError, match="why"):
        await soc_cases.update_task(db, "t1", "case-1", task["id"], "bo", {"status": "skipped"})
    skipped = await soc_cases.update_task(db, "t1", "case-1", task["id"], "bo", {"status": "skipped", "note": "host rebuilt"})
    assert skipped["note"] == "host rebuilt"
    for call in (soc_cases.add_task(db, "t2", "case-1", "eve", "x"), soc_cases.update_task(db, "t1", "case-9", task["id"], "eve", {"status": "done"})):
        with pytest.raises(soc_cases.CaseError) as e:
            await call
        assert e.value.status == 404


async def test_alert_indicators_become_evidence_once_and_manual_duplicates_are_refused(db):
    """protects=the case's alerts give user, IP and file indicators linked to their alerts (no techniques), added once;
    adding a held indicator by hand is refused; fails_when=indicators duplicate or lose their alerts; no_claim=-"""
    offered = (await soc_cases.work(db, "t1", "case-1"))["alertIndicators"]
    kinds = {(i["indicatorKind"], i["key"]) for i in offered}
    assert {("user", "bob"), ("ip", "45.33.32.156"), ("file", "/etc/passwd")} <= kinds
    assert all(i["indicatorKind"] != "technique" for i in offered)
    bob = next(i for i in offered if i["key"] == "bob")
    assert sorted(bob["alertIds"]) == ["a1", "a2"]
    out = await soc_cases.add_alert_indicators(db, "t1", "case-1", "ana")
    assert out["added"] == len(offered)
    assert (await soc_cases.add_alert_indicators(db, "t1", "case-1", "ana"))["added"] == 0
    with pytest.raises(soc_cases.CaseError) as e:
        await soc_cases.add_evidence(db, "t1", "case-1", "ana", "indicator", "BOB", "user")
    assert e.value.status == 409
    note = await soc_cases.add_evidence(db, "t1", "case-1", "ana", "note", "Bob confirmed the task is his")
    assert note["custody"][0]["action"] == "added" and note["custody"][0]["by"] == "ana"


async def test_file_evidence_keeps_its_hash_logs_downloads_and_is_excluded_not_deleted(db):
    """protects=an uploaded file is stored with its SHA-256 outside the listing, a download goes on the custody log,
    exclusion needs a reason and can be undone, the stored name never leaves the server, oversize is 413;
    fails_when=evidence is deleted, served without a trail or its storage path leaks; no_claim=HTTP streaming"""
    data = b"MZ\x90\x00 sample"
    item = await soc_cases.add_file(db, "t1", "case-1", "ana", "../../evil sample.exe", data, note="from the desktop")
    assert item["sha256"] == hashlib.sha256(data).hexdigest() and item["value"] == "evil_sample.exe" and "storedAs" not in item
    listed = (await soc_cases.work(db, "t1", "case-1"))["evidence"]
    assert listed[0]["id"] == item["id"] and "storedAs" not in listed[0]
    got = await soc_cases.file_for_download(db, "t1", "case-1", item["id"], "bo")
    assert open(got["path"], "rb").read() == data and got["path"].startswith(soc_cases.EVIDENCE_DIR)
    with pytest.raises(soc_cases.CaseError):
        await soc_cases.file_for_download(db, "t2", "case-1", item["id"], "eve")
    with pytest.raises(soc_cases.CaseError, match="why"):
        await soc_cases.set_excluded(db, "t1", "case-1", item["id"], "bo", True, "")
    out = await soc_cases.set_excluded(db, "t1", "case-1", item["id"], "bo", True, "not related")
    assert out["excluded"] is True
    back = await soc_cases.set_excluded(db, "t1", "case-1", item["id"], "bo", False, None)
    assert [c["action"] for c in back["custody"]] == ["added", "downloaded", "excluded", "restored"]
    assert await db.soc_case_evidence.count_documents({"caseId": "case-1"}) == 1
    with pytest.raises(soc_cases.CaseError) as e:
        await soc_cases.add_file(db, "t1", "case-1", "ana", "big.bin", b"x" * (soc_cases.MAX_FILE_BYTES + 1))
    assert e.value.status == 413


async def test_case_routes_carry_the_security_overview_guard():
    """protects=every case-work route needs the Security Overview catalogue; fails_when=a route is mounted unguarded;
    no_claim=the permission strings themselves"""
    import soc_case_endpoints
    for route in soc_case_endpoints.router.routes:
        tags = [getattr(d.dependency, "__catalogue_guard__", None) for d in route.dependencies]
        assert any(t and t["catalogue"] == "security" for t in tags), route.path
