"""Hardware identity for agent seats (spec C2).

A seat is tied to the machine, not its hostname, so renames and reinstalls reuse
it. Precedence: BIOS serial, then SMBIOS UUID, then the primary physical MAC.
Agents that send no ``hardware`` block (pre-hardware builds) fall back to their
hostname-derived ``device_id`` and are marked weak.

Pure: standard library only, no I/O.
"""
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

# Firmware placeholders that many OEMs and hypervisors ship instead of a serial.
_JUNK_SERIALS = frozenset({
    "", "0", "none", "null", "n/a", "na", "not available", "not specified", "unknown",
    "to be filled by o.e.m.", "to be filled by oem", "default string", "system serial number",
    "123456789", "1234567890", "0123456789", "chassis serial number", "invalid", "oem",
})
_JUNK_UUIDS = frozenset({
    "00000000-0000-0000-0000-000000000000", "ffffffff-ffff-ffff-ffff-ffffffffffff",
    "03000200-0400-0500-0006-000700080009",  # common AMI placeholder
})
_MAC_RE = re.compile(r"^([0-9a-f]{2}[:-]){5}[0-9a-f]{2}$")


def normalize_serial(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    v = value.strip()
    if v.lower() in _JUNK_SERIALS or len(set(v.replace("-", ""))) <= 1:
        return None
    return v.upper()


def normalize_uuid(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    if len(v.replace("-", "")) < 16 or v in _JUNK_UUIDS:
        return None
    return v


def normalize_mac(value: Any) -> Optional[str]:
    """Lower-case colon form; None for malformed, all-zero, multicast or locally administered."""
    if not isinstance(value, str):
        return None
    v = value.strip().lower().replace("-", ":")
    if not _MAC_RE.match(v) or v == "00:00:00:00:00:00":
        return None
    first_octet = int(v[:2], 16)
    if first_octet & 0x01 or first_octet & 0x02:  # multicast / locally administered (virtual)
        return None
    return v


def normalize_hardware(hardware: Any) -> Dict[str, Any]:
    """The identity fields of an agent's ``hardware`` block, normalized; junk dropped."""
    hw = hardware if isinstance(hardware, dict) else {}
    macs: List[str] = []
    for m in hw.get("macAddresses") or []:
        n = normalize_mac(m)
        if n and n not in macs:
            macs.append(n)
    out: Dict[str, Any] = {
        "serialNumber": normalize_serial(hw.get("serialNumber")),
        "smbiosUuid": normalize_uuid(hw.get("smbiosUuid")),
        "macAddresses": macs,
    }
    for key in ("osFamily", "osName", "osVersion", "deviceType", "loggedInUser"):
        if isinstance(hw.get(key), str) and hw[key].strip():
            out[key] = hw[key].strip()[:200]
    return out


def seat_key(hardware: Dict[str, Any], device_id: Any = None) -> str:
    """The identifier a seat is bound to. ``hardware`` must be normalized."""
    if hardware.get("serialNumber"):
        return f"serial:{hardware['serialNumber']}"
    if hardware.get("smbiosUuid"):
        return f"uuid:{hardware['smbiosUuid']}"
    if hardware.get("macAddresses"):
        return f"mac:{hardware['macAddresses'][0]}"
    return f"legacy:{device_id if isinstance(device_id, str) and device_id else 'unknown'}"


def identity_strength(key: str) -> str:
    """'strong' for serial/UUID, 'medium' for MAC, 'weak' for legacy device ids."""
    if key.startswith(("serial:", "uuid:")):
        return "strong"
    return "medium" if key.startswith("mac:") else "weak"


def hardware_match_filter(tenant_id: str, hardware: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Mongo filter for agents in the tenant whose serial or SMBIOS UUID matches; None if
    neither is known (a MAC alone is too easily cloned to transfer a seat)."""
    terms = []
    if hardware.get("serialNumber"):
        terms.append({"hardware.serialNumber": hardware["serialNumber"]})
    if hardware.get("smbiosUuid"):
        terms.append({"hardware.smbiosUuid": hardware["smbiosUuid"]})
    if not terms:
        return None
    return {"tenantId": tenant_id, "$or": terms}


def hardware_match_other_tenants_filter(hardware: Dict[str, Any], exclude_tenant_id: str,
                                        non_seat_statuses: Optional[Iterable[str]] = None) -> Optional[Dict[str, Any]]:
    """Mongo filter for agents in every tenant but ``exclude_tenant_id`` whose serial or SMBIOS UUID matches,
    limited to seat-holding agents when ``non_seat_statuses`` is given (passed in: this module stays pure and
    cannot import licensing). None when neither identifier is known; a MAC alone never matches (D-35).
    Run it on the raw collection: the request's tenant wrapper would scope it to the enrolling tenant."""
    terms = []
    if hardware.get("serialNumber"):
        terms.append({"hardware.serialNumber": hardware["serialNumber"]})
    if hardware.get("smbiosUuid"):
        terms.append({"hardware.smbiosUuid": hardware["smbiosUuid"]})
    if not terms:
        return None
    flt: Dict[str, Any] = {"tenantId": {"$ne": exclude_tenant_id}}
    if non_seat_statuses is not None:
        flt["status"] = {"$nin": sorted(non_seat_statuses)}
    flt["$or"] = terms
    return flt


def seen_within(agent: Dict[str, Any], window: timedelta, now: Optional[datetime] = None) -> bool:
    """Whether the agent's ``lastSeen`` is less than ``window`` old; an unreadable time is not recent."""
    try:
        last = datetime.fromisoformat(str(agent.get("lastSeen")).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (now or datetime.now(timezone.utc)) - last < window
