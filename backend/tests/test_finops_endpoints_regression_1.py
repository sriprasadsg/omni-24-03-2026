"""
Regression: ISSUE-012 — any tenant admin can rewrite platform-wide service pricing
Found by /qa on 2026-10-13
Report: .gstack/qa-reports/run-20261013T151919Z/qa-report-127.0.0.1-2026-10-13.md

Live repro: POST /api/finops/pricing as a tenant admin with an invalid body returned
400 (validation), not 403, so the permission check passed. Every pricing write route
required only manage:settings, which tenant_admin holds; the pricing they write
applies to all tenants.

Value: protects=a tenant admin gets 403 on every pricing write route while a super
admin still reaches the handler; fails_when=a pricing write route is gated by a
permission tenant roles hold; why_new=no test covers finops pricing authorization;
seam=none; no_claim=JWT/session handling (get_current_user is overridden with a
TokenData; tenant_admin permissions come from the real rbac_defaults table, finops
service writes are mocked). Hermetic: no Mongo.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import finops_endpoints
import rbac_utils
from auth_types import TokenData

WRITES = [
    ("POST", "/api/finops/pricing", [{"id": "qa-authz-probe"}]),
    ("POST", "/api/finops/pricing/service", {"id": "svc", "name": "n", "price": 1, "unit": "u", "category": "c"}),
    ("PATCH", "/api/finops/pricing/service/svc", {"price": 0}),
    ("DELETE", "/api/finops/pricing/service/svc", None),
]


def _client(role):
    app = FastAPI()
    app.include_router(finops_endpoints.router)
    app.dependency_overrides[rbac_utils.get_current_user] = lambda: TokenData(
        username="qa@example.com", role=role, tenant_id="tenant-a", mfa_verified=True)
    return TestClient(app)


def _service():
    service = MagicMock()
    service.save_service_pricing = AsyncMock(return_value=[{"id": "svc"}])
    service.create_service_pricing = AsyncMock(return_value={"id": "svc"})
    service.update_service_pricing = AsyncMock(return_value={"id": "svc"})
    service.delete_service_pricing = AsyncMock(return_value={"deleted": True})
    return service


@pytest.mark.parametrize("method,path,body", WRITES)
def test_tenant_admin_cannot_write_platform_pricing(method, path, body):
    service = _service()
    with patch.object(finops_endpoints, "finops_service", service), \
         patch.object(finops_endpoints, "get_database", MagicMock()):
        r = _client("Tenant Admin").request(method, path, json=body)
    assert r.status_code == 403, (r.status_code, r.text)
    assert not service.save_service_pricing.called
    assert not service.create_service_pricing.called
    assert not service.update_service_pricing.called
    assert not service.delete_service_pricing.called


@pytest.mark.parametrize("method,path,body", WRITES)
def test_super_admin_still_reaches_pricing_writes(method, path, body):
    service = _service()
    with patch.object(finops_endpoints, "finops_service", service), \
         patch.object(finops_endpoints, "get_database", MagicMock()):
        r = _client("Super Admin").request(method, path, json=body)
    assert r.status_code != 403, (r.status_code, r.text)
