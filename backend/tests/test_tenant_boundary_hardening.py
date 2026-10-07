"""
Tenant-boundary fixes from CSO run 1791310678799-7dcecc4e5cd0b8be.

- "admin" is a tenant role (tenant admins can assign it): it must never get the
  cross-tenant super-admin treatment (reports, insights, export, playbooks,
  support/agent chat, compliance evidence, branding).
- Support chat events reach only the conversation tenant's admins.
- Shared "platform" playbooks can be deleted/toggled by super-admins only.
- /api/system/* needs manage:settings and elevates super-admins only.
- Stream publish takes the tenant from the token; other topics are super-only;
  the live feed needs a token.
- Shell/desktop remote sessions need view:remote_access (see test_remote_access).
- Inbound Jira/Zoho webhooks fail closed and run as the signing tenant.
- Training progress/my-training are bound to the caller.
Hermetic — no Mongo.
"""
import hashlib
import hmac
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from auth_types import TokenData
from authentication_service import get_current_user, get_current_user_or_agent
from tenant_context import get_tenant_id, set_tenant_id


@pytest.fixture(autouse=True)
def _restore_tenant_context():
    from tenant_context import _tenant_id_ctx
    token = _tenant_id_ctx.set(_tenant_id_ctx.get())
    yield
    _tenant_id_ctx.reset(token)


def _user(role, tenant="tenant-a", username="u@a.test"):
    return TokenData(username=username, role=role, tenant_id=tenant, mfa_verified=True)


def _app(router, dep=get_current_user, user=None):
    app = FastAPI()
    app.include_router(router)
    if user is not None:
        app.dependency_overrides[dep] = lambda: user
    return app


# ── "admin" is not a super role ──────────────────────────────────────────────

def test_admin_role_does_not_elevate_reports():
    import reporting_endpoints as rep
    set_tenant_id("tenant-a")
    rep._elevate_if_admin(_user("admin"))
    assert get_tenant_id() == "tenant-a"
    assert rep._resolve_tenant_id(_user("admin"), "tenant-b") == "tenant-a"
    rep._elevate_if_admin(_user("Super Admin", tenant="platform-admin"))
    assert get_tenant_id() == "platform-admin"


@pytest.mark.parametrize("module,attr", [
    ("insights_endpoints", "_SUPER_ROLES"),
    ("export_report_endpoint", "_SUPER_ROLES"),
    ("websocket_manager", "_SUPER_ROLES"),
    ("agent_chat_endpoints", "_SUPER_ROLES"),
    ("support_endpoints", "_SUPER_ROLES"),
    ("compliance_artifacts_endpoints", "_SUPER_ROLES"),
    ("compliance_evidence_lifecycle_endpoints", "_SUPER_ROLES"),
])
def test_admin_not_in_cross_tenant_role_sets(module, attr):
    roles = getattr(__import__(module), attr)
    assert "admin" not in roles
    assert "Super Admin" in roles


def test_admin_stays_an_in_tenant_admin_for_chat_and_support():
    import agent_chat_endpoints
    import support_endpoints
    for mod in (agent_chat_endpoints, support_endpoints):
        assert mod._is_admin("admin") and mod._is_admin("Tenant Admin")
        assert not mod._is_super("admin")


async def test_admin_cannot_read_other_tenant_branding():
    import tenant_endpoints
    with pytest.raises(HTTPException) as exc:
        await tenant_endpoints.get_tenant_branding("tenant-b", current_user=_user("admin"))
    assert exc.value.status_code == 403


# ── Support chat fan-out ─────────────────────────────────────────────────────

async def test_user_to_admin_support_event_stays_in_tenant():
    import websocket_manager as wm
    sessions = {"admin-a": "sid-a", "admin-b": "sid-b", "root": "sid-root", "tadmin-a": "sid-ta"}
    roles = {"admin-a": "admin", "admin-b": "Tenant Admin", "root": "Super Admin", "tadmin-a": "Tenant Admin"}
    tenants = {"admin-a": "tenant-a", "admin-b": "tenant-b", "root": "platform-admin", "tadmin-a": "tenant-a"}
    emit = AsyncMock()
    with patch.dict(wm.user_sessions, sessions, clear=True), \
         patch.dict(wm.user_roles, roles, clear=True), \
         patch.dict(wm.user_tenants, tenants, clear=True), \
         patch.object(wm.sio, "emit", emit):
        await wm.broadcast_support_event("tenant-a", "user_to_admin", "new_message", {"initiator_id": "nobody"})
        rooms = {c.kwargs["room"] for c in emit.call_args_list}
        assert rooms == {"sid-a", "sid-ta", "sid-root"}

        emit.reset_mock()
        await wm.broadcast_support_event("tenant-a", "admin_to_superadmin", "new_message", {"initiator_id": "nobody"})
        assert {c.kwargs["room"] for c in emit.call_args_list} == {"sid-root"}


