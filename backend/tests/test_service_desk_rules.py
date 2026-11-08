"""85-05 Tasks 2 and 3: the fixed rules that send a ticket to a person before the model, and the English check.

Whether a ticket goes to a person is decided from the ticket text and fields, never from the model (PROH-85-03).
Two JSONL fixtures pin the phrase lists and the language heuristic: tests/fixtures/service_desk/
escalation_set.jsonl and language_set.jsonl. Hidden and full-width characters in this file are built with chr().
"""
import ast
import json
import re
import time
import unicodedata
from pathlib import Path

import pytest

from service_desk import HANDOFF_REASONS, rules, sanitize
from service_desk.sanitize import clean_text

FIXTURES = Path(__file__).parent / "fixtures" / "service_desk"
ZWSP = chr(0x200B)


def load(name):
    cases = []
    for line in (FIXTURES / name).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if "_comment" not in row:
            cases.append(row)
    return cases


def verdict(case):
    ticket = {"title": case["title"], "description": case["description"], "type": case["type"],
              "priority": case["priority"], "requester_channel": {"template": case["template"]}}
    cleaned = clean_text(case["title"], 200) + "\n" + clean_text(case["description"], 1500)
    return rules.evaluate(ticket, cleaned, case["words"])


def ticket(title="Printer is jammed", description="", type_="task", priority="medium", template=None, **extra):
    row = {"title": title, "description": description, "type": type_, "priority": priority,
           "requester_channel": {"template": template}}
    row.update(extra)
    return row, clean_text(title, 200) + "\n" + clean_text(description, 1500)


def run(title="Printer is jammed", description="", words=None, **fields):
    row, cleaned = ticket(title, description, **fields)
    return rules.evaluate(row, cleaned, words)


# ---------------------------------------------------------------- the escalation set

