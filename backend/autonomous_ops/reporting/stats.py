"""Statistics and time saved over the decision ledger (Phase 86, ACTV-05, ACTV-07, D-05..D-08, D-19).

Skeleton for the failing-test commit: every function exists and answers an empty value.
"""
from typing import Any, Dict, List, Optional


async def compute(db, tenant_id: str, *, days: Optional[int], now=None) -> List[Dict[str, Any]]:
    return []


def fold(groups) -> Dict[str, Any]:
    return {"rules": [], "totals": {}}


def time_saved(groups) -> Dict[str, Any]:
    return {}


def format_minutes(minutes: int) -> str:
    return ""


async def statistics_payload(db, caller, tenant_id: str, days: int, now=None) -> Dict[str, Any]:
    return {}
