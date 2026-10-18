"""Phase 77 plan 01 (D-11, D-16): one closure rule for enforcement and delivery.

manage:X implies view:X and request:X, applied once inside rbac_service.granted_permissions
and _fallback_permissions (before the tenant switches narrow), filtered to the known
permission vocabulary; and every nav screen a role grants but the tenant switched off
carries a screen-off:<view> marker.
"""
import pytest

import permission_vocabulary as vocab
import rbac_defaults
import rbac_service
import rbac_utils
import tenant_features as tf
from auth_types import TokenData
from tests.rbac_test_support import StoreCollection, make_auth_client, login, make_user, me, role_store, shared_role_docs

ITAM_ADMIN_CLOSED_TAIL = ["request:assets", "view:assets", "view:licenses"]


def _use(monkeypatch, db):
    monkeypatch.setattr(rbac_utils, "get_database", lambda: db)
    monkeypatch.setattr(rbac_service, "get_database", lambda: db)


def _store(**extra):
    db, raw = role_store(roles=shared_role_docs(), **extra)
    return db


def _token(role, tenant_id="t1"):
    return TokenData(username="u@acme.test", role=role, tenant_id=tenant_id, mfa_verified=True)


# -- the pure helper --------------------------------------------------------

def test_closure_never_derives_control_or_manage():
    """PROH-77-01: only view:X/request:X come from manage:X; nothing from view:, nothing control:."""
    out = rbac_defaults.deliverable_closure(["manage:assets", "view:remote_access"], vocab.KNOWN_PERMISSIONS)
    assert "control:remote_access" not in out and "manage:remote_access" not in out
    assert out[:2] == ["manage:assets", "view:remote_access"]  # input order kept
    assert "view:assets" in out and "request:assets" in out
    assert not any(p.startswith("control:") for p in out)
    viewer = rbac_defaults.deliverable_closure(rbac_defaults.defaults_for("itam_viewer"), vocab.KNOWN_PERMISSIONS)
    assert "manage:assets" not in viewer


def test_unknown_derivations_are_dropped():
    assert "view:widgets" not in vocab.KNOWN_PERMISSIONS and "request:widgets" not in vocab.KNOWN_PERMISSIONS
    assert rbac_defaults.deliverable_closure(["manage:widgets"], vocab.KNOWN_PERMISSIONS) == ["manage:widgets"]


def test_closure_deduplicates_input_and_is_stable():
    out = rbac_defaults.deliverable_closure(["manage:assets", "view:assets", "manage:assets"], vocab.KNOWN_PERMISSIONS)
    assert out == ["manage:assets", "view:assets", "request:assets"]


def test_vocabulary_is_derived_not_literal():
    assert "*" not in vocab.KNOWN_PERMISSIONS
    assert not any(p.startswith(("screen:", "screen-off:")) for p in vocab.KNOWN_PERMISSIONS)
    assert all(":" in p for p in vocab.KNOWN_PERMISSIONS)
    assert {"view:assets", "request:assets", "view:licenses", "control:remote_access"} <= vocab.KNOWN_PERMISSIONS


@pytest.mark.parametrize("role", sorted(set(rbac_defaults.ROLE_DEFAULTS) - {"itam_admin"}))
def test_closure_adds_nothing_to_other_builtin_roles(role):
    table = list(rbac_defaults.defaults_for(role))
    assert rbac_defaults.deliverable_closure(table, vocab.KNOWN_PERMISSIONS) == table


# -- delivery through /login and /me ---------------------------------------

def test_itam_admin_reaches_assets_and_certificates(monkeypatch):
    user = make_user("ia@acme.test", "itam_admin", "t1")
    db, _raw = role_store(users=[user], roles=shared_role_docs())
    client = make_auth_client(db, monkeypatch)
    first = login(client, user["email"])
    assert first.status_code == 200, first.text
    logged_in = first.json()["user"]["permissions"]
    current = me(client, user["email"], "itam_admin", "t1").json()["permissions"]
    assert logged_in == current
    assert logged_in == list(rbac_defaults.defaults_for("itam_admin")) + ITAM_ADMIN_CLOSED_TAIL
    # assetManagement and certificates both need view:assets (shared/catalogue-access.json)
    for view in ("assetManagement", "certificates"):
        entry = next(c for c in tf._MANIFEST["catalogues"] if c["view"] == view)
        assert entry["permission"] in logged_in


@pytest.mark.parametrize("role,expected", [
    ("itam_user", ["request:assets", "view:assets", "view:itam", "view:licenses", "view:profile"]),
    ("itam_viewer", ["view:assets", "view:itam", "view:licenses", "view:profile"]),
])
async def test_other_itam_roles_unchanged(monkeypatch, role, expected):
    _use(monkeypatch, _store())
    assert await rbac_service.session_permissions(_store(), role, "t1") == expected


async def test_tenant_admin_list_unchanged(monkeypatch):
    db = _store()
    _use(monkeypatch, db)
    delivered = await rbac_service.session_permissions(db, "Tenant Admin", "t1")
    assert delivered == await rbac_service.effective_permissions(db, "Tenant Admin", "t1")


async def test_effective_permissions_stays_unclosed():
    db = _store()
    assert await rbac_service.effective_permissions(db, "itam_admin", "t1") == list(rbac_defaults.defaults_for("itam_admin"))


# -- enforcement parity -----------------------------------------------------

