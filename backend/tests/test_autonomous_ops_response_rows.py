"""ACTV-02, RESP-02, RESP-03, RESP-08: what each Phase 83 Activity row says and which rows may be undone.

``response_views.row_extras`` is pure, so the copy and the canUndo rules are checked on seeded rows
without a database; the last tests go through the real Activity route (private mongod) to prove the
viewer rule: only a person with control:autonomous_ops in an interactive session is offered Undo.

Value: protects=an Undo button is offered only where the server allows the undo, and a block, a
quarantine and a two-source reason read the same words the UI contract fixes; fails_when=Undo is
offered to Platform Support, an API key, a simulated, expired or multi-step row, or a sentence claims
two sources from one; no_claim=the screen (83-18/83-19) and a real browser.
"""
import copy
from datetime import datetime, timedelta, timezone

from autonomous_ops import response_views, views
from tests._autonomous_ops_http import _env, api  # noqa: F401  (fixtures)
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_agent

NOW = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
KEYS = {"canUndo", "undoHint", "incidentId", "blockedUntil", "suggestion", "ticketId", "ticketNumber"}   # 85-04 adds the desk ticket link


def block_row(**over):
    row = {
        "id": "AO-block", "tenantId": "t1", "kind": "security", "origin": "sweep", "dispatcher": "security_response",
        "command": "block_ip", "actions": ["block_ip"], "targets": ["a1"], "target": "203.0.113.7",
        "params": {"ip_address": "203.0.113.7", "ttl_seconds": 86400}, "steps": [{"command": "block_ip"}],
        "state": "verified", "shadow": False, "instructionIds": ["task-1"],
        "reason": {"ruleId": "sweep:block_ip", "inputs": {"origins": ["native", "feed:urlhaus"], "twoSignal": True}},
        "reasonCode": "class_auto", "reasonText": "stored",
        "blockedFrom": NOW - timedelta(hours=1), "blockedUntil": NOW + timedelta(hours=23),
        "undo": {"available": True, "action": "unblock_ip", "params": {}, "undoneAt": None, "undoneBy": None},
        "createdAt": NOW - timedelta(hours=1), "updatedAt": NOW - timedelta(hours=1),
    }
    row.update(over)
    return row


def extras(row, *, can_act=True, now=NOW, host="web-01"):
    return response_views.row_extras(row, host=host, can_act=can_act, now=now)


# ---------------------------------------------------------------- blocks (RESP-02)

def test_an_active_verified_block_can_be_undone_and_says_how_long_it_lasts():
    out = extras(block_row())
    assert KEYS <= set(out)
    assert out["canUndo"] is True
    assert out["undoHint"] == "Removes the block on 203.0.113.7."
    assert out["resultText"] == "Blocked for 24 hours, until {until}. Verified: the firewall rule is in place."
    assert out["blockedUntil"] == (NOW + timedelta(hours=23)).isoformat()
    assert out["reasonText"] == "Two sources agree: agent verdict and URLhaus."
    assert out["incidentId"] is None and out["suggestion"] is None
    assert "state" not in out and "bucket" not in out and "classLine" not in out


def test_a_block_whose_time_ran_out_loses_undo_and_keeps_its_state():
    row = block_row(blockedUntil=NOW - timedelta(minutes=1))
    before = copy.deepcopy(row)
    out = extras(row)
    assert out["canUndo"] is False and out["undoHint"] is None
    assert out["resultText"] == "Block removed automatically at {at} when its time ran out."
    assert row == before                      # no state, chip or ledger change
    assert "state" not in out and "bucket" not in out


def test_a_multi_day_block_reads_in_days_and_a_failed_check_reads_as_failed():
    row = block_row(params={"ip_address": "203.0.113.7", "ttl_seconds": 3 * 86400},
                    blockedFrom=NOW, blockedUntil=NOW + timedelta(days=3))
    assert extras(row)["resultText"].startswith("Blocked for 3 days, until {until}.")
    failed = block_row(state="failed", reasonCode="verify_failed", blockedUntil=None, blockedFrom=None)
    out = extras(failed)
    assert out["resultText"] == "The host did not confirm the firewall rule, so this is marked failed."
    assert out["canUndo"] is False and out["blockedUntil"] is None


def test_an_executed_block_that_is_not_yet_verified_does_not_claim_verification():
    out = extras(block_row(state="executed"))
    assert "resultText" not in out
    assert out["canUndo"] is True


# ---------------------------------------------------------------- who may undo (ACTV-02)

def test_the_viewer_without_the_right_never_sees_undo():
    out = extras(block_row(), can_act=False)
    assert out["canUndo"] is False and out["undoHint"] is None


