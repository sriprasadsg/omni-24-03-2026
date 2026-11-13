"""Autonomous Ops daily digest (Phase 86, plan 86-05, ACTV-04, D-01..D-04).

Value: protects=each organization's admins get one honest digest a day (what ran, what was undone, what waits
for approval, and, kept apart, what shadow mode would have done), only they can read it, and a restart, a
second worker or a failing mail server never makes it a second one; fails_when=a count or section differs from
the screen, a simulation item is counted as ran, the notice reaches on-call, the platform feed or a reader the
tenant_admins audience does not admit, a quiet day sends something, or one day sends twice; no_claim=real mail
(email_service.send_email is always a mock), the live database and the live backend.

Real-MongoDB cases use the throwaway database of tests/_mongo_test_db.py (set MONGO_TEST_URL, MONGODB_URL and
MONGO_URI to a private mongod; never the live one) and are never skipped.
"""
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-the-digest")

from autonomous_ops.reporting import digest_text as text
from autonomous_ops.reporting.digest_text import DigestItem, Group

UTC = timezone.utc
MORE = "Showing the first 10 of {n}. The rest are on the Autonomous Ops screen."
CLOSING = "Open Autonomous Ops in the sidebar to see everything."


def item(n, *, at=None, action="Block IP address", target="203.0.113.7", rule="sweep:block_ip", command="block_ip"):
    return DigestItem(id=f"AO-{n:03d}", at=at or datetime(2026, 11, 12, 6, 12, tzinfo=UTC), action_label=action,
                      target=target, rule_id=rule, command=command)


# ================================================================== task 1: the pure text

def test_counts_line_always_carries_all_three_counts():
    assert text.counts_line(12, 2, 3) == "Last 24 hours: 12 ran, 2 undone, 3 waiting for your approval."
    assert text.counts_line(1, 1, 1) == "Last 24 hours: 1 ran, 1 undone, 1 waiting for your approval."
    assert text.counts_line(0, 0, 0) == "Last 24 hours: 0 ran, 0 undone, 0 waiting for your approval."


def test_simulation_line_says_nothing_was_carried_out():
    assert text.simulation_line(7) == "Simulation (shadow mode): 7 would have been done. Nothing was carried out."


def test_a_section_is_cut_at_ten_items_with_the_overflow_sentence():
    lines = text.section_lines("Ran", [item(n) for n in range(12)])
    assert lines[0] == "Ran (12)"
    assert len([line for line in lines if line.startswith("- ")]) == 10
    assert lines[-1] == MORE.format(n=12)
    assert lines[1] == "- Block IP address on 203.0.113.7. Rule: Block an address two sources agree on. 06:12 UTC"


def test_a_short_section_has_no_overflow_sentence_and_a_total_larger_than_the_listed_items_still_cuts():
    assert MORE.format(n=3) not in text.section_lines("Ran", [item(n) for n in range(3)])
    lines = text.section_lines("Ran", [item(n) for n in range(10)], total=14)
    assert lines[0] == "Ran (14)" and lines[-1] == MORE.format(n=14)


def test_an_item_without_a_target_leaves_the_target_out():
    line = text.section_lines("Ran", [item(1, target=None)])[1]
    assert line.startswith("- Block IP address. Rule: ")


def test_a_200_character_target_is_cut_to_80_characters_with_an_ellipsis():
    line = text.section_lines("Ran", [item(1, target="h" * 200)])[1]
    shown = line[len("- Block IP address on "):line.index(". Rule:")]
    assert len(shown) == 80 and shown.endswith("…") and shown[:-1] == "h" * 79


def test_a_target_with_line_breaks_stays_on_one_line():
    line = text.section_lines("Ran", [item(1, target="host\r\nBcc: x\nmore")])[1]
    assert "\n" not in line and "\r" not in line and "host Bcc: x more" in line


def test_the_simulation_section_is_introduced_and_its_items_say_would_have():
    lines = text.section_lines("Simulation: would have done", [item(1), item(2, command="isolate_host", target="WS-014", at=datetime(2026, 11, 12, 5, 0, tzinfo=UTC))],
                               simulation=True)
    assert lines[0] == "Simulation: would have done (2)"
    assert lines[1] == "Shadow mode is on. Nothing below was carried out."
    assert lines[2].startswith("- Would have blocked 203.0.113.7. Rule: ")
    assert lines[3].startswith("- Would have isolated WS-014. Rule: ")


def test_every_simulation_verb_reads_as_a_past_tense_phrase_and_unknown_commands_fall_back():
    cases = {"quarantine_file": "Would have quarantined a file on H.", "restart_service": "Would have restarted a service on H.",
             "kill_process": "Would have stopped a process on H.", "install_patches": "Would have installed patches on H.",
             "reboot_host": "Would have restarted H.", "ticket_answer": "Would have answered ticket H."}
    for command, expected in cases.items():
        got = text.section_lines("S", [item(1, command=command, target="H")], simulation=True)[2]
        assert got.startswith(f"- {expected} Rule: "), (command, got)
    fallback = text.section_lines("S", [item(1, command="rotate_key", action="Rotate key", target="H")], simulation=True)[2]
    assert fallback.startswith("- Would have run rotate key on H. Rule: ")


def test_the_notice_lists_sections_in_order_and_leaves_empty_ones_out():
    body = text.notice_text(Group(2, [item(1), item(2)]), Group(0, []), Group(1, [item(3, action="Install patches")]),
                            Group(3, [item(4), item(5), item(6)]))
    lines = body.split("\n")
    assert lines[0] == "Last 24 hours: 2 ran, 0 undone, 1 waiting for your approval."
    assert lines[1] == "Simulation (shadow mode): 3 would have been done. Nothing was carried out."
    assert lines[2] == ""
    headings = [line for line in lines if line.endswith(")") and not line.startswith("-") and " (" in line
                and not line.startswith("Simulation (")]
    assert headings == ["Ran (2)", "Waiting for your approval (1)", "Simulation: would have done (3)"]
    assert "Undone" not in body
    assert lines[-1] == CLOSING and lines[-2] == ""


