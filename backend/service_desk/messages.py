"""Every server sentence of Phase 85 (the first-line service desk), in one module.

85-UI-SPEC sections 3, 4, 5 and 8 and the Copywriting Contract are copied verbatim. The desk gate,
the answer writer, the ticket views, the Activity rows and the tray routes all read this module, so no
other new module holds a sentence shown to a person. ACTV-08 scans this file against the rules in
shared/autonomous-ops-banned-terms.json: the feature is called Autonomous Ops and the desk is called
Service desk; the terms listed there are never used (say withdraw / undo / hide).
Dictionary keys are identifiers, not words shown to anyone.

Two audiences, kept apart on purpose (T-85-06, D-24):

* ``STAFF_REASON_LABELS``, ``OUTPUT_RULE_LABELS``, ``STAFF_NOTE_RULE`` and ``DRAFT_REASON_TEXT`` are for
  staff only (Activity rows, staff notes, the draft panel). A requester never sees a reason or a rule.
* ``HANDOFF_NOTICE``, ``WITHDRAWN_NOTICE``, ``NOTICE_TITLE`` and the ``TRAY_*`` texts are what a requester
  can see. They are generic and carry at most the ticket number and title.

Templates use ``{name}`` fields and are filled with ``str.format``. Plain strings only, no HTML: the
browser and the tray render every one of these as text. Stdlib only, plus the Activity words that
autonomous_ops/messages.py declares once (the Activity view lives there; the desk reads them).
"""
from typing import Dict

from autonomous_ops import messages as _ao_messages

# ---------------------------------------------------------------- the five shared constants (D-13, D-22, D-24, D-25)
# components/serviceDesk/serviceDeskCopy.ts holds the same five strings; a vitest test reads this file.

MARK = "AI-assisted answer from your IT knowledge base"
FOOTER = "Not right? Choose 'I still need help' and a person will take over."
HANDOFF_NOTICE = "A person from IT will look at this."
WITHDRAWN_NOTICE = "This answer was withdrawn; a person will follow up."
OFFLINE_STATUS = "Offline: the local model isn't running"

# ---------------------------------------------------------------- staff-only hand-off reasons (D-24)

# The staff-only note naming the reason, added to a ticket the desk hands to a person.
STAFF_NOTE = "Service desk: {label}."

# The same note when the reason is a failed output check: it also names the rule that refused the reply
# (G-85-3). ``{label}`` is the reason label, ``{rule}`` the label from OUTPUT_RULE_LABELS.
STAFF_NOTE_RULE = "Service desk: {label} ({rule})."

# Exactly one label per hand-off code. 85-01 declares the same 19 codes in service_desk/__init__.py and
# 85-12 tests that the two stay equal.
STAFF_REASON_LABELS: Dict[str, str] = {
    "no_article": "no article matched",
    "security_topic": "security topic",
    "billing_topic": "billing topic",
    "legal_topic": "legal topic",
    "account_access": "account access",
    "asked_for_person": "requester asked for a person",
    "tenant_word": "a word your organization added",
    "critical_priority": "critical priority",
    "fulfilment_request": "fulfilment request",
    "type_not_answered": "ticket type the service desk doesn't answer",
    "not_english": "not English",
    "empty_ticket": "nothing to answer",
    "service_desk_offline": "service desk offline",
    "service_desk_busy": "service desk busy",
    "output_check_failed": "output check failed",
    "did_not_help": "did not help",
    "no_reply_to_ai_answer": "no reply to AI answer",
    "answer_withdrawn": "answer withdrawn",
    "desk_stopped": "automatic actions were stopped",
}

# One staff label per output rule of service_desk/checks.py (G-85-3). The keys equal checks.RULES; a test
# keeps the two in step. Staff only: the rule never reaches a requester.
OUTPUT_RULE_LABELS: Dict[str, str] = {
    "unparseable": "the reply was not in the agreed form",
    "empty_answer": "the answer was empty",
    "no_citation": "the answer cited no article",
    "unknown_citation": "no cited article was given",
    "too_long": "the answer was too long",
    "too_many_lines": "the answer had too many lines",
    "html": "the answer held markup",
    "foreign_link": "a link not in the cited articles",
    "foreign_email": "an email address not in the cited articles",
    "foreign_phone": "a phone number not in the cited articles",
    "foreign_command": "a command not in the cited articles",
    "foreign_number": "a number not in the cited articles",
}