# ── Playbooks (shared collection) ────────────────────────────────────────────

PLATFORM_PB = {"id": "pb-1", "tenant_id": "platform", "name": "shared"}
OTHER_PB = {"id": "pb-2", "tenant_id": "tenant-b", "name": "theirs"}


@pytest.mark.parametrize("role", ["Tenant Admin", "admin", "viewer"])
def test_tenant_users_cannot_delete_or_toggle_platform_playbooks(role):
    import playbook_endpoints as pe
    svc = MagicMock(get_playbook=AsyncMock(return_value=PLATFORM_PB),
                    delete_playbook=AsyncMock(return_value=True),
                    toggle_playbook=AsyncMock(return_value={"enabled": False}))
    with patch.object(pe, "playbook_service", svc):
        client = TestClient(_app(pe.router, user=_user(role)))
        assert client.delete("/api/playbooks/pb-1").status_code == 403
        assert client.patch("/api/playbooks/pb-1/toggle").status_code == 403
    svc.delete_playbook.assert_not_awaited()
    svc.toggle_playbook.assert_not_awaited()


def test_super_admin_can_delete_platform_playbook():
    import playbook_endpoints as pe
    svc = MagicMock(get_playbook=AsyncMock(return_value=PLATFORM_PB), delete_playbook=AsyncMock(return_value=True))
    with patch.object(pe, "playbook_service", svc):
        client = TestClient(_app(pe.router, user=_user("Super Admin", tenant="platform-admin")))
        assert client.delete("/api/playbooks/pb-1").status_code == 200


def test_admin_role_sees_only_own_and_platform_playbooks():
    import playbook_endpoints as pe
    mine = {"id": "pb-3", "tenant_id": "tenant-a"}
    svc = MagicMock(get_playbooks=AsyncMock(return_value=[PLATFORM_PB, OTHER_PB, mine]),
                    get_playbook=AsyncMock(return_value=OTHER_PB))
    with patch.object(pe, "playbook_service", svc):
        client = TestClient(_app(pe.router, user=_user("admin")))
        ids = {p["id"] for p in client.get("/api/playbooks").json()}
        assert ids == {"pb-1", "pb-3"}
        assert client.get("/api/playbooks/pb-2").status_code == 404


# ── System health ────────────────────────────────────────────────────────────

def test_system_routes_require_manage_settings():
    import system_health_endpoints as she
    client = TestClient(_app(she.router, user=_user("viewer")))
    with patch("rbac_utils.verify_permission", AsyncMock(return_value=False)):
        for path in ("/api/system/health", "/api/system/fleet", "/api/system/queues",
                     "/api/system/services", "/api/system/resources"):
            assert client.get(path).status_code == 403, path


def test_system_health_elevates_super_admin_only():
    import system_health_endpoints as she
    set_tenant_id("tenant-a")
    assert she._elevate_if_super(_user("Tenant Admin")) is False
    assert she._elevate_if_super(_user("admin")) is False
    assert get_tenant_id() == "tenant-a"
    assert she._elevate_if_super(_user("Super Admin", tenant="platform-admin")) is True
    assert get_tenant_id() == "platform-admin"


# ── Stream publish / live feed ───────────────────────────────────────────────

def _stream_client(user):
    import stream_processing_endpoints as spe
    return spe, TestClient(_app(spe.router, dep=get_current_user_or_agent, user=user))


def test_raw_logs_ingest_uses_token_tenant_not_body():
    spe, client = _stream_client(_user("Tenant Admin"))
    siem = MagicMock(ingest_logs=AsyncMock())
    with patch.object(spe.broker, "publish", AsyncMock()), \
         patch.object(spe, "get_database", MagicMock()), \
         patch.object(spe, "get_siem_engine", MagicMock(return_value=siem)), \
         patch.object(spe, "verify_permission", AsyncMock(return_value=True)):
        r = client.post("/api/stream/publish/raw_logs",
                        json={"tenant_id": "tenant-b", "agent_id": "x", "logs": [{"msg": "hi"}]})
    assert r.status_code == 200
    assert siem.ingest_logs.await_args.args[1] == "tenant-a"


