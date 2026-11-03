"""Partner second wall (Phase 87, plan 87-05, D-01 and D-04): a partner token reaches only the
Partner portal and its own sign-in, MFA and passkey routes; a partner viewer never writes.

The allowlist is proven over every route the real app mounts (run_real_app_walk), not a sample, then
through the mounted middleware on a tiny app, then against the real catalogue guards with no
middleware at all (probe_real_app), so the guards and the edge each hold on their own.

Value: protects=a partner token cannot read or change a customer, a platform screen or any
get_current_user-only route; fails_when=a route outside the portal and the self-service prefixes lets a
partner through, the viewer can write under /api/partner, or a catalogue guard stops refusing partner roles;
no_claim=what a partner sees inside its own portal (test_partner_tracer) and websocket delivery (A-87-A5).
"""
import json
import re
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import authentication_service as auth
import partner_middleware
from partner_middleware import PARTNER_REFUSAL, VIEWER_REFUSAL, PartnerScopeMiddleware, partner_request_refusal
from tenant_middleware import TenantMiddleware
from tests._route_walk import probe_real_app, run_real_app_walk

_ALLOWED_PREFIX = re.compile(r"^/api/(partner(/|$)|auth/|mfa/|passkey/)")
_SHELL_READ = "/api/platform/features"
_METHODS = ("GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE")


@pytest.fixture(scope="module")
def pairs():
    out = []
    for record in run_real_app_walk()["routes"]:
        for method in record["methods"]:
            out.append((method, re.sub(r"\{[^}]+\}", "x", record["path"])))
    assert len(out) > 1000
    return out


def test_a_partner_admin_is_refused_every_route_but_the_portal_and_its_own_security(pairs):
    """protects=PART-05 allowlist over the whole route table; fails_when=any other /api route lets a
    partner_admin through; no_claim=WS routes (the walk marks them WS and no HTTP method applies)."""
    http = [(m, p) for m, p in pairs if m != "WS"]
    # every method a route answers, plus every method on every path: the rule is path based
    paths = {p for _, p in http}
    allowed = {(m, p) for p in paths for m in _METHODS
               if partner_request_refusal("partner_admin", m, p) is None}
    unexpected = sorted((m, p) for m, p in allowed
                        if not (_ALLOWED_PREFIX.search(p)
                                or (p == _SHELL_READ and m in ("GET", "HEAD"))
                                or not p.startswith("/api/")))
    assert unexpected == [], unexpected
    refused = {p for p in paths if p.startswith("/api/") and not _ALLOWED_PREFIX.search(p)
               and p != _SHELL_READ}
    assert len(refused) > 500
    for path in refused:
        assert partner_request_refusal("partner_admin", "GET", path) == PARTNER_REFUSAL, path
    # and the allowed side is not empty: the portal, the sign-in routes and the shell read exist
    assert ("GET", "/api/partner/overview") in {(m, p) for m, p in http}
    assert ("GET", _SHELL_READ) in allowed and ("HEAD", _SHELL_READ) in allowed
    assert ("POST", _SHELL_READ) not in allowed and ("PUT", _SHELL_READ) not in allowed
    assert any(p.startswith("/api/auth/") for _, p in allowed)


def test_a_partner_viewer_cannot_write_under_the_portal_but_keeps_its_own_security_writes(pairs):
    """protects=D-04 viewer is read-only; fails_when=a viewer POST/PUT/PATCH/DELETE under /api/partner passes
    or its own logout/MFA writes are refused; no_claim=viewer reads (the same allowlist as the admin)."""
    portal = sorted({p for _, p in pairs if re.match(r"^/api/partner(/|$)", p)})
    assert "/api/partner/overview" in portal and "/api/partner/customers" in portal
    for path in portal:
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            assert partner_request_refusal("partner_viewer", method, path) == VIEWER_REFUSAL, (method, path)
        for method in ("GET", "HEAD", "OPTIONS"):
            assert partner_request_refusal("partner_viewer", method, path) is None, (method, path)
    for path in ("/api/mfa/setup", "/api/auth/logout", "/api/passkey/register"):
        assert partner_request_refusal("partner_viewer", "POST", path) is None, path
    # the viewer is also confined to the portal like the admin
    assert partner_request_refusal("partner_viewer", "GET", "/api/tenants") == PARTNER_REFUSAL
    assert partner_request_refusal("partner_admin", "POST", "/api/partner/customers") is None


@pytest.mark.parametrize("role", ["tenant_admin", "admin", "Super Admin", "Platform Support",
                                  "Platform Billing", "viewer", "agent", None])
def test_nobody_else_is_touched_by_the_partner_wall(pairs, role):
    """protects=a Super Admin, tenant staff, platform staff and an anonymous request pass unchanged;
    fails_when=the wall refuses a non-partner role anywhere; no_claim=those roles' own authorization."""
    for method, path in {(m, p) for m, p in pairs if m != "WS"}:
        assert partner_request_refusal(role, method, path) is None, (role, method, path)