# Why a drafted answer was kept as a draft (staff only, UI-SPEC section 3). One sentence per draft reason.
DRAFT_REASON_TEXT: Dict[str, str] = {
    "level_suggest": "Kept as a draft because Autonomous Ops is at Suggest.",
    "shadow": "Kept as a draft because this organization is in shadow mode.",
    "mode_drafts": "Kept as a draft because the service desk is set to Drafts only.",
    "desk_rate_limit": "Kept as a draft because the hourly limit of 20 answers was reached.",
    "stopped": "Kept as a draft because automatic actions are stopped.",
    "desk_breaker": "Kept as a draft because the service desk dropped to Drafts only.",
    "no_tray_window": "Kept as a draft because this computer's tray app can't show AI answers yet.",
    "settings_unreadable": ("Kept as a draft because this organization's service desk settings "
                            "couldn't be read."),
}

# ---------------------------------------------------------------- Activity rows (UI-SPEC section 5)

# The action labels of a desk row (the "What ran" cell). Declared once in autonomous_ops/messages.py
# (85-03) so the two modules cannot drift; this is the desk's view of them.
ACTION_LABELS = {
    "post": _ao_messages.ACTION_LABELS["ticket_answer"],
    "draft": _ao_messages.DESK_ACTION_LABELS["draft"],
    "handoff": _ao_messages.ACTION_LABELS["ticket_handoff"],
}

# The Result cell of each row shape. ``{articles}`` is filled with plural(n, "article", "articles").
ACTIVITY: Dict[str, str] = {
    "posted_result": "Posted to the requester with {n} cited {articles}. Waiting for their reply.",
    "confirmed_result": "The requester confirmed it fixed the problem on {date}.",
    "person_replied_result": "A person replied after this answer. Undo is no longer available.",
    "draft_result": "Draft kept for your team. Open the ticket to send, edit or discard it.",
    "sent_result": "Sent by {name} at {time}. Waiting for the requester.",
    "discarded_result": "Discarded by {name}.",
    "handoff_result": ("Ticket {number} went to the normal queue. The requester was told a person "
                       "will look at it."),
    "withdrawn_result": "Withdrawn by {name} at {time}. The ticket went to a person.",
    "failed_result": ("The answer couldn't be saved on the ticket: {reason}. The ticket went to "
                      "a person."),
    "simulation_result": "Would have posted the answer to ticket {number}. Nothing was posted.",
}

UNDO_HINT = _ao_messages.DESK_UNDO_HINT
UNDO_TOAST = "Answer withdrawn. Ticket {number} went to a person."
UNDO_TOAST_BREAKER = ("Answer withdrawn. 3 answers were withdrawn within 24 hours, so the service desk "
                      "dropped to Drafts only. A person with manage access can restore it.")

# ---------------------------------------------------------------- requester-facing notices (D-12, D-33)

# Generic on purpose (T-85-06): the ticket number only, never a preview of any text.
NOTICE_TITLE = "Your ticket {number} has an answer"
# The notice when a person withdraws the answer (D-25): same rule, the ticket number only.
WITHDRAWN_NOTICE_TITLE = "Your ticket {number} has an update"

# The in-app notice to the organization's admins when the desk drops to Drafts only (D-25).
BREAKER_NOTICE_TITLE = "Service desk dropped to Drafts only"
BREAKER_NOTICE = ("3 answers were withdrawn within 24 hours, so the service desk stopped posting answers. "
                  "A person with manage access can restore Post answers in the service desk settings.")

# ---------------------------------------------------------------- the tray window (UI-SPEC section 8, D-05)
# Every display string the tray shows comes from here, so a copy change needs no agent release.

TRAY_STATUS_TEXT = {
    "received": "Received - IT has your ticket.",
    "answer_ready": "Answer ready - please tell us if it fixed the problem.",
    "with_it": "With IT - a person from IT will look at this.",
    "waiting_for_you": "Waiting for you - IT replied.",
    "resolved": "Resolved.",
    "closed": "Closed.",
}

TRAY_HEADINGS = {
    "answer": "Answer from IT support (AI-assisted)",
    "reply": "Reply from IT",
    "you": "You",
}

# The DimGray line under the ticket title when the buttons are disabled.
TRAY_REASON_LINES = {
    "resolved": "This ticket is resolved.",
    "with_it": "A person from IT is looking at this.",
    "withdrawn": WITHDRAWN_NOTICE,
}

