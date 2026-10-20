"""Dashboard Studio: tenant admins design dashboards from the widgets of the screens their tenant
bought; users see what is published to their role, minus screens they cannot read.

An in-memory store stands in for MongoDB (the tenant wrapper is not under test here) and the
caller's delivered permission list is set per role, the way rbac_service would deliver it."""
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from auth_types import TokenData
from authentication_service import get_current_user

ADMIN = TokenData(username="admin@t1.test", role="Tenant Admin", tenant_id="t1", mfa_verified=True)
ANALYST = TokenData(username="ana@t1.test", role="analyst", tenant_id="t1")
VIEWER = TokenData(username="vee@t1.test", role="viewer", tenant_id="t1")

PERMS = {
    "Tenant Admin": ["view:dashboard", "manage:dashboards", "view:agents", "view:assets",
                     "view:compliance", "view:security", "view:audit_log", "view:patching"],
    # The tenant switched the Patch Management screen off for this analyst's organisation.
    "analyst": ["view:dashboard", "view:agents", "view:security", "view:patching",
                "screen-off:patchManagement"],
    "viewer": ["view:dashboard", "view:compliance"],
}


def _match(doc, flt):
    return all(doc.get(k) == v for k, v in (flt or {}).items())


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, length=None):
        return list(self._docs)


class _Col:
    def __init__(self):
        self.docs = []

    def find(self, flt=None, projection=None):
        return _Cursor([dict(d) for d in self.docs if _match(d, flt)])

    async def find_one(self, flt=None, projection=None):
        return next((dict(d) for d in self.docs if _match(d, flt)), None)

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, flt, update, upsert=False):
        for d in self.docs:
            if _match(d, flt):
                d.update(update.get("$set", {}))
                return type("R", (), {"matched_count": 1})()
        if upsert:
            self.docs.append({**flt, **update.get("$set", {})})
        return type("R", (), {"matched_count": 0})()

    async def delete_one(self, flt):
        self.docs = [d for d in self.docs if not _match(d, flt)]

    async def delete_many(self, flt):
        self.docs = [d for d in self.docs if not _match(d, flt)]


class _DB:
    def __init__(self):
        self.tenant_dashboards = _Col()
        self.dashboard_user_prefs = _Col()


@pytest.fixture
def db():
    return _DB()


def _call(db, user, method, path, body=None):
    import tenant_dashboards_endpoints as mod
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_current_user] = lambda: user
    granted = PERMS[user.role]
    with patch.object(mod, "get_database", return_value=db), \
         patch.object(mod, "get_tenant_id", return_value=user.tenant_id), \
         patch.object(mod, "_perms", AsyncMock(return_value=granted)), \
         patch.object(mod, "_audit", AsyncMock()), \
         patch("rbac_utils.verify_permission", AsyncMock(side_effect=lambda u, p: p in PERMS[u.role])):
        with TestClient(app) as c:
            return c.request(method, path, json=body)


