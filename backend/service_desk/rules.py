"""The fixed rules that send a ticket to a person before the model sees it (DESK-02, D-02, D-23, D-32, D-37).

Whether a ticket goes to a person is decided here, on the ticket text and its fields, never from the model's
own confidence or output (PROH-85-03). ``evaluate`` returns None (the ticket may go on to retrieval) or the
first matching hand-off reason in this fixed order:

    empty text, critical priority, ticket type, tray template, security, billing, legal, account access,
    asking for a person, tenant words

so a ticket that hits two rules always reports the earlier rule's reason. Every phrase and tenant word is
normalised with ``sanitize.normalize_for_match`` and matched as an escaped literal with word boundaries;
ticket text is never compiled as a pattern (T-85-18). ``is_english`` is the standard-library language check
(D-20, D-35): script share plus small word sets, pinned by language_set.jsonl. Stdlib only.
"""
import re
import unicodedata
from typing import Any, FrozenSet, Iterable, Mapping, Optional, Pattern, Tuple

from . import ELIGIBLE_TYPES, WORD_MAX, WORDS_MAX
from .phrases import (ACCOUNT_ACCESS, ASK_FOR_PERSON, BILLING, ENGLISH_WORDS, FRENCH_WORDS, GERMAN_WORDS,  # noqa: F401
                      ITALIAN_WORDS, LEGAL, PORTUGUESE_WORDS, SECURITY, SPANISH_WORDS)
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


# ---------------------------------------------------------------- English only (D-20, D-35)

NON_LATIN_SHARE = 0.30          # more than this share of letters outside the Latin script: not English
_ENGLISH: FrozenSet[str] = frozenset(normalize_for_match(w) for w in ENGLISH_WORDS)
_FOREIGN: FrozenSet[str] = frozenset(
    normalize_for_match(w) for words in (SPANISH_WORDS, FRENCH_WORDS, GERMAN_WORDS, PORTUGUESE_WORDS, ITALIAN_WORDS)
    for w in words) - _ENGLISH


def _is_latin_letter(ch: str) -> bool:
    return unicodedata.name(ch, "").startswith("LATIN")


def _english_token(token: str) -> bool:
    """A word of the English set, allowing a plain plural, past or -ing ending."""
    if token in _ENGLISH:
        return True
    forms = []
    for ending, restore in (("ing", ""), ("ing", "e"), ("ed", ""), ("d", ""), ("es", ""), ("s", ""), ("ly", "")):
        if token.endswith(ending) and len(token) > len(ending) + 2:
            forms.append(token[:-len(ending)] + restore)
    return any(form in _ENGLISH for form in forms)


def is_english(text: Any) -> bool:
    """True when the text reads as English. A text with no letters is English (it then fails retrieval).

    More than 30% of the letters outside the Latin script means not English. Otherwise two different words from
    the Spanish, French, German, Portuguese or Italian sets mean not English, and so does one such word when no
    English word is there to outweigh it. The same input always gives the same answer."""
    folded = normalize_for_match(text)
    letters = [ch for ch in folded if ch.isalpha()]
    if not letters:
        return True
    outside = sum(1 for ch in letters if not _is_latin_letter(ch))
    if outside * 10 > len(letters) * 3:
        return False
    tokens = {token for token in folded.split() if token.isalpha()}
    foreign = len(tokens & _FOREIGN)
    if foreign >= 2:
        return False
    return not (foreign == 1 and not any(_english_token(token) for token in tokens))
