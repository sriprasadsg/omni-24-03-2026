"""Watchdog on-call delivery (Phase 82, plan 82-05, HEAL-05 and HEAL-02).

Every external effect is faked: ``FakeHttp`` answers the backend, PagerDuty, a webhook and the heartbeat
service; the fake host and clock come from the restart world. Nothing here opens a socket (the real urllib
client is exercised against a loopback server in test_watchdog_contract.py).
"""
import json
import logging

from tests._watchdog_oncall_world import (ENQUEUE, HEARTBEAT_PATH, HEARTBEAT_URL, HOST, RESULTS, ROUTING_KEY, SECRETS, SYNC,
                                          WEBHOOK_PATH, WEBHOOK_URL, give_up, orig)  # noqa: F401  (orig is a fixture)
from tests._watchdog_support import FakeClock, FakeHttp

from omni_watchdog import config as config_mod, incidents, paging  # noqa: E402

NOW = 1_800_000_000.0
NO_CHANNEL = "No on-call channel is set up on the server."


# --- Task 1: the tracer - a gave-up service becomes exactly one page and, when healthy, one resolve ---

def test_a_gave_up_service_sends_exactly_one_trigger_over_many_runs(orig):
    orig.channel("pagerduty")
    next_run = give_up(orig)
    assert len(orig.triggers()) == 1                                # sent in the very run that gave up
    for step in range(5):                                           # five more runs while it is still down
        orig.at(next_run + 60 * step)
    assert len(orig.triggers()) == 1 and orig.resolves() == []
    trigger = orig.triggers()[0]
    assert trigger["routing_key"] == ROUTING_KEY
    assert trigger["event_action"] == "trigger"
    assert trigger["dedup_key"] == "omni:%s:svc:mongod" % HOST
    assert trigger["payload"]["severity"] == "critical"
    assert trigger["payload"]["source"] == HOST
    assert "MongoDB" in trigger["payload"]["summary"] and len(trigger["payload"]["summary"]) <= 1024
    assert set(trigger) == {"routing_key", "event_action", "dedup_key", "payload"}


def test_the_incident_is_marked_sent_with_its_page_key_and_one_page_sent_event_is_reported(orig):
    orig.channel("pagerduty")
    give_up(orig)
    incident = orig.saved()["incidents"]["svc:mongod"]
    assert incident["sent"] is True and incident["pageKey"] == "svc:mongod" and incident["sentAt"] is not None
    sent = orig.sync_events("page_sent")
    assert len(sent) == 1
    assert sent[0]["params"]["channel"] == "pagerduty" and "MongoDB" in sent[0]["params"]["incident"]
    assert orig.saved()["oncallLast"]["ok"] is True and orig.saved()["oncallLast"]["kind"] == "page"


def test_a_service_healthy_for_an_hour_resolves_the_page_once_with_the_same_dedup_key(orig):
    orig.channel("pagerduty")
    next_run = give_up(orig)
    orig.world.down.discard("mongod")
    orig.at(next_run)                                               # healthy again, the hour starts
    assert orig.resolves() == []
    orig.at(next_run + 3599)
    assert orig.resolves() == []
    orig.at(next_run + 3600)                                        # budget re-armed, incident cleared
    assert len(orig.resolves()) == 1
    resolve = orig.resolves()[0]
    assert resolve == {"routing_key": ROUTING_KEY, "event_action": "resolve", "dedup_key": "omni:%s:svc:mongod" % HOST}
    assert len(orig.sync_events("page_resolved")) == 1
    assert "svc:mongod" not in orig.saved()["incidents"]            # the pager dropped it
    orig.at(next_run + 3660)
    assert len(orig.resolves()) == 1 and len(orig.triggers()) == 1


def test_with_no_channel_nothing_is_sent_and_the_incident_stays_as_the_restart_plan_left_it(orig):
    give_up(orig)                                                   # no oncall.env at all
    assert orig.pagerduty() == []
    assert orig.saved()["incidents"]["svc:mongod"]["sent"] is False
    assert orig.saved()["incidents"]["svc:mongod"]["pageKey"] is None


