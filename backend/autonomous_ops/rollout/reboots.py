"""Restarts of a rollout (Phase 84, D-07, D-08, D-17): the Reboot line, the boot baseline, the new-boot check.

Skeleton for the failing-test commit: the functions exist with the signatures the tests call and answer
"nothing happened" until the implementation commit.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from . import BOOT_TOLERANCE_SECONDS


def is_new_boot(agent: Optional[Dict[str, Any]], host: Dict[str, Any],
                tolerance: int = BOOT_TOLERANCE_SECONDS) -> Optional[bool]:
    return None


def overdue(host: Dict[str, Any], now: datetime) -> bool:
    return False


async def raise_reboot_line(db, tenant_id: str, rollout: Dict[str, Any], ring: int, hosts: List[Dict[str, Any]],
                            now: datetime) -> Dict[str, int]:
    return {"raised": 0, "simulated": 0, "skipped": 0}


async def record_baseline(db, tenant_id: str, host: Dict[str, Any], agent: Optional[Dict[str, Any]],
                          dispatched_at: datetime) -> None:
    return None
