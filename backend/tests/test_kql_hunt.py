"""Advanced Hunting: a KQL subset that really runs over SIEM events, SOC alerts and agent logs.

Value: protects=a query filters, groups, counts, sorts and limits real rows the way KQL reads, inside the caller's
tenant and time range, and only on listed columns; fails_when=a where is ignored (the old keyword run returned
every row), a tenant sees another tenant's rows, a typed name or value reaches MongoDB as an operator or field path,
a count or dcount is wrong, or a bad query runs instead of answering with a reason; no_claim=the SOC Hunting tab
(test_soc_hunt.py), the Advanced Hunting screen (AdvancedHunting.test.tsx).
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import kql_engine
from kql_parser import KqlError, parse
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)


def _ev(minutes_ago, **kw):
    return {"tenantId": "t1", "at": NOW - timedelta(minutes=minutes_ago), "message": "", **kw}


@pytest.fixture
async def db(mongo_db):  # noqa: F811
    await mongo_db.soc_log_events.insert_many([
        _ev(5, source="windows_security", action="login_failed", outcome="failure", eventId=4625, user="ana",
            host="PC1", srcIp="10.0.0.9", logonType="2"),
        _ev(6, source="windows_security", action="login_failed", outcome="failure", eventId=4625, user="ana",
            host="PC1", srcIp="10.0.0.9", logonType="3"),
        _ev(7, source="windows_security", action="login_failed", outcome="failure", eventId=4625, user="bob",
            host="PC2", srcIp="10.0.0.9"),
        _ev(8, source="windows_security", action="group_member_added", outcome="success", eventId=4732,
            user="eve", group="Administrators", host="PC1"),
        _ev(9, source="linux_auth", action="login_failed", outcome="failure", user="root", srcIp="203.0.113.5",
            host="srv"),
        _ev(10, source="linux_auth", action="sudo_command", outcome="success", user="ops", command="apt update",
            host="srv"),
        _ev(11, source="network", action="ids_alert", outcome="detected", srcIp="198.51.100.7", destIp="10.0.0.4",
            destPort=445, signature="ET SCAN SMB", signatureId=2001, category="Attempted Recon"),
        _ev(60 * 30, source="windows_security", action="login_failed", outcome="failure", eventId=4625,
            user="old", host="PC9"),  # 30 hours ago: outside a 24 h range
        {"tenantId": "t2", "at": NOW - timedelta(minutes=5), "source": "windows_security", "action": "login_failed",
         "outcome": "failure", "eventId": 4625, "user": "other-tenant", "host": "X"},
    ])
    await mongo_db.security_alerts.insert_many([
        {"tenantId": "t1", "id": "a1", "title": "Ransomware behaviour: mass file encryption", "severity": "critical",
         "status": "open", "type": "ransomware", "created_at": (NOW - timedelta(hours=1)).isoformat()},
        {"tenantId": "t1", "id": "a2", "title": "Port scan", "severity": "low", "status": "open", "type": "scan",
         "created_at": (NOW - timedelta(hours=2, minutes=10)).isoformat()},
        {"tenantId": "t1", "id": "a3", "title": "Old merged", "severity": "high", "status": "merged", "type": "x",
         "created_at": (NOW - timedelta(hours=1)).isoformat()},
    ])
    return mongo_db


async def _run(db, q, scope="t1", **kw):
    return await kql_engine.run(db, scope, q, now=NOW, **kw)


async def test_where_filters_real_rows_newest_first_with_kql_columns(db):
    out = await _run(db, "SecurityEvent | where EventID == 4625 and Account == 'ana'")
    assert [r["LogonType"] for r in out["results"]] == ["2", "3"]
    assert out["results"][0]["Computer"] == "PC1" and out["results"][0]["TimeGenerated"].startswith("2026-11-19T11:55")
    assert out["table"] == "SecurityEvent" and "EventID" in out["columns"]


async def test_tenant_and_time_range_bound_every_query(db):
    out = await _run(db, "SecurityEvent | where EventID == 4625 | project Account")
    assert sorted(r["Account"] for r in out["results"]) == ["ana", "ana", "bob"]
    wide = await _run(db, "SecurityEvent | where EventID == 4625 | project Account", hours=48)
    assert "old" in [r["Account"] for r in wide["results"]]
    every = await _run(db, "SecurityEvent | where EventID == 4625 | project Account, TenantId", scope=None)
    assert "other-tenant" in [r["Account"] for r in every["results"]]
    with pytest.raises(KqlError, match="Unknown column TenantId"):
        await _run(db, "SecurityEvent | project TenantId")


async def test_summarize_counts_and_distinct_counts_by_group(db):
    out = await _run(db, "SigninLogs | where Outcome == 'failure' | summarize Fails=count(), Accounts=dcount(Account)"
                         " by SourceIP | where Fails > 1 | order by Fails desc")
    assert out["results"] == [{"SourceIP": "10.0.0.9", "Fails": 3, "Accounts": 2}]


async def test_operators_in_contains_startswith_not_and_isnotempty(db):
    q = ("SocEvents | where Source in ('linux_auth', 'network') and not(Action == 'sudo_command')"
         " and isnotempty(SourceIP) | project SourceIP | order by SourceIP asc")
    assert [r["SourceIP"] for r in (await _run(db, q))["results"]] == ["198.51.100.7", "203.0.113.5"]
    q = "IdsAlerts | where Signature startswith 'et scan' and DestinationPort in (445, 3389) | count"
    assert (await _run(db, q))["results"] == [{"Count": 1}]
    q = "Syslog | where CommandLine !contains 'reboot' and Action =~ 'SUDO_COMMAND' | project CommandLine"
    assert (await _run(db, q))["results"] == [{"CommandLine": "apt update"}]
    assert (await _run(db, "SecurityEvent | where Account == 'nobody' | count"))["results"] == [{"Count": 0}]


async def test_a_number_matches_a_text_column_stored_as_text(db):
    out = await _run(db, "SecurityEvent | where LogonType == 3 | project Account")
    assert out["results"] == [{"Account": "ana"}]


async def test_alerts_use_iso_times_hide_merged_and_bin_by_hour(db):
    out = await _run(db, "SecurityAlert | where Title contains 'ransom' | project Title, Severity")
    assert out["results"] == [{"Title": "Ransomware behaviour: mass file encryption", "Severity": "critical"}]
    out = await _run(db, "SecurityAlert | where TimeGenerated > ago(90m) | count")
    assert out["results"] == [{"Count": 1}]  # a3 is merged, so hidden
    out = await _run(db, "SecurityAlert | summarize n=count() by bin(TimeGenerated, 1h) | order by TimeGenerated asc")
    assert [r["n"] for r in out["results"]] == [1, 1]
    assert out["results"][0]["TimeGenerated"].startswith("2026-11-19T09:00")


async def test_take_top_and_the_row_cap(db):
    assert len((await _run(db, "SocEvents | take 2"))["results"]) == 2
    out = await _run(db, "SocEvents | summarize n=count() by Source | top 1 by n")
    assert out["results"] == [{"Source": "windows_security", "n": 4}]
    capped = await _run(db, "SocEvents", limit=3)
    assert len(capped["results"]) == 3 and capped["truncated"] is True


@pytest.mark.parametrize("query,message", [
    ("", "starts with a table"),
    ("Users | take 1", "Unknown table Users"),
    ("SecurityEvent | where password == 'x'", "Unknown column password"),
    ("SecurityEvent | where EventID contains '46'", "is not text"),
    ("SecurityEvent | where EventID == 'abc'", "whole number"),
    ("SecurityEvent | where Account matches regex '('", "pattern is not valid"),
    ("SecurityEvent | extend x = 1", "Unsupported operator 'extend'"),
    ("SecurityEvent | where Account == 'a' Account", "separate operators with |"),
    ("SecurityEvent | summarize x=count() by Account | project $where", "Unexpected character"),
    ("SecurityEvent | project a.b", "Unexpected character"),
    ("SecurityEvent | summarize evil=count() by Account | where evil > 'x'", "compares numbers or times"),
])
async def test_bad_queries_answer_with_a_reason_and_never_run(db, query, message):
    with pytest.raises(KqlError, match=message):
        await _run(db, query)


def test_typed_values_stay_data_and_names_stay_listed_fields():
    _, stages = parse("SocEvents | where Account == '$ne' and Message contains '.*' | project Who = Account")
    _, _, pipeline = kql_engine.build("SocEvents", stages, "t1", NOW, 100)
    assert pipeline[0]["$match"]["tenantId"] == "t1"
    where = pipeline[1]["$match"]["$and"]
    assert where[0] == {"user": "$ne"}
    assert where[1] == {"message": {"$regex": r"\.\*", "$options": "i"}}
    assert pipeline[2] == {"$project": {"_id": 0, "Who": "$user"}}
