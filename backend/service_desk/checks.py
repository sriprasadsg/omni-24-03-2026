"""What the desk accepts from the model (T-85-05, T-85-19, T-85-20, D-19): parse the reply, then check it.

The reply is untrusted text. It never chooses an outcome, a target or a ticket change; it is either an
answer that cites only the articles the desk gave it and says nothing its cited articles do not, or it is
rejected. Every rule is a fixed, pure function of the reply and the cited article text: no model judgement
and no reply field other than ``answer`` and ``cited`` is read. Stdlib and pydantic only.

``check`` returns the first failing rule, in this order: the citation rules (empty_answer, no_citation,
unknown_citation), the length rules (too_long, too_many_lines; blank lines are not counted), html (a tag, an
entity left after decoding, a markdown image), then, for the extracted fragments, foreign_link (URLs with a
scheme, www hosts, markdown link targets, bare domains), foreign_email, foreign_phone (a run of 7 or more
digits with the usual separators), foreign_command (backtick spans, prompt lines, shell words and flags,
pipes and redirects) and foreign_number (4 or more digits). A fragment passes only when it occurs, compared
casefolded and with spaces collapsed, as a whole word or token in the text of the articles the reply cites;
an article that was given but not cited does not count. A single ">" is not a redirect (menu paths such as
"Settings > Network" are ordinary help text); ">>", "2>" and a ">" followed by a file name are.

``verdict`` is the same for the raw model text and adds ``unparseable``. A reply that fails any rule is
handed to a person with the reason ``output_check_failed`` (``HANDOFF_REASON``).
"""
import html
import json
import re
import unicodedata
from typing import Iterable, List, Mapping, Optional

from pydantic import BaseModel, StrictInt, StrictStr

from . import ANSWER_MAX_CHARS, ANSWER_MAX_LINES

RULES = (
    "unparseable", "empty_answer", "no_citation", "unknown_citation", "too_long", "too_many_lines", "html",
    "foreign_link", "foreign_email", "foreign_phone", "foreign_command", "foreign_number",
)
HANDOFF_REASON = "output_check_failed"

_TLDS = ("com|net|org|io|co|edu|gov|info|biz|ai|app|dev|xyz|online|site|top|club|ru|cn|de|uk|us|tv|cc|ly|gg|"
         "mil|int|me|ch|fr")
_NOT_URL_END = "\\s<>\"'`"
_URL = re.compile(
    r"(?<![a-z0-9])(?:[a-z][a-z0-9+.-]{1,20}://|www\.|(?:javascript|data|vbscript|file|mailto|tel|sms):)"
    r"[^" + _NOT_URL_END + r"]*[^" + _NOT_URL_END + r".,;:!?)\]]", re.IGNORECASE)
_MD_TARGET = re.compile(r"\]\(\s*([^)\s]{1,500})\s*\)")
_EMAIL = re.compile(r"[\w.+-]{1,64}@[\w-]{1,63}(?:\.[\w-]{1,63}){1,6}")
_BARE_DOMAIN = re.compile(
    r"(?<![\w@.-])(?:[a-z0-9-]{1,63}\.){1,6}(?:(?:" + _TLDS + r")(?![a-z0-9-])(?:[:/][^" + _NOT_URL_END
    + r"]*)?|[a-z]{2,24}/[^" + _NOT_URL_END + r"]*)", re.IGNORECASE)
_PHONE = re.compile(r"(?<![\w.])\+?\(?\d[\d ()./-]{4,}\d(?!\w)")
_NUMBER = re.compile(r"(?<!\d)\d{4,}(?!\d)")

_TAG = re.compile(r"<\s*/?\s*[a-zA-Z!?]")
_ENTITY = re.compile(r"&(?:#\d{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});")
_MD_IMAGE = re.compile(r"!\[[^\]\[]{0,200}\]\([^)]{0,500}\)")

_BACKTICKS = re.compile(r"`([^`\n]{1,300})`")
_PROMPT_LINE = re.compile(r"^[ \t]*(?:\$|PS[^>\n]{0,40}>|>)[ \t]+(\S[^\n]{0,300})$", re.MULTILINE)
_COMMAND_WORD = re.compile(r"(?<![\w-])(?:sudo|ipconfig|netsh|net|reg|regedit|powershell|cmd|bash|curl|wget|chmod|rm)"
                           r"(?![\w-])", re.IGNORECASE)
_FLAG = re.compile(r"(?<=\s)(?:--?[A-Za-z][\w-]{0,40}|/[A-Za-z][\w-]{0,40})(?=[\s.,;:)]|$)")
_SHELL_OPERATOR = re.compile(r"\S{1,60}[ \t]*(?:\|\||\||&&|>>|2>&1|2>|&>)[ \t]*\S{1,60}"
                             r"|\S{1,60}[ \t]*>[ \t]*(?:[\w.~-]*[/\\][\w./\\~-]*|\w+\.\w{1,4})")


