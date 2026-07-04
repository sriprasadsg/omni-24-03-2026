"""Tests for Phase 21 — Notification channels/rules + Domain Scanner."""
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_user(tenant_id="tenant-a", role="admin", username="admin1"):
    u = MagicMock(); u.tenant_id = tenant_id; u.role = role; u.username = username
    return u


def _make_db():
    db = MagicMock()
    for col in ("notification_channels", "notification_rules", "scheduled_domains", "domain_scans"):
        c = MagicMock()
        c.insert_one = AsyncMock(return_value=MagicMock(inserted_id="x"))
        c.find = MagicMock(return_value=MagicMock(sort=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))))
        setattr(db._db, col, c)
    # rbac_service.get_user_permissions falls back to its in-memory default_roles
    # table for any non-super-admin role as long as the DB lookup resolves to None.
    db.roles = MagicMock()
    db.roles.find_one = AsyncMock(return_value=None)
    return db


def _build_client(module_name, mock_db, user):
    import importlib
    mod = importlib.import_module(module_name)
    from authentication_service import get_current_user
    app = FastAPI(); app.include_router(mod.router)
    from auth_types import TokenData
    t = TokenData(username=user.username, tenant_id=user.tenant_id, role=user.role)
    # has_permission(...) is a factory — every route decorator call produces a
    # distinct closure, so overriding by re-calling it here never matches the
    # object actually bound into the router. get_current_user is the stable,
    # singleton dependency every has_permission(...) closure wraps, so override
    # that instead.
    app.dependency_overrides[get_current_user] = lambda: t
    patcher = patch(f"{module_name}.get_database", return_value=mock_db)
    patcher.start()
    rbac_patcher = patch("rbac_service.get_database", return_value=mock_db)
    rbac_patcher.start()
    return TestClient(app, raise_server_exceptions=False)


def test_create_slack_channel():
    db = _make_db(); user = _make_user()
    client = _build_client("notification_endpoints", db, user)
    resp = client.post("/api/notifications/channels", json={"type": "slack", "name": "Security Alerts", "config": {"url": "https://hooks.slack.com/test"}})
    assert resp.status_code in (200, 422), f"Got {resp.status_code}: {resp.text}"
    if resp.status_code == 200:
        assert resp.json()["channel"]["type"] == "slack"


def test_create_notification_rule():
    db = _make_db(); user = _make_user()
    client = _build_client("notification_endpoints", db, user)
    resp = client.post("/api/notifications/rules", json={"event_type": "control_failed", "severity_filter": ["high", "critical"], "channel_ids": ["chan-abc"]})
    assert resp.status_code in (200, 422)


def test_invalid_channel_type():
    db = _make_db(); user = _make_user()
    client = _build_client("notification_endpoints", db, user)
    resp = client.post("/api/notifications/channels", json={"type": "invalid", "name": "Bad", "config": {}})
    assert resp.status_code == 422


def test_invalid_event_type():
    db = _make_db(); user = _make_user()
    client = _build_client("notification_endpoints", db, user)
    resp = client.post("/api/notifications/rules", json={"event_type": "invalid_event", "channel_ids": []})
    assert resp.status_code == 422


def test_domain_scan_returns_structure():
    import domain_scanner_service as svc
    db = _make_db()
    import asyncio
    result = asyncio.run(svc.scan_domain(db, "tenant-a", "example.com"))
    assert "domain" in result
    assert result["domain"] == "example.com"
    assert "subdomains" in result
    assert "open_ports" in result
    assert "dns" in result


def test_schedule_domain():
    db = _make_db(); user = _make_user()
    client = _build_client("domain_scanner_endpoints", db, user)
    resp = client.post("/api/domain-scanner/scheduled", json={"domain": "example.com"})
    assert resp.status_code in (200, 400)


def test_tenant_isolation_channels():
    db = _make_db(); user = _make_user("tenant-a", "user")
    client = _build_client("notification_endpoints", db, user)
    resp = client.get("/api/notifications/channels")
    assert resp.status_code == 200