def test_a_channel_set_up_later_pages_an_incident_that_is_still_open_once(orig):
    next_run = give_up(orig)
    orig.at(next_run)
    assert orig.pagerduty() == []
    orig.channel("pagerduty")
    orig.at(next_run + 60)
    orig.at(next_run + 120)
    assert len(orig.triggers()) == 1


def test_the_state_is_saved_with_the_page_key_before_the_trigger_leaves(orig, monkeypatch):
    orig.channel("pagerduty")
    seen = []
    real = orig.http.routes[("POST", ENQUEUE)]

    def spy(request):
        seen.append(orig.saved()["incidents"]["svc:mongod"].copy())
        return real[0]
    orig.http.set("POST", ENQUEUE, spy)
    give_up(orig)
    assert seen[0]["pageKey"] == "svc:mongod" and seen[0]["sent"] is False     # on disk before the send (Pitfall 15)
    assert orig.saved()["incidents"]["svc:mongod"]["sent"] is True


def test_the_pager_uses_the_default_verified_ssl_context_only():
    source = open(paging.__file__, encoding="utf-8").read()
    assert "CERT_NONE" not in source and "_create_unverified_context" not in source
    assert source.count("events.pagerduty.com/v2/enqueue") == 1


# --- Task 2 helpers: the pager called directly, with a hand-built incident store --------------------------------

def channel(kind="pagerduty", fmt="json", heartbeat=""):
    return config_mod.Oncall(kind, ROUTING_KEY if kind == "pagerduty" else "", WEBHOOK_URL if kind == "webhook" else "", fmt,
                             heartbeat)


def fake(path=ENQUEUE, *responses):
    http = FakeHttp()
    http.set("POST", path, *(responses or [(202, {"status": "success"})]))
    return http


def open_three(state, now=NOW):
    incidents.open_incident(state, "svc:mongod", "critical", "service_gave_up", "mongod", {"restarts": 3}, now)
    incidents.open_incident(state, "disk:/:95", "critical", "disk_full", "/", {"rung": 3, "usedPct": 96.4}, now)
    incidents.open_incident(state, "cert:/etc/nginx/ssl/omni.crt:7d", "warning", "cert_expiring", "/etc/nginx/ssl/omni.crt",
                            {"rung": 2, "daysLeft": 6.2}, now)


def bodies(http, path=ENQUEUE):
    return [json.loads(r["body"]) for r in http.requests if r["path"] == path]


# --- grouping (D-03) ----------------------------------------------------------------------------------------------

def test_three_incidents_of_one_run_are_one_trigger_keyed_by_a_critical_member():
    state, http = {}, fake()
    open_three(state)
    events = paging.page_incidents(state, channel(), http, HOST, NOW)
    sent = bodies(http)
    assert len(sent) == 1 and sent[0]["event_action"] == "trigger"
    assert sent[0]["dedup_key"] in ("omni:%s:svc:mongod" % HOST, "omni:%s:disk:/:95" % HOST)
    assert sent[0]["payload"]["severity"] == "critical"
    assert len(sent[0]["payload"]["summary"]) <= 1024 and "Also open (2)" in sent[0]["payload"]["summary"]
    assert {i["pageKey"] for i in state["incidents"].values()} == {"disk:/:95"}      # critical, then oldest, then key order
    assert all(i["sent"] for i in state["incidents"].values())
    assert [e["kind"] for e in events] == ["page_sent"]


