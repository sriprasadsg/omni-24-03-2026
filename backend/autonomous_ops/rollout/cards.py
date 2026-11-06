"""Rollout approval cards for Needs your decision (Phase 84, plan 84-10, PTCH-06, D-07, D-08)."""
from datetime import datetime
from typing import Any, Dict, Optional


async def list_cards(db, tenant_id: str, caller, *, offset: int = 0, limit: int = 10,
                     now: Optional[datetime] = None) -> Dict[str, Any]:
    return {"items": [], "total": 0, "offset": offset, "limit": limit, "stopped": None, "serverNow": None,
            "countText": ""}
