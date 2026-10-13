"""Catalogue guard tests (Phase 76, ACC-03/ACC-04).

Tracer: Mobile Device Management on the real mounted app. Matrix: the guard's read
closure (D-03/D-07), write rule, any-of reads, super-admin bypass and role-then-scope
order (D-02), on synthetic routers whose roles come from rbac_defaults.
"""
import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

import rbac_defaults
import rbac_utils
from auth_types import TokenData
from catalogue_guards import catalogue_exempt, catalogue_guard, manage_twin
from tests._route_walk import probe_real_app


def test_tracer_mdm_enforced_on_real_app():
    denied, allowed = probe_real_app([
        {"method": "GET", "path": "/api/mdm/summary", "role": "viewer", "tenant_id": "tenant-a", "auth": "session"},
        {"method": "GET", "path": "/api/mdm/summary", "role": "admin", "tenant_id": "tenant-a", "auth": "session"},
    ])
    assert denied == 403, "a role without view:mdm / manage:mdm must be refused on /api/mdm"
    assert allowed != 403, "a role holding view:mdm must not be refused by the catalogue guard"


# ---------------------------------------------------------------------------
# Behaviour matrix on synthetic routers
# ---------------------------------------------------------------------------

async def _stub_auth():  # replaced per test through dependency_overrides
    raise AssertionError("auth stub must be overridden")


@pytest.fixture(autouse=True)
def _built_in_roles_only(monkeypatch):
    """Resolve roles from rbac_defaults alone: no Mongo, no tenant role documents."""
    async def _defaults_only(db, role, tenant_id):
        return list(rbac_defaults.defaults_for(rbac_utils._rbac_service._normalize_role(role or "")))
    monkeypatch.setattr(rbac_utils, "effective_permissions", _defaults_only)
    monkeypatch.setattr(rbac_utils, "get_database", lambda: None)


# Real default roles: viewer holds neither view:itam nor manage:itam; itam_viewer holds
# view:itam only; admin (tenant_admin) holds both. For the assets pair itam_admin holds
# manage:assets without view:assets.
ITAM = dict(read=("view:itam",), write=("manage:itam",))
ASSETS = dict(read=("view:assets",), write=("manage:assets",))


def _client(guard, role, *, scopes=None, auth_source="session"):
    router = APIRouter()

    @router.api_route("/x", methods=["GET", "HEAD", "OPTIONS", "POST", "PUT", "DELETE"])
    async def handler():
        return {"ok": True}

    app = FastAPI()
    app.include_router(router, dependencies=[Depends(guard)])
    user = TokenData(username="u@example.com", role=role, tenant_id="t1", scopes=scopes, auth_source=auth_source)
    app.dependency_overrides[_stub_auth] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def _guard(**kw):
    return catalogue_guard("demo", auth=_stub_auth, **kw)


def test_read_refused_without_view_or_manage():
    resp = _client(_guard(**ITAM), "viewer").get("/x")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Missing required permission: view:itam"


def test_read_allowed_with_view():
    assert _client(_guard(**ITAM), "itam_viewer").get("/x").status_code == 200


def test_read_allowed_with_manage_twin_only():
    # itam_admin holds manage:assets and not view:assets (D-03 closure, guard only).
    assert "view:assets" not in rbac_defaults.defaults_for("itam_admin")
    assert _client(_guard(**ASSETS), "itam_admin").get("/x").status_code == 200


def test_write_refused_with_view_only():
    for method in ("post", "put", "delete"):
        resp = getattr(_client(_guard(**ITAM), "itam_viewer"), method)("/x")
        assert resp.status_code == 403, method
        assert resp.json()["detail"] == "Missing required permission: manage:itam"


def test_write_allowed_with_manage():
    assert _client(_guard(**ITAM), "admin").post("/x").status_code == 200
    assert _client(_guard(**ASSETS), "itam_admin").post("/x").status_code == 200


def test_head_and_options_follow_the_read_rule():
    allowed, denied = _client(_guard(**ITAM), "itam_viewer"), _client(_guard(**ITAM), "viewer")
    assert allowed.head("/x").status_code == 200
    assert allowed.options("/x").status_code == 200
    assert denied.head("/x").status_code == 403
    assert denied.options("/x").status_code == 403


