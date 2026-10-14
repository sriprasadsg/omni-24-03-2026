"""Spec C5 parity: every mutating route is audited by the middleware (all of /api/) or
listed in audit_exempt with a reason, and the middleware sits inside TenantMiddleware.

Value: protects=no mutating route escapes the audit log silently and no exemption goes
stale; fails_when=a mutating route outside /api/ is added without an exemption, an
exemption names a route that no longer exists, or the middleware runs before the tenant
is known; no_claim=runtime exclusions (agent data-plane tokens), tested in
test_audit_ledger.
"""
import os
import sys

from fastapi import FastAPI

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import audit_exempt
from tests._route_walk import run_real_app_walk


def test_every_mutating_route_is_audited_or_exempt():
    routes = run_real_app_walk()["routes"]
    assert sum(1 for r in routes if set(r["methods"]) & {"POST", "PUT", "PATCH", "DELETE"}) > 500
    assert audit_exempt.coverage_problems(routes) == []


def test_a_new_unaudited_route_fails_parity():
    routes = [{"methods": ["POST"], "path": "/webhooks/new-thing"},
              {"methods": ["POST"], "path": "/api/auth/login"},
              {"methods": ["POST"], "path": "/api/auth/logout"},
              {"methods": ["POST"], "path": "/api/auth/refresh"}]
    assert audit_exempt.coverage_problems(routes) == [
        "POST /webhooks/new-thing: mutating route outside /api/ is neither audited nor exempt"]
    stale = audit_exempt.coverage_problems(routes[1:2])
    assert any("POST /api/auth/logout: exempt entry matches no mounted" in p for p in stale)


def test_audit_middleware_runs_inside_tenant_middleware():
    from app_middleware import register_middleware
    from rate_limiter import limiter
    app = FastAPI()
    register_middleware(app, limiter)
    names = [m.cls.__name__ for m in app.user_middleware]  # outermost first
    assert names.index("TenantMiddleware") < names.index("AuditMiddleware")
