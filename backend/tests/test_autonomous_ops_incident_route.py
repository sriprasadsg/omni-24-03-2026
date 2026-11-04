"""RESP-09 / ACTV-02 / D-17 / D-24 / D-27: GET /api/autonomous-ops/incidents, the Needs your decision cards.
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py; the routers are
mounted as in production with the identity replaced by a dependency override.

Value: protects=one card per incident that needs a person, every waiting line with its own server-decided flags
(no approve-all), automatic lines of the incident as context with no flags, a kill line and its retry folded into
one line, soonest deadline first, and no row of another organization ever reachable;
fails_when=a card lists a finished-only incident, a flag is true for a view-only role, Platform Support or an API
key, a suggestionOnly row shows, two waiting rows share a flag, the retry row is a line of its own, the order or
page size is wrong, or another tenant's incident leaks; no_claim=the browser, the agent, or the approve route.
"""
from datetime import datetime, timedelta, timezone

import pytest

from autonomous_ops import PLATFORM_TENANT_ID, incident_views, ledger, response_messages as rm
from tests._autonomous_ops_http import PLATFORM, _env, api  # noqa: F401  (fixtures)
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_platform_stop

PATH = "/api/autonomous-ops/incidents"


def ms(value):
    return value.replace(microsecond=value.microsecond // 1000 * 1000)


NOW = ms(datetime.now(timezone.utc))


async def host(db, tenant="t1", agent="a1", name="host-a1"):
    await db.agents.replace_one({"id": agent}, {"id": agent, "tenantId": tenant, "hostname": name,
                                                "ipAddress": "10.9.9.9", "status": "Online"}, upsert=True)


async def incident(db, iid="INC-1", tenant="t1", agent="a1", started=None, alerts=2):
    started = started or NOW - timedelta(minutes=30)
    await db.autonomy_incidents.replace_one(
        {"id": iid}, {"id": iid, "tenantId": tenant, "agentId": agent, "startedAt": started, "lastAlertAt": started,
                      "alertCount": alerts, "closed": False, "isolateProposed": False}, upsert=True)


async def row(db, rid, command, state, *, iid="INC-1", tenant="t1", agent="a1", expires=None, minutes=0, code="class_approve",
              params=None, inputs=None, **extra):
    """A ledger row of the security_response dispatcher; ``minutes`` after NOW is its creation time."""
    created = NOW + timedelta(minutes=minutes)
    doc = {"id": rid, "tenantId": tenant, "kind": "security", "origin": "sweep", "dispatcher": "security_response",
           "command": command, "actions": [command], "targets": [agent], "target": agent, "params": params or {},
           "state": state, "reasonCode": code, "reasonText": "Why " + rid, "dedupeKey": f"{tenant}|{rid}",
           "autoDispatched": state in ("dispatching", "executed", "verified") and code == "class_auto",
           "instructionIds": [], "createdAt": created, "updatedAt": created,
           "reason": {"ruleId": "sweep:" + command, "inputs": {"incidentId": iid, **(inputs or {})}},
           "approval": {"requiredBy": code if state in ("awaiting_approval", "suggested") else None,
                        "expiresAt": expires or (created + timedelta(hours=24)), "approver": None, "decidedAt": None},
           "undo": {"available": False}, **extra}
    await db.autonomy_actions.insert_one(doc)
    return doc


async def get(api, role="security_analyst", path=PATH, **kw):
    got = await api.call("GET", path, role=role, **kw)
    assert got.status_code == 200, got.text
    return got.json()


def lines(card):
    return {l["id"]: l for l in card["actions"]}


@pytest.fixture
async def world(api):
    await ledger.ensure_indexes(api.db)
    await host(api.db)
    await incident(api.db)
    return api


# ------------------------------------------------------------------ grouping and flags

async def test_three_waiting_rows_are_one_card_each_with_its_own_flags(world):
    """fails_when=the rows are three cards, or a flag is shared, or there is an approve-all."""
    for n, cmd in enumerate(("isolate_host", "kill_process", "reboot_host")):
        await row(world.db, f"w{n}", cmd, "awaiting_approval", minutes=n)
    body = await get(world)
    assert body["total"] == 1 and len(body["items"]) == 1
    card = body["items"][0]
    assert card["id"] == "INC-1" and card["host"] == "host-a1" and card["alertCount"] == 2
    assert card["startedAt"] == (NOW - timedelta(minutes=30)).isoformat() and card["deadlineKind"] == "expires"
    assert len(card["actions"]) == 3
    for line in card["actions"]:
        assert line["canApprove"] is True and line["canDeny"] is True and line["canConfirmIsolation"] is False
        assert line["needsPerson"] is True and line["result"] is None
    assert lines(card)["w0"]["consequenceText"] == rm.WHAT_HAPPENS["isolate_host"]
    assert lines(card)["w1"]["consequenceText"] == rm.WHAT_HAPPENS["kill_process"]
    assert lines(card)["w2"]["consequenceText"] == rm.WHAT_HAPPENS["reboot_host"]
    assert not any("approve" in k.lower() and "all" in k.lower() for k in card)


async def test_automatic_lines_of_the_incident_are_context_with_no_flags_and_sort_after(world):
    await row(world.db, "auto", "block_ip", "verified", code="class_auto", minutes=5, params={"ip_address": "45.33.32.156"},
              inputs={"origins": ["native", "feed:otx"], "twoSignal": True}, blockedUntil=NOW + timedelta(hours=3),
              blockedFrom=NOW, instructionIds=["i1"], target="45.33.32.156")
    await row(world.db, "wait", "kill_process", "awaiting_approval", minutes=1)
    card = (await get(world))["items"][0]
    assert [l["id"] for l in card["actions"]] == ["wait", "auto"]            # needs a person first, then context
    ctx = lines(card)["auto"]
    assert ctx["needsPerson"] is False and ctx["bucket"] == "done"
    assert not (ctx["canApprove"] or ctx["canDeny"] or ctx["canConfirmIsolation"])
    assert ctx["label"] == "Block IP address" and ctx["target"] == "45.33.32.156"
    # The block's result carries {until}; the browser fills it from this time (83-19), so it must be on the line.
    assert "{until}" in ctx["result"] and ctx["blockedUntil"] == (NOW + timedelta(hours=3)).isoformat()
    assert lines(card)["wait"]["blockedUntil"] is None


async def test_an_incident_with_only_finished_rows_gives_no_card(world):
    await row(world.db, "r1", "block_ip", "verified", code="class_auto")
    await row(world.db, "r2", "kill_process", "denied")
    await row(world.db, "r3", "reboot_host", "awaiting_approval", expires=NOW - timedelta(minutes=1))   # past its 24 hours
    page = await get(world)
    page.pop("serverNow")
    assert page == {"items": [], "total": 0, "offset": 0, "limit": 10, "stopped": None}


async def test_decided_lines_stay_on_a_card_that_still_has_one_waiting(world):
    await row(world.db, "wait", "kill_process", "awaiting_approval", minutes=2)
    await row(world.db, "yes", "reboot_host", "dispatching", minutes=1,
              approval={"approver": {"username": "a", "display": "Alice"}, "expiresAt": NOW + timedelta(hours=1)})
    await row(world.db, "no", "isolate_host", "denied", minutes=0,
              approval={"approver": {"username": "b", "display": "Bob"}, "expiresAt": NOW + timedelta(hours=1)})
    await row(world.db, "late", "restart_service", "expired", minutes=-1)
    by = lines((await get(world))["items"][0])
    assert by["yes"]["result"] == "Approved. Sent to host-a1." and by["yes"]["canApprove"] is False
    assert by["no"]["result"] == "Denied by Bob." and by["no"]["canDeny"] is False
    assert by["late"]["result"] == "Expired after 24 hours, counted as denied."
    assert by["wait"]["canApprove"] is True


# ------------------------------------------------------------------ order and paging

async def test_cards_sort_by_soonest_deadline_then_newer_incident(world):
    for iid, minutes_ago, hours in (("INC-A", 50, 10), ("INC-B", 20, 5), ("INC-C", 10, 5), ("INC-D", 40, 20)):
        await incident(world.db, iid, started=NOW - timedelta(minutes=minutes_ago))
        await row(world.db, "w" + iid, "kill_process", "awaiting_approval", iid=iid, expires=NOW + timedelta(hours=hours))
    order = [c["id"] for c in (await get(world))["items"]]
    assert order == ["INC-C", "INC-B", "INC-A", "INC-D"]          # equal 5 h: the newer incident (C) first


async def test_the_page_size_is_ten_with_a_total(world):
    for n in range(12):
        iid = f"INC-{n:02d}"
        await incident(world.db, iid, started=NOW - timedelta(minutes=n))
        await row(world.db, "w" + iid, "kill_process", "awaiting_approval", iid=iid, expires=NOW + timedelta(hours=1 + n))
    first = await get(world)
    assert first["total"] == 12 and len(first["items"]) == 10 and first["limit"] == 10
    second = await get(world, path=PATH + "?offset=10")
    assert [c["id"] for c in second["items"]] == ["INC-10", "INC-11"] and second["total"] == 12
    assert [c["id"] for c in first["items"]][-1] == "INC-09"
    assert (await world.call("GET", PATH + "?limit=51", role="security_analyst")).status_code == 422


# ------------------------------------------------------------------ the kill chain, protected files, restart cards

KILL = {"target": "4120", "expected_exe": "/tmp/evil.bin", "processes": [{"pid": 4120, "start_time": 1700000000}]}


def chain(mode, qid="q1"):
    return {"chain": {"mode": mode, "quarantineActionId": qid, "path": "/tmp/evil.bin", "sha256": "d" * 64,
                      "process": {"pid": 4120, "name": "evil.bin", "start_time": 1700000000}}}


async def test_a_kill_and_its_retry_are_one_line_with_steps(world):
    await row(world.db, "q1", "quarantine_file", "failed", code="locked", minutes=0, params={"path": "/tmp/evil.bin"})
    await row(world.db, "k1", "kill_process", "awaiting_approval", minutes=1, params=KILL, inputs=chain("retry"),
              reasonText=rm.REASON_TEXT["locked"])
    card = (await get(world))["items"][0]
    assert [l["id"] for l in card["actions"]] == ["k1"]                 # the locked quarantine is the cause, not a line
    line = card["actions"][0]
    assert line["label"] == "Kill process, then quarantine file" and line["target"] == "evil.bin (PID 4120)"
    assert line["chain"]["path"] == "/tmp/evil.bin" and line["notice"] == rm.NOTICES["kill_then_quarantine"]
    assert line["consequenceText"] == rm.WHAT_HAPPENS["kill_then_quarantine"]
    assert line["reason"] == rm.REASON_TEXT["locked"]
    assert line["chain"]["steps"] == [{"label": "Kill process", "state": "pending"},
                                      {"label": "Quarantine file", "state": "pending"}]
    # approved and run: the retry row exists and is not a line of its own
    await world.db.autonomy_actions.update_one({"id": "k1"}, {"$set": {"state": "verified"}})
    await row(world.db, "r1", "quarantine_file", "dispatching", minutes=2, code="class_auto",
              inputs={"parentActionId": "k1"})
    await row(world.db, "w2", "reboot_host", "awaiting_approval", minutes=3)          # keeps the card open
    line = lines((await get(world))["items"][0])["k1"]
    assert "r1" not in lines((await get(world))["items"][0])
    assert line["chain"]["steps"] == [{"label": "Kill process", "state": "done"},
                                      {"label": "Quarantine file", "state": "pending"}]
    await world.db.autonomy_actions.update_one({"id": "r1"}, {"$set": {"state": "failed", "reasonCode": "locked"}})
    line = lines((await get(world))["items"][0])["k1"]
    assert line["chain"]["steps"][1]["state"] == "failed"
    assert line["result"] == "The process was ended but the file is still in place: the file is still in use."


async def test_a_failed_kill_skips_the_second_step(world):
    await row(world.db, "k1", "kill_process", "failed", minutes=1, params=KILL, inputs=chain("retry"))
    await row(world.db, "w", "reboot_host", "awaiting_approval", minutes=2)
    line = lines((await get(world))["items"][0])["k1"]
    assert [s["state"] for s in line["chain"]["steps"]] == ["failed", "skipped"]


async def test_a_kill_only_line_shows_its_notice_once_and_keeps_the_done_quarantine(world):
    await row(world.db, "q1", "quarantine_file", "verified", code="class_auto", minutes=0, params={"path": "/tmp/evil.bin"},
              stillRunning=[{"pid": 4120, "name": "evil.bin", "start_time": 1700000000}])
    await row(world.db, "k1", "kill_process", "awaiting_approval", minutes=1, params=KILL, inputs=chain("kill_only"),
              reasonText=rm.NOTICES["kill_only"])
    by = lines((await get(world))["items"][0])
    assert set(by) == {"q1", "k1"}
    assert by["k1"]["label"] == "Kill process" and by["k1"]["notice"] == rm.NOTICES["kill_only"]
    assert by["k1"]["reason"] is None and by["k1"]["chain"]["steps"] == []        # the notice is not said twice
    assert by["k1"]["consequenceText"] == rm.WHAT_HAPPENS["kill_process"]
    assert by["q1"]["result"].endswith(rm.RESULT_TEMPLATES["quarantine_still_running"])     # a card is waiting


async def test_the_quarantine_stops_pointing_at_a_card_that_is_gone(world):
    """The run notes: a Done kill-only quarantine must not say 'See Needs your decision' when nothing is there."""
    await row(world.db, "q1", "quarantine_file", "verified", code="class_auto", params={"path": "/tmp/evil.bin"},
              stillRunning=[{"pid": 4120, "name": "evil.bin", "start_time": 1700000000}], targets=["a1"])
    await row(world.db, "k1", "kill_process", "denied", params=KILL, inputs=chain("kill_only"))
    page = await world.call("GET", "/api/autonomous-ops/actions", role="security_analyst")
    q = [i for i in page.json()["items"] if i["id"] == "q1"][0]
    assert q["resultText"].endswith("The process is still running.") and "Needs your decision" not in q["resultText"]
    await world.db.autonomy_actions.update_one({"id": "k1"}, {"$set": {"state": "awaiting_approval"}})
    page = await world.call("GET", "/api/autonomous-ops/actions", role="security_analyst")
    assert "See Needs your decision" in [i for i in page.json()["items"] if i["id"] == "q1"][0]["resultText"]


async def test_a_protected_file_line_has_its_reason_and_what_happens(world):
    await row(world.db, "p1", "quarantine_file", "awaiting_approval", code="playbook_raised",
              params={"path": "C:\\Windows\\System32\\x.dll", "allow_protected": True},
              inputs={"protectedPath": True, "detail": "Two sources agree."}, reasonText="ignored",
              target="C:\\Windows\\System32\\x.dll")
    line = (await get(world))["items"][0]["actions"][0]
    assert line["reason"] == "This is a protected system file, so it isn't moved automatically. Two sources agree."
    assert line["consequenceText"] == rm.WHAT_HAPPENS["protected_file"]
    assert line["target"] == "C:\\Windows\\System32\\x.dll"


async def test_the_over_budget_restart_card(world):
    await row(world.db, "s1", "restart_service", "awaiting_approval", code="playbook_raised", params={"service_name": "nginx"},
              inputs={"service": "nginx", "overBudget": True})
    line = (await get(world))["items"][0]["actions"][0]
    assert line["reason"] == "Restarted nginx 3 times in the last hour. Further restarts need your approval."
    assert line["consequenceText"] == "Restarts nginx on this computer. If it fails again it stays down until you act."


async def test_an_approved_restart_card_reads_restarted_without_a_count(world):
    """The run notes (83-17): a card past the budget has no attempt; its Result must still say what happened."""
    await row(world.db, "s1", "restart_service", "verified", code="playbook_raised", params={"service_name": "nginx"},
              inputs={"service": "nginx", "overBudget": True}, result={"healthy_after": 4})
    page = await world.call("GET", "/api/autonomous-ops/actions", role="security_analyst")
    assert page.json()["items"][0]["resultText"] == "Restarted nginx. Healthy again after 4 s."


async def test_a_range_card_says_why_two_sources_agree_not_the_refusal_sentence(world):
    """The run notes (83-08): REASON_TEXT['range_block'] reads like a refusal on a card that asks for approval.
    A range row carries its origins, so the card gives the Why of every block; only a row with no inputs would fall back."""
    await row(world.db, "rng", "block_ip", "awaiting_approval", code="range_block", target="45.33.32.0/24",
              params={"cidr": "45.33.32.0/24", "ttl_seconds": 86400}, reasonText=rm.REASON_TEXT["range_block"],
              inputs={"origins": ["native", "feed:otx"], "twoSignal": True})
    line = (await get(world))["items"][0]["actions"][0]
    assert line["reason"] == "Two sources agree: agent verdict and OTX." and line["target"] == "45.33.32.0/24"
    assert line["canApprove"] is True


# ------------------------------------------------------------------ which rows count (A-83-LEVEL-SUGGEST)

async def test_suggestion_only_rows_never_show_but_a_level_suggest_row_does(world):
    await row(world.db, "only", "block_ip", "suggested", code="suggest_requested", inputs={"suggestionOnly": True})
    await row(world.db, "vuln", "upgrade_software", "suggested", code="level_suggest", inputs={"suggestionOnly": True})
    assert (await get(world))["total"] == 0
    await row(world.db, "lvl", "block_ip", "suggested", code="level_suggest", params={"ip_address": "45.33.32.156"})
    await row(world.db, "unread", "quarantine_file", "suggested", code="settings_unreadable", minutes=1,
              params={"path": "/tmp/x"})
    await row(world.db, "other", "block_ip", "suggested", code="suggest_requested", minutes=2)      # one source, no marker
    card = (await get(world))["items"][0]
    assert set(lines(card)) == {"lvl", "unread"}
    assert all(l["canApprove"] and l["canDeny"] for l in card["actions"])
    assert incident_views.APPROVABLE_SUGGESTION_CODES == ("level_suggest", "settings_unreadable")


async def test_an_unconfirmed_isolation_is_a_waiting_line_with_its_own_deadline(world):
    reverts = NOW + timedelta(hours=3, minutes=12)
    await row(world.db, "iso", "isolate_host", "verified", instructionIds=["t-iso"], isolation={"revertsAt": reverts},
              approval={"approver": {"username": "a"}, "expiresAt": NOW})
    await row(world.db, "w", "kill_process", "awaiting_approval", expires=NOW + timedelta(hours=20), minutes=1)
    card = (await get(world))["items"][0]
    line = lines(card)["iso"]
    assert line["canConfirmIsolation"] is True and line["canApprove"] is False and line["needsPerson"] is True
    assert line["revertsAt"] == reverts.isoformat() and line["result"] == "host-a1 is isolated. The connection to the platform stays open."
    assert line["consequenceText"] == rm.WHAT_HAPPENS["isolation_unconfirmed"]
    assert card["deadlineAt"] == reverts.isoformat() and card["deadlineKind"] == "reverts"
    # confirmed: a context line, no flags, the sentence names who
    await world.db.autonomy_actions.update_one({"id": "iso"}, {"$set": {"isolation.confirmedAt": NOW,
                                                "isolation.confirmedBy": {"username": "c", "display": "Cy"}}})
    card = (await get(world))["items"][0]
    line = lines(card)["iso"]
    assert line["canConfirmIsolation"] is False and line["needsPerson"] is False and line["confirmedBy"] == "Cy"
    assert line["result"] == "Confirmed by Cy at {at}. The computer stays isolated until a person restores it."
    assert card["deadlineKind"] == "expires"
    await world.db.autonomy_actions.delete_one({"id": "w"})
    assert (await get(world))["total"] == 0                       # a confirmed isolation alone needs nobody


# ------------------------------------------------------------------ who sees what

async def test_flags_follow_the_caller_and_the_server_grants_nothing_to_keys_or_view_roles(world):
    await row(world.db, "w", "kill_process", "awaiting_approval")
    await row(world.db, "iso", "isolate_host", "verified", minutes=1, isolation={"revertsAt": NOW + timedelta(hours=1)},
              approval={"expiresAt": NOW})

    def flags(body):
        return [(l["canApprove"], l["canDeny"], l["canConfirmIsolation"]) for l in body["items"][0]["actions"]]

    for role in ("tenant_admin", "security_analyst", "incident_responder"):
        assert set(flags(await get(world, role=role))) == {(True, True, False), (False, False, True)}, role
    for role in ("analyst",):                 # holds view:autonomous_ops, not control (the viewer role has no view)
        assert set(flags(await get(world, role=role))) == {(False, False, False)}, role
    key = await get(world, role="tenant_admin", auth="api_key", scopes=["view:autonomous_ops", "control:autonomous_ops"])
    assert set(flags(key)) == {(False, False, False)}
    support = await get(world, role="platform_support", path=PATH + "?tenantId=t1")
    assert set(flags(support)) == {(False, False, False)}
    root = await get(world, role="super_admin", path=PATH + "?tenantId=t1")
    assert set(flags(root)) == {(True, True, False), (False, False, True)}


async def test_another_tenants_incident_never_leaks(world, api):
    from tests.autonomy_support import seed_tenant
    await row(world.db, "w", "kill_process", "awaiting_approval")
    await host(world.db, "t2", "b1", "host-b1")
    await incident(world.db, "INC-1", "t1")
    own = await get(world, role="security_analyst", tenant="t2")
    own.pop("serverNow")
    assert own == {"items": [], "total": 0, "offset": 0, "limit": 10, "stopped": None}      # empty, not 403
    assert (await world.call("GET", PATH + "?tenantId=t1", role="security_analyst", tenant="t2")).status_code == 403
    # the same incident id on both tenants: each sees only its own row
    await incident(world.db, "INC-1x", "t2", "b1")
    await row(world.db, "w2", "reboot_host", "awaiting_approval", iid="INC-1", tenant="t2", agent="b1")
    mine = await get(world, role="security_analyst", tenant="t2")
    assert [l["id"] for c in mine["items"] for l in c["actions"]] == ["w2"]
    theirs = await get(world, role="security_analyst")
    assert [l["id"] for c in theirs["items"] for l in c["actions"]] == ["w"]


async def test_platform_staff_must_name_a_tenant_and_a_missing_one_is_404(world):
    assert (await world.call("GET", PATH, role="super_admin")).status_code == 400
    assert (await world.call("GET", PATH + "?tenantId=nope", role="super_admin")).status_code == 404
    assert (await world.call("GET", PATH + f"?tenantId={PLATFORM}", role="super_admin")).json()["items"] == []


async def test_the_page_carries_the_servers_clock_as_a_utc_iso_string(world):
    """WR-27 (backend half): the browser compares deadlines with the server's clock, not its own, so every
    page (empty or not) carries ``serverNow``: an ISO-8601 UTC time close to now."""
    empty = await get(world)
    await row(world.db, "w", "kill_process", "awaiting_approval")
    for page in (empty, await get(world)):
        stamp = datetime.fromisoformat(page["serverNow"])
        assert stamp.utcoffset() == timedelta(0) and abs(datetime.now(timezone.utc) - stamp) < timedelta(seconds=30)
    assert len(empty["items"]) == 0 and len((await get(world))["items"]) == 1


async def test_the_stop_is_in_the_payload_with_its_scope(world):
    await row(world.db, "w", "kill_process", "awaiting_approval")
    assert (await get(world))["stopped"] is None
    await world.db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"stop": {"active": True}}})
    assert (await get(world))["stopped"] == {"scope": "tenant"}
    await seed_platform_stop(world.db)
    assert (await get(world))["stopped"] == {"scope": "platform"}
    assert (await get(world))["items"][0]["actions"][0]["canApprove"] is True       # the browser disables Approve
