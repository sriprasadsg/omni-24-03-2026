"""Staged patch rollouts, plan 84-02: every server sentence of a rollout lives in one tested module.

Value: protects=PTCH-04 (and PROH-84-02): the assurance line and the halt block read exactly what the UI-SPEC
says, every template fills from a sample value set, counts are never "1 computers", and no text claims a revert:
every Not reverted sentence ends with "The patch is still installed."; fails_when=a template holds a token no
caller supplies, a string breaks a banned-term rule or holds HTML, or a Not reverted text loses its last
sentence; no_claim=the screens that show these sentences (84-09 and later) or the copy gate's directory walk
(test_autonomous_ops_copy.py).
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops.rollout import messages as m
from tests.test_autonomous_ops_copy import load_rules, violations

SECTIONS = ("RING_DETAIL", "HOST_RESULT", "HEALTH", "FAILURE_RATE", "HALT_REASON", "NOT_REVERTED", "REVERT_SUMMARY",
            "CANARY_OS_GAP", "LEFT_OUT", "OFFLINE_NOW", "PREFLIGHT", "CANNOT_TAKE", "VALIDATION", "CARD", "ACTIVITY",
            "API_DETAIL")
TEXT_NAMES = SECTIONS + ("ASSURANCE", "HALT_SECOND_LINE", "HALT_FIRST_LINE", "STOPPED", "STOPPED_PLATFORM", "SHADOW",
                         "NOT_CHECKED", "SOAK", "LEFT_OUT_MORE", "LEFT_OUT_SHOWING", "NOT_REVERTED_REASON")
TOKEN = re.compile(r"\{([a-z_]+)\}")


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)


def every_text():
    for name in TEXT_NAMES:
        for text in strings(getattr(m, name)):
            yield name, text


# ---------------------------------------------------------------- the fixed lines

def test_the_assurance_line_and_the_halt_second_line_are_verbatim():
    assert m.ASSURANCE == ("A rollout halts on failure; reverts where supported. "
                           "Nothing is installed outside your maintenance window.")
    assert m.HALT_SECOND_LINE == ("A rollout halts on failure; reverts where supported. "
                                  "Rings that already passed keep the patches. Nothing further installs.")
    assert "where supported" in m.ASSURANCE and "where supported" in m.HALT_SECOND_LINE


def test_the_stop_shadow_and_halt_lines_are_verbatim():
    assert m.STOPPED == ("Rollouts are paused while automatic actions are stopped. Nothing new installs or restarts. "
                         "A revert that is already under way still runs.")
    assert "whole platform" in m.STOPPED_PLATFORM and m.STOPPED_PLATFORM.endswith("still runs.")
    assert m.SHADOW.startswith("Shadow mode is on for this organization. A rollout runs as a simulation:")
    assert m.halt_first_line("Pilot", m.fill(m.HALT_REASON["install_denied"])) == "Halted at Pilot: the install was denied."


def test_the_unreachable_and_no_data_sentences_are_verbatim():
    assert m.fill(m.HEALTH["no_data"], signal="the heartbeat after the restart") == (
        "No data for the heartbeat after the restart counts as a failure, so the ring halts.")
    assert m.fill(m.HALT_REASON["no_new_boot"], host="web-1") == (
        "no heartbeat from web-1 within 30 minutes of the restart.")
    assert m.NOT_CHECKED == "{services} can't be checked on {k} of {n} computers until their agent is updated."
    assert m.HEALTH["services_agent_only"] == "Only the agent service is checked."
    assert m.RING_DETAIL["sim_installing"] == "Would install on {computers}."
    assert m.RING_DETAIL["sim_restarting"] == "Would restart {computers}."


# ---------------------------------------------------------------- helpers and templates

def test_every_template_fills_from_a_sample_value_set_without_a_stray_token():
    sample = {}
    for _, text in every_text():
        sample.update({name: f"<{name}>" for name in TOKEN.findall(text)})
    for name, text in every_text():
        filled = m.fill(text, **sample)
        assert TOKEN.search(filled) is None, (name, text)


def test_fill_replaces_only_the_tokens_it_is_given():
    assert m.fill("{a} and {b}", a="x") == "x and {b}"


def test_plural_and_count_agree_with_the_number():
    assert m.plural(1, "computer", "computers") == "1 computer"
    assert m.plural(0, "computer", "computers") == "0 computers"
    assert m.plural(2, "computer", "computers") == "2 computers"
    assert m.count(1, "host", "hosts") == "host" and m.count(3, "host", "hosts") == "hosts"


def test_left_out_has_a_one_and_a_many_form():
    assert m.left_out(1, "Nov") == '1 host is in "Nov" and was left out.'
    assert m.left_out(3, "Nov") == '3 hosts are in "Nov" and were left out.'


def test_offline_now_has_a_one_and_a_many_form():
    assert m.offline_now(1).startswith("1 computer is offline now. It gets")
    assert m.offline_now(4).startswith("4 computers are offline now. They get")


def test_the_canary_os_gap_names_the_group_only_when_there_is_exactly_one():
    assert m.canary_os_gap("Linux", ["Canary"]) == "The canary ring has no Linux host; add one to the Canary group."
    several = m.canary_os_gap("Windows", ["Canary", "Early"])
    assert several == "The canary ring has no Windows host; add one to a group in the canary ring."
    assert m.canary_os_gap("Linux", []) == "The canary ring has no Linux host; add one to a group in the canary ring."


def test_a_revert_that_could_not_happen_says_so_in_one_and_many_forms():
    reason = m.NOT_REVERTED_REASON["not_uninstallable"]
    one = m.forms(1, m.REVERT_SUMMARY["could_not"], computers=m.plural(1, "computer", "computers"), reason=reason)
    many = m.forms(3, m.REVERT_SUMMARY["could_not"], computers=m.plural(3, "computer", "computers"), reason=reason)
    assert one.startswith("1 computer could not be reverted") and one.endswith("still installed on it.")
    assert many.startswith("3 computers could not be reverted") and many.endswith("still installed on them.")


# ---------------------------------------------------------------- no sentence claims a revert (PROH-84-02)

def test_every_not_reverted_text_ends_with_the_patch_is_still_installed():
    assert set(m.NOT_REVERTED) == {"not_uninstallable", "version_not_offered", "agent_unsupported", "no_answer",
                                    "agent_failed"}
    for code, text in m.NOT_REVERTED.items():
        assert text.startswith("Not reverted: "), code
        assert text.endswith("The patch is still installed."), code
    assert m.not_reverted("not_uninstallable") == (
        "Not reverted: Windows doesn't allow this update to be uninstalled. The patch is still installed.")
    assert m.not_reverted("no_answer") == "Not reverted: the computer did not answer. The patch is still installed."
    with pytest.raises(KeyError):
        m.not_reverted("some_new_reason")


def test_every_could_not_revert_sentence_says_the_patch_is_still_installed():
    for text in strings(m.REVERT_SUMMARY["could_not"]):
        assert "The patch is still installed" in text, text


# ---------------------------------------------------------------- the keys later plans read

def test_the_halt_reasons_cover_every_code_the_controller_can_give():
    assert set(m.HALT_REASON) == {"failure_share", "canary_failed", "host_failed", "no_data:install",
                                  "no_data:inventory", "no_data:heartbeat", "no_data:services", "no_new_boot",
                                  "install_denied", "restart_denied", "approval_expired"}


def test_the_blockers_and_computer_reasons_have_their_keys():
    assert set(m.CANNOT_TAKE) == {"agent_too_old", "capability_off", "unsupported_os", "busy", "never_touch"}
    assert m.PREFLIGHT["autonomy_off"] == "Autonomous Ops is off for this organization, so a rollout can't run."
    assert m.PREFLIGHT["stopped"] == "Paused while automatic actions are stopped."
    assert m.PREFLIGHT["cap"] == "A rollout can reach at most 500 computers. Pick fewer patches or split your rings."
    assert m.PREFLIGHT["nothing_pending"] == "Nothing is waiting to be installed."
    assert m.PREFLIGHT["window_blocker"] == "Add a maintenance window first."
    for text in m.CANNOT_TAKE.values():
        assert text.endswith(".") and text.count(". ") == 0


def test_the_api_details_cover_the_refusals_the_routes_return():
    assert set(m.API_DETAIL) == {"already_in_rollout", "platform_tenant", "not_halted", "revert_running",
                                 "cancel_requested", "reason_required", "rollout_not_found", "rings_unreadable",
                                 "suggestion_not_found"}


def test_no_dict_key_in_the_module_is_the_autonomy_stamp_key():
    # The structural gate test treats a dict key named "autonomy" as a stamp write, so only the gate may hold one.
    import ast
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "autonomous_ops", "rollout",
                           "messages.py"), encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    keys = [k.value for node in ast.walk(tree) if isinstance(node, ast.Dict) for k in node.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)]
    assert "autonomy" not in keys and not any(k.startswith("autonomy.") for k in keys)
    assert m.PREFLIGHT["titles"]["autonomous_ops"] == "Autonomous Ops"


def test_the_validation_sentences_are_the_ui_spec_ones():
    assert m.VALIDATION["name"] == "Enter a name for this rollout."
    assert m.VALIDATION["canary_group"] == "Pick at least one group for the Canary ring."
    assert m.VALIDATION["soak_hours"] == "Enter hours between 1 and 168."
    assert m.VALIDATION["fail_pct"] == "Enter a percentage between 1 and 50."
    assert m.VALIDATION["min_sample"] == "Enter a number between 1 and 100."


# ---------------------------------------------------------------- copy rules

def test_no_template_matches_a_banned_term_rule():
    rules = load_rules()["rules"]
    for name, text in every_text():
        assert violations(text, rules) == [], (name, text)


def test_no_template_holds_html_or_an_emoji():
    for name, text in every_text():
        assert "<" not in text and ">" not in text, (name, text)
        assert all(ord(ch) < 0x2000 for ch in text), (name, text)


def test_the_module_file_passes_the_rules_and_names_rollback_patches_only_as_an_identifier():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "autonomous_ops", "rollout",
                        "messages.py")
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    assert violations(source, load_rules()["rules"]) == []
    assert source.count("\n") < 500
    assert "reverts where supported" in source and "The patch is still installed" in source
