"""Shared in-memory role/user store and auth-app builder for the RBAC resolver tests.

The store is the real ``TenantIsolatedDatabase`` over a fake raw handle, so the
tests exercise the wrapper's tenant filter rewriting exactly as production does
(``/login`` is a public path: no tenant ContextVar, wrapper reads are rewritten
to the emergency sentinel).
"""
import uuid
from unittest.mock import MagicMock

import rbac_defaults
from auth_utils import hash_password
from tests.agent_identity_test_support import Collection, RawDB, matches
from database import TenantIsolatedDatabase

TENANT_HEADER = "X-Test-Tenant"


class StoreCollection(Collection):
    """Collection fake that also honours upsert, $set/$setOnInsert/$push, deletes and counts."""

    async def insert_one(self, doc, **k):
        doc = dict(doc)
        doc.setdefault("_id", uuid.uuid4().hex)
        self.docs.append(doc)
        return MagicMock(inserted_id=doc["_id"])

    async def update_one(self, flt, update, upsert=False, **k):
        for d in self.docs:
            if matches(d, flt):
                d.update(update.get("$set", {}))
                for key, val in update.get("$push", {}).items():
                    d.setdefault(key, []).append(val)
                return MagicMock(matched_count=1, modified_count=1, upserted_id=None)
        if not upsert:
            return MagicMock(matched_count=0, modified_count=0, upserted_id=None)
        new_doc = {key: val for key, val in (flt or {}).items()
                   if not key.startswith("$") and not isinstance(val, dict)}
        new_doc.update(update.get("$setOnInsert", {}))
        new_doc.update(update.get("$set", {}))
        for key, val in update.get("$push", {}).items():
            new_doc.setdefault(key, []).append(val)
        new_doc.setdefault("_id", uuid.uuid4().hex)
        self.docs.append(new_doc)
        return MagicMock(matched_count=0, modified_count=0, upserted_id=new_doc["_id"])

    async def delete_one(self, flt, **k):
        for i, d in enumerate(self.docs):
            if matches(d, flt):
                del self.docs[i]
                return MagicMock(deleted_count=1)
        return MagicMock(deleted_count=0)

    async def count_documents(self, flt=None, **k):
        return sum(1 for d in self.docs if matches(d, flt))


class StoreRawDB(RawDB):
    """RawDB whose auto-created collections are StoreCollections."""

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._cols.setdefault(name, StoreCollection())


def role_store(**collections):
    """(TenantIsolatedDatabase, raw store) over the given collections."""
    wrapped = {k: (v if isinstance(v, Collection) else StoreCollection(v)) for k, v in collections.items()}
    raw = StoreRawDB(**wrapped)
    return TenantIsolatedDatabase(raw), raw


def shared_role_docs():
    """The post-seed state of the shared role documents (mirror of the table)."""
    return rbac_defaults.seed_role_documents()


def make_user(email, role, tenant_id, *, password="Password1!", **extra):
    doc = {
        "_id": uuid.uuid4().hex,
        "email": email,
        "username": email,
        "password": hash_password(password),
        "role": role,
        "tenantId": tenant_id,
        "status": "Active",
        "mfa": {"enabled": False},
    }
    doc.update(extra)
    return doc


def reset_shared_limiter():
    """authentication_endpoints decorates /login with the process-wide limiter."""
    from rate_limiter import limiter as shared_limiter
    shared_limiter._storage.reset()


def make_auth_client(db, monkeypatch):
    """TestClient over a minimal auth app whose get_database() returns ``db``.

    Requests carrying ``X-Test-Tenant`` run with that tenant ContextVar (what
    TenantMiddleware derives from the JWT); requests without it, including every
    /login call, run with no tenant context.
    """
    import authentication_endpoints as auth_ep
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from slowapi.util import get_remote_address
    from starlette.middleware.base import BaseHTTPMiddleware
    import tenant_context

    monkeypatch.setattr(auth_ep, "get_database", lambda: db)

    class _TenantFromHeader(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            tenant = request.headers.get(TENANT_HEADER)
            if not tenant:
                return await call_next(request)
            token = tenant_context.set_tenant_id(tenant)
            try:
                return await call_next(request)
            finally:
                tenant_context.reset_tenant_id(token)

    app = FastAPI()
    app.state.limiter = Limiter(key_func=get_remote_address)
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(_TenantFromHeader)
    app.include_router(auth_ep.router)
    return TestClient(app)


def login(client, email, password="Password1!"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def me(client, email, role, tenant_id):
    from auth_types import TokenData
    from authentication_service import get_current_user_mfa_pending
    client.app.dependency_overrides[get_current_user_mfa_pending] = (
        lambda: TokenData(username=email, role=role, tenant_id=tenant_id))
    try:
        return client.get("/api/auth/me", headers={TENANT_HEADER: tenant_id})
    finally:
        client.app.dependency_overrides.pop(get_current_user_mfa_pending, None)