def test_read_may_be_a_manage_string_used_for_writes_too():
    guard = _guard(read=("manage:settings",), write=("manage:settings",))
    assert _client(guard, "admin").get("/x").status_code == 200
    assert _client(guard, "admin").post("/x").status_code == 200
    assert _client(guard, "viewer").get("/x").status_code == 403
    assert _client(guard, "viewer").post("/x").status_code == 403


def test_any_of_reads_accept_either_permission():
    guard = _guard(read=("manage:users", "manage:rbac"), write=("manage:rbac",))
    assert "manage:rbac" not in rbac_defaults.defaults_for("itam_admin")
    assert _client(guard, "itam_admin").get("/x").status_code == 200  # holds manage:users only
    assert _client(guard, "viewer").get("/x").status_code == 403
    assert _client(guard, "itam_admin").post("/x").status_code == 403  # writes need manage:rbac


def test_super_admin_passes_every_check():
    client = _client(_guard(**ITAM), "Super Admin")
    for method in ("get", "head", "options", "post", "put", "delete"):
        assert getattr(client, method)("/x").status_code == 200, method


def test_api_key_scope_that_excludes_the_permission_is_refused():
    # admin's role allows the route; the key's scopes do not (D-02 scope narrowing).
    resp = _client(_guard(**ITAM), "admin", scopes=["view:assets"], auth_source="api_key").get("/x")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "API key scope does not permit: view:itam"


def test_api_key_with_matching_scope_or_wildcard_passes():
    guard = _guard(**ITAM)
    assert _client(guard, "admin", scopes=["view:itam"], auth_source="api_key").get("/x").status_code == 200
    assert _client(guard, "admin", scopes=["*"], auth_source="api_key").get("/x").status_code == 200
    assert _client(guard, "admin", scopes=["manage:itam"], auth_source="api_key").post("/x").status_code == 200
    assert _client(guard, "admin", scopes=["view:itam"], auth_source="api_key").post("/x").status_code == 403


def test_write_scope_also_authorises_a_read_but_never_the_reverse():
    # 76-04: a key scoped manage:assets has always read ITAM data (D-02 compatibility).
    guard = _guard(read=("view:itam",), write=("manage:assets",))
    key = dict(scopes=["manage:assets"], auth_source="api_key")
    assert _client(guard, "admin", **key).get("/x").status_code == 200
    assert _client(guard, "admin", **key).post("/x").status_code == 200
    assert _client(guard, "admin", scopes=["view:itam"], auth_source="api_key").post("/x").status_code == 403


def test_role_is_checked_before_scopes():
    # viewer lacks view:itam; the key's scope lists it, yet the role message wins (D-02 order).
    resp = _client(_guard(**ITAM), "viewer", scopes=["view:itam"], auth_source="api_key").get("/x")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Missing required permission: view:itam"


def test_guard_rejects_empty_or_malformed_permissions():
    for bad in ({"read": (), "write": ("manage:x",)}, {"read": ("view:x",), "write": ()},
                {"read": ("viewx",), "write": ("manage:x",)}, {"read": ("view:x",), "write": ("managex",)}):
        with pytest.raises(ValueError):
            catalogue_guard("demo", **bad)


def test_exempt_requires_a_reason_and_is_not_counted_as_a_guard():
    for blank in ("", "   "):
        with pytest.raises(ValueError):
            catalogue_exempt(blank)
    marker = catalogue_exempt("agent enrollment is key-authenticated")
    assert marker.__catalogue_exempt__ == "agent enrollment is key-authenticated"
    assert marker.__name__ == "_catalogue_exempt_marker" and "_require_" not in marker.__name__


def test_guard_tag_shape_and_name():
    guard = catalogue_guard("demo", read=("view:a", "view:b"), write=("manage:a",), auth=_stub_auth)
    assert guard.__catalogue_guard__ == {"catalogue": "demo", "read": ["view:a", "view:b"], "write": ["manage:a"]}
    assert guard.__name__ == "_require_catalogue"  # matches the baseline PERM_DEP regex


def test_manage_twin():
    assert manage_twin("view:mdm") == "manage:mdm"
    assert manage_twin("manage:settings") == "manage:settings"
    assert manage_twin("investigate:security") == "investigate:security"