def _layout(*widgets, everyone=False, roles=()):
    return {"name": "SecOps wall", "description": "", "sharing": {"everyone": everyone, "roles": list(roles)},
            "widgets": [{"i": f"w{n}", "widget": w, "x": (n % 2) * 6, "y": (n // 2) * 4, "w": 6, "h": 4}
                        for n, w in enumerate(widgets)]}


def test_the_catalogue_offers_only_widgets_of_readable_bought_screens(db):
    body = _call(db, ANALYST, "GET", "/api/dashboards/widgets").json()
    available = {w["id"] for w in body["widgets"] if w["available"]}
    assert "agents-by-platform" in available and "alerts-by-severity" in available
    assert "patch-jobs" not in available          # screen switched off for the tenant
    assert "compliance-frameworks" not in available  # role cannot read compliance
    assert body["grid"]["columns"] == 12


def test_only_a_designer_can_create_and_a_new_dashboard_is_a_draft(db):
    assert _call(db, VIEWER, "POST", "/api/dashboards", _layout("compliance-frameworks")).status_code == 403
    resp = _call(db, ADMIN, "POST", "/api/dashboards", _layout("agents-by-platform", "compliance-frameworks"))
    assert resp.status_code == 200, resp.text
    created = resp.json()
    assert created["status"] == "draft" and created["version"] == 1 and created["widgetCount"] == 2
    # Nobody but designers sees a draft.
    assert _call(db, VIEWER, "GET", "/api/dashboards").json()["dashboards"] == []
    assert _call(db, VIEWER, "GET", f"/api/dashboards/{created['id']}").status_code == 404


@pytest.mark.parametrize("bad,why", [
    ({"widget": "no-such-widget"}, "Unknown widget"),
    ({"widget": "agents-by-platform", "w": 1}, "outside its limits"),
    ({"widget": "agents-by-platform", "x": 10}, "right edge"),
    ({"widget": "agents-by-platform", "i": "a b"}, None),
])
def test_layouts_are_validated(db, bad, why):
    layout = _layout("agents-by-platform")
    layout["widgets"][0].update(bad)
    resp = _call(db, ADMIN, "POST", "/api/dashboards", layout)
    assert resp.status_code in (400, 422)
    if why:
        assert why in resp.json()["detail"]


def test_overlapping_widgets_are_refused(db):
    layout = _layout("agents-by-platform", "alerts-by-severity")
    layout["widgets"][1].update({"x": 2, "y": 0})
    resp = _call(db, ADMIN, "POST", "/api/dashboards", layout)
    assert resp.status_code == 400 and "overlaps" in resp.json()["detail"]


def test_a_designer_cannot_add_widgets_their_tenant_has_not_bought(db):
    PERMS["Tenant Admin"].append("screen-off:assetManagement")
    try:
        resp = _call(db, ADMIN, "POST", "/api/dashboards", _layout("assets-by-os"))
    finally:
        PERMS["Tenant Admin"].remove("screen-off:assetManagement")
    assert resp.status_code == 400 and "not available" in resp.json()["detail"]


def test_publish_shares_with_roles_and_withholds_unreadable_widgets(db):
    created = _call(db, ADMIN, "POST", "/api/dashboards",
                    _layout("agents-by-platform", "compliance-frameworks", roles=["analyst"])).json()
    assert _call(db, ADMIN, "POST", f"/api/dashboards/{created['id']}/publish", {"version": 1}).status_code == 200

    listed = _call(db, ANALYST, "GET", "/api/dashboards").json()
    assert [d["id"] for d in listed["dashboards"]] == [created["id"]] and listed["canDesign"] is False
    seen = _call(db, ANALYST, "GET", f"/api/dashboards/{created['id']}").json()
    assert [w["widget"] for w in seen["widgets"]] == ["agents-by-platform"]
    assert seen["withheld"] == 1
    # Not shared with viewers.
    assert _call(db, VIEWER, "GET", f"/api/dashboards/{created['id']}").status_code == 404


def test_publishing_needs_an_audience(db):
    created = _call(db, ADMIN, "POST", "/api/dashboards", _layout("agents-by-platform")).json()
    resp = _call(db, ADMIN, "POST", f"/api/dashboards/{created['id']}/publish", {"version": 1})
    assert resp.status_code == 400 and "who sees" in resp.json()["detail"]


def test_saving_a_draft_leaves_the_published_copy_until_publish(db):
    created = _call(db, ADMIN, "POST", "/api/dashboards", _layout("agents-by-platform", everyone=True)).json()
    _call(db, ADMIN, "POST", f"/api/dashboards/{created['id']}/publish", {"version": 1})
    saved = _call(db, ADMIN, "PUT", f"/api/dashboards/{created['id']}",
                  {"draft": _layout("agents-by-platform", "alerts-by-severity", everyone=True), "version": 2})
    assert saved.status_code == 200 and saved.json()["hasUnpublishedChanges"] is True
    assert len(_call(db, ANALYST, "GET", f"/api/dashboards/{created['id']}").json()["widgets"]) == 1
    draft = _call(db, ADMIN, "GET", f"/api/dashboards/{created['id']}?mode=draft").json()
    assert len(draft["widgets"]) == 2
    assert _call(db, ANALYST, "GET", f"/api/dashboards/{created['id']}?mode=draft").status_code == 403


def test_a_stale_version_is_refused_instead_of_overwriting(db):
    created = _call(db, ADMIN, "POST", "/api/dashboards", _layout("agents-by-platform")).json()
    ok = {"draft": _layout("agents-by-platform"), "version": 1}
    assert _call(db, ADMIN, "PUT", f"/api/dashboards/{created['id']}", ok).status_code == 200
    assert _call(db, ADMIN, "PUT", f"/api/dashboards/{created['id']}", ok).status_code == 409


def test_users_hide_widgets_only_for_themselves(db):
    created = _call(db, ADMIN, "POST", "/api/dashboards",
                    _layout("agents-by-platform", "alerts-by-severity", everyone=True)).json()
    _call(db, ADMIN, "POST", f"/api/dashboards/{created['id']}/publish", {"version": 1})
    resp = _call(db, ANALYST, "PUT", f"/api/dashboards/{created['id']}/hidden", {"hidden": ["w1", "nope"]})
    assert resp.json() == {"hidden": ["w1"]}
    assert _call(db, ANALYST, "GET", f"/api/dashboards/{created['id']}").json()["hidden"] == ["w1"]
    assert _call(db, ADMIN, "GET", f"/api/dashboards/{created['id']}").json()["hidden"] == []


def test_unpublish_and_delete(db):
    created = _call(db, ADMIN, "POST", "/api/dashboards", _layout("agents-by-platform", everyone=True)).json()
    _call(db, ADMIN, "POST", f"/api/dashboards/{created['id']}/publish", {"version": 1})
    assert _call(db, ADMIN, "POST", f"/api/dashboards/{created['id']}/unpublish").json()["status"] == "draft"
    assert _call(db, ANALYST, "GET", "/api/dashboards").json()["dashboards"] == []
    assert _call(db, ANALYST, "DELETE", f"/api/dashboards/{created['id']}").status_code == 403
    assert _call(db, ADMIN, "DELETE", f"/api/dashboards/{created['id']}").status_code == 200
    assert db.tenant_dashboards.docs == []


def test_another_tenants_dashboards_stay_out_of_reach(db):
    """The database wrapper leaves platform callers unscoped, so the endpoints name the tenant
    themselves: a dashboard stored for t2 is never listed, opened, edited or deleted from t1."""
    other = TokenData(username="admin@t2.test", role="Tenant Admin", tenant_id="t2", mfa_verified=True)
    created = _call(db, other, "POST", "/api/dashboards", _layout("agents-by-platform", everyone=True)).json()
    _call(db, other, "POST", f"/api/dashboards/{created['id']}/publish", {"version": 1})
    assert db.tenant_dashboards.docs[0]["tenantId"] == "t2"
    assert _call(db, ADMIN, "GET", "/api/dashboards").json()["dashboards"] == []
    for method, path, body in (("GET", "", None), ("GET", "?mode=draft", None),
                               ("PUT", "", {"draft": _layout("agents-by-platform"), "version": 2}),
                               ("DELETE", "", None), ("PUT", "/hidden", {"hidden": []})):
        assert _call(db, ADMIN, method, f"/api/dashboards/{created['id']}{path}", body).status_code == 404, (method, path)
    assert len(db.tenant_dashboards.docs) == 1


def test_every_catalogue_widget_belongs_to_a_manifest_screen():
    import dashboard_widgets
    for spec in dashboard_widgets.CATALOGUE["widgets"]:
        assert spec["view"] in dashboard_widgets._VIEWS, spec["id"]
        size = spec["size"]
        assert size["minW"] <= size["w"] <= 12 and size["minH"] <= size["h"] <= size["maxH"], spec["id"]
