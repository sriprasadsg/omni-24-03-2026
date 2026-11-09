"""The Knowledge Base side of the service desk (Phase 85, plan 85-15, DESK-06, DESK-07, decisions D-16, D-17,
D-26, D-27, D-28). Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=an author marks and edits only the tenant's own articles for the desk, the platform articles stay
out of reach, the starter copy never duplicates under a double click or a race, and the gap list reaches only
people who hold both ticket and Knowledge Base permissions; fails_when=a global or foreign article is patched or
marked Help desk, a second press adds a copy, two admins at once add eight, the gap list answers a Knowledge Base
editor without ticket access, or the groups change order between calls; no_claim=the desk reading the articles
(test_service_desk_retrieval.py) and the screen (85-16).
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import knowledge_endpoints
import knowledge_helpdesk_endpoints
from authentication_service import get_current_user
from auth_types import TokenData
from rbac_service import rbac_service
from service_desk import HELPDESK_CONTENT_MAX, gaps, messages, starters, store
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests._route_walk import probe_real_app
from tests.service_desk_support import seed_article

PERMISSIONS = {
    "manager": ["manage:ai_risks", "view:dashboard"],       # edits articles and sees tickets
    "editor": ["manage:ai_risks"],                          # Knowledge Base only
    "agent": ["view:dashboard"],                            # tickets only
    "reader": [],
}
STARTER_ORDER = ["password_reset", "vpn", "printer", "agent_tray"]
OVER = HELPDESK_CONTENT_MAX + 1


def person(name, tenant="t1"):
    return TokenData(username=name, role="user", tenant_id=tenant, mfa_verified=True, auth_source="session")


class KbApp:
    """The Knowledge Base router (with the helpdesk router it includes) on one app; the caller is chosen per
    request and holds the permissions PERMISSIONS names."""

    def __init__(self, db, monkeypatch):
        self.db = db
        self.user = None
        monkeypatch.setattr(knowledge_endpoints, "get_database", lambda: db)
        monkeypatch.setattr(knowledge_helpdesk_endpoints, "get_database", lambda: db)

        async def permissions(user):
            return list(PERMISSIONS.get(user.username, []))

        monkeypatch.setattr(rbac_service, "get_user_permissions", permissions)
        self.app = FastAPI()
        self.app.include_router(knowledge_endpoints.router)
        self.app.dependency_overrides[get_current_user] = lambda: self.user

    async def call(self, method, path, *, who="manager", tenant="t1", json=None):
        self.user = person(who, tenant)
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, json=json)


@pytest.fixture
async def kb(mongo_db, monkeypatch):  # noqa: F811
    await store.ensure_indexes(mongo_db)
    return KbApp(mongo_db, monkeypatch)


async def _seed_global(db):
    await db.knowledge_docs.insert_one({"id": "kb-seed-1", "tenantId": "global", "title": "OWASP", "content": "x",
                                        "tags": [], "source": "platform_seed", "createdAt": "2026-01-01T00:00:00+00:00"})


# ---------------------------------------------------------------- ingest and edit (Task 1)

async def test_ingest_stores_the_help_desk_mark_and_defaults_to_off(kb):
    """protects=D-17 the mark is stored as given and absent means off; fails_when=ingest drops the flag."""
    on = await kb.call("POST", "/api/knowledge/ingest", json={"content": "Printer steps", "title": "Printer", "helpdesk": True})
    off = await kb.call("POST", "/api/knowledge/ingest", json={"content": "Other note", "title": "Note"})
    assert on.status_code == 200 and off.status_code == 200
    assert (await kb.db.knowledge_docs.find_one({"id": on.json()["id"]}))["helpdesk"] is True
    assert (await kb.db.knowledge_docs.find_one({"id": off.json()["id"]}))["helpdesk"] is False


async def test_ingest_refuses_an_over_long_help_desk_article(kb):
    """protects=T-85-59 the 20000-character cap; fails_when=a 20001-character Help desk article is stored."""
    resp = await kb.call("POST", "/api/knowledge/ingest", json={"content": "a" * OVER, "title": "Big", "helpdesk": True})
    assert resp.status_code == 400
    assert resp.json()["detail"] == messages.API_DETAIL["article_too_long"].replace("{max}", str(HELPDESK_CONTENT_MAX))
    assert await kb.db.knowledge_docs.count_documents({"tenantId": "t1"}) == 0


async def test_the_platform_tenant_can_never_mark_an_article_help_desk(kb):
    """protects=D-16 the platform organization is not eligible; fails_when=its article is stored as Help desk."""
    resp = await kb.call("POST", "/api/knowledge/ingest", tenant="platform-admin",
                         json={"content": "Steps", "title": "T", "helpdesk": True})
    assert resp.status_code == 403 and resp.json()["detail"] == messages.API_DETAIL["platform_tenant"]
    await seed_article(kb.db, "platform-admin", "kb-p", title="P", content="c", helpdesk=False)
    patched = await kb.call("PATCH", "/api/knowledge/docs/kb-p", tenant="platform-admin", json={"helpdesk": True})
    assert patched.status_code == 403
    assert (await kb.db.knowledge_docs.find_one({"id": "kb-p"}))["helpdesk"] is False


async def test_patch_marks_an_article_and_returns_it_with_a_new_updated_time(kb):
    """protects=D-17 the edit route; fails_when=the mark is not stored, updatedAt stays unset, or tags are lost."""
    await seed_article(kb.db, "t1", "kb-a", title="Old", content="Old text", helpdesk=False, tags=["x"])
    resp = await kb.call("PATCH", "/api/knowledge/docs/kb-a",
                         json={"helpdesk": True, "title": " New title ", "content": "New text", "tags": ["vpn", "wifi"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "kb-a" and body["helpdesk"] is True and body["title"] == "New title"
    assert body["content"] == "New text" and body["tags"] == ["vpn", "wifi"] and body["updatedAt"]
    assert "_id" not in body
    stored = await kb.db.knowledge_docs.find_one({"id": "kb-a"})
    assert stored["helpdesk"] is True and stored["updatedAt"] == body["updatedAt"] and stored["tenantId"] == "t1"


async def test_patch_changes_only_the_keys_given(kb):
    """protects=a partial edit; fails_when=a missing key blanks the field."""
    await seed_article(kb.db, "t1", "kb-a", title="Keep", content="Keep text", helpdesk=True, tags=["k"])
    await kb.call("PATCH", "/api/knowledge/docs/kb-a", json={"content": "Changed"})
    stored = await kb.db.knowledge_docs.find_one({"id": "kb-a"})
    assert (stored["title"], stored["content"], stored["tags"], stored["helpdesk"]) == ("Keep", "Changed", ["k"], True)


async def test_patch_refuses_bad_values_in_plain_words(kb):
    """protects=T-85-59 and the plain-words refusals; fails_when=an empty title, an over-long article, too many
    tags, a long tag or an unknown key is accepted, or the text differs from the table."""
    await seed_article(kb.db, "t1", "kb-a", title="T", content="C", helpdesk=False)
    path = "/api/knowledge/docs/kb-a"
    empty = await kb.call("PATCH", path, json={"title": "  "})
    assert empty.status_code == 422 and empty.json()["detail"] == messages.API_DETAIL["article_title"]
    blank = await kb.call("PATCH", path, json={"content": ""})
    assert blank.status_code == 422 and blank.json()["detail"] == messages.API_DETAIL["article_content"]
    long = await kb.call("PATCH", path, json={"content": "a" * OVER})
    assert long.status_code == 422
    assert long.json()["detail"] == messages.API_DETAIL["article_too_long"].replace("{max}", str(HELPDESK_CONTENT_MAX))
    assert (await kb.call("PATCH", path, json={"title": "a" * 201})).status_code == 422
    assert (await kb.call("PATCH", path, json={"tags": [f"t{i}" for i in range(21)]})).status_code == 422
    assert (await kb.call("PATCH", path, json={"tags": ["a" * 41]})).status_code == 422
    assert (await kb.call("PATCH", path, json={"tenantId": "t2"})).status_code == 422
    assert (await kb.call("PATCH", path, json={})).status_code == 422
    ok = await kb.call("PATCH", path, json={"title": "a" * 200, "content": "a" * HELPDESK_CONTENT_MAX,
                                            "tags": ["a" * 40] * 20})
    assert ok.status_code == 200
    assert (await kb.db.knowledge_docs.find_one({"id": "kb-a"}))["tenantId"] == "t1"


async def test_marking_a_legacy_over_long_article_help_desk_is_refused(kb):
    """protects=T-85-59 a stored article over the cap cannot be marked without shortening it; fails_when=it is marked."""
    await seed_article(kb.db, "t1", "kb-long", title="Long", content="a" * OVER, helpdesk=False)
    resp = await kb.call("PATCH", "/api/knowledge/docs/kb-long", json={"helpdesk": True})
    assert resp.status_code == 422
    assert (await kb.db.knowledge_docs.find_one({"id": "kb-long"}))["helpdesk"] is False


async def test_a_platform_article_or_another_tenants_article_answers_404_and_is_not_touched(kb):
    """protects=D-16 / T-85-57 global and foreign ids are out of reach; fails_when=either is changed or answers 200."""
    await _seed_global(kb.db)
    await seed_article(kb.db, "t2", "kb-other", title="Theirs", content="Their text", helpdesk=False)
    for doc_id in ("kb-seed-1", "kb-other", "kb-missing"):
        resp = await kb.call("PATCH", f"/api/knowledge/docs/{doc_id}", json={"helpdesk": True, "title": "Mine now"})
        assert resp.status_code == 404 and resp.json()["detail"] == messages.API_DETAIL["article_not_found"]
    assert "helpdesk" not in await kb.db.knowledge_docs.find_one({"id": "kb-seed-1"})
    other = await kb.db.knowledge_docs.find_one({"id": "kb-other"})
    assert other["helpdesk"] is False and other["title"] == "Theirs"
    delete = await kb.call("DELETE", "/api/knowledge/docs/kb-seed-1")
    assert delete.status_code == 404 and await kb.db.knowledge_docs.count_documents({"id": "kb-seed-1"}) == 1


async def test_patch_needs_the_article_permission(kb):
    """protects=the edit route is an author action; fails_when=a ticket user or a reader can edit."""
    await seed_article(kb.db, "t1", "kb-a", title="T", content="C", helpdesk=False)
    for who in ("agent", "reader"):
        assert (await kb.call("PATCH", "/api/knowledge/docs/kb-a", who=who, json={"helpdesk": True})).status_code == 403
    assert (await kb.call("PATCH", "/api/knowledge/docs/kb-a", who="editor", json={"helpdesk": True})).status_code == 200


# ---------------------------------------------------------------- the list (Task 1)

async def test_the_list_carries_the_flags_and_the_per_document_fields(kb):
    """protects=the screen's data; fails_when=a document lacks helpdesk, starterKey or updatedAt, the count
    includes a global or foreign article, or the global article reads as a Help desk article."""
    await _seed_global(kb.db)
    await seed_article(kb.db, "t1", "kb-1", title="One", content="c", helpdesk=True)
    await seed_article(kb.db, "t1", "kb-2", title="Two", content="c", helpdesk=False)
    await seed_article(kb.db, "t2", "kb-3", title="Foreign", content="c", helpdesk=True)
    await kb.db.knowledge_docs.update_many({"tenantId": "t1"}, {"$set": {"createdAt": "2026-02-01T00:00:00+00:00"}})
    await kb.db.knowledge_docs.update_one({"id": "kb-2"}, {"$set": {"updatedAt": "2026-03-01T00:00:00+00:00"}})
    body = (await kb.call("GET", "/api/knowledge/docs")).json()
    by_id = {d["id"]: d for d in body["docs"]}
    assert set(by_id) == {"kb-seed-1", "kb-1", "kb-2"}
    for doc in by_id.values():
        assert isinstance(doc["helpdesk"], bool) and "starterKey" in doc and doc["updatedAt"]
    assert by_id["kb-1"]["updatedAt"] == "2026-02-01T00:00:00+00:00"      # never edited: the creation time
    assert by_id["kb-2"]["updatedAt"] == "2026-03-01T00:00:00+00:00"
    assert by_id["kb-1"]["helpdesk"] is True and by_id["kb-2"]["helpdesk"] is False
    assert by_id["kb-seed-1"]["helpdesk"] is False
    assert body["canManageArticles"] is True and body["canSeeGaps"] is True
    assert body["helpdeskCount"] == 1 and body["starterMissing"] == 4 and body["deskOff"] is False


async def test_the_flags_follow_the_callers_permissions(kb):
    """protects=D-27 the gap tab is offered only with both permissions; fails_when=canSeeGaps is true for a
    Knowledge Base editor without ticket access."""
    seen = {}
    for who in ("manager", "editor", "agent", "reader"):
        body = (await kb.call("GET", "/api/knowledge/docs", who=who)).json()
        seen[who] = (body["canManageArticles"], body["canSeeGaps"])
    assert seen == {"manager": (True, True), "editor": (True, False), "agent": (False, False), "reader": (False, False)}


async def test_the_list_says_when_the_desk_is_off_for_the_tenant(kb):
    """protects=the Off notice on the Knowledge Base screen; fails_when=deskOff ignores serviceDesk.mode."""
    await kb.db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"serviceDesk": {"mode": "off"}}}, upsert=True)
    assert (await kb.call("GET", "/api/knowledge/docs")).json()["deskOff"] is True
    assert (await kb.call("GET", "/api/knowledge/docs", tenant="t2")).json()["deskOff"] is False


# ---------------------------------------------------------------- the starter copy (Task 2)

STARTERS_PATH = "/api/knowledge/helpdesk/starters"


async def _starter_docs(db, tenant="t1"):
    return await db.knowledge_docs.find({"tenantId": tenant, "starterKey": {"$type": "string"}}, {"_id": 0}).to_list(50)


async def test_the_starter_status_of_an_empty_tenant(kb):
    """protects=DESK-07 empty; fails_when=the status is not total 4, missing 4 for a tenant with no copies."""
    resp = await kb.call("GET", STARTERS_PATH)
    assert resp.status_code == 200 and resp.json() == {"total": 4, "missing": 4}


async def test_the_first_press_adds_the_four_starters_in_order_as_editable_help_desk_articles(kb):
    """protects=D-28 the copy is the tenant's own; fails_when=a count or the order is wrong, a copy lacks the mark,
    the key, the source or the tenant, or the text differs from service_desk.starters."""
    resp = await kb.call("POST", STARTERS_PATH)
    assert resp.status_code == 200
    assert resp.json() == {"added": 4, "existing": 0, "addedKeys": STARTER_ORDER}
    docs = {d["starterKey"]: d for d in await _starter_docs(kb.db)}
    assert sorted(docs) == sorted(STARTER_ORDER)
    for starter in starters.STARTERS:
        doc = docs[starter["key"]]
        assert doc["helpdesk"] is True and doc["source"] == "starter" and doc["tenantId"] == "t1"
        assert doc["title"] == starter["title"] and doc["content"] == starter["content"]
        assert doc["createdBy"] == "manager" and doc["updatedAt"]
    assert await kb.db.knowledge_docs.count_documents({"tenantId": {"$ne": "t1"}}) == 0
    assert (await kb.call("GET", STARTERS_PATH)).json() == {"total": 4, "missing": 0}


async def test_pressing_it_again_adds_nothing_and_keeps_an_edited_copy(kb):
    """protects=D-28 adjacency; fails_when=a second press adds a copy or overwrites the admin's edit."""
    await kb.call("POST", STARTERS_PATH)
    doc = (await _starter_docs(kb.db))[0]
    await kb.call("PATCH", f"/api/knowledge/docs/{doc['id']}", json={"content": "Our own wording", "helpdesk": False})
    again = await kb.call("POST", STARTERS_PATH)
    assert again.json() == {"added": 0, "existing": 4, "addedKeys": []}
    docs = await _starter_docs(kb.db)
    assert len(docs) == 4
    kept = next(d for d in docs if d["id"] == doc["id"])
    assert kept["content"] == "Our own wording" and kept["helpdesk"] is False


