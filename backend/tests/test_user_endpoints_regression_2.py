"""
Regression: ISSUE-011 — only one user can ever be created through POST /api/users
Found by /qa on 2026-10-13
Report: .gstack/qa-reports/run-20261013T151919Z/qa-report-127.0.0.1-2026-10-13.md

Live repro on a fresh install: the first API-created user (a tenant admin) succeeded,
the next POST /api/users returned 400 "A user with this email already exists." for an
email nobody had. create_user inserts no `id`, and users has a unique (non-sparse) index
on `id`, so every API-created user after the first collides on id=null.

Value: protects=two different users can be created back to back and each gets its own
id; fails_when=create_user omits `id` again; why_new=no test creates more than one user
through the endpoint; seam=none; no_claim=real Mongo index behaviour (an in-memory fake
enforces the unique id and (email, tenantId) indexes the way Mongo treats a missing field
as null). Hermetic: no Mongo.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

from pymongo.errors import DuplicateKeyError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import user_endpoints
from auth_types import TokenData


class _Users:
    """Unique on `id` (missing == None, as in a non-sparse Mongo index) and on (email, tenantId)."""

    def __init__(self):
        self.docs = []

    async def find_one(self, flt, *_a, **_k):
        return next((d for d in self.docs if all(d.get(k) == v for k, v in flt.items())), None)

    async def insert_one(self, doc, *_a, **_k):
        for d in self.docs:
            if d.get("id") == doc.get("id") or (d["email"], d["tenantId"]) == (doc["email"], doc["tenantId"]):
                raise DuplicateKeyError("E11000 duplicate key error collection: users")
        doc["_id"] = f"oid-{len(self.docs)}"
        self.docs.append(doc)
        return MagicMock(inserted_id=doc["_id"])


async def test_two_users_can_be_created_one_after_another():
    db = MagicMock()
    db.users = _Users()
    db.tenants.find_one = AsyncMock(return_value={"id": "tenant-a"})
    caller = TokenData(username="qa-super@qa.omni.test", role="Super Admin", tenant_id="platform-admin")

    def _body(email):
        return user_endpoints.UserCreate(email=email, password="Str0ng!Passw0rd", full_name=email,
                                         role="Tenant Admin", tenantId="tenant-a")

    with patch.object(user_endpoints, "get_database", return_value=db), \
            patch.object(user_endpoints, "assert_can_assign_role", AsyncMock()), \
            patch.object(user_endpoints, "_audit", AsyncMock()):
        first = await user_endpoints.create_user(_body("admin-one@example.com"), current_user=caller)
        second = await user_endpoints.create_user(_body("admin-two@example.com"), current_user=caller)

    assert first["email"] == "admin-one@example.com"
    assert second["email"] == "admin-two@example.com"
    ids = [d.get("id") for d in db.users.docs]
    assert all(ids) and len(set(ids)) == 2, ids
