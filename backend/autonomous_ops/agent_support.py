"""What an enrolled agent can do for Autonomous Ops response actions (Phase 83, D-13).

The agent contract lives in ``shared/agent-response-contract.json``; the backend tests and the
Rust agent tests read the same file. ``check`` answers whether one host can carry out one command
right now, so the sweep produces no row for a host that cannot (dormant means silent), and the
reason is one of three plain codes: ``capability_off`` (the tenant has not ticked the agent
capability that carries the command), ``agent_offline`` (not Online, or not seen in 5 minutes) and
``agent_unsupported`` (the agent does not report the token the command needs).

Reads only. The tenant's capability list is read through the raw handle with an explicit tenantId;
the ambient tenant ContextVar is never used.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Set

import agent_capabilities

from .scope import raw

logger = logging.getLogger(__name__)

_CONTRACT_PATH = Path(__file__).resolve().parent.parent.parent / "shared" / "agent-response-contract.json"
ONLINE_WITHIN = timedelta(minutes=5)


def _load(path: Path = _CONTRACT_PATH) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


CONTRACT: Dict[str, Any] = _load()


def token_for(command: Any) -> Optional[str]:
    """The agent token a command needs, or None for a command the contract does not name."""
    return CONTRACT["commandToken"].get(command) if isinstance(command, str) else None


def tokens_of(agent: Optional[Dict[str, Any]]) -> Set[str]:
    """The response-action tokens an agent reported in its heartbeat (``meta.response_actions.tokens``)."""
    meta = (agent or {}).get("meta")
    actions = meta.get("response_actions") if isinstance(meta, dict) else None
    tokens = actions.get("tokens") if isinstance(actions, dict) else None
    return {t for t in tokens if isinstance(t, str)} if isinstance(tokens, list) else set()


def _parse_time(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def online(agent: Optional[Dict[str, Any]], now: datetime) -> bool:
    """Status Online (any case) and a lastSeen within 5 minutes; a missing or unparsable lastSeen is offline."""
    if not isinstance(agent, dict) or str(agent.get("status") or "").strip().casefold() != "online":
        return False
    seen = _parse_time(agent.get("lastSeen"))
    if seen is None:
        return False
    now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return now - seen <= ONLINE_WITHIN


async def check(db, tenant_id: str, agent: Optional[Dict[str, Any]], command: str, *,
                now: datetime) -> Optional[str]:
    """None when the host can carry out ``command`` now, else capability_off, agent_offline or
    agent_unsupported (first match in that order). A capability lookup that fails counts as off."""
    capability = agent_capabilities.instruction_capability({"type": command})
    if capability:
        try:
            permitted = await agent_capabilities.allowed_for(raw(db), tenant_id)
        except Exception as exc:
            logger.error("autonomous_ops: capability lookup for %s failed: %s", tenant_id, exc)
            return "capability_off"
        if capability not in permitted:
            return "capability_off"
    if not online(agent, now):
        return "agent_offline"
    token = token_for(command)
    if token is None or token not in tokens_of(agent):
        return "agent_unsupported"
    return None
