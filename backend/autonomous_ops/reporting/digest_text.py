"""The words of the daily digest (Phase 86, ACTV-04, D-04, UI-SPEC section 5). Pure builders: no database.

The in-app notice puts everything that matters in its first two lines (the notification center clamps a
message to two lines): line 1 the three counts, line 2 the simulation line when there is one. Sections follow
in the fixed order Ran, Undone, Waiting for your approval, Simulation: would have done. A simulation item is
never listed under Ran and never counted as ran. Every server string (target, rule name, organization) is cut
and cleaned here; the html body escapes it.
"""
import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, NamedTuple, Optional, Sequence, Tuple

from . import DIGEST_HOUR_UTC, DIGEST_SECTION_CAP, DIGEST_TARGET_CAP
from .rule_names import rule_name

TITLE = "Autonomous Ops daily digest"
CLOSING = "Open Autonomous Ops in the sidebar to see everything."
SIMULATION_HEADING = "Simulation: would have done"
SIMULATION_INTRO = "Shadow mode is on. Nothing below was carried out."
HEADINGS = ("Ran", "Undone", "Waiting for your approval")

# What "would have been done" reads as, by command (past tense, then what it acted on).
SIMULATION_VERBS = {
    "block_ip": "blocked", "quarantine_file": "quarantined a file on", "isolate_host": "isolated",
    "restart_service": "restarted a service on", "kill_process": "stopped a process on",
    "install_patches": "installed patches on", "reboot_host": "restarted", "ticket_answer": "answered ticket",
}

_CONTROL = re.compile(r"[\x00-\x1f\x7f  ]+")


@dataclass
class DigestItem:
    id: str
    at: Optional[datetime]
    action_label: str
    target: Optional[str]
    rule_id: Optional[str]
    command: Optional[str]


class Group(NamedTuple):
    """One digest group: how many rows there are in all, and the (at most DIGEST_SECTION_CAP) items listed."""
    total: int
    items: List[DigestItem]


def _one_line(value: Any) -> str:
    """A server string on one line: control characters (CR, LF, tab) become one space."""
    return _CONTROL.sub(" ", str(value or "")).strip()


def _cut(value: str, cap: int) -> str:
    return value if len(value) <= cap else value[:cap - 1] + "…"


def _group(value: Any) -> Group:
    """A Group, or a plain list of items (its total is its length)."""
    if isinstance(value, Group):
        return value
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], int):
        return Group(value[0], list(value[1]))
    items = list(value or [])
    return Group(len(items), items)


