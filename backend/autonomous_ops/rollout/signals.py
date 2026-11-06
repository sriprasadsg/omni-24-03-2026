"""Per-computer signals for the rollout health gate (Phase 84, PTCH-02).

Skeleton for the failing-test commit: ``host_signals`` exists with its final signature and answers "no
data" for every signal until the implementation commit.
"""
from datetime import datetime
from typing import Any, Dict, Iterable, Optional


async def host_signals(db, tenant_id: str, rollout: Dict[str, Any], host: Dict[str, Any],
                       agent: Optional[Dict[str, Any]], watched: Optional[Iterable[str]], capabilities: Iterable[str],
                       now: datetime) -> Dict[str, Any]:
    return {"agentId": host["agentId"], "state": host.get("state"), "failed": False, "reported": False,
            "install": None, "inventory": None, "heartbeat": None, "services": None}
