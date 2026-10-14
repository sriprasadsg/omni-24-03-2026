"""Per-tenant agent capabilities.

A Super Admin ticks the capabilities a tenant's agents may use (Manage Tenant); the list lives
in ``tenants.agentCapabilities``. The catalogue is ``shared/agent-capabilities.json``, which the
Manage Tenant and agent screens read too.

Rules:
  * ``"all"`` in the list allows every capability; the Platform tenant always has every one;
  * a missing tenant, a missing list or a failed lookup allows only the always-on capabilities
    (fail closed); always-on capabilities (agent self-update) are allowed whatever the list says;
  * for a capability that is not allowed the platform drops its heartbeat data, refuses to hand
    the agent an instruction that needs it, and leaves it out of the configuration agents pull.
Names outside the catalogue are never touched: heartbeat keys and instructions the catalogue does
not name pass as before.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, List, Optional

logger = logging.getLogger(__name__)

_CATALOGUE_PATH = Path(__file__).resolve().parent.parent / "shared" / "agent-capabilities.json"
ALL_CAPABILITIES = "all"
PLATFORM_TENANT_ID = "platform-admin"
REFUSED = "refused"


def _load(path: Path = _CATALOGUE_PATH) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        catalogue = json.load(handle)
    entries = [cap for group in catalogue["groups"] for cap in group["capabilities"]]
    ids = [cap["id"] for cap in entries]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate agent capability in {path.name}")
    return entries


_ENTRIES = _load()
CAPABILITY_IDS: FrozenSet[str] = frozenset(cap["id"] for cap in _ENTRIES)
ALWAYS_ON: FrozenSet[str] = frozenset(cap["id"] for cap in _ENTRIES if cap.get("alwaysOn"))

# Heartbeat keys that carry a capability's data under another name.
_DATA_KEYS: Dict[str, str] = {"software_inventory": "software_management", "installed_software": "software_management"}

# Instruction names (normalised: lower case, text before ":", spaces as "_") -> the capability
# the agent uses to carry them out. Prefix entries end in "*".
_INSTRUCTIONS: Dict[str, str] = {
    "enable_rdp": "remote_access", "disable_rdp": "remote_access", "start_remote_session*": "remote_access",
    "network_scan": "network_discovery", "start_network_scan": "network_discovery",
    "scan_file": "virustotal_scan", "scan_url": "virustotal_scan", "scan_hash": "virustotal_scan",
    "scan_ip": "virustotal_scan", "security_scan": "virustotal_scan",
    "install_software": "software_management", "upgrade_software": "software_management",
    "run_software_scan": "software_management", "install": "software_management",
    "uninstall": "software_management", "upgrade": "software_management", "staged_deployment": "software_management",
    "install_patches": "patch_installer", "rollback_patches": "patch_installer", "os_patch_install": "patch_installer",
    "os_patch_rollback": "patch_installer", "patch_deployment": "patch_installer", "patch_rollback": "patch_installer",
    "run_compliance_scan": "compliance_enforcement", "run_compliance_check": "compliance_enforcement",
    "vulnerability_scan": "vulnerability_scanning", "run_vulnerability_scan": "vulnerability_scanning",
    "run_persistence_scan": "persistence_detection", "log_collection": "log_collection",
    "kill_process": "remediation_executor", "restore_file": "remediation_executor", "block_ip": "remediation_executor",
    "unblock_ip": "remediation_executor", "disable_service": "remediation_executor",
    "enable_service": "remediation_executor", "rotate_key": "remediation_executor",
    "rotate_key_rollback": "remediation_executor", "isolate_host": "remediation_executor",
    "autonomous_remediation": "autonomous_response",
    "start_agent_chat": "chat_window", "agent_chat_message": "chat_window", "close_agent_chat": "chat_window",
    "create_ticket": "ticket_reporter", "report_ticket": "ticket_reporter", "ticket_created": "ticket_reporter",
    "create_vss_snapshot": "vss_manager", "run_vss_rollback_check": "vss_manager",
    "process_injection": "process_injection_simulation",
}
_PREFIXES = [(name[:-1], cap) for name, cap in _INSTRUCTIONS.items() if name.endswith("*")]


def allowed(tenant: Optional[Dict[str, Any]]) -> FrozenSet[str]:
    """The capabilities a tenant's agents may use."""
    if tenant and tenant.get("id") == PLATFORM_TENANT_ID:
        return CAPABILITY_IDS
    chosen = (tenant or {}).get("agentCapabilities")
    if not isinstance(chosen, list):
        return ALWAYS_ON
    if ALL_CAPABILITIES in chosen:
        return CAPABILITY_IDS
    return frozenset(c for c in chosen if c in CAPABILITY_IDS) | ALWAYS_ON


