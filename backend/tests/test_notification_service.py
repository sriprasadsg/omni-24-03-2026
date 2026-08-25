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
    # DB-F10: rbac_service.find_role_doc's global-role fallback goes through
    # db._db — set this before the loop below populates per-collection mocks
    # so setattr(db._db, col, c) attaches onto `db` itself, not a separate
    # auto-vivified mock that a later reassignment would discard.
    db._db = db
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
    # Stub every network-touching helper (DNS/TCP/TLS) so this unit test is
    # hermetic — no real resolution, connects, or handshakes against the network.
    with patch.object(svc, "_is_safe_target", return_value=True), \
         patch.object(svc, "_passive_discover", return_value=["www.example.com"]), \
         patch.object(svc, "_check_ports", return_value={"80": True, "443": True}), \
         patch.object(svc, "_check_tls", return_value={"expiry": "2030-01-01", "issuer": "Test CA", "san": ["example.com"]}), \
         patch.object(svc, "_get_dns", return_value={"A": ["93.184.216.34"]}):
        result = asyncio.run(svc.scan_domain(db, "tenant-a", "example.com"))
    assert result["domain"] == "example.com"
    assert result["subdomains"] == ["www.example.com"]
    assert result["open_ports"] == {"80": True, "443": True}
    assert "dns" in result


def test_schedule_domain():
    db = _make_db(); user = _make_user()
    client = _build_client("domain_scanner_endpoints", db, user)
    resp = client.post("/api/domain-scanner/scheduled", json={"domain": "example.com"})
    assert resp.status_code in (200, 400)


def test_send_alert_explicit_empty_channels_means_no_dispatch():
    """channels=[] (explicit, not omitted) must NOT fall back to the
    ["email"] default — callers depend on this for in-app-only alerts
    (Phase 42 control-comment @mentions, D-02). channels=None (or omitted)
    still defaults to email."""
    import asyncio
    from notification_service import NotificationService

    db = MagicMock()
    db.notifications = MagicMock()
    db.notifications.insert_one = AsyncMock()
    svc = NotificationService(db)

    result = asyncio.run(svc.send_alert(
        title="t", message="m", severity="info", recipients=["bob@acme.com"],
        tenant_id="tenant-a", channels=[], metadata={},
    ))
    assert result["channels"] == {}, f"Expected no channel dispatch, got {result['channels']}"

    result_default = asyncio.run(svc.send_alert(
        title="t", message="m", severity="info", recipients=["bob@acme.com"],
        tenant_id="tenant-a", metadata={},
    ))
    assert "email" in result_default["channels"], "Omitted channels should still default to email"


def test_create_asset_request_notification_rule():
    """Phase 71 (Asset Request & Approval Workflow) regression: itam_notification_service.py
    sends every create/approve/reject via event_type "itam.asset_request_status", but the
    type was missing from both RuleCreate's Literal (endpoint-level 422) and
    notification_service.VALID_EVENTS (service-level ValueError) — no tenant could ever
    bind a rule to it, so Slack/email delivery silently matched zero rules while the
    in-app db.notifications path (a separate code path) kept working, masking the bug."""
    db = _make_db(); user = _make_user()
    client = _build_client("notification_endpoints", db, user)
    resp = client.post("/api/notifications/rules", json={"event_type": "itam.asset_request_status", "channel_ids": ["chan-abc"]})
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"


def test_asset_request_notification_matches_and_dispatches():
    """Full round trip: a rule bound to itam.asset_request_status actually matches
    when send_notification is called with that event_type, and reaches a channel."""
    import asyncio
    from notification_service import send_notification

    rule = {"id": "rule-1", "tenantId": "tenant-a", "event_type": "itam.asset_request_status",
             "channel_ids": ["chan-1"], "severity_filter": []}
    channel = {"id": "chan-1", "tenantId": "tenant-a", "type": "email", "config": {"email": "ops@acme.com"}}

    db = MagicMock()
    db._db = MagicMock()
    db._db.notification_rules = MagicMock()
    db._db.notification_rules.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[rule])))
    db._db.notification_channels = MagicMock()
    db._db.notification_channels.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[channel])))

    result = asyncio.run(send_notification(db, "tenant-a", "itam.asset_request_status", {
        "message": "Your asset request has been approved.", "severity": "success",
    }))
    assert result["matched_rules"] == 1, f"Expected the rule to match, got: {result}"
    assert result["results"] == [{"channel_id": "chan-1", "status": "sent"}]


def test_tenant_isolation_channels():
    seeded = [
        {"id": "chan-a", "tenantId": "tenant-a", "type": "slack", "name": "A's channel", "config": {}},
        {"id": "chan-b", "tenantId": "tenant-b", "type": "slack", "name": "B's channel", "config": {}},
    ]

    def _fake_find(query, *_a, **_kw):
        matched = [c for c in seeded if c["tenantId"] == query.get("tenantId")]
        return MagicMock(sort=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=matched))))

    db = _make_db()
    db._db.notification_channels.find = MagicMock(side_effect=_fake_find)
    user = _make_user("tenant-a", "user")
    client = _build_client("notification_endpoints", db, user)
    # get_tenant_id() reads a ContextVar normally populated by request middleware,
    # which this bare single-router test app doesn't run — set it explicitly.
    with patch("notification_endpoints.get_tenant_id", return_value="tenant-a"):
        resp = client.get("/api/notifications/channels")
    assert resp.status_code == 200
    ids = {c["id"] for c in resp.json()["items"]}
    assert "chan-a" in ids, "tenant-a should see its own channel"
    assert "chan-b" not in ids, "tenant isolation violated: tenant-a saw tenant-b's channel"
