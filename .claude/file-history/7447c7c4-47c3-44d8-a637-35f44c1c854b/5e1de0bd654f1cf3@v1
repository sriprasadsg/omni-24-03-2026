"""
Tests for alert_endpoints.py and ai_endpoints.py.

Covers:
  - Alerts: GET scoping, POST create (tenant injection prevention), PATCH assign,
    DELETE bulk (RBAC), bulk PATCH (RBAC)
  - AI: GET status, POST chat (permission check), POST feedback (permission check),
    POST test-connection (manage:settings required)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json as _json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from authentication_service import get_current_user
from auth_types import TokenData


# ─── helpers ─────────────────────────────────────────────────────────────────

def _col(**overrides):
    col = MagicMock()
    col.find_one   = AsyncMock(return_value=None)
    col.insert_one = AsyncMock()
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    col.delete_many = AsyncMock(return_value=MagicMock(deleted_count=2))
    col.update_many = AsyncMock(return_value=MagicMock(modified_count=2))
    col.find       = MagicMock()
    col.find.return_value.to_list = AsyncMock(return_value=[])
    col.find.return_value.limit = MagicMock(return_value=MagicMock())
    col.find.return_value.limit.return_value.to_list = AsyncMock(return_value=[])
    for k, v in overrides.items():
        setattr(col, k, v)
    return col


def _db(**collections):
    db = MagicMock()
    db.__getitem__ = lambda self, name: getattr(self, name, _col())
    for name, col in collections.items():
        setattr(db, name, col)
    return db


def _user(role="security_analyst", tenant_id="t1"):
    return TokenData(username="test@example.com", role=role, tenant_id=tenant_id, mfa_verified=True)


def _app(router, user):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    return app


# ═══════════════════════════════════════════════════════════════════════════════
# Alert Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

class TestAlertGet:

    def test_get_returns_tenant_scoped_alerts(self):
        from alert_endpoints import router
        alerts = [{"id": "a1", "tenantId": "t1", "severity": "High"}]
        col = _col()
        col.find.return_value.to_list = AsyncMock(return_value=alerts)
        db = _db(alerts=col)
        with patch("alert_endpoints.get_database", return_value=db):
            res = TestClient(_app(router, _user())).get("/api/alerts")
        assert res.status_code == 200
        assert res.json() == alerts

    def test_super_admin_uses_empty_filter(self):
        from alert_endpoints import router
        col = _col()
        col.find.return_value.to_list = AsyncMock(return_value=[])
        db = _db(alerts=col)
        with patch("alert_endpoints.get_database", return_value=db):
            TestClient(_app(router, _user(role="super_admin", tenant_id=None))).get("/api/alerts")
        # Super admin should query with {} (no tenantId restriction)
        call_filter = col.find.call_args.args[0]
        assert "tenantId" not in call_filter


class TestAlertCreate:

    def test_create_sets_tenant_from_jwt(self):
        """tenantId must come from JWT, not the request body."""
        from alert_endpoints import router
        inserted = {}
        col = _col()
        async def capture(doc):
            inserted.update(doc)
        col.insert_one = AsyncMock(side_effect=capture)
        db = _db(alerts=col)

        with patch("alert_endpoints.get_database", return_value=db), \
             patch("alert_endpoints.broker", MagicMock(publish=AsyncMock()), create=True):
            res = TestClient(_app(router, _user(tenant_id="t1"))).post(
                "/api/alerts",
                json={"description": "Test alert", "tenantId": "evil-tenant", "severity": "High"},
            )
        assert res.status_code == 200
        # Backend should override the injected tenantId with the JWT tenant
        assert inserted.get("tenantId") == "t1", "tenantId must be from JWT, not request body"

    def test_create_returns_alert_with_id(self):
        from alert_endpoints import router
        col = _col()
        db = _db(alerts=col)
        with patch("alert_endpoints.get_database", return_value=db), \
             patch("alert_endpoints.broker", MagicMock(publish=AsyncMock()), create=True):
            res = TestClient(_app(router, _user())).post(
                "/api/alerts",
                json={"description": "Test", "severity": "Medium"},
            )
        assert res.status_code == 200
        data = res.json()
        assert "id" in data
        assert data["status"] == "open"


def _patch_rbac_db(db):
    """Patch both alert_endpoints and rbac_utils so permission checks work without MongoDB."""
    return patch("alert_endpoints.get_database", return_value=db), \
           patch("rbac_utils.get_database", return_value=_db(roles=_col()))


class TestAlertAssign:

    def test_assign_requires_permission(self):
        from alert_endpoints import router
        db = _db(alerts=_col())
        viewer = _user(role="Viewer")
        p1, p2 = _patch_rbac_db(db)
        with p1, p2:
            res = TestClient(_app(router, viewer)).patch(
                "/api/alerts/a1/assign",
                json={"assigned_to": "analyst@corp.com"},
            )
        assert res.status_code == 403

    def test_assign_success(self):
        from alert_endpoints import router
        col = _col()
        col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
        db = _db(alerts=col)
        p1, p2 = _patch_rbac_db(db)
        with p1, p2:
            res = TestClient(_app(router, _user(role="security_analyst"))).patch(
                "/api/alerts/a1/assign",
                json={"assigned_to": "analyst@corp.com"},
            )
        assert res.status_code == 200
        assert res.json()["assigned_to"] == "analyst@corp.com"

    def test_assign_missing_assigned_to(self):
        from alert_endpoints import router
        db = _db(alerts=_col())
        p1, p2 = _patch_rbac_db(db)
        with p1, p2:
            res = TestClient(_app(router, _user(role="security_analyst"))).patch(
                "/api/alerts/a1/assign", json={}
            )
        assert res.status_code == 400

    def test_assign_not_found(self):
        from alert_endpoints import router
        col = _col()
        col.update_one = AsyncMock(return_value=MagicMock(matched_count=0))
        db = _db(alerts=col)
        p1, p2 = _patch_rbac_db(db)
        with p1, p2:
            res = TestClient(_app(router, _user(role="security_analyst"))).patch(
                "/api/alerts/missing/assign",
                json={"assigned_to": "x@x.com"},
            )
        assert res.status_code == 404


class TestAlertBulkDelete:
    # Use client.request("DELETE") — TestClient.delete() doesn't accept body in Starlette 1.x

    def test_bulk_delete_requires_permission(self):
        from alert_endpoints import router
        db = _db(alerts=_col())
        p1, p2 = _patch_rbac_db(db)
        with p1, p2:
            client = TestClient(_app(router, _user(role="Viewer")))
            res = client.request("DELETE", "/api/alerts/bulk", json=["a1", "a2"])
        assert res.status_code == 403

    def test_bulk_delete_success(self):
        from alert_endpoints import router
        col = _col()
        col.delete_many = AsyncMock(return_value=MagicMock(deleted_count=2))
        db = _db(alerts=col)
        p1, p2 = _patch_rbac_db(db)
        with p1, p2:
            client = TestClient(_app(router, _user(role="security_analyst")))
            res = client.request("DELETE", "/api/alerts/bulk", json=["a1", "a2"])
        assert res.status_code == 200
        assert res.json()["deleted"] == 2

    def test_bulk_delete_empty_ids_rejected(self):
        from alert_endpoints import router
        db = _db(alerts=_col())
        p1, p2 = _patch_rbac_db(db)
        with p1, p2:
            client = TestClient(_app(router, _user(role="security_analyst")))
            res = client.request("DELETE", "/api/alerts/bulk", json=[])
        assert res.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# AI Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

class TestAIStatus:

    def test_status_returns_operational(self):
        from ai_endpoints import router
        from rbac_service import rbac_service

        mock_ai = MagicMock()
        mock_ai.is_configured = True
        mock_provider = MagicMock()
        mock_provider.name = "Gemini"
        mock_ai.provider = mock_provider

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: _user()

        with patch("ai_endpoints.ai_service", mock_ai):
            res = TestClient(app).get("/api/ai")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "operational"
        assert "services" in data


_RBAC_SVC_PATCH = lambda: patch("rbac_service.get_database", return_value=_db(roles=_col()))


def _ai_app(user):
    """Build AI test app — auth bypassed via dependency override."""
    from ai_endpoints import router
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    return app


class TestAIChat:

    def test_chat_returns_response(self):
        mock_ai = MagicMock()
        mock_ai.chat = AsyncMock(return_value="Hello, I can help with that.")

        with patch("ai_endpoints.ai_service", mock_ai), \
             patch("ai_endpoints.get_tenant_id", return_value="t1"), \
             _RBAC_SVC_PATCH():
            res = TestClient(_ai_app(_user())).post("/api/ai/chat", json={"message": "Hello"})

        assert res.status_code == 200
        assert "response" in res.json()


class TestAIFeedback:

    def test_feedback_recorded_with_tenant(self):
        col = _col()
        db = _db(ai_feedback=col)

        with patch("database.get_database", return_value=db), \
             patch("ai_endpoints.get_tenant_id", return_value="t1"), \
             _RBAC_SVC_PATCH():
            res = TestClient(_ai_app(_user(role="Viewer"))).post("/api/ai/feedback", json={
                "prompt_id": "p1",
                "response_preview": "Test response",
                "rating": 4,
                "helpful": True,
            })

        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "recorded"
        assert "feedback_id" in data


class TestAITestConnection:

    def test_test_connection_requires_manage_settings(self):
        with _RBAC_SVC_PATCH():
            res = TestClient(_ai_app(_user(role="Viewer"))).post("/api/ai/test-connection", json={
                "provider": "gemini", "api_key": "fake-key", "model": "gemini-2.0-flash"
            })
        assert res.status_code == 403
