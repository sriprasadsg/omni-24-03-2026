"""
Smoke tests for the refactored security and compliance endpoint sub-modules.

Each test mounts only the relevant router, patches get_database(), and
overrides get_current_user so no real MongoDB or JWT is required.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from authentication_service import get_current_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _app(router, user):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def _col(**kw):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="fake-id"))
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    col.find = MagicMock()
    col.find.return_value.to_list = AsyncMock(return_value=[])
    col.distinct = AsyncMock(return_value=[])
    col.aggregate = MagicMock()
    col.aggregate.return_value.to_list = AsyncMock(return_value=[])
    for k, v in kw.items():
        setattr(col, k, v)
    return col


def _db(*collection_names):
    db = MagicMock()
    for name in collection_names:
        setattr(db, name, _col())
    return db


# ===========================================================================
# security_cases_endpoints
# ===========================================================================

class TestSecurityCasesEndpoints:

    @pytest.fixture(autouse=True)
    def setup(self, tenant_user):
        import security_cases_endpoints as mod
        self.app = _app(mod.router, tenant_user)
        self.db = _db(
            "security_cases", "security_events", "vulnerability_scans",
            "assets",
        )

    def test_list_security_cases_returns_200(self):
        with patch("security_cases_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as client:
                resp = client.get("/api/security-cases")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_create_security_case_returns_case(self):
        with patch("security_cases_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as client:
                resp = client.post("/api/security-cases", json={"title": "Test Case"})
        assert resp.status_code == 200
        body = resp.json()
        assert "id" in body
        assert body["tenantId"] == "t1"

    def test_list_security_events_returns_200(self):
        with patch("security_cases_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as client:
                resp = client.get("/api/security-events")
        assert resp.status_code == 200

    def test_create_security_event_returns_event(self):
        with patch("security_cases_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as client:
                resp = client.post("/api/security-events", json={"title": "Suspicious login"})
        assert resp.status_code == 200
        body = resp.json()
        assert "id" in body

    def test_list_vulnerability_scans_returns_200(self):
        with patch("security_cases_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as client:
                resp = client.get("/api/vulnerability-scans")
        assert resp.status_code == 200

    def test_update_case_not_found_returns_404(self):
        self.db.security_cases.update_one = AsyncMock(
            return_value=MagicMock(matched_count=0)
        )
        with patch("security_cases_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as client:
                resp = client.put("/api/security-cases/nonexistent", json={"status": "Closed"})
        assert resp.status_code == 404

    def test_incident_impact_not_found_returns_404(self):
        with patch("security_cases_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as client:
                resp = client.get("/api/security/incident-impact/bad-id")
        assert resp.status_code == 404

    def test_incident_impact_no_assets_returns_graph(self):
        self.db.security_cases.find_one = AsyncMock(
            return_value={"id": "inc-1", "affectedAssets": []}
        )
        with patch("security_cases_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as client:
                resp = client.get("/api/security/incident-impact/inc-1")
        assert resp.status_code == 200
        body = resp.json()
        assert "nodes" in body and "edges" in body


# ===========================================================================
# security_scans_endpoints
# ===========================================================================

class TestSecurityScansEndpoints:

    @pytest.fixture(autouse=True)
    def setup(self, tenant_user):
        import security_scans_endpoints as mod
        import attack_path_endpoints as ap_mod
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(mod.router)
        app.include_router(ap_mod.router)
        app.dependency_overrides[get_current_user] = lambda: tenant_user
        self.app = app
        self._user = tenant_user
        self.db = _db("vulnerability_scan_jobs", "assets", "attack_paths", "patches", "alerts",
                      "vulnerabilities", "cspm_findings")

    def test_schedule_scan_creates_job(self):
        with patch("security_scans_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as client:
                resp = client.post(
                    "/api/vulnerability-scans/schedule",
                    json={"assetIds": ["a1", "a2"], "scanType": "Immediate"},
                )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "Queued"
        assert "id" in body

    def test_trigger_asset_scan_not_found_returns_404(self):
        self.db.assets.update_one = AsyncMock(return_value=MagicMock(matched_count=0))
        with patch("security_scans_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as client:
                resp = client.post("/api/assets/nonexistent/scan")
        assert resp.status_code == 404

    def test_trigger_asset_scan_success(self):
        with patch("security_scans_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as client:
                resp = client.post("/api/assets/asset-1/scan")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_get_attack_paths_returns_list(self):
        cursor = MagicMock()
        cursor.sort = MagicMock(return_value=cursor)
        cursor.to_list = AsyncMock(return_value=[])
        self.db.attack_paths.find = MagicMock(return_value=cursor)
        with patch("attack_path_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as client:
                resp = client.get("/api/security/attack-paths")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ===========================================================================
# security_ops_endpoints
# ===========================================================================

class TestSecurityOpsEndpoints:

    @pytest.fixture(autouse=True)
    def setup(self, tenant_user):
        import security_ops_endpoints as mod
        self.app = _app(mod.router, tenant_user)
        self.db = _db("security_audit_log", "agent_versions", "agents")

    def test_encrypt_data_returns_ciphertext(self):
        with patch("security_ops_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as client:
                resp = client.post("/api/security/encrypt", json={"plaintext": "hello"})
        assert resp.status_code == 200
        body = resp.json()
        assert "encrypted" in body
        assert body["algorithm"] == "AES-256-GCM"

    def test_audit_log_returns_events(self):
        self.db.security_audit_log.find = MagicMock()
        cursor = MagicMock()
        cursor.sort = MagicMock(return_value=cursor)
        cursor.limit = MagicMock(return_value=cursor)
        cursor.to_list = AsyncMock(return_value=[{"type": "login", "severity": "Info"}])
        self.db.security_audit_log.find.return_value = cursor

        with patch("security_ops_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as client:
                resp = client.get("/api/security/audit-log")
        assert resp.status_code == 200
        body = resp.json()
        assert "events" in body
        assert "count" in body

    def test_verify_integrity_unknown_version_returns_404(self, super_admin_user):
        # Use super_admin so the authorization check passes; unknown version gives 404
        import security_ops_endpoints as mod
        admin_app = _app(mod.router, super_admin_user)
        self.db.agent_versions.find_one = AsyncMock(return_value=None)
        with patch("security_ops_endpoints.get_database", return_value=self.db):
            with TestClient(admin_app) as client:
                resp = client.post(
                    "/api/agents/agent-1/verify-integrity",
                    json={"version": "1.0.0", "checksum": "abc"},
                )
        assert resp.status_code == 404


# ===========================================================================
# compliance_scans_endpoints
# ===========================================================================

class TestComplianceScanEndpoints:

    @pytest.fixture(autouse=True)
    def setup(self, tenant_user):
        import compliance_scans_endpoints as mod
        self.app = _app(mod.router, tenant_user)
        self.db = _db("agents", "agent_instructions", "assets")

    def test_broadcast_scan_returns_success(self):
        with patch("compliance_scans_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as client:
                resp = client.post("/api/compliance/fw1/scan")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_agent_scan_returns_instruction_id(self):
        with patch("compliance_scans_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as client:
                resp = client.post("/api/agents/agent-1/compliance/scan")
        assert resp.status_code == 200
        assert "instruction_id" in resp.json()

    def test_compliance_fix_returns_success(self):
        with patch("compliance_scans_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as client:
                resp = client.post(
                    "/api/agents/agent-1/compliance/fix",
                    data={"check_name": "disk_encryption"},
                )
        assert resp.status_code == 200
        assert resp.json()["success"] is True


# ===========================================================================
# compliance_framework_mgmt_endpoints
# ===========================================================================

class TestComplianceFrameworkMgmtEndpoints:

    @pytest.fixture(autouse=True)
    def setup(self, tenant_user):
        import compliance_framework_mgmt_endpoints as mod
        self.app = _app(mod.router, tenant_user)
        self.db = _db("compliance_frameworks")

    def test_get_frameworks_returns_list(self):
        self.db.compliance_frameworks.find = MagicMock()
        self.db.compliance_frameworks.find.return_value.to_list = AsyncMock(
            return_value=[{"id": "iso27001", "name": "ISO 27001"}]
        )
        with patch("compliance_framework_mgmt_endpoints.get_database", return_value=self.db), \
             patch("tenant_context.get_tenant_id", return_value="t1"):
            with TestClient(self.app) as client:
                resp = client.get("/api/compliance")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_add_control_missing_fields_returns_400(self):
        with patch("compliance_framework_mgmt_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as client:
                resp = client.post("/api/compliance/iso27001/controls", json={"description": "no id or name"})
        assert resp.status_code == 400

    def test_add_control_framework_not_found_returns_404(self):
        self.db.compliance_frameworks.update_one = AsyncMock(
            return_value=MagicMock(matched_count=0)
        )
        with patch("compliance_framework_mgmt_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as client:
                resp = client.post(
                    "/api/compliance/missing-fw/controls",
                    json={"id": "A.1.1", "name": "Access Control"},
                )
        assert resp.status_code == 404
