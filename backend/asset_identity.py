"""Which asset a computer's agent reports into.

An asset used to be found by name alone (``asset-{hostname}``): a different
computer given the same name took over its record and history, a renamed
computer got a second asset, and a same-named computer in another tenant got
none (asset ids are unique across the platform). An asset now belongs to the
machine's hardware: the seat key from seat_identity (BIOS serial, else SMBIOS
UUID, else a physical network interface), kept on the asset as ``hardwareKey``.

The id stays ``asset-{hostname}`` whenever that is free or already this
machine's, so existing assets keep their ids and history.
"""
import uuid
from typing import Any, Dict, Optional

import seat_identity

HARDWARE_KEY_PREFIXES = ("serial:", "uuid:", "mac:")


def is_hardware_key(key: Any) -> bool:
    """A seat key that names the machine itself (not a hostname-derived device id)."""
    return isinstance(key, str) and key.startswith(HARDWARE_KEY_PREFIXES)


def _belongs_elsewhere(asset: Dict[str, Any], tenant_id: str, key: str, hardware: Dict[str, Any]) -> bool:
    """Whether an existing asset is another machine's (or another tenant's)."""
    if asset.get("tenantId") != tenant_id:
        return True
    bound = asset.get("hardwareKey")
    if bound:
        return bound != key
    # Unbound (made before hardware binding): its recorded serial decides.
    recorded = seat_identity.normalize_serial(asset.get("serialNumber"))
    if not recorded or not is_hardware_key(key):
        return False
    return recorded != hardware.get("serialNumber")


async def resolve_asset_id(db, tenant_id: str, hostname: str, hardware: Dict[str, Any], key: str) -> str:
    """The id of this machine's asset in the tenant; a new id when it has none yet.

    ``hardware`` is seat_identity-normalized and ``key`` its seat key. Reads the raw
    collection: asset ids are unique across tenants, so a name taken in another
    tenant must be seen to be avoided.
    """
    raw = getattr(db, "_db", db)
    if is_hardware_key(key):
        found = await raw.assets.find_one({"tenantId": tenant_id, "hardwareKey": key}, {"id": 1})
        if found:
            return found["id"]
        # A machine first bound by its network interface keeps that asset once it
        # reports a serial or UUID.
        macs = [f"mac:{m}" for m in hardware.get("macAddresses") or []]
        if macs and not key.startswith("mac:"):
            found = await raw.assets.find_one({"tenantId": tenant_id, "hardwareKey": {"$in": macs}}, {"id": 1})
            if found:
                return found["id"]

    legacy = f"asset-{hostname}"
    named = await raw.assets.find_one({"id": legacy}, {"tenantId": 1, "hardwareKey": 1, "serialNumber": 1})
    if named is None or not _belongs_elsewhere(named, tenant_id, key, hardware):
        return legacy
    return f"{legacy}-{uuid.uuid4().hex[:8]}"


def hardware_key_field(key: Optional[str]) -> Dict[str, str]:
    """``{"hardwareKey": key}`` for an asset update, or nothing for a weak key."""
    return {"hardwareKey": key} if is_hardware_key(key) else {}