def test_the_fixture_header_says_the_cases_are_invented():
    first = json.loads((FIXTURES / "escalation_set.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert "invented" in first["_comment"]
    assert "Phase 85" in first["_comment"]


def test_every_case_in_the_escalation_set_gives_exactly_its_expected_reason():
    wrong = []
    for case in load("escalation_set.jsonl"):
        got = verdict(case)
        if got != case["expect"]:
            wrong.append(f"{case['id']}: expected {case['expect']!r}, got {got!r}")
    assert not wrong, "\n".join(wrong)


def test_the_escalation_set_covers_every_category_in_the_agreed_numbers():
    by = {}
    for case in load("escalation_set.jsonl"):
        by.setdefault(case["expect"], []).append(case)
    wanted = {"security_topic": 8, "billing_topic": 8, "legal_topic": 8, "account_access": 8, "asked_for_person": 15,
              "fulfilment_request": 10, "critical_priority": 5, "type_not_answered": 4, "tenant_word": 10,
              "empty_ticket": 1, None: 20}
    short = {key: len(by.get(key, [])) for key, need in wanted.items() if len(by.get(key, [])) < need}
    assert not short, short
    assert {case["expect"] for case in load("escalation_set.jsonl") if case["expect"]} <= set(HANDOFF_REASONS)


def test_the_set_holds_the_six_self_service_password_phrasings_and_they_stay_answerable():
    how_to = [c for c in load("escalation_set.jsonl") if "password" in (c["title"] + c["description"]).lower()
              and c["expect"] is None]
    assert len(how_to) >= 6
    for case in how_to:
        assert verdict(case) is None, case["id"]


# ---------------------------------------------------------------- D-32: password how-to against account access

@pytest.mark.parametrize("text", [
    "I forgot my password, how do I reset it", "how do I change my password", "reset my password please",
    "forgot password", "where can I change my password", "my password expired, how do I set a new one",
])
def test_a_password_how_to_is_answerable(text):
    assert run(text) is None


@pytest.mark.parametrize("text", [
    "please unlock my account", "I am locked out", "my account is locked", "reset my MFA", "my 2FA is not working",
    "I lost my authenticator", "give me access to the shared drive", "I need admin rights", "change my permissions",
    "my account was hacked", "someone logged in as me", "my account has been compromised", "add me to the finance group",
])
def test_unlock_mfa_access_permission_and_compromise_hand_off_as_account_access(text):
    assert run(text) == "account_access"


# ---------------------------------------------------------------- fixed order and the early rules

def test_the_rules_run_in_the_fixed_order():
    assert run("Phishing invoice, my lawyer, unlock my account, talk to a human, payroll",
               words=["payroll"], priority="critical", type_="security") == "critical_priority"
    assert run("Phishing invoice, my lawyer, unlock my account, talk to a human, payroll",
               words=["payroll"], type_="security") == "security_topic"
    assert run("Phishing invoice, my lawyer, unlock my account, talk to a human, payroll",
               words=["payroll"]) == "security_topic"
    assert run("invoice from my lawyer, unlock my account, talk to a human, payroll", words=["payroll"]) == "billing_topic"
    assert run("my lawyer, unlock my account, talk to a human, payroll", words=["payroll"]) == "legal_topic"
    assert run("unlock my account, talk to a human, payroll", words=["payroll"]) == "account_access"
    assert run("talk to a human, payroll", words=["payroll"]) == "asked_for_person"
    assert run("payroll", words=["payroll"]) == "tenant_word"


def test_the_template_rule_runs_before_the_sensitive_lists_and_after_priority_and_type():
    assert run("install it", template="install_software") == "fulfilment_request"
    assert run("my invoice", template="hardware_request") == "fulfilment_request"
    assert run("hello", template="security_concern") == "security_topic"
    assert run("hello", template="access_request") == "account_access"
    assert run("hello", template="install_software", priority="critical") == "critical_priority"
    assert run("hello", template="install_software", type_="change") == "type_not_answered"
    assert run("my printer", template="report_issue") is None and run("my printer", template="custom") is None


def test_an_unknown_template_falls_through_and_the_legacy_title_prefix_is_used_without_one():
    assert run("Printer is jammed", template="made_up") is None
    assert run("Hardware Request: a mouse") == "fulfilment_request"
    assert run("software install request: zoom") == "fulfilment_request"
    assert run("Access Request: wiki") == "account_access"
    assert run("Security Concern: odd file") == "security_topic"
    assert run("Issue: my printer") is None
    assert run("Hardware Requests are slow, my printer is jammed") is None


def test_priority_critical_only_and_types_outside_the_agreed_set():
    for priority in ("high", "medium", "low", None, ""):
        assert run(priority=priority) is None
    assert run(priority="critical") == "critical_priority"
    for good in ("task", "bug", "incident", "Task", " BUG "):
        assert run(type_=good) is None
    assert run(type_="security") == "security_topic"
    assert run(type_="feature") == "fulfilment_request"
    for odd in ("epic", "change", "", None, 5):
        assert run(type_=odd) == "type_not_answered"


def test_a_ticket_with_nothing_left_after_cleaning_never_reaches_the_model():
    assert run("", "") == "empty_ticket"
    assert run("<script>x()</script>", "<style>a{}</style><b> </b>") == "empty_ticket"
    assert run("", "", priority="critical", type_="security") == "empty_ticket"
    assert rules.evaluate({}, "", None) == "empty_ticket"


# ---------------------------------------------------------------- DESK-03 edge: encoding

def test_hidden_full_width_and_accented_forms_still_match_the_phrase_lists():
    assert run("talk to a hu" + ZWSP + "man") == "asked_for_person"
    assert run("".join(chr(ord(c) + 0xFEE0) if c.isalpha() else c for c in "talk to a human")) == "asked_for_person"
    assert run("Pléase unlöck my account") == "account_access"
    assert run("TALK TO A HUMAN!!!") == "asked_for_person"
    assert run("I can" + chr(0x2019) + "t log in, I" + chr(0x2019) + "m locked out") == "account_access"


def test_a_phrase_must_be_a_whole_word_sequence():
    assert run("There is no issue with the printer") is None             # "sue" is not inside "issue"
    assert run("The courtesy phone is broken") is None                   # "court" is not inside "courtesy"
    assert run("My laptop is on the supervisory network") is None
    assert run("Please add me to") == "account_access"


# ---------------------------------------------------------------- tenant words (T-85-18)

def test_tenant_words_are_whole_word_literals_never_patterns():
    assert run("payrollsystem is slow", words=["payroll"]) is None
    assert run("Payroll is slow", words=["payroll"]) == "tenant_word"
    assert run("screen flickers", words=[".*", "(a+)+$", "[", "\\", "a|b", "^"]) is None
    assert run("the screen a|b flickers", words=["a|b"]) == "tenant_word"
    assert run("screen flickers", words=["", " ", None, 3, ["x"]]) is None
    assert run("screen flickers", words=None) is None


def test_tenant_words_are_capped_and_hostile_ones_run_in_bounded_time():
    many = [f"word{n}" for n in range(500)]
    assert run("word0 is slow", words=many) == "tenant_word"           # the first fifty are used
    assert run("word200 is slow", words=many) is None
    started = time.monotonic()
    assert run("a" * 5000 + "!", words=["(a+)+$", "(a|aa)+$", "a" * 40]) is None
    assert time.monotonic() - started < 2


def test_evaluate_is_deterministic():
    case = {"title": "Talk to a human about my invoice", "description": "", "type": "task", "priority": "low",
            "template": None, "words": []}
    assert {verdict(case) for _ in range(5)} == {"billing_topic"}


def test_ticket_text_is_never_compiled_as_a_pattern():
    """re.compile appears only where a phrase or tenant word is escaped first."""
    tree = ast.parse(Path(rules.__file__).read_text(encoding="utf-8"))
    compiles = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute) and node.func.attr in ("compile", "search", "match", "findall")
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "re"]
    assert len(compiles) == 1
    source = Path(rules.__file__).read_text(encoding="utf-8")
    assert "re.escape" in source
    assert not re.search(r"re\.(search|match|findall|sub|compile)\(\s*(text|cleaned_text|title)\b", source)


