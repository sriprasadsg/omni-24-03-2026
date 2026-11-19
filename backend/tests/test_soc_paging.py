"""Paging for critical alerts (soc_paging, Wave 3). protects/fails_when/no_claim per test; PagerDuty, Opsgenie,
Teams and Slack are mocked at the HTTP layer, MongoDB is real.
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
import soc_alerts
import soc_paging as sp
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

T = "t-paging"
KEY = "R0UT1NGkeyR0UT1NGkeyR0UT1NGkey12"
GENIE = "01234567-89ab-cdef-0123-456789abcdef"
NOW = datetime(2026, 11, 18, 10, 0, tzinfo=timezone.utc)  # a Wednesday, 10:00 UTC
REAL = httpx.AsyncClient


@pytest_asyncio.fixture
async def world(mongo_db, monkeypatch):  # noqa: F811
    calls, answer = [], {"status": 202}

    def handler(request: httpx.Request):
        calls.append({"url": str(request.url), "headers": dict(request.headers), "body": json.loads(request.content or b"{}")})
        return httpx.Response(answer["status"], json={"status": "success"})
    monkeypatch.setattr(sp, "_client", lambda **kw: REAL(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(sp, "_now", lambda: NOW)
    monkeypatch.setattr(database.mongodb, "db", mongo_db)
    monkeypatch.setattr(database, "get_database", lambda: mongo_db)
    monkeypatch.setenv("SOC_AUTO_TRIAGE", "0")

    async def chat_ok(url):
        return None
    import webhook_url_validator
    monkeypatch.setattr(webhook_url_validator, "validate_webhook_url", chat_ok)
    return mongo_db, calls, answer


async def _setup(db, **over):
    body = {"provider": "pagerduty", "secret": KEY, **over}
    out = await sp.save_config(db, T, body, "admin@t")
    await db.soc_paging.update_one({"tenantId": T}, {"$set": {"enabledAt": (NOW - timedelta(hours=3)).isoformat()}})
    return out


async def _alert(db, severity="critical", minutes_ago=0, **kw):
    created = (NOW - timedelta(minutes=minutes_ago)).isoformat()
    doc = {"id": kw.pop("id", f"a-{severity}-{minutes_ago}"), "tenantId": T, "type": "runtime_security", "severity": severity,
           "status": "open", "title": "mimikatz.exe started", "hostname": "EILT0197", "created_at": created, **kw}
    await db.security_alerts.insert_one(dict(doc))
    return doc


@pytest.mark.asyncio
async def test_settings_keep_the_key_secret_and_check_what_is_given(world):
    """protects=the key is stored encrypted and never read back, malformed keys, severities, hours and a private
    webhook address are refused, and switching provider needs its own key; fails_when=a routing key or webhook URL
    is readable from the database or the API answer, or paging to 10.0.0.5 is accepted; no_claim=real provider keys"""
    db, _, _ = world
    out = await _setup(db)
    assert out["configured"] and out["provider"] == "pagerduty" and "secret" not in out
    stored = await db.soc_paging.find_one({"tenantId": T})
    assert KEY not in json.dumps(stored, default=str) and stored["secret"]
    bad = [{"provider": "pagerduty", "secret": "short"}, {"provider": "opsgenie", "secret": "not-a-key"},
           {"provider": "email", "secret": KEY}, {"provider": "pagerduty", "secret": KEY, "minSeverity": "medium"},
           {"provider": "pagerduty", "onCall": {"timezone": "Mars/Base", "days": [0], "start": "08:00", "end": "18:00"}},
           {"provider": "pagerduty", "onCall": {"timezone": "UTC", "days": [7], "start": "08:00", "end": "18:00"}},
           {"provider": "pagerduty", "onCall": {"timezone": "UTC", "days": [0], "start": "08:00", "end": "08:00"}},
           {"provider": "slack"}]
    for body in bad:
        with pytest.raises(sp.PagingError):
            await sp.save_config(db, T, body, "admin@t")
    import webhook_url_validator
    from importlib import reload
    reload(webhook_url_validator)  # the real SSRF guard
    with pytest.raises(sp.PagingError):
        await sp.save_config(db, T, {"provider": "teams", "secret": "https://10.0.0.5/hook"}, "admin@t")
    kept = await sp.save_config(db, T, {"provider": "pagerduty", "minSeverity": "high"}, "admin@t")  # same provider: key kept
    assert kept["minSeverity"] == "high" and (await db.soc_paging.find_one({"tenantId": T}))["secret"] == stored["secret"]


def test_on_call_hours_follow_the_organizations_clock():
    """protects=a weekday window in the organization's time zone, and a night window that runs past midnight
    belongs to the day it starts; fails_when=UTC is used instead of the zone or a Friday-night shift stops at
    midnight; no_claim=daylight-saving edge minutes"""
    office = sp._on_call_hours({"timezone": "America/New_York", "days": [0, 1, 2, 3, 4], "start": "09:00", "end": "17:00"})
    assert sp.on_call(office, NOW.replace(hour=14)) and not sp.on_call(office, NOW)  # 09:00 and 05:00 in New York
    night = sp._on_call_hours({"timezone": "UTC", "days": [4], "start": "22:00", "end": "06:00"})  # Friday night
    assert sp.on_call(night, datetime(2026, 11, 21, 3, tzinfo=timezone.utc))  # Saturday 03:00
    assert not sp.on_call(night, datetime(2026, 11, 20, 3, tzinfo=timezone.utc))  # Friday 03:00 (Thursday night)
    assert sp.on_call(sp._on_call_hours(None), NOW)


@pytest.mark.asyncio
async def test_a_new_critical_alert_pages_once_and_closing_it_resolves_the_page(world):
    """protects=record_alert pages a new critical alert through PagerDuty with one dedup key, a second attempt does
    not page again, and closing the alert resolves the incident on the next sweep; fails_when=a repeat or the sweep
    opens a second incident, or a closed alert's incident stays open; no_claim=PagerDuty's own routing"""
    db, calls, _ = world
    await _setup(db)
    alert = await soc_alerts.record_alert(db, {"tenantId": T, "type": "runtime_security", "severity": "critical",
                                               "title": "mimikatz.exe started", "created_at": NOW.isoformat()})
    await asyncio.gather(*list(sp._tasks))
    assert len(calls) == 1 and calls[0]["url"] == sp.PAGERDUTY_EVENTS
    body = calls[0]["body"]
    assert (body["routing_key"], body["event_action"], body["dedup_key"]) == (KEY, "trigger", f"omni-{alert['id']}")
    assert body["payload"]["severity"] == "critical" and "mimikatz" in body["payload"]["summary"]
    assert (await sp.page(db, alert["id"], T, "new"))["why"] == "this alert has already paged"
    await sp.sweep(db, NOW)
    assert len(calls) == 1  # still active: nothing to resolve, nothing to resend
    await db.security_alerts.update_one({"id": alert["id"]}, {"$set": {"status": "closed", "resolution": "resolved"}})
    assert (await sp.sweep(db, NOW))["resolved"] == 1
    assert calls[1]["body"] == {"routing_key": KEY, "event_action": "resolve", "dedup_key": f"omni-{alert['id']}"}
    assert (await db.soc_pages.find_one({"alertId": alert["id"]}))["status"] == "resolved"
    await sp.sweep(db, NOW)
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_what_does_not_page(world):
    """protects=below the paging severity, older than paging, outside on-call hours, switched off, another
    organization's alert and a closed alert send nothing; fails_when=any of them reaches PagerDuty;
    no_claim=the console's own notifications"""
    db, calls, _ = world
    await _setup(db, onCall={"timezone": "UTC", "days": [2], "start": "09:00", "end": "17:00"})
    for a in (await _alert(db, "high", id="high"), await _alert(db, "critical", minutes_ago=600, id="old"),
              await _alert(db, "critical", id="other", tenantId="t-other"), await _alert(db, "critical", id="shut", status="closed")):
        assert not (await sp.page(db, a["id"], T, "new"))["paged"]
    await db.soc_paging.update_one({"tenantId": T}, {"$set": {"onCall.start": "11:00", "onCall.end": "17:00"}})
    assert (await sp.page(db, (await _alert(db, id="early"))["id"], T, "new"))["why"] == "outside on-call hours"
    await sp.save_config(db, T, {"provider": "pagerduty", "enabled": False}, "admin@t")
    assert (await sp.page(db, (await _alert(db, id="off"))["id"], T, "new"))["why"] == "paging is off"
    assert calls == []


