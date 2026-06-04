"""
Smoke tests for the three highest-priority untested endpoint modules:
  - agent_core_endpoints  (GET /api/agents, search, bulk-patch, diagnostics)
  - patch_endpoints       (list, deploy, CVE lookup)
  - vuln_endpoints        (list, stats, scan, resolve)

These tests mount only the relevant router, patch get_database() and any
required services so no real MongoDB, cache, or external services are needed.
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
    col.update_many = AsyncMock(return_value=MagicMock(modified_count=0))
    col.count_documents = AsyncMock(return_value=0)
    col.find = MagicMock()
    col.find.return_value.skip = MagicMock(return_value=MagicMock())
    col.find.return_value.skip.return_value.limit = MagicMock(return_value=MagicMock())
    col.find.return_value.skip.return_value.limit.return_value.to_list = AsyncMock(return_value=[])
    col.find.return_value.to_list = AsyncMock(return_value=[])
    col.distinct = AsyncMock(return_value=[])
    for k, v in kw.items():
        setattr(col, k, v)
    return col


def _db(*names):
    db = MagicMock()
    for name in names:
        setattr(db, name, _col())
    db.__getitem__ = MagicMock(side_effect=lambda k: getattr(db, k, _col()))
    return db


# ===========================================================================
# agent_core_endpoints
# ===========================================================================

class TestAgentCoreEndpoints:
    """
    agent_core_endpoints uses Depends(get_database), so we override the
    dependency rather than patching the module-level symbol.
    """

    def _make_app(self, user, db):
        import agent_core_endpoints as mod
        from database import get_database as _gdb
        with patch("cache_service.cached", lambda **kw: lambda f: f):
            app = FastAPI()
            app.include_router(mod.router)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[_gdb] = lambda: db
        return app

    def test_list_agents_returns_200(self, tenant_user):
        db = _db("agents")
        paged = {"items": [], "total": 0, "page": 1, "pageSize": 50, "totalPages": 0, "hasNext": False, "hasPrev": False}
        app = self._make_app(tenant_user, db)
        mock_paginate = AsyncMock(return_value=paged)
        with patch("agent_core_endpoints.paginate_mongo_query", mock_paginate):
            with TestClient(app) as client:
                resp = client.get("/api/agents")
        assert resp.status_code == 200
        assert isinstance(resp.json(), (list, dict))

    def test_search_agents_returns_200(self, tenant_user):
        db = _db("agents")
        app = self._make_app(tenant_user, db)
        with TestClient(app) as client:
            resp = client.get("/api/agents/search?q=web")
        assert resp.status_code == 200

    def test_bulk_delete_no_ids_returns_error(self, tenant_user):
        db = _db("agents")
        app = self._make_app(tenant_user, db)
        with TestClient(app) as client:
            resp = client.delete("/api/agents/bulk", params={"agent_ids": []})
        assert resp.status_code in (400, 422)

    def test_diagnostics_agent_not_found_returns_404(self, tenant_user):
        db = _db("agents", "agent_instructions")
        db.agents.find_one = AsyncMock(return_value=None)
        app = self._make_app(tenant_user, db)
        with patch("agent_core_endpoints.get_database", return_value=db):
            with TestClient(app) as client:
                resp = client.post("/api/agents/nonexistent/diagnostics")
        assert resp.status_code == 404


# ===========================================================================
# patch_endpoints
# ===========================================================================

class TestPatchEndpoints:

    @pytest.fixture(autouse=True)
    def setup(self, tenant_user):
        import patch_endpoints as mod
        self.app = _app(mod.router, tenant_user)
        self.db = _db("patches", "vulnerability_scan_jobs", "patch_deployment_jobs", "agent_instructions", "agents")

    def test_list_patches_returns_200(self):
        with patch("patch_core_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as client:
                resp = client.get("/api/patches")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_patches_no_tenant_returns_403(self):
        from auth_types import TokenData
        from authentication_service import get_current_user
        no_tenant_user = TokenData(username="u", role="Viewer", tenant_id=None)
        import patch_endpoints as mod
        app = FastAPI()
        app.include_router(mod.router)
        app.dependency_overrides[get_current_user] = lambda: no_tenant_user
        with patch("patch_core_endpoints.get_database", return_value=self.db):
            with TestClient(app) as client:
                resp = client.get("/api/patches")
        assert resp.status_code == 403

    def test_deploy_patches_returns_job(self):
        with patch("patch_core_endpoints.get_database", return_value=self.db), \
             patch("patch_core_endpoints.asyncio.create_task"):
            with TestClient(self.app) as client:
                resp = client.post(
                    "/api/patches/deploy",
                    json={
                        "patch_ids": ["p1", "p2"],
                        "asset_ids": ["a1"],
                        "deployment_type": "Immediate",
                        "tenantId": "t1",
                    },
                )
        assert resp.status_code == 200
        body = resp.json()
        assert "id" in body or "job_id" in body or "success" in body

    def test_cve_lookup_not_found_returns_404(self):
        from unittest.mock import MagicMock
        mock_svc = MagicMock()
        mock_svc.get_cve_details = AsyncMock(return_value=None)
        with patch("patch_enrichment_endpoints.get_patch_service", return_value=mock_svc):
            with TestClient(self.app) as client:
                resp = client.get("/api/patches/cve/CVE-9999-0000")
        assert resp.status_code == 404

    def test_get_deployment_jobs_returns_list(self):
        self.db.patch_deployment_jobs = _col()
        self.db.patch_deployment_jobs.find.return_value.to_list = AsyncMock(
            return_value=[{"id": "job-1", "status": "Completed"}]
        )
        with patch("patch_core_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as client:
                resp = client.get("/api/patches/deployment-jobs")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ===========================================================================
# vuln_endpoints
# ===========================================================================

class TestVulnEndpoints:

    @pytest.fixture(autouse=True)
    def setup(self, tenant_user):
        import vuln_endpoints as mod
        # Patch has_permission at the module level so it never calls get_database
        with patch("rbac_service.RBACService.has_permission", return_value=lambda: tenant_user):
            import importlib
            importlib.reload(mod)
            app = FastAPI()
            app.include_router(mod.router)
        app.dependency_overrides[get_current_user] = lambda: tenant_user
        self.app = app
        self.user = tenant_user

    def _patch_vuln_service(self, **methods):
        defaults = {
            "get_vulnerabilities": AsyncMock(return_value={"items": [], "total": 0, "page": 1}),
            "get_vulnerability_stats": AsyncMock(return_value={"Critical": 0, "High": 0}),
            "scan_vulnerabilities": AsyncMock(return_value={"scanned": 0}),
            "apply_patch": AsyncMock(return_value={"success": True}),
            "resolve_vulnerability": AsyncMock(return_value={"success": True}),
        }
        defaults.update(methods)
        svc = MagicMock()
        for k, v in defaults.items():
            setattr(svc, k, v)
        return svc

    def test_list_vulnerabilities_returns_200(self):
        svc = self._patch_vuln_service()
        with patch("vuln_endpoints.vuln_service", svc), \
             patch("vuln_endpoints.get_tenant_id", return_value="t1"):
            with TestClient(self.app) as client:
                resp = client.get("/api/vulnerabilities")
        assert resp.status_code == 200

    def test_vuln_stats_returns_200(self):
        svc = self._patch_vuln_service()
        with patch("vuln_endpoints.vuln_service", svc), \
             patch("vuln_endpoints.get_tenant_id", return_value="t1"):
            with TestClient(self.app) as client:
                resp = client.get("/api/vulnerabilities/stats")
        assert resp.status_code == 200

    def test_scan_vulnerabilities_returns_200(self):
        db = _db("vulnerability_scans")
        svc = self._patch_vuln_service()
        with patch("vuln_endpoints.vuln_service", svc), \
             patch("vuln_endpoints.get_database", return_value=db), \
             patch("vuln_endpoints.get_tenant_id", return_value="t1"):
            with TestClient(self.app) as client:
                resp = client.post(
                    "/api/vulnerabilities/scan",
                    json={"scan_type": "Full", "assets": ["asset-1"]},
                )
        assert resp.status_code == 200

    def test_apply_patch_invalid_id_returns_400(self):
        svc = self._patch_vuln_service()
        with patch("vuln_endpoints.vuln_service", svc), \
             patch("vuln_endpoints.get_tenant_id", return_value="t1"):
            with TestClient(self.app) as client:
                # ID containing path traversal chars should be rejected
                resp = client.post("/api/vulnerabilities/../../../etc/passwd/apply-patch")
        assert resp.status_code in (400, 404, 422)

    def test_resolve_vulnerability_returns_200(self):
        db = _db("vulnerabilities")
        db.vulnerabilities.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
        svc = self._patch_vuln_service()
        with patch("vuln_endpoints.vuln_service", svc), \
             patch("vuln_endpoints.get_database", return_value=db), \
             patch("vuln_endpoints.get_tenant_id", return_value="t1"):
            with TestClient(self.app) as client:
                resp = client.post("/api/vulnerabilities/vuln-123/resolve")
        assert resp.status_code == 200
