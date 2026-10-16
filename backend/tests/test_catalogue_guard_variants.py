"""Agent-tolerant and platform-read catalogue guard variants (Phase 76-13, WR-01/WR-05).

Unit tests on synthetic routers (roles resolved from rbac_defaults only, no Mongo), router-level
tests on the real software / response / agent-chat routers, and real-app probes over the
production registry. Every new failure mode has a negative control so the verdict does not
depend on test order.
"""

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

import catalogue_guards
import rbac_defaults
import rbac_utils
import tenant_features
from auth_types import TokenData
from authentication_service import AGENT_ROLE, get_current_user, get_current_user_or_agent
from catalogue_guards import agent_tolerant, catalogue_guard, check_catalogue_access
from catalogue_mounts_devices import SOFTWARE_UPDATES_GUARD
from tests._route_walk import probe_real_app

PLATFORM = rbac_defaults.PLATFORM_TENANT_ID

DEMO = dict(read=("manage:settings",), write=("manage:settings",))


@pytest.fixture(autouse=True)
def _built_in_roles_only(monkeypatch):
    """Resolve roles from rbac_defaults alone: no Mongo, no tenant role documents."""
    async def _defaults_only(db, role, tenant_id):
        return list(rbac_defaults.defaults_for(rbac_utils._rbac_service._normalize_role(role or "")))

    async def _all_features(tenant_id, get_db):
        return [tenant_features.ALL_FEATURES]

    monkeypatch.setattr(rbac_utils, "granted_permissions", _defaults_only)
    monkeypatch.setattr(rbac_utils, "get_database", lambda: None)
    monkeypatch.setattr(tenant_features, "enabled_features", _all_features)


def _user(role, tenant="t1", scopes=None):
    return TokenData(username="u@example.com", role=role, tenant_id=tenant, scopes=scopes, auth_source="session")


def _app_with(router, guard, user, *, auth=get_current_user_or_agent):
    app = FastAPI()
    app.include_router(router, dependencies=[Depends(guard)] if guard is not None else [])
    app.dependency_overrides[auth] = lambda: user
    if auth is not get_current_user:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def _demo_client(guard, user, *, auth=get_current_user_or_agent):
    router = APIRouter()

    @router.api_route("/x", methods=["GET", "POST"])
    async def handler():
        return {"ok": True}

    return _app_with(router, guard, user, auth=auth)


# ---------------------------------------------------------------------------
# agent_tolerant: construction and tag shape
# ---------------------------------------------------------------------------

def test_allow_agent_requires_the_agent_aware_auth():
    with pytest.raises(ValueError, match="demo"):
        catalogue_guard("demo", allow_agent=True, **DEMO)


def test_platform_read_must_be_platform_only():
    with pytest.raises(ValueError, match="demo"):
        catalogue_guard("demo", platform_read=("manage:settings",), **DEMO)


def test_agent_tolerant_tag_adds_allow_agent_only():
    tag = agent_tolerant(SOFTWARE_UPDATES_GUARD).__catalogue_guard__
    assert tag == {"catalogue": "softwareUpdates", "read": ["view:software_updates"],
                   "write": ["manage:patches"], "allow_agent": True}
    # Existing guards keep their tag byte for byte (no allow_agent / platform_read keys).
    assert set(SOFTWARE_UPDATES_GUARD.__catalogue_guard__) == {"catalogue", "read", "write"}


def test_platform_read_tag_lists_the_permissions():
    guard = catalogue_guard("demo", platform_read=("view:tenants",), **DEMO)
    assert guard.__catalogue_guard__["platform_read"] == ["view:tenants"]
    assert "allow_agent" not in guard.__catalogue_guard__


def test_agent_tolerant_needs_a_tagged_guard():
    with pytest.raises(ValueError):
        agent_tolerant(lambda: None)


# ---------------------------------------------------------------------------
# agent_tolerant: behaviour
# ---------------------------------------------------------------------------

def test_agent_identity_skips_the_permission_lookup(monkeypatch):
    async def _boom(*a, **kw):
        raise AssertionError("the agent identity must not be permission-checked")
    monkeypatch.setattr(catalogue_guards, "verify_permission", _boom)
    client = _demo_client(agent_tolerant(SOFTWARE_UPDATES_GUARD), _user(AGENT_ROLE))
    assert client.get("/x").status_code == 200
    assert client.post("/x").status_code == 200


def test_viewer_is_refused_on_an_agent_tolerant_guard():
    resp = _demo_client(agent_tolerant(SOFTWARE_UPDATES_GUARD), _user("viewer")).get("/x")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Missing required permission: view:software_updates"


def test_tenant_admin_passes_an_agent_tolerant_guard():
    assert _demo_client(agent_tolerant(SOFTWARE_UPDATES_GUARD), _user("tenant_admin")).get("/x").status_code == 200


