"""Shared HTTP fixtures for the Autonomous Ops route tests (plan 81-09): both routers mounted on one
app (the tenant router behind its catalogue guard), the caller's identity chosen per request, and a
throwaway MongoDB (tests/_mongo_test_db.py).
"""
import os
import sys
from datetime import datetime, timezone

import httpx
import pytest
from fastapi import FastAPI

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import autonomous_ops_endpoints as endpoints
import autonomous_ops_platform_endpoints as platform_endpoints
import autonomous_ops_response_endpoints as response_endpoints
import autonomous_ops_response_platform_endpoints as response_platform_endpoints
import rbac_utils
from api_key_auth import get_current_user_or_api_key
from auth_types import TokenData
from autonomous_ops import ledger, protected
from catalogue_mounts import mount_dependencies
from tests._route_walk import probe_real_app
from tests.autonomy_support import seed_tenant

PLATFORM = "platform-admin"
NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)   # long before any row recorded by the code under test


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")     # the deployment master is off
    protected.cache_clear()


class Api:
    """The tenant router mounted with its catalogue guard; the caller's identity is per request."""

    def __init__(self, db, monkeypatch):
        self.db = db
        self.user = None
        monkeypatch.setattr(endpoints, "get_database", lambda: db)
        monkeypatch.setattr(platform_endpoints, "get_database", lambda: db)
        monkeypatch.setattr(response_endpoints, "get_database", lambda: db)
        monkeypatch.setattr(response_platform_endpoints, "get_database", lambda: db)
        monkeypatch.setattr(rbac_utils, "get_database", lambda: db)     # role documents for the permission checks
        self.app = FastAPI()
        self.app.include_router(endpoints.router,
                                dependencies=mount_dependencies("autonomous_ops_endpoints", "router"))
        self.app.include_router(platform_endpoints.router)
        self.app.include_router(response_endpoints.router,
                                dependencies=mount_dependencies("autonomous_ops_response_endpoints", "router"))
        self.app.include_router(response_platform_endpoints.router)
        self.app.dependency_overrides[get_current_user_or_api_key] = lambda: self.user

    async def call(self, method, path, *, role="tenant_admin", tenant="t1", username=None, auth="session",
                   scopes=None, json=None):
        platform = role in ("super_admin", "platform_support", "platform_billing")
        self.user = TokenData(username=username or f"{role}@example.test", role=role,
                              tenant_id=PLATFORM if platform else tenant, scopes=scopes,
                              auth_source="api_key" if auth == "api_key" else "session")
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, json=json)


@pytest.fixture
async def api(mongo_db, monkeypatch):
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=True)
    await seed_tenant(mongo_db, "t2", shadow=True)
    return Api(mongo_db, monkeypatch)


def _case(path, role, *, method="GET", auth="session_capable", tenant=None, scopes=None, features=None):
    platform = role in ("super_admin", "platform_support", "platform_billing")
    case = {"method": method, "path": path, "role": role, "auth": auth, "scopes": scopes,
            "tenant_id": PLATFORM if platform else (tenant or "t1")}
    if features is not None:
        case["tenant_features"] = features
    return case


def _probe(groups):
    """One interpreter for every case: ``groups`` maps a name to its cases; returns name -> statuses."""
    flat = [case for cases in groups.values() for case in cases]
    codes = iter(probe_real_app(flat))
    return {name: [next(codes) for _ in cases] for name, cases in groups.items()}