def test_agent_raw_logs_are_attributed_to_the_calling_agent():
    spe, client = _stream_client(_user("agent", username="agent-7"))
    siem = MagicMock(ingest_logs=AsyncMock())
    with patch.object(spe.broker, "publish", AsyncMock()), \
         patch.object(spe, "get_database", MagicMock()), \
         patch.object(spe, "get_siem_engine", MagicMock(return_value=siem)):
        client.post("/api/stream/publish/raw_logs", json={"agent_id": "spoofed", "logs": [{"m": 1}]})
    assert siem.ingest_logs.await_args.args[1:] == ("tenant-a", "agent-7")


def test_non_super_cannot_publish_broadcast_topics():
    spe, client = _stream_client(_user("Tenant Admin"))
    publish = AsyncMock()
    with patch.object(spe.broker, "publish", publish):
        assert client.post("/api/stream/publish/security_events", json={"x": 1}).status_code == 403
    publish.assert_not_awaited()


def test_live_feed_rejects_missing_token():
    import stream_processing_endpoints as spe
    client = TestClient(_app(spe.router))
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/stream/live") as ws:
            ws.receive_json()
    assert exc.value.code == 4401


# ── Inbound ticket webhooks ──────────────────────────────────────────────────

class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._docs:
            raise StopAsyncIteration
        return self._docs.pop(0)


def _webhook_post(configs, headers=None, body=None):
    import webhook_endpoints as we
    body = body or {"issue": {"key": "J-1", "fields": {"summary": "s"}}}
    raw = json.dumps(body).encode()
    fake_mongo = MagicMock()
    fake_mongo.db.integration_configs.find = MagicMock(return_value=_Cursor(configs))
    seen = {}

    async def _parse(payload, platform):
        seen["tenant"] = get_tenant_id()
        return {"success": False}

    with patch.object(we, "mongodb", fake_mongo), \
         patch.object(we.intent_parser_service, "parse_and_dispatch", side_effect=_parse), \
         patch.object(we, "get_database", MagicMock()), \
         patch.object(we, "get_integration_service", MagicMock()):
        client = TestClient(_app(we.router))
        r = client.post("/api/webhooks/jira/inbound", content=raw,
                        headers={"Content-Type": "application/json", **(headers or {})})
    return r, seen, raw


def _sig(secret, raw):
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def test_inbound_webhook_without_configured_secret_is_rejected():
    r, seen, _ = _webhook_post([], headers={"X-Hub-Signature-256": "sha256=00"})
    assert r.status_code == 401 and not seen


def test_inbound_webhook_without_signature_is_rejected():
    r, seen, _ = _webhook_post([{"tenantId": "tenant-a", "webhook_secret": "s3cret"}])
    assert r.status_code == 401 and not seen


def test_inbound_webhook_runs_as_signing_tenant():
    body = {"issue": {"key": "J-2", "fields": {"summary": "s"}}}
    raw = json.dumps(body).encode()
    configs = [{"tenantId": "tenant-a", "webhook_secret": "aaa"}, {"tenantId": "tenant-b", "webhook_secret": "bbb"}]
    r, seen, _ = _webhook_post(configs, headers={"X-Hub-Signature-256": _sig("bbb", raw)}, body=body)
    assert r.status_code == 200
    assert seen["tenant"] == "tenant-b"


def test_inbound_webhook_secret_is_stored_sealed(monkeypatch):
    from cryptography.fernet import Fernet
    from integration_service import seal_config
    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    body = {"issue": {"key": "J-3", "fields": {"summary": "s"}}}
    raw = json.dumps(body).encode()
    stored = seal_config({"tenantId": "tenant-a", "platform": "jira", "webhook_secret": "aaa"})
    assert stored["webhook_secret"].startswith("enc:")
    r, seen, _ = _webhook_post([stored], headers={"X-Hub-Signature-256": _sig("aaa", raw)}, body=body)
    assert r.status_code == 200
    assert seen["tenant"] == "tenant-a"


# ── Training ─────────────────────────────────────────────────────────────────

def test_training_is_bound_to_the_caller():
    import training_endpoints as te
    from training_service import TrainingService
    svc = TrainingService()
    mine = svc.assign_training("alice@a.test", "mod-1")
    theirs = svc.assign_training("bob@a.test", "mod-1")
    with patch.object(te, "training_service", svc):
        client = TestClient(_app(te.router, user=_user("user", username="alice@a.test")))
        ids = {a["id"] for a in client.get("/api/training/my-training").json()}
        assert mine.id in ids and theirs.id not in ids
        assert client.put(f"/api/training/progress/{theirs.id}", json={"status": "Completed"}).status_code == 404
        assert client.put(f"/api/training/progress/{mine.id}", json={"status": "Completed"}).status_code == 200