class Reply(BaseModel):
    answer: StrictStr
    cited: List[StrictInt]


def parse_reply(text: str) -> Optional[Reply]:
    """The reply as a Reply, or None for anything that is not exactly an answer with cited numbers."""
    try:
        return Reply.model_validate(json.loads(text))
    except Exception:
        return None


def handoff_reason(rule: str) -> str:
    """The hand-off reason for a failing rule: always output_check_failed."""
    if rule not in RULES:
        raise ValueError("Not a rule of the output checks: %r" % (rule,))
    return HANDOFF_REASON


def _norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _present(fragment: str, haystack: str) -> bool:
    """Whether the fragment occurs in the (already normalised) article text as a whole word or token."""
    wanted = _norm(fragment).rstrip(".,;:!?")
    if not wanted:
        return True
    return re.search(r"(?<![a-z0-9])" + re.escape(wanted) + r"(?![a-z0-9/%?&=#~_-]|\.[a-z0-9])",
                     haystack) is not None


def _take(pattern: "re.Pattern", text: str, found: List[str], group: int = 0) -> str:
    """The text with every match of the pattern blanked out; the matches (or one group) are added to ``found``."""
    def blank(match):
        found.append(match.group(group))
        return " "
    return pattern.sub(blank, text)


def _blank_phone(match: "re.Match", found: List[str]) -> str:
    """Blank a run of 7 or more digits (a phone-like number); a shorter run is left for the number rule."""
    if sum(ch.isdigit() for ch in match.group(0)) < 7:
        return match.group(0)
    found.append(match.group(0))
    return " "


def _is_html(answer: str) -> bool:
    decoded = html.unescape(answer)
    return bool(_TAG.search(answer) or _TAG.search(decoded) or _ENTITY.search(answer) or _MD_IMAGE.search(answer))


def _cited_text(reply: Reply, cited_texts: Optional[Mapping]) -> str:
    """The normalised text of the articles the reply cites; none given means no text."""
    if not cited_texts:
        return ""
    by_number = {}
    for key, value in cited_texts.items():
        try:
            by_number[int(key)] = value if isinstance(value, str) else ""
        except (TypeError, ValueError):
            continue
    return "\n".join(_norm(by_number.get(number, "")) for number in dict.fromkeys(reply.cited))


def check(reply: Reply, given_ids: Iterable[int], cited_texts: Optional[Mapping] = None) -> Optional[str]:
    """None when the reply may be used, else the name of the first failing rule.

    ``given_ids`` are the numbers of the articles the model was given; ``cited_texts`` maps each of those
    numbers to the article text (None reads as no article text, so any link, address, phone, command or
    long number in the reply then fails)."""
    given = set(given_ids)
    answer = reply.answer
    if not answer.strip():
        return "empty_answer"
    if not reply.cited:
        return "no_citation"
    if any(number not in given for number in reply.cited):
        return "unknown_citation"
    if len(answer) > ANSWER_MAX_CHARS:
        return "too_long"
    if sum(1 for line in answer.splitlines() if line.strip()) > ANSWER_MAX_LINES:
        return "too_many_lines"
    if _is_html(answer):
        return "html"

    links: List[str] = []
    emails: List[str] = []
    commands: List[str] = []
    phones: List[str] = []
    numbers: List[str] = []
    rest = _take(_MD_TARGET, answer, links, 1)
    rest = _take(_URL, rest, links)
    rest = _take(_EMAIL, rest, emails)
    rest = _take(_BARE_DOMAIN, rest, links)
    rest = _take(_BACKTICKS, rest, commands, 1)
    rest = _take(_PROMPT_LINE, rest, commands, 1)
    rest = _take(_SHELL_OPERATOR, rest, commands)
    rest = _take(_COMMAND_WORD, rest, commands)
    rest = _take(_FLAG, rest, commands)
    rest = _PHONE.sub(lambda m: _blank_phone(m, phones), rest)
    _take(_NUMBER, rest, numbers)

    allowed = _cited_text(reply, cited_texts)
    for rule, fragments in (("foreign_link", links), ("foreign_email", emails), ("foreign_phone", phones),
                            ("foreign_command", commands), ("foreign_number", numbers)):
        if any(not _present(fragment, allowed) for fragment in fragments):
            return rule
    return None


def verdict(text: str, given_ids: Iterable[int], cited_texts: Optional[Mapping] = None) -> Optional[str]:
    """``check`` for the raw model text: None when it may be used, else the failing rule (unparseable first)."""
    reply = parse_reply(text)
    if reply is None:
        return "unparseable"
    return check(reply, given_ids, cited_texts)
