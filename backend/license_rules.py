"""Enrollment controls beyond the seat count (spec C4).

A new enrollment is checked, in order, against: license expiry (``license_expired``),
the hardware allowlist (``not_allowlisted``), the OS-class sub-limit
(``sublimit:os:<class>``) and the install key's default-group sub-limit
(``sublimit:group:<id>``). The first rule it fails holds it Pending with that reason;
the total seat limit (licensing.try_claim_seat) still applies after all of them.
Agents already enrolled are never re-checked: an expired license or a full sub-limit
stops new machines, it does not suspend running ones.

Sub-limits count seat-holding agents at the moment of enrollment. Unlike the total
seat counter this check is not atomic, so concurrent installs of the same class can
overshoot a sub-limit by the number racing; the total limit can never be exceeded.
"""
import logging
import math
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import agent_allowlist
import licensing

logger = logging.getLogger(__name__)

REASON_EXPIRED = "license_expired"
REASON_NOT_ALLOWLISTED = "not_allowlisted"
REASON_KEY_EXHAUSTED = "key_exhausted"

OS_CLASSES = ("windows_workstation", "windows_server", "linux", "macos")
_SUBLIMIT_KEY = re.compile(r"^(os:(windows_workstation|windows_server|linux|macos)|group:[A-Za-z0-9_-]{1,64})$")
MAX_SUBLIMITS = 50
EXPIRY_REMINDER_DAYS = (30, 7, 1)


def _raw(db):
    return getattr(db, "_db", db)


def os_class(hardware: Optional[Dict[str, Any]], platform: Any = None) -> Optional[str]:
    """windows_workstation | windows_server | linux | macos, or None when unknown.
    Windows servers are told apart by the OS name or a server chassis: most run as VMs."""
    hw = hardware or {}
    family = str(hw.get("osFamily") or platform or "").strip().lower()
    if family.startswith("win"):
        name = f"{hw.get('osName') or ''} {hw.get('osVersion') or ''}".lower()
        return "windows_server" if "server" in name or hw.get("deviceType") == "server" else "windows_workstation"
    if family.startswith("linux"):
        return "linux"
    if family in ("macos", "darwin", "mac", "osx"):
        return "macos"
    return None


class ControlError(ValueError):
    pass