# R9: says what is shown, never claims it is private (the Windows user name is soft scoping, D-34).
TRAY_FOOTNOTE = "Showing tickets you raised from this computer as {user}."
TRAY_EMPTY = ("You haven't raised any tickets from this computer yet. Choose Raise a Ticket in the "
              "tray menu.")
# R11: shown in the Raise a Ticket dialog after a successful submit.
TRAY_CREATED = "Ticket {number} created. Choose My tickets in the tray menu to see any reply."
TRAY_POPUP_TITLE = "Your ticket has an answer"
TRAY_POPUP_TEXT = "{number}: {title}. Click to read it."
# R12: the author shown on a staff reply in the tray.
STAFF_REPLY_AUTHOR_TRAY = "IT"

# ---------------------------------------------------------------- API error and validation details

API_DETAIL: Dict[str, str] = {
    "already_handled": "This draft was already handled.",
    "ticket_closed": "This ticket is {state}, so the draft can't be sent. You can still discard it.",
    "person_replied": ("A person already replied, so this draft can't be sent. You can still "
                       "discard it."),
    "no_requester": "This ticket has no requester who can see an answer, so the draft can't be sent.",
    "not_requester": "Only the person who raised this ticket can answer this.",
    "staff_only": "Only staff can send, edit or discard this draft.",
    "not_confirmable": "This ticket has no answer waiting for your reply.",
    "no_reply_target": ("This ticket was raised by an automated source, so there is no requester to "
                        "reply to."),
    "not_found": "Ticket not found.",
    "breaker_tripped": "Restore Post answers first.",
    "platform_tenant": "The service desk isn't available for the platform organization.",
    "word_empty": "Enter a word or phrase.",
    "word_shape": "Use 2 to 40 characters: letters, numbers, spaces and - ' & / .",
    "word_duplicate": "{word} is already on the list.",
    "word_limit": "You can add up to 50 words.",
    "article_title": "Enter a title.",
    "article_content": "Enter the article text.",
    "article_too_long": "The article is over {max} characters. Shorten it.",
    "edit_unchanged": "Change the text, or use Send as is.",
    "draft_empty": "Enter the answer text.",
    "draft_too_long": "The answer is over {max} characters. Shorten it.",
    "help_too_long": "Use up to {max} characters.",
    "article_not_found": "Article not found.",
    "mode_invalid": "Choose Off, Drafts only or Post answers.",
    "not_tripped": "Post answers doesn't need restoring.",
    "gap_article_not_helpdesk": ("An article written from a knowledge gap must be a Help desk article, so the "
                                 "service desk can use it."),
}

# The three desk modes as a person reads them (the settings card, the activity list).
MODE_LABELS: Dict[str, str] = {"off": "Off", "drafts": "Drafts only", "post": "Post answers"}

# The reason line of a settings change in the activity list (the label is in autonomous_ops CONTROL_LABELS).
CONTROL_REASONS: Dict[str, str] = {
    "service_desk_mode_changed": "Service desk set to {mode}.",
    "service_desk_words_changed": "{count} extra words send a ticket to a person: {words}.",
    "service_desk_words_none": "No extra words are set now. The built-in rules still apply.",
    "service_desk_restored": "Post answers restored. Answers post again once every condition is met.",
    "service_desk_breaker_tripped": ("3 answers were withdrawn within 24 hours, so the service desk dropped to "
                                     "Drafts only."),
}

# ---------------------------------------------------------------- helpers


def plural(n: int, one: str, many: str) -> str:
    """``one`` when n is 1, else ``many``."""
    return one if n == 1 else many


def sentence(label: str) -> str:
    """A staff reason label as a sentence: first letter capitalised, a full stop at the end.

    Only the first character changes, so "AI" and "English" keep their capitals:
    "no article matched" -> "No article matched.", "no reply to AI answer" -> "No reply to AI answer.".
    """
    text = (label or "").strip()
    if not text:
        return ""
    text = text[0].upper() + text[1:]
    return text if text.endswith(".") else text + "."


def activity_why(number: str, title: str, n: int) -> str:
    """The Why cell of a desk row: ``Ticket TKT-0042: "VPN drops" matched 1 Help desk article.``"""
    return 'Ticket {}: "{}" matched {} Help desk {}.'.format(number, title, n, plural(n, "article", "articles"))
