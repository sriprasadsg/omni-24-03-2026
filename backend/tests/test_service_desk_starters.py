"""85-02 Task 1: the service desk's server copy and the four starter IT articles.

The starter text is generic on purpose (D-36, T-85-07): no URL, email address, phone number, vendor or
product name, so an output check can never allow a foreign link from a starter. These tests load the same
module the Knowledge Base button copies (``service_desk.starters``), not a JSON duplicate.
"""
import re
from datetime import datetime, timezone

import pytest

from service_desk import messages, starters

HANDOFF_CODES = [
    "no_article", "security_topic", "billing_topic", "legal_topic", "account_access", "asked_for_person",
    "tenant_word", "critical_priority", "fulfilment_request", "type_not_answered", "not_english",
    "empty_ticket", "service_desk_offline", "service_desk_busy", "output_check_failed", "did_not_help",
    "no_reply_to_ai_answer", "answer_withdrawn", "desk_stopped",
]
DRAFT_REASONS = [
    "level_suggest", "shadow", "mode_drafts", "desk_rate_limit", "stopped", "desk_breaker",
    "no_tray_window", "settings_unreadable",
]
VENDORS = [
    "Cisco", "AnyConnect", "GlobalProtect", "FortiClient", "OpenVPN", "WireGuard", "Pulse", "Zscaler", "HP",
    "Canon", "Epson", "Brother", "Xerox", "Lexmark", "Ricoh", "Microsoft", "Windows", "macOS", "Apple",
    "Google", "Okta", "Azure", "Omni",
]
FIRST_LINE = "Edit this article to match your organization before you rely on it."


# ---------------------------------------------------------------- messages

def test_the_five_shared_strings_are_exact():
    assert messages.MARK == "AI-assisted answer from your IT knowledge base"
    assert messages.FOOTER == "Not right? Choose 'I still need help' and a person will take over."
    assert messages.HANDOFF_NOTICE == "A person from IT will look at this."
    assert messages.WITHDRAWN_NOTICE == "This answer was withdrawn; a person will follow up."
    assert messages.OFFLINE_STATUS == "Offline: the local model isn't running"


def test_staff_reason_labels_cover_exactly_the_nineteen_codes():
    assert sorted(messages.STAFF_REASON_LABELS) == sorted(HANDOFF_CODES)
    assert len(HANDOFF_CODES) == 19
    assert len(set(messages.STAFF_REASON_LABELS.values())) == 19
    assert messages.STAFF_REASON_LABELS["no_article"] == "no article matched"
    assert messages.STAFF_REASON_LABELS["tenant_word"] == "a word your organization added"
    assert messages.STAFF_REASON_LABELS["type_not_answered"] == "ticket type the service desk doesn't answer"
    assert messages.STAFF_REASON_LABELS["desk_stopped"] == "automatic actions were stopped"


def test_draft_reason_text_covers_exactly_the_eight_reasons():
    assert sorted(messages.DRAFT_REASON_TEXT) == sorted(DRAFT_REASONS)
    assert messages.DRAFT_REASON_TEXT["level_suggest"] == "Kept as a draft because Autonomous Ops is at Suggest."
    for text in messages.DRAFT_REASON_TEXT.values():
        assert text.startswith("Kept as a draft because ") and text.endswith(".")


def test_requester_facing_texts_never_carry_a_staff_reason():
    visible = [messages.HANDOFF_NOTICE, messages.WITHDRAWN_NOTICE, messages.NOTICE_TITLE,
               messages.TRAY_POPUP_TITLE, messages.TRAY_POPUP_TEXT, messages.TRAY_CREATED,
               *messages.TRAY_STATUS_TEXT.values(), *messages.TRAY_REASON_LINES.values()]
    labels = [label.lower() for label in messages.STAFF_REASON_LABELS.values()]
    for text in visible:
        for label in labels:
            assert label not in text.lower(), (label, text)
    assert messages.NOTICE_TITLE.format(number="TKT-0042") == "Your ticket TKT-0042 has an answer"


@pytest.mark.parametrize("label, expected", [
    ("no article matched", "No article matched."),
    ("no reply to AI answer", "No reply to AI answer."),
    ("not English", "Not English."),
    ("a word your organization added", "A word your organization added."),
])
def test_sentence_cases_a_label_and_keeps_ai_and_english_capitalised(label, expected):
    assert messages.sentence(label) == expected


def test_every_staff_label_makes_a_one_sentence_line():
    for label in messages.STAFF_REASON_LABELS.values():
        line = messages.sentence(label)
        assert line[0].isupper() and line.endswith(".") and not line.endswith("..")


def test_activity_why_and_plural():
    assert messages.activity_why("TKT-0042", "VPN drops", 1) == 'Ticket TKT-0042: "VPN drops" matched 1 Help desk article.'
    assert messages.activity_why("TKT-0042", "VPN drops", 3) == 'Ticket TKT-0042: "VPN drops" matched 3 Help desk articles.'
    assert messages.plural(1, "article", "articles") == "article"
    assert messages.plural(0, "article", "articles") == "articles"


