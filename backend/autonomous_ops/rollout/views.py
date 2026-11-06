"""Payload builders for the Rollouts tab (plan 84-09). Skeleton: every builder answers neutrally until the
implementation lands."""
from typing import Any, Dict, List, Tuple


async def build_caller(user, tenant_id, tenant):
    return None


async def rollout_page(db, tenant_id, caller, offset, limit, now) -> Dict[str, Any]:
    return {"items": [], "total": 0, "offset": offset, "limit": limit, "attentionCount": 0, "window": {},
            "flags": {}, "ringsSet": False, "ringsSummary": ""}


async def rollout_card(db, tenant_id, rollout, caller, now) -> Dict[str, Any]:
    return {}


async def window_strip(db, tenant_id, now) -> Dict[str, Any]:
    return {}


async def rings_summary(db, tenant_id) -> Tuple[bool, str]:
    return False, ""
