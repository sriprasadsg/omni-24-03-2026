"""
Integration routes: SSRF fix (CSO finding fbfc84f2) and secret masking.

POST /api/integrations/test and /siem/test used to let any logged-in user
make the backend POST to an arbitrary endpoint and read the response. They
now need manage:settings, the senders refuse internal destinations, and
stored configs come back with secrets masked (and masked values round-trip
without overwriting the stored secret). Hermetic — no Mongo, no network.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import integration_endpoints
import integrations_v2
from auth_types import TokenData
from authentication_service import get_current_user
from database import get_database
from integration_service import SECRET_MASK, IntegrationService, _keep_stored_secrets, redact_config
from rbac_service import rbac_service


@pytest.fixture(autouse=True)
def _restore_tenant_context():
    """verify_token/get_current_user set the ambient tenant context; restore it
    so later tests that assert an empty context are unaffected."""
    from tenant_context import _tenant_id_ctx
    token = _tenant_id_ctx.set(_tenant_id_ctx.get())
    yield
    _tenant_id_ctx.reset(token)


def _user(role):
    return TokenData(username="u@example.com", role=role, tenant_id="tenant-a", mfa_verified=True)


def _client(role, permissions):
    app = FastAPI()
    # Same order as router_registry: integrations_v2 shadows the shared paths.
    app.include_router(integrations_v2.router)
    app.include_router(integration_endpoints.router)
    app.dependency_overrides[get_current_user] = lambda: _user(role)
    app.dependency_overrides[get_database] = lambda: MagicMock()
    perms = patch.object(rbac_service, "get_user_permissions", new=AsyncMock(return_value=permissions))
    return app, perms


SIEM_BODY = {"platform": "splunk", "config": {"endpoint": "http://127.0.0.1:11434/api/tags?", "token": "x"}}


@pytest.mark.parametrize("method,path,body", [
    ("post", "/api/integrations/siem/test", SIEM_BODY),
    ("post", "/api/integrations/test", {"type": "siem", **SIEM_BODY}),
    ("get", "/api/integrations/configs", None),
    ("post", "/api/integrations/config", {"id": "slack", "config": {}}),
    ("put", "/api/integrations/connectors/jira/config", {"base_url": "https://x.example"}),
    ("post", "/api/integrations/action", {"platform": "jira"}),
])
def test_viewer_is_forbidden(method, path, body):
    app, perms = _client("viewer", ["view:dashboard"])
    with perms, TestClient(app) as client:
        resp = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
    assert resp.status_code == 403, resp.text


def test_admin_siem_test_to_internal_host_is_refused_without_outbound_call():
    app, perms = _client("admin", ["manage:settings"])
    with perms, patch("integration_service_siem.guarded_session") as session, TestClient(app) as client:
        resp = client.post("/api/integrations/siem/test", json=SIEM_BODY)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert "not permitted" in body["error"]
    session.assert_not_called()


def test_connector_config_with_internal_url_rejected():
    app, perms = _client("admin", ["manage:settings"])
    with perms, TestClient(app) as client:
        resp = client.put("/api/integrations/connectors/jira/config", json={"base_url": "http://169.254.169.254/"})
    assert resp.status_code == 400
    assert "base_url" in resp.json()["detail"]


async def test_splunk_failure_does_not_echo_remote_body_or_exception():
    svc = IntegrationService(MagicMock())
    with patch("integration_service_siem.avalidate_outbound_url", new=AsyncMock(side_effect=OSError("secret internal detail"))):
        result = await svc._send_to_splunk("e", "info", {}, {"endpoint": "https://hec.example", "token": "t"})
    assert result == {"success": False, "platform": "splunk", "error": "Connection failed"}


def test_redact_config_masks_top_level_and_nested_secrets():
    doc = {"platform": "jira", "token": "t0k", "config": {"apiToken": "abc", "webhookUrl": "https://hooks/x", "projectKey": "SEC"}}
    out = redact_config(doc)
    assert out["token"] == SECRET_MASK
    assert out["config"] == {"apiToken": SECRET_MASK, "webhookUrl": SECRET_MASK, "projectKey": "SEC"}
    assert doc["token"] == "t0k"  # input untouched


def test_masked_secret_round_trip_keeps_stored_value():
    stored = {"token": "real", "config": {"apiToken": "real-nested", "projectKey": "OLD"}}
    incoming = {"token": SECRET_MASK, "config": {"apiToken": SECRET_MASK, "projectKey": "NEW"}}
    merged = _keep_stored_secrets(incoming, stored)
    assert merged["token"] == "real"
    assert merged["config"] == {"apiToken": "real-nested", "projectKey": "NEW"}


def test_mask_is_never_persisted_when_nothing_is_stored():
    merged = _keep_stored_secrets({"token": SECRET_MASK, "password": None}, {})
    assert "token" not in merged
    assert merged["password"] is None