@pytest.mark.asyncio
async def test_an_alert_not_acknowledged_in_time_pages_once(world):
    """protects=the sweep pages an open high alert past its 60-minute acknowledge target, and not an acknowledged
    one, a younger one, or one already paged; fails_when=breaches never page or page every minute;
    no_claim=close-target breaches (they do not page)"""
    db, calls, _ = world
    await _setup(db)
    late = await _alert(db, "high", minutes_ago=61, id="late")
    await _alert(db, "high", minutes_ago=30, id="young")
    await _alert(db, "high", minutes_ago=90, id="seen", status="acknowledged", acknowledgedAt=NOW.isoformat())
    assert (await sp.sweep(db, NOW))["breaches"] == 1
    assert [c["body"]["dedup_key"] for c in calls] == [f"omni-{late['id']}"]
    assert "Not acknowledged in time" in calls[0]["body"]["payload"]["summary"]
    assert (await sp.sweep(db, NOW))["breaches"] == 0 and len(calls) == 1
    await sp.save_config(db, T, {"provider": "pagerduty", "pageBreaches": False}, "admin@t")
    await _alert(db, "critical", minutes_ago=20, id="late2")
    assert (await sp.sweep(db, NOW))["breaches"] == 0


@pytest.mark.asyncio
async def test_opsgenie_teams_and_slack_get_their_own_formats(world):
    """protects=Opsgenie gets a P1 alert with the GenieKey header at the EU address and is closed by alias; Teams gets
    an Adaptive Card; Slack gets text, then a resolved line; fails_when=a provider is sent another's format or the
    close goes to the wrong address; no_claim=how each app displays it"""
    db, calls, _ = world
    await _setup(db, provider="opsgenie", secret=GENIE, region="eu")
    a = await _alert(db, id="og")
    assert (await sp.page(db, a["id"], T, "new"))["paged"]
    assert calls[0]["url"] == sp.OPSGENIE["eu"] and calls[0]["headers"]["authorization"] == f"GenieKey {GENIE}"
    assert calls[0]["body"]["priority"] == "P1" and calls[0]["body"]["alias"] == "omni-og"
    await db.security_alerts.update_one({"id": "og"}, {"$set": {"status": "closed"}})
    await sp.sweep(db, NOW)
    assert calls[1]["url"] == f"{sp.OPSGENIE['eu']}/omni-og/close?identifierType=alias"
    for provider, url in (("teams", "https://contoso.webhook.office.com/x"), ("slack", "https://hooks.slack.com/services/x")):
        await sp.save_config(db, T, {"provider": provider, "secret": url}, "admin@t")
        assert (await sp.page(db, (await _alert(db, id=provider))["id"], T, "new"))["paged"] and calls[-1]["url"] == url
    teams, slack = calls[-2]["body"], calls[-1]["body"]
    assert teams["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"
    assert slack["text"].startswith("*[CRITICAL] mimikatz.exe started on EILT0197*")
    await db.security_alerts.update_one({"id": "slack"}, {"$set": {"status": "closed", "resolution": "false_positive"}})
    await sp.sweep(db, NOW)
    assert calls[-1]["body"]["text"].startswith("*Resolved: mimikatz.exe started*") and "false_positive" in calls[-1]["body"]["text"]
    assert (await db.soc_pages.find_one({"alertId": "teams"}))["status"] == "left_open"  # paging moved to Slack


@pytest.mark.asyncio
async def test_a_refused_page_is_retried_then_left_and_never_shows_the_key(world):
    """protects=a page the provider refuses is recorded as failed with the HTTP status, retried by the sweep up to
    three sends, and its error never contains the key; fails_when=a failure is reported as paged, retried forever,
    or the routing key leaks into the stored error; no_claim=PagerDuty's error text (not kept)"""
    db, calls, answer = world
    await _setup(db)
    answer["status"] = 401
    out = await sp.page(db, (await _alert(db, id="refused"))["id"], T, "new")
    assert not out["paged"] and out["error"] == "PagerDuty answered HTTP 401: the key was refused"
    for _ in range(4):
        await sp.sweep(db, NOW)
    assert len(calls) == sp.MAX_ATTEMPTS
    stored = await db.soc_pages.find_one({"alertId": "refused"}, {"_id": 0})
    cfg = await db.soc_paging.find_one({"tenantId": T}, {"_id": 0, "secret": 0})
    assert KEY not in json.dumps([stored, cfg], default=str) and cfg["lastResult"]["ok"] is False


@pytest.mark.asyncio
async def test_at_most_twenty_pages_an_hour(world):
    """protects=an alert storm pages at most MAX_PER_HOUR times an hour per organization and counts the rest;
    fails_when=a storm sends a page per alert; no_claim=a digest of the suppressed ones"""
    db, calls, _ = world
    await _setup(db)
    for i in range(sp.MAX_PER_HOUR + 2):
        await sp.page(db, (await _alert(db, id=f"storm-{i}"))["id"], T, "new")
    assert len(calls) == sp.MAX_PER_HOUR
    assert (await db.soc_paging.find_one({"tenantId": T}))["suppressed"] == 2


@pytest.mark.asyncio
async def test_the_test_page_raises_a_console_alert_that_resolves_when_closed(world):
    """protects=Send test page raises a critical "Paging test" alert and pages it even outside on-call hours and
    switched off; closing that alert resolves the page; fails_when=the test needs a real incident to prove paging
    or leaves its PagerDuty incident open; no_claim=the analyst closing it"""
    db, calls, _ = world
    with pytest.raises(sp.PagingError):
        await sp.send_test(db, T, "admin@t")
    await _setup(db, enabled=False, onCall={"timezone": "UTC", "days": [6], "start": "01:00", "end": "02:00"})
    out = await sp.send_test(db, T, "admin@t")
    assert out["paged"] and calls[0]["body"]["dedup_key"] == f"omni-{out['alertId']}"
    alert = await db.security_alerts.find_one({"id": out["alertId"]})
    assert (alert["type"], alert["severity"], alert["status"]) == ("paging_test", "critical", "open")
    await db.security_alerts.update_one({"id": out["alertId"]}, {"$set": {"status": "closed"}})
    await sp.sweep(db, NOW)
    assert calls[1]["body"]["event_action"] == "resolve"


@pytest.mark.asyncio
async def test_ntfy_pushes_to_the_topic_with_its_token_and_resolves(world):
    """protects=ntfy (open source) gets a JSON publish at the server root naming the topic, priority 5 for critical and
    the access token as a Bearer header; the token is encrypted and never read back; a URL that is not one topic or a
    malformed token is refused; closing the alert posts a resolved push; fails_when=the token is readable, the push
    goes to the topic URL as plain text, or a page without its topic; no_claim=how the ntfy app shows it"""
    db, calls, _ = world
    token = "tk_" + "a1B2c3D4e5" * 2 + "f6G7h8J9k"
    for bad in ({"secret": "https://ntfy.sh/"}, {"secret": "https://ntfy.sh/a/b"}, {"secret": "https://ntfy.sh/x", "token": "tk_short"}):
        with pytest.raises(sp.PagingError):
            await sp.save_config(db, T, {"provider": "ntfy", **bad}, "admin@t")
    out = await _setup(db, provider="ntfy", secret="https://ntfy.sh/omni-oncall-7f3k", token=token)
    assert out["provider"] == "ntfy" and out["webhookHost"] == "ntfy.sh" and out["hasToken"] is True and "token" not in out
    assert token not in json.dumps(await db.soc_paging.find_one({"tenantId": T}), default=str)
    assert (await sp.page(db, (await _alert(db, id="nt"))["id"], T, "new"))["paged"]
    push = calls[-1]
    assert push["url"] == "https://ntfy.sh/" and push["headers"]["authorization"] == f"Bearer {token}"
    assert push["body"]["topic"] == "omni-oncall-7f3k" and push["body"]["priority"] == 5
    assert push["body"]["title"] == "[CRITICAL] mimikatz.exe started on EILT0197" and "Alert nt" in push["body"]["message"]
    await db.security_alerts.update_one({"id": "nt"}, {"$set": {"status": "closed"}})
    await sp.sweep(db, NOW)
    assert calls[-1]["body"]["title"] == "Resolved: mimikatz.exe started" and calls[-1]["body"]["priority"] == 3
    out = await sp.save_config(db, T, {"provider": "ntfy", "secret": "https://ntfy.sh/omni-oncall-7f3k"}, "admin@t")
    assert out["hasToken"] is False  # a new URL without a token clears the old token
