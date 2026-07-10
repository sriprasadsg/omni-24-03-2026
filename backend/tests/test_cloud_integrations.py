"""
Tests for cloud_integrations_endpoints.py and ingest modules (oci, alibaba, cloudflare).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from authentication_service import get_current_user
from auth_types import TokenData

# ─── helpers ─────────────────────────────────────────────────────────────────

def _col(**overrides):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.insert_one = AsyncMock()
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    col.delete_one = AsyncMock()
    col.find = MagicMock()
    col.find.return_value.to_list = AsyncMock(return_value=[])
    col.insert_many = AsyncMock()
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

# ═══════════════════════════════════════════════════════════════════════════════
# Ingest Module Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestIngestModules:

    @pytest.mark.asyncio
    async def test_oci_poll_success(self):
        from oci_ingest import poll_oci_cloud_guard_problems
        db = _db(security_events=_col())
        with patch("oci_ingest.get_database", return_value=db), \
             patch("oci_ingest._OCI_SDK_AVAILABLE", True):
            count = await poll_oci_cloud_guard_problems(
                {"oci_tenancy_ocid": "t", "oci_user_ocid": "u", "oci_private_key": "k", "oci_fingerprint": "f", "oci_region": "r"},
                "t1"
            )
        assert count == 2
        assert db.security_events.insert_many.called

    @pytest.mark.asyncio
    async def test_oci_poll_missing_fields(self):
        from oci_ingest import poll_oci_cloud_guard_problems
        count = await poll_oci_cloud_guard_problems({}, "t1")
        assert count == 0

    @pytest.mark.asyncio
    async def test_alibaba_poll_success(self):
        from alibaba_ingest import poll_alibaba_sas_alerts
        db = _db(security_events=_col())
        with patch("alibaba_ingest.get_database", return_value=db), \
             patch("alibaba_ingest._ALIBABA_SDK_AVAILABLE", True):
            count = await poll_alibaba_sas_alerts(
                {"access_key_id": "k", "access_key_secret": "s", "region_id": "r"},
                "t1"
            )
        assert count == 3
        assert db.security_events.insert_many.called

    @pytest.mark.asyncio
    async def test_cloudflare_poll_success(self):
        from cloudflare_ingest import poll_cloudflare_zero_trust_events
        db = _db(security_events=_col())
        with patch("cloudflare_ingest.get_database", return_value=db), \
             patch("cloudflare_ingest._CLOUDFLARE_SDK_AVAILABLE", True):
            count = await poll_cloudflare_zero_trust_events(
                {"cf_account_id": "a", "cf_api_token": "t"},
                "t1"
            )
        assert count == 1
        assert db.security_events.insert_many.called

def _app(router, user):
    app = FastAPI()
    app.include_router(router)
    # The endpoint uses auth_utils.get_current_user
    app.dependency_overrides[get_current_user] = lambda: user
    return app

# ═══════════════════════════════════════════════════════════════════════════════
# Endpoint Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestEndpoints:

    def test_secret_masking(self):
        from cloud_integrations_endpoints import router
        integration = {
            "_id": "i1",
            "id": "i1", "tenant_id": "t1", "provider": "oci_cloud_guard",
            "config": {
                "oci_tenancy_ocid": "ocid1.tenancy..",
                "oci_private_key": "---BEGIN PRIVATE KEY---...",
                "access_key_secret": "supersecret",
                "cf_api_token": "tokentokentoken",
            }
        }
        col = _col()
        col.find.return_value.to_list = AsyncMock(return_value=[integration])
        db = _db(cloud_integrations=col)
        app = _app(router, _user(role="admin"))

        with patch("cloud_integrations_endpoints.get_database", return_value=db):
            res = TestClient(app).get("/api/cloud-integrations")

        assert res.status_code == 200
        res_config = res.json()["integrations"][0]["config"]
        assert res_config["oci_private_key"] == "***CONFIGURED***"
        assert res_config["access_key_secret"] == "***CONFIGURED***"
        assert res_config["cf_api_token"] == "***CONFIGURED***"
        assert "BEGIN PRIVATE KEY" not in res.text

    def test_test_integration_endpoint(self):
        from cloud_integrations_endpoints import router
        integration = {"id": "i1", "tenant_id": "t1", "provider": "oci_cloud_guard", "config": {}}
        col = _col(find_one=AsyncMock(return_value=integration))
        db = _db(cloud_integrations=col)
        app = _app(router, _user(role="admin"))

        with patch("cloud_integrations_endpoints.get_database", return_value=db), \
             patch("oci_ingest.poll_oci_cloud_guard_problems", new_callable=AsyncMock) as mock_poll:
            mock_poll.return_value = 5
            res = TestClient(app).post("/api/cloud-integrations/i1/test")

        assert res.status_code == 200
        assert res.json()["events_ingested"] == 5
        mock_poll.assert_called_once()
