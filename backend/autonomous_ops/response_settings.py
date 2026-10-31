"""Per-tenant response settings for the automatic sweep (Phase 83, D-04, D-13).

Stored as ``autonomy_settings.response`` ({twoSignal, blockHours, watchedServices}). A new tenant
reads the defaults with nothing stored, so there is no backfill: two sources required, a block
lasts 24 hours, no watched services. ``load`` never raises. A value that is present but not
understood reads as the safe default and sets ``readable`` False so a caller can say so.

Raw Mongo handle with an explicit tenantId; the ambient tenant ContextVar is never used.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, List

from .scope import raw

logger = logging.getLogger(__name__)

DEFAULT_TWO_SIGNAL = True
DEFAULT_BLOCK_HOURS = 24
MIN_BLOCK_HOURS = 1
MAX_BLOCK_HOURS = 168          # 604800 seconds, the contract's longest block


@dataclass
class ResponseSettings:
    two_signal: bool = DEFAULT_TWO_SIGNAL
    block_hours: int = DEFAULT_BLOCK_HOURS
    watched_services: List[str] = field(default_factory=list)
    readable: bool = True


def _is_hours(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and MIN_BLOCK_HOURS <= value <= MAX_BLOCK_HOURS


async def load(db, tenant_id: str) -> ResponseSettings:
    """The tenant's response settings; defaults for anything absent, the safe default plus
    ``readable`` False for anything malformed or unreadable. Never raises."""
    s = ResponseSettings()
    try:
        doc = await raw(db).autonomy_settings.find_one({"tenantId": tenant_id}, {"_id": 0, "response": 1})
    except Exception as exc:
        logger.warning("autonomous_ops: response settings for %s could not be read: %s", tenant_id, exc)
        s.readable = False
        return s
    stored = (doc or {}).get("response")
    if stored is None:
        return s
    if not isinstance(stored, dict):
        s.readable = False
        return s
    if "twoSignal" in stored:
        if isinstance(stored["twoSignal"], bool):
            s.two_signal = stored["twoSignal"]
        else:
            s.readable = False
    if "blockHours" in stored:
        if _is_hours(stored["blockHours"]):
            s.block_hours = stored["blockHours"]
        else:
            s.readable = False
    if "watchedServices" in stored:
        names = stored["watchedServices"]
        if isinstance(names, list) and all(isinstance(n, str) for n in names):
            s.watched_services = list(names)
        else:
            s.readable = False
    return s