def test_the_group_resolves_only_when_every_member_has_cleared():
    state, http = {}, fake()
    open_three(state)
    paging.page_incidents(state, channel(), http, HOST, NOW)
    incidents.clear_incident(state, "svc:mongod", NOW + 60)
    incidents.clear_incident(state, "cert:/etc/nginx/ssl/omni.crt:7d", NOW + 60)
    assert paging.page_incidents(state, channel(), http, HOST, NOW + 60) == []
    assert [b["event_action"] for b in bodies(http)] == ["trigger"]
    incidents.clear_incident(state, "disk:/:95", NOW + 120)
    events = paging.page_incidents(state, channel(), http, HOST, NOW + 120)
    sent = bodies(http)
    assert [b["event_action"] for b in sent] == ["trigger", "resolve"]
    assert sent[1] == {"routing_key": ROUTING_KEY, "event_action": "resolve", "dedup_key": sent[0]["dedup_key"]}
    assert [e["kind"] for e in events] == ["page_resolved"] and state["incidents"] == {}


def test_an_incident_opened_later_is_its_own_page_and_does_not_repage_the_first():
    state, http = {}, fake()
    incidents.open_incident(state, "svc:nginx", "critical", "service_gave_up", "nginx", {"restarts": 3}, NOW)
    paging.page_incidents(state, channel(), http, HOST, NOW)
    incidents.open_incident(state, "disk:/:90", "warning", "disk_full", "/", {"rung": 2, "usedPct": 91.0}, NOW + 60)
    paging.page_incidents(state, channel(), http, HOST, NOW + 60)
    paging.page_incidents(state, channel(), http, HOST, NOW + 120)
    assert [b["dedup_key"] for b in bodies(http)] == ["omni:%s:svc:nginx" % HOST, "omni:%s:disk:/:90" % HOST]


def test_a_ladder_move_resolves_the_old_key_before_it_triggers_the_new_one():
    state, http = {}, fake()
    incidents.open_incident(state, "cert:/c.crt:7d", "warning", "cert_expiring", "/c.crt", {"rung": 2, "daysLeft": 6.0}, NOW)
    paging.page_incidents(state, channel(), http, HOST, NOW)
    incidents.clear_incident(state, "cert:/c.crt:7d", NOW + 60)
    incidents.open_incident(state, "cert:/c.crt:1d", "critical", "cert_expiring", "/c.crt", {"rung": 3, "daysLeft": 0.5}, NOW + 60)
    paging.page_incidents(state, channel(), http, HOST, NOW + 60)
    assert [(b["event_action"], b["dedup_key"].rsplit(":", 1)[-1]) for b in bodies(http)] == [
        ("trigger", "7d"), ("resolve", "7d"), ("trigger", "1d")]


def test_a_long_dedup_key_stays_within_255_characters_and_stays_unique():
    long_a, long_b = "/" + "a" * 300 + "x", "/" + "a" * 300 + "y"
    first, second = paging.dedup_key(HOST, "cert:%s:7d" % long_a), paging.dedup_key(HOST, "cert:%s:7d" % long_b)
    assert len(first) <= 255 and len(second) <= 255 and first != second


# --- webhook shapes (D-02) ----------------------------------------------------------------------------------------

def _webhook_run(fmt):
    state, http = {}, fake(WEBHOOK_PATH, (200, "ok"))
    incidents.open_incident(state, "svc:mongod", "critical", "service_gave_up", "mongod", {"restarts": 3}, NOW)
    paging.page_incidents(state, channel("webhook", fmt), http, HOST, NOW)
    incidents.clear_incident(state, "svc:mongod", NOW + 60)
    paging.page_incidents(state, channel("webhook", fmt), http, HOST, NOW + 60)
    assert [r["url"] for r in http.requests] == [WEBHOOK_URL, WEBHOOK_URL]          # one POST per trigger and per resolve
    return bodies(http, WEBHOOK_PATH)


def test_the_json_webhook_body_has_the_documented_fields():
    trigger, resolve = _webhook_run("json")
    assert set(trigger) == {"source", "host", "action", "dedupKey", "severity", "summary", "details", "at"}
    assert trigger["source"] == "omni-watchdog" and trigger["host"] == HOST and trigger["action"] == "trigger"
    assert trigger["dedupKey"] == "omni:%s:svc:mongod" % HOST and trigger["severity"] == "critical"
    assert "MongoDB" in trigger["summary"] and trigger["details"]["host"] == HOST and trigger["at"].endswith("Z")
    assert resolve["action"] == "resolve" and resolve["dedupKey"] == trigger["dedupKey"]


