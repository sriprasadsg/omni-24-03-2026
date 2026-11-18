"""SIEM pipeline (siem_pipeline, migration 039). protects/fails_when/no_claim per test; real MongoDB.

Linux lines are copied from this server's auth.log on 2026-11-18 (internet SSH probes).
"""
import importlib
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
import siem_pipeline
from tenant_context import reset_tenant_id, set_tenant_id
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

migration = importlib.import_module("migrations.039_siem_rules_executable")
T0 = datetime(2026, 11, 18, 14, 0, tzinfo=timezone.utc)


def _line(minute: float, text: str, prog: str = "sshd[463926]") -> str:
    return f"{(T0 + timedelta(minutes=minute)).isoformat()} Omniai-copy {prog}: {text}"


@pytest.mark.parametrize("text,prog,expected", [
    ("Invalid user admin from 35.187.231.181 port 37088", "sshd[1]", {"action": "login_failed", "user": "admin", "srcIp": "35.187.231.181"}),
    ("Invalid user  from 35.187.231.181 port 37062", "sshd[1]", {"action": "login_failed", "user": None, "srcIp": "35.187.231.181"}),
    ("Failed password for invalid user probe from 193.46.255.86 port 64544 ssh2", "sshd[1]", {"action": "login_failed", "user": "probe"}),
    ("Accepted publickey for azureuser from 203.193.174.92 port 50122 ssh2", "sshd[1]", {"action": "login_success", "user": "azureuser"}),
    ("pam_unix(sudo:auth): authentication failure; logname=bob uid=1001 euid=0 tty=/dev/pts/0 ruser=bob rhost=  user=bob", "sudo",
     {"action": "sudo_failed", "user": "bob"}),
    ("new user: name=backdoor, UID=1002, GID=1002, home=/home/backdoor, shell=/bin/bash, from=/dev/pts/1", "useradd[9]",
     {"action": "account_created", "user": "backdoor"}),
    ("add 'backdoor' to group 'sudo'", "usermod[9]", {"action": "admin_group_add", "user": "backdoor", "group": "sudo"}),
    ("Started session-12.scope - Session 12 of User azureuser.", "systemd[1]", None),
])
def test_linux_lines_become_events_and_noise_does_not(text, prog, expected):
    """protects=sshd failures (incl. an empty user), accepted keys, sudo failures, useradd and sudo-group adds are
    recognised with user and source IP; ordinary lines are not; fails_when=attacks are missed or every line is
    copied; no_claim=other daemons' formats"""
    event = siem_pipeline.parse_linux({"message": _line(0, text, prog)})
    if expected is None:
        assert event is None
    else:
        assert {k: event.get(k) for k in expected} == expected and event["source"] == "linux_auth"


