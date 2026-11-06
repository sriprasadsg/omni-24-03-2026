"""Starting a rollout: choose the computers, snapshot the rings and claim every computer atomically.

``start_rollout`` is called by an operator (a person, never the controller). It refuses the Platform
tenant, a tenant with no maintenance window or fewer than two rings, and patch ids an agent could not
install. A computer is eligible when it is enrolled, runs Windows or Linux, reports it can restart
(``reboot_host``) and its boot time, and is not on the never-touch list. A computer already held by
another active rollout is left out and reported, never double-claimed (PTCH-07).

Plan 84-06 replaces the refusals with the full preflight; the signature stays.

Raw Mongo handle with an explicit tenantId only.
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .. import PLATFORM_TENANT_ID, agent_support, protected, settings
from ..scope import raw
from . import TOKEN_REBOOT, rings as rings_mod, store, windows as windows_mod

logger = logging.getLogger(__name__)

_KB = re.compile(r"^KB\d+$")
_AGENT_FIELDS = {"_id": 0, "id": 1, "tenantId": 1, "hostname": 1, "ipAddress": 1, "status": 1, "platform": 1,
                 "lastSeen": 1, "meta.response_actions": 1, "meta.response_state": 1,
                 "meta.system_patching": 1, "meta.os_patches": 1}


def refused(code: str, **extra: Any) -> Dict[str, Any]:
    return {"status": "refused", "reason": code, **extra}


def os_of(agent: Dict[str, Any]) -> Optional[str]:
    """"windows" or "linux" from the agent's platform text, else None."""
    text = str(agent.get("platform") or "").casefold()
    if "windows" in text:
        return "windows"
    return "linux" if "linux" in text else None


def pending_ids(agent: Dict[str, Any]) -> List[str]:
    """The installable ids the agent reports as pending (system patching scan and OS patch scan)."""
    from patch_core_endpoints import pending_entry_id
    meta = agent.get("meta") if isinstance(agent.get("meta"), dict) else {}
    found: List[str] = []
    for section, key in (("system_patching", "pending_updates"), ("os_patches", "items")):
        block = meta.get(section) if isinstance(meta.get(section), dict) else {}
        for entry in block.get(key) if isinstance(block.get(key), list) else []:
            patch_id = pending_entry_id(entry)
            if patch_id and patch_id not in found:
                found.append(patch_id)
    return found


def boot_time_of(agent: Dict[str, Any]) -> Optional[int]:
    meta = agent.get("meta") if isinstance(agent.get("meta"), dict) else {}
    state = meta.get("response_state") if isinstance(meta.get("response_state"), dict) else {}
    boot = state.get("boot_time")
    return boot if isinstance(boot, int) and not isinstance(boot, bool) else None


async def eligible_agents(db, tenant_id: str) -> List[Dict[str, Any]]:
    """The tenant's computers a rollout may touch, in a stable order."""
    out: List[Dict[str, Any]] = []
    found = raw(db).agents.find({"tenantId": tenant_id}, _AGENT_FIELDS)
    async for agent in found:
        if str(agent.get("status") or "").casefold() == "uninstalled" or os_of(agent) is None:
            continue
        if TOKEN_REBOOT not in agent_support.tokens_of(agent) or boot_time_of(agent) is None:
            continue
        if await protected.check(db, tenant_id, agent=agent):
            continue
        out.append(agent)
    return sorted(out, key=lambda a: (str(a.get("hostname") or "").casefold(), a["id"]))


async def start_rollout(db, tenant_id: str, *, name: str, patch_ids: List[str], actor: Dict[str, Any],
                        now: Optional[datetime] = None) -> Dict[str, Any]:
    """Start a rollout. Returns ``{"status": "started", "rolloutId", "claimed", "leftOut"}`` or
    ``{"status": "refused", "reason"}``. Nothing is installed here: the controller does that, inside a window."""
    from patch_core_endpoints import installable_patch_id
    now = store.aware(now or datetime.now(timezone.utc))
    if not isinstance(tenant_id, str) or not tenant_id or tenant_id == PLATFORM_TENANT_ID:
        return refused("platform_tenant")
    ids = [installable_patch_id(p) for p in patch_ids] if isinstance(patch_ids, list) else []
    if not ids or any(i is None for i in ids):
        return refused("invalid_patch_ids")
    ids = list(dict.fromkeys(ids))
    tenant_windows = await windows_mod.load(db, tenant_id)
    if not tenant_windows.readable or not tenant_windows.windows:
        return refused("no_window")
    configured = await rings_mod.load(db, tenant_id)
    if not configured.readable or len(configured.rings) < 2:
        return refused("no_rings")
    tenant = await settings.load(db, tenant_id)
    agents = await eligible_agents(db, tenant_id)
    placement = await rings_mod.membership(db, tenant_id, configured.rings, [a["id"] for a in agents])
    claims: List[Dict[str, Any]] = []
    for agent in agents:
        applicable = [p for p in pending_ids(agent) if p in ids]
        if applicable:
            claims.append({"agentId": agent["id"], "ring": placement[agent["id"]], "state": "waiting",
                           "os": os_of(agent), "hostname": agent.get("hostname"), "patchIds": applicable,
                           "attempt": 0, "createdAt": now})
    if not claims:
        return refused("no_hosts")
    rollout_id = uuid.uuid4().hex
    shadow, _ = settings.shadow_state(tenant)
    await store.rollouts(db).insert_one({
        "id": rollout_id, "tenantId": tenant_id, "name": str(name or "").strip()[:120], "patchIds": ids,
        "patchesByOs": {"windows": [i for i in ids if _KB.match(i)], "linux": [i for i in ids if not _KB.match(i)]},
        "status": "running", "shadow": shadow, "currentRing": 0,
        "rings": [r.snapshot(i) for i, r in enumerate(configured.rings)],
        "createdAt": now, "createdBy": {"id": (actor or {}).get("id"), "name": (actor or {}).get("name")}})
    claimed, left_out = await store.claim_hosts(db, tenant_id, rollout_id, claims)
    if not claimed:
        await store.rollouts(db).delete_one({"id": rollout_id, "tenantId": tenant_id})
        return refused("no_hosts", leftOut=left_out)
    return {"status": "started", "rolloutId": rollout_id, "claimed": claimed, "leftOut": left_out}