def test_the_slack_and_teams_webhook_bodies_are_just_text():
    for fmt in ("slack", "teams"):
        trigger, resolve = _webhook_run(fmt)
        assert set(trigger) == {"text"} and set(resolve) == {"text"}
        assert "MongoDB" in trigger["text"] and "critical" in trigger["text"] and HOST in trigger["text"]
        assert resolve["text"].startswith("[resolved]")


# --- delivery rules -------------------------------------------------------------------------------------------------

def test_a_503_twice_then_202_is_one_delivery_after_waits_of_1_and_3_seconds():
    http, waits = fake(ENQUEUE, (503, "x"), (503, "x"), (202, {})), []
    message = paging.pagerduty_event(channel(), "trigger", "omni:h:k", "critical", "s", {}, "h")
    assert paging.send(http, channel(), message, sleep=waits.append) == (True, None)
    assert len(http.requests) == 3 and waits == [1, 3]


def test_429_is_retried_and_a_third_failure_gives_up_with_the_status_in_the_error():
    http, waits = fake(ENQUEUE, (429, "x")), []
    message = paging.pagerduty_event(channel(), "trigger", "omni:h:k", "critical", "s", {}, "h")
    assert paging.send(http, channel(), message, sleep=waits.append) == (False, "PagerDuty answered HTTP 429.")
    assert len(http.requests) == 3 and waits == [1, 3]


def test_a_400_or_other_4xx_is_never_retried():
    for status in (400, 401, 404):
        http, waits = fake(ENQUEUE, (status, "bad")), []
        message = paging.pagerduty_event(channel(), "trigger", "omni:h:k", "critical", "s", {}, "h")
        assert paging.send(http, channel(), message, sleep=waits.append) == (False, "PagerDuty answered HTTP %d." % status)
        assert len(http.requests) == 1 and waits == []


def test_a_failed_page_emits_one_page_failed_leaves_the_incident_unsent_and_is_retried_next_run():
    state, http = {}, fake(ENQUEUE, (400, "bad"), (400, "bad"), (202, {}))
    incidents.open_incident(state, "svc:mongod", "critical", "service_gave_up", "mongod", {"restarts": 3}, NOW)
    first = paging.page_incidents(state, channel(), http, HOST, NOW)
    assert [e["kind"] for e in first] == ["page_failed"]
    assert first[0]["params"]["error"] == "PagerDuty answered HTTP 400." and first[0]["params"]["channel"] == "pagerduty"
    assert state["incidents"]["svc:mongod"]["sent"] is False and state["incidents"]["svc:mongod"]["pageKey"] == "svc:mongod"
    assert state["oncallLast"]["ok"] is False and state["oncallLast"]["kind"] == "page"
    assert paging.page_incidents(state, channel(), http, HOST, NOW + 60) == []      # same error: not another event per minute
    assert len(bodies(http)) == 2 and set(state["incidents"]) == {"svc:mongod"}      # retried, still one incident
    done = paging.page_incidents(state, channel(), http, HOST, NOW + 120)
    assert [e["kind"] for e in done] == ["page_sent"] and state["incidents"]["svc:mongod"]["sent"] is True
    assert paging.page_incidents(state, channel(), http, HOST, NOW + 180) == [] and len(bodies(http)) == 3


def test_a_connection_failure_is_retried_and_the_error_names_only_the_exception_class():
    http, waits = FakeHttp(), []
    http.set("POST", ENQUEUE, ConnectionRefusedError("refused connecting to https://events.pagerduty.com secret"))
    message = paging.pagerduty_event(channel(), "trigger", "omni:h:k", "critical", "s", {}, "h")
    ok, error = paging.send(http, channel(), message, sleep=waits.append)
    assert ok is False and error == "PagerDuty could not be reached (ConnectionRefusedError)." and waits == [1, 3]


