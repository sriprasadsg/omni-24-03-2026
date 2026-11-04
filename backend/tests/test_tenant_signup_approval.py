"""Approval of self-service sign-ups: only a Super Admin lists, approves or rejects them; approval
activates the tenant and its pending admin, rejection removes both. In-memory store."""
import os
import sys
from datetime import datetime, timedelta, timezone
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


def _ago(**delta):
    return (datetime.now(timezone.utc) - timedelta(**delta)).isoformat()


RECENT = _ago(days=1)


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, key, direction=1):
        self._docs.sort(key=lambda d: d.get(key) or "", reverse=direction < 0)
        return self

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
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)

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
        tenants=_Col([{"id": "tp", "name": "ABC", "status": "pending_approval", "signupRequestedAt": RECENT},
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
        with TestClient(app, raise_server_exceptions=False) as c:
            return c.request(method, path)


def test_only_a_super_admin_reviews_signups():
    db = _db()
    for method, path in (("GET", "/api/tenants/signups/pending"), ("POST", "/api/tenants/signups/tp/approve"),
                         ("POST", "/api/tenants/signups/tp/reject")):
        assert _call(db, ADMIN, method, path).status_code == 403, path
    assert db.tenants.docs[0]["status"] == "pending_approval"


def test_pending_signups_list_names_the_requesting_admin():
    body = _call(_db(), SUPER, "GET", "/api/tenants/signups/pending").json()
    assert body["signups"] == [{"id": "tp", "name": "ABC", "requestedAt": RECENT,
                                "adminEmail": "p@abc.test", "adminName": "Pat", "adminEmailVerified": False}]


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


# ── 77 WR-12: approval writes the users first and the tenant last ──

class _FailOnce:
    """Wraps one collection method so its first call raises, like a store error mid-approval."""

    def __init__(self, col, name):
        self.calls = 0
        real = getattr(col, name)

        async def flaky(*a, **k):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("store hiccup")
            return await real(*a, **k)

        setattr(col, name, flaky)


def test_a_failed_user_write_leaves_the_signup_pending_and_retryable():
    db = _db()
    _FailOnce(db.users, "update_many")
    assert _call(db, SUPER, "POST", "/api/tenants/signups/tp/approve").status_code == 500
    assert db.tenants.docs[0]["status"] == "pending_approval"
    retry = _call(db, SUPER, "POST", "/api/tenants/signups/tp/approve")
    assert retry.status_code == 200 and retry.json()["usersActivated"] == 1
    assert db.tenants.docs[0]["status"] == "active" and db.users.docs[0]["status"] == "Active"


def test_a_failed_tenant_write_keeps_the_signup_listed_and_a_retry_completes_it():
    db = _db()
    _FailOnce(db.tenants, "update_one")
    assert _call(db, SUPER, "POST", "/api/tenants/signups/tp/approve").status_code == 500
    assert db.users.docs[0]["status"] == "Active" and db.tenants.docs[0]["status"] == "pending_approval"
    listed = _call(db, SUPER, "GET", "/api/tenants/signups/pending").json()["signups"]
    assert [s["id"] for s in listed] == ["tp"]
    assert _call(db, SUPER, "POST", "/api/tenants/signups/tp/approve").status_code == 200
    assert db.tenants.docs[0]["status"] == "active"


def test_reject_after_a_half_finished_approval_removes_the_activated_admin():
    """The tenant goes, so no account of it may stay behind, whatever its status."""
    db = _db()
    db.users.docs[0]["status"] = "Active"  # the user write of an approval landed, the tenant write did not
    assert _call(db, SUPER, "POST", "/api/tenants/signups/tp/reject").status_code == 200
    assert [u["email"] for u in db.users.docs] == ["a@acme.test"]
    assert [t["id"] for t in db.tenants.docs] == ["ta"]


def test_approval_answers_409_when_the_signup_was_removed_meanwhile():
    db = _db()
    real = db.users.update_many

    async def removed_meanwhile(flt, update):
        result = await real(flt, update)
        db.tenants.docs = [t for t in db.tenants.docs if t["id"] != "tp"]
        return result

    db.users.update_many = removed_meanwhile
    assert _call(db, SUPER, "POST", "/api/tenants/signups/tp/approve").status_code == 409


# ── 77 WR-13: unconfirmed sign-ups expire ──

def test_expired_signups_drop_out_of_the_pending_list():
    import tenant_signup_endpoints as signups
    db = _db()
    db.tenants.docs.append({"id": "told", "name": "Old", "status": "pending_approval",
                            "signupRequestedAt": _ago(days=signups.SIGNUP_PENDING_DAYS, minutes=1)})
    db.users.docs.append({"email": "o@old.test", "name": "Olly", "tenantId": "told", "status": "Pending"})
    listed = _call(db, SUPER, "GET", "/api/tenants/signups/pending").json()["signups"]
    assert [s["id"] for s in listed] == ["tp"]


def test_an_expired_signup_cannot_be_approved_but_can_be_rejected():
    import tenant_signup_endpoints as signups
    db = _db()
    db.tenants.docs[0]["signupRequestedAt"] = _ago(days=signups.SIGNUP_PENDING_DAYS + 1)
    resp = _call(db, SUPER, "POST", "/api/tenants/signups/tp/approve")
    assert resp.status_code == 410 and "expired" in resp.json()["detail"]
    assert db.tenants.docs[0]["status"] == "pending_approval" and db.users.docs[0]["status"] == "Pending"
    assert _call(db, SUPER, "POST", "/api/tenants/signups/tp/reject").status_code == 200
    assert [t["id"] for t in db.tenants.docs] == ["ta"]


def test_a_signup_whose_age_cannot_be_read_never_expires():
    import tenant_signup_endpoints as signups
    for stored in (None, "", "not a date"):
        assert signups.signup_expired({"signupRequestedAt": stored}) is False
    assert signups.signup_expired({"createdAt": _ago(days=30)}) is True
    assert signups.signup_expired({"signupRequestedAt": "2020-01-01T00:00:00"}) is True