async def test_two_admins_at_once_leave_exactly_one_copy_of_each(kb):
    """protects=T-85-58 the race; fails_when=two concurrent presses leave more than four starter documents or the
    two answers do not account for four additions."""
    first, second = await asyncio.gather(kb.call("POST", STARTERS_PATH), kb.call("POST", STARTERS_PATH))
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["added"] + second.json()["added"] == 4
    assert first.json()["existing"] + second.json()["existing"] == 4
    docs = await _starter_docs(kb.db)
    assert sorted(d["starterKey"] for d in docs) == sorted(STARTER_ORDER)


async def test_a_deleted_copy_is_the_only_one_added_back(kb):
    """protects=DESK-07 ordering of the gap; fails_when=the call adds more than the missing starter."""
    await kb.call("POST", STARTERS_PATH)
    gone = next(d for d in await _starter_docs(kb.db) if d["starterKey"] == "printer")
    assert (await kb.call("DELETE", f"/api/knowledge/docs/{gone['id']}")).status_code == 200
    assert (await kb.call("GET", STARTERS_PATH)).json()["missing"] == 1
    resp = await kb.call("POST", STARTERS_PATH)
    assert resp.json() == {"added": 1, "existing": 3, "addedKeys": ["printer"]}
    assert len(await _starter_docs(kb.db)) == 4


