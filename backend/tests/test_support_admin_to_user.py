"""
Regression tests for admin_to_user support conversations.

Root bug: the admin picker sends `target_user_id = user.id` (an internal uuid),
but the JWT `sub` — and therefore the user's access filter and the WS session
key — is the user's *email*. So the stored conversation was invisible to the
target user and no realtime event reached them.

These tests use a tiny in-memory collection that actually evaluates the Mongo
queries the endpoints build (equality, $or, $in, $nin) so we prove the target
user can genuinely list/read the conversation after the fix.
"""
import sys
import os
import asyncio
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from auth_types import TokenData
from support_endpoints import (
    start_conversation, list_conversations, get_conversation, StartConvoRequest,
)


# ── Minimal in-memory Mongo-ish collection ────────────────────────────────────

def _match(doc, query):
    for k, v in query.items():
        if k == "$or":
            if not any(_match(doc, sub) for sub in v):
                return False
        elif k == "$and":
            if not all(_match(doc, sub) for sub in v):
                return False
        elif isinstance(v, dict) and ("$in" in v or "$nin" in v):
            if "$in" in v and doc.get(k) not in v["$in"]:
                return False
            if "$nin" in v and doc.get(k) in v["$nin"]:
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


def _project(doc, projection):
    if not projection:
        return dict(doc)
    inclusion = any(val == 1 for key, val in projection.items() if key != "_id")
    if inclusion:
        keep = {k for k, val in projection.items() if val == 1}
        out = {k: doc[k] for k in keep if k in doc}
    else:
        out = {k: v for k, v in doc.items() if projection.get(k) != 0}
    if projection.get("_id") == 0:
        out.pop("_id", None)
    return out


class _Cursor:
    def __init__(self, docs):
        self._docs = docs
    def sort(self, *a, **k):
        return self
    async def to_list(self, n=None):
        return self._docs[:n] if n else list(self._docs)


class _Collection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return type("R", (), {"inserted_id": "x"})()
    async def find_one(self, query, projection=None):
        for d in self.docs:
            if _match(d, query):
                return _project(d, projection)
        return None
    def find(self, query, projection=None):
        return _Cursor([_project(d, projection) for d in self.docs if _match(d, query)])
    async def update_one(self, query, update):
        for d in self.docs:
            if _match(d, query):
                d.update(update.get("$set", {}))
                return type("R", (), {"matched_count": 1})()
        return type("R", (), {"matched_count": 0})()
    async def count_documents(self, query):
        return sum(1 for d in self.docs if _match(d, query))


class _DB:
    def __init__(self, users, convos):
        self.support_conversations = convos
        self._db = type("Inner", (), {"users": users})()


# ── Fixtures ──────────────────────────────────────────────────────────────────

ADMIN = TokenData(username="admin@t1.com", role="Tenant Admin", tenant_id="t1")

USER_DOC = {
    "id":       "uuid-user-123",           # what the picker sends as target_user_id
    "email":    "alice@t1.com",            # what the user actually logs in with (sub)
    "username": "alice@t1.com",
    "name":     "Alice",
    "role":     "user",
    "tenantId": "t1",
}
ADMIN_DOC = {"email": "admin@t1.com", "username": "admin@t1.com", "name": "Admin", "tenantId": "t1"}


def _make_db():
    return _DB(_Collection([dict(USER_DOC), dict(ADMIN_DOC)]), _Collection())


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_admin_to_user_stores_target_login_id_not_uuid():
    db = _make_db()
    with patch("support_endpoints.get_database", return_value=db):
        convo = _run(start_conversation(
            StartConvoRequest(
                subject="Hi", message="Please check your agent",
                chat_type="admin_to_user",
                target_user_id="uuid-user-123",      # picker sends the uuid
                target_user_name="Alice",
            ),
            ADMIN,
        ))
    # The fix: stored target must be the login id (email), NOT the uuid.
    assert convo["target_user_id"] == "alice@t1.com"
    assert convo["target_user_id"] != "uuid-user-123"


def test_target_user_can_list_and_open_admin_initiated_convo():
    db = _make_db()
    with patch("support_endpoints.get_database", return_value=db):
        convo = _run(start_conversation(
            StartConvoRequest(
                subject="Hi", message="hello",
                chat_type="admin_to_user",
                target_user_id="uuid-user-123",
                target_user_name="Alice",
            ),
            ADMIN,
        ))
        # Alice authenticates as her email (sub) — the access filter keys on username.
        alice = TokenData(username="alice@t1.com", role="user", tenant_id="t1")
        listed = _run(list_conversations(current_user=alice))
        opened = _run(get_conversation(convo["id"], current_user=alice))

    assert any(c["id"] == convo["id"] for c in listed), "user must see the admin-started convo in their list"
    assert opened["id"] == convo["id"]
    assert opened["messages"][0]["content"] == "hello"


def test_unrelated_user_cannot_see_convo():
    db = _make_db()
    with patch("support_endpoints.get_database", return_value=db):
        _run(start_conversation(
            StartConvoRequest(
                subject="Hi", message="hello",
                chat_type="admin_to_user",
                target_user_id="uuid-user-123", target_user_name="Alice",
            ),
            ADMIN,
        ))
        bob = TokenData(username="bob@t1.com", role="user", tenant_id="t1")
        listed = _run(list_conversations(current_user=bob))
    assert listed == [], "a different user must not see someone else's direct convo"
