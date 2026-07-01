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


# ===========================================================================
# Patch instruction regression tests
# Verifies fixes for:
#   B1 — instruction docs include tenantId so agents can fetch them
#   B2 — instruction string is "install_patches" (not embedded KB list)
#   B3 — list_patches for super admin with no tenant param returns all patches
# ===========================================================================

class TestPatchInstructionFixes:

    @pytest.fixture(autouse=True)
    def setup(self, tenant_user):
        import patch_endpoints as mod
        self.app = _app(mod.router, tenant_user)
        self.db = _db(
            "patches", "vulnerability_scan_jobs", "patch_deployment_jobs",
            "agent_instructions", "agents", "local_repo", "software_inventory",
        )
        self.tenant_user = tenant_user

    # ── B1 + B2: create_deployment_job stores tenantId and "install_patches" ──

    @staticmethod
    def _async_cursor(items):
        """Return an object that supports `async for` iteration over items."""
        class _AsyncIter:
            def __init__(self, data):
                self._iter = iter(data)
            def __aiter__(self):
                return self
            async def __anext__(self):
                try:
                    return next(self._iter)
                except StopIteration:
                    raise StopAsyncIteration
        return _AsyncIter(items)

    def test_deploy_instruction_has_tenant_id_and_correct_format(self):
        """create_deployment_job must store tenantId and instruction='install_patches' in every doc."""
        captured: list[dict] = []

        async def _insert_many(docs, **kw):
            captured.extend(docs)
            return MagicMock()

        # patch_cursor uses `async for` (not .to_list), so we need a real async iterable
        self.db.patches.find.return_value = self._async_cursor([])
        # agent_cursor also uses `async for`
        self.db.agents.find.return_value = self._async_cursor(
            [{"id": "agent-1", "tenantId": "t1", "hostname": "host1", "assetId": None}]
        )
        self.db.agent_instructions.insert_many = AsyncMock(side_effect=_insert_many)

        with patch("patch_core_endpoints.get_database", return_value=self.db), \
             patch("patch_core_endpoints.asyncio.create_task"):
            with TestClient(self.app) as client:
                resp = client.post(
                    "/api/patches/deploy",
                    json={"patch_ids": ["KB001", "KB002"], "asset_ids": ["agent-1"],
                          "deployment_type": "Immediate", "tenantId": "t1"},
                )

        assert resp.status_code == 200
        assert captured, "No instruction docs were inserted"
        doc = captured[0]
        assert doc.get("tenantId") == "t1", f"tenantId missing or wrong: {doc}"
        assert doc.get("instruction") == "install_patches", f"Wrong instruction: {doc.get('instruction')!r}"
        payload = doc.get("payload", {})
        assert "patch_ids" in payload, "patch_ids not in payload"
        assert "job_id" in payload, "job_id not in payload"
        assert "id" in doc, "instruction doc missing id field"

    # ── B1: apply_os_patches stores tenantId and "install_patches" ────────────

    def test_apply_os_patches_instruction_has_tenant_id_and_correct_format(self):
        """apply_os_patches must store tenantId and instruction='install_patches'."""
        captured: list[dict] = []

        async def _insert_one(doc):
            captured.append(doc)
            return MagicMock(inserted_id="fake")

        self.db.agents.find_one = AsyncMock(return_value={"id": "agent-1", "tenantId": "t1"})
        self.db.agent_instructions.insert_one = AsyncMock(side_effect=_insert_one)

        with patch("patch_software_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as client:
                resp = client.post(
                    "/api/patches/apply-os-patches",
                    json={"agent_id": "agent-1", "patch_ids": ["KB001", "KB002"]},
                )

        assert resp.status_code == 200
        assert captured, "No instruction doc inserted"
        doc = captured[0]
        assert doc.get("tenantId") == "t1", f"tenantId missing: {doc}"
        assert doc.get("instruction") == "install_patches", f"Wrong instruction: {doc.get('instruction')!r}"
        payload = doc.get("payload", {})
        assert "patch_ids" in payload, "patch_ids missing from payload"

    # ── B1: apply_software_update stores tenantId ─────────────────────────────

    def test_apply_software_update_instruction_has_tenant_id(self):
        """apply_software_update must store tenantId so the agent can fetch it."""
        captured: list[dict] = []

        async def _insert_one(doc):
            captured.append(doc)
            return MagicMock(inserted_id="fake")

        self.db.agents.find_one = AsyncMock(return_value={"id": "agent-1", "tenantId": "t1"})
        self.db.local_repo.find_one = AsyncMock(return_value=None)
        self.db.agent_instructions.insert_one = AsyncMock(side_effect=_insert_one)

        with patch("patch_software_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as client:
                resp = client.post(
                    "/api/patches/apply-software-update",
                    json={"agent_id": "agent-1", "package_name": "openssl", "pkg_type": "apt"},
                )

        assert resp.status_code == 200
        assert captured, "No instruction doc inserted"
        doc = captured[0]
        assert doc.get("tenantId") == "t1", f"tenantId missing: {doc}"
        assert "upgrade_software:" in doc.get("instruction", "")

    # ── B3: list_patches for super admin with no tenant param returns all ─────

    def test_list_patches_super_admin_no_tenant_returns_all(self):
        """Super admin without ?tenant_id should see patches from all tenants (empty filter)."""
        from auth_types import TokenData
        from authentication_service import get_current_user as _gcu
        import patch_endpoints as mod

        super_admin = TokenData(username="sa@platform.com", role="Super Admin", tenant_id=None)
        app = _app(mod.router, super_admin)

        all_patches = [
            {"id": "p1", "tenantId": "tenant-a"},
            {"id": "p2", "tenantId": "tenant-b"},
        ]
        db = _db("patches", "vulnerability_scan_jobs", "patch_deployment_jobs",
                 "agent_instructions", "agents")
        db.patches.find.return_value.to_list = AsyncMock(return_value=all_patches)

        query_used: list[dict] = []
        original_find = db.patches.find

        def _tracking_find(q, *a, **kw):
            query_used.append(q)
            return original_find(q, *a, **kw)

        db.patches.find = _tracking_find
        db.patches.find.return_value = original_find.return_value

        with patch("patch_core_endpoints.get_database", return_value=db):
            with TestClient(app) as client:
                resp = client.get("/api/patches")

        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        # The query must NOT filter by tenantId when super admin has no tenant param
        if query_used:
            assert "tenantId" not in query_used[0], (
                f"Super admin should not have tenantId filter, got: {query_used[0]}"
            )