def test_rows_that_cannot_be_undone_get_false_and_no_hint():
    undoable = dict(command="block_ip")
    cases = {
        "shadow": block_row(state="shadow", shadow=True),
        "simulated flag": block_row(shadow=True),
        "restart": block_row(command="restart_service", actions=["restart_service"],
                             params={"service": "nginx"}, undo={"available": False}),
        "kill": block_row(command="kill_process", actions=["kill_process"], undo={"available": False}),
        "failed": block_row(state="failed"),
        "pending": block_row(state="awaiting_approval"),
        "undone": block_row(state="undone"),
        "two steps": block_row(steps=[{"command": "block_ip"}, {"command": "quarantine_file"}]),
        "no target": block_row(targets=[]),
        "control": {"id": "AO-c", "kind": "control", "state": "recorded", "controlEvent": "stop_pressed",
                    "reason": {"ruleId": "control:stop_pressed", "inputs": {}}},
    }
    for name, row in cases.items():
        out = extras(row)
        assert out["canUndo"] is False, name
        assert out["undoHint"] is None, name
    assert undoable


def test_quarantine_and_isolation_rows_offer_their_own_undo_hint():
    quarantine = block_row(command="quarantine_file", actions=["quarantine_file"], target="C:\\Users\\Public\\x.exe",
                           params={"path": "C:\\Users\\Public\\x.exe"}, blockedUntil=None, blockedFrom=None,
                           undo={"available": True, "action": "unquarantine_file"})
    out = extras(quarantine)
    assert out["canUndo"] is True and out["undoHint"] == "Restores C:\\Users\\Public\\x.exe to where it was."
    assert out["resultText"] == ("Moved C:\\Users\\Public\\x.exe to quarantine. It was not deleted. Verified: "
                                 "the file is in quarantine.")
    isolate = block_row(command="isolate_host", actions=["isolate_host"], params={}, blockedUntil=None,
                        blockedFrom=None, target="web-01", undo={"available": True, "action": "restore_host"})
    out = extras(isolate)
    assert out["canUndo"] is True and out["undoHint"] == "Restores the network connection."
    assert out["resultText"] == "web-01 is isolated. The connection to the platform stays open."


def test_a_quarantine_whose_process_still_runs_says_so_in_its_result():
    row = block_row(command="quarantine_file", actions=["quarantine_file"], params={"path": "/tmp/x"}, target="/tmp/x",
                    blockedUntil=None, blockedFrom=None,
                    result={"still_running": [{"pid": 4242, "name": "evil.exe", "start_time": 1761900000}]})
    text = extras(row)["resultText"]
    assert text.startswith("Moved /tmp/x to quarantine.") and text.endswith("The process is still running. See Needs your decision.")


def test_a_restart_row_and_an_auto_reverted_isolation_read_from_their_inputs():
    restart = block_row(command="restart_service", actions=["restart_service"], params={"service": "nginx"},
                        undo={"available": False}, blockedUntil=None, blockedFrom=None, result={"healthy_after": 30},
                        reason={"ruleId": "sweep:restart_service", "inputs": {"service": "nginx", "attempt": 2}})
    out = extras(restart)
    assert out["reasonText"] == "nginx stopped and is on your watched list."
    assert out["resultText"] == "Restarted nginx. Healthy again after 30 s. Restart 2 of 3 this hour."
    assert out["canUndo"] is False
    over = copy.deepcopy(restart)
    over["reason"]["inputs"]["overBudget"] = True
    assert extras(over)["reasonText"] == "Restarted nginx 3 times in the last hour. Further restarts need your approval."
    reverted = block_row(command="isolate_host", actions=["isolate_host"], state="undone", reasonCode="auto_reverted",
                         blockedUntil=None, blockedFrom=None)
    assert extras(reverted)["resultText"] == ("Returned to the network automatically after 4 hours. "
                                             "Nobody confirmed the isolation.")


# ---------------------------------------------------------------- incident id

def test_a_pending_row_carries_its_incident_id():
    row = block_row(state="awaiting_approval", reason={"ruleId": "sweep:x", "inputs": {"incidentId": "INC-7"}})
    assert extras(row)["incidentId"] == "INC-7"
    assert extras(block_row())["incidentId"] is None


# ---------------------------------------------------------------- reasons (RESP-08)

