"""Behavioural check of catalogue_exempt reads (Phase 76 WR-01).

The PROH-76-08 rule in ``_catalogue_parity`` is lexical: a reason starting "self-service" on a
path that names a tenant or user. A reworded reason, another placeholder or no placeholder at
all passes it, which is how ``GET /api/tenants/me`` once returned the whole tenant document
(CR-01). This file probes every exempt GET of the real app as the lowest tenant roles, against a
tenant whose document carries sentinel secrets, and fails when any sentinel reaches a body.

The probe needs a real MongoDB: it runs only against ``MONGO_TEST_URL`` (the private test
server), in a throwaway database it drops afterwards, and skips when that is unset.
"""
import json
import os
import subprocess
import sys
import uuid

import pytest
from fastapi import Depends

from catalogue_guards import catalogue_exempt
from tests._catalogue_parity import _NAMES_TENANT_OR_USER, exempt_reads
from tests._route_walk import BACKEND_DIR, run_real_app_walk, throwaway_env, walk_app

TENANT = "probe-tenant"
ROLES = ("viewer", "itam_viewer")
CONTROL_PATH = "/api/probe-control/tenant-dump"
SENTINELS = {
    "registrationKey": "SENTINEL-REGISTRATION-KEY-7f3a",
    "emailConfig.smtpPassword": "SENTINEL-SMTP-PASSWORD-7f3a",
    "emailConfig.smtpPasswordEncrypted": "SENTINEL-SMTP-ENCRYPTED-7f3a",
    "emailConfig.smtpUser": "SENTINEL-SMTP-USER-7f3a",
    "license.key": "SENTINEL-LICENSE-KEY-7f3a",
    "users.hashed_password": "SENTINEL-PASSWORD-HASH-7f3a",
}
SEED = {
    "tenants": [{
        "id": TENANT, "name": "Probe Tenant", "subscriptionTier": "enterprise",
        "registrationKey": SENTINELS["registrationKey"], "maxAgents": 4242,
        "emailConfig": {"smtpHost": "smtp.probe.invalid", "smtpUser": SENTINELS["emailConfig.smtpUser"],
                        "smtpPassword": SENTINELS["emailConfig.smtpPassword"],
                        "smtpPasswordEncrypted": SENTINELS["emailConfig.smtpPasswordEncrypted"]},
        "license": {"key": SENTINELS["license.key"], "seats": 4242},
    }],
    "users": [{"email": "probe@example.com", "tenantId": TENANT, "role": "viewer", "status": "Active",
               "full_name": "Probe", "hashed_password": SENTINELS["users.hashed_password"]}],
}

# The child serves the real app against the private Mongo in one event loop, so Motor, the
# seed and every request share it. A control route reproducing CR-01 (an exempt read that
# returns the raw tenant document) can be mounted to prove the check catches a leak.
_PROBE = r"""
import asyncio, json, logging, sys
logging.disable(logging.CRITICAL)
from fastapi import Depends, FastAPI
import httpx
from motor.motor_asyncio import AsyncIOMotorClient
import api_key_auth
import authentication_service as auth
import database
import tenant_features
from auth_types import TokenData
from catalogue_guards import catalogue_exempt
from router_registry import register_all_routers
from tenant_context import set_tenant_id

spec = json.loads(sys.argv[1])

async def _all_on(tenant_id, get_db):
    return [tenant_features.ALL_FEATURES]

tenant_features.enabled_features = _all_on
app = FastAPI()
register_all_routers(app)
if spec["control"]:
    @app.get(spec["control"], dependencies=[Depends(catalogue_exempt("self-service: caller's own tenant record"))])
    async def _tenant_dump(user=Depends(auth.get_current_user)):
        return await database.mongodb.db.tenants.find_one({"id": user.tenant_id}, {"_id": 0})

async def main():
    client = AsyncIOMotorClient(spec["url"], serverSelectionTimeoutMS=3000)
    database.mongodb.client, database.mongodb.db = client, client[spec["db"]]
    out = []
    try:
        for name, docs in spec["seed"].items():
            await database.mongodb.db[name].insert_many(docs)
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://probe") as http:
            for case in spec["cases"]:
                td = TokenData(username="probe@example.com", role=case["role"], tenant_id=spec["tenant"],
                               auth_source="session")

                async def _as_caller(td=td):
                    set_tenant_id(td.tenant_id)  # what the real auth dependency does
                    return td

                for dep in (auth.get_current_user, auth.get_current_user_or_agent,
                            api_key_auth.get_current_user_or_api_key):
                    app.dependency_overrides[dep] = _as_caller
                resp = await http.get(case["path"])
                out.append({"status": resp.status_code, "body": resp.text})
    finally:
        await client.drop_database(spec["db"])
        client.close()
    return out

json.dump(asyncio.run(main()), sys.stdout)
"""


def _leaks(paths, *, control=None):
    url = os.getenv("MONGO_TEST_URL")
    if not url:
        pytest.skip("set MONGO_TEST_URL to the private test MongoDB to probe exempt reads")
    cases = [{"path": path, "role": role} for path in paths for role in ROLES]
    spec = {"url": url, "db": f"omni_test_exempt_{uuid.uuid4().hex[:10]}", "tenant": TENANT,
            "seed": SEED, "cases": cases, "control": control}
    env = throwaway_env()
    env["MONGODB_DB_NAME"] = spec["db"]
    proc = subprocess.run([sys.executable, "-c", _PROBE, json.dumps(spec)], cwd=BACKEND_DIR, env=env,
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-2000:]
    results = json.loads(proc.stdout.strip().splitlines()[-1])
    found = {}
    for case, result in zip(cases, results):
        hits = sorted(name for name, value in SENTINELS.items() if value in result["body"])
        if hits:
            found.setdefault(case["path"], set()).update(hits)
    return found, [(c["path"], c["role"], r["status"]) for c, r in zip(cases, results)]


def test_no_exempt_read_returns_tenant_or_account_secrets():
    """Every exempt GET, as the lowest tenant roles: no seeded secret appears in any body."""
    paths = exempt_reads(run_real_app_walk()["routes"], TENANT)
    assert "/api/tenants/me" in paths and len(paths) >= 10, paths
    found, statuses = _leaks(paths)
    assert found == {}, f"exempt reads return secrets: {found}"
    # A probe that only ever met errors would prove nothing: the self-service reads must answer.
    answered = {path for path, _role, status in statuses if status == 200}
    assert {"/api/tenants/me", "/api/users/me"} <= answered, statuses


def test_the_check_catches_what_the_lexical_rule_misses():
    """Negative control: an exempt self-service read with no placeholder that returns the raw
    tenant document (the CR-01 shape) passes the PROH-76-08 path rule and fails the probe."""
    from authentication_service import get_current_user
    from fastapi import APIRouter, FastAPI

    router = APIRouter()

    @router.get(CONTROL_PATH, dependencies=[Depends(catalogue_exempt("self-service: caller's own tenant record"))])
    async def tenant_dump(user=Depends(get_current_user)):
        return {}

    app = FastAPI()
    app.include_router(router)
    record = next(r for r in walk_app(app)["routes"] if r["path"] == CONTROL_PATH)
    assert record["exempt"] and not _NAMES_TENANT_OR_USER.search(record["path"])  # the lexical rule passes it
    found, _statuses = _leaks([CONTROL_PATH], control=CONTROL_PATH)
    assert {"registrationKey", "emailConfig.smtpPassword", "license.key"} <= found.get(CONTROL_PATH, set())