def test_spelling_variants_of_a_partner_role_are_walled_too():
    """protects=a Partner Admin spelled with spaces or capitals gets the same wall; fails_when=a spelling
    slips past the exact-key match; no_claim=which spellings the sign-in issues."""
    for role in ("Partner Admin", "PARTNER_ADMIN", "partner admin", "Partner Viewer"):
        assert partner_request_refusal(role, "GET", "/api/tenants") == PARTNER_REFUSAL, role
    assert partner_request_refusal("Partner Viewer", "POST", "/api/partner/customers") == VIEWER_REFUSAL
    assert partner_request_refusal("partner_admin", "GET", "/api/partnerz/x") == PARTNER_REFUSAL
    assert partner_request_refusal("partner_admin", "GET", "/api/partners") == PARTNER_REFUSAL
    assert partner_request_refusal("partner_admin", "GET", "/api/platform/partners") == PARTNER_REFUSAL
    assert partner_request_refusal("partner_admin", "GET", "/api/partner") is None


def _token(role, tenant="t-1"):
    return auth.create_access_token({"sub": "who@example.com", "role": role, "tenant_id": tenant})


@pytest.fixture
def client():
    app = FastAPI()
    seen = []

    def route(path):
        async def handler():
            seen.append(path)
            return {"ok": True}
        return handler

    for path in ("/api/tenants", "/api/mssp/overview", "/api/partner/overview"):
        app.add_api_route(path, route(path), methods=["GET"])
    app.add_api_route("/api/partner/customers", route("/api/partner/customers"), methods=["POST"])
    app.add_api_route("/api/mfa/setup", route("/api/mfa/setup"), methods=["POST"])
    app.add_middleware(PartnerScopeMiddleware)
    app.add_middleware(TenantMiddleware)
    with patch("ip_ban_service.is_banned", AsyncMock(return_value=False)):
        c = TestClient(app, raise_server_exceptions=False)
        c.seen = seen
        yield c


def _bearer(role):
    return {"Authorization": f"Bearer {_token(role)}"}