async def allowed_for(db, tenant_id: Optional[str]) -> FrozenSet[str]:
    """``allowed`` for a tenant id; a failed lookup counts as no list (fail closed)."""
    if not tenant_id:
        return ALWAYS_ON
    raw = getattr(db, "_db", db)
    try:
        tenant = await raw.tenants.find_one({"id": tenant_id}, {"_id": 0, "id": 1, "agentCapabilities": 1})
    except Exception as exc:
        logger.warning("Agent capability lookup failed for tenant %s (allowing only always-on): %s", tenant_id, exc)
        return ALWAYS_ON
    return allowed(tenant)


def validate(chosen: Iterable[Any]) -> List[str]:
    """A Super Admin's selection, checked: catalogue ids (or "all") only, always-on ones added."""
    chosen = list(chosen)
    if any(not isinstance(c, str) for c in chosen):
        raise ValueError("agentCapabilities must be a list of capability ids")
    if ALL_CAPABILITIES in chosen:
        return [ALL_CAPABILITIES]
    unknown = sorted(set(chosen) - CAPABILITY_IDS)
    if unknown:
        raise ValueError(f"Unknown agent capabilities: {', '.join(unknown)}")
    return sorted(set(chosen) | ALWAYS_ON)


def assert_allowed(tenant: Optional[Dict[str, Any]], capability: str) -> None:
    """403 for an agent upload of ``capability`` data when its tenant (the verify_agent_key result)
    does not have the capability."""
    if capability not in allowed(tenant):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail=f"Agent capability {capability} is not enabled for this organization")


def every_capability() -> List[str]:
    """What a new tenant starts with: every capability, named one by one."""
    return sorted(CAPABILITY_IDS)


def strip_heartbeat(payload: Dict[str, Any], permitted: FrozenSet[str]) -> List[str]:
    """Remove the data of every capability outside ``permitted`` from the heartbeat's meta, in
    place; returns the capabilities whose data was dropped."""
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return []
    dropped = set()
    for key in list(meta):
        cap = key if key in CAPABILITY_IDS else _DATA_KEYS.get(key)
        if cap and cap not in permitted:
            del meta[key]
            dropped.add(cap)
    return sorted(dropped)


def _normalise(name: Any) -> str:
    return str(name or "").split(":", 1)[0].strip().lower().replace(" ", "_").replace("-", "_")


def instruction_capability(instruction: Dict[str, Any]) -> Optional[str]:
    """The catalogue capability an agent instruction needs, or None when it names none."""
    for field in ("instruction", "type", "action"):
        name = _normalise(instruction.get(field))
        if not name:
            continue
        if name in _INSTRUCTIONS:
            return _INSTRUCTIONS[name]
        for prefix, cap in _PREFIXES:
            if name.startswith(prefix):
                return cap
    return None


async def hold_back(db, tenant_id: Optional[str], instructions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The instructions the agent may receive. Each one that needs a capability the tenant does
    not have is marked refused (never delivered) instead."""
    if not instructions:
        return instructions
    permitted = await allowed_for(db, tenant_id)
    deliver, refused = [], []
    for instr in instructions:
        cap = instruction_capability(instr)
        (refused if cap and cap not in permitted else deliver).append((instr, cap))
    for instr, cap in refused:
        logger.info("Refused instruction %r for agent %s: capability %s is not enabled for tenant %s",
                    instr.get("instruction") or instr.get("type"), instr.get("agent_id"), cap, tenant_id)
        await db.agent_instructions.update_one(
            {"_id": instr["_id"]},
            {"$set": {"status": REFUSED, "error": f"capability_not_enabled: {cap}",
                      "refused_at": datetime.now(timezone.utc).isoformat()}})
    return [instr for instr, _ in deliver]
