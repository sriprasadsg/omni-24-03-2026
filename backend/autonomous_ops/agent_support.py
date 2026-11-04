"""What an enrolled agent can do for Autonomous Ops response actions (Phase 83, D-13).

The agent contract lives in ``shared/agent-response-contract.json``; the backend tests and the
Rust agent tests read the same file. ``check`` answers whether one host can carry out one command
right now, so the sweep produces no row for a host that cannot (dormant means silent), and the
reason is one of three plain codes: ``capability_off`` (the tenant has not ticked the agent
capability that carries the command), ``agent_offline`` (not Online, or not seen in 5 minutes) and
``agent_unsupported`` (the agent does not report the token the command needs).

``gate_step`` is the gate's dormancy step (RESP-10): for a ``security_response`` request that is not
only a suggestion it runs ``check`` for every target and step and refuses with that code, recording
nothing. ``approvals`` runs the same ``check`` again when a card is approved, which can be 24 hours later.
Support is read from the heartbeat's feature tokens and never from a version number: a 2.1.15 agent has
``block_ip`` in its code but not the ``block_ip_ttl`` token, so it would take the instruction and ignore
the time limit.

Reads only. The tenant's capability list is read through the raw handle with an explicit tenantId;
the ambient tenant ContextVar is never used.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Set

import agent_capabilities

from . import dispatch_check, registry
from .scope import raw

logger = logging.getLogger(__name__)

_CONTRACT_PATH = Path(__file__).resolve().parent.parent.parent / "shared" / "agent-response-contract.json"
ONLINE_WITHIN = timedelta(minutes=5)
_AGENT_FIELDS = {"_id": 0, "id": 1, "status": 1, "lastSeen": 1, "platform": 1, "meta.response_actions": 1}


def _load(path: Path = _CONTRACT_PATH) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


CONTRACT: Dict[str, Any] = _load()


def token_for(command: Any, params: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """The agent token a command needs, or None for a command the contract does not name. Params that
    name a network (``cidr``) need the range token instead of the single-address one."""
    if not isinstance(command, str):
        return None
    spec = registry.resolve(command)
    if spec is not None and isinstance(params, dict) and any(params.get(k) for k in spec.cidr_params):
        return CONTRACT["rangeToken"]
    return CONTRACT["commandToken"].get(command)


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
                now: datetime, params: Optional[Dict[str, Any]] = None) -> Optional[str]:
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
    token = token_for(command, params)
    if token is None or token not in tokens_of(agent):
        return "agent_unsupported"
    return None


async def reports_failing(db, tenant_id: str, agent_id: Any, service: Any) -> Optional[bool]:
    """Whether this tenant's computer still lists ``service`` in ``meta.service_failures`` (case-insensitive),
    or None when there is no such computer or no service name to look for."""
    agent = await raw(db).agents.find_one({"id": agent_id, "tenantId": tenant_id}, {"_id": 0, "meta.service_failures": 1})
    if agent is None or not isinstance(service, str):
        return None
    meta = agent.get("meta") if isinstance(agent.get("meta"), dict) else {}
    items = meta.get("service_failures") if isinstance(meta.get("service_failures"), list) else []
    return any(isinstance(i, dict) and isinstance(i.get("name"), str) and
               i["name"].strip().casefold() == service.casefold() for i in items)


async def agent_of(db, target: Any) -> Optional[Dict[str, Any]]:
    """The fields ``check`` reads for one agent id, or None when there is no such agent."""
    return await raw(db).agents.find_one({"id": target}, _AGENT_FIELDS)


async def gate_step(ctx) -> None:
    """The gate step after the protected-target step: a ``security_response`` request that is not a
    suggestion must be carried by every host it names (capability, online, token, in that order). The
    refusal is unrecorded: a dormant rule waits quietly and leaves no row. An unreadable agent counts as
    offline (fail closed). Every other dispatcher passes through untouched."""
    req = ctx.req
    if req.dispatcher != "security_response" or req.force_suggest:
        return
    try:
        for target in ctx.distinct:
            agent = await agent_of(ctx.db, target)
            for name, params in dispatch_check.request_steps(req):
                spec = registry.resolve(name)
                code = await check(ctx.db, req.tenant_id, agent, spec.name if spec else str(name),
                                   params=params, now=ctx.now)
                if code:
                    return ctx.refuse("agent_support", code, record=False)
    except Exception as exc:
        logger.error("autonomous_ops: agent support unreadable, treating the host as offline: %s", exc)
        return ctx.refuse("agent_support", "agent_offline", record=False)
    ctx.note("agent_support", "pass")
