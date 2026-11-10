"""One agent id per machine, for life.

A computer used to get a new random agent id whenever it enrolled without its agent's
secret: after a reinstall an administrator deleted the agent, and the next enrollment
started a stranger to the machine's history (EILT0197 had three ids on 2026-11-10). The
id is now remembered per tenant and hardware key (seat_identity: BIOS serial, else SMBIOS
UUID, else a physical network interface) in ``machine_identities``, which outlives the
agent record, so the machine enrolls again under the id it had.

Reusing an id without the agent's secret supersedes the install that held it: the caller
cuts off every token issued under it until then (authentication_service.
revoke_agent_tokens), so an old copy of the agent, or a token copied from one, stops
working. Machines with no hardware identity (a weak seat key) keep a random id.
"""
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, NamedTuple, Optional

from asset_identity import is_hardware_key

COLLECTION = "machine_identities"

RecordCheck = Callable[[Dict[str, Any]], Awaitable[bool]]


class KnownMachine(NamedTuple):
    agent_id: Optional[str]            # the id to enroll under; None for a new random one
    record: Optional[Dict[str, Any]]   # the machine's agent record to update, if it still has one
    supersedes: bool                   # tokens issued under agent_id until now must stop working


async def remembered_id(db, tenant_id: str, key: str) -> Optional[str]:
    if not is_hardware_key(key):
        return None
    doc = await getattr(db, "_db", db)[COLLECTION].find_one(
        {"tenantId": tenant_id, "hardwareKey": key}, {"agentId": 1})
    return doc.get("agentId") if doc else None


async def remember(db, tenant_id: str, key: str, agent_id: str, hostname: str) -> None:
    """Bind the machine to the agent that has just enrolled on it."""
    if not is_hardware_key(key):
        return
    now = datetime.now(timezone.utc).isoformat()
    await getattr(db, "_db", db)[COLLECTION].update_one(
        {"tenantId": tenant_id, "hardwareKey": key},
        {"$set": {"agentId": agent_id, "hostname": hostname, "updatedAt": now},
         "$setOnInsert": {"createdAt": now}},
        upsert=True,
    )


async def known_machine(db, tenant_id: str, key: str, proves: RecordCheck, is_live: RecordCheck) -> KnownMachine:
    """The id a machine enrolling under a name its tenant has no agent for gets back.

    ``proves(record)``: the caller presented that agent's secret or token.
    ``is_live(record)``: a seat-holding agent seen recently (spec C2), which is left alone
    so the duplicate check holds this enrollment as Pending instead.
    """
    known = await remembered_id(db, tenant_id, key)
    if not known:
        return KnownMachine(None, None, False)
    record = await getattr(db, "_db", db).agents.find_one({"id": known})
    if record is None:
        return KnownMachine(known, None, True)       # its agent was deleted: a new record, same id
    if record.get("tenantId") != tenant_id:
        return KnownMachine(None, None, False)       # that agent was moved to another tenant
    if await proves(record):
        return KnownMachine(known, record, False)    # its own agent, enrolling under a new name
    if await is_live(record):
        return KnownMachine(None, None, False)
    return KnownMachine(known, record, True)         # reinstalled or renamed: takes its record over


async def ensure_indexes(db) -> None:
    await getattr(db, "_db", db)[COLLECTION].create_index(
        [("tenantId", 1), ("hardwareKey", 1)], unique=True, name="one_id_per_machine")