def test_no_retry_starts_after_the_runs_send_window():
    clock = FakeClock(NOW)
    budget = paging.Budget(clock=clock, deadline=NOW + paging.SEND_WINDOW)
    http = fake(ENQUEUE, (503, "x"))
    message = paging.pagerduty_event(channel(), "trigger", "omni:h:k", "critical", "s", {}, "h")

    def slow(seconds):
        clock.advance(seconds + paging.SEND_WINDOW)      # the wait is so long the window is over afterwards
    ok, _error = paging.send(http, channel(), message, sleep=slow, budget=budget)
    assert ok is False and len(http.requests) == 2 and budget.can_send() is False


# --- the backend's outbox (D-04) and the results report -------------------------------------------------------

def notice(n, **extra):
    item = {"id": "OB-%032d" % n, "kind": "trigger", "dedupKey": None, "severity": "warning",
            "summary": "Automatic actions stopped: Stopped by Ana.", "details": {"title": "Automatic actions stopped", "tenantId": "t1"}}
    item.update(extra)
    return item


def test_every_outbox_message_is_delivered_once_and_reported_through_results_in_the_same_run(orig):
    orig.channel("pagerduty")
    orig.sync_says(outbox=[notice(1), notice(2)])
    orig.at(0)
    sent = orig.triggers()
    assert [b["dedup_key"] for b in sent] == ["omni:%s:OB-%032d" % (HOST, 1), "omni:%s:OB-%032d" % (HOST, 2)]
    assert sent[0]["payload"]["severity"] == "warning" and sent[0]["payload"]["summary"].startswith("Automatic actions stopped")
    assert sent[0]["payload"]["custom_details"] == {"title": "Automatic actions stopped", "tenantId": "t1"}
    posted = orig.results()
    assert len(posted) == 1 and posted[0]["v"] == 1 and "testResult" not in posted[0]
    assert [(d["id"], d["ok"]) for d in posted[0]["delivered"]] == [("OB-%032d" % 1, True), ("OB-%032d" % 2, True)]
    assert all(d["at"].endswith("Z") for d in posted[0]["delivered"])
    assert orig.saved()["delivered"] == ["OB-%032d" % 1, "OB-%032d" % 2]


def test_an_outbox_id_that_comes_back_is_not_sent_again(orig):
    orig.channel("pagerduty")
    orig.sync_says(outbox=[notice(1)])
    orig.at(0)
    orig.at(60)                                                     # the backend lost the acknowledgement and lists it again
    orig.at(120)
    assert len(orig.triggers()) == 1
    assert [d["id"] for d in orig.results()[-1]["delivered"]] == ["OB-%032d" % 1]    # only re-reported


def test_a_message_that_carries_a_dedup_key_uses_it_and_a_resolve_kind_resolves(orig):
    orig.channel("pagerduty")
    orig.sync_says(outbox=[notice(1, dedupKey="notice:stop:1"), notice(2, kind="resolve", dedupKey="notice:stop:1")])
    orig.at(0)
    assert [(b["event_action"], b["dedup_key"]) for b in orig.pagerduty()] == [("trigger", "notice:stop:1"),
                                                                                ("resolve", "notice:stop:1")]


def test_a_failed_outbox_delivery_is_reported_with_its_error_and_not_resent(orig):
    orig.channel("pagerduty")
    orig.http.set("POST", ENQUEUE, (400, "bad"))
    orig.sync_says(outbox=[notice(1)])
    orig.at(0)
    orig.at(60)
    assert len(orig.pagerduty()) == 1
    entry = orig.results()[0]["delivered"][0]
    assert entry["ok"] is False and entry["error"] == "PagerDuty answered HTTP 400."
    assert orig.results()[1]["delivered"][0]["ok"] is False