def test_role_spelled_Agent_is_a_person():
    # Only the exact token role "agent" is the agent identity (PROH-76-05).
    client = _demo_client(agent_tolerant(SOFTWARE_UPDATES_GUARD), _user("Agent"))
    assert client.get("/x").status_code == 403


def test_plain_guard_still_refuses_agent_role_without_the_permission():
    # Negative control: without allow_agent the agent role has no special standing.
    guard = catalogue_guard("demo", auth=get_current_user_or_agent, **DEMO)
    assert _demo_client(guard, _user(AGENT_ROLE)).get("/x").status_code == 403


# ---------------------------------------------------------------------------
# platform_read
# ---------------------------------------------------------------------------

def _platform_client(role, tenant, *, scopes=None):
    guard = catalogue_guard("demo", platform_read=("view:tenants",), auth=get_current_user, **DEMO)
    return _demo_client(guard, _user(role, tenant, scopes), auth=get_current_user)


def test_platform_support_reads_but_never_writes():
    client = _platform_client("platform_support", PLATFORM)
    assert client.get("/x").status_code == 200
    assert client.post("/x").status_code == 403


def test_platform_billing_reads_in_the_platform_tenant():
    assert _platform_client("platform_billing", PLATFORM).get("/x").status_code == 200


def test_platform_support_in_a_tenant_is_refused():
    assert _platform_client("platform_support", "t1").get("/x").status_code == 403


def test_tenant_admin_and_viewer_unchanged_with_platform_read():
    assert _platform_client("tenant_admin", "t1").get("/x").status_code == 200
    assert _platform_client("viewer", "t1").get("/x").status_code == 403


def test_super_admin_reads():
    assert _platform_client("super_admin", "t1").get("/x").status_code == 200


def test_narrowed_scope_refuses_platform_staff():
    resp = _platform_client("platform_support", PLATFORM, scopes=["view:dashboard"]).get("/x")
    assert resp.status_code == 403
    assert resp.json()["detail"].startswith("API key scope does not permit")


def test_scope_for_the_platform_permission_is_enough():
    assert _platform_client("platform_support", PLATFORM, scopes=["view:tenants"]).get("/x").status_code == 200


@pytest.mark.asyncio
async def test_check_catalogue_access_platform_read_keyword():
    from fastapi import HTTPException
    await check_catalogue_access(_user("platform_support", PLATFORM), "GET", DEMO["read"], DEMO["write"],
                                 platform_read=("view:tenants",))
    with pytest.raises(HTTPException):
        await check_catalogue_access(_user("platform_support", PLATFORM), "GET", DEMO["read"], DEMO["write"])


# ---------------------------------------------------------------------------
# Installer download (software_endpoints) mounted alone
# ---------------------------------------------------------------------------

@pytest.fixture()
def software_app(tmp_path, monkeypatch):
    import software_endpoints
    (tmp_path / "pkg.msi").write_bytes(b"installer-bytes")
    monkeypatch.setattr(software_endpoints, "UPLOAD_DIR", tmp_path)

    def _build(role):
        app = FastAPI()
        app.include_router(software_endpoints.router)
        user = _user(role)
        app.dependency_overrides[get_current_user_or_agent] = lambda: user
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app, raise_server_exceptions=False)
    return _build


@pytest.mark.parametrize("role", [AGENT_ROLE, "tenant_admin"])
def test_download_serves_agent_and_permitted_roles(software_app, role):
    resp = software_app(role).get("/api/software/download/pkg.msi")
    assert resp.status_code == 200
    assert resp.content == b"installer-bytes"


@pytest.mark.parametrize("role", ["viewer", "itam_viewer"])
def test_download_refuses_roles_without_view_software_updates(software_app, role):
    assert software_app(role).get("/api/software/download/pkg.msi").status_code == 403


def test_download_route_keeps_its_own_agent_aware_auth():
    import software_endpoints
    route = next(r for r in software_endpoints.router.routes if r.path == "/api/software/download/{filename}")
    calls = [d.call for d in route.dependant.dependencies]
    assert get_current_user_or_agent in calls
    assert any(getattr(c, "__catalogue_guard__", {}).get("allow_agent") for c in calls)


def test_download_on_the_real_app():
    def case(role, tenant="tenant-a"):
        return {"method": "GET", "path": "/api/software/download/probe-missing.msi", "role": role,
                "tenant_id": tenant, "auth": "agent_capable"}
    agent, admin, support, viewer, itam_viewer, nobody = probe_real_app([
        case(AGENT_ROLE), case("tenant_admin"), case("platform_support", PLATFORM),
        case("viewer"), case("itam_viewer"), case("nobody"),
    ])
    assert (agent, admin, support) == (404, 404, 404), "the handler must be reached (file missing)"
    assert (viewer, itam_viewer, nobody) == (403, 403, 403)
