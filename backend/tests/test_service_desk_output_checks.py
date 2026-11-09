"""85-06 Task 2: the strict output checks every desk answer must pass (D-19, DESK-03, T-85-19, T-85-20).

Value: protects=a model reply is used only when it cites an article the desk gave it, stays short and plain
and carries no link, address, phone number, command or long number that its cited articles do not contain;
fails_when=a reply with a foreign link, address, phone, command or number, with markup, or with a citation
it was not given, passes, a reply that quotes its cited article is refused, or a reply field such as
"confidence" or "close_ticket" is read; no_claim=whether an answer is helpful or correct (a person reads
drafts, and the requester can say it did not help) and the model's wording.

output_checks.jsonl: every reply and article is invented for this phase. expect is "pass" or the first
failing rule.
"""
import ast
import json
from pathlib import Path

import pytest

from service_desk import ANSWER_MAX_CHARS, ANSWER_MAX_LINES, HANDOFF_REASONS, checks

FIXTURE = Path(__file__).parent / "fixtures" / "service_desk" / "output_checks.jsonl"


def _cases():
    rows = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [row for row in rows if "_comment" not in row]


def _verdict(case):
    reply = case["reply"] if isinstance(case["reply"], str) else json.dumps(case["reply"])
    texts = case["cited_texts"]
    if texts is not None:
        texts = {int(number): text for number, text in texts.items()}
    return checks.verdict(reply, case["given"], texts)


CASES = _cases()


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_every_case_gives_its_expected_verdict(case):
    expected = None if case["expect"] == "pass" else case["expect"]
    assert _verdict(case) == expected, case["reply"]


def test_the_set_is_big_enough_and_every_rule_appears_at_least_twice():
    assert len(CASES) >= 30
    for rule in checks.RULES:
        assert sum(1 for c in CASES if c["expect"] == rule) >= 2, rule
    assert sum(1 for c in CASES if c["expect"] == "pass") >= 8
    assert {c["expect"] for c in CASES} <= set(checks.RULES) | {"pass"}


def test_the_rules_are_the_eleven_of_the_plan_plus_the_empty_answer():
    assert set(checks.RULES) == {
        "unparseable", "empty_answer", "no_citation", "unknown_citation", "too_long", "too_many_lines", "html",
        "foreign_link", "foreign_email", "foreign_phone", "foreign_command", "foreign_number"}


def test_every_failing_rule_hands_the_ticket_over_as_output_check_failed():
    assert checks.HANDOFF_REASON == "output_check_failed" and checks.HANDOFF_REASON in HANDOFF_REASONS
    for rule in checks.RULES:
        assert checks.handoff_reason(rule) == "output_check_failed"
    with pytest.raises(ValueError):
        checks.handoff_reason("a_rule_nobody_wrote")


def test_the_limits_are_the_desk_constants():
    assert checks.check(checks.Reply(answer="a" * ANSWER_MAX_CHARS, cited=[1]), [1]) is None
    assert checks.check(checks.Reply(answer="a" * (ANSWER_MAX_CHARS + 1), cited=[1]), [1]) == "too_long"
    lines = "\n".join("Wait." for _ in range(ANSWER_MAX_LINES))
    assert checks.check(checks.Reply(answer=lines, cited=[1]), [1]) is None
    assert checks.check(checks.Reply(answer=lines + "\nWait.", cited=[1]), [1]) == "too_many_lines"
    blank = "Wait.\n\n\n\nWait."
    assert checks.check(checks.Reply(answer=blank, cited=[1]), [1]) is None, "blank lines are not counted"


def test_a_link_only_in_a_not_cited_article_still_fails():
    texts = {1: "Open the sign-in page.", 2: "The portal is https://portal.example.org/start."}
    reply = checks.Reply(answer="Open https://portal.example.org/start.", cited=[1])
    assert checks.check(reply, [1, 2], texts) == "foreign_link"
    assert checks.check(checks.Reply(answer="Open https://portal.example.org/start.", cited=[1, 2]),
                        [1, 2], texts) is None


def test_a_link_that_only_starts_like_an_article_link_does_not_pass():
    texts = {1: "Open https://help.example.com/reset-password-page for help."}
    for answer in ("Open https://help.example.com/reset-password-pag", "Open https://help.example.com/reset",
                   "Open https://help.example.com/reset-password-page?next=https://evil.test"):
        assert checks.check(checks.Reply(answer=answer, cited=[1]), [1], texts) == "foreign_link", answer
    assert checks.check(checks.Reply(answer="Open https://help.example.com/reset-password-page.", cited=[1]),
                        [1], texts) is None


def test_a_number_inside_a_longer_number_of_the_article_does_not_pass():
    texts = {1: "The code is 548211."}
    assert checks.check(checks.Reply(answer="The code is 4821.", cited=[1]), [1], texts) == "foreign_number"
    assert checks.check(checks.Reply(answer="The code is 548211.", cited=[1]), [1], texts) is None


def test_matching_ignores_case_width_and_spacing():
    texts = {1: "Run  IPCONFIG   /FlushDNS  and wait."}
    assert checks.check(checks.Reply(answer="Run `ipconfig /flushdns` and wait.", cited=[1]), [1], texts) is None


def test_extra_reply_keys_are_ignored_and_never_read():
    reply = checks.parse_reply(json.dumps({"answer": "Wait a minute.", "cited": [1], "confidence": 1.0,
                                           "close_ticket": True, "status": "resolved", "targets": ["a1"]}))
    assert reply is not None and checks.check(reply, [1]) is None
    assert not any(hasattr(reply, name) for name in ("confidence", "close_ticket", "status", "targets"))
    source = (Path(__file__).parent.parent / "service_desk" / "checks.py").read_text(encoding="utf-8")
    for name in ("confidence", "close_ticket"):
        assert name not in source, name


def test_parse_reply_refuses_anything_but_an_answer_with_whole_numbers():
    assert checks.parse_reply("") is None
    assert checks.parse_reply("null") is None
    assert checks.parse_reply('{"answer": "x", "cited": [1.5]}') is None
    assert checks.parse_reply('{"answer": "x", "cited": [true]}') is None
    assert checks.parse_reply('{"answer": "x", "cited": [1]}') is not None


def test_checks_are_pure_and_import_no_model_no_settings_no_network():
    tree = ast.parse((Path(__file__).parent.parent / "service_desk" / "checks.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(("." * node.level) + (node.module or ""))
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    # ".sanitize" is the desk's one fold (85-24): stdlib only, no model, settings or network.
    allowed = {"json", "re", "html", "unicodedata", "typing", "pydantic", ".", ".sanitize"}
    assert imported <= allowed, imported - allowed
    assert checks.check(checks.Reply(answer="Wait.", cited=[1]), [1]) is None


def test_hostile_input_is_checked_in_linear_time():
    import time
    hostile = ("a." * 3000) + "https://" + ("a" * 5000) + " " + ("1 " * 3000) + ("<" * 3000) + ("&" * 3000)
    started = time.perf_counter()
    reply = checks.Reply(answer=hostile[:ANSWER_MAX_CHARS], cited=[1])
    for _ in range(20):
        checks.check(reply, [1], {1: hostile})
    assert time.perf_counter() - started < 2.0
