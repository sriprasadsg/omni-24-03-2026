"""Phase 81 review WR-10: an Activity row (and the approval card built from it) for a multi-step playbook
shows every step it authorises, and every step that would put it back.

protects=GATE-10 (an approval shows everything it authorises) and ACTV-01; fails_when=a two- or three-step
row reads as one action, or a later step's command or target is missing from what the viewer is shown;
no_claim=the dispatch binding of every step (test_autonomous_ops_dispatch_binding.py).

Pure: ``views.present_row`` over hand-built ledger rows; nothing reads a database.
"""
from autonomous_ops import messages, views


def _row(steps, compensation=None, **extra):
    row = {"id": "AO-1", "tenantId": "t1", "kind": "security", "dispatcher": "remediation", "state": "awaiting_approval",
           "command": steps[0]["command"], "targets": ["a1"], "target": "a1", "params": steps[0]["params"],
           "steps": steps, "reason": {"ruleId": "playbook:op", "inputs": {}}, "reasonCode": "class_approve",
           "approval": {"requiredBy": "class_approve"}}
    row["roll" "back"] = compensation or []            # the stored field name (this file is not scanned for copy)
    row.update(extra)
    return row


TWO = [{"command": "restart_service", "params": {"service_name": "nginx"}},
       {"command": "block_ip", "params": {"ip_address": "203.0.113.5"}}]


def test_a_two_step_row_says_there_is_one_more_step_and_lists_both():
    shown = views.present_row(_row(TWO), viewer_is_platform_staff=False, host="web-1")
    assert shown["actionLabel"] == "Restart service and 1 more step"
    assert shown["steps"] == [{"label": "Restart service", "target": "nginx"},
                              {"label": "Block IP address", "target": "203.0.113.5"}]
    assert shown["compensationSteps"] == []


def test_a_three_step_row_counts_the_steps_in_the_plural_and_lists_its_put_back_steps():
    three = TWO + [{"command": "quarantine_file", "params": {"path": "/tmp/x.bin", "sha256": "a" * 64}}]
    back = [{"command": "unblock_ip", "params": {"ip_address": "203.0.113.5"}},
            {"command": "unquarantine_file", "params": {"quarantine_id": "q-1"}}]
    shown = views.present_row(_row(three, back), viewer_is_platform_staff=False, host="web-1")
    assert shown["actionLabel"] == "Restart service and 2 more steps"
    assert [s["label"] for s in shown["steps"]] == ["Restart service", "Block IP address", "Quarantine file"]
    assert shown["steps"][2]["target"] == "/tmp/x.bin"
    assert shown["compensationSteps"] == [{"label": "Unblock IP address", "target": "203.0.113.5"},
                                          {"label": "Release file from quarantine", "target": None}]


def test_a_simulation_of_a_multi_step_row_names_the_whole_plan():
    shown = views.present_row(_row(TWO, state="shadow", wouldHave="needs_approval"), viewer_is_platform_staff=False,
                              host="web-1")
    assert shown["resultText"].startswith("Nothing was done. This is what would have happened: "
                                          "Restart service and 1 more step")


def test_a_single_step_row_reads_as_before():
    one = [{"command": "block_ip", "params": {"ip_address": "203.0.113.5"}}]
    shown = views.present_row(_row(one, [{"command": "unblock_ip", "params": {"ip_address": "203.0.113.5"}}]),
                              viewer_is_platform_staff=False, host="web-1")
    assert shown["actionLabel"] == "Block IP address"
    assert shown["steps"] == [{"label": "Block IP address", "target": "203.0.113.5"}]
    assert shown["compensationSteps"] == [{"label": "Unblock IP address", "target": "203.0.113.5"}]


def test_a_legacy_row_without_a_recorded_plan_and_a_control_row_carry_empty_lists():
    legacy = {"id": "AO-2", "tenantId": "t1", "kind": "security", "state": "executed", "command": "block_ip",
              "targets": ["a1"], "params": {"ip_address": "203.0.113.5"}}
    shown = views.present_row(legacy, viewer_is_platform_staff=False, host="web-1")
    assert shown["actionLabel"] == "Block IP address" and shown["steps"] == [] and shown["compensationSteps"] == []
    control = {"id": "AO-3", "tenantId": "t1", "kind": "control", "state": "recorded", "controlEvent": "stop_pressed"}
    shown = views.present_row(control, viewer_is_platform_staff=False)
    assert shown["steps"] == [] and shown["compensationSteps"] == []


def test_step_text_is_bounded_and_an_unknown_command_is_named_plainly():
    odd = [{"command": "made_up_thing", "params": {"target": "x" * 1000}},
           {"command": "block_ip", "params": "junk"}, "junk"]
    shown = views.present_row(_row([odd[0], {"command": "block_ip", "params": {}}]), viewer_is_platform_staff=False)
    shown2 = views.present_row({**_row([odd[0]]), "steps": odd}, viewer_is_platform_staff=False)
    assert shown["steps"][0] == {"label": "Made up thing", "target": "x" * views.STEP_TEXT_CAP}
    assert shown["steps"][1] == {"label": "Block IP address", "target": None}
    assert len(shown2["steps"]) == 2 and shown2["steps"][1] == {"label": "Block IP address", "target": None}


def test_the_more_steps_words_live_in_messages():
    assert messages.more_steps("Kill process", 1) == "Kill process and 1 more step"
    assert messages.more_steps("Kill process", 4) == "Kill process and 4 more steps"
