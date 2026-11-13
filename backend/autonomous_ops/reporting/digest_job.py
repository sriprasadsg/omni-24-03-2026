"""The 07:00 UTC digest loop (Phase 86, ACTV-04). Skeleton: the behaviour arrives with the next commit."""
from datetime import datetime
from typing import Dict, Optional

LOCK_NAME = "autonomous_ops_digest"
LOCK_TTL_SECONDS = 120
LOCK_RENEW_EVERY = 30
WAKE_EVERY = 300
STARTUP_DELAY = 120


async def _sleep(seconds):
    return None


def due(now: datetime) -> bool:
    return False


async def run_once(db, *, now: Optional[datetime] = None) -> Optional[Dict[str, int]]:
    return None


async def digest_loop() -> None:
    return None
