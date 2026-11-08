"""What the desk accepts from the model (T-85-05, D-19): parse the reply, then check it.

The reply is untrusted text. It never chooses an outcome, a target or a ticket change; it is either an
answer that cites only the articles the desk gave it, or it is rejected. Stdlib and pydantic only.
85-06 adds the markup, link, address, phone, command and number rules.
"""
import json
from typing import Iterable, List, Optional

from pydantic import BaseModel, StrictInt, StrictStr

from . import ANSWER_MAX_CHARS


class Reply(BaseModel):
    answer: StrictStr
    cited: List[StrictInt]


def parse_reply(text: str) -> Optional[Reply]:
    """The reply as a Reply, or None for anything that is not exactly an answer with cited numbers."""
    try:
        return Reply.model_validate(json.loads(text))
    except Exception:
        return None


def check(reply: Reply, given_ids: Iterable[int]) -> Optional[str]:
    """None when the reply may be used, else the name of the failing rule."""
    given = set(given_ids)
    if not reply.answer.strip():
        return "empty_answer"
    if not reply.cited:
        return "no_citation"
    if any(number not in given for number in reply.cited):
        return "unknown_citation"
    if len(reply.answer) > ANSWER_MAX_CHARS:
        return "too_long"
    return None
