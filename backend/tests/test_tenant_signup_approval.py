"""Approval of self-service sign-ups: only a Super Admin lists, approves or rejects them; approval
activates the tenant and its pending admin, rejection removes both. In-memory store."""
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from auth_types import TokenData
from authentication_service import get_current_user

SUPER = TokenData(username="super@omni.test", role="Super Admin", tenant_id="platform-admin", mfa_verified=True)
ADMIN = TokenData(username="admin@t1.test", role="Tenant Admin", tenant_id="t1", mfa_verified=True)


def _match(doc, flt):
    return all(doc.get(k) == v for k, v in (flt or {}).items())


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, length=None):
        return list(self._docs)


class _Col:
    def __init__(self, docs):
        self.docs = [dict(d) for d in docs]

    def find(self, flt=None, projection=None):
        return _Cursor([dict(d) for d in self.docs if _match(d, flt)])

    async def find_one(self, flt=None, projection=None):
        return next((dict(d) for d in self.docs if _match(d, flt)), None)

    async def update_one(self, flt, update):
        for d in self.docs:
            if _match(d, flt):
                d.update(update["$set"])
                return

    async def update_many(self, flt, update):
        hits = [d for d in self.docs if _match(d, flt)]
        for d in hits:
            d.update(update["$set"])
        return SimpleNamespace(modified_count=len(hits))

    async def delete_one(self, flt):
        hit = next((d for d in self.docs if _match(d, flt)), None)
        if hit:
            self.docs.remove(hit)

    async def delete_many(self, flt):
        self.docs = [d for d in self.docs if not _match(d, flt)]


def _db():
    return SimpleNamespace(
        tenants=_Col([{"id": "tp", "name": "ABC", "status": "pending_approval", "signupRequestedAt": "2026-10-20T02:34:23Z"},
                      {"id": "ta", "name": "Acme", "status": "active"}]),
        users=_Col([{"email": "p@abc.test", "name": "Pat", "tenantId": "tp", "status": "Pending"},
                    {"email": "a@acme.test", "tenantId": "ta", "status": "Active"}]),
        user_consents=_Col([{"tenantId": "tp"}]),
    )


def _call(db, user, method, path):
    import tenant_signup_endpoints as mod
    from catalogue_mounts_billing_identity import TENANT_MANAGEMENT_GUARD
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[TENANT_MANAGEMENT_GUARD] = lambda: user
    with patch.object(mod, "mongodb", SimpleNamespace(db=db)), patch.object(mod, "_audit", AsyncMock()):
        with TestClient(app) as c:
            return c.request(method, path)


def test_only_a_super_admin_reviews_signups():
    db = _db()
    for method, path in (("GET", "/api/tenants/signups/pending"), ("POST", "/api/tenants/signups/tp/approve"),
                         ("POST", "/api/tenants/signups/tp/reject")):
        assert _call(db, ADMIN, method, path).status_code == 403, path
    assert db.tenants.docs[0]["status"] == "pending_approval"


def test_pending_signups_list_names_the_requesting_admin():
    body = _call(_db(), SUPER, "GET", "/api/tenants/signups/pending").json()
    assert body["signups"] == [{"id": "tp", "name": "ABC", "requestedAt": "2026-10-20T02:34:23Z",
                                "adminEmail": "p@abc.test", "adminName": "Pat"}]


def test_approval_activates_the_tenant_and_its_admin():
    db = _db()
    resp = _call(db, SUPER, "POST", "/api/tenants/signups/tp/approve")
    assert resp.status_code == 200 and resp.json()["usersActivated"] == 1
    assert db.tenants.docs[0]["status"] == "active" and db.tenants.docs[0]["approvedBy"] == "super@omni.test"
    assert db.users.docs[0]["status"] == "Active"
    from authentication_service import account_is_active
    assert account_is_active(db.users.docs[0])
    # Approving twice, or an active tenant, is not a pending sign-up.
    assert _call(db, SUPER, "POST", "/api/tenants/signups/tp/approve").status_code == 404
    assert _call(db, SUPER, "POST", "/api/tenants/signups/ta/approve").status_code == 404


def test_rejection_removes_only_the_pending_signup():
    db = _db()
    assert _call(db, SUPER, "POST", "/api/tenants/signups/tp/reject").status_code == 200
    assert [t["id"] for t in db.tenants.docs] == ["ta"]
    assert [u["email"] for u in db.users.docs] == ["a@acme.test"]
    assert db.user_consents.docs == []
    assert _call(db, SUPER, "POST", "/api/tenants/signups/ta/reject").status_code == 404
