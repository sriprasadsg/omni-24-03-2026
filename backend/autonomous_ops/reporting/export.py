"""Activity export builder (inert skeleton, RED step of plan 86-06)."""
from dataclasses import dataclass, field
from typing import List, Optional

CSV_HEADER = ("When (UTC)", "State", "Action", "Target", "Host", "Rule", "Rule id", "Approved by", "Result")
STATE_WORDS = {}


@dataclass
class ExportResult:
    content: Optional[bytes]
    filename: str
    media_type: str
    shown: int
    total: int
    truncated: bool
    rows: List[List[str]] = field(default_factory=list)


def cap_sentence(shown, total):
    return ""


def file_name(tenant_id, fmt, now):
    return ""


async def build(db, tenant_id, *, bucket, days, fmt, viewer_is_platform_staff, now=None):
    return ExportResult(b"", "", "", 0, 0, False)
