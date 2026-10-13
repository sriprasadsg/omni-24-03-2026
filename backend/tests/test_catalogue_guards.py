"""Catalogue guard tests (Phase 76, ACC-03/ACC-04).

Task 1 tracer: Mobile Device Management on the real mounted app.
"""
import json
import os
import subprocess
import sys

BACKEND = os.path.join(os.path.dirname(__file__), "..")

# Real app in a fresh interpreter: other tests reload authentication_service, so an
# in-process app would not see the dependency identity the guard was built with.
# The child points Mongo at an unroutable port and a throwaway database name, so
# nothing it does can reach the live omni_platform data.
_PROBE = r"""
import json, logging, sys
logging.disable(logging.CRITICAL)
from fastapi import FastAPI
from fastapi.testclient import TestClient
import authentication_service as auth
from auth_types import TokenData
from router_registry import register_all_routers

app = FastAPI()
register_all_routers(app)
out = []
for case in json.loads(sys.argv[1]):
    td = TokenData(username="probe@example.com", role=case["role"], tenant_id=case["tenant_id"])
    app.dependency_overrides[auth.get_current_user] = lambda td=td: td
    client = TestClient(app, raise_server_exceptions=False)
    out.append(client.request(case["method"], case["path"]).status_code)
json.dump(out, sys.stdout)
"""


def _probe(cases):
    env = dict(os.environ)
    env.update({
        "MONGODB_URL": "mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=300",
        "MONGO_URI": "mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=300",
        "MONGODB_DB_NAME": "catalogue_probe_throwaway",
        "ENVIRONMENT": "test",
    })
    proc = subprocess.run([sys.executable, "-c", _PROBE, json.dumps(cases)], cwd=BACKEND, env=env,
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_tracer_mdm_enforced_on_real_app():
    denied, allowed = _probe([
        {"method": "GET", "path": "/api/mdm/summary", "role": "viewer", "tenant_id": "tenant-a"},
        {"method": "GET", "path": "/api/mdm/summary", "role": "admin", "tenant_id": "tenant-a"},
    ])
    assert denied == 403, "a role without view:mdm / manage:mdm must be refused on /api/mdm"
    assert allowed != 403, "a role holding view:mdm must not be refused by the catalogue guard"