def test_one_origin_with_the_rule_off_says_so_and_one_origin_with_the_rule_on_claims_nothing():
    off = block_row(reason={"ruleId": "sweep:block_ip", "inputs": {"origins": ["native"], "twoSignal": False}})
    assert extras(off)["reasonText"] == ("This organization's two-source rule is off, so one source was enough: "
                                         "agent verdict.")
    on = block_row(reason={"ruleId": "sweep:block_ip", "inputs": {"origins": ["native"], "twoSignal": True}})
    assert "reasonText" not in extras(on)


def test_two_entries_from_one_origin_never_read_as_two_sources_and_an_unknown_origin_is_never_shown():
    same = block_row(reason={"ruleId": "sweep:block_ip", "inputs": {"origins": ["native", "native"], "twoSignal": True}})
    assert "reasonText" not in extras(same)
    odd = block_row(reason={"ruleId": "sweep:block_ip", "inputs": {"origins": ["native", "feed:evil"], "twoSignal": True}})
    out = extras(odd)
    assert "reasonText" not in out and "feed:evil" not in str(out)


def test_a_row_with_no_inputs_keeps_its_stored_wording():
    row = block_row(dispatcher="instruction", reason={"ruleId": "playbook:contain-ip", "inputs": {}})
    out = extras(row, can_act=False)
    assert set(out) == KEYS
    assert out["canUndo"] is False and out["suggestion"] is None


def test_an_undone_earlier_row_says_when_and_that_it_is_not_repeated():
    row = block_row(state="refused", reasonCode="suppressed_by_undo", blockedUntil=None, blockedFrom=None,
                    reason={"ruleId": "sweep:block_ip", "inputs": {"origins": ["native"], "twoSignal": False,
                                                                   "undoneAt": "2026-10-30T09:00:00+00:00"}})
    out = extras(row)
    assert out["reasonText"] == "You undid this action on Oct 30. It isn't repeated for 24 hours."
    assert out["resultText"] == "Not repeated."


# ---------------------------------------------------------------- suggestions (D-03, D-07, D-08, D-25)

def suggestion_row(command, suggestion, **over):
    row = block_row(command=command, actions=[command], state="suggested", blockedUntil=None, blockedFrom=None,
                    reason={"ruleId": "sweep:suggest", "inputs": {"suggestionOnly": True, "suggestion": suggestion,
                                                                 "origins": ["native"]}},
                    undo={"available": False})
    row.update(over)
    return row


def test_a_one_source_suggestion_is_labelled_and_worded_from_the_table():
    out = extras(suggestion_row("block_ip", {"kind": "single_signal"}))
    assert out["actionLabel"] == "Suggested: block IP address"
    assert out["classLine"] == "Suggestion only"
    assert out["reasonText"] == "Only one source flagged this: agent verdict. A second, different source has to agree."
    assert out["resultText"].startswith("Nothing was done. If a second source agrees within 24 hours")
    assert out["suggestion"] == {"kind": "single_signal", "count": 1, "items": [], "openView": None}
    assert out["canUndo"] is False
    quarantine = extras(suggestion_row("quarantine_file", {"kind": "single_signal"}))
    assert quarantine["actionLabel"] == "Suggested: quarantine file"


def test_a_vulnerability_suggestion_is_grouped_capped_and_links_to_patching():
    items = [{"cve": f"CVE-2026-{1000 + i}", "package": f"pkg{i}", "extra": "dropped"} for i in range(15)]
    out = extras(suggestion_row("upgrade_software", {"kind": "vulnerability", "count": 25, "severity": "Critical",
                                                     "items": items}))
    assert out["actionLabel"] == "Suggested: patch vulnerabilities" and out["classLine"] == "Suggestion only"
    assert out["reasonText"] == "25 known vulnerabilities reported by web-01. Highest severity: Critical."
    assert out["resultText"] == "No action was taken. Patching is where you apply fixes."
    sugg = out["suggestion"]
    assert sugg["kind"] == "vulnerability" and sugg["count"] == 25 and sugg["openView"] == "patchManagement"
    assert len(sugg["items"]) == 10 and sugg["items"][0] == {"cve": "CVE-2026-1000", "package": "pkg0"}
    one = extras(suggestion_row("upgrade_software", {"kind": "vulnerability", "count": 1, "severity": "High",
                                                     "items": items[:1]}))
    assert one["reasonText"] == "1 known vulnerability reported by web-01. Highest severity: High."


def test_a_file_change_suggestion_links_to_file_integrity():
    out = extras(suggestion_row("restore_file", {"kind": "file_change", "count": 3,
                                                 "items": [{"path": "/etc/passwd"}, {"path": "/etc/hosts"}]}))
    assert out["actionLabel"] == "Suggested: review file changes"
    assert out["reasonText"] == "3 files changed on web-01 since the last baseline."
    assert out["resultText"] == "No action was taken. Check whether these changes were expected."
    assert out["suggestion"] == {"kind": "file_change", "count": 3, "openView": "fimMonitoring",
                                 "items": [{"path": "/etc/passwd"}, {"path": "/etc/hosts"}]}


