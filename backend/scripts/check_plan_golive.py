"""Read-only go-live check for migration 034 (Phase 88, LIC-01, LIC-03, LIC-04, LIC-05, LIC-06).

Run it after the backend restart that applies migration 034::

    backend/venv/bin/python backend/scripts/check_plan_golive.py [--url mongodb://127.0.0.1:27017] [--db omni_platform]

It reads the database and writes nothing. It prints one line per tenant (name, plan, seats, seat override,
trial end, allowed networks), then one ``FAIL ...`` line per unmet expectation, then ``OK`` when there is none.
The exit code is 0 when every expectation holds and 1 otherwise.

Expectations: migration 034 is recorded; the four plans exist; every direct tenant has its old seat number
recorded and holds its plan's seats or its own override; the platform organization has no such record; every
tenant except partner organizations and the platform has a trial (a Free one with an end); every admitted
agent's public address is inside its tenant's allowed networks; the agents collection has both sparse
hardware indexes.
"""
import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

PLATFORM_ID = "platform-admin"
HARDWARE_INDEXES = ("agents_hw_serial_sparse", "agents_hw_uuid_sparse")
NOT_ADMITTED = ["Pending", "Rejected"]


def _is_org(tenant: Dict[str, Any]) -> bool:
    return tenant.get("type") == "partner"


def _is_direct(tenant: Dict[str, Any]) -> bool:
    return not _is_org(tenant) and not tenant.get("partnerId") and tenant.get("id") != PLATFORM_ID


def _int(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


async def _tenants(db) -> List[Dict[str, Any]]:
    return await db.tenants.find({}, {"_id": 0}).sort("id", 1).to_list(None)


async def check(db) -> List[str]:
    """Every unmet expectation, one sentence each; an empty list means the go-live state holds."""
    import licensing
    import network_rules
    import plan_service

    failures: List[str] = []
    if await db["_migrations"].find_one({"version": "034"}) is None:
        failures.append("migration 034 is not recorded in _migrations")
    stored = {doc.get("key") for doc in await db[plan_service.COLLECTION].find({}, {"_id": 0, "key": 1}).to_list(None)}
    for key in plan_service.PLAN_KEYS:
        if key not in stored:
            failures.append(f"the plans collection has no {key} plan")
    plans = await plan_service.plans(db)
    tenants = await _tenants(db)
    for tenant in tenants:
        tid, lic = tenant.get("id"), tenant.get("license") or {}
        if tid == PLATFORM_ID and "maxAgentsBeforePlans" in lic:
            failures.append(f"{tid} has a maxAgentsBeforePlans record, but the platform keeps its seats untouched")
        if _is_direct(tenant):
            seats, override = licensing.license_of(tenant)["maxAgents"], lic.get("seatOverride")
            wanted = plans[plan_service.plan_key_of(tenant)].get("seats")
            if "maxAgentsBeforePlans" not in lic:
                failures.append(f"{tid} has no maxAgentsBeforePlans record of its old seat number")
            if seats != wanted and not (_int(override) is not None and seats == override):
                failures.append(f"{tid} has {seats} seats, neither its plan's {wanted} nor its override {override}")
        if _is_org(tenant) or tid == PLATFORM_ID:
            continue
        trial = tenant.get("trial")
        if not isinstance(trial, dict):
            failures.append(f"{tid} has no trial")
        elif plan_service.plan_key_of(tenant) == "Free" and not trial.get("endsAt"):
            failures.append(f"{tid} is on Free and its trial has no end")
        listed = tenant.get("allowedNetworks") or []
        async for agent in db.agents.find({"tenantId": tid, "status": {"$nin": NOT_ADMITTED}},
                                          {"_id": 0, "hostname": 1, "publicIp": 1}):
            ip = network_rules.normalize_ip(agent.get("publicIp"))
            if ip is not None and ip.is_global and not network_rules.contains(listed, ip):
                failures.append(f"{tid}: agent {agent.get('hostname')} public address {ip} is not inside "
                                "its allowed networks")
    indexes = await db.agents.index_information()
    for name in HARDWARE_INDEXES:
        if not (indexes.get(name) or {}).get("sparse"):
            failures.append(f"the agents collection has no sparse index {name}")
    return failures


async def report(db) -> List[str]:
    """One line per tenant: name, plan, seats, override, trial end and allowed networks."""
    import licensing
    import plan_service

    lines: List[str] = []
    for tenant in await _tenants(db):
        lic = tenant.get("license") or {}
        trial = tenant.get("trial") if isinstance(tenant.get("trial"), dict) else {}
        nets = ",".join(str(e.get("cidr")) for e in tenant.get("allowedNetworks") or [] if isinstance(e, dict))
        plan = "partner organization" if _is_org(tenant) else plan_service.plan_key_of(tenant)
        lines.append(f"{tenant.get('name') or tenant.get('id')} | plan {plan} | maxAgents "
                     f"{licensing.license_of(tenant)['maxAgents']} | override {lic.get('seatOverride', '-')} | "
                     f"trial ends {trial.get('endsAt') or '-'} | networks {nets or '-'}")
    return lines


async def run(url: str, db_name: str) -> int:
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=5000)
    try:
        db = client[db_name]
        for line in await report(db):
            print(line)
        failures = await check(db)
    finally:
        client.close()
    for failure in failures:
        print(f"FAIL {failure}")
    if not failures:
        print("OK")
    return 1 if failures else 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only check of the Phase 88 plan-licensing go-live state.")
    parser.add_argument("--url", default="mongodb://127.0.0.1:27017")
    parser.add_argument("--db", default="omni_platform")
    args = parser.parse_args(argv)
    return asyncio.run(run(args.url, args.db))


if __name__ == "__main__":
    sys.exit(main())
