"""Phase 14 SaaS Evidence Integration tests — SAAS-01, SAAS-02, SAAS-03.

Tests:
  - test_encrypt_decrypt_round_trip: Fernet encrypt/decrypt preserves plaintext
  - test_store_connection_with_encrypted_token: Token stored encrypted, not plaintext
  - test_pull_github_evidence_maps_to_control: GitHub evidence maps to Secure Development control
  - test_pull_jira_evidence_maps_to_control: Jira evidence maps to Change Management control
  - test_pull_okta_evidence_maps_to_control: Okta evidence maps to MFA/Identity control
  - test_pull_google_workspace_evidence_maps_to_control: GWS evidence maps to Account Security
  - test_pull_slack_evidence_maps_to_control: Slack evidence maps to Audit Logging control
  - test_pull_evidence_writes_to_control_evidence: pull_all_evidence writes to control_evidence collection
  - test_tenant_isolation_blocks_cross_tenant_pull: Cross-tenant pull returns 403
  - test_delete_connection_removes_record: DELETE removes connection record from DB

asyncio.run() used for async cases (pytest-asyncio not installed — decision 02-01).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Test 1: Encrypt/decrypt round-trip
# ---------------------------------------------------------------------------

def test_encrypt_decrypt_round_trip():
    """_encrypt then _decrypt returns original plaintext."""
    from saas_integration_service import _encrypt, _decrypt
    plaintext = "ghp_supersecret_token_12345"
    ciphertext = _encrypt(plaintext)
    assert ciphertext != plaintext, "Encrypted token must differ from plaintext"
    recovered = _decrypt(ciphertext)
    assert recovered == plaintext, "Decrypted value must match original plaintext"


# ---------------------------------------------------------------------------
# Test 2: Store connection with encrypted token
# ---------------------------------------------------------------------------

def test_store_connection_with_encrypted_token():
    """store_connection saves encrypted tokens — plaintext never stored in DB."""
    from saas_integration_service import SaaSIntegrationService, _decrypt

    db = MagicMock()
    db.saas_connections = MagicMock()
    db.saas_connections.insert_one = AsyncMock(return_value=None)

    svc = SaaSIntegrationService()

    async def run():
        connection_id = await svc.store_connection(
            db=db,
            provider="github",
            tenant_id="tenant-a",
            access_token="ghp_plaintext",
            refresh_token="refresh_plain",
        )
        assert connection_id is not None

        # Verify the doc written to DB has encrypted tokens (stored as *_enc fields)
        call_args = db.saas_connections.insert_one.call_args
        doc = call_args[0][0]
        assert doc["access_token_enc"] != "ghp_plaintext", "access_token_enc must be encrypted"
        assert doc["refresh_token_enc"] != "refresh_plain", "refresh_token_enc must be encrypted"
        # Verify decryption works
        assert _decrypt(doc["access_token_enc"]) == "ghp_plaintext"
        assert _decrypt(doc["refresh_token_enc"]) == "refresh_plain"
        assert doc["tenant_id"] == "tenant-a"
        assert doc["provider"] == "github"

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 3: GitHub evidence maps to Secure Development control
# ---------------------------------------------------------------------------

def test_pull_github_evidence_maps_to_control():
    """pull_github_evidence returns evidence records mapped to Secure Development control."""
    from saas_integration_service import SaaSIntegrationService

    svc = SaaSIntegrationService()

    fake_prs = {"data": [{"number": 1, "title": "Fix vuln", "merged_at": "2026-06-01"}]}
    fake_branch = {"protection": {"enabled": True}}
    fake_alerts = []

    async def run():
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            def make_resp(data):
                resp = MagicMock()
                resp.status_code = 200
                resp.json = MagicMock(return_value=data)
                resp.raise_for_status = MagicMock()
                return resp

            mock_client.get = AsyncMock(side_effect=[
                make_resp(fake_prs),
                make_resp(fake_branch),
                make_resp(fake_alerts),
            ])
            mock_client_cls.return_value = mock_client

            evidence_list = await svc.pull_github_evidence(
                token="ghp_fake", tenant_id="tenant-a", db=None
            )

        assert len(evidence_list) > 0
        control_ids = [e["control_id"] for e in evidence_list]
        # Should map to Secure Development or Access to Source Code
        assert any(
            cid in ["Secure Development & Coding Simulation", "Access to Source Code Simulation",
                    "Security Patch Status"]
            for cid in control_ids
        ), f"Expected compliance control in evidence, got: {control_ids}"

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 4: Jira evidence maps to Change Management control
# ---------------------------------------------------------------------------

def test_pull_jira_evidence_maps_to_control():
    """pull_jira_evidence returns evidence records mapped to Change Management control."""
    from saas_integration_service import SaaSIntegrationService

    svc = SaaSIntegrationService()
    fake_issues = {"issues": [{"key": "COMP-1", "fields": {"summary": "Deploy change", "status": {"name": "Done"}}}]}

    async def run():
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            resp = MagicMock()
            resp.status_code = 200
            resp.json = MagicMock(return_value=fake_issues)
            resp.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client_cls.return_value = mock_client

            evidence_list = await svc.pull_jira_evidence(
                token="jira_fake", tenant_id="tenant-a", db=None,
                domain="https://my-org.atlassian.net"
            )

        assert len(evidence_list) > 0
        control_ids = [e["control_id"] for e in evidence_list]
        assert any("Change Management" in cid for cid in control_ids), (
            f"Expected Change Management control in evidence, got: {control_ids}"
        )

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 5: Okta evidence maps to MFA / Identity control
# ---------------------------------------------------------------------------

def test_pull_okta_evidence_maps_to_control():
    """pull_okta_evidence returns evidence mapped to MFA for All Users / Identity control."""
    from saas_integration_service import SaaSIntegrationService

    svc = SaaSIntegrationService()
    fake_users = [
        {"id": "u1", "profile": {"login": "alice@co.com"}, "status": "ACTIVE"},
        {"id": "u2", "profile": {"login": "bob@co.com"}, "status": "ACTIVE"},
    ]
    fake_factors = [{"factorType": "token:software:totp", "status": "ACTIVE"}]

    async def run():
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            def make_resp(data):
                resp = MagicMock()
                resp.status_code = 200
                resp.json = MagicMock(return_value=data)
                resp.raise_for_status = MagicMock()
                return resp

            mock_client.get = AsyncMock(side_effect=[
                make_resp(fake_users),
                make_resp(fake_factors),
                make_resp(fake_factors),
            ])
            mock_client_cls.return_value = mock_client

            evidence_list = await svc.pull_okta_evidence(
                token="okta_fake", tenant_id="tenant-a", db=None,
                domain="https://myorg.okta.com"
            )

        assert len(evidence_list) > 0
        control_ids = [e["control_id"] for e in evidence_list]
        assert any(
            "MFA" in cid or "Identity" in cid or "Authentication" in cid
            for cid in control_ids
        ), f"Expected MFA/Identity control, got: {control_ids}"

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 6: Google Workspace evidence maps to Account Security control
# ---------------------------------------------------------------------------

def test_pull_google_workspace_evidence_maps_to_control():
    """pull_google_workspace_evidence returns evidence mapped to Account Security control."""
    from saas_integration_service import SaaSIntegrationService

    svc = SaaSIntegrationService()
    fake_users = {"users": [
        {"primaryEmail": "alice@co.com", "isEnrolledIn2Sv": True, "isAdmin": False},
        {"primaryEmail": "bob@co.com", "isEnrolledIn2Sv": True, "isAdmin": False},
    ]}

    async def run():
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            resp = MagicMock()
            resp.status_code = 200
            resp.json = MagicMock(return_value=fake_users)
            resp.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client_cls.return_value = mock_client

            evidence_list = await svc.pull_google_workspace_evidence(
                token="gws_fake", tenant_id="tenant-a", db=None
            )

        assert len(evidence_list) > 0
        control_ids = [e["control_id"] for e in evidence_list]
        assert any(
            "Account Security" in cid or "Leakage" in cid or "Data Leakage" in cid
            for cid in control_ids
        ), f"Expected Account Security/DLP control, got: {control_ids}"

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 7: Slack evidence maps to Audit Logging control
# ---------------------------------------------------------------------------

def test_pull_slack_evidence_maps_to_control():
    """pull_slack_evidence returns evidence mapped to Audit Logging Extension control."""
    from saas_integration_service import SaaSIntegrationService

    svc = SaaSIntegrationService()
    fake_channels = {"ok": True, "channels": [{"id": "C1", "name": "general", "retention_type": "retain_all"}]}

    async def run():
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            resp = MagicMock()
            resp.status_code = 200
            resp.json = MagicMock(return_value=fake_channels)
            resp.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client_cls.return_value = mock_client

            evidence_list = await svc.pull_slack_evidence(
                token="xoxb_fake", tenant_id="tenant-a", db=None
            )

        assert len(evidence_list) > 0
        control_ids = [e["control_id"] for e in evidence_list]
        assert any("Audit Logging" in cid for cid in control_ids), (
            f"Expected Audit Logging control, got: {control_ids}"
        )

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 8: pull_all_evidence writes to control_evidence collection
# ---------------------------------------------------------------------------

def test_pull_evidence_writes_to_control_evidence():
    """pull_all_evidence persists evidence records to control_evidence collection."""
    from saas_integration_service import SaaSIntegrationService

    svc = SaaSIntegrationService()

    db = MagicMock()
    db.control_evidence = MagicMock()
    db.control_evidence.insert_many = AsyncMock(return_value=None)
    db.saas_connections = MagicMock()
    db.saas_connections.update_one = AsyncMock(return_value=None)

    connection = {
        "id": "conn-1",
        "provider": "github",
        "tenant_id": "tenant-a",
        "access_token_enc": None,
        "refresh_token_enc": None,
        "_access_token_plain": "ghp_fake",
    }

    fake_evidence = [
        {"control_id": "Secure Development & Coding Simulation", "content": "evidence data",
         "source": "saas-github", "tenant_id": "tenant-a", "collected_at": "2026-06-23"}
    ]

    async def run():
        with patch.object(svc, "pull_github_evidence", AsyncMock(return_value=fake_evidence)):
            await svc.pull_all_evidence(connection=connection, db=db)

        db.control_evidence.insert_many.assert_called_once()
        call_args = db.control_evidence.insert_many.call_args[0][0]
        assert len(call_args) > 0
        assert call_args[0]["source"] == "saas-github"
        assert call_args[0]["tenant_id"] == "tenant-a"

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 9: Tenant isolation blocks cross-tenant pull via endpoint
# ---------------------------------------------------------------------------

def test_tenant_isolation_blocks_cross_tenant_pull():
    """POST /api/saas/connections/{id}/pull-evidence returns 403 for cross-tenant access."""
    from authentication_service import get_current_user
    import saas_integration_endpoints as ep_mod

    # Connection belongs to tenant-b; user is tenant-a
    connection_doc = {
        "id": "conn-other",
        "provider": "github",
        "tenant_id": "tenant-b",
        "access_token_enc": "enc_token",
        "last_synced": None,
        "evidence_count": 0,
        "status": "active",
    }

    db = MagicMock()
    db.saas_connections = MagicMock()
    db.saas_connections.find_one = AsyncMock(return_value=connection_doc)

    user = MagicMock()
    user.role = "admin"
    user.tenant_id = "tenant-a"

    app = FastAPI()
    app.include_router(ep_mod.router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[ep_mod.get_db] = lambda: db

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/api/saas/connections/conn-other/pull-evidence")
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"


# ---------------------------------------------------------------------------
# Test 10: DELETE connection removes record from DB
# ---------------------------------------------------------------------------

def test_delete_connection_removes_record():
    """DELETE /api/saas/connections/{id} removes connection from DB."""
    from authentication_service import get_current_user
    import saas_integration_endpoints as ep_mod

    connection_doc = {
        "id": "conn-1",
        "provider": "github",
        "tenant_id": "tenant-a",
        "access_token_enc": "enc_token",
        "last_synced": None,
        "evidence_count": 0,
        "status": "active",
    }

    db = MagicMock()
    db.saas_connections = MagicMock()
    db.saas_connections.find_one = AsyncMock(return_value=connection_doc)
    db.saas_connections.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))

    user = MagicMock()
    user.role = "admin"
    user.tenant_id = "tenant-a"

    app = FastAPI()
    app.include_router(ep_mod.router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[ep_mod.get_db] = lambda: db

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.delete("/api/saas/connections/conn-1")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    db.saas_connections.delete_one.assert_called_once()