@pytest_asyncio.fixture
async def db(mongo_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(database.mongodb, "db", mongo_db)
    monkeypatch.setenv("SOC_AUTO_TRIAGE", "0")
    await mongo_db.siem_rules.insert_one({"id": "old-1", "tenant_id": "platform-admin", "name": "Password Spray via Microsoft Entra",
                                          "conditions": {"threshold": "20_accounts/10m"}, "mitre_technique": "T1110.003"})
    await migration.up(mongo_db)
    token = set_tenant_id("platform-admin")
    try:
        yield mongo_db
    finally:
        reset_tenant_id(token)


async def _logs(db, tenant, agent, lines):
    await db.logs.insert_many([{"service": "auth", "tenantId": tenant, "agentId": agent, "message": m} for m in lines])


@pytest.mark.asyncio
async def test_brute_force_and_spray_hit_once_in_record_mode_and_stay_inside_the_tenant(db):
    """protects=10 failures from one IP in 10 minutes is one brute-force hit and 5 accounts one spray hit, kept to the
    tenant whose agent saw them; the next pass makes no second hit; library rules record without alerting for 7 days;
    9 failures from another IP or another tenant's lines do not hit; fails_when=a hit per pass, a cross-tenant count,
    or alerts before the tuning week; no_claim=-"""
    users = ["root", "admin", "test", "oracle", "ubuntu"]
    await _logs(db, "t1", "ag1", [_line(i * 0.5, f"Invalid user {users[i % 5]} from 35.187.231.181 port {4000 + i}") for i in range(10)])
    await _logs(db, "t1", "ag1", [_line(i, f"Invalid user x from 193.46.255.86 port {5000 + i}") for i in range(9)])
    await _logs(db, "t2", "ag9", [_line(i, f"Invalid user y from 35.187.231.181 port {6000 + i}") for i in range(3)])
    out = await siem_pipeline.run_once(db)
    assert out["events"] == 22
    hits = await db.siem_hits.find({}, {"_id": 0}).to_list(10)
    assert sorted((h["ruleId"], h["tenantId"], h["group"], h["count"]) for h in hits) == [
        ("lib-linux-ssh-bruteforce", "t1", "35.187.231.181", 10), ("lib-linux-ssh-spray", "t1", "35.187.231.181", 5)]
    assert all(h["alerted"] is False for h in hits) and await db.security_alerts.count_documents({}) == 0
    await _logs(db, "t1", "ag1", [_line(6, "Invalid user root from 35.187.231.181 port 7000")])
    assert (await siem_pipeline.run_once(db))["hits"] == 0
    assert (await db.siem_rules.find_one({"id": "lib-linux-ssh-bruteforce"}))["match_count"] == 1


@pytest.mark.asyncio
async def test_an_alerting_rule_raises_one_soc_alert_and_windows_events_are_read_once(db):
    """protects=once a rule alerts, its hit is a SOC alert (type siem_rule, the rule's technique, tenant and endpoint);
    heartbeat Windows events become events once, however often the heartbeat repeats them; fails_when=hits never
    reach analysts or a repeated heartbeat doubles the count; no_claim=-"""
    await db.siem_rules.update_many({"id": {"$in": ["lib-win-admin-group", "lib-linux-new-account"]}}, {"$set": {"mode": "alert"}})
    await db.agents.insert_one({"id": "win1", "tenantId": "t1", "hostname": "PC-1", "meta": {"log_collection": {"recent_events": [
        {"source": "Microsoft-Windows-Security-Auditing", "event_id": 4732, "time": "2026-11-18T14:05:00Z",
         "message": "A member was added to a security-enabled local group.\r\nMember:\r\n Account Name: CORP\\eve\r\nGroup:\r\n Group Name: Administrators"},
        {"source": "Microsoft-Windows-GroupPolicy", "event_id": 1500, "time": "2026-11-18T14:05:01Z", "message": "Group Policy ok"}]}}})
    await _logs(db, "t1", "ag1", [_line(1, "new user: name=backdoor, UID=1002, GID=1002", "useradd[9]")])
    assert (await siem_pipeline.run_once(db)) == {"events": 2, "hits": 2}
    assert (await siem_pipeline.run_once(db))["events"] == 0
    alerts = {a["rule"]: a for a in await db.security_alerts.find({}, {"_id": 0}).to_list(10)}
    win = alerts["Account added to Administrators"]
    assert (win["type"], win["tenantId"], win["agent_id"], win["severity"]) == ("siem_rule", "t1", "win1", "high")
    assert "T1098" in win["mitre"] and alerts["New local account on a Linux host"]["agent_id"] == "ag1"


def _sec(record: int, eid: int, minute: float, log: str = "Security", **data) -> dict:
    return {"log": log, "source": "Microsoft-Windows-Security-Auditing", "event_id": eid, "record_id": record,
            "time": (T0 + timedelta(minutes=minute)).strftime("%Y-%m-%dT%H:%M:%S.1234567Z"), "data": data}


@pytest.mark.asyncio
async def test_security_log_fields_from_agent_2_1_21_feed_the_windows_rules_once(db):
    """protects=the 2.1.21 heartbeat's Security events (event data, record number) become events with the account,
    source address and group; Administrators is known by its SID in any language; a resent record counts once and
    the agent's recent_events are not read beside them; ten failed sign-ins in ten minutes hit the brute-force rule;
    fails_when=4625s carry no account or address, a German "Administratoren" add is missed, a 7045 in both lists
    counts twice; no_claim=what Windows writes to its own log"""
    failures = [_sec(100 + i, 4625, i * 0.5, TargetUserName="admin", IpAddress="203.0.113.7", LogonType="3")
                for i in range(12)]
    security = [*failures,
                _sec(200, 4732, 7, MemberName="-", MemberSid="S-1-5-21-1-2-3-1001", TargetUserName="Administratoren",
                     TargetSid="S-1-5-32-544", SubjectUserName="eve"),
                _sec(201, 1102, 8, SubjectUserName="eve"),
                _sec(9001, 7045, 9, log="System", ServiceName="evilsvc", ImagePath="C:\\x.exe", AccountName="LocalSystem"),
                _sec(202, 4625, 9.5, TargetUserName="bob", IpAddress="::1")]
    recent = [{"source": "Service Control Manager", "event_id": 7045, "time": "2026-11-18T14:09:00Z",
               "message": "A service was installed in the system."}]
    await db.agents.insert_one({"id": "win2", "tenantId": "t1", "hostname": "PC-2", "meta": {"log_collection": {
        "security_events": security, "recent_events": recent}}})
    assert (await siem_pipeline.run_once(db))["events"] == 16
    assert (await siem_pipeline.run_once(db))["events"] == 0
    events = {e["key"]: e for e in await db.soc_log_events.find({"agentId": "win2"}, {"_id": 0}).to_list(50)}
    assert len(events) == 16 and "win2|System|9001" in events
    first = events["win2|Security|100"]
    assert (first["action"], first["user"], first["srcIp"], first["logonType"]) == ("login_failed", "admin", "203.0.113.7", "3")
    added = events["win2|Security|200"]
    assert (added["action"], added["group"], added["user"]) == ("admin_group_add", "Administrators", "S-1-5-21-1-2-3-1001")
    assert events["win2|Security|201"]["action"] == "log_cleared" and events["win2|Security|201"]["user"] == "eve"
    assert events["win2|System|9001"]["process"] == "evilsvc" and events["win2|Security|202"]["srcIp"] is None
    rules = {h["ruleId"] for h in await db.siem_hits.find({"agentId": "win2"}, {"_id": 0}).to_list(20)}
    assert {"lib-win-logon-failures", "lib-win-admin-group", "lib-win-log-cleared", "lib-win-service-installed"} <= rules


@pytest.mark.asyncio
async def test_rule_states_say_what_runs_and_what_waits(db):
    """protects=a rule runs once its log source sent events in 7 days; a descriptive library rule waits for the source
    migration 039 named; fails_when=the console calls a rule with no data running; no_claim=-"""
    await _logs(db, "t1", "ag1", [_line(0, "Invalid user a from 35.187.231.181 port 1")])
    await siem_pipeline.run_once(db)
    states = await siem_pipeline.rule_states(db, "t1", now=T0 + timedelta(hours=1))
    assert states["lib-linux-ssh-bruteforce"] == "running" and states["lib-win-log-cleared"] == "waiting for windows_security"
    assert states["old-1"] == "waiting for entra_id"
    assert await db.siem_rules.count_documents({"logic": {"$exists": True}}) == 10
    await migration.up(db)  # a second run changes nothing
    assert await db.siem_rules.count_documents({}) == 11


@pytest.mark.asyncio
async def test_opening_the_siem_rules_screen_keeps_the_executable_library(db):
    """protects=the SIEM Rules screen's seed refresh (siem_endpoints._upsert_seed_rules) removes only stale descriptive
    seeds, never a rule with logic; fails_when=a Super Admin opening the screen deletes migration 039's 10 rules;
    no_claim=the seed list's content"""
    import siem_endpoints
    await db.siem_rules.insert_one({"id": "stale", "tenant_id": "platform-admin", "created_by": "system", "name": "Gone"})
    await siem_endpoints._upsert_seed_rules(db, "platform-admin")
    assert await db.siem_rules.count_documents({"logic": {"$exists": True}}) == 10
    assert not await db.siem_rules.find_one({"id": "stale"})
