"""The fixed rules that send a ticket to a person before the model sees it (DESK-02, D-02, D-23, D-32, D-37).

Whether a ticket goes to a person is decided here, on the ticket text and its fields, never from the model's
own confidence or output (PROH-85-03). ``evaluate`` returns None (the ticket may go on to retrieval) or the
first matching hand-off reason in this fixed order:

    empty text, critical priority, ticket type, tray template, security, billing, legal, account access,
    asking for a person, tenant words

so a ticket that hits two rules always reports the earlier rule's reason. Every phrase and tenant word is
normalised with ``sanitize.normalize_for_match`` and matched as an escaped literal with word boundaries;
ticket text is never compiled as a pattern (T-85-18). Stdlib only (D-35).
"""
import re
from typing import Any, Dict, Iterable, Mapping, Optional, Pattern, Tuple

from . import ELIGIBLE_TYPES, WORD_MAX, WORDS_MAX
from .phrases import ACCOUNT_ACCESS, ASK_FOR_PERSON, BILLING, LEGAL, SECURITY  # noqa: F401  (re-exported)
from .sanitize import normalize_for_match
from .tray_contract import LEGACY_TITLE_PREFIXES, TEMPLATE_CLASS

# What a tray template class hands off as.
_CLASS_REASON = {"fulfilment": "fulfilment_request", "security": "security_topic", "account_access": "account_access"}


def _alternation(phrases: Iterable[str]) -> Optional[Pattern[str]]:
    """One word-boundary pattern over escaped, normalised literals; None when there is nothing to match."""
    literals = {normalize_for_match(p) for p in phrases if isinstance(p, str)}
    literals.discard("")
    if not literals:
        return None
    body = "|".join(re.escape(p) for p in sorted(literals, key=lambda p: (-len(p), p)))
    return re.compile(r"(?<!\w)(?:" + body + r")(?!\w)")


_SENSITIVE: Tuple[Tuple[str, Pattern[str]], ...] = tuple(
    (reason, _alternation(phrases)) for reason, phrases in (
        ("security_topic", SECURITY), ("billing_topic", BILLING), ("legal_topic", LEGAL),
        ("account_access", ACCOUNT_ACCESS), ("asked_for_person", ASK_FOR_PERSON)))

_LEGACY_PREFIXES = tuple((normalize_for_match(prefix), template) for prefix, template in LEGACY_TITLE_PREFIXES.items())


def _template_class(ticket: Mapping[str, Any]) -> Optional[str]:
    """The desk class of the ticket's tray template: the stored template, else the legacy title prefix."""
    channel = ticket.get("requester_channel")
    template = channel.get("template") if isinstance(channel, dict) else None
    if isinstance(template, str) and template in TEMPLATE_CLASS:
        return TEMPLATE_CLASS[template]
    title = normalize_for_match(ticket.get("title"))
    for prefix, legacy in _LEGACY_PREFIXES:
        if title == prefix or title.startswith(prefix + " "):
            return TEMPLATE_CLASS[legacy]
    return None


def _tenant_hit(text: str, words: Optional[Iterable[Any]]) -> bool:
    """True when a tenant-added word occurs in the text as a whole word (a literal, never a pattern)."""
    if not words:
        return False
    usable = []
    for word in words:
        if isinstance(word, str) and len(word) <= WORD_MAX * 4:
            usable.append(word)
        if len(usable) >= WORDS_MAX:
            break
    pattern = _alternation(usable)
    return bool(pattern and pattern.search(text))


def evaluate(ticket: Mapping[str, Any], cleaned_text: str, words: Optional[Iterable[Any]] = None) -> Optional[str]:
    """None, or the first hand-off reason that sends this ticket to a person before the model.

    ``ticket`` supplies priority, type, requester_channel.template and title; ``cleaned_text`` is the
    sanitised title and description; ``words`` is the tenant's own word list."""
    text = normalize_for_match(cleaned_text)
    if not text:
        return "empty_ticket"
    if str(ticket.get("priority") or "").strip().casefold() == "critical":
        return "critical_priority"                                        # D-37: high, medium and low stay eligible
    ticket_type = str(ticket.get("type") or "").strip().casefold()
    if ticket_type == "security":
        return "security_topic"
    if ticket_type == "feature":
        return "fulfilment_request"
    if ticket_type not in ELIGIBLE_TYPES:
        return "type_not_answered"
    template_reason = _CLASS_REASON.get(_template_class(ticket) or "")
    if template_reason:
        return template_reason
    for reason, pattern in _SENSITIVE:
        if pattern is not None and pattern.search(text):
            return reason
    if _tenant_hit(text, words):
        return "tenant_word"
    return None
