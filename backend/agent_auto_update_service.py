"""
Auto-push `agent_update` instruction when an agent heartbeats an outdated
binary version.

Extracted from agent_heartbeat_endpoints.py (CLAUDE.md-driven adjustment,
Phase 46 Plan 05, Rule 2) — the endpoint file was already at 517 lines pre-
existing this plan (over the 500-line cap from an earlier, unrelated
commit), and this plan's own acceptance criteria requires it stay under 500
after the ASN/location-history wiring lands. This block was self-contained
(only needs db, agent_id, payload) and had no dependency on the surrounding
heartbeat logic, making it a clean, behavior-preserving extraction.
"""
import re
import logging
from datetime import datetime, timezone

logger = logging.getLogger("agent_auto_update_service")

_LATEST_AGENT_VERSION = "2.1.4"
_MIN_SELF_UPDATE_VERSION = (2, 0, 5)


def _parse_ver(v: str):
    m = re.match(r"(\d+)\.(\d+)\.(\d+)", v or "")
    return tuple(int(g) for g in m.groups()) if m else None


async def maybe_push_update_instruction(db, agent_id: str, payload: dict) -> None:
    """Windows-only: the published update binary is the Windows rust agent;
    pushing to other platforms just generates "unavailable" instruction noise.

    Only push to agents whose self-updater actually works. The updater resolves
    its own service by binary path (rather than a hardcoded name) starting in
    2.0.5 (commit 1439b2e1); before that it ran `net stop OmniAgent`, which
    silently fails on hosts installed as the "OmniAgentRust" service — the swap
    never happens and the agent re-reports the old version forever. Pushing to
    those hosts only spams the instruction history; they require a one-time
    manual reinstall instead.
    """
    _reported_version = payload.get("version", "")
    _rv = _parse_ver(_reported_version)
    if not (_reported_version and _reported_version != _LATEST_AGENT_VERSION
            and payload.get("platform") == "Windows"
            and _rv is not None and _rv >= _MIN_SELF_UPDATE_VERSION):
        return

    # Dedup against pending AND sent: auto-pushed instructions flip to "sent" as
    # soon as the agent polls, so checking only "pending" would insert a new row
    # on every heartbeat until the agent finishes updating.
    _existing = await db.agent_instructions.find_one(
        {"agent_id": agent_id, "instruction": "agent_update",
         "status": {"$in": ["pending", "sent"]}}
    )
    if not _existing:
        await db.agent_instructions.insert_one({
            "agent_id": agent_id,
            "instruction": "agent_update",
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "auto_update",
            "priority": "normal",
        })
        logger.info("Auto-pushed agent_update instruction to %s (reported %s < %s)",
                    agent_id, _reported_version, _LATEST_AGENT_VERSION)