async def test_strict_request_assets_check_passes_for_itam_admin(monkeypatch):
    _use(monkeypatch, _store())
    admin = _token("itam_admin")
    assert await rbac_utils.verify_permission(admin, "request:assets") is True
    assert await rbac_utils.verify_permission(admin, "view:assets") is True
    assert await rbac_utils.verify_permission(_token("itam_viewer"), "manage:assets") is False


async def test_delivery_equals_enforcement_for_every_known_permission(monkeypatch):
    db = _store()
    _use(monkeypatch, db)
    delivered = set(await rbac_service.session_permissions(db, "itam_admin", "t1"))
    for perm in sorted(vocab.KNOWN_PERMISSIONS):
        assert (perm in delivered) == await rbac_utils.verify_permission(_token("itam_admin"), perm), perm


# -- fallback parity --------------------------------------------------------

async def test_fallback_applies_the_closure():
    delivered = await rbac_service._fallback_permissions(None, "itam_admin", "t1")
    assert delivered[-3:] == ITAM_ADMIN_CLOSED_TAIL


async def test_session_permissions_fall_back_with_the_closure_when_the_store_fails(monkeypatch):
    class _Boom(StoreCollection):
        async def find_one(self, *a, **k):
            raise RuntimeError("down")

    db, _raw = role_store(roles=_Boom())
    delivered = await rbac_service.session_permissions(db, "itam_admin", "t1")
    assert "view:assets" in delivered
# -- D-16 switched-off markers ---------------------------------------------

def _tdb(tenants=(), roles=()):
    from tests.test_tenant_feature_switches import _db
    return _db(tenants=list(tenants), roles=list(roles))


def _tenant(features):
    return {"id": "tenant-a", "name": "A", "enabledFeatures": features}


@pytest.mark.real_tenant_features
async def test_markers_cover_every_granted_but_switched_off_nav_screen():
    db = _tdb(tenants=[_tenant(["view:security", "screen:edr"])])
    granted = await rbac_service.granted_permissions(db, "Tenant Admin", "tenant-a")
    assert "screen-off:alertManagement" in granted
    assert "screen-off:edr" not in granted
    assert "screen-off:compliance" in granted and "view:compliance" not in granted
    assert not any(p.startswith("screen:") for p in granted)
    assert len(granted) == len(set(granted))


@pytest.mark.real_tenant_features
async def test_no_marker_for_a_screen_the_role_never_held():
    db = _tdb(tenants=[_tenant(["view:security", "screen:edr"])])
    granted = await rbac_service.granted_permissions(db, "viewer", "tenant-a")
    held_views = {c["view"] for c in tf._MANIFEST["catalogues"] if c["permission"] in rbac_defaults.defaults_for("viewer")}
    markers = {p[len(tf.SCREEN_OFF_PREFIX):] for p in granted if p.startswith(tf.SCREEN_OFF_PREFIX)}
    assert markers <= held_views


@pytest.mark.real_tenant_features
async def test_viewer_has_no_marker_for_a_permission_it_lacks():
    db = _tdb(tenants=[_tenant(["view:security"])])
    granted = await rbac_service.granted_permissions(db, "itam_viewer", "tenant-a")
    assert "screen-off:agents" not in granted  # itam_viewer never held view:agents


@pytest.mark.real_tenant_features
async def test_all_on_tenant_gets_the_closed_set_and_no_markers():
    db = _tdb(tenants=[_tenant(["all"])])
    granted = await rbac_service.granted_permissions(db, "itam_admin", "tenant-a")
    assert granted == list(rbac_defaults.defaults_for("itam_admin")) + ITAM_ADMIN_CLOSED_TAIL
    assert not any(p.startswith(tf.SCREEN_OFF_PREFIX) for p in granted)


@pytest.mark.real_tenant_features
async def test_itam_admin_loses_assets_when_the_switch_is_off():
    db = _tdb(tenants=[_tenant(["view:itam"])])
    granted = await rbac_service.granted_permissions(db, "itam_admin", "tenant-a")
    assert "view:assets" not in granted and "manage:assets" not in granted
    assert "screen-off:assetManagement" in granted and "screen-off:certificates" in granted


@pytest.mark.real_tenant_features
async def test_fallback_emits_the_same_markers_as_granted():
    db = _tdb(tenants=[_tenant(["view:security", "screen:edr"])])
    granted = await rbac_service.granted_permissions(db, "Tenant Admin", "tenant-a")
    fallback = await rbac_service._fallback_permissions(db, "Tenant Admin", "tenant-a")
    assert fallback == granted


@pytest.mark.real_tenant_features
async def test_custom_role_non_marker_entries_unchanged():
    db = _tdb(tenants=[_tenant(["view:agents"])],
              roles=[{"name": "Helpdesk", "tenantId": "tenant-a", "permissions": ["view:security", "view:agents"]}])
    granted = await rbac_service.granted_permissions(db, "Helpdesk", "tenant-a")
    assert [p for p in granted if not p.startswith(tf.SCREEN_OFF_PREFIX)] == ["view:agents"]


def test_nav_screens_and_groups_are_derived_from_the_manifest():
    assert len(tf.NAV_SCREENS) == 188 and len(tf.NAV_GROUPS) == 8
    assert all(len(row) == 4 for row in tf.NAV_SCREENS)


def test_apply_tenant_has_no_duplicates():
    perms = list(rbac_defaults.defaults_for("tenant_admin"))
    out = tf.apply_tenant(perms, ["view:security"])
    assert len(out) == len(set(out))
