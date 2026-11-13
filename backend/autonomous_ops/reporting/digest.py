"""Daily digest for one organization (Phase 86, ACTV-04). Skeleton: the behaviour arrives with the next commit."""
from datetime import datetime
from typing import Any, Tuple

from .digest_text import Group


EMAIL_TIMEOUT = 30


def window(day: str) -> Tuple[datetime, datetime]:
    return datetime.min, datetime.min


async def ensure_indexes(db) -> None:
    return None


async def gather(db, tenant_id: str, day: str, now: datetime) -> Tuple[Group, Group, Group, Group]:
    return Group(0, []), Group(0, []), Group(0, []), Group(0, [])


async def send_for_tenant(db, tenant_id: str, day: str, now: datetime) -> Any:
    return "quiet"