def test_the_phrase_lists_are_plain_strings_and_the_password_howto_is_in_none_of_them():
    for name in ("SECURITY", "BILLING", "LEGAL", "ACCOUNT_ACCESS", "ASK_FOR_PERSON"):
        phrases = getattr(rules, name)
        assert len(phrases) >= 10 and all(isinstance(p, str) and p.strip() for p in phrases), name
    everything = {sanitize.normalize_for_match(p) for name in
                  ("SECURITY", "BILLING", "LEGAL", "ACCOUNT_ACCESS", "ASK_FOR_PERSON") for p in getattr(rules, name)}
    for how_to in ("forgot my password", "reset my password", "change my password", "forgot password", "password"):
        assert how_to not in everything


# ---------------------------------------------------------------- English only (Task 3, D-20, D-35)

def test_every_case_in_the_language_set_gives_its_expected_answer():
    wrong = []
    for case in load("language_set.jsonl"):
        got = "english" if rules.is_english(case["text"]) else "not_english"
        if got != case["expect"]:
            wrong.append(f"{case['id']}: {case['text']!r} expected {case['expect']}, got {got}")
    assert not wrong, "\n".join(wrong)


def test_the_language_set_is_big_enough_and_says_its_cases_are_invented():
    cases = load("language_set.jsonl")
    assert sum(c["expect"] == "english" for c in cases) >= 20
    assert sum(c["expect"] == "not_english" for c in cases) >= 20
    header = json.loads((FIXTURES / "language_set.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert "invented" in header["_comment"]
    assert {"english", "not_english"} == {c["expect"] for c in cases}


def unicodedata_name(ch):
    return unicodedata.name(ch, "").split(" ")[0]


def test_the_language_set_covers_every_language_the_plan_names():
    texts = " ".join(c["text"] for c in load("language_set.jsonl") if c["expect"] == "not_english")
    scripts = {name for ch in texts if ch.isalpha() for name in [unicodedata_name(ch)] if name != "LATIN"}
    assert {"CJK", "HIRAGANA", "KATAKANA", "CYRILLIC", "ARABIC", "DEVANAGARI", "HANGUL"} <= scripts
    for mixed in ("VPN no funciona", "la impresora no imprime", "mon mot de passe ne marche pas"):
        assert mixed in texts


@pytest.mark.parametrize("text", ["printer broken", "wifi down", "VPN not connecting", "can't print",
                                  "email keeps crashing", "no internet", "no wifi and no internet", "12345", ""])
def test_short_english_tickets_are_not_mistaken_for_another_language(text):
    assert rules.is_english(text) is True


@pytest.mark.parametrize("text", ["VPN no funciona", "la impresora no imprime", "mon mot de passe ne marche pas",
                                  "wifi funktioniert nicht", "ordinateur lent"])
def test_short_mixed_non_english_tickets_are_recognised(text):
    assert rules.is_english(text) is False


def test_the_script_share_decides_before_any_word_list():
    assert rules.is_english("VPN " + chr(0x4E0D) + chr(0x80FD) + chr(0x8FDE) + chr(0x63A5)) is False
    assert rules.is_english("printer broken " + chr(0x3B1)) is True        # one stray letter is not a language
    assert rules.is_english(chr(0xFF50) + chr(0xFF52) + chr(0xFF49) + chr(0xFF4E) + chr(0xFF54) + " broken") is True


def test_is_english_is_deterministic_and_takes_any_input():
    for text in ("Mein Drucker druckt nicht mehr", "printer broken", "VPN no funciona"):
        assert len({rules.is_english(text) for _ in range(5)}) == 1
    assert rules.is_english(None) is True and rules.is_english(5) is True


def test_the_language_check_needs_no_new_dependency():
    source = Path(rules.__file__).read_text(encoding="utf-8")
    body = ast.parse(source).body
    imported = {n.names[0].name.split(".")[0] for n in body if isinstance(n, ast.Import)}
    imported |= {n.module.split(".")[0] for n in body if isinstance(n, ast.ImportFrom) and not n.level and n.module}
    assert imported <= {"re", "unicodedata", "typing"}, imported
