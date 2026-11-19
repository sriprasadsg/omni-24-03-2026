"""Connect Omni-Agent to the open-source services scripts/oss/oss.sh installed (run by `sudo scripts/oss/oss.sh connect`).

It runs as the backend's user with the backend's environment (oss.sh starts it through systemd-run with the unit's
EnvironmentFiles, from backend/ so its .env loads too), so each setting goes through the same code as its screen:
checked, encrypted with the backend's key and audited.
  * fleet     - the Fleet device connector (https://localhost:8412), then one sync;
  * authentik - authentik as a cloud log source (http://127.0.0.1:9000), then one pull;
  * ntfy      - paging to the ntfy topic http://127.0.0.1:2586/omni-oncall, then a test page;
  * scim      - only with --scim-org: a SCIM token for that organization, for authentik's SCIM provider.
Fleet, authentik and ntfy are set for the Platform organization unless --org names another. A setting already
there is left as it is unless --replace. The tokens arrive as JSON on stdin (oss.sh reads them from /opt/omni-oss as
root) and are never printed; the one line starting SCIM_TOKEN= is for oss.sh, which keeps it out of what it shows.
"""
import argparse
import asyncio
import json
import os
import sys

WHO = "oss.sh connect (root on the server)"
FLEET_URL = "https://localhost:8412"
AUTHENTIK_URL = "http://127.0.0.1:9000"
NTFY_URL = "http://127.0.0.1:2586/omni-oncall"
SCIM_LABEL = "authentik (oss.sh connect)"
PLATFORM = "platform-admin"


def say(line: str) -> None:
    print(line, flush=True)


async def connect_fleet(db, tenant: str, token: str, replace: bool) -> None:
    import fleet_service
    if (await fleet_service.get_config(db, tenant)).get("connected") and not replace:
        return say("fleet: already connected, left as it is")
    await fleet_service.save_config(db, tenant, FLEET_URL, token, WHO)
    out = await fleet_service.sync(db, tenant, WHO)
    say(f"fleet: connected to {FLEET_URL}; first sync read {out['devices']} device(s)")


async def connect_authentik(db, tenant: str, token: str, replace: bool) -> None:
    import log_connectors
    if (await log_connectors.list_config(db, tenant))["authentik"]["connected"] and not replace:
        return say("authentik: already a log source, left as it is")
    await log_connectors.save_config(db, tenant, "authentik", {"baseUrl": AUTHENTIK_URL, "secret": token}, WHO)
    out = await log_connectors.pull_now(db, tenant, "authentik", WHO)
    say(f"authentik: log source saved; first pull read {out.get('read', 0)} event(s), {out.get('new', 0)} new"
        if out.get("ok") else f"authentik: saved, but the first pull failed: {out.get('error')}")


async def connect_ntfy(db, tenant: str, token: str, replace: bool) -> None:
    import audit_ledger
    import soc_paging
    if (await soc_paging.get_config(db, tenant)).get("configured") and not replace:
        return say("ntfy: paging is already set up, left as it is")
    out = await soc_paging.save_config(db, tenant, {"provider": "ntfy", "secret": NTFY_URL, "token": token}, WHO)
    await audit_ledger.event("soc.paging.update", tenant, actor={"email": WHO, "tenantId": tenant}, db=db,
                             provider=out.get("provider"), enabled=out.get("enabled"))
    test = await soc_paging.send_test(db, tenant, WHO)
    await audit_ledger.event("soc.paging.test", tenant, actor={"email": WHO, "tenantId": tenant}, db=db,
                             alertId=test["alertId"], paged=test.get("paged"))
    say(f"ntfy: paging to {NTFY_URL} (critical alerts); test page "
        + ("sent: close the 'Paging test from Omni-Agent' alert to resolve it" if test.get("paged") else f"failed: {test.get('error')}"))


async def scim_token(db, org: str, replace: bool) -> bool:
    import scim_service
    tenant = await db.tenants.find_one({"$or": [{"id": org}, {"name": org}]}, {"_id": 0, "id": 1, "name": 1})
    if not tenant or tenant["id"] == PLATFORM:
        say(f"scim: no organization {org!r} to provision into (the Platform cannot hold a SCIM token)")
        return False
    old = await db.scim_tokens.find_one({"tenantId": tenant["id"], "label": SCIM_LABEL, "revokedAt": None}, {"_id": 0, "id": 1})
    if old and not replace:
        say(f"scim: authentik already has a token for {tenant['name']}, left as it is")
        return True
    if old:
        await scim_service.revoke_token(db, tenant["id"], old["id"], WHO)
        await scim_service.audit(db, "scim.token.revoke", tenant["id"], WHO, resourceId=old["id"])
    out = await scim_service.create_token(db, tenant["id"], WHO, SCIM_LABEL)
    await scim_service.audit(db, "scim.token.create", tenant["id"], WHO, resourceId=out["id"])
    say(f"scim: token {out['prefix']}... created for {tenant['name']} ({tenant['id']})")
    say("SCIM_TOKEN=" + out["token"])
    return True


async def main(args: argparse.Namespace) -> int:
    sys.path.insert(0, os.getcwd())
    import database  # loads backend/.env, as the backend does
    from motor.motor_asyncio import AsyncIOMotorClient
    url = os.getenv("MONGODB_URL") or os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
    if not url or not os.getenv("PAYMENT_ENCRYPTION_KEY"):
        say("refused: run this through `sudo scripts/oss/oss.sh connect` (the backend's database and key are not set)")
        return 2
    secrets = json.loads(sys.stdin.read() or "{}")
    client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=10000)
    db = client[os.getenv("MONGODB_DB_NAME", "omni_platform")]
    database.mongodb.client, database.mongodb.db = client, db  # code that calls get_database() sees the same database
    import fleet_service
    import httpx
    import log_connectors
    import soc_paging
    refused = (fleet_service.FleetError, log_connectors.ConnectorError, soc_paging.PagingError, httpx.HTTPError, ValueError)
    failed = 0
    steps = [("fleet", connect_fleet), ("authentik", connect_authentik), ("ntfy", connect_ntfy)]
    for name, step in steps:
        if name not in args.only:
            continue
        if not secrets.get(name):
            say(f"{name}: skipped (scripts/oss/oss.sh apply {name} first)")
            continue
        try:
            await step(db, args.org, secrets[name], args.replace)
        except refused as exc:  # each service's own error says what it refused
            failed += 1
            say(f"{name}: refused: {exc}")
    if args.scim_org and not await scim_token(db, args.scim_org, args.replace):
        failed += 1
    client.close()
    return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--org", default=PLATFORM, help="organization for Fleet, authentik and ntfy (default: the Platform)")
    parser.add_argument("--scim-org", help="organization (id or name) that receives authentik's test users")
    parser.add_argument("--only", default="fleet,authentik,ntfy", type=lambda s: set(s.split(",")))
    parser.add_argument("--replace", action="store_true", help="save again over a setting that is already there")
    sys.exit(asyncio.run(main(parser.parse_args())))
