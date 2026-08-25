"""Tests for CycloneDX SBOM export endpoint."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from starlette.testclient import TestClient


def _mkuser(t="tenant-a", r="admin"):
    u = MagicMock()
    u.tenant_id = t
    u.role = r
    return u


def _mkdb():
    db = MagicMock()
    db._db = db  # DB-F10: rbac_service.find_role_doc bypasses the wrapper via db._db for global-role fallback lookups; set before use below
    c = MagicMock()
    c.find_one = AsyncMock(return_value=None)
    db._db.container_scan_results = c
    # rbac_service.get_database falls back to in-memory roles
    db.roles = MagicMock()
    db.roles.find_one = AsyncMock(return_value=None)
    return db


def _build(module_name, mock_db, user):
    import importlib
    mod = importlib.import_module(module_name)
    from authentication_service import get_current_user
    app = FastAPI()
    app.include_router(mod.router)
    t = MagicMock()
    t.tenant_id = user.tenant_id
    t.role = user.role
    app.dependency_overrides[get_current_user] = lambda: t
    patcher = patch(f"{module_name}.get_database", return_value=mock_db)
    patcher.start()
    rbac_patcher = patch("rbac_service.get_database", return_value=mock_db)
    rbac_patcher.start()
    return TestClient(app, raise_server_exceptions=False)


def _mock_scan_result(scan_id, tenant_id, simulated=False):
    return {
        "scan_id": scan_id,
        "tenantId": tenant_id,
        "image": "nginx:latest",
        "trivy": False,
        "simulated": simulated,
        "vulns": [
            {
                "id": "CVE-2024-1234",
                "pkg_name": "openssl",
                "installed_version": "3.0.2",
                "fixed_version": "3.0.3",
                "severity": "HIGH",
                "title": "OpenSSL vulnerability",
                "description": "Buffer overflow in OpenSSL"
            },
            {
                "id": "CVE-2024-5678",
                "pkg_name": "openssl",
                "installed_version": "3.0.2",
                "fixed_version": "3.0.3",
                "severity": "CRITICAL",
                "title": "Another OpenSSL vuln",
                "description": "Heartbleed-like"
            },
            {
                "id": "CVE-2024-9999",
                "pkg_name": "zlib",
                "installed_version": "1.2.13",
                "fixed_version": "1.2.14",
                "severity": "MEDIUM",
                "title": "zlib issue",
                "description": "Compression bug"
            },
        ],
        "total": 3,
        "critical": 1,
        "high": 1,
        "medium": 1,
        "low": 0,
        "scanned_at": "2026-01-01T00:00:00Z",
    }


class TestCycloneDXSbomExport:
    def setup_method(self):
        self.user = _mkuser("tenant-a", "admin")
        self.db = _mkdb()
        self.client = _build("container_scanner_endpoints", self.db, self.user)

    def test_structure(self):
        """GET /api/container/results/{scan_id}/sbom returns 200 with valid CycloneDX structure."""
        mock_scan = _mock_scan_result("scan123", self.user.tenant_id)
        self.db._db.container_scan_results.find_one.return_value = mock_scan

        resp = self.client.get("/api/container/results/scan123/sbom")

        assert resp.status_code == 200
        body = resp.json()
        assert "bomFormat" in body
        assert body["bomFormat"] == "CycloneDX"
        assert "specVersion" in body
        assert body["specVersion"] == "1.6"
        assert "serialNumber" in body
        assert body["serialNumber"].startswith("urn:uuid:")
        assert "version" in body
        assert isinstance(body["version"], int)
        assert "metadata" in body
        assert body["metadata"]["component"]["type"] == "container"
        assert "components" in body
        assert isinstance(body["components"], list)
        assert "vulnerabilities" in body
        assert isinstance(body["vulnerabilities"], list)

    def test_dedup_bomref_unique(self):
        """Multiple CVEs for same package/version → exactly one component entry with unique bom-ref."""
        mock_scan = _mock_scan_result("scan123", self.user.tenant_id)
        self.db._db.container_scan_results.find_one.return_value = mock_scan

        resp = self.client.get("/api/container/results/scan123/sbom")
        body = resp.json()

        # openssl 3.0.2 has 2 CVEs, zlib 1.2.13 has 1 CVE → 2 unique components
        comps = body["components"]
        assert len(comps) == 2
        bom_refs = [c["bom-ref"] for c in comps]
        assert len(set(bom_refs)) == 2, "bom-ref must be unique"
        # Each vuln references a component by bom-ref
        vulns = body["vulnerabilities"]
        for v in vulns:
            assert v["affects"][0]["ref"] in bom_refs

    def test_simulated_flag(self):
        """Simulated scan results include omniagent:simulated flag in metadata.properties."""
        mock_scan = _mock_scan_result("scan123", self.user.tenant_id, simulated=True)
        self.db._db.container_scan_results.find_one.return_value = mock_scan

        resp = self.client.get("/api/container/results/scan123/sbom")
        body = resp.json()

        assert resp.status_code == 200
        props = body.get("metadata", {}).get("properties", [])
        sim_prop = next((p for p in props if p.get("name") == "omniagent:simulated"), None)
        assert sim_prop is not None, "missing omniagent:simulated property"
        assert sim_prop["value"] == "true"

    def test_tenant_isolation(self):
        """Wrong-tenant scan_id returns 404 (no enumeration leak)."""
        # mock returns None for wrong tenant query
        self.db._db.container_scan_results.find_one.return_value = None

        resp = self.client.get("/api/container/results/other-tenant-scan/sbom")

        assert resp.status_code == 404
        assert "Scan result not found" in resp.json().get("detail", "")