def test_tray_and_activity_and_api_texts_are_present():
    assert messages.TRAY_STATUS_TEXT["answer_ready"] == "Answer ready - please tell us if it fixed the problem."
    assert sorted(messages.TRAY_STATUS_TEXT) == sorted(
        ["received", "answer_ready", "with_it", "waiting_for_you", "resolved", "closed"])
    assert messages.TRAY_HEADINGS == {"answer": "Answer from IT support (AI-assisted)",
                                      "reply": "Reply from IT", "you": "You"}
    assert messages.TRAY_REASON_LINES["withdrawn"] == messages.WITHDRAWN_NOTICE
    assert messages.TRAY_FOOTNOTE.format(user="ann") == "Showing tickets you raised from this computer as ann."
    assert messages.TRAY_CREATED.format(number="TKT-1") == (
        "Ticket TKT-1 created. Choose My tickets in the tray menu to see any reply.")
    assert messages.TRAY_POPUP_TEXT.format(number="TKT-1", title="VPN") == "TKT-1: VPN. Click to read it."
    assert messages.STAFF_REPLY_AUTHOR_TRAY == "IT"
    assert messages.STAFF_NOTE.format(label="billing topic") == "Service desk: billing topic."
    assert sorted(messages.ACTIVITY) == sorted([
        "posted_result", "confirmed_result", "person_replied_result", "draft_result", "sent_result",
        "discarded_result", "handoff_result", "withdrawn_result", "failed_result", "simulation_result"])
    for key in ("already_handled", "ticket_closed", "person_replied", "no_requester", "not_requester",
                "staff_only", "not_confirmable", "no_reply_target", "not_found", "breaker_tripped",
                "platform_tenant", "word_empty", "word_shape", "word_duplicate", "word_limit",
                "article_title", "article_content", "article_too_long", "edit_unchanged"):
        assert messages.API_DETAIL[key]
    assert messages.API_DETAIL["not_requester"] == "Only the person who raised this ticket can answer this."
    assert messages.API_DETAIL["breaker_tripped"] == "Restore Post answers first."


# ---------------------------------------------------------------- starters

def test_keys_and_order():
    assert [s["key"] for s in starters.STARTERS] == ["password_reset", "vpn", "printer", "agent_tray"]


@pytest.mark.parametrize("starter", starters.STARTERS, ids=lambda s: s["key"])
def test_every_starter_follows_the_content_rules(starter):
    content = starter["content"]
    assert content.splitlines()[0] == FIRST_LINE
    assert "your company's" in content
    assert len(content) < 20000
    assert starter["title"].strip() and starter["tags"]
    assert not re.search(r"https?://|ftp://", content, re.I)
    assert not re.search(r"\bwww\.", content, re.I)
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", content)
    assert not re.search(r"\d[\d\s().+-]{5,}\d", content), "a run of 7 or more digits looks like a phone number"
    assert re.search(r"^1\. ", content, re.M), "plain numbered steps"
    for vendor in VENDORS:
        assert not re.search(r"\b" + re.escape(vendor) + r"\b", content + " " + starter["title"], re.I), vendor


def test_password_reset_is_the_self_service_how_to_and_sends_the_rest_to_a_person():
    content = next(s for s in starters.STARTERS if s["key"] == "password_reset")["content"].lower()
    assert "reset" in content and "forgot" in content
    assert "unlock" in content or "locked" in content
    assert "mfa" in content
    assert '"i still need help"' in content


def test_agent_tray_names_the_menu_items_and_buttons():
    content = next(s for s in starters.STARTERS if s["key"] == "agent_tray")["content"]
    for words in ("Raise a Ticket", "My tickets", "This fixed it", "I still need help"):
        assert words in content


def test_each_starter_has_topic_words_for_retrieval():
    topics = {"password_reset": "password", "vpn": "vpn", "printer": "printer", "agent_tray": "tray"}
    for starter in starters.STARTERS:
        assert topics[starter["key"]] in (starter["title"] + " " + starter["content"]).lower()


def test_copy_docs_builds_four_tenant_scoped_help_desk_documents():
    now = datetime(2026, 11, 8, 9, 30, tzinfo=timezone.utc)
    docs = starters.copy_docs("t1", {"name": "Ann"}, now)
    assert [d["starterKey"] for d in docs] == ["password_reset", "vpn", "printer", "agent_tray"]
    assert len({d["id"] for d in docs}) == 4
    for doc in docs:
        assert re.fullmatch(r"kb-[0-9a-f]{12}", doc["id"])
        assert doc["tenantId"] == "t1" and doc["helpdesk"] is True and doc["source"] == "starter"
        assert doc["createdBy"] == "Ann"
        assert doc["createdAt"] == doc["updatedAt"] == now.isoformat()
        assert doc["title"] and doc["content"] and doc["tags"]
    docs[0]["tags"].append("x")
    assert "x" not in starters.STARTERS[0]["tags"], "copies must not share the starter's tag list"


@pytest.mark.parametrize("bad", ["", "   ", "global", None])
def test_copy_docs_refuses_an_empty_or_global_tenant(bad):
    with pytest.raises(ValueError):
        starters.copy_docs(bad, {"name": "Ann"}, datetime.now(timezone.utc))


def test_no_banned_copy_term_in_the_new_modules():
    for module in (messages, starters):
        text = open(module.__file__, encoding="utf-8").read()
        assert not re.search(r"\bASI\b|\bAGI\b|autopilot|fully[ -]autonomous|\broll(?:ed|ing)?[ -]?back\b",
                             text, re.I), module.__name__
