"""Assets slice (Phase 76-04): asset, ITAM and certificate routes carry the manifest guard.

Parity names every in-scope route of the slice's modules that lacks the guard the manifest
prescribes. The real-app probes prove the guard enforces on the mounted app and that ITAM
API-key callers behave as before (D-02: role first, then key scopes).
"""
import pytest

from tests._catalogue_parity import load_manifest, parity_offenders, resolved_read, slice_modules
from tests._route_walk import probe_real_app, run_real_app_walk

TENANT = "tenant-a"


def _case(path, role, *, method="GET", scopes=None, api_key=False):
    case = {"method": method, "path": path, "role": role, "tenant_id": TENANT,
            "auth": "api_key" if api_key else "session"}
    if scopes is not None:
        case["scopes"] = scopes
    return case


def test_assets_slice_parity():
    records = run_real_app_walk()["routes"]
    manifest = load_manifest()
    modules = slice_modules("assets", records, manifest)
    assert "itam_lifecycle_endpoints" in modules and "asset_endpoints" in modules
    offenders = parity_offenders(records, manifest, modules)
    assert offenders == [], "unguarded or mis-guarded asset-slice routes:\n" + "\n".join(offenders)


def test_assets_real_app_enforced():
    # "nobody" is a role that holds no permission at all: it must be refused everywhere.
    denied_assets, denied_cert, denied_itam, denied_history, allowed_assets, allowed_itam_admin, allowed_cert = probe_real_app([
        _case("/api/assets", "nobody"),
        _case("/api/certificates", "nobody"),
        _case("/api/itam/kpis", "nobody", api_key=True),
        _case("/api/assets/a1/history", "nobody", api_key=True),
        _case("/api/assets", "viewer"),
        # D-03 twin: itam_admin holds manage:assets but not view:assets and still reads /api/assets
        _case("/api/assets", "itam_admin"),
        _case("/api/certificates", "viewer"),
    ])
    assert denied_assets == 403, "a role without view:assets/manage:assets must be refused on GET /api/assets"
    assert denied_cert == 403
    assert denied_itam == 403
    assert denied_history == 403, "/api/assets/{id}/history belongs to assetManagement"
    assert allowed_assets != 403, "a role holding view:assets must not be refused by the catalogue guard"
    assert allowed_itam_admin != 403, "manage:assets satisfies the view:assets read (D-03 twin)"
    assert allowed_cert != 403


def test_compliance_and_scan_asset_routes_enforced_on_real_app():
    refused = probe_real_app([
        _case("/api/assets/a1/compliance", "nobody"),
        _case("/api/assets/a1/compliance/status", "nobody", method="PATCH"),
        _case("/api/assets/a1/scan", "nobody", method="POST"),
        _case("/api/vulnerability-scans/schedule", "nobody", method="POST"),
    ])
    assert refused == [403, 403, 403, 403]
    assert probe_real_app([_case("/api/assets/a1/compliance", "viewer")])[0] != 403


def test_itam_reads_follow_view_itam_on_real_app():
    viewer_denied, itam_viewer_ok, itam_admin_ok = probe_real_app([
        _case("/api/itam/kpis", "viewer", api_key=True),        # holds view:assets, not view:itam
        _case("/api/itam/kpis", "itam_viewer", api_key=True),   # view:itam
        _case("/api/itam/kpis", "itam_admin", api_key=True),    # manage:itam twin
    ])
    assert viewer_denied == 403
    assert itam_viewer_ok != 403
    assert itam_admin_ok != 403


def test_itam_api_key_unchanged():
    ok_view, wrong_scope, ok_manage, wrong_role, post_view_scope = probe_real_app([
        _case("/api/itam/kpis", "itam_viewer", scopes=["view:itam"], api_key=True),
        _case("/api/itam/kpis", "itam_viewer", scopes=["view:assets"], api_key=True),
        # manage:assets-scoped keys have always been able to read ITAM; they still can
        _case("/api/itam/kpis", "itam_viewer", scopes=["manage:assets"], api_key=True),
        # the role is the outer bound: a wildcard key cannot lift a role without the permission
        _case("/api/itam/kpis", "viewer", scopes=["*"], api_key=True),
        _case("/api/itam/data/import", "itam_admin", method="POST", scopes=["view:itam"], api_key=True),
    ])
    assert ok_view != 403, "a key scoped view:itam must still read ITAM routes"
    assert wrong_scope == 403, "a key without an ITAM scope must still be refused"
    assert ok_manage != 403, "a key scoped manage:assets must still read ITAM routes"
    assert wrong_role == 403, "the role check still runs first"
    assert post_view_scope == 403, "a read-only scope never authorises a write"


# Custom tenant roles (role documents), resolved without Mongo for the in-process checks below.
_CUSTOM_ROLES = {"assets manager": ["manage:assets", "view:assets"], "itam reader": ["view:itam"],
                 "asset reader": ["view:assets"], "nobody": []}


@pytest.fixture()
def custom_role_app(monkeypatch):
    """ITAM_GUARD and the ITAM handlers' own read check, side by side on stub routes returning 200."""
    import rbac_utils
    import tenant_features
    from fastapi import APIRouter, Depends, FastAPI
    from fastapi.testclient import TestClient
    from api_key_auth import get_current_user_or_api_key
    from auth_types import TokenData
    from authentication_service import get_current_user
    from catalogue_mounts_assets import ITAM_API_KEY_GUARD, ITAM_GUARD
    from itam_asset_endpoints import _require_itam_viewer

    async def _custom(db, role, tenant_id):
        return list(_CUSTOM_ROLES[role])

    async def _all_features(tenant_id, get_db):
        return [tenant_features.ALL_FEATURES]

    monkeypatch.setattr(rbac_utils, "granted_permissions", _custom)
    monkeypatch.setattr(rbac_utils, "get_database", lambda: None)
    monkeypatch.setattr(tenant_features, "enabled_features", _all_features)

    def client(role):
        router = APIRouter()

        @router.get("/guard", dependencies=[Depends(ITAM_GUARD)])
        async def guarded():
            return {"ok": True}

        @router.get("/key-guard", dependencies=[Depends(ITAM_API_KEY_GUARD)])
        async def key_guarded():
            return {"ok": True}

        @router.get("/handler", dependencies=[Depends(_require_itam_viewer)])
        async def handler():
            return {"ok": True}

        app = FastAPI()
        app.include_router(router)
        user = TokenData(username="u@example.com", role=role, tenant_id=TENANT, auth_source="session")
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_user_or_api_key] = lambda: user
        return TestClient(app, raise_server_exceptions=False)

    return client


def test_itam_guard_reads_like_the_itam_handlers(custom_role_app):
    """76 WR-03: the guard's ITAM read accepts manage:assets, as _require_itam_viewer does."""
    for role, expected in (("assets manager", 200), ("itam reader", 200), ("asset reader", 403), ("nobody", 403)):
        client = custom_role_app(role)
        statuses = [client.get(path).status_code for path in ("/guard", "/key-guard", "/handler")]
        assert statuses == [expected] * 3, (role, statuses)


def test_itam_manifest_read_mirrors_the_guard():
    by_view = {c["view"]: c for c in load_manifest()["catalogues"]}
    from catalogue_mounts_assets import ITAM_GUARD
    assert sorted(ITAM_GUARD.__catalogue_guard__["read"]) == sorted(resolved_read(by_view["itam"]))
    assert sorted(resolved_read(by_view["itam"])) == ["manage:assets", "view:itam"]
    assert by_view["itam"]["permission"] == "view:itam", "the sidebar still gates ITAM on view:itam"
