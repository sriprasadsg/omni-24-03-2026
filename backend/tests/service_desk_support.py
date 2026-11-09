"""Shared helpers for the service desk tests (Phase 85, plan 85-01).

Real-database helpers (use with ``tests._mongo_test_db.mongo_db``): ``seed_desk_tenant``,
``seed_article``. ``ollama_transport`` is the stand-in for the local model (an ``httpx.MockTransport``
plus the list of requests it received): no test reaches a real Ollama. ``desk_app`` mounts the two
ticket routers on one app with the caller's identity chosen per request. Later plans add helpers in
their own test files, not here.
"""
import json
import os
import sys
from typing import Any, Dict, List, Tuple
from unittest.mock import AsyncMock, MagicMock

import httpx
from fastapi import FastAPI

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from authentication_service import get_current_user
from auth_types import TokenData
from tests.autonomy_support import seed_tenant

_TIMINGS = {"eval_count": 40, "eval_duration": 4_000_000_000, "prompt_eval_count": 300,
            "prompt_eval_duration": 6_000_000_000, "load_duration": 1_000_000_000, "total_duration": 11_000_000_000}


async def seed_desk_tenant(db, tid, *, level="undoable_auto", shadow=False, mode=None, ticked=True, screens=True):
    """A tenant with the Autonomous Ops screen ticked (or not), the two ticket screens ticked (or not; the
    Knowledge Base screen also needs its parent switch manage:settings, as tenant_features.switched_off
    reads it) and, when ``mode`` is given, ``autonomy_settings.serviceDesk.mode`` stored (nothing stored otherwise)."""
    await seed_tenant(db, tid, level=level, max_level=level, shadow=shadow, ticked=ticked)
    if screens:
        await db.tenants.update_one({"id": tid}, {"$addToSet": {"enabledFeatures": {
            "$each": ["screen:internalTickets", "screen:knowledgeBase", "manage:settings"]}}})
    if mode is not None:
        await db.autonomy_settings.update_one({"tenantId": tid}, {"$set": {"serviceDesk": {"mode": mode}}})


async def desk_indexes_without_ttl(db):
    """The desk indexes without the two 90-day TTL indexes (finished_ttl on service_desk_jobs, created_ttl on
    service_desk_gaps). Fixtures that stamp rows from fixed clocks (or rows 100 days old) must not run with the TTL
    monitor, which would delete them once the real date passes the stamp; migration 032's own test keeps covering
    the TTL indexes."""
    from autonomous_ops.scope import raw
    from service_desk import store
    await store.ensure_indexes(db)
    handle = raw(db)
    await handle.service_desk_jobs.drop_index("finished_ttl")
    await handle.service_desk_gaps.drop_index("created_ttl")


async def seed_article(db, tid, doc_id, *, title, content, helpdesk=True, tags=()):
    """A knowledge_docs row as the Knowledge Base stores it, with the Help desk mark on or off."""
    await db.knowledge_docs.insert_one({"id": doc_id, "tenantId": tid, "title": title, "content": content,
                                        "tags": list(tags), "helpdesk": helpdesk, "source": "manual"})


def ollama_transport(answer: str, cited: List[int], *, tags=("llama3.2:3b",), status=200,
                     fail_tags=False, reply_text=None) -> Tuple[httpx.MockTransport, List[Dict[str, Any]]]:
    """A stand-in Ollama. GET /api/tags lists ``tags`` (or fails with a connect error); POST /api/generate
    answers ``{"answer", "cited"}`` (or ``reply_text`` verbatim). Every request is appended to the returned
    list as {method, path, body}."""
    calls: List[Dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append({"method": request.method, "path": request.url.path, "body": body})
        if request.url.path == "/api/tags":
            if fail_tags:
                raise httpx.ConnectError("no model is running", request=request)
            return httpx.Response(200, json={"models": [{"name": t, "model": t} for t in tags]})
        if request.url.path == "/api/generate":
            text = reply_text if reply_text is not None else json.dumps({"answer": answer, "cited": cited})
            return httpx.Response(status, json={"response": text, **_TIMINGS})
        return httpx.Response(404)

    return httpx.MockTransport(handler), calls


def portal_user(tenant, username, *, auth_source="session", role="user") -> TokenData:
    """A signed-in person (or, with auth_source api_key, an integration key) of ``tenant``."""
    return TokenData(username=username, role=role, tenant_id=tenant, mfa_verified=True, auth_source=auth_source)


def _mock_rbac_db():
    db = MagicMock()
    db.roles = MagicMock()
    db.roles.find_one = AsyncMock(return_value=None)       # no role document: the built-in role permissions apply
    db._db = db
    return db


class DeskApp:
    """The ticket routes and the desk route on one app; the caller is chosen per request."""

    def __init__(self, db, monkeypatch):
        import rbac_service
        import rbac_utils
        import tickets_config_mixin
        import tickets_endpoints
        import tickets_service
        import service_desk_endpoints
        self.db = db
        self.user = None
        for module in (tickets_service, tickets_config_mixin, tickets_endpoints, service_desk_endpoints):
            monkeypatch.setattr(module, "get_database", lambda: db)
        rbac_db = _mock_rbac_db()
        monkeypatch.setattr(rbac_service, "get_database", lambda: rbac_db)
        monkeypatch.setattr(rbac_utils, "get_database", lambda: rbac_db)
        import ticket_notifications
        monkeypatch.setattr(ticket_notifications, "notify_ticket_created", AsyncMock())
        import ticket_webhook_service
        monkeypatch.setattr(ticket_webhook_service, "dispatch_event", AsyncMock())
        self.app = FastAPI()
        self.app.include_router(tickets_endpoints.router)
        self.app.include_router(service_desk_endpoints.router)
        self.app.dependency_overrides[get_current_user] = lambda: self.user

    async def call(self, method, path, *, user, json=None):
        self.user = user
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, json=json)


def desk_app(mongo_db, monkeypatch) -> DeskApp:
    return DeskApp(mongo_db, monkeypatch)
