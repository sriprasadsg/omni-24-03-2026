"""RESP-01, D-07 / D-08: vulnerabilities and file changes are one quiet suggestion per computer and kind.
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=a computer that reports hundreds of findings produces ONE suggestion row that is refreshed in
place, ends when the findings are gone and never becomes an approval card or an instruction; a FIM change is
never evidence of malice; fails_when=240 findings make more than one row, an unchanged tick writes, a changed
tick adds a row or an audit event, a vanished finding leaves its row open, or a file change writes an origin;
no_claim=the Activity screen (83-18) and real agents.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import ledger, protected, response_views, signals, sweep
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_agent, seed_fim_event, seed_feed_ioc, seed_tenant

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
SHA = "ab" * 32
SEVERITIES = ["Low", "Medium", "High", "Critical"]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()


async def _world(db, tenant="t1", **kw):
    await ledger.ensure_indexes(db)
    await signals.ensure_indexes(db)
    await seed_tenant(db, tenant, shadow=False, **kw)
    await seed_agent(db, tenant, f"a-{tenant}", hostname=f"host-{tenant}")


async def _vulns(db, n, *, tenant="t1", agent="host-t1", start=0, cve=True, severity=None):
    docs = []
    for i in range(start, start + n):
        docs.append({"tenantId": tenant, "agentId": agent, "source": "agent", "status": "Open",
                     "cveId": f"CVE-2026-{i:05d}" if cve else None, "cve_id": f"CVE-2026-{i:05d}" if cve else None,
                     "severity": severity or SEVERITIES[i % 4], "package": f"pkg-{i:05d}"})
    if docs:
        await db.vulnerabilities.insert_many(docs)


async def _tick(db, at=NOW):
    return await sweep.tick(db, now=at)


async def _rows(db, tenant="t1", state=None):
    flt = {"tenantId": tenant, "kind": {"$ne": "control"}}
    if state:
        flt["state"] = state
    return [r async for r in db.autonomy_actions.find(flt, {"_id": 0}).sort("createdAt", 1)]


async def _audit(db, tenant="t1"):
    return await db.audit_logs.count_documents({"tenantId": tenant})


# ------------------------------------------------------------------ vulnerabilities (D-07)

async def test_240_vulnerabilities_on_one_computer_are_one_suggested_row(mongo_db):
    await _world(mongo_db)
    await _vulns(mongo_db, 240)
    await _tick(mongo_db)
    (row,) = await _rows(mongo_db)
    assert row["state"] == "suggested" and row["command"] == "upgrade_software" and row["targets"] == ["a-t1"]
    inputs = row["reason"]["inputs"]
    assert inputs["suggestionOnly"] is True and row["reason"]["ruleId"] == "sweep:suggest_vulnerability"
    suggestion = inputs["suggestion"]
    assert suggestion["kind"] == "vulnerability" and suggestion["count"] == 240 and suggestion["severity"] == "Critical"
    assert len(suggestion["items"]) == 10
    # severity first (all Critical here), then the id
    assert [i["cve"] for i in suggestion["items"]] == sorted(i["cve"] for i in suggestion["items"])
    assert all(i["cve"].startswith("CVE-2026-") for i in suggestion["items"])
    view = response_views.row_extras(row, host="host-t1", now=NOW)["suggestion"]
    assert view["openView"] == "patchManagement" and view["count"] == 240 and len(view["items"]) == 10
    assert await mongo_db.agent_instructions.count_documents({}) == 0
    assert await mongo_db.autonomy_actions.count_documents({"state": "awaiting_approval"}) == 0


async def test_items_are_sorted_by_severity_and_then_by_id(mongo_db):
    await _world(mongo_db)
    await _vulns(mongo_db, 4, severity="Low")
    await _vulns(mongo_db, 3, start=100, severity="High")
    await _vulns(mongo_db, 1, start=200, severity="Medium")
    await _tick(mongo_db)
    (row,) = await _rows(mongo_db)
    suggestion = row["reason"]["inputs"]["suggestion"]
    assert suggestion["severity"] == "High" and suggestion["count"] == 8
    assert [i["cve"] for i in suggestion["items"]] == [
        "CVE-2026-00100", "CVE-2026-00101", "CVE-2026-00102", "CVE-2026-00200",
        "CVE-2026-00000", "CVE-2026-00001", "CVE-2026-00002", "CVE-2026-00003"]


async def test_findings_with_and_without_a_cve_share_the_row(mongo_db):
    await _world(mongo_db)
    await _vulns(mongo_db, 3)
    await _vulns(mongo_db, 2, start=50, cve=False, severity="Medium")
    await _tick(mongo_db)
    (row,) = await _rows(mongo_db)
    suggestion = row["reason"]["inputs"]["suggestion"]
    assert suggestion["count"] == 5
    assert any("cve" not in i and i.get("package") for i in suggestion["items"])
    assert any(i.get("cve") for i in suggestion["items"])


async def test_only_open_agent_vulnerabilities_of_this_tenant_count(mongo_db):
    await _world(mongo_db)
    await _world(mongo_db, "t2")
    await _vulns(mongo_db, 2)
    await _vulns(mongo_db, 5, tenant="t2", agent="host-t2")
    await mongo_db.vulnerabilities.insert_many([
        {"tenantId": "t1", "agentId": "host-t1", "source": "agent", "status": "Fixed", "cveId": "CVE-1", "severity": "High"},
        {"tenantId": "t1", "agentId": "host-t1", "source": "scanner", "status": "Open", "cveId": "CVE-2", "severity": "High"}])
    await _tick(mongo_db)
    (one,), (two,) = await _rows(mongo_db), await _rows(mongo_db, "t2")
    assert one["reason"]["inputs"]["suggestion"]["count"] == 2 and one["tenantId"] == "t1"
    assert two["reason"]["inputs"]["suggestion"]["count"] == 5 and two["targets"] == ["a-t2"]


async def test_ten_ticks_with_no_change_leave_one_row_and_no_write_after_the_first(mongo_db):
    await _world(mongo_db)
    await _vulns(mongo_db, 30)
    await _tick(mongo_db)
    before, audit = await mongo_db.autonomy_actions.find({}, {"_id": 0}).to_list(10), await _audit(mongo_db)
    for minute in range(1, 11):
        await _tick(mongo_db, NOW + timedelta(minutes=minute))
    assert await mongo_db.autonomy_actions.find({}, {"_id": 0}).to_list(10) == before
    assert len(before) == 1 and await _audit(mongo_db) == audit


async def test_the_expiry_is_extended_only_when_under_twelve_hours_remain(mongo_db):
    await _world(mongo_db)
    await _vulns(mongo_db, 3)
    await _tick(mongo_db)
    (first,) = await _rows(mongo_db)
    expires = first["approval"]["expiresAt"].replace(tzinfo=timezone.utc)
    await _tick(mongo_db, expires - timedelta(hours=12))                       # exactly 12 hours left: no write
    (same,) = await _rows(mongo_db)
    assert same["updatedAt"] == first["updatedAt"] and same["approval"]["expiresAt"] == first["approval"]["expiresAt"]
    late = expires - timedelta(hours=11, minutes=59)
    await _tick(mongo_db, late)
    (extended,) = await _rows(mongo_db)
    assert extended["id"] == first["id"] and extended["state"] == "suggested"
    assert extended["approval"]["expiresAt"].replace(tzinfo=timezone.utc) == late + timedelta(hours=24)
    assert extended["createdAt"] == first["createdAt"]                          # nothing changed but the clock


async def test_a_new_vulnerability_updates_the_row_in_place_with_no_new_row_and_no_audit_event(mongo_db):
    await _world(mongo_db)
    await _vulns(mongo_db, 5)
    await _tick(mongo_db)
    (first,) = await _rows(mongo_db)
    audit = await _audit(mongo_db)
    await _vulns(mongo_db, 1, start=500, severity="Critical")
    later = NOW + timedelta(minutes=5)
    await _tick(mongo_db, later)
    (row,) = await _rows(mongo_db)
    assert row["id"] == first["id"] and row["state"] == "suggested"
    assert row["reason"]["inputs"]["suggestion"]["count"] == 6
    assert row["createdAt"].replace(tzinfo=timezone.utc) == later and row["createdAt"] != first["createdAt"]
    assert await _audit(mongo_db) == audit and await mongo_db.autonomy_actions.count_documents({}) == 1


async def test_when_no_vulnerabilities_are_left_the_row_ends_expired_superseded(mongo_db):
    await _world(mongo_db)
    await _vulns(mongo_db, 5)
    await _tick(mongo_db)
    await mongo_db.vulnerabilities.update_many({}, {"$set": {"status": "Fixed"}})
    await _tick(mongo_db, NOW + timedelta(minutes=2))
    (row,) = await _rows(mongo_db)
    assert row["state"] == "expired" and row["reasonCode"] == "superseded" and row["reasonText"]
    await _tick(mongo_db, NOW + timedelta(minutes=3))
    assert len(await _rows(mongo_db)) == 1                                       # nothing new for nothing


async def test_findings_that_return_after_the_row_ended_make_a_new_row(mongo_db):
    await _world(mongo_db)
    await _vulns(mongo_db, 2)
    await _tick(mongo_db)
    await mongo_db.vulnerabilities.update_many({}, {"$set": {"status": "Fixed"}})
    await _tick(mongo_db, NOW + timedelta(minutes=2))
    await mongo_db.vulnerabilities.update_many({}, {"$set": {"status": "Open"}})
    await _tick(mongo_db, NOW + timedelta(minutes=4))
    assert [r["state"] for r in await _rows(mongo_db)] == ["expired", "suggested"]


async def test_two_computers_give_two_rows_and_two_tenants_stay_apart(mongo_db):
    await _world(mongo_db)
    await seed_agent(mongo_db, "t1", "a-second", hostname="host-second")
    await _world(mongo_db, "t2")
    await _vulns(mongo_db, 3)
    await _vulns(mongo_db, 4, agent="host-second")
    await _vulns(mongo_db, 6, tenant="t2", agent="a-t2")
    await _tick(mongo_db)
    rows = await _rows(mongo_db)
    assert sorted((r["targets"][0], r["reason"]["inputs"]["suggestion"]["count"]) for r in rows) == [
        ("a-second", 4), ("a-t1", 3)]
    assert [(r["targets"][0], r["reason"]["inputs"]["suggestion"]["count"]) for r in await _rows(mongo_db, "t2")] == [("a-t2", 6)]


async def test_a_hostname_shared_by_two_computers_is_skipped_and_an_id_is_resolved(mongo_db):
    await _world(mongo_db)
    await seed_agent(mongo_db, "t1", "dup-1", hostname="Dup")
    await mongo_db.agents.insert_one({"id": "dup-2", "tenantId": "t1", "hostname": "dup ", "status": "Online"})
    await _vulns(mongo_db, 2, agent="dup")
    await _vulns(mongo_db, 3, agent="a-t1")                                        # an agent id works too
    await _tick(mongo_db)
    rows = await _rows(mongo_db)
    assert [(r["targets"], r["reason"]["inputs"]["suggestion"]["count"]) for r in rows] == [(["a-t1"], 3)]


async def test_a_never_touch_computer_records_one_refused_row_and_the_memory_holds_it_a_day(mongo_db):
    await _world(mongo_db)
    await _vulns(mongo_db, 2)
    await protected.add_entry(mongo_db, scope="tenant", tenant_id="t1", kind="agent", value="a-t1")
    for minute in range(5):
        await _tick(mongo_db, NOW + timedelta(minutes=minute))
    (row,) = await _rows(mongo_db)
    assert row["state"] == "refused" and row["reasonCode"] == "protected_target"
    await _tick(mongo_db, NOW + timedelta(hours=25))
    assert [r["state"] for r in await _rows(mongo_db)] == ["refused", "refused"]


async def test_a_tenant_in_shadow_gets_one_simulation_per_computer_and_kind_in_a_day(mongo_db):
    await _world(mongo_db)
    await mongo_db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"shadow": True}})
    await _vulns(mongo_db, 3)
    for minute in range(6):
        await _tick(mongo_db, NOW + timedelta(minutes=minute))
    (row,) = await _rows(mongo_db)
    assert row["state"] == "shadow"


async def test_a_row_exists_whether_or_not_the_agent_supports_any_action(mongo_db):
    await _world(mongo_db)                                  # a plain agent: no tokens, no capability ticks
    await _vulns(mongo_db, 1)
    await _tick(mongo_db)
    assert len(await _rows(mongo_db, state="suggested")) == 1


async def test_the_approve_route_would_refuse_the_row_because_it_is_suggestion_only(mongo_db):
    await _world(mongo_db)
    await _vulns(mongo_db, 1)
    await _tick(mongo_db)
    (row,) = await _rows(mongo_db)
    assert row["reason"]["inputs"]["suggestionOnly"] is True and row["undo"]["available"] is False


# ------------------------------------------------------------------ file changes (D-08)

async def _change(db, path, *, change="Changed", at=None, hash_after=None, tenant="t1", agent="host-t1"):
    stamp = (at or NOW - timedelta(minutes=5)).isoformat()
    await db.fim_events.insert_one({"id": f"{path}-{stamp}-{change}", "agent_id": agent, "tenantId": tenant,
                                    "path": path, "change_type": change, "hash_after": hash_after,
                                    "sha256": None, "received_at": stamp})


async def test_three_changed_paths_in_a_day_are_one_row_with_the_paths(mongo_db):
    await _world(mongo_db)
    for path in ("/etc/ssh/sshd_config", "/etc/hosts", "/etc/passwd"):
        await _change(mongo_db, path)
    await _tick(mongo_db)
    (row,) = await _rows(mongo_db)
    suggestion = row["reason"]["inputs"]["suggestion"]
    assert row["state"] == "suggested" and row["command"] == "restore_file" and row["targets"] == ["a-t1"]
    assert row["reason"]["ruleId"] == "sweep:suggest_file_change" and row["reason"]["inputs"]["suggestionOnly"] is True
    assert suggestion["kind"] == "file_change" and suggestion["count"] == 3
    assert [i["path"] for i in suggestion["items"]] == ["/etc/hosts", "/etc/passwd", "/etc/ssh/sshd_config"]
    view = response_views.row_extras(row, host="host-t1", now=NOW)["suggestion"]
    assert view["openView"] == "fimMonitoring" and view["count"] == 3
    assert await mongo_db.agent_instructions.count_documents({}) == 0


async def test_duplicate_events_on_one_path_count_once_and_hostnames_resolve(mongo_db):
    await _world(mongo_db)
    for minute in range(4):
        await _change(mongo_db, "/etc/hosts", at=NOW - timedelta(minutes=minute + 1))
    await _change(mongo_db, "/etc/hosts", agent="a-t1")
    await _tick(mongo_db)
    (row,) = await _rows(mongo_db)
    assert row["reason"]["inputs"]["suggestion"]["count"] == 1


async def test_an_added_or_removed_event_is_not_a_change(mongo_db):
    await _world(mongo_db)
    await _change(mongo_db, "/etc/new", change="Added")
    await _change(mongo_db, "/etc/gone", change="Removed")
    await _change(mongo_db, "/etc/odd", change=None)
    await _tick(mongo_db)
    assert await _rows(mongo_db) == []
    await _change(mongo_db, "/etc/real")
    await _tick(mongo_db, NOW + timedelta(minutes=1))
    (row,) = await _rows(mongo_db)
    assert row["reason"]["inputs"]["suggestion"]["count"] == 1


async def test_a_path_whose_hash_is_flagged_leaves_the_row_and_without_others_there_is_no_row(mongo_db):
    await _world(mongo_db)
    await seed_feed_ioc(mongo_db, ioc_type="hash", value=SHA, feed="malwarebazaar")
    await _change(mongo_db, "/tmp/evil", hash_after=SHA)
    await _tick(mongo_db)
    assert await mongo_db.autonomy_signals.count_documents({"kind": "file", "indicator": SHA, "agentId": "a-t1"}) == 1
    assert [r for r in await _rows(mongo_db) if r["command"] == "restore_file"] == []
    await _change(mongo_db, "/etc/hosts", hash_after="cd" * 32)
    await _tick(mongo_db, NOW + timedelta(minutes=1))
    (row,) = [r for r in await _rows(mongo_db) if r["command"] == "restore_file"]
    assert [i["path"] for i in row["reason"]["inputs"]["suggestion"]["items"]] == ["/etc/hosts"]


async def test_the_same_hash_flagged_on_another_computer_does_not_remove_this_ones_path(mongo_db):
    await _world(mongo_db)
    await seed_agent(mongo_db, "t1", "a-other", hostname="host-other")
    await mongo_db.autonomy_signals.insert_one({"tenantId": "t1", "agentId": "a-other", "kind": "file", "indicator": SHA,
                                                "origins": {}, "lastSeenAt": NOW})
    await _change(mongo_db, "/etc/hosts", hash_after=SHA)
    await _tick(mongo_db)
    (row,) = await _rows(mongo_db)
    assert row["reason"]["inputs"]["suggestion"]["count"] == 1


async def test_a_file_change_tick_writes_no_signal_and_no_origin(mongo_db):
    await _world(mongo_db)
    for path in ("/etc/a", "/etc/b"):
        await _change(mongo_db, path, hash_after="ef" * 32)
    before = await mongo_db.autonomy_signals.find({}, {"_id": 0}).to_list(50)
    await _tick(mongo_db)
    await _tick(mongo_db, NOW + timedelta(minutes=1))
    assert len(await _rows(mongo_db)) == 1
    assert await mongo_db.autonomy_signals.find({}, {"_id": 0}).to_list(50) == before == []


async def test_events_older_than_a_day_are_ignored_and_the_row_closes_when_none_remain(mongo_db):
    await _world(mongo_db)
    await _change(mongo_db, "/etc/hosts", at=NOW - timedelta(hours=23))
    await _change(mongo_db, "/etc/old", at=NOW - timedelta(hours=30))
    await _tick(mongo_db)
    (row,) = await _rows(mongo_db)
    assert row["reason"]["inputs"]["suggestion"]["count"] == 1
    await _tick(mongo_db, NOW + timedelta(hours=2))
    (row,) = await _rows(mongo_db)
    assert row["state"] == "expired" and row["reasonCode"] == "superseded"


async def test_vulnerabilities_and_file_changes_are_two_rows_for_one_computer(mongo_db):
    await _world(mongo_db)
    await _vulns(mongo_db, 3)
    await _change(mongo_db, "/etc/hosts")
    await _tick(mongo_db)
    await _tick(mongo_db, NOW + timedelta(minutes=1))
    assert sorted(r["command"] for r in await _rows(mongo_db)) == ["restore_file", "upgrade_software"]