def test_at_most_ten_messages_go_out_in_one_run_and_the_rest_wait(orig):
    orig.channel("pagerduty")
    orig.sync_says(outbox=[notice(n) for n in range(1, 16)])
    orig.at(0)
    assert len(orig.pagerduty()) == 10 and len(orig.results()[0]["delivered"]) == 10
    orig.at(60)
    assert len(orig.pagerduty()) == 15


def test_with_no_channel_the_outbox_is_left_for_the_backend_to_expire(orig):
    orig.sync_says(outbox=[notice(1)])
    orig.at(0)
    assert orig.pagerduty() == [] and orig.results() == [] and orig.saved().get("delivered") is None


def test_a_results_call_that_fails_leaves_delivered_for_the_next_sync_body(orig):
    orig.channel("pagerduty")
    orig.http.set("POST", RESULTS, (503, "down"), (200, {"ok": True}))
    orig.sync_says(outbox=[notice(1)])
    orig.at(0)
    assert [d["id"] for d in orig.saved()["pendingDelivered"]] == ["OB-%032d" % 1]
    orig.sync_says(outbox=[])
    orig.at(60)
    assert [d["id"] for d in orig.body()["delivered"]] == ["OB-%032d" % 1]
    assert orig.saved()["pendingDelivered"] == [] and len(orig.pagerduty()) == 1


# --- the test alert (D-21, Pitfall 11) ------------------------------------------------------------------------------

REQUEST = {"id": "TR-" + "ab12" * 8, "requestedAt": "2027-01-15T08:00:00+00:00"}


def test_a_test_request_is_a_trigger_then_a_resolve_with_the_same_key_and_is_reported(orig):
    orig.channel("pagerduty")
    orig.sync_says(test_request=REQUEST)
    orig.at(0)
    key = "omni:%s:test:%s" % (HOST, REQUEST["id"])
    sent = orig.pagerduty()
    assert [(b["event_action"], b["dedup_key"], b["routing_key"]) for b in sent] == [("trigger", key, ROUTING_KEY),
                                                                                     ("resolve", key, ROUTING_KEY)]
    assert sent[0]["payload"]["severity"] == "info"
    result = orig.results()[0]["testResult"]
    assert result["id"] == REQUEST["id"] and result["ok"] is True and "error" not in result
    events = orig.run_events("test_alert")
    assert len(events) == 1 and events[0]["id"] == "test-" + REQUEST["id"]
    assert events[0]["params"] == {"requestId": REQUEST["id"], "ok": True}
    orig.sync_says()
    orig.at(60)                                                     # the event reaches the backend with the next sync
    assert [e["id"] for e in orig.sync_events("test_alert")] == ["test-" + REQUEST["id"]]
    assert "pendingTest" not in orig.saved()


def test_a_test_request_with_no_channel_is_a_failed_result_and_makes_no_http_call(orig):
    orig.sync_says(test_request=REQUEST)
    orig.at(0)
    assert orig.pagerduty() == [] and orig.webhook() == []
    result = orig.results()[0]["testResult"]
    assert result["ok"] is False and result["error"] == NO_CHANNEL
    assert orig.run_events("test_alert")[0]["params"]["error"] == NO_CHANNEL


def test_a_test_trigger_that_fails_sends_no_resolve_and_reports_the_error(orig):
    orig.channel("pagerduty")
    orig.http.set("POST", ENQUEUE, (400, "bad"))
    orig.sync_says(test_request=REQUEST)
    orig.at(0)
    assert [b["event_action"] for b in orig.pagerduty()] == ["trigger"]
    assert orig.results()[0]["testResult"]["error"] == "PagerDuty answered HTTP 400."


def test_a_test_resolve_that_fails_is_reported_as_not_delivered(orig):
    orig.channel("pagerduty")
    orig.http.set("POST", ENQUEUE, (202, {}), (400, "bad"))
    orig.sync_says(test_request=REQUEST)
    orig.at(0)
    result = orig.results()[0]["testResult"]
    assert result["ok"] is False and result["error"].startswith("The test alert arrived but could not be resolved")


