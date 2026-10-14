"""Shared fakes for the agent-identity tests: an in-memory store wrapped in the
real TenantIsolatedDatabase, plus agent / user tokens."""
import time
from datetime import timedelta
from unittest.mock import MagicMock

import jwt

from authentication_service import ALGORITHM, SECRET_KEY, create_access_token
from database import TenantIsolatedDatabase


def matches(doc, flt):
    for k, v in (flt or {}).items():
        if k == "$or":
            if not any(matches(doc, c) for c in v):
                return False
        elif isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        elif doc.get(k) != v:
            return False
    return True


class Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, length=None):
        return list(self._docs)


class Collection:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]
        self.name = "fake"

    async def find_one(self, flt=None, projection=None, **k):
        return next((dict(d) for d in self.docs if matches(d, flt)), None)

    def find(self, flt=None, projection=None, **k):
        return Cursor([dict(d) for d in self.docs if matches(d, flt)])

    async def insert_one(self, doc, **k):
        self.docs.append(dict(doc))
        return MagicMock(inserted_id=doc.get("_id"))

    async def update_one(self, flt, update, upsert=False, **k):
        for d in self.docs:
            if matches(d, flt):
                d.update(update.get("$set", {}))
                for key, val in update.get("$push", {}).items():
                    d.setdefault(key, []).append(val)
                return MagicMock(matched_count=1, modified_count=1)
        return MagicMock(matched_count=0, modified_count=0)

    async def update_many(self, flt, update, **k):
        n = 0
        for d in self.docs:
            if matches(d, flt):
                d.update(update.get("$set", {}))
                n += 1
        return MagicMock(matched_count=n, modified_count=n)


class RawDB:
    def __init__(self, **collections):
        self._cols = collections

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._cols.setdefault(name, Collection())


def tenant_db(**collections):
    """(TenantIsolatedDatabase, raw store) over the given collections."""
    raw = RawDB(**collections)
    return TenantIsolatedDatabase(raw), raw


def agent_token(agent_id, tenant_id="t1", jti=None):
    data = {"sub": agent_id, "role": "agent", "typ": "agent", "tenant_id": tenant_id}
    if jti:  # create_access_token always picks its own jti
        return jwt.encode({**data, "jti": jti, "exp": time.time() + 3600}, SECRET_KEY, algorithm=ALGORITHM)
    return create_access_token(data=data, expires_delta=timedelta(days=1))


def user_token(username="viewer@acme.test", role="viewer", tenant_id="t1"):
    return create_access_token(data={"sub": username, "role": role, "tenant_id": tenant_id})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}
