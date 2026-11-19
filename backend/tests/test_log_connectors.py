"""Cloud log connectors (log_connectors, log_connector_sources, migration 044; Wave 3). protects/fails_when/no_claim per
test. Entra, Graph, the Office 365 Management API and Google's Reports API are mocked at the HTTP layer; CloudTrail and
Google's token at their SDK seam; MongoDB is real.
"""
import importlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

import httpx
import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import log_connector_sources as src
import log_connectors as lc
import siem_pipeline
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

T = "t-logs"
TID, CID, SECRET = "11111111-2222-3333-4444-555555555555", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "cl13nt~s3cr3t"
AWS_ID, AWS_SECRET = "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
SA = json.dumps({"type": "service_account", "client_email": "reader@proj.iam.gserviceaccount.com", "private_key": "-----BEGIN PRIVATE KEY-----x"})
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
REAL = httpx.AsyncClient
migration = importlib.import_module("migrations.044_log_connector_rules")


def _signin(i, user="anna@contoso.example", ok=False, minute=0):
    return {"id": f"s{i}", "createdDateTime": f"2026-11-19T11:{50 + minute:02d}:00Z", "userPrincipalName": user, "ipAddress": "203.0.113.9",
            "appDisplayName": "Office 365", "status": {"errorCode": 0 if ok else 50126, "failureReason": None if ok else "Invalid password"},
            "location": {"countryOrRegion": "GB"}, "riskLevelDuringSignIn": "none", "clientAppUsed": "Browser"}