async def validate_sub_limits(db, tenant_id: str, sub_limits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalized sub-limits; raises ControlError naming the bad entry."""
    if len(sub_limits) > MAX_SUBLIMITS:
        raise ControlError(f"at most {MAX_SUBLIMITS} sub-limits")
    out, keys = [], set()
    for item in sub_limits:
        key, cap = str(item.get("key") or ""), item.get("max")
        if not _SUBLIMIT_KEY.match(key):
            raise ControlError(f"subLimits: unknown key {key[:80]!r} (os:<class> or group:<agentGroupId>)")
        if not isinstance(cap, int) or isinstance(cap, bool) or not 0 <= cap <= licensing.MAX_AGENTS_CEILING:
            raise ControlError(f"subLimits: max for {key} must be a whole number from 0 to {licensing.MAX_AGENTS_CEILING}")
        if key in keys:
            raise ControlError(f"subLimits: {key} is listed twice")
        if key.startswith("group:") and not await _raw(db).agent_groups.find_one(
                {"id": key[6:], "tenantId": tenant_id}, {"_id": 1}):
            raise ControlError(f"subLimits: agent group {key[6:]} does not exist in this tenant")
        keys.add(key)
        out.append({"key": key, "max": cap})
    return out


def _cap(lic: Dict[str, Any], key: str) -> Optional[int]:
    return next((s["max"] for s in lic["subLimits"] if s.get("key") == key and isinstance(s.get("max"), int)), None)


async def _seat_holders_of_class(raw, tenant_id: str, cls: str) -> int:
    count = 0
    async for agent in raw.agents.find(licensing.seat_holding_filter(tenant_id),
                                       {"_id": 0, "hardware": 1, "platform": 1}):
        if os_class(agent.get("hardware"), agent.get("platform")) == cls:
            count += 1
    return count


async def group_seat_holders(db, tenant_id: str, group_id: str) -> int:
    raw = _raw(db)
    ids = await raw.agent_group_members.distinct("agent_id", {"group_id": group_id, "tenantId": tenant_id})
    if not ids:
        return 0
    return await raw.agents.count_documents({**licensing.seat_holding_filter(tenant_id), "id": {"$in": ids}})


async def group_room(db, tenant: Dict[str, Any], group_id: str) -> Optional[int]:
    """Free places under the group's sub-limit, or None when it has none."""
    cap = _cap(licensing.license_of(tenant), f"group:{group_id}")
    if cap is None:
        return None
    return max(0, cap - await group_seat_holders(db, tenant["id"], group_id))


def expired(lic: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    if not lic.get("expiresAt"):
        return False
    try:
        at = datetime.fromisoformat(lic["expiresAt"].replace("Z", "+00:00"))
    except ValueError:
        return False
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return (now or datetime.now(timezone.utc)) >= at


async def hold_reason(db, tenant: Dict[str, Any], hardware: Dict[str, Any], platform: Any,
                      default_group_id: Optional[str] = None) -> Optional[str]:
    """Why a new enrollment must wait for approval, or None when the C4 controls admit it."""
    raw = _raw(db)
    fresh = await raw.tenants.find_one({"id": tenant["id"]}) or tenant
    lic = licensing.license_of(fresh)
    if expired(lic):
        return REASON_EXPIRED
    if lic["allowlistMode"] == "enforce" and not await agent_allowlist.matches(db, tenant["id"], hardware):
        return REASON_NOT_ALLOWLISTED
    cls = os_class(hardware, platform)
    cap = _cap(lic, f"os:{cls}") if cls else None
    if cap is not None and await _seat_holders_of_class(raw, tenant["id"], cls) >= cap:
        return f"sublimit:os:{cls}"
    if default_group_id and await group_room(db, fresh, default_group_id) == 0:
        return f"sublimit:group:{default_group_id}"
    return None


async def join_group(db, tenant_id: str, group_id: str, agent_id: str, actor: str) -> None:
    """Membership for an agent enrolled with a key that names a default group."""
    raw = _raw(db)
    if not await raw.agent_groups.find_one({"id": group_id, "tenantId": tenant_id}, {"_id": 1}):
        return
    if await raw.agent_group_members.find_one({"group_id": group_id, "agent_id": agent_id, "tenantId": tenant_id}):
        return
    await raw.agent_group_members.insert_one({
        "id": str(uuid.uuid4()), "tenantId": tenant_id, "group_id": group_id, "agent_id": agent_id,
        "added_at": datetime.now(timezone.utc).isoformat(), "added_by": actor})


async def send_expiry_reminders(db, now: Optional[datetime] = None) -> int:
    """Alert platform staff and tenant admins 30, 7 and 1 days before a license expires,
    once per threshold. Returns how many reminders went out."""
    import pending_agents  # cycle: pending_agents -> licensing only
    raw = _raw(db)
    now = now or datetime.now(timezone.utc)
    sent = 0
    async for tenant in raw.tenants.find({"license.expiresAt": {"$type": "string"}},
                                         {"_id": 0, "id": 1, "name": 1, "license": 1, "maxAgents": 1}):
        lic = licensing.license_of(tenant)
        if expired(lic, now):
            continue
        try:
            at = datetime.fromisoformat(lic["expiresAt"].replace("Z", "+00:00"))
        except ValueError:
            continue
        at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
        done = set((tenant.get("license") or {}).get("expiryRemindersSent") or [])
        due = [d for d in EXPIRY_REMINDER_DAYS if at - now <= timedelta(days=d) and d not in done]
        if not due:
            continue
        threshold = min(due)  # one reminder for the closest threshold crossed
        res = await raw.tenants.update_one(
            {"id": tenant["id"], "license.expiryRemindersSent": {"$nin": [threshold]}},
            {"$addToSet": {"license.expiryRemindersSent": {"$each": due}}})
        if res.modified_count != 1:
            continue
        label = tenant.get("name") or tenant["id"]
        days_left = max(1, math.ceil((at - now) / timedelta(days=1)))
        await pending_agents.post_to_recipients(
            raw, tenant, f"Agent license for {label} expires in {days_left} day{'s' if days_left > 1 else ''}",
            f"The agent license of {label} expires on {at.date().isoformat()}. After that, new agents are held "
            "for approval; running agents keep working.", "warning",
            {"event": "license.expiry_reminder", "tenantId": tenant["id"], "daysLeft": days_left,
             "expiresAt": lic["expiresAt"], "threshold": threshold})
        sent += 1
    return sent