async def test_each_tenant_gets_its_own_copies(kb):
    """protects=tenant isolation; fails_when=one tenant's press changes another's status."""
    await kb.call("POST", STARTERS_PATH, tenant="t1")
    assert (await kb.call("GET", STARTERS_PATH, tenant="t2")).json()["missing"] == 4
    assert (await kb.call("POST", STARTERS_PATH, tenant="t2")).json()["added"] == 4
    assert len(await _starter_docs(kb.db, "t1")) == 4 and len(await _starter_docs(kb.db, "t2")) == 4


async def test_the_starter_routes_need_the_article_permission_and_a_real_tenant(kb):
    """protects=D-28 an admin action, not for the platform organization; fails_when=a ticket user or reader presses
    it, or the platform tenant gets copies."""
    for who in ("agent", "reader"):
        assert (await kb.call("GET", STARTERS_PATH, who=who)).status_code == 403
        assert (await kb.call("POST", STARTERS_PATH, who=who)).status_code == 403
    for method in ("GET", "POST"):
        resp = await kb.call(method, STARTERS_PATH, tenant="platform-admin")
        assert resp.status_code == 403 and resp.json()["detail"] == messages.API_DETAIL["platform_tenant"]
    assert await kb.db.knowledge_docs.count_documents({}) == 0


