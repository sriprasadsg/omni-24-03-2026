"""The words of the daily digest (Phase 86, ACTV-04, D-04, UI-SPEC section 5). Pure builders: no database."""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, NamedTuple, Optional, Sequence

SIMULATION_VERBS = {}


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


def counts_line(ran: int, undone: int, waiting: int) -> str:
    return ""


def simulation_line(count: int) -> str:
    return ""


def section_lines(heading: str, items: Sequence[DigestItem], cap: int = 10, simulation: bool = False,
                  total: Optional[int] = None) -> List[str]:
    return []


def notice_title() -> str:
    return ""


def notice_text(ran: Any, undone: Any, waiting: Any, simulation: Any) -> str:
    return ""


def email_subject(org_name: str, ran: int, undone: int, waiting: int) -> str:
    return ""


def email_text(org_name: str, day: str, sections: Any, link: str) -> str:
    return ""


def email_html(org_name: str, day: str, sections: Any, link: str) -> str:
    return ""