def _utc(at: Optional[datetime]) -> Optional[datetime]:
    if not isinstance(at, datetime):
        return None
    return (at if at.tzinfo else at.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _newest_first(items: Sequence[DigestItem]) -> List[DigestItem]:
    floor = datetime.min.replace(tzinfo=timezone.utc)
    return sorted(items, key=lambda i: (_utc(i.at) or floor, str(i.id)), reverse=True)


def counts_line(ran: int, undone: int, waiting: int) -> str:
    return f"Last 24 hours: {ran} ran, {undone} undone, {waiting} waiting for your approval."


def simulation_line(count: int) -> str:
    return f"Simulation (shadow mode): {count} would have been done. Nothing was carried out."


def _where(item: DigestItem) -> str:
    return _cut(_one_line(item.target), DIGEST_TARGET_CAP)


def _tail(item: DigestItem) -> str:
    at = _utc(item.at)
    clock = f" {at:%H:%M} UTC" if at else ""
    rule = _cut(_one_line(rule_name(item.rule_id) if item.rule_id else "Automatic decision"), 200)
    return f" Rule: {rule}.{clock}"


def _item_line(item: DigestItem) -> str:
    where = _where(item)
    return f"- {_one_line(item.action_label) or 'Action'}{f' on {where}' if where else ''}.{_tail(item)}"


def _simulation_item_line(item: DigestItem) -> str:
    where = _where(item)
    verb = SIMULATION_VERBS.get(item.command or "")
    if verb:
        phrase = f"Would have {verb}{f' {where}' if where else ''}"
    else:
        phrase = f"Would have run {_one_line(item.action_label).lower() or 'an action'}{f' on {where}' if where else ''}"
    return f"- {phrase}.{_tail(item)}"


def section_lines(heading: str, items: Sequence[DigestItem], cap: int = DIGEST_SECTION_CAP, simulation: bool = False,
                  total: Optional[int] = None) -> List[str]:
    """One section: ``{heading} ({total})``, up to ``cap`` item lines newest first, and the overflow sentence when
    the group holds more than is listed. ``total`` defaults to the number of items given."""
    count = len(items) if total is None else total
    shown = _newest_first(items)[:cap]
    lines = [f"{heading} ({count})"]
    if simulation:
        lines.append(SIMULATION_INTRO)
    lines += [(_simulation_item_line if simulation else _item_line)(i) for i in shown]
    if count > len(shown):
        lines.append(f"Showing the first {len(shown)} of {count}. The rest are on the Autonomous Ops screen.")
    return lines


def _blocks(sections: Tuple[Any, Any, Any, Any]) -> List[List[str]]:
    """The non-empty sections in their fixed order."""
    ran, undone, waiting, simulation = (_group(s) for s in sections)
    blocks = [section_lines(h, g.items, total=g.total) for h, g in zip(HEADINGS, (ran, undone, waiting)) if g.total]
    if simulation.total:
        blocks.append(section_lines(SIMULATION_HEADING, simulation.items, simulation=True, total=simulation.total))
    return blocks


def _counts(sections: Tuple[Any, Any, Any, Any]) -> Tuple[int, int, int, int]:
    return tuple(_group(s).total for s in sections)  # type: ignore[return-value]


def notice_title() -> str:
    return TITLE


def notice_text(ran: Any, undone: Any, waiting: Any, simulation: Any) -> str:
    """The in-app message: counts, the simulation line when any, then a blank line, the sections and the closing line."""
    sections = (ran, undone, waiting, simulation)
    r, u, w, s = _counts(sections)
    lines = [counts_line(r, u, w)]
    if s:
        lines.append(simulation_line(s))
    lines.append("")
    for block in _blocks(sections):
        lines += block + [""]
    lines.append(CLOSING)
    return "\n".join(lines)


def email_subject(org_name: str, ran: int, undone: int, waiting: int) -> str:
    """One header line: any CR, LF or other control character in the organization name becomes a space."""
    return f"{TITLE} for {_one_line(org_name)}: {ran} ran, {undone} undone, {waiting} waiting"


def _date_words(day: str) -> str:
    return datetime.strptime(day, "%Y-%m-%d").strftime("%d %b %Y")


def _closing(org: str) -> str:
    return (f"You get this because you are an administrator of {org}. It is sent once a day, and only on days when "
            "something ran, was undone, is waiting for approval or would have been done in shadow mode.")


def email_text(org_name: str, day: str, sections: Any, link: str) -> str:
    r, u, w, _ = _counts(sections)
    org = _one_line(org_name)
    lines = [f"{TITLE} for {org}", f"The last 24 hours, up to {DIGEST_HOUR_UTC:02d}:00 UTC on {_date_words(day)}.", "",
             f"{r} ran, {u} undone, {w} waiting for your approval.", ""]
    for block in _blocks(sections):
        lines += block + [""]
    lines += [f"See everything: {link}", "", _closing(org)]
    return "\n".join(lines)


def email_html(org_name: str, day: str, sections: Any, link: str) -> str:
    """The same words in the same order as paragraphs and plain lists; no images; every server string escaped."""
    esc = html.escape
    r, u, w, _ = _counts(sections)
    org = _one_line(org_name)
    parts = [f"<h2>{esc(TITLE)} for {esc(org)}</h2>",
             f"<p>The last 24 hours, up to {DIGEST_HOUR_UTC:02d}:00 UTC on {esc(_date_words(day))}.</p>",
             f"<p>{r} ran, {u} undone, {w} waiting for your approval.</p>"]
    for block in _blocks(sections):
        heading, rest = block[0], block[1:]
        parts.append(f"<h3>{esc(heading)}</h3>")
        intro = [line for line in rest if not line.startswith("- ") and line.startswith("Shadow mode")]
        more = [line for line in rest if line.startswith("Showing the first")]
        if intro:
            parts.append(f"<p>{esc(intro[0])}</p>")
        parts.append("<ul>" + "".join(f"<li>{esc(line[2:])}</li>" for line in rest if line.startswith("- ")) + "</ul>")
        if more:
            parts.append(f"<p>{esc(more[0])}</p>")
    parts.append(f'<p>See everything: <a href="{esc(link, quote=True)}">{esc(link)}</a></p>')
    parts.append(f"<p>{esc(_closing(org))}</p>")
    return "".join(parts)