def test_nothing_seeds_the_starters_automatically():
    """protects=D-28 only an admin's press adds the copies; fails_when=a migration or startup hook calls copy_docs."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    users = []
    for folder, _dirs, files in os.walk(root):
        if "venv" in folder or "tests" in folder or "node_modules" in folder:
            continue
        for name in files:
            if name.endswith(".py") and "copy_docs" in open(os.path.join(folder, name), encoding="utf-8").read():
                users.append(name)
    assert sorted(users) == ["knowledge_helpdesk_endpoints.py", "starters.py"]


# ---------------------------------------------------------------- the inherited guard (Task 1)

def _case(path, role, *, method="GET"):
    return {"method": method, "path": path, "role": role, "tenant_id": "tenant-a", "auth": "session"}


def test_the_new_routes_inherit_the_knowledge_base_guard():
    """protects=the manage:settings guard of the Knowledge Base catalogue covers the included router; fails_when=
    a viewer (no manage:settings) reaches any new route, or the tenant administrator is refused by the guard."""
    routes = [("PATCH", "/api/knowledge/docs/kb-x"), ("GET", "/api/knowledge/helpdesk/starters"),
              ("POST", "/api/knowledge/helpdesk/starters")]
    for role in ("nobody", "viewer"):
        denied = probe_real_app([_case(p, role, method=m) for m, p in routes])
        assert denied == [403] * len(routes), (role, dict(zip(routes, denied)))
    allowed = probe_real_app([_case(p, "tenant_admin", method=m) for m, p in routes])
    assert 403 not in allowed, dict(zip(routes, allowed))