@pytest_asyncio.fixture
async def world(mongo_db, monkeypatch):  # noqa: F811
    calls, feed = [], {"signins": [[_signin(i, minute=i) for i in range(3)], [_signin(i, minute=i) for i in range(3, 6)]],
                       "audits": [{"id": "d1", "activityDateTime": "2026-11-19T11:58:00Z", "activityDisplayName": "Add member to role",
                                   "result": "success", "initiatedBy": {"user": {"userPrincipalName": "it@contoso.example", "ipAddress": "198.51.100.4"}},
                                   "targetResources": [{"userPrincipalName": "ben@contoso.example"}]}],
                       "graph_status": 200, "m365": [], "google": {}}

    def handler(request: httpx.Request):
        url = unquote(str(request.url))
        calls.append(url)
        if url.startswith("https://login.microsoftonline.com/"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        if url.startswith(src.GRAPH):
            if feed["graph_status"] != 200:
                return httpx.Response(feed["graph_status"], json={"error": {"message": SECRET}})
            if "signIns" in url:
                second = "skiptoken" in url
                body = {"value": feed["signins"][1 if second else 0]}
                if not second:
                    body["@odata.nextLink"] = f"{src.GRAPH}/auditLogs/signIns?$skiptoken=x"
                return httpx.Response(200, json=body)
            return httpx.Response(200, json={"value": feed["audits"]})
        if url.startswith(src.MANAGE):
            if "/subscriptions/start" in url:
                return httpx.Response(400, json={"error": {"code": "AF20024"}})
            if "/subscriptions/content" in url:
                blobs = [{"contentUri": f"https://blob.example/{len(calls)}", "contentCreated": "2026-11-19T11:55:00Z"}] if "Exchange" in url else []
                return httpx.Response(200, json=blobs)
        if url.startswith("https://blob.example/"):
            return httpx.Response(200, json=feed["m365"])
        if url.startswith(src.GOOGLE_REPORTS):
            app = "login" if "/login" in url else "admin"
            pages = feed["google"].get(app, [[]])
            page = 1 if "pageToken" in url else 0
            body = {"items": pages[page]}
            if page + 1 < len(pages):
                body["nextPageToken"] = "p2"
            return httpx.Response(200, json=body)
        return httpx.Response(404)
    monkeypatch.setattr(src, "_client", lambda **kw: REAL(transport=httpx.MockTransport(handler), **kw))
    await siem_pipeline.ensure_indexes(mongo_db)
    await migration.up(mongo_db)
    return mongo_db, calls, feed


async def _row(db, provider):
    return await db.log_connectors.find_one({"tenantId": T, "provider": provider}, {"_id": 0})


@pytest.mark.asyncio
async def test_settings_keep_the_secret_encrypted_and_check_what_is_given(world):
    """protects=each provider's ids are checked, the secret is stored encrypted and never listed, a first save needs
    the secret, a later one keeps it, and every provider is listed connected or not; fails_when=a client secret, AWS
    secret or service-account key is readable from the database or the API, or a malformed id is stored;
    no_claim=that the credentials work (a pull proves that)"""
    db, _, _ = world
    out = await lc.save_config(db, T, "entra", {"azureTenantId": TID, "clientId": CID, "secret": SECRET}, "admin@t")
    assert out["connected"] and out["azureTenantId"] == TID and "secret" not in out
    await lc.save_config(db, T, "aws", {"accessKeyId": AWS_ID, "secret": AWS_SECRET, "regions": ["eu-west-1"]}, "admin@t")
    g = await lc.save_config(db, T, "google", {"adminEmail": "Admin@Contoso.example", "secret": SA}, "admin@t")
    assert g["serviceAccount"] == "reader@proj.iam.gserviceaccount.com" and g["adminEmail"] == "admin@contoso.example"
    stored = await db.log_connectors.find({"tenantId": T}).to_list(10)
    assert not any(s in json.dumps(stored, default=str) for s in (SECRET, AWS_SECRET, "BEGIN PRIVATE KEY"))
    listed = await lc.list_config(db, T)
    assert set(listed) == {"entra", "m365", "aws", "google"} and not listed["m365"]["connected"]
    assert "secret" not in json.dumps(listed) and "cursor" not in listed["entra"]
    for provider, body in (("entra", {"azureTenantId": "contoso", "clientId": CID, "secret": "x"}),
                           ("m365", {"azureTenantId": TID, "clientId": CID}),
                           ("aws", {"accessKeyId": "AKIA123", "secret": AWS_SECRET}),
                           ("aws", {"accessKeyId": AWS_ID, "secret": "short"}),
                           ("aws", {"accessKeyId": AWS_ID, "regions": ["mars-1"]}),
                           ("google", {"adminEmail": "admin@contoso.example", "secret": "{\"type\": \"user\"}"}),
                           ("splunk", {"secret": "x"})):
        with pytest.raises(lc.ConnectorError):
            await lc.save_config(db, T, provider, body, "admin@t")
    before = (await _row(db, "entra"))["secret"]
    await lc.save_config(db, T, "entra", {"azureTenantId": TID, "clientId": CID, "enabled": False}, "admin@t")
    after = await _row(db, "entra")
    assert after["secret"] == before and after["enabled"] is False


@pytest.mark.asyncio
async def test_entra_sign_ins_and_audits_become_siem_events_and_hit_a_rule(world):
    """protects=a pull reads every page of sign-ins and the directory audits, stores them as entra_id events, moves
    each stream's cursor to its newest record, runs the library rules (6 failed sign-ins for one account = one hit,
    recorded, not alerting in its first 7 days) and a second pull stores nothing twice; fails_when=the second page is
    dropped, a repeat pull duplicates events, or the cursor stays put; no_claim=Entra's own delay before it lists a sign-in"""
    db, calls, _ = world
    await lc.save_config(db, T, "entra", {"azureTenantId": TID, "clientId": CID, "secret": SECRET}, "admin@t")
    out = await lc.run(db, await _row(db, "entra"), NOW)
    assert out == {"ok": True, "read": 7, "new": 7, "hits": 2}  # brute force + admin role
    assert any("$filter=createdDateTime ge 2026-11-18T12:00:00Z" in c for c in calls)  # first look: 24 hours
    failed = await db.soc_log_events.count_documents({"tenantId": T, "source": "entra_id", "action": "login_failed", "user": "anna@contoso.example"})
    role = await db.soc_log_events.find_one({"tenantId": T, "action": "admin_role_add"}, {"_id": 0})
    assert failed == 6 and role["user"] == "it@contoso.example" and role["target"] == "ben@contoso.example"
    hits = {h["ruleId"]: h for h in await db.siem_hits.find({"tenantId": T}).to_list(10)}
    assert set(hits) == {"lib-entra-signin-failures", "lib-entra-admin-role"} and not hits["lib-entra-signin-failures"]["alerted"]
    row = await _row(db, "entra")
    assert row["cursor"] == {"signIns": "2026-11-19T11:55:00Z", "directoryAudits": "2026-11-19T11:58:00Z"}
    assert (row["lastCount"], row["totalEvents"], row["lastError"], row["lastSuccessAt"]) == (7, 7, None, NOW.isoformat())
    assert (await lc.run(db, row, NOW + timedelta(minutes=5)))["new"] == 0
    assert any("$filter=createdDateTime ge 2026-11-19T11:55:00Z" in c for c in calls)


@pytest.mark.asyncio
async def test_a_refused_pull_is_recorded_and_retried_from_the_same_place(world):
    """protects=a provider refusal sets lastError with the HTTP status and why, keeps the cursor and the last success,
    and never puts the secret in the error; fails_when=a failed pull moves the cursor (losing logs) or reports
    success; no_claim=Graph's own error text (not kept)"""
    db, _, feed = world
    await lc.save_config(db, T, "entra", {"azureTenantId": TID, "clientId": CID, "secret": SECRET}, "admin@t")
    await lc.run(db, await _row(db, "entra"), NOW)
    feed["graph_status"] = 403
    out = await lc.run(db, await _row(db, "entra"), NOW + timedelta(minutes=5))
    assert out == {"ok": False, "error": "Microsoft Graph answered HTTP 403: the app lacks a permission or licence"}
    row = await _row(db, "entra")
    assert row["cursor"]["signIns"] == "2026-11-19T11:55:00Z" and row["lastSuccessAt"] == NOW.isoformat()
    assert row["lastError"] == out["error"] and SECRET not in json.dumps(row, default=str).replace(row["secret"], "")


@pytest.mark.asyncio
async def test_microsoft_365_audit_records_with_forwarding_rules(world):
    """protects=the Management API subscriptions are started once (already-on is fine), content is listed for at most
    the last 24 hours, each blob's records become m365 events, and a forwarding inbox rule is told apart and hits its
    rule; fails_when=forwarding looks like any other inbox rule, or a week-old cursor asks the API for more than a day;
    no_claim=the API's own delay (up to hours) before content appears"""
    db, calls, feed = world
    feed["m365"] = [{"Id": "m1", "CreationTime": "2026-11-19T11:54:00", "Operation": "New-InboxRule", "UserId": "anna@contoso.example",
                     "ClientIP": "203.0.113.9", "Workload": "Exchange", "Parameters": [{"Name": "ForwardTo", "Value": "x@evil.example"}]},
                    {"Id": "m2", "CreationTime": "2026-11-19T11:54:30", "Operation": "UserLoginFailed", "UserId": "ben@contoso.example",
                     "ResultStatus": "Failed", "Workload": "AzureActiveDirectory"}]
    await lc.save_config(db, T, "m365", {"azureTenantId": TID, "clientId": CID, "secret": SECRET}, "admin@t")
    await db.log_connectors.update_one({"tenantId": T, "provider": "m365"}, {"$set": {"cursor": {"Audit.Exchange": "2026-11-10T00:00:00Z"}}})
    out = await lc.run(db, await _row(db, "m365"), NOW)
    assert out["ok"] and out["new"] == 2 and out["hits"] == 1
    assert sum("/subscriptions/start" in c for c in calls) == 4
    assert any("contentType=Audit.Exchange&startTime=2026-11-18T12:05:00Z" in c for c in calls)
    events = {e["key"]: e async for e in db.soc_log_events.find({"tenantId": T, "source": "m365"}, {"_id": 0})}
    assert events["m365|m1"]["action"] == "mail_forward_rule" and events["m365|m2"]["action"] == "login_failed"
    assert events["m365|m1"]["at"].replace(tzinfo=timezone.utc) == datetime(2026, 11, 19, 11, 54, tzinfo=timezone.utc)
    row = await _row(db, "m365")
    assert row["cursor"]["Audit.Exchange"] == "2026-11-19T11:55:00Z" and row["cursor"]["Audit.General:on"] == "yes"
    calls.clear()
    await lc.run(db, row, NOW)
    assert not any("/subscriptions/start" in c for c in calls)


@pytest.mark.asyncio
async def test_aws_cloudtrail_events_per_region(world, monkeypatch):
    """protects=each region is read from its own cursor, root use, failed console sign-ins and stopped trails get
    their actions and the root rule hits; fails_when=a region's cursor moves past events it never read or root use
    is missed; no_claim=data events (LookupEvents lists management events only)"""
    db, _, _ = world
    seen = []

    def lookup(cfg, region, start, end):
        seen.append((region, start))
        t = datetime(2026, 11, 19, 11, 40, tzinfo=timezone.utc)
        return [] if region == "us-east-1" else [
            {"EventId": "e1", "EventName": "ConsoleLogin", "EventTime": t, "Username": "root", "CloudTrailEvent": json.dumps({
                "userIdentity": {"type": "Root"}, "sourceIPAddress": "203.0.113.9", "responseElements": {"ConsoleLogin": "Success"}})},
            {"EventId": "e2", "EventName": "ConsoleLogin", "EventTime": t, "Username": "dev", "CloudTrailEvent": json.dumps({
                "userIdentity": {"type": "IAMUser"}, "responseElements": {"ConsoleLogin": "Failure"}})},
            {"EventId": "e3", "EventName": "StopLogging", "EventTime": t + timedelta(minutes=5), "Username": "dev",
             "CloudTrailEvent": json.dumps({"userIdentity": {"type": "IAMUser"}, "eventSource": "cloudtrail.amazonaws.com"})}]
    monkeypatch.setattr(src, "_aws_lookup", lookup)
    await lc.save_config(db, T, "aws", {"accessKeyId": AWS_ID, "secret": AWS_SECRET, "regions": ["us-east-1", "eu-west-1"]}, "admin@t")
    await db.log_connectors.update_one({"tenantId": T, "provider": "aws"}, {"$set": {"cursor": {"us-east-1": "2026-11-19T10:00:00Z"}}})
    out = await lc.run(db, await _row(db, "aws"), NOW)
    assert out["new"] == 3 and out["hits"] == 2  # root use + trail stopped
    assert seen == [("eu-west-1", NOW - timedelta(hours=24)), ("us-east-1", datetime(2026, 11, 19, 10, tzinfo=timezone.utc))]
    events = {e["key"]: e async for e in db.soc_log_events.find({"tenantId": T}, {"_id": 0})}
    assert events["aws_cloudtrail|e1"]["rootUser"] is True and events["aws_cloudtrail|e2"]["action"] == "login_failed"
    assert events["aws_cloudtrail|e3"]["action"] == "log_disabled" and events["aws_cloudtrail|e3"]["host"] == "eu-west-1"
    cursor = (await _row(db, "aws"))["cursor"]
    assert cursor == {"eu-west-1": "2026-11-19T11:45:00Z", "us-east-1": "2026-11-19T10:00:00Z"}


@pytest.mark.asyncio
async def test_google_workspace_login_and_admin_activity(world, monkeypatch):
    """protects=both report applications are read across pages, a failed login and a role grant get their actions,
    and each application's cursor moves to its newest activity; fails_when=the second page or the admin report is
    dropped; no_claim=Google's report delay"""
    db, calls, feed = world
    monkeypatch.setattr(src, "_google_token", lambda cfg: "gtok")

    def act(q, t, name, email="anna@contoso.example"):
        return {"id": {"uniqueQualifier": q, "time": t}, "actor": {"email": email}, "ipAddress": "203.0.113.9", "events": [{"name": name}]}
    feed["google"] = {"login": [[act("1", "2026-11-19T11:30:00.000Z", "login_failure")], [act("2", "2026-11-19T11:31:00.000Z", "login_success")]],
                      "admin": [[act("3", "2026-11-19T11:20:00.000Z", "ASSIGN_ROLE", "it@contoso.example")]]}
    await lc.save_config(db, T, "google", {"adminEmail": "admin@contoso.example", "secret": SA}, "admin@t")
    out = await lc.run(db, await _row(db, "google"), NOW)
    assert out["new"] == 3 and out["hits"] == 1
    actions = sorted([e["action"] async for e in db.soc_log_events.find({"tenantId": T, "source": "google_workspace"})])
    assert actions == ["admin_role_add", "login_failed", "login_success"]
    assert (await _row(db, "google"))["cursor"] == {"login": "2026-11-19T11:31:00.000Z", "admin": "2026-11-19T11:20:00.000Z"}


@pytest.mark.asyncio
async def test_migration_044_adds_the_library_rules_once_and_keeps_tuning(world):
    """protects=12 cloud rules exist in record mode for 7 days, and a second run neither duplicates nor resets a rule
    an analyst changed; fails_when=re-running the migration re-enables or re-thresholds a tuned rule;
    no_claim=the rules' quality (they record for a week first)"""
    db, _, _ = world
    rules = await db.siem_rules.find({"id": {"$regex": "^lib-(entra|m365|aws|gws)-"}}, {"_id": 0}).to_list(50)
    assert len(rules) == 12 and all(r["mode"] == "record" and r["tenant_id"] == "platform-admin" for r in rules)
    await db.siem_rules.update_one({"id": "lib-aws-root-use"}, {"$set": {"enabled": False}})
    await migration.up(db)
    assert await db.siem_rules.count_documents({"id": {"$regex": "^lib-(entra|m365|aws|gws)-"}}) == 12
    assert (await db.siem_rules.find_one({"id": "lib-aws-root-use"}))["enabled"] is False