def test_a_test_result_that_could_not_be_posted_is_posted_again_without_a_second_alert(orig):
    orig.channel("pagerduty")
    orig.http.set("POST", RESULTS, (503, "down"), (200, {"ok": True}))
    orig.sync_says(test_request=REQUEST)
    orig.at(0)
    assert orig.saved()["pendingTest"]["id"] == REQUEST["id"]
    orig.at(60)                                                     # the backend still lists the request: result re-posted, not re-sent
    assert len(orig.pagerduty()) == 2
    assert [r["testResult"]["id"] for r in orig.results()] == [REQUEST["id"], REQUEST["id"]]
    assert "pendingTest" not in orig.saved()


def test_a_test_alert_on_a_webhook_sends_the_trigger_and_the_resolve(orig):
    orig.channel("webhook", WEBHOOK_FORMAT="slack")
    orig.sync_says(test_request=REQUEST)
    orig.at(0)
    texts = [b["text"] for b in orig.webhook()]
    assert len(texts) == 2 and texts[1].startswith("[resolved]") and orig.results()[0]["testResult"]["ok"] is True


# --- the external heartbeat (D-05) and secrecy (D-01) ---------------------------------------------------------------

def test_the_heartbeat_url_gets_one_get_per_run_with_a_5_second_timeout(orig):
    orig.channel("none", HEARTBEAT_URL=HEARTBEAT_URL)
    orig.http.set("GET", HEARTBEAT_PATH, (200, "OK"))
    for t in (0, 60, 120):
        orig.at(t)
    pings = [r for r in orig.http.requests if r["path"] == HEARTBEAT_PATH]
    assert len(pings) == 3 and {r["method"] for r in pings} == {"GET"} and {r["timeout"] for r in pings} == {5}
    assert all(r["url"] == HEARTBEAT_URL for r in pings)
    assert orig.body()["oncall"] == {"type": "none", "heartbeatConfigured": True, "last": None}


def test_a_failing_heartbeat_changes_nothing_and_logs_no_url(orig, caplog):
    orig.channel("none", HEARTBEAT_URL=HEARTBEAT_URL)
    orig.http.set("GET", HEARTBEAT_PATH, ConnectionRefusedError("refused " + HEARTBEAT_URL))
    with caplog.at_level(logging.DEBUG):
        summary = orig.at(0)
    assert summary["synced"] is True
    assert "heartbeat ping failed (ConnectionRefusedError)" in caplog.text
    assert "SECRET-HEARTBEAT" not in caplog.text and HEARTBEAT_URL not in caplog.text


def test_no_heartbeat_is_sent_when_none_is_configured(orig):
    orig.channel("none")
    orig.at(0)
    assert [r for r in orig.http.requests if r["path"] == HEARTBEAT_PATH] == []


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def test_no_secret_appears_in_any_body_sent_to_the_backend_in_an_event_or_in_the_state_file(orig):
    orig.channel("pagerduty", HEARTBEAT_URL=HEARTBEAT_URL, WEBHOOK_URL=WEBHOOK_URL)
    orig.http.set("GET", HEARTBEAT_PATH, (200, "OK"))
    orig.http.set("POST", ENQUEUE, (400, "echo %s %s" % (ROUTING_KEY, WEBHOOK_URL)))      # a hostile answer echoing secrets
    orig.sync_says(outbox=[notice(1)], test_request=REQUEST)
    give_up(orig)
    orig.at(600)
    posted = orig.http.posted(SYNC) + orig.http.posted(RESULTS)
    assert posted
    for body in posted:
        for text in _strings(body):
            assert not any(secret in text for secret in SECRETS), text
    assert not any(secret in open(orig.state_dir + "/state.json", encoding="utf-8").read() for secret in SECRETS)
    assert orig.body()["oncall"]["heartbeatConfigured"] is True and set(orig.body()["oncall"]) == {"type", "heartbeatConfigured", "last"}
    assert set(orig.body()["oncall"]["last"]) == {"at", "ok", "error", "kind"}