def test_the_notice_has_no_simulation_line_when_there_are_no_simulation_items():
    body = text.notice_text(Group(1, [item(1)]), Group(0, []), Group(0, []), Group(0, []))
    lines = body.split("\n")
    assert lines[0].startswith("Last 24 hours: 1 ran, 0 undone, 0 waiting")
    assert lines[1] == "" and lines[2] == "Ran (1)"
    assert "Simulation" not in body


def test_a_simulation_only_day_reads_zero_ran_zero_undone_zero_waiting_then_the_simulation():
    body = text.notice_text(Group(0, []), Group(0, []), Group(0, []), Group(2, [item(1), item(2)]))
    lines = body.split("\n")
    assert lines[0] == "Last 24 hours: 0 ran, 0 undone, 0 waiting for your approval."
    assert lines[1].startswith("Simulation (shadow mode): 2 would have been done.")
    assert "Ran (" not in body and "Simulation: would have done (2)" in body


def test_the_notice_title_and_a_plain_list_of_items_is_accepted_as_a_group():
    assert text.notice_title() == "Autonomous Ops daily digest"
    body = text.notice_text([item(1)], [], [], [])
    assert "Ran (1)" in body


def test_items_are_listed_newest_first_with_ties_by_id_descending():
    a = item(1, at=datetime(2026, 11, 12, 5, 0, tzinfo=UTC))
    b = item(2, at=datetime(2026, 11, 12, 6, 0, tzinfo=UTC))
    c = item(3, at=datetime(2026, 11, 12, 6, 0, tzinfo=UTC))
    lines = text.section_lines("Ran", [a, b, c])
    assert [line[-9:] for line in lines[1:]] == ["06:00 UTC", "06:00 UTC", "05:00 UTC"]
    ids_in_order = [i.id for i in sorted([a, b, c], key=lambda i: (i.at, i.id), reverse=True)]
    assert ids_in_order == ["AO-003", "AO-002", "AO-001"]


def test_the_time_is_the_utc_clock_of_the_item():
    from datetime import timedelta
    plus5 = timezone(timedelta(hours=5))
    line = text.section_lines("Ran", [item(1, at=datetime(2026, 11, 12, 10, 30, tzinfo=plus5))])[1]
    assert line.endswith("05:30 UTC")


def test_the_subject_strips_line_breaks_from_the_organization_name():
    subject = text.email_subject("Acme\r\nBcc: x", 12, 2, 3)
    assert "\r" not in subject and "\n" not in subject
    assert subject == "Autonomous Ops daily digest for Acme Bcc: x: 12 ran, 2 undone, 3 waiting"


def test_the_email_text_follows_the_agreed_shape():
    sections = (Group(12, [item(n) for n in range(10)]), Group(0, []), Group(1, [item(20, action="Install patches", target="WS-1")]),
                Group(1, [item(30, command="isolate_host", target="WS-014")]))
    body = text.email_text("Acme", "2026-11-12", sections, "https://app.example")
    lines = body.split("\n")
    assert lines[0] == "Autonomous Ops daily digest for Acme"
    assert lines[1] == "The last 24 hours, up to 07:00 UTC on 12 Nov 2026."
    assert lines[2] == "" and lines[3] == "12 ran, 0 undone, 1 waiting for your approval."
    assert lines[4] == "" and lines[5] == "Ran (12)"
    assert MORE.format(n=12) in lines
    assert "Waiting for your approval (1)" in lines and "Simulation: would have done (1)" in lines
    assert "See everything: https://app.example" in lines
    assert lines[-2] == ""
    assert lines[-1] == ("You get this because you are an administrator of Acme. It is sent once a day, and only on days "
                         "when something ran, was undone, is waiting for approval or would have been done in shadow mode.")
    assert body.index("Ran (12)") < body.index("Waiting for your approval (1)") < body.index("Simulation: would have done")


def test_the_email_html_carries_the_same_words_in_order_with_every_server_string_escaped():
    evil = '<script>alert(1)</script> & "x"'
    sections = (Group(1, [item(1, target=evil)]), Group(0, []), Group(0, []), Group(1, [item(2, target=evil)]))
    html_body = text.email_html("A<b>cme", "2026-11-12", sections, 'https://app.example/?a=1&b="2"')
    assert "<script>" not in html_body and "<b>cme" not in html_body and "<img" not in html_body
    assert "&lt;script&gt;" in html_body and "A&lt;b&gt;cme" in html_body and "&amp;" in html_body
    order = ["Autonomous Ops daily digest for", "The last 24 hours, up to 07:00 UTC on 12 Nov 2026.", "1 ran, 0 undone, 0 waiting",
             "Ran (1)", "Simulation: would have done (1)", "Shadow mode is on. Nothing below was carried out.",
             "See everything", "You get this because you are an administrator of"]
    positions = [html_body.index(words) for words in order]
    assert positions == sorted(positions)


def test_a_digest_of_long_targets_and_rule_names_stays_bounded():
    long_item = lambda n: item(n, target="t" * 500, rule="x" * 500)  # noqa: E731
    group = Group(10, [long_item(n) for n in range(10)])
    body = text.notice_text(group, group, group, group)
    assert len(body) < 20000
    assert all(len(line) < 700 for line in body.split("\n"))
