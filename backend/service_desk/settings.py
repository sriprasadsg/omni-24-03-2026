"""The tenant's service desk setting (D-03): what is stored under ``autonomy_settings.serviceDesk``.

Nothing stored means Drafts only. A value that is not understood, or a read that fails, also reads
Drafts only with ``readable`` False, so the desk never posts on a setting it could not read. ``load``
never raises. Validation, saving and the status view come with 85-11.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from autonomous_ops.scope import raw

from . import DEFAULT_MODE, MODES

logger = logging.getLogger(__name__)


@dataclass
class DeskSettings:
    mode: str = DEFAULT_MODE
    words: List[str] = field(default_factory=list)
    breaker: Optional[Dict[str, Any]] = None
    readable: bool = True


async def load(db, tenant_id: str) -> DeskSettings:
    """The tenant's desk setting; absent reads Drafts only (D-03)."""
    try:
        doc = await raw(db).autonomy_settings.find_one({"tenantId": tenant_id}, {"_id": 0, "serviceDesk": 1})
    except Exception as exc:
        logger.warning("service_desk: settings for %s could not be read: %s", tenant_id, exc)
        return DeskSettings(readable=False)
    stored = (doc or {}).get("serviceDesk")
    if stored is None:
        return DeskSettings()
    if not isinstance(stored, dict):
        return DeskSettings(readable=False)
    mode = stored.get("mode", DEFAULT_MODE)
    result = DeskSettings()
    if isinstance(mode, str) and mode in MODES:
        result.mode = mode
    else:
        result.readable = False
    words = stored.get("words")
    if isinstance(words, list):
        result.words = [w for w in words if isinstance(w, str)]
    breaker = stored.get("breaker")
    result.breaker = breaker if isinstance(breaker, dict) else None
    return result