def test_mounted_middleware_walls_a_partner_token_and_leaves_everyone_else_alone(client):
    """protects=the middleware as mounted: 403 JSON {error, status_code} for a partner, pass for the portal,
    a Super Admin and no token; fails_when=the response shape drifts from PlatformReadOnlyMiddleware or the
    handler runs for a refused request; no_claim=audit of the refusal (outer AuditMiddleware, 87-05 summary)."""
    for path in ("/api/tenants", "/api/mssp/overview"):
        response = client.get(path, headers=_bearer("partner_admin"))
        assert response.status_code == 403, path
        assert response.json() == {"error": "Partner accounts can use only the Partner portal", "status_code": 403}
    assert client.seen == []                                   # the handler never ran
    assert client.get("/api/partner/overview", headers=_bearer("partner_admin")).status_code == 200
    assert client.get("/api/partner/overview", headers=_bearer("partner_viewer")).status_code == 200
    viewer = client.post("/api/partner/customers", headers=_bearer("partner_viewer"))
    assert viewer.status_code == 403
    assert viewer.json() == {"error": "Partner viewers have read-only access", "status_code": 403}
    assert client.post("/api/partner/customers", headers=_bearer("partner_admin")).status_code == 200
    assert client.post("/api/mfa/setup", headers=_bearer("partner_viewer")).status_code == 200
    assert client.get("/api/tenants", headers=_bearer("Super Admin")).status_code == 200
    assert client.get("/api/tenants").status_code == 200       # no token: the route's own auth decides
    assert client.get("/api/tenants", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 200


# Header spellings get_current_user (OAuth2PasswordBearer) accepts besides the exact "Bearer <token>".
_SPELLINGS = ("bearer {t}", "BEARER {t}", "bEaReR {t}", "Bearer  {t}", "Bearer {t} ")


def _auth(spelling, token):
    return {"Authorization": spelling.format(t=token)}


def test_the_edge_role_reader_accepts_exactly_the_headers_the_route_auth_accepts():
    """protects=T-87-13: _bearer_role, which feeds the partner, platform read-only and screen-switch walls, reads a
    role from exactly the Authorization headers OAuth2PasswordBearer accepts; fails_when=any header that gets a token
    past get_current_user is invisible to the walls, or the walls read one the route would refuse; no_claim=nginx."""
    from fastapi import Depends
    from fastapi.security import OAuth2PasswordBearer
    from tenant_middleware import _bearer_role

    app = FastAPI()
    scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

    @app.get("/echo")
    async def echo(token=Depends(scheme)):
        return {"token": token}

    route_auth = TestClient(app)
    t = _token("partner_admin")
    headers = [s.format(t=t) for s in ("Bearer {t}",) + _SPELLINGS]
    headers += [f"Basic {t}", f"Bearer{t}", f"Bearer\t{t}", t, "Bearer", "Bearer ", ""]
    for header in headers:
        accepted = route_auth.get("/echo", headers={"Authorization": header}).json()["token"] == t
        role = _bearer_role({"headers": [(b"authorization", header.encode("latin-1"))]})
        assert (role == "partner_admin") == accepted, repr(header)


def test_mounted_wall_refuses_a_partner_token_in_every_spelling_the_route_auth_accepts(client):
    """protects=T-87-13 as mounted: a lower-case scheme or extra spaces get the same 403 as "Bearer <token>" and the
    handler never runs; fails_when=a spelling variant passes PartnerScopeMiddleware; no_claim=the routes' own auth."""
    t = _token("partner_admin")
    for spelling in _SPELLINGS:
        response = client.get("/api/tenants", headers=_auth(spelling, t))
        assert response.status_code == 403, spelling
        assert response.json() == {"error": PARTNER_REFUSAL, "status_code": 403}
    assert client.seen == []


def test_read_only_platform_wall_refuses_a_write_in_every_spelling():
    """protects=PlatformReadOnlyMiddleware shares the role reader, so T-87-13 reached it too; fails_when=Platform
    Support writes past the wall with a lower-case scheme; no_claim=the support role's own permissions."""
    from tenant_middleware import PlatformReadOnlyMiddleware

    app = FastAPI()
    seen = []

    @app.post("/api/tenants")
    async def write():
        seen.append(1)
        return {"ok": True}

    app.add_middleware(PlatformReadOnlyMiddleware)
    c = TestClient(app)
    t = _token("platform_support", "platform-admin")
    for spelling in ("Bearer {t}",) + _SPELLINGS:
        assert c.post("/api/tenants", headers=_auth(spelling, t)).status_code == 403, spelling
    assert seen == []


def test_tenant_context_and_audit_actor_are_read_from_every_spelling():
    """protects=TenantMiddleware and the audit actor read the same headers as the walls, so a spelling variant
    neither runs without its tenant context nor goes into the ledger without an actor; fails_when=either parser
    keeps the exact-prefix check; no_claim=the DB wrapper's own fail-closed behaviour."""
    from audit_middleware import actor_of
    from tenant_context import get_tenant_id

    app = FastAPI()

    @app.get("/api/whose-tenant")
    async def whose_tenant():
        return {"tenant": get_tenant_id()}

    app.add_middleware(TenantMiddleware)
    t = _token("Admin", "t-7")
    with patch("ip_ban_service.is_banned", AsyncMock(return_value=False)):
        c = TestClient(app)
        for spelling in ("Bearer {t}",) + _SPELLINGS:
            assert c.get("/api/whose-tenant", headers=_auth(spelling, t)).json() == {"tenant": "t-7"}, spelling
    for spelling in ("Bearer {t}",) + _SPELLINGS:
        actor, is_agent = actor_of({"headers": [(b"authorization", spelling.format(t=t).encode("latin-1"))]})
        assert actor and actor["email"] == "who@example.com" and actor["tenantId"] == "t-7", spelling
        assert is_agent is False


def test_the_wall_ignores_non_http_scopes():
    """protects=websocket and lifespan scopes pass straight through (A-87-A5 is a live check, not this wall);
    fails_when=the middleware inspects a non-http scope; no_claim=websocket delivery."""
    import asyncio
    called = []

    async def inner(scope, receive, send):
        called.append(scope["type"])

    wall = PartnerScopeMiddleware(inner)
    for kind in ("websocket", "lifespan"):
        asyncio.run(wall({"type": kind, "path": "/api/tenants", "headers": []}, None, None))
    assert called == ["websocket", "lifespan"]


def test_module_exposes_the_two_refusal_strings():
    """protects=the strings the UI can rely on; fails_when=they change silently; no_claim=their wording elsewhere."""
    assert partner_middleware.PARTNER_REFUSAL == "Partner accounts can use only the Partner portal"
    assert partner_middleware.VIEWER_REFUSAL == "Partner viewers have read-only access"


_GUARDED_READS = ["/api/tenants", "/api/mssp/overview", "/api/assets", "/api/agents", "/api/users",
                  "/api/platform/partners"]


def test_the_catalogue_guards_alone_refuse_both_partner_roles_on_the_customer_surfaces():
    """protects=the first wall: with no middleware, the real app's catalogue guards answer 403 to a partner on
    tenants, MSSP, assets, agents, users and the Super Admin Partners screen; fails_when=any of these answers
    anything but 403; no_claim=routes with no catalogue guard (the edge allowlist above covers those)."""
    cases = [{"method": "GET", "path": path, "role": role, "tenant_id": "partner-org-1"}
             for role in ("partner_admin", "partner_viewer") for path in _GUARDED_READS]
    statuses = probe_real_app(cases)
    assert statuses == [403] * len(cases), list(zip([(c["role"], c["path"]) for c in cases], statuses))
