"""Shared helpers for the Knowledge Base desk tests (Phase 85, plan 85-15): the Knowledge Base router on one app
with the caller's identity and permissions chosen per request, and the shared seeding helpers."""
import os
import sys

import httpx
from fastapi import FastAPI

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import knowledge_endpoints
import knowledge_helpdesk_endpoints
from authentication_service import get_current_user
from auth_types import TokenData
from rbac_service import rbac_service
from service_desk import HELPDESK_CONTENT_MAX

PERMISSIONS = {
    "manager": ["manage:ai_risks", "view:dashboard", "manage:tickets"],   # edits articles and is ticket staff
    "kb_viewer": ["manage:ai_risks", "view:dashboard"],     # edits articles, sees the dashboard, is not ticket staff
    "editor": ["manage:ai_risks"],                          # Knowledge Base only
    "agent": ["view:dashboard"],                            # tickets only
    "reader": [],
}
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