def test_a_correlation_suggestion_names_its_rule_and_a_bad_suggestion_is_ignored():
    out = extras(suggestion_row("isolate_host", {"kind": "correlation", "rule": "lateral-movement"}))
    assert out["actionLabel"] == "Suggested: isolate host"
    assert out["reasonText"] == "A correlation rule asked for this: lateral-movement."
    assert out["resultText"] == "Nothing was done. Correlation rules only suggest actions."
    bad = extras(suggestion_row("block_ip", {"kind": "no_such_kind"}))
    assert bad["suggestion"] is None and "actionLabel" not in bad
    junk = extras(suggestion_row("block_ip", "not a dict"))
    assert junk["suggestion"] is None


def test_server_copy_holds_no_markup_even_for_hostile_item_text():
    out = extras(suggestion_row("restore_file", {"kind": "file_change", "count": 1,
                                                 "items": [{"path": "<script>alert(1)</script>" + "x" * 900}]}))
    path = out["suggestion"]["items"][0]["path"]
    assert len(path) <= 300 and isinstance(path, str)        # plain text; the browser renders it as text


# ---------------------------------------------------------------- the real route

async def _insert(db, **over):
    row = block_row(blockedFrom=datetime.now(timezone.utc), blockedUntil=datetime.now(timezone.utc) + timedelta(hours=20),
                    createdAt=datetime.now(timezone.utc), updatedAt=datetime.now(timezone.utc))
    row.update(over)
    await db.autonomy_actions.insert_one(row)


async def test_the_activity_route_offers_undo_only_to_a_person_who_may_use_it(api):
    await seed_agent(api.db, "t1", "a1", hostname="web-01")
    await _insert(api.db)
    path = "/api/autonomous-ops/actions?bucket=all"
    expected = {"tenant_admin": True, "security_analyst": True, "analyst": False}
    for role, can in expected.items():
        body = (await api.call("GET", path, role=role)).json()
        item = body["items"][0]
        assert item["canUndo"] is can, role
        assert item["undoHint"] == ("Removes the block on 203.0.113.7." if can else None), role
        assert item["host"] == "web-01" and item["blockedUntil"]
        assert item["resultText"].startswith("Blocked for 24 hours, until {until}.")
    support = (await api.call("GET", path + "&tenantId=t1", role="platform_support")).json()["items"][0]
    assert support["canUndo"] is False and support["undoHint"] is None
    owner = (await api.call("GET", path + "&tenantId=t1", role="super_admin")).json()["items"][0]
    assert owner["canUndo"] is True
    key = (await api.call("GET", path, role="tenant_admin", auth="api_key")).json()["items"][0]
    assert key["canUndo"] is False and key["undoHint"] is None


async def test_an_old_row_presents_as_before_with_the_new_keys_empty(api):
    await seed_agent(api.db, "t1", "a1", hostname="web-01")
    old = block_row(id="AO-old", dispatcher="instruction", state="executed", origin="playbook",
                    reason={"ruleId": "playbook:contain-ip", "inputs": {}}, reasonCode="class_auto",
                    reasonText="This action is allowed to run on its own within the limits you set.",
                    blockedFrom=None, blockedUntil=None, steps=None)
    old.pop("steps")
    await api.db.autonomy_actions.insert_one(old)
    item = (await api.call("GET", "/api/autonomous-ops/actions", role="tenant_admin")).json()["items"][0]
    assert item["resultText"] == "Done." and item["actionLabel"] == "Block IP address"
    assert item["reasonText"] == "This action is allowed to run on its own within the limits you set."
    assert item["incidentId"] is None and item["blockedUntil"] is None and item["suggestion"] is None
    assert item["classLine"] == "Automatic"
    assert views.present_row(old, viewer_is_platform_staff=False)["canUndo"] is False


async def test_a_block_past_its_time_reads_as_removed_on_the_route_without_changing_state(api):
    await seed_agent(api.db, "t1", "a1", hostname="web-01")
    await _insert(api.db, blockedUntil=datetime.now(timezone.utc) - timedelta(minutes=5))
    item = (await api.call("GET", "/api/autonomous-ops/actions", role="tenant_admin")).json()["items"][0]
    assert item["state"] == "verified" and item["bucket"] == "done"
    assert item["canUndo"] is False
    assert item["resultText"] == "Block removed automatically at {at} when its time ran out."
